-- Query 201b: enumerate every distinct non-NULL eMAR product description.
-- This is a recursive next-key walk over the indexed source field.
WITH RECURSIVE name_walk(raw_name) AS (
    (SELECT product_description
     FROM mimiciv_hosp.emar_detail
     WHERE product_description IS NOT NULL
     ORDER BY product_description
     LIMIT 1)
    UNION ALL
    SELECT next_name.raw_name
    FROM name_walk previous_name
    CROSS JOIN LATERAL (
        SELECT product_description AS raw_name
        FROM mimiciv_hosp.emar_detail
        WHERE product_description > previous_name.raw_name
        ORDER BY product_description
        LIMIT 1
    ) next_name
),
payload AS (
    SELECT jsonb_build_object(
      'schema_version',1,
      'stage','detail_product_description',
      'source_key','detail_product_description',
      'source_field','mimiciv_hosp.emar_detail.product_description',
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
