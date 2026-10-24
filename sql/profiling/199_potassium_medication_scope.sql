-- Full potassium-token medication-scope audit, not IV eligibility, a delivered
-- dose, action, intervention universe, episode, label, or cohort.
-- No TABLESAMPLE and no detail scan. The existing medication btree supports a
-- monotone distinct-name walk; LIMIT 1 advances dictionary enumeration, never
-- truncates the cohort or chooses one clinical record. Names outside this
-- potassium/KCl lexical scope (including unrecognized brands) are not exhausted.
-- Only the selected medication-name and coded-status vocabulary is output,
-- never IDs, timestamps, laboratory values, product text or patient narrative.
-- Strata are neutral diagnostics for the next product-level audit; they do not
-- include/exclude treatments. In particular, the paper says IV potassium but
-- does not disclose whether potassium phosphate/acetate count.
-- Prescription components are aggregated PER pharmacy BEFORE the event join.
-- Auxiliary joins are bulk equality joins, not per-event LATERAL lookups.
-- int4 keys widen losslessly to int8 for the pharmacy equality: the lexical
-- dictionary's underestimated cardinality otherwise chose >270k random index
-- probes. Single-use transformations stay inline; grouping sets compute each
-- scope's distinct counts directly without materializing duplicate wide heads.
WITH RECURSIVE medication_walk(medication) AS (
    (SELECT medication FROM mimiciv_hosp.emar WHERE medication IS NOT NULL
     ORDER BY medication LIMIT 1)
    UNION ALL
    SELECT next_name.medication FROM medication_walk previous
    CROSS JOIN LATERAL (
        SELECT medication FROM mimiciv_hosp.emar WHERE medication > previous.medication
        ORDER BY medication LIMIT 1
    ) next_name
), name_flags AS MATERIALIZED (
    SELECT medication,
           lower(regexp_replace(trim(medication), '[[:space:]]+', ' ', 'g'))
             AS normalized_name,
           trim(medication) IN ('Potassium Chloride',
             'Potassium Chloride Replacement (Critical Care and Oncology)') AS two_exact_names,
           medication ~* 'potassium[[:space:]-]+chloride|(^|[^[:alnum:]])kcl([^[:alnum:]]|$)' AS chloride_name,
           medication ~* 'potassium[[:space:]-]+acetate' AS acetate_name,
           medication ~* 'potassium[[:space:]-]+phosph' AS phosphate_name,
           medication ~* 'potassium[[:space:]-]+(citrate|bicarbonate|gluconate|iodide|permanganate|perchlorate|tartrate)' AS other_salt_name,
           medication ~* 'losartan|penicillin|amoxicillin|clavulan|diclofenac|clorazepate' AS other_active_name_hint,
           medication ~* 'powder' AS powder_name_hint,
           medication ~* 'fetal[[:space:]]+reduction' AS fetal_reduction_name_hint,
           medication ~* 'critical[[:space:]]+care|oncology' AS critical_care_or_oncology_name_hint,
           medication ~* '(^|[^[:alnum:]])(oral|orally|tablet|tablets|tab|capsule|capsules|caps|packet|packets|elixir|syrup)([^[:alnum:]]|$)' AS oral_form_hint,
           medication ~* '(^|[^[:alnum:]])(topical|ophthalmic|ophth|otic|cutaneous|cream|ointment|irrigation|mouthwash|enema|rectal)([^[:alnum:]]|$)' AS local_external_hint,
           medication ~* '(^|[^[:alnum:]])(inhalation|inhaled|nebulizer|nebulized)([^[:alnum:]]|$)' AS inhaled_hint,
           medication ~* '(^|[^[:alnum:]])(injection|injectable|intravenous|iv|inj)([^[:alnum:]]|$)' AS injection_hint
    FROM medication_walk
    WHERE medication ~* 'potassium|(^|[^[:alnum:]])kcl([^[:alnum:]]|$)'
), names AS MATERIALIZED (
    SELECT f.*, CASE
        WHEN other_active_name_hint THEN 'other_active_ingredient_name_hint'
        WHEN chloride_name::int + acetate_name::int + phosphate_name::int + other_salt_name::int > 1
             THEN 'multiple_named_potassium_salts'
        WHEN chloride_name THEN 'chloride_or_kcl_name'
        WHEN acetate_name THEN 'acetate_name'
        WHEN phosphate_name THEN 'phosphate_name'
        WHEN other_salt_name THEN 'other_named_potassium_salt'
        ELSE 'other_potassium_token_unresolved' END AS name_family,
        CASE WHEN oral_form_hint::int + local_external_hint::int + inhaled_hint::int + injection_hint::int > 1
                  THEN 'multiple_route_or_form_name_hints'
             WHEN local_external_hint THEN 'local_external_name_hint'
             WHEN inhaled_hint THEN 'inhaled_name_hint'
             WHEN oral_form_hint THEN 'oral_form_name_hint'
             WHEN injection_hint THEN 'injection_name_hint_not_iv_proof'
             ELSE 'no_route_or_form_name_hint' END AS name_route_hint,
        CASE
          WHEN trim(medication) IN ('Potassium Chloride',
               'Potassium Chloride Replacement (Critical Care and Oncology)')
            THEN 'canonical_kcl_name'
          WHEN other_active_name_hint THEN 'other_active_drug_salt'
          WHEN chloride_name::int + acetate_name::int + phosphate_name::int
                 + other_salt_name::int > 1
            THEN 'multiple_named_potassium_salts'
          WHEN chloride_name THEN 'noncanonical_kcl_name'
          WHEN phosphate_name THEN 'potassium_phosphate_name'
          WHEN acetate_name THEN 'potassium_acetate_name'
          WHEN other_salt_name THEN 'other_potassium_salt'
          ELSE 'unresolved_potassium_name'
        END AS name_stratum,
        CASE
          WHEN powder_name_hint THEN 'powder_name_hint'
          WHEN fetal_reduction_name_hint THEN 'fetal_reduction_name_hint'
          WHEN critical_care_or_oncology_name_hint
            THEN 'critical_care_or_oncology_name_hint'
          ELSE 'no_special_use_name_hint'
        END AS special_use_name_hint
    FROM name_flags f
), events AS MATERIALIZED (
    SELECT e.emar_id,e.subject_id,e.hadm_id,e.pharmacy_id,e.poe_id,e.event_txt,
           e.charttime,e.storetime,n.*
    FROM names n JOIN mimiciv_hosp.emar e ON e.medication = n.medication
), pharmacy_keys AS MATERIALIZED (
    SELECT DISTINCT pharmacy_id FROM events WHERE pharmacy_id IS NOT NULL
), pharmacy_rows AS MATERIALIZED (
    SELECT p.pharmacy_id,p.subject_id,p.hadm_id,p.poe_id,p.route,
           CASE WHEN nullif(trim(p.route),'') IS NULL THEN 'missing'
                WHEN upper(trim(p.route)) IN ('IV','INTRAVENOUS','IV DRIP','IV BOLUS','IVP') THEN 'explicit_iv'
                WHEN upper(trim(p.route)) IN ('PO','ORAL','NG','OG','PO/NG','G TUBE','J TUBE','PEG','ENTERAL') THEN 'explicit_enteral'
                ELSE 'other_unmapped' END AS route_class
    FROM mimiciv_hosp.pharmacy p
    WHERE EXISTS (SELECT 1 FROM pharmacy_keys k
                  WHERE p.pharmacy_id::bigint = k.pharmacy_id::bigint)
), pharmacies AS MATERIALIZED (
    SELECT pharmacy_id,count(*) AS pharmacy_rows,min(subject_id) AS pharmacy_subject,
           min(hadm_id) AS pharmacy_hadm,count(DISTINCT subject_id) AS pharmacy_subjects,
           count(DISTINCT hadm_id) AS pharmacy_admissions,
           count(*) FILTER (WHERE subject_id IS NULL OR hadm_id IS NULL) AS pharmacy_missing_identity,
           count(DISTINCT nullif(trim(poe_id),'')) AS pharmacy_poe_count,
           min(nullif(trim(poe_id),'')) AS pharmacy_poe,
           count(*) FILTER (WHERE nullif(trim(poe_id),'') IS NULL) AS pharmacy_missing_poe,
           bool_or(route_class='explicit_iv') AS pharmacy_iv,
           bool_or(route_class='explicit_enteral') AS pharmacy_enteral,
           bool_or(route_class='other_unmapped') AS pharmacy_other,
           bool_or(route_class='missing') AS pharmacy_missing_route
    FROM pharmacy_rows GROUP BY pharmacy_id
), prescription_rows AS MATERIALIZED (
    SELECT p.pharmacy_id,p.subject_id,p.hadm_id,p.poe_id,p.route,p.drug_type,
           CASE WHEN nullif(trim(p.route),'') IS NULL THEN 'missing'
                WHEN upper(trim(p.route)) IN ('IV','INTRAVENOUS','IV DRIP','IV BOLUS','IVP') THEN 'explicit_iv'
                WHEN upper(trim(p.route)) IN ('PO','ORAL','NG','OG','PO/NG','G TUBE','J TUBE','PEG','ENTERAL') THEN 'explicit_enteral'
                ELSE 'other_unmapped' END AS route_class
    FROM pharmacy_keys k JOIN mimiciv_hosp.prescriptions p USING (pharmacy_id)
), prescriptions AS MATERIALIZED (
    SELECT pharmacy_id,count(*) AS component_rows,min(subject_id) AS rx_subject,min(hadm_id) AS rx_hadm,
           count(DISTINCT subject_id) AS rx_subjects,count(DISTINCT hadm_id) AS rx_admissions,
           count(*) FILTER (WHERE subject_id IS NULL OR hadm_id IS NULL) AS rx_missing_identity,
           count(DISTINCT nullif(trim(poe_id),'')) AS rx_poe_count,
           min(nullif(trim(poe_id),'')) AS rx_poe,
           count(*) FILTER (WHERE nullif(trim(poe_id),'') IS NULL) AS rx_missing_poe,
           bool_or(route_class='explicit_iv') AS rx_iv,
           bool_or(route_class='explicit_enteral') AS rx_enteral,
           bool_or(route_class='other_unmapped') AS rx_other,
           bool_or(route_class='missing') AS rx_missing_route
    FROM prescription_rows GROUP BY pharmacy_id
), linked AS NOT MATERIALIZED (
    SELECT e.*,p.pharmacy_rows,p.pharmacy_poe_count,p.pharmacy_poe,p.pharmacy_missing_poe,
           p.pharmacy_iv,p.pharmacy_enteral,p.pharmacy_other,p.pharmacy_missing_route,
           r.component_rows,r.rx_poe_count,r.rx_poe,r.rx_missing_poe,
           r.rx_iv,r.rx_enteral,r.rx_other,r.rx_missing_route,
           CASE WHEN e.pharmacy_id IS NULL THEN 'missing_head_key'
                WHEN p.pharmacy_id IS NULL THEN 'key_not_found'
                WHEN e.subject_id IS NULL OR e.hadm_id IS NULL THEN 'missing_event_identity'
                WHEN p.pharmacy_subjects<>1 OR p.pharmacy_admissions<>1
                     OR p.pharmacy_missing_identity>0
                    THEN 'ambiguous_pharmacy_identity'
                WHEN p.pharmacy_subject IS DISTINCT FROM e.subject_id
                     OR p.pharmacy_hadm IS DISTINCT FROM e.hadm_id
                    THEN 'identity_conflict' ELSE 'identity_consistent' END AS pharmacy_link,
           CASE WHEN e.pharmacy_id IS NULL THEN 'missing_head_key'
                WHEN r.pharmacy_id IS NULL THEN 'key_not_found'
                WHEN e.subject_id IS NULL OR e.hadm_id IS NULL THEN 'missing_event_identity'
                WHEN r.rx_subjects<>1 OR r.rx_admissions<>1 OR r.rx_missing_identity>0
                    THEN 'ambiguous_prescription_identity'
                WHEN r.rx_subject IS DISTINCT FROM e.subject_id OR r.rx_hadm IS DISTINCT FROM e.hadm_id
                    THEN 'identity_conflict' ELSE 'identity_consistent' END AS prescription_link
    FROM events e LEFT JOIN pharmacies p USING (pharmacy_id)
    LEFT JOIN prescriptions r USING (pharmacy_id)
), evidence AS NOT MATERIALIZED (
    SELECT l.*,
           (pharmacy_link='identity_consistent' AND pharmacy_iv)
            OR (prescription_link='identity_consistent' AND rx_iv) AS has_iv_order_route,
           (pharmacy_link='identity_consistent' AND pharmacy_enteral)
            OR (prescription_link='identity_consistent' AND rx_enteral) AS has_enteral_order_route,
           (pharmacy_link='identity_consistent' AND pharmacy_other)
            OR (prescription_link='identity_consistent' AND rx_other) AS has_other_order_route
    FROM linked l
), assessed AS MATERIALIZED (
    SELECT e.*, CASE WHEN has_iv_order_route AND has_enteral_order_route THEN 'iv_enteral_conflict'
                    WHEN has_other_order_route THEN 'other_unmapped_route_present'
                    WHEN has_iv_order_route THEN 'iv_order_route_only'
                    WHEN has_enteral_order_route THEN 'enteral_order_route_only'
                    ELSE 'no_valid_known_order_route' END AS order_route_pattern,
           CASE WHEN event_txt = 'Administered' THEN 'administered_exact'
                WHEN event_txt = 'Partial Administered' THEN 'partial_administered'
                WHEN event_txt = 'Delayed Administered' THEN 'delayed_administered'
                WHEN event_txt IN ('Started','Delayed Started','Restarted')
                  THEN 'start_or_restart_control'
                WHEN event_txt IN ('Not Given','Not Given per Sliding Scale','Hold Dose')
                  THEN 'not_given_or_hold'
                WHEN event_txt IN ('Stopped','Stopped - Unscheduled','Confirmed','Flushed','Not Flushed')
                  THEN 'other_control_record'
                WHEN event_txt IS NULL THEN 'missing_status'
                ELSE 'other_status' END AS event_status_class
    FROM evidence e
)
SELECT 'dictionary_metadata'::text AS section,'{}'::jsonb AS dimensions,
       (SELECT count(*) FROM medication_walk) AS records,
       jsonb_build_object(
           'non_null_distinct_medication_names',(SELECT count(*) FROM medication_walk),
           'selected_distinct_medication_names',(SELECT count(*) FROM names),
           'blank_distinct_medication_names',(SELECT count(*) FROM medication_walk
                                               WHERE nullif(trim(medication),'') IS NULL),
           'null_medication_heads',(SELECT count(*) FROM mimiciv_hosp.emar
                                    WHERE medication IS NULL),
           'blank_medication_heads',(SELECT count(*) FROM medication_walk n
                                     JOIN mimiciv_hosp.emar e ON e.medication=n.medication
                                     WHERE nullif(trim(n.medication),'') IS NULL),
           'vocabulary_complete_within_declared_lexical_scope',true,
           'full_emar_row_count_not_computed',true,
           'null_medication_product_sources_examined',false,
           'unrecognized_brand_sources_examined',false,
           'scope_exhausts_all_potassium_interventions',false,
           'prescription_components_preaggregated',true,
           'pharmacy_rows_preaggregated',true,
           'raw_identifiers_times_or_patient_text_emitted',false) AS counters
