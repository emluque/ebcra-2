from scraper.db import DBConnection
from scraper.web_pipeline import _run_web_scraper
from yahoo.client import YahooAPIError, YahooClient

TABLE_NAME = "merval_yahoo"


def run_yahoo(conn: DBConnection) -> bool:
    """Fetch all Yahoo Finance MERVAL history and insert new records."""
    return _run_web_scraper(
        conn=conn,
        client=YahooClient(),
        api_error_type=YahooAPIError,
        table_name=TABLE_NAME,
        fetch_method="fetch_merval",
        dedup_strategy="first",
        label="Yahoo Merval",
    )
