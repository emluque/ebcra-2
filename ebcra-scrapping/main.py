import argparse
import json
import logging
import os
import sys

import requests
from dotenv import load_dotenv

from ambito.pipeline import run_ambito
from calculated.pipeline import run_calculated
from yahoo.pipeline import run_yahoo
from scraper.api_client import BCRAClient
from scraper.db import get_connection
from scraper.pipeline import run_variable


def setup_logging() -> None:
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )


def clear_service_cache(service_url: str) -> None:
    try:
        resp = requests.get(f"{service_url}/clear_cache", timeout=10)
        resp.raise_for_status()
        logging.getLogger(__name__).info("Service cache cleared.")
    except requests.RequestException as exc:
        logging.getLogger(__name__).error("Failed to clear service cache: %s", exc)


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        logging.critical("Required environment variable '%s' is not set.", name)
        sys.exit(1)
    return value


def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)

    load_dotenv()

    parser = argparse.ArgumentParser(description="BCRA data pipeline")
    parser.add_argument(
        "--config",
        default="config/variables.json",
        help="Path to variables JSON config (default: config/variables.json)",
    )
    parser.add_argument(
        "--full-refresh",
        action="store_true",
        help="Ignore MAX(date) and fetch all historical data",
    )
    args = parser.parse_args()

    base_url = get_required_env("BCRA_BASE_URL")
    db_config = {
        "host":     get_required_env("DB_HOST"),
        "port":     get_required_env("DB_PORT"),
        "database": get_required_env("DB_NAME"),
        "user":     get_required_env("DB_USER"),
        "password": get_required_env("DB_PASSWORD"),
    }

    try:
        with open(args.config, encoding="utf-8") as f:
            variables = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to load config file %s: %s", args.config, exc)
        sys.exit(1)

    try:
        conn = get_connection(db_config)
    except Exception as exc:
        logger.error("Failed to connect to database: %s", exc)
        sys.exit(1)

    client = BCRAClient(base_url=base_url)

    succeeded = []
    failed = []

    try:
        for entry in variables:
            variable_id = entry["id"]
            table_name = entry["tableName"]
            ok = run_variable(
                client=client,
                conn=conn,
                variable_id=variable_id,
                table_name=table_name,
                full_refresh=args.full_refresh,
            )
            if ok:
                succeeded.append(variable_id)
            else:
                failed.append(variable_id)

        ok = run_ambito(conn=conn)
        if ok:
            succeeded.append("ambito_dollar_blue")
        else:
            failed.append("ambito_dollar_blue")

        ok = run_yahoo(conn=conn)
        if ok:
            succeeded.append("yahoo_merval")
        else:
            failed.append("yahoo_merval")

        ok = run_calculated(conn=conn, full_refresh=args.full_refresh)
        if ok:
            succeeded.append("calculated_metrics")
        else:
            failed.append("calculated_metrics")
    finally:
        conn.close()

    service_url = os.getenv("EBCRA_SERVICE_URL")
    if service_url:
        clear_service_cache(service_url)
    else:
        logger.warning("EBCRA_SERVICE_URL not set; skipping cache clear.")

    logger.info(
        "Done. %d succeeded, %d failed.%s",
        len(succeeded),
        len(failed),
        f" Failed IDs: {failed}" if failed else "",
    )

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
