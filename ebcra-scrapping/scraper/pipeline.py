import datetime
import logging

from scraper.api_client import BCRAAPIError, BCRAClient
from scraper.db import DELTA_LOOKBACK_DAYS, DBConnection, get_max_date, upsert_records

logger = logging.getLogger(__name__)


def run_variable(
    client: BCRAClient,
    conn: DBConnection,
    variable_id: int,
    table_name: str,
    full_refresh: bool = False,
) -> bool:
    try:
        desde = None
        if not full_refresh:
            desde = get_max_date(conn, table_name)
            if desde:
                desde = str(
                    datetime.date.fromisoformat(desde) - datetime.timedelta(days=DELTA_LOOKBACK_DAYS)
                )
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
        return False

    except Exception as exc:
        logger.error(
            "Variable %d (%s): unexpected error — %s",
            variable_id, table_name, exc,
        )
        return False
