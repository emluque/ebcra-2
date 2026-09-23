-- Adds scrape_status: per-table record of whether the last scrape/calculation
-- attempt for a given table succeeded, and how old its latest value is.
-- Written by ebcra-scrapping (scraper/db.py::record_scrape_status), read by
-- ebcra-service (internal/status) to power data-freshness warnings on
-- ebcra-web report pages.
--
-- Run against the existing estadisticasbcra database as the postgres
-- superuser, e.g.:
--   sudo docker compose exec postgres psql -U postgres -d estadisticasbcra \
--     -f /path/to/2026-09-23.scrape_status.sql
-- (or paste the contents into `psql -U postgres -d estadisticasbcra`).

CREATE TABLE public.scrape_status (
    table_name         text PRIMARY KEY,
    source_kind        text NOT NULL,   -- 'bcra_variable' | 'cronista' | 'yahoo' | 'calculated'
    variable_id        integer,         -- BCRA variable id, when source_kind = 'bcra_variable'
    status              text NOT NULL,   -- 'ok' | 'stale' | 'error'
    last_success_date  date,            -- MAX(date) currently in the target table
    checked_at          timestamptz NOT NULL,
    source_url          text,            -- BCRA API URL, for bcra_variable rows
    error_code          text,
    error_message        text,
    caused_by           text[]           -- for source_kind='calculated': upstream table_name(s) that are not 'ok'
);

ALTER TABLE public.scrape_status OWNER TO postgres;

GRANT SELECT ON public.scrape_status TO estadisticasbcra;
GRANT SELECT, INSERT, UPDATE ON public.scrape_status TO "ebcra-scraping";
