import logging

from scraper.playwright_base import BasePlaywrightScraper, ScraperError

logger = logging.getLogger(__name__)

PAGE_URL = "https://www.ambito.com/contenidos/dolar-informal-historico.html"
TABLE_ROW_SELECTOR = "table.general-historical__table tbody.general-historical__tbody tr"


class AmbitoAPIError(Exception):
    pass


class AmbitoClient(BasePlaywrightScraper):
    def fetch_dollar_blue(self) -> list[dict]:
        """
        Render the Ambito Dollar Blue historical page and extract venta (sell) prices.
        Returns list of {"date": "YYYY-MM-DD", "value": str}.
        """
        try:
            raw_rows = self.fetch_raw_rows(PAGE_URL, TABLE_ROW_SELECTOR, min_cells=3)
        except ScraperError as exc:
            raise AmbitoAPIError(str(exc)) from exc

        records = []
        for cells in raw_rows:
            date_raw = cells[0]
            venta_raw = cells[2]
            try:
                records.append({
                    "date": _parse_date(date_raw),
                    "value": venta_raw.replace(",", "."),
                })
            except ValueError as exc:
                logger.warning("Skipping row with date %r: %s", date_raw, exc)

        logger.debug("Ambito: scraped %d records", len(records))
        return records


def _parse_date(date_str: str) -> str:
    """Convert DD/MM/YYYY to YYYY-MM-DD."""
    parts = date_str.split("/")
    if len(parts) != 3:
        raise ValueError(f"Unexpected date format: {date_str!r}")
    day, month, year = parts
    return f"{year}-{month}-{day}"
