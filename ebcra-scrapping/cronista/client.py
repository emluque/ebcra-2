import datetime
import json
import logging
import re

from scraper.constants import CRONISTA_LEGACY_END_DATE
from scraper.playwright_base import BasePlaywrightScraper, ScraperError

logger = logging.getLogger(__name__)

PAGE_URL = "https://www.cronista.com/MercadosOnline/moneda/ARSB/"

# The visible "Valor de venta" quote card. Server-rendered into the static
# page (no client-side hydration wait needed), and a real widget a human
# visiting the page would actually look at first. Waiting on it (rather than
# reading page.content() immediately after goto()) both mimics normal
# browsing and doubles as a challenge/interstitial detector: if this never
# renders, that timeout is the signal.
WAIT_SELECTOR = ".markets-online__card--sell"

# NOTE: the historical *chart* on this page is visually paywalled
# (`.markets-online__graph--paywall` in the markup) for anonymous visitors,
# but the underlying historical series is still delivered in the page's own
# Fusion.contentCache payload regardless — it's SSR/hydration data, not
# gated server-side (confirmed via a plain, unauthenticated fetch during
# recon). If Cronista ever tightens this to only embed a short window for
# anonymous visitors, this scraper should fail loudly rather than silently
# starving the unified series — see _MIN_EXPECTED_ROWS below.

_CACHE_MARKER = "Fusion.contentCache="
_DATE_RE = re.compile(r"/Date\((-?\d+)\)/")

# Sanity floor, not a real expectation of an exact count — the page has
# shown ~200 business days in practice. Guards against the paywall-tightening
# scenario above, or any other page-shape change that would otherwise pass
# silently as "fetched 0 records, upserted 0 rows" and look like a no-op.
_MIN_EXPECTED_ROWS = 30


class CronistaAPIError(Exception):
    pass


class CronistaClient(BasePlaywrightScraper):
    def fetch_dollar_blue(self) -> list[dict]:
        """
        Render the Cronista ARSB (Dollar Blue) page and extract the
        embedded historical series.
        Returns list of {"date": "YYYY-MM-DD", "value": str}.
        """
        try:
            html = self.fetch_rendered_html(PAGE_URL, WAIT_SELECTOR)
        except ScraperError as exc:
            raise CronistaAPIError(str(exc)) from exc

        historico = _extract_historico(html)
        if len(historico) < _MIN_EXPECTED_ROWS:
            raise CronistaAPIError(
                f"Expected at least {_MIN_EXPECTED_ROWS} historical rows, got "
                f"{len(historico)} — page shape may have changed"
            )

        records = _parse_records(historico)
        logger.debug("Cronista: scraped %d records", len(records))
        return records


def _extract_historico(html: str) -> list[dict]:
    """Pull ["markets-general"][<only entry>]["data"][0]["historico"] out of
    the page's Fusion.contentCache payload."""
    cache = _extract_balanced_json(html, _CACHE_MARKER)

    try:
        markets_general = cache["markets-general"]
    except KeyError as exc:
        raise CronistaAPIError("'markets-general' not found in Fusion.contentCache") from exc

    # Keyed by a JSON-encoded query string that embeds today's date — don't
    # hardcode it, just require there be exactly one entry.
    if len(markets_general) != 1:
        raise CronistaAPIError(
            f"Expected exactly one markets-general cache entry, found {len(markets_general)}"
        )
    entry = next(iter(markets_general.values()))

    try:
        data = entry["data"]
    except KeyError as exc:
        raise CronistaAPIError("markets-general entry has no 'data'") from exc

    if len(data) != 1:
        raise CronistaAPIError(f"Expected exactly one market entry, found {len(data)}")

    quote = data[0]
    if quote.get("UrlId") != "ARSB":
        raise CronistaAPIError(f"Unexpected UrlId in market entry: {quote.get('UrlId')!r}")

    try:
        return quote["historico"]
    except KeyError as exc:
        raise CronistaAPIError("Market entry has no 'historico'") from exc


def _extract_balanced_json(html: str, marker: str) -> dict:
    """Extract the JSON object assigned right after `marker` in `html`.

    Scans brace depth (respecting quoted strings) rather than searching for
    a fixed terminator string — the payload is large and could plausibly
    contain something that coincidentally matches a naive terminator.
    """
    start = html.find(marker)
    if start == -1:
        raise CronistaAPIError(f"Could not find {marker!r} in page source")

    brace_start = html.find("{", start)
    if brace_start == -1:
        raise CronistaAPIError(f"Could not find JSON object after {marker!r}")

    depth = 0
    in_string = False
    escape = False
    for i in range(brace_start, len(html)):
        ch = html[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                raw = html[brace_start:i + 1]
                try:
                    return json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise CronistaAPIError(f"Failed to parse JSON after {marker!r}: {exc}") from exc

    raise CronistaAPIError(f"Unterminated JSON object after {marker!r}")


def _parse_records(historico: list[dict]) -> list[dict]:
    records = []
    for row in historico:
        fecha_raw = row.get("Fecha", "")
        venta = row.get("Venta")

        match = _DATE_RE.match(fecha_raw)
        if not match:
            logger.warning("Skipping row with unparseable Fecha %r", fecha_raw)
            continue

        dt = datetime.datetime.fromtimestamp(int(match.group(1)) / 1000, datetime.timezone.utc)
        # Cronista's own timestamp convention changed mid-series: 00:00 UTC
        # before 2021-09-21, 03:00 UTC (= midnight ART) from then on. Taking
        # the UTC date is correct in both regimes — only the hour differs.
        # Warn (don't fail) if a future convention shift breaks this
        # assumption, so it's visible rather than silently off-by-one-ing.
        if dt.hour not in (0, 3) or dt.minute or dt.second:
            logger.warning(
                "Cronista row has unexpected time-of-day %s for date %s — "
                "timestamp convention may have changed; using UTC date as-is",
                dt.time(), dt.date(),
            )
        date_str = dt.date().isoformat()

        if not venta:
            logger.warning("Skipping row with missing/zero Venta for date %r", date_str)
            continue

        if date_str <= CRONISTA_LEGACY_END_DATE:
            # Defensive floor:
            # dollar_blue_cronista also holds hand-collected legacy rows up
            # to this date, and upsert_records does ON CONFLICT DO UPDATE —
            # a row this old should never come from this page (it only ever
            # shows a trailing ~10-month window), but if it ever did, this
            # stops it from silently overwriting legacy history.
            logger.warning(
                "Skipping row dated %r at/before legacy boundary %r — refusing "
                "to touch dollar_blue_cronista's legacy segment",
                date_str, CRONISTA_LEGACY_END_DATE,
            )
            continue

        records.append({"date": date_str, "value": str(float(venta))})

    return records
