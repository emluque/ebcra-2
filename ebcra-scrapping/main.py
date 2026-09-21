import argparse
import json
import logging
import os
import sys

import requests
from dotenv import load_dotenv

from calculated.pipeline import run_calculated
from cronista.pipeline import run_cronista
from yahoo.pipeline import run_yahoo
from scraper.api_client import BCRAClient
from scraper.db import get_connection
from scraper.jitter import jittered_delay
from scraper.pipeline import run_variable

# Max random delay before an --only-dollar-blue run starts, so it doesn't
# hit Cronista at the same clock minute every day.
_DOLLAR_BLUE_JITTER_MAX_MINUTES = 30


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
    parser.add_argument(
        "--skip-dollar-blue",
        action="store_true",
        help=(
            "Skip the Cronista dollar-blue scraper and the calculated tables "
            "that depend on it. Dollar-blue is run separately via "
            "--only-dollar-blue."
        ),
    )
    parser.add_argument(
        "--only-dollar-blue",
        action="store_true",
        help=(
            "Run only the Cronista dollar-blue scraper and the calculated "
            "tables that depend on it, skipping the BCRA variable loop and "
            "the Yahoo scraper."
        ),
    )
    args = parser.parse_args()

    if args.skip_dollar_blue and args.only_dollar_blue:
        logger.critical("--skip-dollar-blue and --only-dollar-blue are mutually exclusive.")
        sys.exit(1)

    if args.only_dollar_blue:
        jittered_delay(_DOLLAR_BLUE_JITTER_MAX_MINUTES, label="dollar-blue run")

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

    if args.only_dollar_blue:
        calculated_scope = "dollar_blue"
    elif args.skip_dollar_blue:
        calculated_scope = "non_dollar_blue"
    else:
        calculated_scope = "all"

    succeeded = []
    failed = []

    try:
        if not args.only_dollar_blue:
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

            ok = run_yahoo(conn=conn)
            if ok:
                succeeded.append("yahoo_merval")
            else:
                failed.append("yahoo_merval")

        if args.skip_dollar_blue:
            logger.warning("Skipping Cronista dollar-blue scraper (--skip-dollar-blue set).")
        else:
            ok = run_cronista(conn=conn)
            if ok:
                succeeded.append("cronista_dollar_blue")
            else:
                failed.append("cronista_dollar_blue")

        ok = run_calculated(conn=conn, full_refresh=args.full_refresh, scope=calculated_scope)
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