UNION ALL
SELECT 'scope_conservation',jsonb_build_object('scope',
       CASE WHEN grouping(two_exact_names)=1 THEN 'all_selected_names'
            WHEN two_exact_names THEN 'canonical_trim_exact_names'
            ELSE 'other_selected_names' END),count(*),
       jsonb_build_object(
           'emar_heads',count(DISTINCT emar_id),
           'subjects',count(DISTINCT subject_id),
           'admissions',count(DISTINCT hadm_id),
           'medication_names',count(DISTINCT medication),
           'pharmacy_keys',count(DISTINCT pharmacy_id),
           'poe_keys',count(DISTINCT nullif(trim(poe_id),'')),
           'missing_subject_heads',count(*) FILTER (WHERE subject_id IS NULL),
           'missing_admission_heads',count(*) FILTER (WHERE hadm_id IS NULL),
           'missing_pharmacy_key_heads',count(*) FILTER (WHERE pharmacy_id IS NULL),
           'missing_poe_key_heads',count(*) FILTER (WHERE nullif(trim(poe_id),'') IS NULL),
           'missing_charttime_heads',count(*) FILTER (WHERE charttime IS NULL),
           'missing_storetime_heads',count(*) FILTER (WHERE storetime IS NULL),
           'storetime_before_charttime_heads',count(*) FILTER (WHERE storetime<charttime),
           'administered_exact_heads',count(*) FILTER (WHERE event_status_class='administered_exact'),
           'partial_administered_heads',count(*) FILTER (WHERE event_status_class='partial_administered'),
           'delayed_administered_heads',count(*) FILTER (WHERE event_status_class='delayed_administered'),
           'start_or_restart_control_heads',count(*) FILTER (WHERE event_status_class='start_or_restart_control'),
           'not_given_or_hold_heads',count(*) FILTER (WHERE event_status_class='not_given_or_hold'),
           'other_control_record_heads',count(*) FILTER (WHERE event_status_class='other_control_record'),
           'missing_status_heads',count(*) FILTER (WHERE event_status_class='missing_status'),
           'other_status_heads',count(*) FILTER (WHERE event_status_class='other_status'),
           'iv_enteral_conflict_heads',count(*) FILTER (WHERE order_route_pattern='iv_enteral_conflict'),
           'other_unmapped_route_present_heads',count(*) FILTER (WHERE order_route_pattern='other_unmapped_route_present'),
           'iv_order_route_only_heads',count(*) FILTER (WHERE order_route_pattern='iv_order_route_only'),
           'enteral_order_route_only_heads',count(*) FILTER (WHERE order_route_pattern='enteral_order_route_only'),
           'no_valid_known_order_route_heads',count(*) FILTER (WHERE order_route_pattern='no_valid_known_order_route'),
           'pharmacy_identity_consistent_heads',count(*) FILTER (WHERE pharmacy_link='identity_consistent'),
           'prescription_identity_consistent_heads',count(*) FILTER (WHERE prescription_link='identity_consistent'),
           'formal_cohort',false,'detail_rows_examined',false,
           'route_is_administration_proof',false)
