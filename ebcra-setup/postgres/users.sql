CREATE USER "ebcra-scraping" WITH PASSWORD 'scrapeandotetodo';
GRANT CONNECT ON DATABASE estadisticasbcra TO "ebcra-scraping";                                                                                                                            
GRANT USAGE ON SCHEMA public TO "ebcra-scraping";                                                                                                                                          
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO "ebcra-scraping";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE ON TABLES TO "ebcra-scraping";