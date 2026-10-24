-- D005-K-QUERY202-PREADJUDICATION-EVIDENCE-v2 202a8: complete typed exact boundary replay.
-- SQL NULL and every non-NULL UTF-8 byte string remain distinct.  No trim,
-- normalization, semantic filter, sample, patient identifier, or timestamp is emitted.
WITH grouped AS MATERIALIZED (
    SELECT convert_to(route::text, 'UTF8') AS raw_bytes,
           count(*)::bigint AS exact_row_count
    FROM mimiciv_hosp.prescriptions
    GROUP BY convert_to(route::text, 'UTF8')
), completed AS (
    SELECT raw_bytes IS NULL AS raw_is_null,
           CASE WHEN raw_bytes IS NULL THEN ''::text
                ELSE replace(encode(raw_bytes, 'base64'), E'\n', '')
           END AS raw_value_base64,
           exact_row_count,
           CASE WHEN raw_bytes IS NULL THEN 0
                ELSE octet_length(raw_bytes)
           END::bigint AS raw_utf8_bytes
    FROM grouped
    UNION ALL
    SELECT true, ''::text, 0::bigint, 0::bigint
    WHERE NOT EXISTS (SELECT 1 FROM grouped WHERE raw_bytes IS NULL)
)
SELECT 2::integer AS schema_version,
       '202a8'::text AS stage,
       'prescriptions_route'::text AS source_key,
       'mimiciv_hosp.prescriptions.route'::text AS source_field,
       current_setting('transaction_isolation') AS transaction_isolation,
       current_setting('transaction_read_only') AS transaction_read_only,
       pg_current_snapshot()::text AS snapshot_token,
       raw_is_null,
       raw_value_base64,
       exact_row_count,
       raw_utf8_bytes
FROM completed
ORDER BY raw_is_null DESC, raw_value_base64;
