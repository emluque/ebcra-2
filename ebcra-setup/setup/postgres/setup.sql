 CREATE USER estadisticasbcra WITH PASSWORD 'estadisticasbcra-password';
  CREATE USER "ebcra-scraping" WITH PASSWORD 'scraping-password';

  -- Database
  CREATE DATABASE estadisticasbcra OWNER postgres;

  -- Connect to the new database
  \c estadisticasbcra

  -- Schema usage
  GRANT CONNECT ON DATABASE estadisticasbcra TO estadisticasbcra;
  GRANT CONNECT ON DATABASE estadisticasbcra TO "ebcra-scraping";

  GRANT USAGE ON SCHEMA public TO estadisticasbcra;
  GRANT USAGE ON SCHEMA public TO "ebcra-scraping";

  -- estadisticasbcra (Go API) — read-only
  GRANT SELECT ON ALL TABLES IN SCHEMA public TO estadisticasbcra;
  GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO estadisticasbcra;

  -- ebcra-scraping — full write access
  GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO "ebcra-scraping";
  GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO "ebcra-scraping";

  -- Default privileges for future objects
  ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO estadisticasbcra;
  ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO estadisticasbcra;
  ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO "ebcra-scraping";
  ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO "ebcra-scraping";
