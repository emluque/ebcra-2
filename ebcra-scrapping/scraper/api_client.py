import logging
import time
import requests

logger = logging.getLogger(__name__)

PAGE_LIMIT = 7
PAGE_DELAY = 0.5       # seconds between paginated requests
MAX_RETRIES = 4        # attempts per page (1 original + 3 retries)
RETRY_BACKOFF = 2.0    # exponential base (2, 4, 8 seconds)


class BCRAAPIError(Exception):
    def __init__(self, message, status_code=None, variable_id=None):
        super().__init__(message)
        self.status_code = status_code
        self.variable_id = variable_id


class BCRAClient:
    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def fetch_variable(self, id_variable: int, desde: str | None = None) -> list[dict]:
        records = []
        offset = 0

        while True:
            params = {"Limit": PAGE_LIMIT, "Offset": offset}
            if desde:
                params["Desde"] = desde

            if offset > 0:
                time.sleep(PAGE_DELAY)

            data = self._get_page(id_variable, params)

            results = data.get("results", [])
            for result in results:
                for entry in result.get("detalle", []):
                    records.append({
                        "fecha": entry["fecha"],
                        "valor": entry["valor"],
                    })

            total = data.get("metadata", {}).get("resultset", {}).get("count", 0)
            offset += PAGE_LIMIT

            if offset >= total:
                break

        logger.debug("Variable %d: fetched %d records", id_variable, len(records))
        return records

    def _get_page(self, id_variable: int, params: dict) -> dict:
        url = f"{self.base_url}/estadisticas/v4.0/Monetarias/{id_variable}"
        last_exc = None

        for attempt in range(MAX_RETRIES):
            if attempt > 0:
                delay = RETRY_BACKOFF ** attempt
                logger.warning(
                    "Variable %d: retrying page (attempt %d/%d) after %.0fs — %s",
                    id_variable, attempt + 1, MAX_RETRIES, delay, last_exc,
                )
                time.sleep(delay)

            try:
                response = requests.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                last_exc = exc
                continue

            if response.status_code != 200:
                # Don't retry hard API errors (400/404); they won't change.
                raise BCRAAPIError(
                    f"API returned {response.status_code} for variable {id_variable}",
                    status_code=response.status_code,
                    variable_id=id_variable,
                )

            try:
                return response.json()
            except requests.exceptions.JSONDecodeError as exc:
                raise BCRAAPIError(
                    f"Invalid JSON from variable {id_variable}: {exc}",
                    variable_id=id_variable,
                ) from exc

        raise BCRAAPIError(
            f"Network error fetching variable {id_variable}: {last_exc}",
            variable_id=id_variable,
        ) from last_exc
