# estadisticasbcra.com

Source for [estadisticasbcra.com](https://estadisticasbcra.com), a site that tracks and publishes economic statistics from the Central Bank of Argentina (BCRA): monetary variables, exchange rates, interest rates, and derived series (currency conversions, ratios, year-over-year variations, etc.).

This is a monorepo bundling four previously-separate projects, each independently deployable:

| Directory | Language / Stack | Role |
|---|---|---|
| [`ebcra-scrapping/`](ebcra-scrapping) | Python 3.13 | Scrapes/fetches BCRA + market data, writes to Postgres |
| [`ebcra-service/`](ebcra-service) | Go | API service — serves data from Postgres, issues/verifies JWTs |
| [`ebcra-web/`](ebcra-web) | Python 3.12 / Django | Public-facing website (server-rendered), calls `ebcra-service` |
| [`ebcra-setup/`](ebcra-setup) | Docker / nginx / SQL | Infra: docker-compose, Dockerfiles, nginx config, Postgres bootstrap |

## How it fits together

```
BCRA API / Ambito / Yahoo Finance  ──▶  ebcra-scrapping  ──▶  Postgres
                                                                  │
                                                        (read-only queries)
                                                                  ▼
                          browser  ◀──HTTP──  ebcra-web  ◀──HTTP──  ebcra-service
                             │                                     ▲
                             └─────────── chart data (JWT) ────────┘
```

- **`ebcra-scrapping`** is a one-shot batch job (not a daemon — it's triggered externally, e.g. by cron). It fetches BCRA variables and market data (dollar blue, Merval index), writes them to Postgres, derives secondary tables (unified series, aggregations, conversions, ratios, year-over-year deltas), and finally tells `ebcra-service` to drop its cache.
- **`ebcra-service`** is a Go API that reads from Postgres and serves it as JSON, in two flavors: JWT-authenticated "core" endpoints (raw series, one per BCRA variable) called directly by the browser, and IP-allowlisted "variations" endpoints (Postgres stored procedures) called by `ebcra-web`. It also issues short-lived JWTs to `ebcra-web` so the browser can call the core endpoints without hitting Django in the middle.
- **`ebcra-web`** is a server-rendered Django site with no database access of its own. It renders one report page per BCRA variable/topic, optionally pre-fetching variation data from `ebcra-service`, and hands the browser a JWT (fetched server-side, session-cached) so client-side charts can pull raw series straight from `ebcra-service`.
- **`ebcra-setup`** ties the three services plus Postgres and nginx together with Docker Compose, on two isolated Docker networks (`apps` and `data-network`) so `ebcra-web` can never reach Postgres directly.

Each app directory has its own dependency file (`go.mod`, `requirements.txt`) and its own README with directory-specific details — there is no shared build system across them.

## Running the project

The full stack (all four components) runs via Docker Compose from `ebcra-setup/`. Each service can also be run standalone against a local or remote Postgres instance for development — see the per-directory READMEs below.

### Full stack via Docker Compose

```bash
cd ebcra-setup
mkdir -p /home/data/postgres /home/data/nginx-logs
sudo docker compose up -d postgres        # start Postgres first
sudo docker exec -i -e PGPASSWORD=<postgres-password> postgres \
  psql -U postgres -f - < setup/postgres/setup.sql   # create DB, schema, users
sudo docker compose up -d --build         # build and start everything else
```

Add `estadisticasbcra.com` and `api.estadisticasbcra.com` to `/etc/hosts` pointing at `127.0.0.1` to browse the stack locally. See [`ebcra-setup/setup/setup.md`](ebcra-setup/setup/setup.md) for the full first-time provisioning guide (host directories, users/permissions, verification steps) and [`ebcra-setup/README.md`](ebcra-setup/README.md) for a stack overview.

Compose's build contexts are absolute paths back into this repo (e.g. `/home/Projects/ebcra-2/ebcra-service`), so `docker compose` must be run from a checkout at that exact path, or the paths in `ebcra-setup/docker-compose.yml` adjusted to match your checkout location.

The bundled `docker-compose.yml` is a development configuration: it runs over plain HTTP with hardcoded, non-production credentials for Postgres, JWT signing, and Django's secret key. **Do not deploy it as-is** — replace every embedded password/secret with your own (via `.env`, Docker secrets, or a secrets manager) and add TLS termination to nginx before exposing it publicly. See the comments in `ebcra-setup/docker-compose.yml` for the specific settings that need to flip when moving from HTTP to HTTPS.

### Running an individual service

<details>
<summary><code>ebcra-service</code> (Go API)</summary>

```bash
cd ebcra-service
go build ./...
go run .   # needs JWT_SECRET, DB_USER, DB_PASSWORD, CLEAN_CACHE_IP, PROMETHEUS_IP, CLIENT_IP set
```

See [`ebcra-service/env-variables.md`](ebcra-service/env-variables.md) for the full list of environment variables and defaults.
</details>

<details>
<summary><code>ebcra-scrapping</code> (Python data pipeline)</summary>

```bash
cd ebcra-scrapping
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium --with-deps    # only needed for the ambito/yahoo scrapers
cp .env.example .env                       # fill in DB_* and BCRA_BASE_URL
python main.py                             # delta run (only fetches since last stored date)
python main.py --full-refresh              # ignore existing data, backfill everything
```
</details>

<details>
<summary><code>ebcra-web</code> (Django frontend)</summary>

```bash
cd ebcra-web
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
export DJANGO_SETTINGS_MODULE=ebcra.settings.local
python manage.py runserver
```
</details>

A Postgres database with the `estadisticasbcra` schema (see [`ebcra-setup/setup/postgres/setup.sql`](ebcra-setup/setup/postgres/setup.sql)) and, for `ebcra-web`/browser charts, a running `ebcra-service` instance are prerequisites for any of the above beyond `ebcra-scrapping`'s scraping step.

## Data flow in more detail

1. **Ingestion** (`ebcra-scrapping/main.py`): reads `config/variables.json` (BCRA variable id → destination table), fetches each series from the BCRA API using a delta window, and runs Playwright-based scrapers for dollar blue (Ambito) and the Merval index (Yahoo Finance). It then derives secondary tables in a fixed order — unified multi-source series, aggregations, currency conversions, ratios, and year-over-year deltas — and finally clears `ebcra-service`'s cache so new data is served immediately.
2. **API** (`ebcra-service`): a single Go binary with three route groups — **core** (one JWT-gated endpoint per table, defined in `internal/core/core.json`), **variations** (IP-gated endpoints backed by Postgres stored procedures), and **JWT** (issues tokens, restricted to `ebcra-web`'s IP). Responses are cached in-process and flushed wholesale on `/clear_cache`.
3. **Frontend** (`ebcra-web`): renders one report page per topic (Spanish at `/`, English at `/en/`, via separate URL confs sharing one view), optionally pre-fetching variation data server-side, and injects a JWT into the page so client-side JS can fetch raw series directly from `ebcra-service` for charts.
