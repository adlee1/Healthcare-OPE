-- Physical alternative to 304; the scientific source and action rules are unchanged.
-- Discover candidate heads before parsing doses or expanding all linked orders.
-- A discovery hit on ANY detail row or either order table is sufficient; identity,
-- product ordinal, status, route and dose never filter discovery.
-- Then read ALL details and ALL linked order rows for each selected head and run
-- the original 304 classification, including multiplicity-sensitive diagnostics.
-- The detail table has no emar_id index: discovery and complete-context retrieval
-- use ordinary joins, permitting two sequential passes instead of per-head scans.
-- Name dictionaries are enumerated in this query, not imported from an old cohort.
WITH RECURSIVE
head_name_walk(raw_name) AS (
    (SELECT medication FROM mimiciv_hosp.emar WHERE medication IS NOT NULL
     ORDER BY medication LIMIT 1)
    UNION ALL
    SELECT n.raw_name FROM head_name_walk previous CROSS JOIN LATERAL (
        SELECT medication AS raw_name FROM mimiciv_hosp.emar
        WHERE medication > previous.raw_name ORDER BY medication LIMIT 1
    ) n
), detail_name_walk(raw_name) AS (
    (SELECT product_description FROM mimiciv_hosp.emar_detail
     WHERE product_description IS NOT NULL ORDER BY product_description LIMIT 1)
    UNION ALL
    SELECT n.raw_name FROM detail_name_walk previous CROSS JOIN LATERAL (
        SELECT product_description AS raw_name FROM mimiciv_hosp.emar_detail
        WHERE product_description > previous.raw_name ORDER BY product_description LIMIT 1
    ) n
), pharmacy_name_walk(raw_name) AS (
    (SELECT medication FROM mimiciv_hosp.pharmacy WHERE medication IS NOT NULL
     ORDER BY medication LIMIT 1)
    UNION ALL
    SELECT n.raw_name FROM pharmacy_name_walk previous CROSS JOIN LATERAL (
        SELECT medication AS raw_name FROM mimiciv_hosp.pharmacy
        WHERE medication > previous.raw_name ORDER BY medication LIMIT 1
    ) n
), prescription_names AS MATERIALIZED (
    -- No leading drug-name index: evaluate the regex on distinct names, then
    -- hash-join the small matching dictionary against prescriptions below.
    SELECT DISTINCT drug AS raw_name FROM mimiciv_hosp.prescriptions WHERE drug IS NOT NULL
), matching_head_names AS MATERIALIZED (
    SELECT raw_name FROM head_name_walk
    WHERE raw_name ~* 'potassium|(^|[^[:alnum:]])k[ -]?phos([^[:alnum:]]|$)|(^|[^[:alnum:]])kcl([^[:alnum:]]|$)'
), matching_detail_names AS MATERIALIZED (
    SELECT raw_name FROM detail_name_walk
    WHERE raw_name ~* 'potassium|(^|[^[:alnum:]])k[ -]?phos([^[:alnum:]]|$)|(^|[^[:alnum:]])kcl([^[:alnum:]]|$)'
), matching_pharmacy_names AS MATERIALIZED (
    SELECT raw_name FROM pharmacy_name_walk
    WHERE raw_name ~* 'potassium|(^|[^[:alnum:]])k[ -]?phos([^[:alnum:]]|$)|(^|[^[:alnum:]])kcl([^[:alnum:]]|$)'
), matching_prescription_names AS MATERIALIZED (
    SELECT raw_name FROM prescription_names
    WHERE raw_name ~* 'potassium|(^|[^[:alnum:]])k[ -]?phos([^[:alnum:]]|$)|(^|[^[:alnum:]])kcl([^[:alnum:]]|$)'
), named_order_keys AS MATERIALIZED (
    -- This set is for discovery only; complete order context is re-read below.
    -- NULL order identities and components with non-K names remain available
    -- in that complete context. A NULL pharmacy_id cannot join in 304 either.
    SELECT p.pharmacy_id
    FROM matching_pharmacy_names n CROSS JOIN LATERAL (
        SELECT pharmacy_id FROM mimiciv_hosp.pharmacy p
        WHERE p.medication = n.raw_name AND p.pharmacy_id IS NOT NULL OFFSET 0
    ) p
    UNION
    SELECT p.pharmacy_id
    FROM mimiciv_hosp.prescriptions p JOIN matching_prescription_names n ON p.drug = n.raw_name
    WHERE p.pharmacy_id IS NOT NULL
), all_bucket_heads AS MATERIALIZED (
    SELECT emar_id, emar_seq, subject_id, hadm_id, pharmacy_id,
           charttime, storetime, medication, event_txt
    FROM mimiciv_hosp.emar
    WHERE mod(subject_id, __BUCKET_COUNT__) = __BUCKET_ID__
       OR (subject_id IS NULL AND __BUCKET_ID__ = 0)
), detail_discovered_heads AS MATERIALIZED (
    -- First complete detail pass. Do not require detail.subject_id, sequence,
    -- parent ordinal, or pharmacy to agree with the associated head.
    SELECT DISTINCT d.emar_id
    FROM mimiciv_hosp.emar_detail d JOIN all_bucket_heads h ON d.emar_id = h.emar_id
    LEFT JOIN matching_detail_names n ON d.product_description = n.raw_name
    LEFT JOIN named_order_keys o ON d.pharmacy_id = o.pharmacy_id
    WHERE n.raw_name IS NOT NULL OR o.pharmacy_id IS NOT NULL
       OR d.product_description_other ~* 'potassium|(^|[^[:alnum:]])k[ -]?phos([^[:alnum:]]|$)|(^|[^[:alnum:]])kcl([^[:alnum:]]|$)'
), candidate_head_ids AS MATERIALIZED (
    SELECT h.emar_id
    FROM all_bucket_heads h
    LEFT JOIN matching_head_names n ON h.medication = n.raw_name
    LEFT JOIN named_order_keys o ON h.pharmacy_id = o.pharmacy_id
    WHERE n.raw_name IS NOT NULL OR o.pharmacy_id IS NOT NULL
    UNION
    SELECT emar_id FROM detail_discovered_heads
), bucket_heads AS MATERIALIZED (
    SELECT h.*
    FROM all_bucket_heads h JOIN candidate_head_ids c ON c.emar_id = h.emar_id
), details AS MATERIALIZED (
    -- One ordinary join permits ONE scan of detail when emar_id lacks an index.
    SELECT h.emar_id AS head_id, h.subject_id AS head_subject,
           h.hadm_id AS head_hadm, d.pharmacy_id, d.parent_field_ordinal,
           d.product_description, d.product_description_other,
           d.route, d.dose_given_unit, d.product_unit,
           CASE WHEN trim(d.dose_given) ~ '^[0-9]+([.][0-9]+)?$'
                THEN trim(d.dose_given)::numeric END AS dose_numeric,
           coalesce(nullif(trim(d.product_description), ''),
                    nullif(trim(d.product_description_other), '')) AS component_name,
           d.subject_id IS NOT DISTINCT FROM h.subject_id
             AND d.emar_seq IS NOT DISTINCT FROM h.emar_seq
             AND h.subject_id IS NOT NULL AND h.emar_seq IS NOT NULL AS identity_ok,
           CASE WHEN upper(trim(d.complete_dose_not_given)) IN ('Y', 'YES') THEN 'yes'
                WHEN upper(trim(d.complete_dose_not_given)) IN ('N', 'NO') THEN 'no'
                WHEN nullif(trim(d.complete_dose_not_given), '') IS NULL THEN 'missing'
                ELSE 'unrecognized' END AS incomplete_flag,
           CASE WHEN upper(trim(d.will_remainder_of_dose_be_given)) IN ('Y', 'YES') THEN 'yes'
                WHEN upper(trim(d.will_remainder_of_dose_be_given)) IN ('N', 'NO') THEN 'no'
                WHEN nullif(trim(d.will_remainder_of_dose_be_given), '') IS NULL THEN 'missing'
                ELSE 'unrecognized' END AS remainder_flag
    FROM bucket_heads h JOIN mimiciv_hosp.emar_detail d ON d.emar_id = h.emar_id
), pharmacy_keys AS MATERIALIZED (
    SELECT emar_id AS head_id, subject_id AS head_subject, hadm_id AS head_hadm, pharmacy_id
    FROM bucket_heads WHERE pharmacy_id IS NOT NULL
    UNION
    SELECT head_id, head_subject, head_hadm, pharmacy_id
    FROM details WHERE pharmacy_id IS NOT NULL
), unique_pharmacy_keys AS MATERIALIZED (
    SELECT DISTINCT pharmacy_id FROM pharmacy_keys
), order_rows AS MATERIALIZED (
    SELECT p.pharmacy_id, p.subject_id, p.hadm_id, p.route,
           'pharmacy'::text AS source_kind, p.medication AS source_name
    FROM unique_pharmacy_keys k CROSS JOIN LATERAL (
        SELECT pharmacy_id, subject_id, hadm_id, route, medication
        FROM mimiciv_hosp.pharmacy p WHERE p.pharmacy_id = k.pharmacy_id OFFSET 0
    ) p
    UNION ALL
    SELECT p.pharmacy_id, p.subject_id, p.hadm_id, p.route,
           'prescription'::text, p.drug
    FROM unique_pharmacy_keys k CROSS JOIN LATERAL (
        SELECT pharmacy_id, subject_id, hadm_id, route, drug
        FROM mimiciv_hosp.prescriptions p WHERE p.pharmacy_id = k.pharmacy_id OFFSET 0
    ) p
), linked_orders AS MATERIALIZED (
    SELECT k.head_id, p.source_kind, p.source_name, p.route,
           p.subject_id AS order_subject_id, p.hadm_id AS order_hadm_id,
           p.subject_id IS NOT DISTINCT FROM k.head_subject
             AND p.hadm_id IS NOT DISTINCT FROM k.head_hadm
             AND k.head_subject IS NOT NULL AND k.head_hadm IS NOT NULL AS identity_ok
    FROM pharmacy_keys k JOIN order_rows p USING (pharmacy_id)
), source_order_keys AS MATERIALIZED (
    -- Aggregate separately: repeated pharmacy/prescription evidence is one
    -- logical (subject, admission) key, never extra medication components.
    -- Preserve this key for a blocker, not an identity/dose repair.
    SELECT head_id,
           CASE WHEN count(*) FILTER (WHERE order_subject_id IS NOT NULL AND order_hadm_id IS NOT NULL) = count(*)
                  AND count(DISTINCT (order_subject_id, order_hadm_id)) = 1
                THEN min(order_subject_id) END AS source_order_subject_id,
           CASE WHEN count(*) FILTER (WHERE order_subject_id IS NOT NULL AND order_hadm_id IS NOT NULL) = count(*)
                  AND count(DISTINCT (order_subject_id, order_hadm_id)) = 1
                THEN min(order_hadm_id) END AS source_order_hadm_id
    FROM linked_orders GROUP BY head_id
), names AS MATERIALIZED (
    SELECT emar_id AS head_id, 'head'::text AS source_kind, medication AS source_name
    FROM bucket_heads
    UNION ALL
    SELECT head_id, 'product_description', product_description FROM details
    UNION ALL
    SELECT head_id, 'product_description_other', product_description_other FROM details
    UNION ALL
    SELECT head_id, source_kind, source_name FROM linked_orders
), matched_names AS MATERIALIZED (
    SELECT *,
           source_name ~* 'potassium[[:space:]-]+(chloride|chl|acetate|phosph)|(^|[^[:alnum:]])k[ -]?phos([^[:alnum:]]|$)|(^|[^[:alnum:]])kcl([^[:alnum:]]|$)'
             AS repletion_hint,
           source_name ~* 'losartan|penicillin|amoxicillin|clavulan|diclofenac|clorazepate'
             AS other_active_drug_hint
    FROM names
    WHERE source_name ~* 'potassium|(^|[^[:alnum:]])k[ -]?phos([^[:alnum:]]|$)|(^|[^[:alnum:]])kcl([^[:alnum:]]|$)'
), scope AS MATERIALIZED (
    SELECT head_id, count(*) AS matching_name_rows,
           bool_or(source_kind = 'head') AS head_name_match,
           bool_or(source_kind = 'pharmacy') AS pharmacy_name_match,
           bool_or(source_kind = 'prescription') AS prescription_name_match,
           bool_or(source_kind = 'product_description') AS product_description_match,
           bool_or(source_kind = 'product_description_other') AS product_description_other_match,
           bool_or(repletion_hint) AS any_repletion_hint,
           bool_and(other_active_drug_hint AND NOT repletion_hint) AS exclusively_other_active_drug
    FROM matched_names GROUP BY head_id
), heads AS MATERIALIZED (
    SELECT h.emar_id, h.emar_seq, h.subject_id, h.hadm_id, h.pharmacy_id,
           h.charttime, h.storetime, h.event_txt AS raw_administration_status, s.*,
           o.source_order_subject_id, o.source_order_hadm_id,
           CASE
             WHEN h.medication ~* 'losartan|penicillin|amoxicillin|clavulan|diclofenac|clorazepate'
               THEN 'other_active_drug_potassium_salt'
             WHEN h.medication ~* 'potassium[[:space:]-]+(chloride|chl)([^[:alpha:]]|$)|(^|[^[:alnum:]])kcl([^[:alnum:]]|$)'
               THEN 'potassium_chloride'
             WHEN h.medication ~* 'potassium[[:space:]-]+acetate' THEN 'potassium_acetate'
             WHEN h.medication ~* 'potassium[[:space:]-]+phosph|(^|[^[:alnum:]])k[ -]?phos([^[:alnum:]]|$)'
               THEN 'potassium_phosphate'
             WHEN s.any_repletion_hint THEN 'potassium_repletion_nonhead_evidence'
             WHEN s.exclusively_other_active_drug THEN 'other_active_drug_potassium_salt'
             ELSE 'unresolved_potassium_evidence' END AS medication_family,
           CASE lower(trim(h.event_txt))
             WHEN 'administered' THEN 'administered'
             WHEN 'partial administered' THEN 'partial_administered'
             WHEN 'started' THEN 'started'
             WHEN 'stopped' THEN 'stopped'
             WHEN 'not given' THEN 'not_given'
             ELSE CASE WHEN nullif(trim(h.event_txt), '') IS NULL
                       THEN 'missing' ELSE 'other' END END AS administration_status
    FROM bucket_heads h JOIN scope s ON s.head_id = h.emar_id
    LEFT JOIN source_order_keys o ON o.head_id = h.emar_id
), detail_summary AS MATERIALIZED (
    SELECT d.head_id, count(*) AS detail_rows,
           count(*) FILTER (WHERE d.parent_field_ordinal IS NULL) AS parent_rows,
           count(*) FILTER (WHERE d.parent_field_ordinal IS NOT NULL) AS product_rows,
           count(*) FILTER (WHERE NOT d.identity_ok) AS detail_identity_bad_rows,
           count(DISTINCT trim(d.parent_field_ordinal))
             FILTER (WHERE d.parent_field_ordinal IS NOT NULL) AS distinct_product_ordinals,
           count(*) FILTER (WHERE d.parent_field_ordinal IS NOT NULL
             AND NOT (trim(d.parent_field_ordinal) ~ '^[0-9]+([.][0-9]+)?$')) AS unparsed_product_ordinals,
           count(*) FILTER (WHERE d.parent_field_ordinal IS NOT NULL
             AND d.dose_numeric > 0 AND upper(trim(d.dose_given_unit)) = 'MEQ') AS positive_meq_product_rows,
           count(*) FILTER (WHERE d.parent_field_ordinal IS NOT NULL
             AND upper(trim(d.dose_given_unit)) IN ('MMOL', 'MILLIMOLE', 'MILLIMOLES')) AS mmol_product_rows,
           count(*) FILTER (WHERE d.parent_field_ordinal IS NOT NULL AND d.component_name IS NULL)
             AS missing_product_name_rows,
           count(*) FILTER (WHERE d.parent_field_ordinal IS NOT NULL AND d.dose_numeric > 0
             AND upper(trim(d.dose_given_unit)) = 'MEQ' AND d.component_name IS NOT NULL
             AND NOT (d.component_name ~* 'potassium[[:space:]-]+(chloride|chl|acetate|phosph)|(^|[^[:alnum:]])k[ -]?phos([^[:alnum:]]|$)|(^|[^[:alnum:]])kcl([^[:alnum:]]|$)'))
             AS non_potassium_named_meq_product_rows,
           sum(d.dose_numeric) FILTER (WHERE d.parent_field_ordinal IS NOT NULL
             AND upper(trim(d.dose_given_unit)) = 'MEQ') AS product_sum_meq,
           count(*) FILTER (WHERE d.parent_field_ordinal IS NOT NULL
             AND upper(trim(d.product_unit)) IN ('TAB', 'TABLET', 'PKT', 'PACKET')) AS enteral_product_rows,
           count(*) FILTER (WHERE d.parent_field_ordinal IS NOT NULL
             AND (d.product_description ~* 'losartan|penicillin|amoxicillin|clavulan|diclofenac|clorazepate'
               OR d.product_description_other ~* 'losartan|penicillin|amoxicillin|clavulan|diclofenac|clorazepate'))
             AS other_active_drug_product_rows,
           count(*) FILTER (WHERE d.incomplete_flag = 'yes' OR d.remainder_flag = 'yes')
             AS affirmative_incomplete_rows,
           count(*) FILTER (WHERE d.incomplete_flag = 'unrecognized' OR d.remainder_flag = 'unrecognized')
             AS unknown_flag_rows,
           count(*) FILTER (WHERE d.parent_field_ordinal IS NULL
             AND d.incomplete_flag = 'no' AND d.remainder_flag = 'no') AS explicit_complete_parent_rows
    FROM details d JOIN scope s ON s.head_id = d.head_id GROUP BY d.head_id
), route_evidence AS MATERIALIZED (
    SELECT d.head_id, d.route, d.identity_ok
    FROM details d JOIN scope s ON s.head_id = d.head_id
    UNION ALL
    SELECT o.head_id, o.route, o.identity_ok
    FROM linked_orders o JOIN scope s ON s.head_id = o.head_id
), routes AS MATERIALIZED (
    SELECT *, CASE WHEN nullif(trim(route), '') IS NULL THEN 'missing'
             WHEN upper(trim(route)) IN ('IV', 'INTRAVENOUS', 'IV DRIP', 'IV BOLUS', 'IVP') THEN 'iv'
             WHEN upper(trim(route)) IN ('PO', 'ORAL', 'NG', 'OG', 'PO/NG', 'G TUBE', 'J TUBE',
               'PEG', 'ENTERAL', 'IM', 'SC', 'SQ', 'SUBQ', 'SUBCUTANEOUS', 'TOP', 'TOPICAL', 'PR', 'RECTAL')
               THEN 'non_iv' ELSE 'unmapped' END AS route_class
    FROM route_evidence
), route_summary AS MATERIALIZED (
    SELECT head_id, count(*) FILTER (WHERE NOT identity_ok) AS route_identity_bad_rows,
           count(*) FILTER (WHERE identity_ok AND route_class = 'iv') AS iv_rows,
           count(*) FILTER (WHERE identity_ok AND route_class = 'non_iv') AS non_iv_rows,
           count(*) FILTER (WHERE identity_ok AND route_class = 'unmapped') AS unmapped_rows
    FROM routes GROUP BY head_id
), evidence AS MATERIALIZED (
    SELECT h.*,
           coalesce(d.detail_rows, 0) AS detail_rows, coalesce(d.parent_rows, 0) AS parent_rows,
           coalesce(d.product_rows, 0) AS product_rows,
           coalesce(d.detail_identity_bad_rows, 0) AS detail_identity_bad_rows,
           coalesce(r.route_identity_bad_rows, 0) AS route_identity_bad_rows,
           coalesce(d.distinct_product_ordinals, 0) AS distinct_product_ordinals,
           coalesce(d.unparsed_product_ordinals, 0) AS unparsed_product_ordinals,
           coalesce(d.positive_meq_product_rows, 0) AS positive_meq_product_rows,
           coalesce(d.mmol_product_rows, 0) AS mmol_product_rows,
           coalesce(d.missing_product_name_rows, 0) AS missing_product_name_rows,
           coalesce(d.non_potassium_named_meq_product_rows, 0) AS non_potassium_named_meq_product_rows,
           coalesce(d.enteral_product_rows, 0) AS enteral_product_rows,
           coalesce(d.other_active_drug_product_rows, 0) AS other_active_drug_product_rows,
           CASE WHEN d.product_rows > 0 AND d.positive_meq_product_rows = d.product_rows
                  AND d.distinct_product_ordinals = d.product_rows AND d.unparsed_product_ordinals = 0
                  AND d.non_potassium_named_meq_product_rows = 0
                  AND h.medication_family IN ('potassium_chloride', 'potassium_acetate', 'potassium_phosphate')
                THEN d.product_sum_meq END AS recorded_component_dose_meq,
           CASE WHEN coalesce(d.affirmative_incomplete_rows, 0) > 0 THEN 'affirmative_incomplete_or_remainder'
                WHEN coalesce(d.unknown_flag_rows, 0) > 0 THEN 'unrecognized_flags'
                WHEN d.parent_rows > 0 AND d.explicit_complete_parent_rows = d.parent_rows
                  THEN 'explicit_negative_parent_flags' ELSE 'unknown_missing_flags' END AS completeness_class,
           CASE WHEN coalesce(r.iv_rows, 0) > 0 AND coalesce(r.non_iv_rows, 0) > 0 THEN 'iv_non_iv_conflict'
                WHEN coalesce(r.unmapped_rows, 0) > 0 THEN 'unmapped_evidence'
                WHEN coalesce(r.iv_rows, 0) > 0 THEN 'iv_only'
                WHEN coalesce(r.non_iv_rows, 0) > 0 THEN 'non_iv_only'
                ELSE 'missing' END AS route_class
    FROM heads h LEFT JOIN detail_summary d ON d.head_id = h.emar_id
    LEFT JOIN route_summary r ON r.head_id = h.emar_id
), classified AS MATERIALIZED (
    SELECT *,
           CASE WHEN subject_id IS NULL OR hadm_id IS NULL OR emar_id IS NULL OR emar_seq IS NULL
                  THEN 'missing_head_identity'
                WHEN charttime IS NULL OR storetime < charttime THEN 'head_time'
                WHEN medication_family NOT IN ('potassium_chloride', 'potassium_acetate', 'potassium_phosphate')
                  THEN 'nonhead_or_unsupported_medication_family'
                WHEN administration_status <> 'administered' THEN 'not_administered_status'
                WHEN detail_identity_bad_rows > 0 OR route_identity_bad_rows > 0 THEN 'linked_identity_conflict'
                WHEN route_class <> 'iv_only' THEN 'non_iv_unknown_or_conflicting_route'
                WHEN enteral_product_rows > 0 OR other_active_drug_product_rows > 0
                  OR non_potassium_named_meq_product_rows > 0 THEN 'product_identity_or_form_conflict'
                WHEN completeness_class IN ('affirmative_incomplete_or_remainder', 'unrecognized_flags')
                  THEN 'incomplete_or_unrecognized_completion'
                WHEN product_rows = 0 THEN 'no_recorded_product_components'
                WHEN distinct_product_ordinals <> product_rows OR unparsed_product_ordinals > 0
                  THEN 'ambiguous_product_structure'
                WHEN positive_meq_product_rows <> product_rows THEN 'component_dose_not_positive_meq'
                WHEN recorded_component_dose_meq IS NULL THEN 'component_dose_unresolved'
                ELSE NULL END AS dose_exclusion_reason,
           CASE WHEN administration_status = 'not_given' THEN 'documented_not_given'
                WHEN detail_identity_bad_rows = 0 AND route_identity_bad_rows = 0
                  AND route_class = 'non_iv_only' THEN 'explicit_non_iv'
                WHEN detail_identity_bad_rows = 0 AND route_identity_bad_rows = 0
                  AND exclusively_other_active_drug THEN 'known_other_active_drug_salt'
                ELSE NULL END AS exposure_exclusion_reason
    FROM evidence
)
SELECT 'potassium_action_sources_v1'::text AS extraction_version,
       emar_id, emar_seq, subject_id, hadm_id, pharmacy_id,
       source_order_subject_id, source_order_hadm_id,
       charttime AS anchor_time, storetime AS emar_storetime,
       administration_status, raw_administration_status, medication_family, route_class, completeness_class,
       recorded_component_dose_meq,
       dose_exclusion_reason IS NULL AS dose_usable,
       CASE WHEN dose_exclusion_reason IS NULL AND recorded_component_dose_meq IN (10, 20, 40)
            THEN recorded_component_dose_meq::integer END AS positive_action_value,
       coalesce(dose_exclusion_reason IS NULL AND recorded_component_dose_meq IN (10, 20, 40), false)
         AS action_in_paper_set,
       administration_status = 'not_given' AS is_documented_nonadministration,
       exposure_exclusion_reason IS NULL AS possible_relevant_exposure,
       dose_exclusion_reason, exposure_exclusion_reason,
       head_name_match, pharmacy_name_match, prescription_name_match,
       product_description_match, product_description_other_match,
       matching_name_rows, any_repletion_hint, exclusively_other_active_drug,
       detail_rows, parent_rows, product_rows, distinct_product_ordinals, unparsed_product_ordinals,
       detail_identity_bad_rows, route_identity_bad_rows,
       positive_meq_product_rows, mmol_product_rows, missing_product_name_rows,
       non_potassium_named_meq_product_rows, enteral_product_rows, other_active_drug_product_rows
FROM classified
ORDER BY subject_id, hadm_id, charttime, emar_id, emar_seq;
