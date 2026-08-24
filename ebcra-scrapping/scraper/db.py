import logging
import re
from contextlib import contextmanager

import psycopg2

logger = logging.getLogger(__name__)

DELTA_LOOKBACK_DAYS: int = 14
DBConnection = psycopg2.extensions.connection

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
