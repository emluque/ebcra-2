from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


class ScraperError(Exception):
    pass


class BasePlaywrightScraper:
    def __init__(self, timeout: int = 60000):
        self.timeout = timeout  # milliseconds

    def fetch_raw_rows(self, url: str, row_selector: str, min_cells: int = 1) -> list[list[str]]:
        """Launch a headless browser, navigate to url, and return cell text for each matching row.

        Each element of the returned list is a list of stripped cell text strings for one row.
        Rows with fewer than min_cells cells are skipped.
        Raises ScraperError on timeout or any other browser/navigation failure.
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            try:
                page = browser.new_page()
                page.goto(url, timeout=self.timeout)
                page.wait_for_selector(row_selector, timeout=self.timeout)

                rows = page.query_selector_all(row_selector)
                result = []
                for row in rows:
                    cells = row.query_selector_all("td")
                    if len(cells) < min_cells:
                        continue
                    result.append([cell.inner_text().strip() for cell in cells])
                return result

            except PlaywrightTimeoutError as exc:
                raise ScraperError(
                    f"Timed out waiting for {row_selector!r}: {exc}"
                ) from exc
            except ScraperError:
                raise
            except Exception as exc:
                raise ScraperError(f"Error scraping {url}: {exc}") from exc
            finally:
                page.close()
                browser.close()
