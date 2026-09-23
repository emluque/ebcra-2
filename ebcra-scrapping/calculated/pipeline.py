import logging

from scraper.constants import CRONISTA_LEGACY_END_DATE
from scraper.db import (
    DELTA_LOOKBACK_DAYS,
    DBConnection,
    _cursor,
    _validate_table_name,
    get_scrape_statuses,
    record_scrape_status,
)
from calculated.yoy import compute_yoy

logger = logging.getLogger(__name__)


_STATUS_SEVERITY = {"ok": 0, "stale": 1, "error": 2}


def _record_calculated_status(conn: DBConnection, dest: str, sources: list[str], run_ok: bool) -> None:
    """Record scrape_status for a calculated table, attributing degradation to
    whichever of its source tables aren't currently "ok".

    The calculated table's status is floored at the worst status among its
    sources — its own last-value age can still look fresh (e.g. a delta join
    that only touches recent dates) even while a source it depends on is
    currently stale/erroring.
    """
    if not run_ok:
        record_scrape_status(conn, dest, "calculated", ok=False, error_message="calculation failed")
        return
    upstream = get_scrape_statuses(conn, sources)
    degraded = [t for t in sources if upstream.get(t, {}).get("status") != "ok"]
    worst = "ok"
    for t in degraded:
        st = upstream.get(t, {}).get("status", "ok")
        if _STATUS_SEVERITY.get(st, 0) > _STATUS_SEVERITY.get(worst, 0):
            worst = st
    record_scrape_status(
        conn, dest, "calculated", ok=True,
        caused_by=degraded or None,
        min_status=worst if degraded else None,
    )


# ---------------------------------------------------------------------------
# Source boundary dates for unified series
# ---------------------------------------------------------------------------

# Dollar_Blue_Unified: legacy Cronista data covers up to this date; Ambito
# used thereafter. Shared with cronista/client.py via scraper/constants.py
# (see there for why) — don't redefine this locally.
_CRONISTA_END_DATE = CRONISTA_LEGACY_END_DATE

# Dollar_Blue_Unified: Ambito covers from _CRONISTA_END_DATE through this
# date; the active Cronista scrape (cronista/pipeline.py, writing into the
# SAME dollar_blue_cronista table as the legacy segment above) is used
# thereafter.
#
# Set by hand (not computed by this code). Ambito's scraper stopped
# producing data before this date; any gap is filled out of band in
# dollar_blue_ambito. dollar_blue_cronista's active-scrape segment takes
# over from 2026-09-21 onward.
_AMBITO_BLUE_END_DATE = "2026-09-20"

# Merval_Unified: Invertia data ends here
_INVERTIA_END_DATE = "2018-11-26"
# Merval_Unified: Ambito covers from _INVERTIA_END_DATE through this date; Yahoo used thereafter
_AMBITO_MERVAL_END_DATE = "2024-08-30"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _exec(conn: DBConnection, sql: str) -> int:
    """Execute a SQL statement, commit, and return the affected row count."""
    with _cursor(conn) as cursor:
        try:
            cursor.execute(sql)
            conn.commit()
            return cursor.rowcount
        except Exception:
            conn.rollback()
            raise


def _run_binary_calc(
    conn: DBConnection,
    dest: str,
    src_a: str,
    src_b: str,
    value_expr: str,
    full_refresh: bool,
) -> bool:
    """Insert rows into dest computed by joining src_a and src_b on date.

    value_expr uses 'a' for src_a alias and 'b' for src_b alias, e.g.
    'a.`value` / b.`value`'.
    """
    _validate_table_name(dest)
    _validate_table_name(src_a)
    _validate_table_name(src_b)

    select = (
        f'a."date", {value_expr} '
        f'FROM "{src_a}" a '
        f'JOIN "{src_b}" b ON a."date" = b."date"'
    )

    try:
        if full_refresh:
            count = _exec(
                conn,
                f'INSERT INTO "{dest}" ("date", "value") SELECT {select} '
                f'ON CONFLICT ("date") DO UPDATE SET "value" = EXCLUDED."value"',
            )
        else:
            count = _exec(
                conn,
                f'INSERT INTO "{dest}" ("date", "value") '
                f'SELECT {select} '
                f'WHERE a."date" NOT IN (SELECT "date" FROM "{dest}") '
                f'   OR a."date" > NOW() - INTERVAL \'{DELTA_LOOKBACK_DAYS} days\' '
                f'ON CONFLICT ("date") DO UPDATE SET "value" = EXCLUDED."value"',
            )
        logger.info("%-60s %d row(s) upserted", dest + ":", count)
        return True
    except Exception as exc:
        logger.error("Failed to calculate %s: %s", dest, exc)
        return False


