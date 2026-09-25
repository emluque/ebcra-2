import datetime
import logging
import re
from contextlib import contextmanager

import psycopg2
from dateutil.relativedelta import relativedelta

logger = logging.getLogger(__name__)

DELTA_LOOKBACK_DAYS: int = 14
STALE_THRESHOLD_DAYS: int = 31
DBConnection = psycopg2.extensions.connection

_STATUS_SEVERITY = {"ok": 0, "stale": 1, "error": 2}

_TABLE_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


@contextmanager
def _cursor(conn: DBConnection):
    cur = conn.cursor()
    try:
        yield cur
    finally:
        cur.close()


def get_connection(config: dict):
    return psycopg2.connect(
        host=config["host"],
        port=int(config["port"]),
        dbname=config["database"],
        user=config["user"],
        password=config["password"],
    )


def get_max_date(conn: DBConnection, table_name: str) -> str | None:
    _validate_table_name(table_name)
    with _cursor(conn) as cursor:
        cursor.execute(f'SELECT MAX("date") FROM "{table_name}"')
        row = cursor.fetchone()
        if row and row[0] is not None:
            return str(row[0])
        return None


def record_scrape_status(
    conn: DBConnection,
    table_name: str,
    source_kind: str,
    *,
    ok: bool,
    variable_id: int | None = None,
    source_url: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    caused_by: list[str] | None = None,
    min_status: str | None = None,
    expected_lag: relativedelta | None = None,
) -> str:
    """Upsert scrape_status for table_name and return the derived status.

    status is "error" if the attempt failed (or the table has never had any
    data), "stale" if the latest stored value is older than
    STALE_THRESHOLD_DAYS days, otherwise "ok" — unless min_status ("stale" or
    "error") is given and is more severe, in which case it wins. Used for
    calculated tables: their own last-value age can still look fresh even
    when a source they depend on is currently stale/erroring (e.g. a delta
    join that only touches recent dates), so the caller passes the worst
    status among their sources as a floor.

    expected_lag is for tables whose latest date structurally trails their
    source's (e.g. YoY tables are keyed by the past date, so their MAX(date)
    is always ~1 year behind): it is added to the latest date before
    measuring its age, so that built-in lag isn't reported as "stale".

    This is a best-effort telemetry write: a failure here (e.g. a transient
    DB error) is logged and swallowed rather than raised, so it can never
    abort the calling scrape/calculation loop the way a failure in
    upsert_records legitimately should.
    """
    _validate_table_name(table_name)
    try:
        last_date = get_max_date(conn, table_name)

        if not ok or last_date is None:
            status = "error"
        else:
            effective_date = datetime.date.fromisoformat(last_date)
            if expected_lag:
                effective_date += expected_lag
            age_days = (datetime.date.today() - effective_date).days
            status = "stale" if age_days > STALE_THRESHOLD_DAYS else "ok"

        if min_status and _STATUS_SEVERITY.get(min_status, 0) > _STATUS_SEVERITY.get(status, 0):
            status = min_status

        if status != "ok":
            logger.warning(
                "%s (%s): status=%s last_success_date=%s error=%s",
                source_kind, table_name, status, last_date, error_message,
            )

        sql = (
            'INSERT INTO scrape_status '
            '("table_name", "source_kind", "variable_id", "status", "last_success_date", '
            '"checked_at", "source_url", "error_code", "error_message", "caused_by") '
            'VALUES (%s, %s, %s, %s, %s, now(), %s, %s, %s, %s) '
            'ON CONFLICT ("table_name") DO UPDATE SET '
            '"source_kind" = EXCLUDED."source_kind", '
            '"variable_id" = EXCLUDED."variable_id", '
            '"status" = EXCLUDED."status", '
            '"last_success_date" = EXCLUDED."last_success_date", '
            '"checked_at" = EXCLUDED."checked_at", '
            '"source_url" = EXCLUDED."source_url", '
            '"error_code" = EXCLUDED."error_code", '
            '"error_message" = EXCLUDED."error_message", '
            '"caused_by" = EXCLUDED."caused_by"'
        )
        with _cursor(conn) as cursor:
            cursor.execute(sql, (
                table_name, source_kind, variable_id, status, last_date,
                source_url, error_code, error_message, caused_by,
            ))
        conn.commit()
        return status
    except Exception as exc:
        conn.rollback()
        logger.error("Failed to record scrape_status for %s: %s", table_name, exc)
        return "error"


def get_scrape_statuses(conn: DBConnection, table_names: list[str]) -> dict[str, dict]:
    """Fetch current scrape_status rows for table_names, keyed by table_name."""
    if not table_names:
        return {}
    with _cursor(conn) as cursor:
        cursor.execute(
            'SELECT "table_name", "status", "variable_id" FROM scrape_status '
            'WHERE "table_name" = ANY(%s)',
            (table_names,),
        )
        return {
            row[0]: {"status": row[1], "variable_id": row[2]}
            for row in cursor.fetchall()
        }


def upsert_records(conn: DBConnection, table_name: str, records: list[dict]) -> int:
    _validate_table_name(table_name)
    if not records:
        return 0

    sql = (
        f'INSERT INTO "{table_name}" ("date", "value") VALUES (%s, %s) '
        f'ON CONFLICT ("date") DO UPDATE SET "value" = EXCLUDED."value"'
    )
    rows = [(r["date"], r["value"]) for r in records]

    with _cursor(conn) as cursor:
        try:
            cursor.executemany(sql, rows)
            conn.commit()
            affected = cursor.rowcount
            logger.debug("Upserted %d row(s) into %s", affected, table_name)
            return affected
        except Exception:
            conn.rollback()
            raise


def insert_ignore_records(conn: DBConnection, table_name: str, records: list[dict]) -> int:
    _validate_table_name(table_name)
    if not records:
        return 0

    sql = f'INSERT INTO "{table_name}" ("date", "value") VALUES (%s, %s) ON CONFLICT DO NOTHING'
    rows = [(r["date"], r["value"]) for r in records]

    with _cursor(conn) as cursor:
        try:
            cursor.executemany(sql, rows)
            conn.commit()
            affected = cursor.rowcount
            logger.debug("INSERT IGNORE: %d row(s) into %s", affected, table_name)
            return affected
        except Exception:
            conn.rollback()
            raise


def deduplicate(records: list[dict], strategy: str = "first") -> list[dict]:
    """Deduplicate records by date, keeping one record per date.

    strategy="first": keep the first record seen for each date
    strategy="max":   keep the record with the highest value for each date
    """
    seen: dict = {}
    for r in records:
        date = r["date"]
        if strategy == "max":
            if date not in seen or float(r["value"]) > float(seen[date]["value"]):
                seen[date] = r
        else:  # "first"
            if date not in seen:
                seen[date] = r
    return list(seen.values())


def _validate_table_name(table_name: str) -> None:
    if not _TABLE_NAME_RE.match(table_name):
        raise ValueError(f"Invalid table name: {table_name!r}")
