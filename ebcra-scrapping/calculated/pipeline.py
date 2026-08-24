import logging

from scraper.db import DELTA_LOOKBACK_DAYS, DBConnection, _cursor, _validate_table_name
from calculated.yoy import compute_yoy

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Source boundary dates for unified series
# ---------------------------------------------------------------------------

# Dollar_Blue_Unified: Cronista data covers up to this date; Ambito used thereafter
_CRONISTA_END_DATE = "2019-01-01"

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

def _run_unifications(conn: DBConnection, full_refresh: bool) -> list[str]:
    """Populate Dollar_Blue_Unified and Merval_Unified. Returns list of failed tables."""
    failed = []

    # dollar_blue_unified
    dest = "dollar_blue_unified"
    try:
        if full_refresh:
            _exec(
                conn,
                f'INSERT INTO "{dest}" ("date", "value") '
                'SELECT "date", "value" FROM "dollar_blue_cronista" '
                f'WHERE "date" <= \'{_CRONISTA_END_DATE}\' '
                'ON CONFLICT ("date") DO UPDATE SET "value" = EXCLUDED."value"',
            )
            count = _exec(
                conn,
                f'INSERT INTO "{dest}" ("date", "value") '
                'SELECT "date", "value" FROM "dollar_blue_ambito" '
                f'WHERE "date" > \'{_CRONISTA_END_DATE}\' AND "value" != 0 '
                'ON CONFLICT ("date") DO UPDATE SET "value" = EXCLUDED."value"',
            )
        else:
            count = _exec(
                conn,
                f'INSERT INTO "{dest}" ("date", "value") '
                'SELECT "date", "value" FROM "dollar_blue_ambito" '
                f'WHERE "date" > NOW() - INTERVAL \'{DELTA_LOOKBACK_DAYS} days\' '
                'AND "value" != 0 '
                'ON CONFLICT ("date") DO UPDATE SET "value" = EXCLUDED."value"',
            )
        logger.info("%-60s %d row(s) upserted", dest + ":", count)
    except Exception as exc:
        logger.error("Failed to calculate %s: %s", dest, exc)
        failed.append(dest)

    # merval_unified
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
    except Exception as exc:
        logger.error("Failed to calculate %s: %s", dest, exc)
        failed.append(dest)

    return failed


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
# Public entry point
# ---------------------------------------------------------------------------

def run_calculated(conn: DBConnection, full_refresh: bool = False) -> bool:
    """Run all calculated metric pipelines in dependency order.

    Execution order:
      1. Unifications (Dollar_Blue_Unified, Merval_Unified)
      2. Aggregations (base+deposits, m2+deposits_a_plazo)
      3. Currency conversions
      4. Ratios and other arithmetic
      5. Year-over-year variations

    Returns True if all calculations succeeded, False if any failed.
    """
    logger.info(
        "Starting calculated metrics pipeline (%s)",
        "full refresh" if full_refresh else "delta",
    )

    failed: list[str] = []

    # Step 1: Unifications
    failed.extend(_run_unifications(conn, full_refresh))

    # Steps 2–4: Binary calculations (aggregations, conversions, ratios)
    for dest, src_a, src_b, value_expr in _AGGREGATIONS + _CONVERSIONS + _RATIOS:
        ok = _run_binary_calc(conn, dest, src_a, src_b, value_expr, full_refresh)
        if not ok:
            failed.append(dest)

    # Step 5: Year-over-year variations
    for source_table, dest_table in _YOY_CALCS:
        ok = _run_yoy(conn, source_table, dest_table, full_refresh)
        if not ok:
            failed.append(dest_table)

    if failed:
        logger.error("Calculated metrics: %d failure(s): %s", len(failed), failed)
        return False

    logger.info("Calculated metrics: all done.")
    return True
