-- Query 200 unbucketed pharmacy/prescription component.  This aggregate-only
-- SELECT reproduces the two order-name source-vocabulary paths, expands each
-- selected pharmacy key to all of its source components, and counts reverse
-- product-detail links.  It emits no patient identifiers.
WITH
discovery_metadata(non_null_emar_medication_names,non_null_detail_product_descriptions,non_null_pharmacy_medication_names,identity_consistent_lexical_detail_product_rows,identity_consistent_lexical_detail_events) AS (
    VALUES (__DISCOVERY_COUNTS__)
),
indexed_lexical_names(source_type,raw_name) AS MATERIALIZED (
__INDEXED_LEXICAL_NAMES__
),
prescription_lexical_names(raw_name) AS MATERIALIZED (
__PRESCRIPTION_NAMES__
),
pharmacy_name_rows AS MATERIALIZED (
    SELECT p.pharmacy_id,p.subject_id,p.hadm_id,p.poe_id,p.medication
    FROM mimiciv_hosp.pharmacy p
    WHERE p.medication = ANY (__PHARMACY_NAME_ARRAY__)
),
prescription_lexical_rows AS MATERIALIZED (
    -- prescriptions.drug has no leading lookup index in the audited schema;
    -- this is the single full scan assigned to the global order component.
    SELECT p.pharmacy_id,p.subject_id,p.hadm_id,p.poe_id,p.drug
    FROM mimiciv_hosp.prescriptions p
    WHERE p.drug = ANY (__PRESCRIPTION_NAME_ARRAY__)
),
source_names(source_type,evidence_path,raw_name) AS MATERIALIZED (
    SELECT 'pharmacy_medication'::text,'pharmacy_name'::text,raw_name
    FROM indexed_lexical_names
    WHERE source_type='pharmacy_medication'
    UNION ALL
    SELECT 'prescription_drug','prescription_name',raw_name
    FROM prescription_lexical_names
),
name_flags AS MATERIALIZED (
    SELECT source_type,evidence_path,raw_name,
           lower(regexp_replace(trim(raw_name),'[[:space:]]+',' ','g'))
             AS normalized_name,
           raw_name ~* 'potassium[[:space:]-]+(chloride|chl)([^[:alpha:]]|$)|(^|[^[:alnum:]])kcl([^[:alnum:]]|$)'
             AS focal_kcl_hint,
           raw_name ~* 'potassium[[:space:]-]+phosph|(^|[^[:alnum:]])k[ -]?phos([^[:alnum:]]|$)'
             AS phosphate_hint,
           raw_name ~* 'potassium[[:space:]-]+acetate' AS acetate_hint,
           raw_name ~* 'potassium[[:space:]-]+(citrate|bicarbonate|gluconate|iodide|permanganate|perchlorate|tartrate)'
             AS other_potassium_salt_hint,
           raw_name ~* 'losartan|penicillin|amoxicillin|clavulan|diclofenac|clorazepate'
             AS non_repletion_active_drug_hint
    FROM source_names
),
classified_names AS MATERIALIZED (
    SELECT *,
           focal_kcl_hint OR phosphate_hint OR acetate_hint
             AS broader_repletion_hint,
           NOT coalesce(focal_kcl_hint,false)
             AND NOT coalesce(phosphate_hint,false)
             AND NOT coalesce(acetate_hint,false)
             AND NOT coalesce(other_potassium_salt_hint,false)
             AND NOT coalesce(non_repletion_active_drug_hint,false)
             AS unresolved_name_hint,
           CASE
             WHEN non_repletion_active_drug_hint
               THEN 'non_repletion_active_drug_hint'
             WHEN focal_kcl_hint THEN 'focal_kcl_repletion_hint'
             WHEN phosphate_hint OR acetate_hint
               THEN 'broader_phosphate_or_acetate_repletion_hint'
             WHEN other_potassium_salt_hint
               THEN 'other_potassium_salt_review'
             ELSE 'unresolved_name_or_local_code_review'
           END AS source_review_stratum
    FROM name_flags
),
pharmacy_signal_by_key AS MATERIALIZED (
    SELECT p.pharmacy_id,count(*) AS source_rows,
           count(DISTINCT p.subject_id) AS source_subjects,
           min(p.subject_id) AS source_subject,
           count(*) FILTER (WHERE p.subject_id IS NULL)
             AS source_missing_subject_rows,
           count(DISTINCT p.hadm_id) AS source_admissions,
           min(p.hadm_id) AS source_admission,
           count(*) FILTER (WHERE p.hadm_id IS NULL)
             AS source_missing_admission_rows,
           count(DISTINCT nullif(trim(p.poe_id),'')) AS source_poe_keys,
           min(nullif(trim(p.poe_id),'')) AS source_poe_key,
           count(*) FILTER (WHERE nullif(trim(p.poe_id),'') IS NULL)
             AS source_missing_poe_rows,
           bool_or(n.focal_kcl_hint) AS focal_kcl_hint,
           bool_or(n.phosphate_hint OR n.acetate_hint)
             AS phosphate_or_acetate_hint,
           bool_or(n.other_potassium_salt_hint) AS other_potassium_salt_hint,
           bool_or(n.non_repletion_active_drug_hint) AS active_drug_hint,
           bool_or(n.unresolved_name_hint) AS unresolved_hint
    FROM pharmacy_name_rows p
    JOIN classified_names n
      ON n.source_type='pharmacy_medication'
     AND n.evidence_path='pharmacy_name' AND n.raw_name=p.medication
    GROUP BY p.pharmacy_id
),
pharmacy_by_key AS MATERIALIZED (
    -- pharmacy_id is the audited single-column primary key, so the lexical row
    -- is already the complete component set for that key.
    SELECT s.pharmacy_id,s.source_rows,s.source_rows AS full_component_rows,
           s.source_subjects,s.source_subject,s.source_missing_subject_rows,
           s.source_admissions,s.source_admission,s.source_missing_admission_rows,
           s.source_poe_keys,s.source_poe_key,s.source_missing_poe_rows,
           s.focal_kcl_hint,s.phosphate_or_acetate_hint,
           s.other_potassium_salt_hint,s.active_drug_hint,s.unresolved_hint
    FROM pharmacy_signal_by_key s
),
prescription_signal_by_key AS MATERIALIZED (
    SELECT p.pharmacy_id,count(*) AS source_rows,
           bool_or(n.focal_kcl_hint) AS focal_kcl_hint,
           bool_or(n.phosphate_hint OR n.acetate_hint)
             AS phosphate_or_acetate_hint,
           bool_or(n.other_potassium_salt_hint) AS other_potassium_salt_hint,
           bool_or(n.non_repletion_active_drug_hint) AS active_drug_hint,
           bool_or(n.unresolved_name_hint) AS unresolved_hint
    FROM prescription_lexical_rows p
    JOIN classified_names n
      ON n.source_type='prescription_drug'
     AND n.evidence_path='prescription_name' AND n.raw_name=p.drug
    GROUP BY p.pharmacy_id
),
prescription_by_key AS MATERIALIZED (
    SELECT s.pharmacy_id,max(s.source_rows) AS source_rows,
           count(p.pharmacy_id) AS full_component_rows,
           count(DISTINCT p.subject_id) AS source_subjects,
           min(p.subject_id) AS source_subject,
           count(*) FILTER (WHERE p.subject_id IS NULL)
             AS source_missing_subject_rows,
           count(DISTINCT p.hadm_id) AS source_admissions,
           min(p.hadm_id) AS source_admission,
           count(*) FILTER (WHERE p.hadm_id IS NULL)
             AS source_missing_admission_rows,
           count(DISTINCT nullif(trim(p.poe_id),'')) AS source_poe_keys,
           min(nullif(trim(p.poe_id),'')) AS source_poe_key,
           count(*) FILTER (WHERE nullif(trim(p.poe_id),'') IS NULL)
             AS source_missing_poe_rows,
           bool_or(s.focal_kcl_hint) AS focal_kcl_hint,
           bool_or(s.phosphate_or_acetate_hint)
             AS phosphate_or_acetate_hint,
           bool_or(s.other_potassium_salt_hint) AS other_potassium_salt_hint,
           bool_or(s.active_drug_hint) AS active_drug_hint,
           bool_or(s.unresolved_hint) AS unresolved_hint
    FROM prescription_signal_by_key s
    JOIN mimiciv_hosp.prescriptions p
      ON p.pharmacy_id::numeric=s.pharmacy_id::numeric
    GROUP BY s.pharmacy_id
),
order_keys AS MATERIALIZED (
    SELECT pharmacy_id FROM pharmacy_by_key
    UNION
    SELECT pharmacy_id FROM prescription_by_key
),
order_detail_links AS MATERIALIZED (
    -- Nearly all selected order keys have a lexical potassium-family component;
    -- use one exact numeric-key hash join instead of millions of random probes.
    -- Parent detail rows are not product evidence and remain excluded.
    SELECT d.emar_id,d.subject_id,d.emar_seq,d.pharmacy_id
    FROM order_keys k
    JOIN mimiciv_hosp.emar_detail d
      ON d.pharmacy_id::numeric=k.pharmacy_id::numeric
    WHERE d.parent_field_ordinal IS NOT NULL
),
vocabulary_rollup AS MATERIALIZED (
    SELECT 'pharmacy_medication'::text AS source_type,
           'pharmacy_name'::text AS evidence_path,
           p.medication::text AS raw_name,count(*) AS source_rows,
           0::bigint AS emar_events,
           count(DISTINCT p.pharmacy_id) AS pharmacy_keys,
           0::bigint AS local_product_codes,
           0::bigint AS rows_missing_local_product_code
    FROM pharmacy_name_rows p
    GROUP BY p.medication
    UNION ALL
    SELECT 'prescription_drug','prescription_name',p.drug::text,count(*),0,
           count(DISTINCT p.pharmacy_id),0,0
    FROM prescription_lexical_rows p
    GROUP BY p.drug
),
schema_guards AS MATERIALIZED (
    SELECT EXISTS (
             SELECT 1
             FROM pg_catalog.pg_index i
             JOIN pg_catalog.pg_class t ON t.oid=i.indrelid
             JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace
             JOIN pg_catalog.pg_attribute a
               ON a.attrelid=t.oid AND a.attnum=i.indkey[0]
             WHERE n.nspname='mimiciv_hosp' AND t.relname='pharmacy'
               AND i.indisprimary AND i.indisvalid AND i.indisready
               AND i.indnkeyatts=1 AND a.attname='pharmacy_id')
             AS pharmacy_id_primary_key_confirmed,
           (SELECT count(*)=4
                   AND bool_and(a.atttypid IN (
                         'pg_catalog.int2'::regtype,
                         'pg_catalog.int4'::regtype,
                         'pg_catalog.int8'::regtype))
            FROM pg_catalog.pg_class t
            JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace
            JOIN pg_catalog.pg_attribute a ON a.attrelid=t.oid
            WHERE n.nspname='mimiciv_hosp'
              AND t.relname IN ('pharmacy','prescriptions','emar','emar_detail')
              AND t.relkind IN ('r','p')
              AND a.attname='pharmacy_id'
              AND a.attnum>0 AND NOT a.attisdropped)
             AS pharmacy_id_integer_types_confirmed
)
SELECT 'closure_global_order_metadata'::text AS section,
       '{}'::jsonb AS dimensions,
       (SELECT count(*) FROM order_detail_links) AS records,
       jsonb_build_object(
         'non_null_emar_medication_names',
           (SELECT non_null_emar_medication_names FROM discovery_metadata),
         'non_null_detail_product_descriptions',
           (SELECT non_null_detail_product_descriptions FROM discovery_metadata),
         'non_null_pharmacy_medication_names',
           (SELECT non_null_pharmacy_medication_names FROM discovery_metadata),
         'selected_indexed_source_names',
           (SELECT count(*) FROM indexed_lexical_names),
         'selected_prescription_drug_names',
           (SELECT count(*) FROM prescription_lexical_names),
         'order_linked_detail_product_rows',
           (SELECT count(*) FROM order_detail_links),
         'selected_pharmacy_keys',(SELECT count(*) FROM pharmacy_by_key),
         'selected_pharmacy_full_component_rows',
           (SELECT coalesce(sum(full_component_rows),0) FROM pharmacy_by_key),
         'selected_prescription_keys',(SELECT count(*) FROM prescription_by_key),
         'selected_prescription_full_component_rows',
           (SELECT coalesce(sum(full_component_rows),0)
            FROM prescription_by_key),
         'identity_consistent_lexical_detail_events',
           (SELECT identity_consistent_lexical_detail_events
            FROM discovery_metadata),
         'declared_scope_exact',true,
         'pharmacy_id_primary_key_confirmed',
           g.pharmacy_id_primary_key_confirmed,
         'pharmacy_id_integer_types_confirmed',
           g.pharmacy_id_integer_types_confirmed,
         'lexical_scope',
           'query 199 potassium/bounded-KCl scope plus K-Phos/KPhos',
         'global_order_prescription_lexical_pass_count',1,
         'global_order_prescription_component_pass_count',1,
         'raw_identifiers_times_or_patient_text_emitted',false) AS counters
FROM schema_guards g
UNION ALL
SELECT 'source_vocabulary',jsonb_build_object(
         'source_type',v.source_type,'evidence_path',v.evidence_path,
         'raw_name',v.raw_name,'normalized_name',n.normalized_name,
         'source_review_stratum',n.source_review_stratum,
         'focal_kcl_hint',n.focal_kcl_hint,
         'broader_repletion_hint',n.broader_repletion_hint,
         'non_repletion_active_drug_hint',n.non_repletion_active_drug_hint),
       v.source_rows,
       jsonb_build_object(
         'source_rows',v.source_rows,'emar_events',v.emar_events,
         'pharmacy_keys',v.pharmacy_keys,
         'distinct_local_product_codes',v.local_product_codes,
         'rows_missing_local_product_code',v.rows_missing_local_product_code,
         'dictionary_value_is_patient_text',false,
         'source_review_stratum_is_final_policy',false)
FROM vocabulary_rollup v
JOIN classified_names n
  ON n.source_type=v.source_type AND n.evidence_path=v.evidence_path
 AND n.raw_name IS NOT DISTINCT FROM v.raw_name
ORDER BY section,records DESC,dimensions;
