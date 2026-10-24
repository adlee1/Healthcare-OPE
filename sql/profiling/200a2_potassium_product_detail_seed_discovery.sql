-- Query 200, stage 2 of 3: derive identity-consistent local product-code
-- seeds from the exact detail-name set discovered by stage 1. The runner
-- replaces the one marker with validated, constant varchar(255) literals.
WITH
detail_names(raw_name) AS MATERIALIZED (
__DETAIL_NAME_VALUES__
),
lexical_detail_rows AS MATERIALIZED (
    SELECT d.emar_id,d.subject_id,d.emar_seq,d.product_code,
           d.product_description
    FROM detail_names n
    JOIN mimiciv_hosp.emar_detail d
      ON d.product_description=n.raw_name
    WHERE d.parent_field_ordinal IS NOT NULL
),
detail_identity AS MATERIALIZED (
    SELECT emar_id,count(*) AS source_rows,
           count(DISTINCT subject_id) AS subjects,min(subject_id) AS subject_id,
           count(*) FILTER (WHERE subject_id IS NULL) AS null_subjects,
           count(DISTINCT emar_seq) AS sequences,min(emar_seq) AS emar_seq,
           count(*) FILTER (WHERE emar_seq IS NULL) AS null_sequences
    FROM lexical_detail_rows
    GROUP BY emar_id
),
valid_detail_events AS MATERIALIZED (
    SELECT i.emar_id,i.source_rows
    FROM detail_identity i
    JOIN mimiciv_hosp.emar e USING (emar_id)
    WHERE i.subjects=1
      AND i.null_subjects=0
      AND i.sequences=1
      AND i.null_sequences=0
      AND e.subject_id=i.subject_id
      AND e.emar_seq=i.emar_seq
),
seed_codes AS MATERIALIZED (
    SELECT d.product_code::text AS product_code,
           count(*) AS lexical_detail_rows,
           count(DISTINCT d.emar_id) AS lexical_emar_events,
           count(DISTINCT d.product_description) AS lexical_descriptions
    FROM lexical_detail_rows d
    JOIN valid_detail_events v USING (emar_id)
    WHERE nullif(trim(d.product_code),'') IS NOT NULL
    GROUP BY d.product_code
),
payload AS (
    SELECT jsonb_build_object(
      'schema_version',1,
      'stage','detail_seed_discovery',
      'transaction_isolation',current_setting('transaction_isolation'),
      'transaction_read_only',current_setting('transaction_read_only'),
      'snapshot_token',pg_current_snapshot()::text,
      'identity_consistent_lexical_detail_product_rows',
        (SELECT coalesce(sum(source_rows),0) FROM valid_detail_events),
      'identity_consistent_lexical_detail_events',
        (SELECT count(*) FROM valid_detail_events),
      'seed_product_codes',coalesce(
        (SELECT jsonb_agg(jsonb_build_object(
          'product_code',product_code,
          'lexical_detail_rows',lexical_detail_rows,
          'lexical_emar_events',lexical_emar_events,
          'lexical_descriptions',lexical_descriptions)
         ORDER BY product_code)
         FROM seed_codes),
        '[]'::jsonb)
    ) AS value
)
SELECT replace(encode(convert_to(value::text,'UTF8'),'base64'),E'\n','')
       AS detail_seed_payload
FROM payload;
