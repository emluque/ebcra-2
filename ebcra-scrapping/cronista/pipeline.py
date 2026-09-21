from cronista.client import CronistaAPIError, CronistaClient
from scraper.db import DBConnection
from scraper.web_pipeline import _run_web_scraper

# Shared with the legacy pre-2019 Cronista rows: same table, disjoint date
# ranges (see scraper/constants.py).
TABLE_NAME = "dollar_blue_cronista"


def run_cronista(conn: DBConnection) -> bool:
    """Fetch Cronista's visible Dollar Blue history and upsert new records."""
    return _run_web_scraper(
        conn=conn,
        client=CronistaClient(),
        api_error_type=CronistaAPIError,
        table_name=TABLE_NAME,
        fetch_method="fetch_dollar_blue",
        dedup_strategy="max",
        label="Cronista Dollar Blue",
    )
