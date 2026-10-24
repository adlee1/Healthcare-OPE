-- Query 200, stage 1 of 3: discover the exact lexical source-name sets.
-- The runner decodes this transport payload only in private memory. This
-- statement must run inside the runner's REPEATABLE READ READ ONLY transaction.
WITH RECURSIVE
emar_name_walk(raw_name) AS (
    (SELECT medication
     FROM mimiciv_hosp.emar
     WHERE medication IS NOT NULL
     ORDER BY medication
     LIMIT 1)
    UNION ALL
    SELECT n.raw_name
    FROM emar_name_walk p
    CROSS JOIN LATERAL (
        SELECT medication AS raw_name
        FROM mimiciv_hosp.emar
        WHERE medication > p.raw_name
        ORDER BY medication
        LIMIT 1
    ) n
),
detail_name_walk(raw_name) AS (
    (SELECT product_description
     FROM mimiciv_hosp.emar_detail
     WHERE product_description IS NOT NULL
     ORDER BY product_description
     LIMIT 1)
    UNION ALL
    SELECT n.raw_name
    FROM detail_name_walk p
    CROSS JOIN LATERAL (
        SELECT product_description AS raw_name
        FROM mimiciv_hosp.emar_detail
        WHERE product_description > p.raw_name
        ORDER BY product_description
        LIMIT 1
    ) n
),
pharmacy_name_walk(raw_name) AS (
    (SELECT medication
     FROM mimiciv_hosp.pharmacy
     WHERE medication IS NOT NULL
     ORDER BY medication
     LIMIT 1)
    UNION ALL
    SELECT n.raw_name
    FROM pharmacy_name_walk p
    CROSS JOIN LATERAL (
        SELECT medication AS raw_name
        FROM mimiciv_hosp.pharmacy
        WHERE medication > p.raw_name
        ORDER BY medication
        LIMIT 1
    ) n
),
emar_names AS MATERIALIZED (
    SELECT raw_name
    FROM emar_name_walk
    WHERE raw_name ~* 'potassium|(^|[^[:alnum:]])k[ -]?phos([^[:alnum:]]|$)|(^|[^[:alnum:]])kcl([^[:alnum:]]|$)'
       OR raw_name ~* 'potassium[[:space:]-]+chl([^[:alpha:]]|$)'
),
detail_names AS MATERIALIZED (
    SELECT raw_name
    FROM detail_name_walk
    WHERE raw_name ~* 'potassium|(^|[^[:alnum:]])k[ -]?phos([^[:alnum:]]|$)|(^|[^[:alnum:]])kcl([^[:alnum:]]|$)'
       OR raw_name ~* 'potassium[[:space:]-]+chl([^[:alpha:]]|$)'
),
pharmacy_names AS MATERIALIZED (
    SELECT raw_name
    FROM pharmacy_name_walk
    WHERE raw_name ~* 'potassium|(^|[^[:alnum:]])k[ -]?phos([^[:alnum:]]|$)|(^|[^[:alnum:]])kcl([^[:alnum:]]|$)'
       OR raw_name ~* 'potassium[[:space:]-]+chl([^[:alpha:]]|$)'
),
prescription_names AS MATERIALIZED (
    SELECT DISTINCT drug AS raw_name
    FROM mimiciv_hosp.prescriptions
    WHERE drug ~* 'potassium|(^|[^[:alnum:]])k[ -]?phos([^[:alnum:]]|$)|(^|[^[:alnum:]])kcl([^[:alnum:]]|$)'
       OR drug ~* 'potassium[[:space:]-]+chl([^[:alpha:]]|$)'
),
payload AS (
    SELECT jsonb_build_object(
      'schema_version',1,
      'stage','names_discovery',
      'transaction_isolation',current_setting('transaction_isolation'),
      'transaction_read_only',current_setting('transaction_read_only'),
      'snapshot_token',pg_current_snapshot()::text,
      'non_null_emar_medication_names',(SELECT count(*) FROM emar_name_walk),
      'non_null_detail_product_descriptions',(SELECT count(*) FROM detail_name_walk),
      'non_null_pharmacy_medication_names',(SELECT count(*) FROM pharmacy_name_walk),
      'emar_names',coalesce(
          (SELECT jsonb_agg(raw_name ORDER BY raw_name) FROM emar_names),
          '[]'::jsonb),
      'detail_names',coalesce(
          (SELECT jsonb_agg(raw_name ORDER BY raw_name) FROM detail_names),
          '[]'::jsonb),
      'pharmacy_names',coalesce(
          (SELECT jsonb_agg(raw_name ORDER BY raw_name) FROM pharmacy_names),
          '[]'::jsonb),
      'prescription_names',coalesce(
          (SELECT jsonb_agg(raw_name ORDER BY raw_name) FROM prescription_names),
          '[]'::jsonb)
    ) AS value
)
SELECT replace(encode(convert_to(value::text,'UTF8'),'base64'),E'\n','')
       AS names_payload
FROM payload;
