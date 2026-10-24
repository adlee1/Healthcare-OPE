-- Product-dose semantics diagnostic only, using the unchanged 191 sample,
-- complete-detail joins, route evidence and single-product source candidate.
-- Explicit finite description dictionary is based on vocabulary seen in 191;
-- unknown product descriptions are never emitted or parsed with broad regexes.
-- Listed strength x product_amount is a numeric consistency diagnostic, NOT
-- delivered dose. dose_due and prescription information never become actual dose.
-- No raw patient identifier, time, product code, ordinal or dose text is output.
-- New source columns dose_due/dose_due_unit/product_code were verified in the
-- saved 020_column_inventory.csv before use. All statuses remain separate.
-- will_remainder_of_dose_be_given is also present in that saved inventory.
-- "label_amount" is a legacy short diagnostic name for product-description
-- strength only, NOT an independently verified NDC or external product label.
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
                ELSE 'same_meq_values_multiple_products_inference_open' END AS product_dose_pattern
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
), product_dictionary (description_key, product_concept, listed_meq, listed_amount, listed_unit) AS (
    VALUES
      ('potassium chloride (powder) 20meq packet', 'kcl_powder_20meq_packet', 20::numeric, 1::numeric, 'PKT'),
      ('potassium chloride 10meq er tablet', 'kcl_10meq_er_tablet', 10, 1, 'TAB'),
      ('potassium chloride 10 meq / 100 ml sw', 'kcl_10meq_100ml_water', 10, 100, 'ML'),
      ('potassium chloride 10 meq / 100 ml sw ___', 'kcl_10meq_100ml_water', 10, 100, 'ML'),
      ('potassium chloride 20 meq / 250 ml 0.9% sodium chloride', 'kcl_20meq_250ml_saline', 20, 250, 'ML'),
      ('potassium chloride 20 meq / 250 ml 5% dextrose', 'kcl_20meq_250ml_dextrose', 20, 250, 'ML'),
      ('potassium chloride 20 meq / 50 ml 0.9% sodium chloride ___', 'kcl_20meq_50ml_saline', 20, 50, 'ML'),
      ('potassium chloride 20 meq / 50 ml sterile water', 'kcl_20meq_50ml_water', 20, 50, 'ML'),
      ('potassium chloride 20 meq / 50 ml sterile water ___', 'kcl_20meq_50ml_water', 20, 50, 'ML'),
      ('potassium chloride 20meq/50ml premix', 'kcl_20meq_50ml_premix', 20, 50, 'ML'),
      ('potassium chloride 40 meq / 500 ml 0.9% sodium chloride', 'kcl_40meq_500ml_saline', 40, 500, 'ML'),
      ('potassium chloride 40 meq / 500 ml 0.9% sodium chloride <b>(standard diluent for compound)</b>', 'kcl_40meq_500ml_saline_compound', 40, 500, 'ML'),
      ('potassium chloride 40 meq / 500 ml 5% dextrose', 'kcl_40meq_500ml_dextrose', 40, 500, 'ML'),
      ('potassium chloride 40 meq in 100 ml sterile water', 'kcl_40meq_100ml_water', 40, 100, 'ML'),
      ('potassium chloride 60 meq in 1000 ml 0.9% sodium chloride', 'kcl_60meq_1000ml_saline', 60, 1000, 'ML'),
      ('potassium chloride 60 meq in 1000 ml 5% dextrose', 'kcl_60meq_1000ml_dextrose', 60, 1000, 'ML')
), parsed_details AS MATERIALIZED (
    SELECT d.*, a.route_pattern, a.single_product_source_candidate,
           a.product_dose_pattern, a.common_product_meq_bucket,
           CASE WHEN trim(dose_due) ~ '^[0-9]+([.][0-9]+)?$'
                THEN trim(dose_due)::numeric END AS due_numeric,
           CASE WHEN trim(product_amount_given) ~ '^[0-9]+([.][0-9]+)?$'
                THEN trim(product_amount_given)::numeric END AS amount_numeric,
           CASE WHEN upper(trim(product_unit)) IN ('ML', 'MEQ') THEN upper(trim(product_unit))
                WHEN upper(trim(product_unit)) IN ('TAB', 'TABLET') THEN 'TAB'
                WHEN upper(trim(product_unit)) IN ('PKT', 'PACKET') THEN 'PKT'
                WHEN nullif(trim(product_unit), '') IS NULL THEN 'missing'
                ELSE 'other' END AS amount_unit_class,
           CASE WHEN upper(trim(dose_due_unit)) = 'MEQ' THEN 'MEQ'
                WHEN nullif(trim(dose_due_unit), '') IS NULL THEN 'missing'
                ELSE 'other' END AS due_unit_class,
           CASE WHEN upper(trim(dose_given_unit)) = 'MEQ' THEN 'MEQ'
                WHEN nullif(trim(dose_given_unit), '') IS NULL THEN 'missing'
                ELSE 'other' END AS given_unit_class,
           CASE WHEN upper(trim(complete_dose_not_given)) IN ('Y', 'N', 'YES', 'NO')
                     THEN upper(trim(complete_dose_not_given))
                WHEN nullif(trim(complete_dose_not_given), '') IS NULL THEN 'missing'
                ELSE 'other_nonempty' END AS complete_dose_not_given_class,
           CASE WHEN upper(trim(will_remainder_of_dose_be_given)) IN ('Y', 'N', 'YES', 'NO')
                     THEN upper(trim(will_remainder_of_dose_be_given))
                WHEN nullif(trim(will_remainder_of_dose_be_given), '') IS NULL THEN 'missing'
                ELSE 'other_nonempty' END AS remainder_will_be_given_class,
           CASE WHEN parent_field_ordinal IS NULL THEN 'parent'
                WHEN trim(parent_field_ordinal) ~ '^[0-9]+$' THEN 'integer_product'
                WHEN trim(parent_field_ordinal) ~ '^[0-9]+[.][0-9]+$' THEN 'dotted_product'
                ELSE 'other_product' END AS ordinal_form,
           CASE WHEN trim(parent_field_ordinal) ~ '^[0-9]+([.][0-9]+)?$'
                THEN split_part(trim(parent_field_ordinal), '.', 1) END AS ordinal_prefix,
           coalesce(p.product_concept,
               CASE WHEN nullif(trim(product_description), '') IS NULL
                    THEN 'missing_description' ELSE 'unmapped_description' END) AS product_concept,
           p.listed_meq, p.listed_amount, p.listed_unit
    FROM details d JOIN assessed a ON a.emar_id = d.event_key
    LEFT JOIN product_dictionary p ON p.description_key =
        lower(regexp_replace(trim(d.product_description), '[[:space:]]+', ' ', 'g'))
), compared_details AS MATERIALIZED (
    SELECT *, CASE WHEN amount_numeric IS NOT NULL AND amount_unit_class = listed_unit
                       AND parent_field_ordinal IS NOT NULL
                  THEN amount_numeric * listed_meq / listed_amount END AS label_amount_meq_diagnostic,
           CASE WHEN dose_numeric IS NULL OR due_numeric IS NULL
                          OR given_unit_class <> 'MEQ' OR due_unit_class <> 'MEQ' THEN 'not_comparable'
                WHEN dose_numeric = due_numeric THEN 'equal' ELSE 'different' END AS row_due_vs_given
    FROM parsed_details
), detail_semantics AS MATERIALIZED (
    SELECT *, CASE
        WHEN label_amount_meq_diagnostic IS NULL OR dose_numeric IS NULL
                     OR given_unit_class <> 'MEQ' THEN 'not_comparable'
        WHEN label_amount_meq_diagnostic = dose_numeric THEN 'equal'
        ELSE 'different' END AS given_vs_label_amount,
        CASE WHEN dose_numeric IN (0, 10, 20, 40, 60, 80) THEN dose_numeric::integer::text
             WHEN dose_numeric IS NOT NULL THEN 'other_numeric'
             WHEN nullif(trim(dose_given), '') IS NULL THEN 'missing' ELSE 'non_numeric' END AS given_bucket,
        CASE WHEN due_numeric IN (0, 10, 20, 40, 60, 80) THEN due_numeric::integer::text
             WHEN due_numeric IS NOT NULL THEN 'other_numeric'
             WHEN nullif(trim(dose_due), '') IS NULL THEN 'missing' ELSE 'non_numeric' END AS due_bucket,
        CASE WHEN amount_numeric IN (0, 1, 2, 5, 10, 20, 25, 40, 50, 100, 250, 500, 1000)
                  THEN amount_numeric::integer::text
             WHEN amount_numeric IS NOT NULL THEN 'other_numeric'
             WHEN nullif(trim(product_amount_given), '') IS NULL THEN 'missing'
             ELSE 'non_numeric' END AS amount_bucket
    FROM compared_details
), dose_event_shapes AS MATERIALIZED (
    SELECT event_key,
        count(*) FILTER (WHERE parent_field_ordinal IS NULL AND nullif(trim(dose_due), '') IS NOT NULL) AS parent_due_present_rows,
        count(*) FILTER (WHERE parent_field_ordinal IS NULL AND due_numeric IS NOT NULL AND due_unit_class = 'MEQ') AS parent_due_numeric_meq_rows,
        min(due_numeric) FILTER (WHERE parent_field_ordinal IS NULL AND due_unit_class = 'MEQ') AS parent_due_meq,
        count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL AND nullif(trim(dose_due), '') IS NOT NULL) AS product_due_present_rows,
        count(*) FILTER (WHERE complete_dose_not_given_class IN ('Y', 'YES')) AS incomplete_dose_yes_rows,
        count(*) FILTER (WHERE parent_field_ordinal IS NULL AND complete_dose_not_given_class IN ('Y', 'YES')) AS parent_incomplete_dose_yes_rows,
        count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL AND complete_dose_not_given_class IN ('Y', 'YES')) AS product_incomplete_dose_yes_rows,
        count(*) FILTER (WHERE remainder_will_be_given_class IN ('Y', 'YES')) AS remainder_yes_rows,
        count(*) FILTER (WHERE parent_field_ordinal IS NULL AND remainder_will_be_given_class IN ('Y', 'YES')) AS parent_remainder_yes_rows,
        count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL AND remainder_will_be_given_class IN ('Y', 'YES')) AS product_remainder_yes_rows,
        count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL AND given_vs_label_amount = 'equal') AS products_given_equal_label_amount,
        count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL AND given_vs_label_amount = 'different') AS products_given_different_label_amount,
        count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL AND label_amount_meq_diagnostic IS NOT NULL) AS products_with_computable_label_amount,
        sum(label_amount_meq_diagnostic) FILTER (WHERE parent_field_ordinal IS NOT NULL) AS label_amount_sum_diagnostic,
        count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL AND product_concept = 'unmapped_description') AS products_unmapped_description,
        count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL AND product_concept = 'missing_description') AS products_missing_description,
        count(DISTINCT product_concept) FILTER (WHERE parent_field_ordinal IS NOT NULL) AS distinct_product_concepts,
        count(DISTINCT nullif(trim(product_description), '')) FILTER (WHERE parent_field_ordinal IS NOT NULL) AS distinct_raw_product_descriptions,
        count(DISTINCT nullif(trim(product_code), '')) FILTER (WHERE parent_field_ordinal IS NOT NULL) AS distinct_product_codes,
        count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL AND nullif(trim(product_code), '') IS NULL) AS products_missing_code,
        count(DISTINCT trim(parent_field_ordinal)) FILTER (WHERE parent_field_ordinal IS NOT NULL) AS distinct_product_ordinals,
        count(DISTINCT ordinal_prefix) FILTER (WHERE parent_field_ordinal IS NOT NULL) AS distinct_numeric_ordinal_prefixes,
        count(*) FILTER (WHERE ordinal_form = 'other_product') AS products_unparsed_ordinal
    FROM detail_semantics GROUP BY event_key
), event_comparisons AS MATERIALIZED (
    SELECT a.*, s.parent_due_present_rows, s.parent_due_numeric_meq_rows,
        s.parent_due_meq, s.product_due_present_rows,
        s.incomplete_dose_yes_rows, s.parent_incomplete_dose_yes_rows,
        s.product_incomplete_dose_yes_rows,
        s.remainder_yes_rows, s.parent_remainder_yes_rows, s.product_remainder_yes_rows,
        s.products_given_equal_label_amount, s.products_given_different_label_amount,
        s.products_with_computable_label_amount, s.label_amount_sum_diagnostic,
        s.products_unmapped_description, s.products_missing_description,
        s.distinct_product_concepts, s.distinct_raw_product_descriptions,
        s.distinct_product_codes, s.products_missing_code, s.distinct_product_ordinals,
        s.distinct_numeric_ordinal_prefixes, s.products_unparsed_ordinal,
        CASE WHEN coalesce(a.product_rows, 0) = 0 THEN 'no_product_rows'
             WHEN a.product_numeric_meq_rows <> a.product_rows THEN 'incomplete_product_meq_doses'
             WHEN a.product_meq_sum_diagnostic IN (0, 10, 20, 30, 40, 60, 80)
                  THEN a.product_meq_sum_diagnostic::integer::text
             ELSE 'other_numeric' END AS component_sum_bucket,
        CASE WHEN a.parent_rows <> 1 OR s.parent_due_numeric_meq_rows <> 1
                      OR s.parent_due_numeric_meq_rows IS NULL THEN 'no_single_numeric_meq_parent_due'
             WHEN a.product_rows = 0 OR a.product_numeric_meq_rows <> a.product_rows THEN 'incomplete_product_meq_doses'
             WHEN s.parent_due_meq = a.product_meq_sum_diagnostic
                      AND a.distinct_meq_doses = 1 AND s.parent_due_meq = a.min_product_meq_dose THEN 'equals_each_and_sum'
             WHEN s.parent_due_meq = a.product_meq_sum_diagnostic THEN 'equals_sum_not_each'
             WHEN a.distinct_meq_doses = 1 AND s.parent_due_meq = a.min_product_meq_dose THEN 'equals_each_not_sum'
             ELSE 'different_from_each_and_sum' END AS parent_due_vs_product_given,
        CASE WHEN coalesce(a.product_rows, 0) = 0 THEN 'no_product_rows'
             WHEN s.products_given_different_label_amount > 0 THEN 'at_least_one_difference'
             WHEN s.products_given_equal_label_amount = a.product_rows THEN 'all_equal'
             ELSE 'some_not_comparable' END AS product_given_vs_label_amount,
        CASE WHEN a.parent_rows <> 1 OR s.parent_due_numeric_meq_rows <> 1
                      OR s.parent_due_numeric_meq_rows IS NULL THEN 'no_single_numeric_meq_parent_due'
             WHEN a.product_rows = 0 OR s.products_with_computable_label_amount <> a.product_rows THEN 'incomplete_label_amount'
             WHEN s.parent_due_meq = s.label_amount_sum_diagnostic THEN 'equal'
             ELSE 'different' END AS parent_due_vs_label_amount_sum
    FROM assessed a LEFT JOIN dose_event_shapes s ON s.event_key = a.emar_id
), profiles AS (
    SELECT 'sample_summary'::text AS profile_section, '{}'::jsonb AS dimensions,
           count(*) AS source_rows, count(DISTINCT emar_id) AS emar_events,
           jsonb_build_object(
               'sampled_emar_rows', (SELECT count(*) FROM sampled),
               'selected_emar_rows', count(*),
               'complete_detail_rows', (SELECT count(*) FROM details),
               'single_product_source_candidates_191_rule', count(*) FILTER (WHERE single_product_source_candidate),
               'events_with_detail_identity_failure', count(*) FILTER (WHERE detail_identity_bad_rows > 0),
               'events_with_route_identity_failure', count(*) FILTER (WHERE identity_bad_evidence_rows > 0),
               'events_without_details', count(*) FILTER (WHERE detail_rows IS NULL),
               'events_with_parent_due', count(*) FILTER (WHERE parent_due_present_rows > 0),
               'events_with_complete_dose_not_given_yes', count(*) FILTER (WHERE incomplete_dose_yes_rows > 0),
               'events_with_remainder_will_be_given_yes', count(*) FILTER (WHERE remainder_yes_rows > 0),
               'events_missing_subject', count(*) FILTER (WHERE subject_id IS NULL),
               'events_missing_hadm', count(*) FILTER (WHERE hadm_id IS NULL),
               'events_missing_charttime', count(*) FILTER (WHERE charttime IS NULL),
               'events_missing_storetime', count(*) FILTER (WHERE storetime IS NULL),
               'events_storetime_before_charttime', count(*) FILTER (WHERE storetime < charttime),
               'events_with_unmapped_product_description', count(*) FILTER (WHERE products_unmapped_description > 0),
               'events_with_missing_product_description', count(*) FILTER (WHERE products_missing_description > 0)
           ) AS counters
    FROM event_comparisons
    UNION ALL
    SELECT 'detail_semantics',
           jsonb_build_object('event_txt', event_txt, 'route_pattern', route_pattern,
               'role', CASE WHEN parent_field_ordinal IS NULL THEN 'parent' ELSE 'product' END,
               'detail_identity_ok', detail_identity_ok, 'ordinal_form', ordinal_form,
               'complete_dose_not_given_class', complete_dose_not_given_class,
               'remainder_will_be_given_class', remainder_will_be_given_class,
               'product_concept', product_concept, 'due_bucket', due_bucket,
               'given_bucket', given_bucket, 'amount_bucket', amount_bucket,
               'due_unit_class', due_unit_class, 'given_unit_class', given_unit_class,
               'amount_unit_class', amount_unit_class,
               'row_due_vs_given', row_due_vs_given,
               'given_vs_label_amount', given_vs_label_amount),
           count(*), count(DISTINCT event_key),
           jsonb_build_object(
               'single_product_source_candidate_rows_191_rule', count(*) FILTER (WHERE single_product_source_candidate),
               'rows_with_product_code', count(*) FILTER (WHERE nullif(trim(product_code), '') IS NOT NULL),
               'distinct_product_codes', count(DISTINCT nullif(trim(product_code), '')),
               'distinct_raw_product_descriptions', count(DISTINCT nullif(trim(product_description), '')),
               'rows_with_computable_label_amount', count(*) FILTER (WHERE label_amount_meq_diagnostic IS NOT NULL),
               'listed_meq', min(listed_meq), 'listed_amount', min(listed_amount),
               'listed_amount_unit', min(listed_unit)
           )
    FROM detail_semantics
    GROUP BY event_txt, route_pattern, parent_field_ordinal IS NULL, detail_identity_ok,
             ordinal_form, complete_dose_not_given_class, remainder_will_be_given_class,
             product_concept, due_bucket, given_bucket, amount_bucket,
             due_unit_class, given_unit_class, amount_unit_class,
             row_due_vs_given, given_vs_label_amount
    UNION ALL
    SELECT 'event_comparison',
           jsonb_build_object('event_txt', event_txt, 'route_pattern', route_pattern,
               'single_product_source_candidate_191_rule', single_product_source_candidate,
               'any_complete_dose_not_given_yes', coalesce(incomplete_dose_yes_rows > 0, false),
               'any_remainder_will_be_given_yes', coalesce(remainder_yes_rows > 0, false),
               'product_dose_pattern', product_dose_pattern,
               'common_product_meq_bucket', common_product_meq_bucket,
               'component_sum_bucket', component_sum_bucket,
               'parent_due_vs_product_given', parent_due_vs_product_given,
               'product_given_vs_label_amount', product_given_vs_label_amount,
               'parent_due_vs_label_amount_sum', parent_due_vs_label_amount_sum),
           count(*), count(DISTINCT emar_id),
           jsonb_build_object(
               'product_rows', coalesce(sum(product_rows), 0),
               'events_with_parent_due', count(*) FILTER (WHERE parent_due_present_rows > 0),
               'events_with_product_due', count(*) FILTER (WHERE product_due_present_rows > 0),
               'events_with_parent_complete_dose_not_given_yes', count(*) FILTER (WHERE parent_incomplete_dose_yes_rows > 0),
               'events_with_product_complete_dose_not_given_yes', count(*) FILTER (WHERE product_incomplete_dose_yes_rows > 0),
               'events_with_parent_remainder_will_be_given_yes', count(*) FILTER (WHERE parent_remainder_yes_rows > 0),
               'events_with_product_remainder_will_be_given_yes', count(*) FILTER (WHERE product_remainder_yes_rows > 0),
               'events_missing_subject', count(*) FILTER (WHERE subject_id IS NULL),
               'events_missing_hadm', count(*) FILTER (WHERE hadm_id IS NULL),
               'events_missing_charttime', count(*) FILTER (WHERE charttime IS NULL),
               'events_missing_storetime', count(*) FILTER (WHERE storetime IS NULL),
               'events_storetime_before_charttime', count(*) FILTER (WHERE storetime < charttime),
               'events_with_known_other_pharmacy', count(*) FILTER (WHERE known_other_pharmacy_rows > 0),
               'events_with_product_missing_pharmacy', count(*) FILTER (WHERE product_missing_pharmacy_rows > 0),
               'events_with_multiple_products', count(*) FILTER (WHERE product_rows > 1),
               'events_with_multiple_product_concepts', count(*) FILTER (WHERE distinct_product_concepts > 1),
               'events_with_multiple_raw_descriptions', count(*) FILTER (WHERE distinct_raw_product_descriptions > 1),
               'events_with_multiple_product_codes', count(*) FILTER (WHERE distinct_product_codes > 1),
               'events_with_all_product_codes_same', count(*) FILTER (WHERE product_rows > 1 AND distinct_product_codes = 1 AND products_missing_code = 0),
               'events_with_missing_product_code', count(*) FILTER (WHERE products_missing_code > 0),
               'events_with_repeated_product_ordinal', count(*) FILTER (WHERE distinct_product_ordinals < product_rows),
               'events_with_multiple_ordinal_prefixes', count(*) FILTER (WHERE distinct_numeric_ordinal_prefixes > 1),
               'events_with_unparsed_product_ordinal', count(*) FILTER (WHERE products_unparsed_ordinal > 0),
               'events_with_unmapped_product_description', count(*) FILTER (WHERE products_unmapped_description > 0),
               'events_with_missing_product_description', count(*) FILTER (WHERE products_missing_description > 0),
               'events_with_detail_identity_failure', count(*) FILTER (WHERE detail_identity_bad_rows > 0),
               'events_with_route_identity_failure', count(*) FILTER (WHERE identity_bad_evidence_rows > 0),
               'events_with_iv_route_enteral_product_form_conflict', count(*) FILTER (WHERE route_pattern = 'explicit_iv_only' AND (tab_product_rows > 0 OR pkt_product_rows > 0))
           )
    FROM event_comparisons
    GROUP BY event_txt, route_pattern, single_product_source_candidate,
             coalesce(incomplete_dose_yes_rows > 0, false),
             coalesce(remainder_yes_rows > 0, false),
             product_dose_pattern, common_product_meq_bucket, component_sum_bucket,
             parent_due_vs_product_given, product_given_vs_label_amount,
             parent_due_vs_label_amount_sum
)
SELECT profile_section, dimensions, source_rows, emar_events,
       counters || jsonb_build_object('system_sample_percent', 1.0,
           'sample_seed', 20261011, 'formal_action_mapping', false,
           'dose_due_is_actual_dose', false, 'label_amount_is_actual_dose', false,
           'product_sum_is_actual_dose', false,
           'strength_evidence', 'description_strength_only_not_external_label_verified',
           'flag_tokens', 'Y/YES affirmative; N/NO negative; other text unclassified; case/outer space normalized',
           'dictionary_scope', 'finite observed 191 product vocabulary; unmapped descriptions retained') AS counters
FROM profiles
ORDER BY profile_section, source_rows DESC, dimensions;