def _run_yoy(conn: DBConnection, source_table: str, dest_table: str, full_refresh: bool) -> bool:
    try:
        count = compute_yoy(conn, source_table, dest_table, full_refresh)
        logger.info("%-60s %d row(s) upserted", dest_table + ":", count)
        return True
    except Exception as exc:
        logger.error("Failed to calculate %s: %s", dest_table, exc)
        return False


# ---------------------------------------------------------------------------
# Step 1: Unifications
# ---------------------------------------------------------------------------

def _run_dollar_blue_unification(conn: DBConnection, full_refresh: bool) -> list[str]:
    """Populate dollar_blue_unified. Returns [] on success, ["dollar_blue_unified"] on failure.

    Three segments (see _AMBITO_BLUE_END_DATE's comment — segments 1 and 3
    read from the same dollar_blue_cronista table, disjoint date ranges):
      … ≤ _CRONISTA_END_DATE    -> dollar_blue_cronista (legacy)
      … ≤ _AMBITO_BLUE_END_DATE -> dollar_blue_ambito
      >  _AMBITO_BLUE_END_DATE  -> dollar_blue_cronista (active scrape)
    """
    dest = "dollar_blue_unified"
    try:
        if _AMBITO_BLUE_END_DATE is None:
            raise RuntimeError(
                "_AMBITO_BLUE_END_DATE is not set — see its definition "
                "above. It must be set by hand, once, after reviewing "
                "continuity between dollar_blue_ambito's last good data and "
                "dollar_blue_cronista's newly-scraped days; it is not "
                "computed automatically. Refusing to run rather than guess."
            )

        if full_refresh:
            _exec(
                conn,
                f'INSERT INTO "{dest}" ("date", "value") '
                'SELECT "date", "value" FROM "dollar_blue_cronista" '
                f'WHERE "date" <= \'{_CRONISTA_END_DATE}\' '
                'ON CONFLICT ("date") DO UPDATE SET "value" = EXCLUDED."value"',
            )
            _exec(
                conn,
                f'INSERT INTO "{dest}" ("date", "value") '
                'SELECT "date", "value" FROM "dollar_blue_ambito" '
                f'WHERE "date" > \'{_CRONISTA_END_DATE}\' '
                f'AND "date" <= \'{_AMBITO_BLUE_END_DATE}\' AND "value" != 0 '
                'ON CONFLICT ("date") DO UPDATE SET "value" = EXCLUDED."value"',
            )
            count = _exec(
                conn,
                f'INSERT INTO "{dest}" ("date", "value") '
                'SELECT "date", "value" FROM "dollar_blue_cronista" '
                f'WHERE "date" > \'{_AMBITO_BLUE_END_DATE}\' '
                'ON CONFLICT ("date") DO UPDATE SET "value" = EXCLUDED."value"',
            )
        else:
            count = _exec(
                conn,
                f'INSERT INTO "{dest}" ("date", "value") '
                'SELECT "date", "value" FROM "dollar_blue_cronista" '
                f'WHERE "date" > NOW() - INTERVAL \'{DELTA_LOOKBACK_DAYS} days\' '
                f'AND "date" > \'{_AMBITO_BLUE_END_DATE}\' '
                'ON CONFLICT ("date") DO UPDATE SET "value" = EXCLUDED."value"',
            )
        logger.info("%-60s %d row(s) upserted", dest + ":", count)
        _record_calculated_status(conn, dest, ["dollar_blue_cronista"], run_ok=True)
        return []
    except Exception as exc:
        logger.error("Failed to calculate %s: %s", dest, exc)
        _record_calculated_status(conn, dest, ["dollar_blue_cronista"], run_ok=False)
        return [dest]


