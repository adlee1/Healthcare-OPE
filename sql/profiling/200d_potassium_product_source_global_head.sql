-- Query 200 unbucketed head-vocabulary component.  This aggregate-only SELECT
-- supplies the exact head rows and head-side metadata needed to reconstruct the
-- original global closure output.  It emits no patient identifiers.
WITH
discovery_metadata(non_null_emar_medication_names,non_null_detail_product_descriptions,non_null_pharmacy_medication_names,identity_consistent_lexical_detail_product_rows,identity_consistent_lexical_detail_events) AS (
    VALUES (__DISCOVERY_COUNTS__)
),
indexed_lexical_names(source_type,raw_name) AS MATERIALIZED (
__INDEXED_LEXICAL_NAMES__
),
emar_lexical_name_flags AS MATERIALIZED (
    SELECT raw_name,
           raw_name ~* 'potassium|(^|[^[:alnum:]])kcl([^[:alnum:]]|$)'
             AS query199_head_scope
    FROM indexed_lexical_names
    WHERE source_type='emar_medication'
),
direct_rows AS MATERIALIZED (
    SELECT e.emar_id,e.medication,n.query199_head_scope
    FROM mimiciv_hosp.emar e
    JOIN emar_lexical_name_flags n ON n.raw_name=e.medication
    WHERE e.medication = ANY (__EMAR_NAME_ARRAY__)
),
name_flags AS MATERIALIZED (
    SELECT 'emar_medication'::text AS source_type,'head_text'::text AS evidence_path,
           raw_name,
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
    FROM indexed_lexical_names
    WHERE source_type='emar_medication'
),
classified_names AS MATERIALIZED (
    SELECT *,focal_kcl_hint OR phosphate_hint OR acetate_hint
             AS broader_repletion_hint,
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
vocabulary_rollup AS MATERIALIZED (
    SELECT d.medication::text AS raw_name,count(*) AS source_rows,
           count(DISTINCT d.emar_id) AS emar_events
    FROM direct_rows d
    GROUP BY d.medication
)
SELECT 'closure_global_head_metadata'::text AS section,'{}'::jsonb AS dimensions,
       count(*) AS records,
       jsonb_build_object(
         'non_null_emar_medication_names',
           (SELECT non_null_emar_medication_names FROM discovery_metadata),
         'non_null_detail_product_descriptions',
           (SELECT non_null_detail_product_descriptions FROM discovery_metadata),
         'non_null_pharmacy_medication_names',
           (SELECT non_null_pharmacy_medication_names FROM discovery_metadata),
         'selected_indexed_source_names',(SELECT count(*) FROM indexed_lexical_names),
         'direct_head_evidence_heads',count(*),
         'query199_head_scope_distinct_heads',count(*) FILTER (
             WHERE query199_head_scope),
         'query199_prior_real_audit_reference_heads',559191,
         'query199_reference_requires_real_audit_comparison',true,
         'raw_identifiers_times_or_patient_text_emitted',false) AS counters
FROM direct_rows
UNION ALL
SELECT 'source_vocabulary',jsonb_build_object(
         'source_type','emar_medication','evidence_path','head_text',
         'raw_name',v.raw_name,'normalized_name',n.normalized_name,
         'source_review_stratum',n.source_review_stratum,
         'focal_kcl_hint',n.focal_kcl_hint,
         'broader_repletion_hint',n.broader_repletion_hint,
         'non_repletion_active_drug_hint',n.non_repletion_active_drug_hint),
       v.source_rows,
       jsonb_build_object(
         'source_rows',v.source_rows,'emar_events',v.emar_events,
         'pharmacy_keys',0,'distinct_local_product_codes',0,
         'rows_missing_local_product_code',0,
         'dictionary_value_is_patient_text',false,
         'source_review_stratum_is_final_policy',false)
FROM vocabulary_rollup v
JOIN classified_names n ON n.raw_name=v.raw_name
ORDER BY section,records DESC,dimensions;
