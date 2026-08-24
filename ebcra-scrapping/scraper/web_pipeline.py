import datetime
import logging

from scraper.db import DBConnection, deduplicate, upsert_records

logger = logging.getLogger(__name__)


def _run_web_scraper(
    conn: DBConnection,
    client,
    api_error_type: type,
    table_name: str,
    fetch_method: str,
    dedup_strategy: str,
    label: str,
) -> bool:
    """Shared logic for Playwright-based web scrapers (Ambito, Yahoo)."""
    try:
        records = getattr(client, fetch_method)()
        logger.info("%s: fetched %d records", label, len(records))

        records = deduplicate(records, strategy=dedup_strategy)
        logger.info("%s: %d records after deduplication", label, len(records))

        today = datetime.date.today().isoformat()
        records = [r for r in records if r["date"] != today]
        logger.info("%s: %d records after skipping today", label, len(records))

        inserted = upsert_records(conn, table_name, records)
        logger.info("%s (%s): %d record(s) upserted", label, table_name, inserted)
        return True

    except api_error_type as exc:
        logger.error("%s: API error — %s", label, exc)
        return False

    except Exception as exc:
        logger.error("%s: unexpected error — %s", label, exc)
        return False
