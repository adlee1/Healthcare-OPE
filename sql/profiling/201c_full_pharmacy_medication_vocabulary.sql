-- Query 201c: enumerate every distinct non-NULL pharmacy medication value.
-- This is a recursive next-key walk over the indexed source field.
WITH RECURSIVE name_walk(raw_name) AS (
    (SELECT medication
     FROM mimiciv_hosp.pharmacy
     WHERE medication IS NOT NULL
     ORDER BY medication
     LIMIT 1)
    UNION ALL
    SELECT next_name.raw_name
    FROM name_walk previous_name
    CROSS JOIN LATERAL (
        SELECT medication AS raw_name
        FROM mimiciv_hosp.pharmacy
        WHERE medication > previous_name.raw_name
        ORDER BY medication
        LIMIT 1
    ) next_name
),
payload AS (
    SELECT jsonb_build_object(
      'schema_version',1,
      'stage','pharmacy_medication',
      'source_key','pharmacy_medication',
      'source_field','mimiciv_hosp.pharmacy.medication',
      'enumeration_method','recursive_index_walk',
      'transaction_isolation',current_setting('transaction_isolation'),
      'transaction_read_only',current_setting('transaction_read_only'),
      'snapshot_token',pg_current_snapshot()::text,
      'distinct_nonnull_values',(SELECT count(*) FROM name_walk),
      'values',coalesce(
          (SELECT jsonb_agg(raw_name ORDER BY raw_name) FROM name_walk),
          '[]'::jsonb)
    ) AS value
)
SELECT replace(encode(convert_to(value::text,'UTF8'),'base64'),E'\n','')
       AS vocabulary_payload
FROM payload;
