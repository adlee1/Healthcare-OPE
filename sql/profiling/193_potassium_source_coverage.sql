-- Full eMAR HEAD/source audit, not IV eligibility, delivered dose or a cohort.
-- No TABLESAMPLE and no detail scan. The existing medication btree supports a
-- monotone distinct-name walk; LIMIT 1 advances dictionary enumeration, never
-- truncates the cohort or chooses one clinical record. Names outside this
-- potassium/KCl lexical scope (including unrecognized brands) are not exhausted.
-- Only selected medication vocabulary is output, never patient text/IDs/times.
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
           trim(medication) IN ('Potassium Chloride',
             'Potassium Chloride Replacement (Critical Care and Oncology)') AS two_exact_names,
           medication ~* 'potassium[[:space:]-]+chloride|(^|[^[:alnum:]])kcl([^[:alnum:]]|$)' AS chloride_name,
           medication ~* 'potassium[[:space:]-]+acetate' AS acetate_name,
           medication ~* 'potassium[[:space:]-]+phosph' AS phosphate_name,
           medication ~* 'potassium[[:space:]-]+(citrate|bicarbonate|gluconate|iodide|permanganate|perchlorate|tartrate)' AS other_salt_name,
           medication ~* 'losartan|penicillin|amoxicillin|clavulan|diclofenac|clorazepate' AS other_active_name_hint,
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
             ELSE 'no_route_or_form_name_hint' END AS name_route_hint
    FROM name_flags f
), events AS MATERIALIZED (
    SELECT e.emar_id,e.subject_id,e.hadm_id,e.pharmacy_id,e.poe_id,e.event_txt,
           e.charttime,e.storetime,n.*
    FROM names n JOIN mimiciv_hosp.emar e ON e.medication = n.medication
), pharmacy_keys AS MATERIALIZED (
    SELECT DISTINCT pharmacy_id FROM events WHERE pharmacy_id IS NOT NULL
), pharmacies AS MATERIALIZED (
    SELECT p.pharmacy_id,p.subject_id,p.hadm_id,p.poe_id,p.route,
           CASE WHEN nullif(trim(p.route),'') IS NULL THEN 'missing'
                WHEN upper(trim(p.route)) IN ('IV','INTRAVENOUS','IV DRIP','IV BOLUS','IVP') THEN 'explicit_iv'
                WHEN upper(trim(p.route)) IN ('PO','ORAL','NG','OG','PO/NG','G TUBE','J TUBE','PEG','ENTERAL') THEN 'explicit_enteral'
                ELSE 'other_unmapped' END AS route_class
    FROM mimiciv_hosp.pharmacy p
    WHERE EXISTS (SELECT 1 FROM pharmacy_keys k
                  WHERE p.pharmacy_id::bigint = k.pharmacy_id::bigint)
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
    SELECT e.*,p.route_class AS pharmacy_route_class,p.poe_id AS pharmacy_poe,
           r.component_rows,r.rx_poe_count,r.rx_poe,r.rx_missing_poe,
           r.rx_iv,r.rx_enteral,r.rx_other,r.rx_missing_route,
           CASE WHEN e.pharmacy_id IS NULL THEN 'missing_head_key'
                WHEN p.pharmacy_id IS NULL THEN 'key_not_found'
                WHEN e.subject_id IS NULL OR e.hadm_id IS NULL THEN 'missing_event_identity'
                WHEN p.subject_id IS DISTINCT FROM e.subject_id OR p.hadm_id IS DISTINCT FROM e.hadm_id
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
           (pharmacy_link='identity_consistent' AND pharmacy_route_class='explicit_iv')
            OR (prescription_link='identity_consistent' AND rx_iv) AS has_iv_order_route,
           (pharmacy_link='identity_consistent' AND pharmacy_route_class='explicit_enteral')
            OR (prescription_link='identity_consistent' AND rx_enteral) AS has_enteral_order_route,
           (pharmacy_link='identity_consistent' AND pharmacy_route_class='other_unmapped')
            OR (prescription_link='identity_consistent' AND rx_other) AS has_other_order_route
    FROM linked l
), assessed AS MATERIALIZED (
    SELECT e.*, CASE WHEN has_iv_order_route AND has_enteral_order_route THEN 'iv_enteral_conflict'
                    WHEN has_other_order_route THEN 'other_unmapped_route_present'
                    WHEN has_iv_order_route THEN 'iv_order_route_only'
                    WHEN has_enteral_order_route THEN 'enteral_order_route_only'
                    ELSE 'no_valid_known_order_route' END AS order_route_pattern
    FROM evidence e
)
SELECT 'dictionary_metadata'::text AS section,'{}'::jsonb AS dimensions,
       (SELECT count(*) FROM medication_walk) AS records,
       jsonb_build_object('non_null_distinct_medication_names',(SELECT count(*) FROM medication_walk),
           'selected_distinct_medication_names',(SELECT count(*) FROM names),
           'blank_distinct_medication_names',(SELECT count(*) FROM medication_walk WHERE nullif(trim(medication),'') IS NULL),
           'null_medication_heads',(SELECT count(*) FROM mimiciv_hosp.emar WHERE medication IS NULL),
           'blank_medication_heads',(SELECT count(*) FROM medication_walk n JOIN mimiciv_hosp.emar e
                 ON e.medication=n.medication WHERE nullif(trim(n.medication),'') IS NULL),
           'full_emar_row_count_not_computed',true,'scope_exhausts_all_iv_potassium_synonyms',false) AS counters
