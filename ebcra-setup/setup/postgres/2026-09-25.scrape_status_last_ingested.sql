-- Adds scrape_status.last_ingested_at: when new data last landed in the
-- table, i.e. the last time its MAX(date) advanced. Unlike checked_at (bumped
-- on every attempt, failed or not), this only moves on a real ingestion.
-- Set by ebcra-scrapping (scraper/db.py::record_scrape_status), shown on the
-- ebcra-web status page (/estado, /en/status).
--
-- Existing rows start as NULL and get a value the next time their data
-- advances.
--
-- Run against the existing estadisticasbcra database as the postgres
-- superuser, e.g.:
--   sudo docker compose exec -T postgres psql -U postgres -d estadisticasbcra \
--     < /path/to/2026-09-25.scrape_status_last_ingested.sql

ALTER TABLE public.scrape_status ADD COLUMN last_ingested_at timestamptz;
