-- Candidate-source audit, NOT a potassium cohort or actual-dose/action mapping.
-- Same exact-name 1% SYSTEM page sample/seed as 190; retain ALL statuses.
-- Complete details join by emar_id, including NULL-pharmacy parent rows.
-- Route evidence is collected independently of dose rows. Prescription
-- components NEVER multiply the dose table. mL/TAB/PKT are product units,
-- never administration routes. Numeric sum is only a duplication diagnostic.
-- A common dose repeated across products is not summed into a factual dose.
-- Identity failures remain visible and cannot provide eligible route evidence.
WITH sampled AS MATERIALIZED (
    SELECT emar_id, emar_seq, subject_id, hadm_id, pharmacy_id, medication,
           event_txt, charttime, storetime
    FROM mimiciv_hosp.emar TABLESAMPLE SYSTEM (1) REPEATABLE (20261011)
), events AS MATERIALIZED (
    SELECT * FROM sampled
    WHERE trim(medication) IN (
        'Potassium Chloride',
        'Potassium Chloride Replacement (Critical Care and Oncology)'
    )
), details AS MATERIALIZED (
    SELECT e.emar_id AS event_key, e.emar_seq AS event_sequence,
           e.subject_id AS event_subject, e.hadm_id AS event_hadm,
           e.pharmacy_id AS event_pharmacy, e.event_txt, d.*,
           d.subject_id IS NOT DISTINCT FROM e.subject_id
             AND e.subject_id IS NOT NULL
             AND d.emar_seq IS NOT DISTINCT FROM e.emar_seq
             AND e.emar_seq IS NOT NULL AS detail_identity_ok,
           CASE WHEN trim(d.dose_given) ~ '^[0-9]+([.][0-9]+)?$'
                THEN trim(d.dose_given)::numeric END AS dose_numeric
    FROM events e JOIN mimiciv_hosp.emar_detail d ON d.emar_id = e.emar_id
), pharmacy_keys AS MATERIALIZED (
    SELECT pharmacy_id FROM events WHERE pharmacy_id IS NOT NULL
    UNION SELECT pharmacy_id FROM details WHERE pharmacy_id IS NOT NULL
), pharmacies AS MATERIALIZED (
    SELECT p.* FROM pharmacy_keys k
    JOIN LATERAL (
        SELECT pharmacy_id, subject_id, hadm_id, route
        FROM mimiciv_hosp.pharmacy p WHERE p.pharmacy_id = k.pharmacy_id OFFSET 0
    ) p ON true
), prescriptions AS MATERIALIZED (
    SELECT p.* FROM pharmacy_keys k
    JOIN LATERAL (
        SELECT pharmacy_id, subject_id, hadm_id, route, drug_type,
               prod_strength, dose_unit_rx
        FROM mimiciv_hosp.prescriptions p WHERE p.pharmacy_id = k.pharmacy_id OFFSET 0
    ) p ON true
), route_evidence AS MATERIALIZED (
    SELECT e.emar_id AS event_key, 'head_pharmacy'::text AS source,
           p.route, NULL::text AS drug_type, NULL::text AS prod_strength,
           NULL::text AS dose_unit_rx,
           e.subject_id IS NOT NULL AND e.hadm_id IS NOT NULL
             AND p.subject_id IS NOT DISTINCT FROM e.subject_id
             AND p.hadm_id IS NOT DISTINCT FROM e.hadm_id AS identity_ok
    FROM events e JOIN pharmacies p USING (pharmacy_id)
    UNION ALL
    SELECT e.emar_id, 'head_prescription', p.route, p.drug_type, p.prod_strength,
           p.dose_unit_rx,
           e.subject_id IS NOT NULL AND e.hadm_id IS NOT NULL
             AND p.subject_id IS NOT DISTINCT FROM e.subject_id
             AND p.hadm_id IS NOT DISTINCT FROM e.hadm_id
    FROM events e JOIN prescriptions p USING (pharmacy_id)
    UNION ALL
    SELECT d.event_key,
           CASE WHEN d.parent_field_ordinal IS NULL THEN 'parent_route' ELSE 'product_route' END,
           d.route, NULL, NULL, NULL, d.detail_identity_ok
    FROM details d
    UNION ALL
    SELECT d.event_key,
           CASE WHEN d.parent_field_ordinal IS NULL THEN 'parent_pharmacy' ELSE 'product_pharmacy' END,
           p.route, NULL, NULL, NULL,
           d.detail_identity_ok AND d.event_hadm IS NOT NULL
             AND p.subject_id IS NOT DISTINCT FROM d.event_subject
             AND p.hadm_id IS NOT DISTINCT FROM d.event_hadm
    FROM details d JOIN pharmacies p USING (pharmacy_id)
    UNION ALL
    SELECT d.event_key,
           CASE WHEN d.parent_field_ordinal IS NULL THEN 'parent_prescription' ELSE 'product_prescription' END,
           p.route, p.drug_type, p.prod_strength, p.dose_unit_rx,
           d.detail_identity_ok AND d.event_hadm IS NOT NULL
             AND p.subject_id IS NOT DISTINCT FROM d.event_subject
             AND p.hadm_id IS NOT DISTINCT FROM d.event_hadm
    FROM details d JOIN prescriptions p USING (pharmacy_id)
), classified_routes AS MATERIALIZED (
    SELECT *, CASE
        WHEN nullif(trim(route), '') IS NULL THEN 'missing'
        WHEN upper(trim(route)) IN ('IV', 'INTRAVENOUS', 'IV DRIP', 'IV BOLUS', 'IVP') THEN 'explicit_iv'
        WHEN upper(trim(route)) IN ('PO', 'ORAL', 'NG', 'OG', 'PO/NG', 'G TUBE', 'J TUBE', 'PEG', 'ENTERAL') THEN 'explicit_enteral'
        ELSE 'other_unmapped' END AS route_class
    FROM route_evidence
), route_shapes AS MATERIALIZED (
    SELECT event_key,
           count(*) FILTER (WHERE NOT identity_ok) AS identity_bad_evidence_rows,
           count(*) FILTER (WHERE identity_ok AND route_class = 'explicit_iv') AS iv_evidence_rows,
           count(*) FILTER (WHERE identity_ok AND route_class = 'explicit_enteral') AS enteral_evidence_rows,
           count(*) FILTER (WHERE identity_ok AND route_class = 'other_unmapped') AS other_evidence_rows,
           count(*) FILTER (WHERE identity_ok AND route_class = 'missing') AS missing_route_evidence_rows
    FROM classified_routes GROUP BY event_key
), detail_shapes AS MATERIALIZED (
    SELECT event_key, count(*) AS detail_rows,
           count(*) FILTER (WHERE parent_field_ordinal IS NULL) AS parent_rows,
           count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL) AS product_rows,
           count(*) FILTER (WHERE NOT detail_identity_ok) AS detail_identity_bad_rows,
           count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL AND pharmacy_id IS NULL) AS product_missing_pharmacy_rows,
           count(*) FILTER (WHERE pharmacy_id IS NOT NULL AND event_pharmacy IS NOT NULL AND pharmacy_id <> event_pharmacy) AS known_other_pharmacy_rows,
           count(DISTINCT nullif(trim(product_description), '')) FILTER (WHERE parent_field_ordinal IS NOT NULL) AS distinct_product_descriptions,
           count(DISTINCT upper(nullif(trim(product_unit), ''))) FILTER (WHERE parent_field_ordinal IS NOT NULL) AS distinct_product_units,
           count(*) FILTER (WHERE parent_field_ordinal IS NULL AND nullif(trim(dose_given), '') IS NOT NULL) AS parent_dose_present_rows,
           count(*) FILTER (WHERE parent_field_ordinal IS NULL AND dose_numeric IS NOT NULL) AS parent_numeric_rows,
           count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL AND dose_numeric IS NOT NULL) AS product_numeric_rows,
           count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL AND dose_numeric IS NOT NULL AND upper(trim(dose_given_unit)) = 'MEQ') AS product_numeric_meq_rows,
           count(DISTINCT dose_numeric) FILTER (WHERE parent_field_ordinal IS NOT NULL AND upper(trim(dose_given_unit)) = 'MEQ') AS distinct_meq_doses,
           min(dose_numeric) FILTER (WHERE parent_field_ordinal IS NOT NULL AND upper(trim(dose_given_unit)) = 'MEQ') AS min_product_meq_dose,
           max(dose_numeric) FILTER (WHERE parent_field_ordinal IS NOT NULL AND upper(trim(dose_given_unit)) = 'MEQ') AS max_product_meq_dose,
           sum(dose_numeric) FILTER (WHERE parent_field_ordinal IS NOT NULL AND upper(trim(dose_given_unit)) = 'MEQ') AS product_meq_sum_diagnostic,
           count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL AND upper(trim(product_unit)) = 'ML') AS ml_product_rows,
           count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL AND upper(trim(product_unit)) IN ('TAB', 'TABLET')) AS tab_product_rows,
           count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL AND upper(trim(product_unit)) IN ('PKT', 'PACKET')) AS pkt_product_rows
    FROM details GROUP BY event_key
), event_shapes AS MATERIALIZED (
    SELECT e.*, d.detail_rows, d.parent_rows, d.product_rows,
           d.detail_identity_bad_rows, d.product_missing_pharmacy_rows,
           d.known_other_pharmacy_rows, d.distinct_product_descriptions,
           d.distinct_product_units, d.parent_dose_present_rows, d.parent_numeric_rows, d.product_numeric_rows,
           d.product_numeric_meq_rows, d.distinct_meq_doses,
           d.min_product_meq_dose, d.max_product_meq_dose,
           d.product_meq_sum_diagnostic, d.ml_product_rows, d.tab_product_rows,
           d.pkt_product_rows, r.identity_bad_evidence_rows,
           CASE WHEN coalesce(r.iv_evidence_rows, 0) > 0
                     AND coalesce(r.enteral_evidence_rows, 0) > 0 THEN 'iv_enteral_conflict'
                WHEN coalesce(r.other_evidence_rows, 0) > 0 THEN 'other_route_evidence_present'
                WHEN coalesce(r.iv_evidence_rows, 0) > 0 THEN 'explicit_iv_only'
                WHEN coalesce(r.enteral_evidence_rows, 0) > 0 THEN 'explicit_enteral_only'
                ELSE 'no_valid_known_route' END AS route_pattern,
           CASE WHEN coalesce(d.product_rows, 0) = 0 THEN 'no_product_rows'
                WHEN d.product_numeric_meq_rows <> d.product_rows THEN 'missing_non_numeric_or_non_meq_product_dose'
                WHEN d.distinct_meq_doses > 1 THEN 'different_product_meq_doses'
                WHEN d.product_rows = 1 THEN 'single_product_meq_dose'
                ELSE 'repeated_same_product_meq_dose_do_not_sum' END AS product_dose_pattern
    FROM events e LEFT JOIN detail_shapes d ON d.event_key = e.emar_id
    LEFT JOIN route_shapes r ON r.event_key = e.emar_id
), assessed AS MATERIALIZED (
    SELECT *, CASE
        WHEN product_numeric_meq_rows = product_rows AND distinct_meq_doses = 1
             AND min_product_meq_dose IN (0, 10, 20, 40)
        THEN min_product_meq_dose::text ELSE 'other_or_unresolved' END AS common_product_meq_bucket,
        -- A strict source candidate only, still NOT a factual action. One product
        -- avoids resolving multi-product duplication by an undocumented rule.
        coalesce(event_txt = 'Administered' AND subject_id IS NOT NULL
           AND hadm_id IS NOT NULL AND charttime IS NOT NULL
           AND parent_rows = 1 AND product_rows = 1
           AND detail_identity_bad_rows = 0
           AND coalesce(identity_bad_evidence_rows, 0) = 0
           AND route_pattern = 'explicit_iv_only'
           AND parent_dose_present_rows = 0 AND product_numeric_meq_rows = 1
           AND tab_product_rows = 0 AND pkt_product_rows = 0
           AND min_product_meq_dose IN (10, 20, 40), false) AS single_product_source_candidate
    FROM event_shapes
), profiles AS (
    SELECT 'sample_summary'::text AS profile_section,
           jsonb_build_object('selection', 'same exact-name SYSTEM 1% sample as 190; all statuses') AS dimensions,
           count(*) AS source_rows, count(DISTINCT emar_id) AS emar_events,
           jsonb_build_object(
               'sampled_emar_rows', (SELECT count(*) FROM sampled),
               'selected_emar_rows', count(*),
               'complete_detail_rows', (SELECT count(*) FROM details),
               'candidate_pharmacy_keys', (SELECT count(*) FROM pharmacy_keys),
               'found_pharmacy_rows', (SELECT count(*) FROM pharmacies),
               'found_prescription_component_rows', (SELECT count(*) FROM prescriptions),
               'events_without_details', count(*) FILTER (WHERE detail_rows IS NULL),
               'events_with_detail_identity_failure', count(*) FILTER (WHERE detail_identity_bad_rows > 0),
               'events_with_route_identity_failure', count(*) FILTER (WHERE identity_bad_evidence_rows > 0),
               'events_with_iv_enteral_conflict', count(*) FILTER (WHERE route_pattern = 'iv_enteral_conflict'),
               'single_product_source_candidates', count(*) FILTER (WHERE single_product_source_candidate)
           ) AS counters
    FROM assessed
    UNION ALL
    SELECT 'route_evidence_vocabulary',
           jsonb_build_object('source', source, 'route_raw', route,
                              'route_class', route_class, 'identity_ok', identity_ok,
                              'drug_type', drug_type, 'prod_strength', prod_strength,
                              'dose_unit_rx', dose_unit_rx),
           count(*), count(DISTINCT event_key), '{}'::jsonb
    FROM classified_routes
    GROUP BY source, route, route_class, identity_ok, drug_type, prod_strength, dose_unit_rx
    UNION ALL
    SELECT 'detail_dose_vocabulary',
           jsonb_build_object('event_txt', event_txt,
               'role', CASE WHEN parent_field_ordinal IS NULL THEN 'parent' ELSE 'product' END,
               'dose_given_unit', dose_given_unit, 'product_unit', product_unit,
               'product_description', product_description, 'identity_ok', detail_identity_ok,
               'dose_bucket', CASE WHEN dose_numeric IN (0, 10, 20, 40) THEN dose_numeric::text
                                   WHEN dose_numeric IS NOT NULL THEN 'other_numeric'
                                   WHEN nullif(trim(dose_given), '') IS NULL THEN 'missing'
                                   ELSE 'non_numeric' END),
           count(*), count(DISTINCT event_key),
           jsonb_build_object('numeric_rows', count(*) FILTER (WHERE dose_numeric IS NOT NULL))
    FROM details
    GROUP BY event_txt, parent_field_ordinal IS NULL, dose_given_unit, product_unit,
             product_description, detail_identity_ok,
             CASE WHEN dose_numeric IN (0, 10, 20, 40) THEN dose_numeric::text
                  WHEN dose_numeric IS NOT NULL THEN 'other_numeric'
                  WHEN nullif(trim(dose_given), '') IS NULL THEN 'missing' ELSE 'non_numeric' END
    UNION ALL
    SELECT 'event_route_dose',
           jsonb_build_object('event_txt', event_txt, 'route_pattern', route_pattern,
               'product_dose_pattern', product_dose_pattern,
               'common_product_meq_bucket', common_product_meq_bucket,
               'single_product_source_candidate', single_product_source_candidate),
           count(*), count(DISTINCT emar_id),
           jsonb_build_object(
               'product_rows', coalesce(sum(product_rows), 0),
               'events_with_multiple_products', count(*) FILTER (WHERE product_rows > 1),
               'events_with_multiple_product_descriptions', count(*) FILTER (WHERE distinct_product_descriptions > 1),
               'events_with_multiple_product_units', count(*) FILTER (WHERE distinct_product_units > 1),
               'events_with_parent_numeric_dose', count(*) FILTER (WHERE parent_numeric_rows > 0),
               'events_with_parent_dose_present', count(*) FILTER (WHERE parent_dose_present_rows > 0),
               'events_with_iv_route_enteral_product_form_conflict', count(*) FILTER (
                   WHERE route_pattern = 'explicit_iv_only' AND (tab_product_rows > 0 OR pkt_product_rows > 0)),
               'events_with_product_missing_pharmacy', count(*) FILTER (WHERE product_missing_pharmacy_rows > 0),
               'events_with_known_other_pharmacy', count(*) FILTER (WHERE known_other_pharmacy_rows > 0),
               'events_with_detail_identity_failure', count(*) FILTER (WHERE detail_identity_bad_rows > 0),
               'events_with_route_identity_failure', count(*) FILTER (WHERE identity_bad_evidence_rows > 0),
               'events_with_ml_products', count(*) FILTER (WHERE ml_product_rows > 0),
               'events_with_tab_products', count(*) FILTER (WHERE tab_product_rows > 0),
               'events_with_pkt_products', count(*) FILTER (WHERE pkt_product_rows > 0),
               'events_missing_hadm', count(*) FILTER (WHERE hadm_id IS NULL),
               'events_missing_head_pharmacy', count(*) FILTER (WHERE pharmacy_id IS NULL),
               'events_missing_charttime', count(*) FILTER (WHERE charttime IS NULL),
               'events_store_before_charttime', count(*) FILTER (WHERE storetime < charttime),
               'product_meq_sum_diagnostic_min', min(product_meq_sum_diagnostic),
               'product_meq_sum_diagnostic_max', max(product_meq_sum_diagnostic),
               'product_meq_sum_is_actual_dose', false
           )
    FROM assessed
    GROUP BY event_txt, route_pattern, product_dose_pattern,
             common_product_meq_bucket, single_product_source_candidate
)
SELECT profile_section, dimensions, source_rows, emar_events,
       counters || jsonb_build_object('system_sample_percent', 1.0,
           'sample_seed', 20261011, 'formal_action_mapping', false,
           'route_whitelist_status', 'diagnostic only; unmapped raw routes retained') AS counters
FROM profiles
ORDER BY profile_section, source_rows DESC, dimensions;
