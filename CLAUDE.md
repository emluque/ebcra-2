# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

`ebcra-2` is a monorepo for [estadisticasbcra.com](https://estadisticasbcra.com), a site that tracks and exposes economic statistics from the Central Bank of Argentina (BCRA). It bundles four previously-separate projects into one repo, each as a top-level directory:

| Directory | Language | Role |
|---|---|---|
| `ebcra-scrapping/` | Python 3.13 | Scrapes/fetches BCRA + market data, writes to Postgres |
| `ebcra-service/` | Go | API service — serves data from Postgres, issues/verifies JWTs |
| `ebcra-web/` | Python 3.12 / Django | Public-facing website (server-rendered), calls `ebcra-service` |
| `ebcra-setup/` | Docker / nginx / SQL | Infra: docker-compose, Dockerfiles, nginx config, postgres bootstrap |

Each directory is independently deployable and has its own dependency file (`go.mod`, `requirements.txt`) — there is no shared build system across them. `ebcra-setup/` holds the Dockerfiles for the other three but their build *context* is the sibling directory in this repo (see `ebcra-setup/docker-compose.yml`).

`ebcra-setup/CLAUDE.md` and `ebcra-setup/README.md` describe an older topology where each app lived in its own sibling repo under `/home/Projects/ebcra/` (e.g. `ebcra-service-2.0`). That has been superseded by this monorepo — application code now lives here, not in sibling repos — so treat the repo paths in `ebcra-setup/CLAUDE.md` as outdated, but its Docker network layout, nginx routing, and Postgres user/permission info are still accurate.

## Common commands

### Full stack (from `ebcra-setup/`)
```bash
sudo docker compose up -d --build          # start everything
sudo docker compose up -d postgres         # start just postgres (e.g. before first init)
sudo docker compose logs -f ebcra-service  # tail one service's logs
sudo docker compose up -d --build ebcra-service  # rebuild+restart one service
```
Compose build contexts are absolute paths back into this repo (e.g. `context: /home/Projects/ebcra-2/ebcra-service`), so compose must be run against the checked-out location of this repo.

### ebcra-service (Go)
```bash
cd ebcra-service
go build ./...
go vet ./...
go run .            # needs JWT_SECRET, DB_USER, DB_PASSWORD, CLEAN_CACHE_IP, PROMETHEUS_IP, CLIENT_IP set (see below)
```
There are no `*_test.go` files in this service currently.

### ebcra-scrapping (Python)
```bash
cd ebcra-scrapping
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium --with-deps    # only needed for ambito/yahoo scrapers
cp .env.example .env                       # then fill in DB_* and BCRA_BASE_URL
python main.py                             # delta run (only fetches since last MAX(date))
python main.py --full-refresh              # ignore existing data, backfill everything
python main.py --config config/variables.json
```
No test suite present.

### ebcra-web (Django)
```bash
cd ebcra-web
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
export DJANGO_SETTINGS_MODULE=ebcra.settings.local
python manage.py runserver
```
Settings are split as `ebcra/settings/base.py` (production defaults, `DEBUG=False`) and `ebcra/settings/local.py` (imports base, flips `DEBUG=True` and relaxes cookie security). No test suite present.

## Architecture

### Data flow
```
BCRA API / Ambito / Yahoo Finance  ─(ebcra-scrapping)─▶  Postgres  ◀─(reads)─  ebcra-service  ◀─(HTTP)─  ebcra-web  ──▶ browser
```
1. **`ebcra-scrapping/main.py`** is a one-shot batch job (not a daemon — its Docker container just runs `tail -f /dev/null` and is exec'd into or triggered externally, e.g. by cron). Each run:
   - Reads `config/variables.json` (BCRA variable id → destination table name).
   - For each variable, fetches from the BCRA API (`scraper/api_client.py`, `scraper/pipeline.py`) using a delta window (`MAX(date)` in the destination table minus a 14-day lookback, `DELTA_LOOKBACK_DAYS` in `scraper/db.py`), unless `--full-refresh` is passed.
   - Also runs the Playwright-based scrapers: `ambito/` (dollar blue historical rate) and `yahoo/` (Merval index), both funneled through the shared `scraper/web_pipeline.py::_run_web_scraper`.
   - Then runs `calculated/pipeline.py::run_calculated`, which derives secondary tables in a fixed dependency order: (1) unify multi-source series that changed provider over time (e.g. `dollar_blue_unified` stitches Cronista pre-2019 with Ambito after), (2) aggregations, (3) currency conversions (divide ARS series by `dollar_blue_unified` / `bcra_usd_mayorista`), (4) ratios, (5) year-over-year deltas (`calculated/yoy.py`). The source-table lists for steps 3–5 are hardcoded lists of `(dest, src_a, src_b, expr)` tuples in `calculated/pipeline.py` — add new derived series there.
   - On success, calls `GET {EBCRA_SERVICE_URL}/clear_cache` so `ebcra-service` picks up fresh data instead of serving its in-memory cache.
   - All table names are validated against `^[A-Za-z0-9_]+$` before being interpolated into SQL (`scraper/db.py::_validate_table_name`) since Postgres doesn't allow parameterized identifiers — this is the injection guard, don't bypass it.

2. **`ebcra-service`** is a single Go binary (`main.go`) with three route groups, all registered as plain `net/http` handlers (no router library):
   - **Core** (`internal/core`): one handler per row in `internal/core/core.json` (`[url, cacheKey, tableName, responseType]`). Requires a valid `Authorization: Bearer <jwt>` header. Serves `select date, value from <table>` as JSON, cached in-process by `internal/cache` (a flat `map[string]string`, flushed wholesale on `/clear_cache`, never expires otherwise). `mysqlField`/table names from `core.json` are validated at startup against `[A-Za-z0-9_]+`.
   - **Variations** (`internal/variations`): endpoints like `/var_base`, `/var_m2`, etc. call Postgres stored procedures (`SELECT * FROM sp_ebcra_var_*()`) instead of table selects, gated by an allowlist map (`allowedProcedures`) rather than JWT — auth here is IP-based (`CLIENT_IP`), matched against `RemoteAddr` or `X-Forwarded-For`. Also cached in-process, also flushed by `/clear_cache`.
   - **JWT** (`internal/jwt`): `GET /get-js-jwt` issues a 24h HS512 token, but only to `CLIENT_IP` (i.e. only `ebcra-web`'s middleware fetches these, browsers never call it directly).
   - `config.Config` (`internal/config/config.go`) requires `JWT_SECRET`, `DB_USER`, `DB_PASSWORD`, `CLEAN_CACHE_IP`, `PROMETHEUS_IP`, `CLIENT_IP` at startup (fails fast if missing) and builds the Postgres DSN. Despite the historical "mysqlField" naming throughout `core.go` and `ebcra-service/env-variables.md` describing a MySQL setup, the service connects to **Postgres** via `github.com/lib/pq` — `env-variables.md` is stale on that point.
   - `/clear_cache` and `/metrics` are both IP-gated (`CLEAN_CACHE_IP`, and `PROMETHEUS_IP`/`127.0.0.1` respectively).
   - CORS is origin-allowlisted per `cfg.Environment` (`development` → allow `http://(www.)estadisticasbcra.com`; anything else → `https://` origins only) — see `core.go::setCORSHeaders`.

3. **`ebcra-web`** is server-rendered Django with no ORM models/DB access of its own — `portal/views.py` renders one template per report page and, for pages listed in `_VARIATIONS_PATHS`, fetches variation data from `ebcra-service` synchronously via `httpx` (`_fetch_variations`) with a 5s timeout, degrading to `{}` on failure rather than erroring. `ebcra.middleware.JWTMiddleware` fetches (and session-caches for 23h) a JWT from `ebcra-service`'s `/get-js-jwt`, exposed to templates as `jsToken` via `portal.context_processors.site_globals` — this token is handed to client-side JS so browsers can call `ebcra-service`'s core (JWT-gated) endpoints directly for chart data, bypassing Django for the actual numbers.
   - Routing is language-prefixed and duplicated: `portal/urls_es.py` (Spanish, at `/`) and `portal/urls_en.py` (English, at `/en/`) each map distinct human-readable slugs to the *same* `views.report(request, page=...)` view with a shared `page` key — `views._ALTERNATE_URLS` is the ES↔EN slug lookup used to build the `hreflang`/language-switcher links. When adding a new report page, add entries to both URL confs, `_ALTERNATE_URLS`, and (if it has a variations chart) `_VARIATIONS_PATHS`, plus the template under `portal/templates/portal/pages/`.
   - `USE_I18N = False` — the ES/EN split is entirely hand-rolled through the two urlconfs and `_lang()`/`_ctx()`, not Django's i18n framework.
   - Non-DEBUG responses get `Cache-Control: max-age=14400, public` (`views._cache_headers`); nginx separately caches `/static/` for 30 days.

### Infra (`ebcra-setup/`)
Two Docker networks: `apps` (nginx + all three app services) and `data-network` (postgres + only `ebcra-service`/`ebcra-scraping`, i.e. `ebcra-web` cannot reach Postgres directly). nginx proxies `estadisticasbcra.com` → `ebcra-web:8000` and `api.estadisticasbcra.com` → `ebcra-service:9001`; static files are served by nginx directly from a shared volume, not proxied through Django. Two distinct Postgres users enforce least privilege: `estadisticasbcra` (read-only, used by `ebcra-service`) and `"ebcra-scraping"` (full write, used by `ebcra-scrapping`) — the latter's username has a hyphen and must be quoted in raw SQL. Full details (IP addressing, HTTPS cutover steps, first-time host provisioning) are in `ebcra-setup/CLAUDE.md` and `ebcra-setup/setup/setup.md`.
