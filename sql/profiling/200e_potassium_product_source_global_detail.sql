-- Query 200 unbucketed detail-vocabulary and local-code component.  This
-- aggregate-only SELECT reproduces the two detail source-vocabulary paths and
-- the local-product-code shape rows from the monolithic closure query.  It
-- emits no patient identifiers.
WITH
discovery_metadata(non_null_emar_medication_names,non_null_detail_product_descriptions,non_null_pharmacy_medication_names,identity_consistent_lexical_detail_product_rows,identity_consistent_lexical_detail_events) AS (
    VALUES (__DISCOVERY_COUNTS__)
),
indexed_lexical_names(source_type,raw_name) AS MATERIALIZED (
__INDEXED_LEXICAL_NAMES__
),
discovered_seed_product_codes(product_code,lexical_detail_rows,lexical_emar_events,lexical_descriptions) AS MATERIALIZED (
__SEED_PRODUCT_CODES__
),
seed_product_codes AS MATERIALIZED (
    SELECT product_code,lexical_detail_rows,lexical_emar_events,
           lexical_descriptions
    FROM discovered_seed_product_codes
),
selected_detail_rows AS MATERIALIZED (
    -- These native typed constant arrays preserve the indexed BitmapOr used by
    -- the closure query.  The VALUES dictionaries above remain private output
    -- inputs and do not drive the fact-table predicates.
    SELECT matched.*
    FROM (
        SELECT d.emar_id,d.subject_id,d.emar_seq,d.pharmacy_id,
               d.product_code,d.product_description,
               d.product_description = ANY (__DETAIL_NAME_ARRAY__) AS text_match,
               d.product_code = ANY (__SEED_PRODUCT_CODE_ARRAY__) AS code_match
        FROM mimiciv_hosp.emar_detail d
        WHERE d.parent_field_ordinal IS NOT NULL
    ) matched
    WHERE matched.text_match OR matched.code_match
),
detail_text_rows_raw AS MATERIALIZED (
    SELECT emar_id,subject_id,emar_seq,pharmacy_id,
           product_code,product_description
    FROM selected_detail_rows
    WHERE text_match
),
detail_code_rows AS MATERIALIZED (
    SELECT d.emar_id,d.subject_id,d.emar_seq,
           d.product_code,d.product_description,count(*) AS source_rows
    FROM selected_detail_rows d
    WHERE d.code_match
    GROUP BY d.emar_id,d.subject_id,d.emar_seq,
             d.product_code,d.product_description
),
source_names(source_type,evidence_path,raw_name) AS MATERIALIZED (
    SELECT 'detail_product_description'::text,
           'detail_text_seed'::text,raw_name
    FROM indexed_lexical_names
    WHERE source_type='detail_product_description'
    UNION ALL
    SELECT DISTINCT 'detail_product_description',
           'detail_local_code_closure',product_description::text
    FROM detail_code_rows
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
classified_detail_code_rows AS MATERIALIZED (
    -- Ordinary equality gives the large non-NULL closure a hash join.  NULL
    -- descriptions retain the monolithic query's explicit unresolved class.
    SELECT d.*,
           coalesce(n.focal_kcl_hint,false) AS focal_kcl_hint,
           coalesce(n.phosphate_hint,false)
             OR coalesce(n.acetate_hint,false) AS phosphate_or_acetate_hint,
           coalesce(n.other_potassium_salt_hint,false)
             AS other_potassium_salt_hint,
           coalesce(n.non_repletion_active_drug_hint,false) AS active_drug_hint,
           coalesce(n.unresolved_name_hint,true) AS unresolved_hint,
           coalesce(n.source_review_stratum,
                    'unresolved_name_or_local_code_review') AS source_review_stratum
    FROM detail_code_rows d
    LEFT JOIN classified_names n
      ON n.source_type='detail_product_description'
     AND n.evidence_path='detail_local_code_closure'
     AND n.raw_name=d.product_description
),
vocabulary_rollup AS MATERIALIZED (
    SELECT 'detail_product_description'::text AS source_type,
           'detail_text_seed'::text AS evidence_path,
           d.product_description::text AS raw_name,count(*) AS source_rows,
           count(DISTINCT d.emar_id) AS emar_events,
           0::bigint AS pharmacy_keys,
           count(DISTINCT nullif(trim(d.product_code),''))
             AS local_product_codes,
           count(*) FILTER (WHERE nullif(trim(d.product_code),'') IS NULL)
             AS rows_missing_local_product_code
    FROM detail_text_rows_raw d
    GROUP BY d.product_description
    UNION ALL
    SELECT 'detail_product_description','detail_local_code_closure',
           d.product_description::text,sum(d.source_rows),
           count(DISTINCT d.emar_id),0,
           count(DISTINCT nullif(trim(d.product_code),'')),
           coalesce(sum(d.source_rows) FILTER (
             WHERE nullif(trim(d.product_code),'') IS NULL),0)
    FROM detail_code_rows d
    GROUP BY d.product_description
),
seed_code_shapes AS MATERIALIZED (
    SELECT product_code,lexical_detail_rows,lexical_emar_events,
           lexical_descriptions
    FROM seed_product_codes
),
closure_code_shapes AS MATERIALIZED (
    SELECT d.product_code,sum(d.source_rows) AS closure_detail_rows,
           count(DISTINCT d.emar_id) AS closure_emar_event_memberships,
           count(DISTINCT d.product_description)
             AS nonnull_closure_descriptions,
           coalesce(sum(d.source_rows) FILTER (
             WHERE d.product_description IS NULL),0)
             AS missing_description_rows,
           count(DISTINCT d.source_review_stratum) AS review_strata,
           bool_or(d.unresolved_hint) AS unresolved_description_present,
           bool_or(d.source_review_stratum='non_repletion_active_drug_hint')
             AS active_drug_description_present
    FROM classified_detail_code_rows d
    GROUP BY d.product_code
),
code_shapes AS MATERIALIZED (
    SELECT s.product_code,s.lexical_detail_rows,s.lexical_emar_events,
           s.lexical_descriptions,c.closure_detail_rows,
           c.closure_emar_event_memberships,c.nonnull_closure_descriptions,
           c.missing_description_rows,c.review_strata,
           c.unresolved_description_present,c.active_drug_description_present,
           CASE WHEN c.nonnull_closure_descriptions=0
                  THEN 'no_nonnull_description'
                WHEN c.nonnull_closure_descriptions=1
                  THEN 'one_nonnull_description'
                ELSE 'multiple_nonnull_descriptions' END AS description_shape,
           CASE WHEN c.review_strata=1 THEN 'one_review_stratum'
                ELSE 'multiple_review_strata' END AS review_shape
    FROM seed_code_shapes s
    JOIN closure_code_shapes c USING (product_code)
)
SELECT 'closure_global_detail_metadata'::text AS section,
       '{}'::jsonb AS dimensions,
       (SELECT count(*) FROM selected_detail_rows) AS records,
       jsonb_build_object(
         'non_null_emar_medication_names',
           (SELECT non_null_emar_medication_names FROM discovery_metadata),
         'non_null_detail_product_descriptions',
           (SELECT non_null_detail_product_descriptions FROM discovery_metadata),
         'non_null_pharmacy_medication_names',
           (SELECT non_null_pharmacy_medication_names FROM discovery_metadata),
         'selected_indexed_source_names',
           (SELECT count(*) FROM indexed_lexical_names),
         'seed_local_product_codes',(SELECT count(*) FROM seed_product_codes),
         'detail_code_dictionary_names',
           (SELECT count(*) FROM classified_names
            WHERE source_type='detail_product_description'
              AND evidence_path='detail_local_code_closure'),
         'selected_detail_rows',(SELECT count(*) FROM selected_detail_rows),
         'detail_text_rows',(SELECT count(*) FROM detail_text_rows_raw),
         'detail_code_rows',
           (SELECT coalesce(sum(source_rows),0) FROM detail_code_rows),
         'largest_one_hop_code_detail_rows',
           (SELECT coalesce(max(closure_detail_rows),0) FROM code_shapes),
         'raw_lexical_detail_product_rows',
           (SELECT count(*) FROM detail_text_rows_raw),
         'identity_consistent_lexical_detail_product_rows',
           (SELECT identity_consistent_lexical_detail_product_rows
            FROM discovery_metadata),
         'identity_consistent_lexical_detail_events',
           (SELECT identity_consistent_lexical_detail_events
            FROM discovery_metadata),
         'declared_scope_exact',true,
         'lexical_scope',
           'query 199 potassium/bounded-KCl scope plus K-Phos/KPhos',
         'local_product_code_scope',
           'one exact-value hop from lexical detail product rows',
         'product_code_interpretation','MIMIC-local linkage token, not NDC',
         'raw_identifiers_times_or_patient_text_emitted',false) AS counters
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
UNION ALL
SELECT 'closure_detail_code_dictionary',jsonb_build_object(
         'raw_name',n.raw_name,
         'focal_kcl_hint',coalesce(n.focal_kcl_hint,false),
         'phosphate_or_acetate_hint',
           coalesce(n.phosphate_hint,false) OR coalesce(n.acetate_hint,false),
         'other_potassium_salt_hint',
           coalesce(n.other_potassium_salt_hint,false),
         'active_drug_hint',
           coalesce(n.non_repletion_active_drug_hint,false),
         'unresolved_hint',coalesce(n.unresolved_name_hint,true)),
       0,
       jsonb_build_object(
         'private_control_dictionary',true,
         'dictionary_value_is_patient_text',false)
FROM classified_names n
WHERE n.source_type='detail_product_description'
  AND n.evidence_path='detail_local_code_closure'
UNION ALL
SELECT 'local_product_code_shape',jsonb_build_object(
         'description_shape',description_shape,
         'review_shape',review_shape,
         'unresolved_description_present',unresolved_description_present,
         'active_drug_description_present',active_drug_description_present,
         'missing_description_present',missing_description_rows>0),
       count(*),
       jsonb_build_object(
         'local_product_codes',count(*),
         'lexical_seed_detail_rows',sum(lexical_detail_rows),
         'closure_detail_rows',sum(closure_detail_rows),
         'lexical_seed_event_memberships',sum(lexical_emar_events),
         'closure_event_memberships',sum(closure_emar_event_memberships),
         'event_memberships_are_additive_across_codes',true,
         'local_product_code_is_ndc',false,
         'local_product_code_used_for_final_product_identity',false)
FROM code_shapes
GROUP BY description_shape,review_shape,unresolved_description_present,
         active_drug_description_present,missing_description_rows>0
ORDER BY section,records DESC,dimensions;