FROM assessed GROUP BY GROUPING SETS ((),(two_exact_names)) HAVING count(*)>0
UNION ALL
SELECT 'name_stratum_summary',jsonb_build_object('name_stratum',name_stratum),count(*),
       jsonb_build_object(
           'emar_heads',count(DISTINCT emar_id),
           'subjects',count(DISTINCT subject_id),
           'admissions',count(DISTINCT hadm_id),
           'medication_names',count(DISTINCT medication),
           'administered_exact_heads',count(*) FILTER (WHERE event_status_class='administered_exact'),
           'partial_administered_heads',count(*) FILTER (WHERE event_status_class='partial_administered'),
           'delayed_administered_heads',count(*) FILTER (WHERE event_status_class='delayed_administered'),
           'start_or_restart_control_heads',count(*) FILTER (WHERE event_status_class='start_or_restart_control'),
           'not_given_or_hold_heads',count(*) FILTER (WHERE event_status_class='not_given_or_hold'),
           'other_control_record_heads',count(*) FILTER (WHERE event_status_class='other_control_record'),
           'missing_status_heads',count(*) FILTER (WHERE event_status_class='missing_status'),
           'other_status_heads',count(*) FILTER (WHERE event_status_class='other_status'),
           'iv_enteral_conflict_heads',count(*) FILTER (WHERE order_route_pattern='iv_enteral_conflict'),
           'other_unmapped_route_present_heads',count(*) FILTER (WHERE order_route_pattern='other_unmapped_route_present'),
           'iv_order_route_only_heads',count(*) FILTER (WHERE order_route_pattern='iv_order_route_only'),
           'enteral_order_route_only_heads',count(*) FILTER (WHERE order_route_pattern='enteral_order_route_only'),
           'no_valid_known_order_route_heads',count(*) FILTER (WHERE order_route_pattern='no_valid_known_order_route'),
           'missing_admission_heads',count(*) FILTER (WHERE hadm_id IS NULL),
           'missing_pharmacy_key_heads',count(*) FILTER (WHERE pharmacy_id IS NULL),
           'storetime_before_charttime_heads',count(*) FILTER (WHERE storetime<charttime))
