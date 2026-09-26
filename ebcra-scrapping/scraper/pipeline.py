import datetime
import logging

from scraper.api_client import BCRAAPIError, BCRAClient
from scraper.db import DELTA_LOOKBACK_DAYS, DBConnection, get_max_date, record_scrape_status, upsert_records

logger = logging.getLogger(__name__)


def run_variable(
    client: BCRAClient,
    conn: DBConnection,
    variable_id: int,
    table_name: str,
    full_refresh: bool = False,
) -> bool:
    source_url = f"{client.base_url}/estadisticas/v4.0/Monetarias/{variable_id}"
    try:
        desde = None
        if not full_refresh:
            desde = get_max_date(conn, table_name)
            if desde:
                # Some series (CER, UVA, UVI, ICL) are published ahead of
                # time, so MAX(date) can be in the future. The API rejects a
                # future Desde with a 400; cap at yesterday to stay clear of
                # UTC-vs-Argentina date skew on the host.
                desde = str(min(
                    datetime.date.fromisoformat(desde) - datetime.timedelta(days=DELTA_LOOKBACK_DAYS),
                    datetime.date.today() - datetime.timedelta(days=1),
                ))
            if desde:
                logger.info(
                    "Variable %d (%s): delta fetch from %s",
                    variable_id, table_name, desde,
                )
            else:
                logger.info(
                    "Variable %d (%s): full backfill (empty table)",
                    variable_id, table_name,
                )
        else:
            logger.info(
                "Variable %d (%s): full refresh requested",
                variable_id, table_name,
            )

        raw_records = client.fetch_variable(variable_id, desde=desde)

        records = [{"date": r["fecha"], "value": r["valor"]} for r in raw_records]

        affected = upsert_records(conn, table_name, records)
        logger.info(
            "Variable %d (%s): %d record(s) upserted",
            variable_id, table_name, affected,
        )
        record_scrape_status(
            conn, table_name, "bcra_variable",
            ok=True, variable_id=variable_id, source_url=source_url,
        )
        return True

    except BCRAAPIError as exc:
        if exc.status_code in (400, 404):
            logger.warning(
                "Variable %d (%s): skipped — API returned %s",
                variable_id, table_name, exc.status_code,
            )
        else:
            logger.error(
                "Variable %d (%s): API error — %s",
                variable_id, table_name, exc,
            )
        record_scrape_status(
            conn, table_name, "bcra_variable",
            ok=False, variable_id=variable_id, source_url=source_url,
            error_code=str(exc.status_code) if exc.status_code else None,
            error_message=str(exc),
        )
        return False

    except Exception as exc:
        logger.error(
            "Variable %d (%s): unexpected error — %s",
            variable_id, table_name, exc,
        )
        record_scrape_status(
            conn, table_name, "bcra_variable",
            ok=False, variable_id=variable_id, source_url=source_url,
            error_message=str(exc),
        )
        return False
