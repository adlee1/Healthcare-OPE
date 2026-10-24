-- Metadata only. The caller must start a READ ONLY transaction and set a
-- statement_timeout before running this file. Do not embed connection secrets.
-- A successful connection does not establish the MIMIC release or provenance.
SELECT
    current_database() AS database_name,
    current_setting('server_version') AS postgres_version,
    current_setting('TimeZone') AS session_timezone,
    current_setting('transaction_read_only') AS transaction_read_only,
    current_setting('statement_timeout') AS statement_timeout;
