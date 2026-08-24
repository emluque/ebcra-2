import logging

from scraper.playwright_base import BasePlaywrightScraper, ScraperError

logger = logging.getLogger(__name__)

PAGE_URL = "https://es.finance.yahoo.com/quote/%5EMERV/history/"
TABLE_ROW_SELECTOR = "tbody tr"

MONTHS = {
    "ene": "01", "feb": "02", "mar": "03", "abr": "04",
    "may": "05", "jun": "06", "jul": "07", "ago": "08",
    "sep": "09", "oct": "10", "nov": "11", "dic": "12",
}


class YahooAPIError(Exception):
    pass


class YahooClient(BasePlaywrightScraper):
    def fetch_merval(self) -> list[dict]:
        """
        Render the Yahoo Finance MERVAL history page and extract close prices.
        Returns list of {"date": "YYYY-MM-DD", "value": str}.
        """
        try:
            raw_rows = self.fetch_raw_rows(PAGE_URL, TABLE_ROW_SELECTOR, min_cells=5)
        except ScraperError as exc:
            raise YahooAPIError(str(exc)) from exc

        records = []
        for cells in raw_rows:
            date_raw = cells[0]
            close_raw = cells[4]
            try:
                records.append({
                    "date": _parse_date(date_raw),
                    "value": _parse_number(close_raw),
                })
            except (ValueError, KeyError) as exc:
                logger.warning("Skipping row with date %r: %s", date_raw, exc)

        logger.debug("Yahoo Merval: scraped %d records", len(records))
        return records


def _parse_date(date_str: str) -> str:
    """Convert '23 mar 2026' to '2026-03-23'."""
    parts = date_str.split()
    if len(parts) != 3:
        raise ValueError(f"Unexpected date format: {date_str!r}")
    day, month_abbr, year = parts
    month = MONTHS[month_abbr.lower()]
    return f"{year}-{month}-{int(day):02d}"


def _parse_number(text: str) -> str:
    """Convert '2.778.025,00' to '2778025.0'."""
    return str(float(text.replace(".", "").replace(",", ".")))
