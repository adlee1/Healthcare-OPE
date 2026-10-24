-- D005 mapping preflight 202p1: exact eMAR-detail route vocabulary counts.
-- A zero-count NULL sentinel is emitted when the physical table has no NULL
-- route, so downstream validation can distinguish absence from omission.
WITH grouped AS MATERIALIZED (
    SELECT convert_to(route::text, 'UTF8') AS raw_bytes,
           count(*)::bigint AS exact_row_count
    FROM mimiciv_hosp.emar_detail
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
SELECT 1::integer AS schema_version,
       'emar_detail_route'::text AS stage,
       'emar_detail_route'::text AS source_key,
       'mimiciv_hosp.emar_detail.route'::text AS source_field,
       current_setting('transaction_isolation') AS transaction_isolation,
       current_setting('transaction_read_only') AS transaction_read_only,
       pg_current_snapshot()::text AS snapshot_token,
       raw_is_null,
       raw_value_base64,
       exact_row_count,
       raw_utf8_bytes
FROM completed
ORDER BY raw_is_null DESC, raw_value_base64;
