import datetime
from bisect import bisect_left
from decimal import Decimal, ROUND_HALF_UP

from dateutil.relativedelta import relativedelta

from scraper.db import DELTA_LOOKBACK_DAYS, DBConnection, _cursor, _validate_table_name, upsert_records

_QUANTIZER = Decimal("0.0001")
_HUNDRED = Decimal("100")


def compute_yoy(conn: DBConnection, source_table: str, dest_table: str, full_refresh: bool = False) -> int:
    """Compute year-over-year percentage change for every date in source_table.

    For each row (date D, value V_past), finds the nearest source row on or after
    D + 1 calendar year (V_future at date F) and computes:

        variation = ((V_future / V_past) * 100) - 100

    Stored in dest_table with date D (the investment/past date). Uses bisect_left for O(N log N) performance
    instead of a correlated SQL subquery.

    Returns the number of records upserted.
    """
    _validate_table_name(source_table)
    _validate_table_name(dest_table)

    # 1. Fetch all source rows in a single query
    with _cursor(conn) as cursor:
        cursor.execute(
            f'SELECT "date", "value" FROM "{source_table}" ORDER BY "date" ASC'
        )
        rows = cursor.fetchall()

    if not rows:
        return 0

    dates = [r[0] for r in rows]   # list[datetime.date], ascending
    values = [r[1] for r in rows]  # list[Decimal | None]

    # 2a. In delta mode, skip dates already present in dest (outside 14-day window)
    existing: set = set()
    if not full_refresh:
        cutoff = datetime.date.today() - datetime.timedelta(days=DELTA_LOOKBACK_DAYS)
        with _cursor(conn) as cursor:
            cursor.execute(f'SELECT "date" FROM "{dest_table}"')
            existing = {r[0] for r in cursor.fetchall() if r[0] < cutoff}

    # 2b. Compute YoY values using bisect
    results: list[dict] = []
    n = len(dates)

    for past_date, past_val in zip(dates, values):
        if past_val is None or past_val == 0:
            continue

        target_date = past_date + relativedelta(years=1)
        j = bisect_left(dates, target_date)
        if j >= n:
            continue

        future_val = values[j]
        if future_val is None:
            continue

        output_date = past_date
        if output_date in existing:
            continue

        yoy = ((Decimal(str(future_val)) / Decimal(str(past_val))) * _HUNDRED - _HUNDRED).quantize(
            _QUANTIZER, rounding=ROUND_HALF_UP
        )
        results.append({"date": output_date, "value": yoy})

    if not results:
        return 0

    # 3. Bulk upsert — ON DUPLICATE KEY UPDATE so stale values are always corrected
    return upsert_records(conn, dest_table, results)