def _run_merval_unification(conn: DBConnection, full_refresh: bool) -> list[str]:
    """Populate merval_unified. Returns [] on success, ["merval_unified"] on failure."""
    dest = "merval_unified"
    try:
        if full_refresh:
            _exec(  # Invertia: historical up to _INVERTIA_END_DATE
                conn,
                f'INSERT INTO "{dest}" ("date", "value") '
                'SELECT "date", "value" FROM "merval_invertia" '
                f'WHERE "date" <= \'{_INVERTIA_END_DATE}\' '
                'ON CONFLICT ("date") DO UPDATE SET "value" = EXCLUDED."value"',
            )
            _exec(  # Ambito: _INVERTIA_END_DATE+1 through _AMBITO_MERVAL_END_DATE
                conn,
                f'INSERT INTO "{dest}" ("date", "value") '
                'SELECT "date", "value" FROM "merval_ambito" '
                f'WHERE "date" > \'{_INVERTIA_END_DATE}\' AND "date" <= \'{_AMBITO_MERVAL_END_DATE}\' '
                'ON CONFLICT ("date") DO UPDATE SET "value" = EXCLUDED."value"',
            )
            count = _exec(  # Yahoo: from _AMBITO_MERVAL_END_DATE+1 onward
                conn,
                f'INSERT INTO "{dest}" ("date", "value") '
                'SELECT "date", "value" FROM "merval_yahoo" '
                f'WHERE "date" > \'{_AMBITO_MERVAL_END_DATE}\' '
                'ON CONFLICT ("date") DO UPDATE SET "value" = EXCLUDED."value"',
            )
        else:
            count = _exec(
                conn,
                f'INSERT INTO "{dest}" ("date", "value") '
                'SELECT "date", "value" FROM "merval_yahoo" '
                f'WHERE "date" > NOW() - INTERVAL \'{DELTA_LOOKBACK_DAYS} days\' '
                'ON CONFLICT ("date") DO UPDATE SET "value" = EXCLUDED."value"',
            )
        logger.info("%-60s %d row(s) upserted", dest + ":", count)
        _record_calculated_status(conn, dest, ["merval_yahoo"], run_ok=True)
        return []
    except Exception as exc:
        logger.error("Failed to calculate %s: %s", dest, exc)
        _record_calculated_status(conn, dest, ["merval_yahoo"], run_ok=False)
        return [dest]


# ---------------------------------------------------------------------------
# Step 2: Aggregations
# ---------------------------------------------------------------------------

_AGGREGATIONS: list[tuple[str, str, str, str]] = []


# ---------------------------------------------------------------------------
# Step 3: Currency conversions
# ---------------------------------------------------------------------------

_CONVERSIONS: list[tuple[str, str, str, str]] = [
    # (dest, numerator_table, denominator_table, value_expr)
    (
        "calculated_base_en_dollar",
        "bcra_base_monetaria",
        "dollar_blue_unified",
        'a."value" / b."value"',
    ),
    (
        "calculated_base_en_dollar_oficial",
        "bcra_base_monetaria",
        "bcra_usd_mayorista",
        'a."value" / b."value"',
    ),
    (
        "calculated_m2_en_dollar",
        "bcra_m2",
        "dollar_blue_unified",
        'a."value" / b."value"',
    ),
    (
        "calculated_m2_en_dollar_oficial",
        "bcra_m2",
        "bcra_usd_mayorista",
        'a."value" / b."value"',
    ),
    (
        "calculated_m2_transaccional_privado_en_dollar",
        "bcra_m2_transaccional_privado",
        "dollar_blue_unified",
        'a."value" / b."value"',
    ),
    (
        "calculated_m2_transaccional_privado_en_dollar_oficial",
        "bcra_m2_transaccional_privado",
        "bcra_usd_mayorista",
        'a."value" / b."value"',
    ),
    (
        "calculated_m2_privado_en_dollar",
        "bcra_m2_privado",
        "dollar_blue_unified",
        'a."value" / b."value"',
    ),
    (
        "calculated_m2_privado_en_dollar_oficial",
        "bcra_m2_privado",
        "bcra_usd_mayorista",
        'a."value" / b."value"',
    ),
    (
        "merval_en_dollar",
        "merval_unified",
        "dollar_blue_unified",
        'a."value" / b."value"',
    ),
    (
        "calculated_m1_en_dollar",
        "bcra_m1",
        "dollar_blue_unified",
        'a."value" / b."value"',
    ),
    (
        "calculated_m1_en_dollar_oficial",
        "bcra_m1",
        "bcra_usd_mayorista",
        'a."value" / b."value"',
    ),
    (
        "calculated_m3_en_dollar",
        "bcra_m3",
        "dollar_blue_unified",
        'a."value" / b."value"',
    ),
    (
        "calculated_m3_en_dollar_oficial",
        "bcra_m3",
        "bcra_usd_mayorista",
        'a."value" / b."value"',
    ),
]


