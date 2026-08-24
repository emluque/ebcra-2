# ebcra-2-setup

Infrastructure and Docker configuration for [estadisticasbcra.com](https://estadisticasbcra.com), an open source project that tracks and exposes economic statistics from the Central Bank of Argentina (BCRA).


## Stack

- **nginx** — reverse proxy, serves static files
- **ebcra-2-web** — Django/Gunicorn frontend (port 8000)
- **ebcra-2-service** — Go API (port 9001)
- **ebcra-2-scraping** — Playwright/Chromium scraper (triggered externally)
- **postgres** — database (not exposed to the web)

All services run via Docker Compose. See [setup/setup.md](setup/setup.md) for the full provisioning guide.