UNION ALL
SELECT 'source_scope_summary',jsonb_build_object('source_scope',
       CASE WHEN grouping(two_exact_names)=1 THEN 'all_lexical_candidates'
            WHEN two_exact_names THEN 'two_exact_names' ELSE 'other_lexical_names' END),count(*),
       jsonb_build_object('emar_heads',count(DISTINCT emar_id),'subjects',count(DISTINCT subject_id),
           'admissions',count(DISTINCT hadm_id),'medication_names',count(DISTINCT medication),
           'pharmacy_keys',count(DISTINCT pharmacy_id),'poe_keys',count(DISTINCT nullif(trim(poe_id),'')),
           'missing_subject',count(*) FILTER (WHERE subject_id IS NULL),
           'missing_admission',count(*) FILTER (WHERE hadm_id IS NULL),
           'missing_pharmacy_key',count(*) FILTER (WHERE pharmacy_id IS NULL),
           'missing_poe_key',count(*) FILTER (WHERE nullif(trim(poe_id),'') IS NULL),
           'missing_charttime',count(*) FILTER (WHERE charttime IS NULL),
           'missing_storetime',count(*) FILTER (WHERE storetime IS NULL),
           'storetime_before_charttime',count(*) FILTER (WHERE storetime<charttime),
           'pharmacy_identity_consistent_heads',count(*) FILTER (WHERE pharmacy_link='identity_consistent'),
           'prescription_identity_consistent_heads',count(*) FILTER (WHERE prescription_link='identity_consistent'),
           'iv_order_route_only_heads',count(*) FILTER (WHERE order_route_pattern='iv_order_route_only'),
           'formal_cohort',false,'detail_rows_examined',false)
FROM assessed GROUP BY GROUPING SETS ((),(two_exact_names)) HAVING count(*)>0
UNION ALL
SELECT 'selected_medication_vocabulary',jsonb_build_object('medication',medication,'name_family',name_family,
       'name_route_hint',name_route_hint,'two_exact_names',two_exact_names),count(*),
       jsonb_build_object('emar_heads',count(DISTINCT emar_id),'subjects',count(DISTINCT subject_id),
           'admissions',count(DISTINCT hadm_id),'chloride_name',bool_or(chloride_name),
           'acetate_name',bool_or(acetate_name),'phosphate_name',bool_or(phosphate_name),
           'other_salt_name',bool_or(other_salt_name),'other_active_name_hint',bool_or(other_active_name_hint))
FROM assessed GROUP BY medication,name_family,name_route_hint,two_exact_names
UNION ALL
SELECT 'name_status_coverage',jsonb_build_object('medication',medication,'name_family',name_family,
       'two_exact_names',two_exact_names,'event_txt',event_txt),count(*),
       jsonb_build_object('emar_heads',count(DISTINCT emar_id),'subjects',count(DISTINCT subject_id),
           'admissions',count(DISTINCT hadm_id),'missing_admission',count(*) FILTER (WHERE hadm_id IS NULL),
           'missing_pharmacy_key',count(*) FILTER (WHERE pharmacy_id IS NULL),
           'missing_poe_key',count(*) FILTER (WHERE nullif(trim(poe_id),'') IS NULL),
           'missing_charttime',count(*) FILTER (WHERE charttime IS NULL),
           'missing_storetime',count(*) FILTER (WHERE storetime IS NULL),
           'storetime_before_charttime',count(*) FILTER (WHERE storetime<charttime))
FROM assessed GROUP BY medication,name_family,two_exact_names,event_txt
UNION ALL
SELECT 'head_order_link_route',jsonb_build_object('two_exact_names',two_exact_names,
       'name_family',name_family,'event_txt',event_txt,'pharmacy_link',pharmacy_link,
       'prescription_link',prescription_link,'order_route_pattern',order_route_pattern),count(*),
       jsonb_build_object('emar_heads',count(DISTINCT emar_id),'subjects',count(DISTINCT subject_id),
           'admissions',count(DISTINCT hadm_id),
           'event_pharmacy_poe_disagreement',count(*) FILTER (WHERE nullif(trim(poe_id),'') IS NOT NULL
               AND nullif(trim(pharmacy_poe),'') IS NOT NULL AND trim(poe_id)<>trim(pharmacy_poe)),
           'event_prescription_poe_disagreement',count(*) FILTER (WHERE nullif(trim(poe_id),'') IS NOT NULL
               AND rx_poe_count=1 AND rx_poe IS NOT NULL AND trim(poe_id)<>rx_poe),
           'matched_prescription_poe_ambiguous_or_missing',count(*) FILTER (WHERE rx_poe_count<>1 OR rx_missing_poe>0),
           'heads_with_multiple_prescription_components',count(*) FILTER (WHERE component_rows>1),
           'route_is_administration_proof',false)
FROM assessed GROUP BY two_exact_names,name_family,event_txt,pharmacy_link,prescription_link,order_route_pattern
UNION ALL
SELECT 'linked_order_route_vocabulary',jsonb_build_object('source','pharmacy','route_raw',route,
       'route_class',route_class),count(*),jsonb_build_object('pharmacy_keys',count(DISTINCT pharmacy_id))
FROM pharmacies GROUP BY route,route_class
UNION ALL
SELECT 'linked_order_route_vocabulary',jsonb_build_object('source','prescription_component','route_raw',route,
       'route_class',route_class,'drug_type',drug_type),count(*),jsonb_build_object('pharmacy_keys',count(DISTINCT pharmacy_id))
FROM prescription_rows GROUP BY route,route_class,drug_type
ORDER BY section,records DESC,dimensions;
