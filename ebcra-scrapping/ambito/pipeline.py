from ambito.client import AmbitoAPIError, AmbitoClient
from scraper.db import DBConnection
from scraper.web_pipeline import _run_web_scraper

TABLE_NAME = "dollar_blue_ambito"


def run_ambito(conn: DBConnection) -> bool:
    """Fetch all Ambito Dollar Blue history and insert new records."""
    return _run_web_scraper(
        conn=conn,
        client=AmbitoClient(),
        api_error_type=AmbitoAPIError,
        table_name=TABLE_NAME,
        fetch_method="fetch_dollar_blue",
        dedup_strategy="max",
        label="Ambito Dollar Blue",
    )