FROM assessed GROUP BY name_stratum
UNION ALL
SELECT 'medication_scope_vocabulary',jsonb_build_object(
       'raw_medication',medication,'normalized_name',normalized_name,
       'name_stratum',name_stratum,'name_family',name_family,
       'name_route_hint',name_route_hint,'special_use_name_hint',special_use_name_hint,
       'powder_name_hint',powder_name_hint,
       'fetal_reduction_name_hint',fetal_reduction_name_hint,
       'critical_care_or_oncology_name_hint',critical_care_or_oncology_name_hint,
       'canonical_trim_exact_name',two_exact_names),count(*),
       jsonb_build_object(
           'emar_heads',count(DISTINCT emar_id),
           'subjects',count(DISTINCT subject_id),
           'admissions',count(DISTINCT hadm_id),
           'administered_exact_heads',count(*) FILTER (WHERE event_status_class='administered_exact'),
           'partial_administered_heads',count(*) FILTER (WHERE event_status_class='partial_administered'),
           'delayed_administered_heads',count(*) FILTER (WHERE event_status_class='delayed_administered'),
           'start_or_restart_control_heads',count(*) FILTER (WHERE event_status_class='start_or_restart_control'),
           'not_given_or_hold_heads',count(*) FILTER (WHERE event_status_class='not_given_or_hold'),
           'other_control_record_heads',count(*) FILTER (WHERE event_status_class='other_control_record'),
           'missing_status_heads',count(*) FILTER (WHERE event_status_class='missing_status'),
           'other_status_heads',count(*) FILTER (WHERE event_status_class='other_status'),
           'iv_enteral_conflict_heads',count(*) FILTER (WHERE order_route_pattern='iv_enteral_conflict'),
           'other_unmapped_route_present_heads',count(*) FILTER (WHERE order_route_pattern='other_unmapped_route_present'),
           'iv_order_route_only_heads',count(*) FILTER (WHERE order_route_pattern='iv_order_route_only'),
           'enteral_order_route_only_heads',count(*) FILTER (WHERE order_route_pattern='enteral_order_route_only'),
           'no_valid_known_order_route_heads',count(*) FILTER (WHERE order_route_pattern='no_valid_known_order_route'),
           'missing_subject_heads',count(*) FILTER (WHERE subject_id IS NULL),
           'missing_admission_heads',count(*) FILTER (WHERE hadm_id IS NULL),
           'missing_pharmacy_key_heads',count(*) FILTER (WHERE pharmacy_id IS NULL),
           'missing_poe_key_heads',count(*) FILTER (WHERE nullif(trim(poe_id),'') IS NULL),
           'missing_charttime_heads',count(*) FILTER (WHERE charttime IS NULL),
           'missing_storetime_heads',count(*) FILTER (WHERE storetime IS NULL),
           'storetime_before_charttime_heads',count(*) FILTER (WHERE storetime<charttime))
