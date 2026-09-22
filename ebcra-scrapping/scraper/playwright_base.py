import logging
import random
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

# A single bounded retry on failure, with randomized backoff — not zero
# (transient hiccups shouldn't fail a whole run), not unbounded (repeatedly
# hammering a target that's actively challenging/blocking us is exactly the
# bot-like behavior this hardening is meant to avoid). The backoff is
# randomized, not fixed, so a retry doesn't itself look like a
# metronomic, scripted pattern.
_RETRY_BACKOFF_SECONDS = (60, 180)

# Where per-scraper session state (cookies, local storage) is persisted
# between runs, keyed by label — so a scraper looks like a continuing
# session rather than a brand-new anonymous client on every run. Resolves
# relative to this file so it lands at ebcra-scrapping/.playwright-state
# regardless of CWD (matches the Docker image's WORKDIR too). Gitignored.
#
# NOTE: this directory must be a mounted volume (see
# ebcra-setup/docker-compose.yml) to survive image rebuilds; otherwise
# session continuity resets on every rebuild.
STATE_DIR = Path(__file__).resolve().parent.parent / ".playwright-state"

# Named (not inline) so diagnostic scripts can import the exact same launch
# args instead of keeping a second, driftable copy.
LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--use-gl=swiftshader",
]

# Playwright's `headless` only accepts a boolean (a string like "new" is
# rejected). With headless=True the default is chromium-headless-shell, the
# stripped-down legacy-style build; channel="chromium" opts into the full
# Chromium in its new headless mode, which renders and fingerprints much
# closer to a real Chrome. Needs the full Chromium build installed
# (`playwright install chromium` installs it alongside the shell).
LAUNCH_OPTIONS = {
    "headless": True,
    "channel": "chromium",
    "args": LAUNCH_ARGS,
}

# Context is deliberately NOT a fully-matched geographic persona (Argentine
# locale + Argentine timezone). timezone_id is a JS/OS-level signal
# (Intl.DateTimeFormat().resolvedOptions().timeZone) that CDN bot mitigation
# commonly cross-checks against IP geolocation, so it should match wherever
# the scraper's traffic actually egresses from. locale (and the
# Accept-Language header Playwright derives from it) has no such tie — it's
# a soft, self-reported preference real users routinely set independent of
# their location — so it stays es-AR, consistent with the Spanish-language
# target site.
CONTEXT_OPTIONS = {
    "locale": "es-AR",
    # Set this to the IANA timezone of the egress IP's region.
    "timezone_id": "America/Toronto",
    "viewport": {"width": 1920, "height": 1080},
}

# Deliberately no manual user_agent override and no hand-crafted Sec-CH-UA*
# headers here. The new headless mode (LAUNCH_OPTIONS) already makes Chromium report its
# true, non-"HeadlessChrome" UA matching its actual bundled build, and the
# browser generates its own Sec-CH-UA Client Hints consistent with that same
# real build automatically. Hand-setting an invented Chrome version would
# make the UA and the browser's own native Client Hints disagree with each
# other — the same class of self-inflicted mismatch as the timezone/IP
# issue above, and just as counterproductive.

# Neutralizes the one automation tell that's cheap and durable to patch.
# Deliberately not a full stealth plugin (e.g. playwright-extra-stealth) —
# that's an ongoing arms race against evolving
# bot-mitigation heuristics; this plus new headless mode, GPU rendering, and
# session continuity covers the durable wins without that upkeep burden.
_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
"""


class ScraperError(Exception):
    pass


class BasePlaywrightScraper:
    def __init__(self, timeout: int = 60000, label: str | None = None):
        self.timeout = timeout  # milliseconds
        self.label = label or type(self).__name__

    def _state_path(self) -> Path:
        return STATE_DIR / f"{self.label}.json"

    def fetch_raw_rows(self, url: str, row_selector: str, min_cells: int = 1) -> list[list[str]]:
        """Launch a headless browser, navigate to url, and return cell text for each matching row.

        Each element of the returned list is a list of stripped cell text strings for one row.
        Rows with fewer than min_cells cells are skipped.
        Raises ScraperError on timeout or any other browser/navigation failure,
        after one bounded retry with backoff (see _RETRY_BACKOFF_SECONDS).
        """
        def _extract(page):
            rows = page.query_selector_all(row_selector)
            result = []
            for row in rows:
                cells = row.query_selector_all("td")
                if len(cells) < min_cells:
                    continue
                result.append([cell.inner_text().strip() for cell in cells])
            return result

        return self._fetch_with_retry(url, row_selector, _extract)

    def fetch_rendered_html(self, url: str, wait_selector: str) -> str:
        """Launch a headless browser, navigate to url, wait for wait_selector
        to render, and return the full rendered page HTML (page.content()).

        For scrapers whose data lives embedded in the page source (e.g. a
        script tag) rather than in visible table rows — fetch_raw_rows
        doesn't fit those since there's nothing to run a row/cell selector
        over. wait_selector should still be something a real visitor would
        see appear, both to look like normal browsing and to double as a
        challenge/interstitial detector, same as fetch_raw_rows's row_selector.
        Same retry policy as fetch_raw_rows.
        """
        return self._fetch_with_retry(url, wait_selector, lambda page: page.content())

    def _fetch_with_retry(self, url: str, wait_selector: str, extract):
        last_exc: ScraperError | None = None
        for attempt in range(2):
            if attempt:
                backoff = random.uniform(*_RETRY_BACKOFF_SECONDS)
                logger.warning(
                    "%s: retrying after %.0fs backoff (attempt %d/2) following: %s",
                    url, backoff, attempt + 1, last_exc,
                )
                time.sleep(backoff)
            try:
                return self._fetch_once(url, wait_selector, extract)
            except ScraperError as exc:
                last_exc = exc
        raise last_exc

    def _fetch_once(self, url: str, wait_selector: str, extract):
        """One full browser launch + navigate + read cycle. See fetch_raw_rows/
        fetch_rendered_html for the retry policy wrapping this."""
        state_path = self._state_path()

        with sync_playwright() as p:
            browser = p.chromium.launch(**LAUNCH_OPTIONS)
            context_kwargs = dict(CONTEXT_OPTIONS)
            if state_path.exists():
                context_kwargs["storage_state"] = str(state_path)

            context = browser.new_context(**context_kwargs)
            context.add_init_script(_INIT_SCRIPT)
            page = context.new_page()
            try:
                # goto()'s default wait_until="load" already waits for the
                # full load event (not just navigation); wait_for_selector
                # below then waits for a real, visible element before
                # reading anything — matching how a real browser session
                # pauses before interacting, and doubling as a
                # challenge/interstitial detector: if the expected content
                # never shows, that timeout is the signal.
                page.goto(url, timeout=self.timeout)
                page.wait_for_selector(wait_selector, timeout=self.timeout)

                result = extract(page)

                # Persist session state only on success, so a failed/blocked
                # run doesn't clobber the last known-good cookies with a
                # broken or challenged session.
                state_path.parent.mkdir(parents=True, exist_ok=True)
                context.storage_state(path=str(state_path))
                return result

            except PlaywrightTimeoutError as exc:
                raise ScraperError(
                    f"Timed out waiting for {wait_selector!r}: {exc}"
                ) from exc
            except ScraperError:
                raise
            except Exception as exc:
                raise ScraperError(f"Error scraping {url}: {exc}") from exc
            finally:
                page.close()
                context.close()
                browser.close()