# ---------------------------------------------------------------------------
# Step 4: Ratios and other arithmetic
# ---------------------------------------------------------------------------

_RATIOS: list[tuple[str, str, str, str]] = [
    (
        "calculated_base_dividido_reservas",
        "bcra_base_monetaria",
        "bcra_reservas_internacionales",
        'a."value" / b."value"',
    ),
    (
        "calculated_m2_dividido_reservas",
        "bcra_m2",
        "bcra_reservas_internacionales",
        'a."value" / b."value"',
    ),
    (
        "calculated_porcentaje_prestamos_vs_depositos",
        "bcra_prestamos_entidades_financieras_sector_privado",
        "bcra_depositos_efectivo_entidades_financieras_total",
        'ROUND((a."value" / b."value") * 100, 4)',
    ),
    (
        "var_dollar_blue_vs_oficial",
        "dollar_blue_unified",
        "bcra_usd_mayorista",
        '((a."value" / b."value") * 100) - 100',
    ),
    (
        "calculated_m1_dividido_reservas",
        "bcra_m1",
        "bcra_reservas_internacionales",
        'a."value" / b."value"',
    ),
    (
        "calculated_m3_dividido_reservas",
        "bcra_m3",
        "bcra_reservas_internacionales",
        'a."value" / b."value"',
    ),
]


# ---------------------------------------------------------------------------
# Step 5: Year-over-year variations
# ---------------------------------------------------------------------------

_YOY_CALCS: list[tuple[str, str]] = [
    # (source_table, dest_table)
    ("bcra_usd_mayorista",                         "var_dollar_oficial_interanual"),
    ("dollar_blue_unified",                        "var_dollar_interanual"),
    ("merval_unified",                             "var_merval_interanual"),
]


# ---------------------------------------------------------------------------
# Dollar-blue scope: which of the steps 2-5 tables transitively depend on
# dollar_blue_unified, so main.py's --skip-dollar-blue / --only-dollar-blue
# can include/exclude exactly those without a hand-maintained list drifting
# out of sync with _AGGREGATIONS/_CONVERSIONS/_RATIOS/_YOY_CALCS.
# ---------------------------------------------------------------------------

def _derive_dollar_blue_scope() -> frozenset[str]:
    """Tables in steps 2-5 that transitively depend on dollar_blue_unified.

    Walks the (dest, src_a, src_b, ...) tuples as a dependency graph, seeded
    with dollar_blue_unified, to a fixed point — so a series added later
    that chains off another dollar-blue-derived table (not just directly off
    dollar_blue_unified) is still picked up correctly.
    """
    dependent = {"dollar_blue_unified"}
    changed = True
    while changed:
        changed = False
        for dest, src_a, src_b, _expr in _AGGREGATIONS + _CONVERSIONS + _RATIOS:
            if dest not in dependent and (src_a in dependent or src_b in dependent):
                dependent.add(dest)
                changed = True
        for source_table, dest_table in _YOY_CALCS:
            if dest_table not in dependent and source_table in dependent:
                dependent.add(dest_table)
                changed = True
    dependent.discard("dollar_blue_unified")  # that's the unification step itself, handled separately
    return frozenset(dependent)