FROM assessed GROUP BY medication,normalized_name,name_stratum,name_family,name_route_hint,
                       special_use_name_hint,powder_name_hint,fetal_reduction_name_hint,
                       critical_care_or_oncology_name_hint,two_exact_names
UNION ALL
SELECT 'medication_event_route',jsonb_build_object(
       'raw_medication',medication,'normalized_name',normalized_name,
       'name_stratum',name_stratum,'event_txt',event_txt,
       'event_status_class',event_status_class,'pharmacy_link',pharmacy_link,
       'prescription_link',prescription_link,'order_route_pattern',order_route_pattern),count(*),
       jsonb_build_object(
           'emar_heads',count(DISTINCT emar_id),
           'subjects',count(DISTINCT subject_id),
           'admissions',count(DISTINCT hadm_id),
           'event_pharmacy_poe_disagreement_heads',count(*) FILTER (
               WHERE nullif(trim(poe_id),'') IS NOT NULL AND pharmacy_poe_count=1
                 AND pharmacy_poe IS NOT NULL AND trim(poe_id)<>pharmacy_poe),
           'event_prescription_poe_disagreement_heads',count(*) FILTER (
               WHERE nullif(trim(poe_id),'') IS NOT NULL AND rx_poe_count=1
                 AND rx_poe IS NOT NULL AND trim(poe_id)<>rx_poe),
           'heads_without_pharmacy_match',count(*) FILTER (WHERE pharmacy_rows IS NULL),
           'heads_with_pharmacy_match_but_poe_not_unique_or_missing',count(*) FILTER (
               WHERE pharmacy_rows IS NOT NULL AND (pharmacy_poe_count IS DISTINCT FROM 1
                  OR coalesce(pharmacy_missing_poe,0)>0)),
           'heads_without_prescription_match',count(*) FILTER (WHERE component_rows IS NULL),
           'heads_with_prescription_match_but_poe_not_unique_or_missing',count(*) FILTER (
               WHERE component_rows IS NOT NULL AND (rx_poe_count IS DISTINCT FROM 1
                  OR coalesce(rx_missing_poe,0)>0)),
           'identity_consistent_pharmacy_heads_with_missing_route',count(*) FILTER (
               WHERE pharmacy_link='identity_consistent' AND pharmacy_missing_route),
           'identity_consistent_prescription_heads_with_missing_route',count(*) FILTER (
               WHERE prescription_link='identity_consistent' AND rx_missing_route),
           'heads_with_multiple_pharmacy_rows',count(*) FILTER (WHERE pharmacy_rows>1),
           'heads_with_multiple_prescription_components',count(*) FILTER (WHERE component_rows>1),
           'missing_charttime_heads',count(*) FILTER (WHERE charttime IS NULL),
           'missing_storetime_heads',count(*) FILTER (WHERE storetime IS NULL),
           'storetime_before_charttime_heads',count(*) FILTER (WHERE storetime<charttime),
           'route_is_administration_proof',false)
FROM assessed GROUP BY medication,normalized_name,name_stratum,event_txt,event_status_class,
                       pharmacy_link,prescription_link,order_route_pattern
UNION ALL
SELECT 'scope_guards','{}'::jsonb,count(*),jsonb_build_object(
           'vocabulary_complete_within_declared_lexical_scope',true,
           'neutral_name_strata_only',true,
           'prescription_components_preaggregated',true,
           'pharmacy_rows_preaggregated',true,
           'detail_rows_examined',false,
           'product_identity_decided',false,
           'final_source_policy',false,
           'full_intervention_coverage',false,
           'route_is_administration_proof',false,
           'delivered_dose_defined',false,
           'formal_action',false,
           'zero_action_constructed',false,
           'formal_episode',false,
           'formal_label',false,
           'formal_non_icu_rule',false,
           'formal_cohort',false,
           'raw_identifiers_times_or_patient_text_emitted',false)
FROM assessed
ORDER BY section,records DESC,dimensions;
