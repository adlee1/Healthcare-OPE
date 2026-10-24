-- Query 201d: enumerate every distinct non-NULL prescription drug value.
-- The audited schema has no leading lookup index for prescriptions.drug, so
-- this stage performs one bounded full DISTINCT scan in the shared snapshot.
WITH names AS MATERIALIZED (
    SELECT DISTINCT drug AS raw_name
    FROM mimiciv_hosp.prescriptions
    WHERE drug IS NOT NULL
),
payload AS (
    SELECT jsonb_build_object(
      'schema_version',1,
      'stage','prescription_drug',
      'source_key','prescription_drug',
      'source_field','mimiciv_hosp.prescriptions.drug',
      'enumeration_method','full_distinct_scan',
      'transaction_isolation',current_setting('transaction_isolation'),
      'transaction_read_only',current_setting('transaction_read_only'),
      'snapshot_token',pg_current_snapshot()::text,
      'distinct_nonnull_values',(SELECT count(*) FROM names),
      'values',coalesce(
          (SELECT jsonb_agg(raw_name ORDER BY raw_name) FROM names),
          '[]'::jsonb)
    ) AS value
)
SELECT replace(encode(convert_to(value::text,'UTF8'),'base64'),E'\n','')
       AS vocabulary_payload
FROM payload;