# Pinned expectation for the set above — deliberately hand-written and
# checked at import time (not just derived), so a series added to
# _CONVERSIONS/_RATIOS/_YOY_CALCS without updating this constant fails loudly
# the moment this module is imported, rather than silently changing what
# --skip-dollar-blue/--only-dollar-blue cover.
_EXPECTED_DOLLAR_BLUE_SCOPE = frozenset({
    "calculated_base_en_dollar",
    "calculated_m1_en_dollar",
    "calculated_m2_en_dollar",
    "calculated_m2_privado_en_dollar",
    "calculated_m2_transaccional_privado_en_dollar",
    "calculated_m3_en_dollar",
    "merval_en_dollar",
    "var_dollar_blue_vs_oficial",
    "var_dollar_interanual",
})

_DOLLAR_BLUE_SCOPE = _derive_dollar_blue_scope()
if _DOLLAR_BLUE_SCOPE != _EXPECTED_DOLLAR_BLUE_SCOPE:
    raise RuntimeError(
        "calculated/pipeline.py: derived dollar-blue-dependent table set "
        f"{sorted(_DOLLAR_BLUE_SCOPE)} does not match the pinned "
        f"_EXPECTED_DOLLAR_BLUE_SCOPE {sorted(_EXPECTED_DOLLAR_BLUE_SCOPE)}. "
        "A series was added to/changed in _AGGREGATIONS/_CONVERSIONS/"
        "_RATIOS/_YOY_CALCS without updating _EXPECTED_DOLLAR_BLUE_SCOPE — "
        "update the constant (after confirming the newly derived set is "
        "actually correct) rather than silencing this."
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

_VALID_SCOPES = frozenset({"all", "dollar_blue", "non_dollar_blue"})


def run_calculated(conn: DBConnection, full_refresh: bool = False, scope: str = "all") -> bool:
    """Run calculated metric pipelines in dependency order.

    scope selects which tables run:
      "all"           — everything (default).
      "dollar_blue"   — only dollar_blue_unified and whatever transitively
                         depends on it (see _DOLLAR_BLUE_SCOPE). For
                         dollar-blue-only runs.
      "non_dollar_blue" — everything except those, for runs that don't touch
                         the dollar-blue source.

    Execution order within the selected scope:
      1. Unifications (Dollar_Blue_Unified, Merval_Unified)
      2. Aggregations (base+deposits, m2+deposits_a_plazo)
      3. Currency conversions
      4. Ratios and other arithmetic
      5. Year-over-year variations

    Returns True if all calculations succeeded, False if any failed.
    """
    if scope not in _VALID_SCOPES:
        raise ValueError(f"Invalid scope {scope!r}; must be one of {sorted(_VALID_SCOPES)}")

    logger.info(
        "Starting calculated metrics pipeline (%s, scope=%s)",
        "full refresh" if full_refresh else "delta", scope,
    )

    failed: list[str] = []

    # Step 1: Unifications
    if scope in ("all", "dollar_blue"):
        failed.extend(_run_dollar_blue_unification(conn, full_refresh))
    if scope in ("all", "non_dollar_blue"):
        failed.extend(_run_merval_unification(conn, full_refresh))

    # Steps 2–4: Binary calculations (aggregations, conversions, ratios)
    for dest, src_a, src_b, value_expr in _AGGREGATIONS + _CONVERSIONS + _RATIOS:
        if scope == "dollar_blue" and dest not in _DOLLAR_BLUE_SCOPE:
            continue
        if scope == "non_dollar_blue" and dest in _DOLLAR_BLUE_SCOPE:
            continue
        ok = _run_binary_calc(conn, dest, src_a, src_b, value_expr, full_refresh)
        _record_calculated_status(conn, dest, [src_a, src_b], run_ok=ok)
        if not ok:
            failed.append(dest)

    # Step 5: Year-over-year variations
    for source_table, dest_table in _YOY_CALCS:
        if scope == "dollar_blue" and dest_table not in _DOLLAR_BLUE_SCOPE:
            continue
        if scope == "non_dollar_blue" and dest_table in _DOLLAR_BLUE_SCOPE:
            continue
        ok = _run_yoy(conn, source_table, dest_table, full_refresh)
        _record_calculated_status(conn, dest_table, [source_table], run_ok=ok)
        if not ok:
            failed.append(dest_table)

    if failed:
        logger.error("Calculated metrics: %d failure(s): %s", len(failed), failed)
        return False

    logger.info("Calculated metrics: all done.")
    return True
