-- D003/D005 event-level intersection audit only. This query recomputes the 194
-- provisional source-dose rule and the 195 anchor/location/lab diagnostics in
-- one read-only statement over the same fixed 1% eMAR page sample. Internal
-- joins use emar_id, subject_id and hadm_id, but no identifier, timestamp, raw
-- value, free text, product code, ordinal or dose string is emitted.
--
-- The source-dose rule remains conservative: Administered, exact-name source,
-- explicit-IV-only evidence, valid identity/time/pharmacy and product shape,
-- strictly positive numeric mEq components, no TAB/PKT conflict, parent
-- dose_due equal to ordinary component SUM, finite local description arithmetic,
-- and no affirmative parent or any product-row completion flag. It is still not
-- an accepted actual dose or paper action; parent completeness can remain unknown.
--
-- eMAR charttime remains only an administration-record anchor. Provisional
-- transfer coverage, pre-anchor lab availability and the first strictly later K
-- timestamp are intersected with candidates without becoming a formal non-ICU
-- rule, baseline-value rule, treatment endpoint or post-infusion label. Lab
-- availability means storetime <= anchor; finite values, units and ties stay
-- explicit. The diagnostic flow is a transparent nested count, not a cohort.
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
           e.pharmacy_id AS event_pharmacy, d.*,
           d.subject_id IS NOT DISTINCT FROM e.subject_id
             AND e.subject_id IS NOT NULL
             AND d.emar_seq IS NOT DISTINCT FROM e.emar_seq
             AND e.emar_seq IS NOT NULL AS detail_identity_ok,
           CASE WHEN trim(d.dose_given) ~ '^[0-9]+([.][0-9]+)?$'
                THEN trim(d.dose_given)::numeric END AS dose_numeric
    FROM events e JOIN mimiciv_hosp.emar_detail d ON d.emar_id = e.emar_id
), pharmacy_keys AS MATERIALIZED (
    SELECT pharmacy_id FROM events WHERE pharmacy_id IS NOT NULL
    UNION
    SELECT pharmacy_id FROM details WHERE pharmacy_id IS NOT NULL
), pharmacies AS MATERIALIZED (
    SELECT p.* FROM pharmacy_keys k
    JOIN LATERAL (
        SELECT pharmacy_id, subject_id, hadm_id, route
        FROM mimiciv_hosp.pharmacy p
        WHERE p.pharmacy_id = k.pharmacy_id OFFSET 0
    ) p ON true
), prescriptions AS MATERIALIZED (
    SELECT p.* FROM pharmacy_keys k
    JOIN LATERAL (
        SELECT pharmacy_id, subject_id, hadm_id, route
        FROM mimiciv_hosp.prescriptions p
        WHERE p.pharmacy_id = k.pharmacy_id OFFSET 0
    ) p ON true
), route_evidence AS MATERIALIZED (
    SELECT e.emar_id AS event_key, p.route,
           e.subject_id IS NOT NULL AND e.hadm_id IS NOT NULL
             AND p.subject_id IS NOT DISTINCT FROM e.subject_id
             AND p.hadm_id IS NOT DISTINCT FROM e.hadm_id AS identity_ok
    FROM events e JOIN pharmacies p USING (pharmacy_id)
    UNION ALL
    SELECT e.emar_id, p.route,
           e.subject_id IS NOT NULL AND e.hadm_id IS NOT NULL
             AND p.subject_id IS NOT DISTINCT FROM e.subject_id
             AND p.hadm_id IS NOT DISTINCT FROM e.hadm_id
    FROM events e JOIN prescriptions p USING (pharmacy_id)
    UNION ALL
    SELECT d.event_key, d.route, d.detail_identity_ok
    FROM details d
    UNION ALL
    SELECT d.event_key, p.route,
           d.detail_identity_ok AND d.event_hadm IS NOT NULL
             AND p.subject_id IS NOT DISTINCT FROM d.event_subject
             AND p.hadm_id IS NOT DISTINCT FROM d.event_hadm
    FROM details d JOIN pharmacies p USING (pharmacy_id)
    UNION ALL
    SELECT d.event_key, p.route,
           d.detail_identity_ok AND d.event_hadm IS NOT NULL
             AND p.subject_id IS NOT DISTINCT FROM d.event_subject
             AND p.hadm_id IS NOT DISTINCT FROM d.event_hadm
    FROM details d JOIN prescriptions p USING (pharmacy_id)
), classified_routes AS MATERIALIZED (
    SELECT *, CASE
        WHEN nullif(trim(route), '') IS NULL THEN 'missing'
        WHEN upper(trim(route)) IN
             ('IV', 'INTRAVENOUS', 'IV DRIP', 'IV BOLUS', 'IVP') THEN 'explicit_iv'
        WHEN upper(trim(route)) IN
             ('PO', 'ORAL', 'NG', 'OG', 'PO/NG', 'G TUBE', 'J TUBE', 'PEG', 'ENTERAL')
             THEN 'explicit_enteral'
        ELSE 'other_unmapped' END AS route_class
    FROM route_evidence
), route_shapes AS MATERIALIZED (
    SELECT event_key,
           count(*) FILTER (WHERE NOT identity_ok) AS identity_bad_evidence_rows,
           count(*) FILTER (WHERE identity_ok AND route_class = 'explicit_iv') AS iv_evidence_rows,
           count(*) FILTER (WHERE identity_ok AND route_class = 'explicit_enteral') AS enteral_evidence_rows,
           count(*) FILTER (WHERE identity_ok AND route_class = 'other_unmapped') AS other_evidence_rows
    FROM classified_routes GROUP BY event_key
), product_dictionary
   (description_key, product_concept, listed_meq, listed_amount, listed_unit) AS (
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
    SELECT d.*,
           CASE WHEN trim(dose_due) ~ '^[0-9]+([.][0-9]+)?$'
                THEN trim(dose_due)::numeric END AS due_numeric,
           CASE WHEN trim(product_amount_given) ~ '^[0-9]+([.][0-9]+)?$'
                THEN trim(product_amount_given)::numeric END AS amount_numeric,
           CASE WHEN upper(trim(dose_due_unit)) = 'MEQ' THEN 'MEQ'
                WHEN nullif(trim(dose_due_unit), '') IS NULL THEN 'missing'
                ELSE 'other' END AS due_unit_class,
           CASE WHEN upper(trim(dose_given_unit)) = 'MEQ' THEN 'MEQ'
                WHEN nullif(trim(dose_given_unit), '') IS NULL THEN 'missing'
                ELSE 'other' END AS given_unit_class,
           CASE WHEN upper(trim(product_unit)) = 'ML' THEN 'ML'
                WHEN upper(trim(product_unit)) IN ('TAB', 'TABLET') THEN 'TAB'
                WHEN upper(trim(product_unit)) IN ('PKT', 'PACKET') THEN 'PKT'
                WHEN nullif(trim(product_unit), '') IS NULL THEN 'missing'
                ELSE 'other' END AS amount_unit_class,
           CASE WHEN upper(trim(complete_dose_not_given)) IN ('Y', 'N', 'YES', 'NO')
                     THEN upper(trim(complete_dose_not_given))
                WHEN nullif(trim(complete_dose_not_given), '') IS NULL THEN 'missing'
                ELSE 'other_nonempty' END AS incomplete_flag_class,
           CASE WHEN upper(trim(will_remainder_of_dose_be_given)) IN ('Y', 'N', 'YES', 'NO')
                     THEN upper(trim(will_remainder_of_dose_be_given))
                WHEN nullif(trim(will_remainder_of_dose_be_given), '') IS NULL THEN 'missing'
                ELSE 'other_nonempty' END AS remainder_flag_class,
           CASE WHEN parent_field_ordinal IS NULL THEN 'parent'
                WHEN trim(parent_field_ordinal) ~ '^[0-9]+$' THEN 'integer_product'
                WHEN trim(parent_field_ordinal) ~ '^[0-9]+[.][0-9]+$' THEN 'dotted_product'
                ELSE 'other_product' END AS ordinal_form,
           CASE WHEN trim(parent_field_ordinal) ~ '^[0-9]+([.][0-9]+)?$'
                THEN split_part(trim(parent_field_ordinal), '.', 1) END AS ordinal_prefix,
           p.product_concept, p.listed_meq, p.listed_amount, p.listed_unit
    FROM details d LEFT JOIN product_dictionary p ON p.description_key =
        lower(regexp_replace(trim(d.product_description), '[[:space:]]+', ' ', 'g'))
), compared_details AS MATERIALIZED (
    SELECT *,
           CASE WHEN parent_field_ordinal IS NOT NULL
                       AND amount_numeric IS NOT NULL
                       AND amount_unit_class = listed_unit
                THEN amount_numeric * listed_meq / listed_amount END
                AS description_amount_meq_diagnostic
    FROM parsed_details
), detail_semantics AS MATERIALIZED (
    SELECT *, CASE
        WHEN parent_field_ordinal IS NULL THEN 'not_product'
        WHEN dose_numeric IS NULL OR given_unit_class <> 'MEQ'
                  OR description_amount_meq_diagnostic IS NULL THEN 'unresolved'
        WHEN dose_numeric = description_amount_meq_diagnostic THEN 'equal'
        ELSE 'different' END AS product_internal_consistency
    FROM compared_details
), detail_shapes AS MATERIALIZED (
    SELECT event_key,
        count(*) AS detail_rows,
        count(*) FILTER (WHERE parent_field_ordinal IS NULL) AS parent_rows,
        count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL) AS product_rows,
        count(*) FILTER (WHERE NOT detail_identity_ok) AS detail_identity_bad_rows,
        count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL AND pharmacy_id IS NULL)
            AS product_missing_pharmacy_rows,
        count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL
                              AND pharmacy_id IS NOT NULL
                              AND event_pharmacy IS NOT NULL
                              AND pharmacy_id <> event_pharmacy)
            AS product_other_pharmacy_rows,
        count(*) FILTER (WHERE parent_field_ordinal IS NULL
                              AND nullif(trim(dose_due), '') IS NOT NULL)
            AS parent_due_present_rows,
        count(*) FILTER (WHERE parent_field_ordinal IS NULL
                              AND due_numeric IS NOT NULL AND due_unit_class = 'MEQ')
            AS parent_due_numeric_meq_rows,
        min(due_numeric) FILTER (WHERE parent_field_ordinal IS NULL
                                      AND due_unit_class = 'MEQ') AS parent_due_meq,
        count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL
                              AND nullif(trim(dose_due), '') IS NOT NULL)
            AS product_due_present_rows,
        count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL
                              AND dose_numeric IS NOT NULL AND given_unit_class = 'MEQ')
            AS product_numeric_meq_rows,
        sum(dose_numeric) FILTER (WHERE parent_field_ordinal IS NOT NULL
                                      AND given_unit_class = 'MEQ')
            AS product_component_sum_meq,
        count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL
                              AND product_internal_consistency = 'equal')
            AS product_consistent_rows,
        count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL
                              AND product_internal_consistency = 'different')
            AS product_inconsistent_rows,
        count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL
                              AND product_internal_consistency = 'unresolved')
            AS product_consistency_unresolved_rows,
        count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL
                              AND amount_unit_class IN ('TAB', 'PKT'))
            AS enteral_product_form_rows,
        count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL
                              AND dose_numeric IS NOT NULL
                              AND given_unit_class = 'MEQ'
                              AND dose_numeric <= 0)
            AS nonpositive_product_component_rows,
        count(*) FILTER (WHERE parent_field_ordinal IS NULL
                              AND incomplete_flag_class IN ('Y', 'YES'))
            AS parent_incomplete_affirmative_rows,
        count(*) FILTER (WHERE parent_field_ordinal IS NULL
                              AND remainder_flag_class IN ('Y', 'YES'))
            AS parent_remainder_affirmative_rows,
        count(*) FILTER (WHERE parent_field_ordinal IS NULL
                              AND (incomplete_flag_class = 'other_nonempty'
                                   OR remainder_flag_class = 'other_nonempty'))
            AS parent_unrecognized_flag_rows,
        count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL
                              AND (incomplete_flag_class <> 'missing'
                                   OR remainder_flag_class <> 'missing'))
            AS product_completion_flag_rows,
        count(*) FILTER (WHERE parent_field_ordinal IS NULL
                              AND incomplete_flag_class IN ('N', 'NO'))
            AS parent_incomplete_negative_rows,
        count(*) FILTER (WHERE parent_field_ordinal IS NULL
                              AND remainder_flag_class IN ('N', 'NO'))
            AS parent_remainder_negative_rows,
        count(DISTINCT trim(parent_field_ordinal))
            FILTER (WHERE parent_field_ordinal IS NOT NULL) AS distinct_product_ordinals,
        count(DISTINCT ordinal_prefix)
            FILTER (WHERE parent_field_ordinal IS NOT NULL) AS distinct_ordinal_prefixes,
        count(*) FILTER (WHERE ordinal_form = 'other_product') AS unparsed_product_ordinals,
        count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL
                              AND product_concept IS NULL) AS unmapped_product_rows,
        count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL
                              AND nullif(trim(product_code), '') IS NULL) AS missing_product_code_rows
    FROM detail_semantics GROUP BY event_key
), event_shapes AS MATERIALIZED (
    SELECT e.*,
        coalesce(d.detail_rows, 0) AS detail_rows,
        coalesce(d.parent_rows, 0) AS parent_rows,
        coalesce(d.product_rows, 0) AS product_rows,
        coalesce(d.detail_identity_bad_rows, 0) AS detail_identity_bad_rows,
        coalesce(d.product_missing_pharmacy_rows, 0) AS product_missing_pharmacy_rows,
        coalesce(d.product_other_pharmacy_rows, 0) AS product_other_pharmacy_rows,
        coalesce(d.parent_due_present_rows, 0) AS parent_due_present_rows,
        coalesce(d.parent_due_numeric_meq_rows, 0) AS parent_due_numeric_meq_rows,
        d.parent_due_meq,
        coalesce(d.product_due_present_rows, 0) AS product_due_present_rows,
        coalesce(d.product_numeric_meq_rows, 0) AS product_numeric_meq_rows,
        d.product_component_sum_meq,
        coalesce(d.product_consistent_rows, 0) AS product_consistent_rows,
        coalesce(d.product_inconsistent_rows, 0) AS product_inconsistent_rows,
        coalesce(d.product_consistency_unresolved_rows, 0) AS product_consistency_unresolved_rows,
        coalesce(d.enteral_product_form_rows, 0) AS enteral_product_form_rows,
        coalesce(d.nonpositive_product_component_rows, 0)
            AS nonpositive_product_component_rows,
        coalesce(d.parent_incomplete_affirmative_rows, 0)
            AS parent_incomplete_affirmative_rows,
        coalesce(d.parent_remainder_affirmative_rows, 0)
            AS parent_remainder_affirmative_rows,
        coalesce(d.parent_unrecognized_flag_rows, 0) AS parent_unrecognized_flag_rows,
        coalesce(d.product_completion_flag_rows, 0) AS product_completion_flag_rows,
        coalesce(d.parent_incomplete_negative_rows, 0) AS parent_incomplete_negative_rows,
        coalesce(d.parent_remainder_negative_rows, 0) AS parent_remainder_negative_rows,
        coalesce(d.distinct_product_ordinals, 0) AS distinct_product_ordinals,
        coalesce(d.distinct_ordinal_prefixes, 0) AS distinct_ordinal_prefixes,
        coalesce(d.unparsed_product_ordinals, 0) AS unparsed_product_ordinals,
        coalesce(d.unmapped_product_rows, 0) AS unmapped_product_rows,
        coalesce(d.missing_product_code_rows, 0) AS missing_product_code_rows,
        coalesce(r.identity_bad_evidence_rows, 0) AS route_identity_bad_rows,
        CASE WHEN coalesce(r.iv_evidence_rows, 0) > 0
                       AND coalesce(r.enteral_evidence_rows, 0) > 0 THEN 'iv_enteral_conflict'
             WHEN coalesce(r.other_evidence_rows, 0) > 0 THEN 'other_route_evidence_present'
             WHEN coalesce(r.iv_evidence_rows, 0) > 0 THEN 'explicit_iv_only'
             WHEN coalesce(r.enteral_evidence_rows, 0) > 0 THEN 'explicit_enteral_only'
             ELSE 'no_valid_known_route' END AS route_pattern
    FROM events e LEFT JOIN detail_shapes d ON d.event_key = e.emar_id
    LEFT JOIN route_shapes r ON r.event_key = e.emar_id
), evidence_classes AS MATERIALIZED (
    SELECT *,
        CASE WHEN trim(event_txt) = 'Administered' THEN 'administered'
             WHEN trim(event_txt) = 'Partial Administered' THEN 'partial_administered'
             WHEN trim(event_txt) = 'Started' THEN 'started'
             WHEN trim(event_txt) = 'Stopped' THEN 'stopped'
             WHEN trim(event_txt) = 'Not Given' THEN 'not_given'
             WHEN nullif(trim(event_txt), '') IS NULL THEN 'missing'
             ELSE 'other_nonempty' END AS event_status_class,
        CASE WHEN parent_rows <> 1 THEN 'invalid_parent_structure'
             WHEN parent_due_numeric_meq_rows <> 1 THEN 'non_numeric_or_non_meq'
             WHEN parent_due_meq IN (10, 20, 40, 60, 80)
                  THEN parent_due_meq::integer::text
             ELSE 'other_numeric' END AS parent_due_bucket,
        CASE WHEN product_rows = 0 THEN 'no_product_rows'
             WHEN product_numeric_meq_rows <> product_rows THEN 'non_numeric_or_non_meq'
             WHEN product_component_sum_meq IN (10, 20, 40, 60, 80)
                  THEN product_component_sum_meq::integer::text
             ELSE 'other_numeric' END AS component_sum_bucket,
        CASE WHEN product_rows = 0 THEN 'no_product_rows'
             WHEN product_rows = 1 THEN 'single_product'
             ELSE 'multiple_products' END AS component_structure,
        CASE WHEN parent_rows <> 1 OR parent_due_numeric_meq_rows <> 1
                  THEN 'parent_due_unresolved'
             WHEN product_rows = 0 OR product_numeric_meq_rows <> product_rows
                  THEN 'component_sum_unresolved'
             WHEN parent_due_meq = product_component_sum_meq THEN 'equal'
             ELSE 'different' END AS parent_due_vs_component_sum,
        CASE WHEN product_rows = 0 THEN 'no_product_rows'
             WHEN product_inconsistent_rows > 0 THEN 'at_least_one_difference'
             WHEN product_consistent_rows = product_rows THEN 'all_equal'
             ELSE 'at_least_one_unresolved' END AS component_internal_consistency,
        CASE WHEN parent_incomplete_affirmative_rows > 0
                       OR parent_remainder_affirmative_rows > 0
                  THEN 'affirmative_incomplete_or_remainder'
             WHEN parent_rows = 1
                  AND parent_incomplete_negative_rows = 1
                  AND parent_remainder_negative_rows = 1
                  AND parent_unrecognized_flag_rows = 0
                  THEN 'explicit_negative_parent_flags'
             WHEN parent_unrecognized_flag_rows > 0
                  THEN 'unknown_unrecognized_parent_token'
             ELSE 'unknown_missing_or_partial_negative' END AS completeness_evidence,
        (subject_id IS NULL OR hadm_id IS NULL OR emar_id IS NULL OR emar_seq IS NULL
             OR detail_identity_bad_rows > 0 OR route_identity_bad_rows > 0) AS identity_issue,
        (charttime IS NULL OR storetime IS NULL OR storetime < charttime) AS time_issue,
        (pharmacy_id IS NULL OR product_missing_pharmacy_rows > 0
             OR product_other_pharmacy_rows > 0) AS pharmacy_issue,
        (product_rows = 0 OR unparsed_product_ordinals > 0
             OR distinct_product_ordinals <> product_rows
             OR distinct_ordinal_prefixes <> 1) AS product_structure_issue
    FROM event_shapes
), classified AS MATERIALIZED (
    SELECT *,
        coalesce(
          event_status_class = 'administered'
          AND parent_incomplete_affirmative_rows = 0
          AND parent_remainder_affirmative_rows = 0
          AND product_completion_flag_rows = 0
          AND NOT identity_issue
          AND NOT time_issue
          AND route_pattern = 'explicit_iv_only'
          AND enteral_product_form_rows = 0
          AND NOT pharmacy_issue
          AND parent_rows = 1
          AND NOT product_structure_issue
          AND parent_due_numeric_meq_rows = 1
          AND product_numeric_meq_rows = product_rows
          AND parent_due_meq = product_component_sum_meq
          AND product_consistent_rows = product_rows
          AND product_rows > 0
          AND nonpositive_product_component_rows = 0
          AND product_component_sum_meq > 0,
          false) AS provisional_component_dose_candidate,
        CASE
          WHEN event_status_class <> 'administered' THEN 'non_administered_status'
          WHEN parent_incomplete_affirmative_rows > 0
                    OR parent_remainder_affirmative_rows > 0
               THEN 'affirmative_incomplete_or_remainder'
          WHEN product_completion_flag_rows > 0 THEN 'product_completion_flag_anomaly'
          WHEN identity_issue THEN 'identity_issue'
          WHEN time_issue THEN 'time_issue'
          WHEN route_pattern <> 'explicit_iv_only' THEN 'route_issue'
          WHEN enteral_product_form_rows > 0 THEN 'enteral_product_form_conflict'
          WHEN pharmacy_issue THEN 'pharmacy_linkage_issue'
          WHEN parent_rows <> 1 THEN 'parent_structure_issue'
          WHEN product_structure_issue THEN 'product_structure_issue'
          WHEN parent_due_numeric_meq_rows <> 1 THEN 'parent_due_non_numeric_or_non_meq'
          WHEN product_numeric_meq_rows <> product_rows THEN 'component_non_numeric_or_non_meq'
          WHEN parent_due_meq <> product_component_sum_meq THEN 'parent_due_component_sum_mismatch'
          WHEN product_inconsistent_rows > 0 THEN 'component_internal_consistency_failed'
          WHEN product_consistent_rows <> product_rows THEN 'component_internal_consistency_unresolved'
          WHEN product_component_sum_meq <= 0 THEN 'nonpositive_component_sum_not_zero_action'
          WHEN nonpositive_product_component_rows > 0
               THEN 'nonpositive_component_present_not_zero_action'
          WHEN completeness_evidence = 'explicit_negative_parent_flags'
               THEN 'internally_consistent_with_explicit_negative_flags'
          ELSE 'internally_consistent_but_completeness_unknown'
        END AS source_dose_status,
        CASE WHEN product_rows = 0 OR product_numeric_meq_rows <> product_rows
                  THEN 'unresolved'
             WHEN product_component_sum_meq IN (10, 20, 40)
                  THEN 'matches_positive_paper_action_value'
             WHEN product_component_sum_meq IN (60, 80)
                  THEN 'explicit_60_or_80_outside_paper_action_set'
             WHEN product_component_sum_meq > 0 THEN 'other_positive_outside_paper_action_set'
             ELSE 'nonpositive_not_zero_action' END AS paper_action_relation
    FROM evidence_classes
), candidate_anchors AS MATERIALIZED (
    SELECT emar_id, subject_id, hadm_id, charttime,
           product_component_sum_meq, component_sum_bucket,
           component_structure, completeness_evidence, paper_action_relation
    FROM classified
    WHERE provisional_component_dose_candidate
), candidate_admissions AS MATERIALIZED (
    SELECT DISTINCT subject_id, hadm_id FROM candidate_anchors
), icu_units(careunit) AS (
    VALUES ('Cardiac Vascular Intensive Care Unit (CVICU)'),
           ('Coronary Care Unit (CCU)'), ('Intensive Care Unit (ICU)'),
           ('Medical Intensive Care Unit (MICU)'),
           ('Medical/Surgical Intensive Care Unit (MICU/SICU)'),
           ('Neuro Surgical Intensive Care Unit (Neuro SICU)'),
           ('Surgical Intensive Care Unit (SICU)'), ('Trauma SICU (TSICU)')
), admission_transfers AS MATERIALIZED (
    SELECT a.subject_id, a.hadm_id, t.careunit, t.intime, t.outtime,
           (t.intime IS NOT NULL AND t.outtime IS NOT NULL
             AND t.outtime > t.intime) AS valid_interval,
           u.careunit IS NOT NULL AS is_icu,
           (u.careunit IS NULL AND nullif(trim(t.careunit), '') IS NOT NULL
             AND upper(trim(t.careunit)) <> 'UNKNOWN') AS is_named_non_icu
    FROM candidate_admissions a JOIN mimiciv_hosp.transfers t
      ON t.subject_id = a.subject_id AND t.hadm_id = a.hadm_id
    LEFT JOIN icu_units u ON u.careunit = t.careunit
    WHERE t.eventtype IS DISTINCT FROM 'discharge'
), anchor_points_base AS MATERIALIZED (
    SELECT a.emar_id,
           count(*) FILTER (WHERE t.valid_interval
              AND a.charttime >= t.intime AND a.charttime < t.outtime) AS active_intervals,
           count(*) FILTER (WHERE t.valid_interval AND t.is_icu
              AND a.charttime >= t.intime AND a.charttime < t.outtime) AS active_icu_intervals,
           count(*) FILTER (WHERE t.valid_interval AND t.is_named_non_icu
              AND a.charttime >= t.intime AND a.charttime < t.outtime)
              AS active_named_non_icu_intervals,
           count(*) FILTER (WHERE t.valid_interval IS FALSE AND
              (t.intime IS NULL OR t.outtime IS NULL OR
               (a.charttime >= least(t.intime,t.outtime)
                AND a.charttime <= greatest(t.intime,t.outtime)))) AS invalid_at_anchor_rows
    FROM candidate_anchors a LEFT JOIN admission_transfers t
      ON t.subject_id = a.subject_id AND t.hadm_id = a.hadm_id
    GROUP BY a.emar_id
), anchor_points AS MATERIALIZED (
    SELECT a.emar_id, b.active_intervals, b.active_icu_intervals,
           b.active_named_non_icu_intervals, b.invalid_at_anchor_rows,
           CASE WHEN b.invalid_at_anchor_rows > 0 THEN 'potential_invalid_transfer'
                WHEN b.active_intervals = 0 THEN 'gap_no_active_interval'
                WHEN b.active_intervals > 1 THEN 'overlap_multiple_active_intervals'
                WHEN b.active_icu_intervals = 1 THEN 'icu'
                WHEN b.active_named_non_icu_intervals = 1 THEN 'non_icu_provisional'
                ELSE 'unknown_careunit' END AS anchor_point_status
    FROM candidate_anchors a JOIN anchor_points_base b USING (emar_id)
), context_windows AS MATERIALIZED (
    SELECT emar_id, subject_id, hadm_id, charttime - interval '4 hours' AS window_start,
           charttime AS window_end
    FROM candidate_anchors
), cutpoints AS MATERIALIZED (
    SELECT emar_id, window_start AS cutpoint FROM context_windows
    UNION
    SELECT emar_id, window_end FROM context_windows
    UNION
    SELECT w.emar_id, greatest(w.window_start, t.intime)
    FROM context_windows w JOIN admission_transfers t USING (subject_id, hadm_id)
    WHERE t.valid_interval AND t.intime < w.window_end AND t.outtime > w.window_start
    UNION
    SELECT w.emar_id, least(w.window_end, t.outtime)
    FROM context_windows w JOIN admission_transfers t USING (subject_id, hadm_id)
    WHERE t.valid_interval AND t.intime < w.window_end AND t.outtime > w.window_start
), atoms_base AS MATERIALIZED (
    SELECT emar_id, cutpoint AS atom_start,
           lead(cutpoint) OVER (PARTITION BY emar_id ORDER BY cutpoint) AS atom_end
    FROM cutpoints
), atoms AS MATERIALIZED (
    SELECT w.emar_id, extract(epoch FROM (b.atom_end-b.atom_start)) AS seconds,
           count(*) FILTER (WHERE t.valid_interval) AS active_intervals,
           count(*) FILTER (WHERE t.valid_interval AND t.is_icu) AS active_icu_intervals,
           count(*) FILTER (WHERE t.valid_interval AND t.is_named_non_icu)
               AS active_named_non_icu_intervals
    FROM atoms_base b JOIN context_windows w USING (emar_id)
    LEFT JOIN admission_transfers t
      ON t.subject_id = w.subject_id AND t.hadm_id = w.hadm_id
     AND t.valid_interval AND t.intime <= b.atom_start AND t.outtime >= b.atom_end
    WHERE b.atom_end > b.atom_start
    GROUP BY w.emar_id, b.atom_start, b.atom_end
), atom_summary AS MATERIALIZED (
    SELECT emar_id, sum(seconds) AS evaluated_seconds,
           coalesce(sum(seconds) FILTER (WHERE active_intervals=0),0) AS gap_seconds,
           coalesce(sum(seconds) FILTER (WHERE active_intervals>1),0) AS overlap_seconds,
           coalesce(sum(seconds) FILTER (WHERE active_icu_intervals>0),0) AS icu_seconds,
           coalesce(sum(seconds) FILTER (WHERE active_intervals=1
               AND active_icu_intervals=0 AND active_named_non_icu_intervals=0),0)
               AS unknown_unit_seconds,
           coalesce(sum(seconds) FILTER (WHERE active_intervals=1
               AND active_named_non_icu_intervals=1),0) AS single_named_non_icu_seconds
    FROM atoms GROUP BY emar_id
), invalid_window_summary AS MATERIALIZED (
    SELECT w.emar_id,
           count(*) FILTER (WHERE t.valid_interval IS FALSE) AS invalid_admission_rows,
           count(*) FILTER (WHERE t.valid_interval IS FALSE AND
             (t.intime IS NULL OR t.outtime IS NULL OR
              (greatest(t.intime,t.outtime) >= w.window_start
               AND least(t.intime,t.outtime) < w.window_end)))
               AS potentially_intersecting_invalid_rows
    FROM context_windows w LEFT JOIN admission_transfers t USING (subject_id,hadm_id)
    GROUP BY w.emar_id
), window_locations AS MATERIALIZED (
    SELECT w.emar_id, a.evaluated_seconds, a.gap_seconds, a.overlap_seconds,
           a.icu_seconds, a.unknown_unit_seconds, a.single_named_non_icu_seconds,
           i.invalid_admission_rows, i.potentially_intersecting_invalid_rows,
           CASE WHEN a.icu_seconds > 0 THEN 'contains_icu'
                WHEN a.overlap_seconds > 0 THEN 'contains_overlap'
                WHEN a.gap_seconds > 0 THEN 'contains_gap'
                WHEN a.unknown_unit_seconds > 0 THEN 'contains_unknown_careunit'
                WHEN i.potentially_intersecting_invalid_rows > 0
                    THEN 'potential_invalid_transfer'
                WHEN a.evaluated_seconds = 14400
                  AND a.single_named_non_icu_seconds = a.evaluated_seconds
                    THEN 'complete_single_named_non_icu_provisional'
                ELSE 'unexplained_coverage' END AS pre4h_window_status
    FROM context_windows w JOIN atom_summary a USING (emar_id)
    JOIN invalid_window_summary i USING (emar_id)
), rare_labs AS MATERIALIZED (
    -- These rare itemids lack the useful partial indexes available for 50971
    -- and 50912. Restrict one scan to candidate admissions.
    SELECT l.labevent_id,l.subject_id,l.hadm_id,l.itemid,l.charttime,l.storetime,
           l.valuenum,l.valueuom
    FROM mimiciv_hosp.labevents l JOIN candidate_admissions a
      ON a.subject_id=l.subject_id AND a.hadm_id=l.hadm_id
    WHERE l.itemid IN (52610,52546)
), common_pre_labs AS MATERIALIZED (
    SELECT a.emar_id,a.subject_id,a.hadm_id,a.charttime AS anchor_time,
           'potassium'::text AS concept,l.labevent_id,l.itemid,l.charttime,
           l.storetime,l.valuenum,l.valueuom
    FROM candidate_anchors a CROSS JOIN LATERAL (
        SELECT labevent_id,itemid,charttime,storetime,valuenum,valueuom
        FROM mimiciv_hosp.labevents l
        WHERE l.subject_id=a.subject_id AND l.hadm_id=a.hadm_id
          AND l.itemid=50971
          AND l.charttime>=a.charttime-interval '4 hours'
          AND l.charttime<a.charttime OFFSET 0
    ) l
    UNION ALL
    SELECT a.emar_id,a.subject_id,a.hadm_id,a.charttime,
           'creatinine'::text,l.labevent_id,l.itemid,l.charttime,
           l.storetime,l.valuenum,l.valueuom
    FROM candidate_anchors a CROSS JOIN LATERAL (
        SELECT labevent_id,itemid,charttime,storetime,valuenum,valueuom
        FROM mimiciv_hosp.labevents l
        WHERE l.subject_id=a.subject_id AND l.hadm_id=a.hadm_id
          AND l.itemid=50912
          AND l.charttime>=a.charttime-interval '4 hours'
          AND l.charttime<a.charttime OFFSET 0
    ) l
), rare_pre_labs AS MATERIALIZED (
    SELECT a.emar_id,a.subject_id,a.hadm_id,a.charttime AS anchor_time,
           CASE WHEN l.itemid=52610 THEN 'potassium'::text ELSE 'creatinine'::text END
             AS concept,
           l.labevent_id,l.itemid,l.charttime,l.storetime,l.valuenum,l.valueuom
    FROM candidate_anchors a JOIN rare_labs l
      ON l.subject_id=a.subject_id AND l.hadm_id=a.hadm_id
     AND l.charttime>=a.charttime-interval '4 hours' AND l.charttime<a.charttime
), pre_labs AS MATERIALIZED (
    SELECT * FROM common_pre_labs
    UNION ALL
    SELECT * FROM rare_pre_labs
), pre_times AS MATERIALIZED (
    SELECT emar_id,concept,max(charttime) AS latest_sample_time,
           max(charttime) FILTER (WHERE storetime<=anchor_time) AS latest_available_time
    FROM pre_labs GROUP BY emar_id,concept
), pre_counts AS MATERIALIZED (
    SELECT p.emar_id,p.concept,
           count(*) AS window_rows,
           count(*) FILTER (WHERE p.storetime<=p.anchor_time) AS available_rows,
           count(*) FILTER (WHERE p.storetime>p.anchor_time) AS delayed_rows,
           count(*) FILTER (WHERE p.storetime IS NULL) AS missing_storetime_rows,
           count(*) FILTER (WHERE p.storetime<p.charttime) AS reversed_storetime_rows,
           count(*) FILTER (WHERE p.charttime=t.latest_sample_time) AS latest_sample_rows,
           count(*) FILTER (WHERE p.charttime=t.latest_available_time
                             AND p.storetime<=p.anchor_time) AS latest_available_rows,
           count(*) FILTER (WHERE p.charttime=t.latest_available_time
                             AND p.storetime<=p.anchor_time
                             AND p.valuenum IS NOT NULL
                             AND p.valuenum::text NOT IN ('NaN','Infinity','-Infinity'))
               AS latest_available_finite_rows,
           count(*) FILTER (WHERE p.charttime=t.latest_available_time
                             AND p.storetime<=p.anchor_time
                             AND p.valuenum IS NOT NULL
                             AND p.valuenum::text NOT IN ('NaN','Infinity','-Infinity')
                             AND ((p.concept='potassium' AND upper(trim(p.valueuom))='MEQ/L')
                               OR (p.concept='creatinine' AND upper(trim(p.valueuom))='MG/DL')))
               AS latest_available_expected_unit_finite_rows,
           count(*) FILTER (WHERE p.charttime=t.latest_available_time
                             AND p.storetime<=p.anchor_time AND p.valuenum IS NULL)
               AS latest_available_missing_value_rows,
           count(*) FILTER (WHERE p.charttime=t.latest_available_time
                             AND p.storetime<=p.anchor_time
                             AND p.valuenum::text IN ('NaN','Infinity','-Infinity'))
               AS latest_available_nonfinite_rows,
           count(*) FILTER (WHERE p.charttime=t.latest_available_time
                             AND p.storetime<=p.anchor_time
                             AND nullif(trim(p.valueuom),'') IS NULL)
               AS latest_available_missing_unit_rows,
           count(*) FILTER (WHERE p.charttime=t.latest_available_time
                             AND p.storetime<=p.anchor_time
                             AND nullif(trim(p.valueuom),'') IS NOT NULL
                             AND NOT ((p.concept='potassium' AND upper(trim(p.valueuom))='MEQ/L')
                               OR (p.concept='creatinine' AND upper(trim(p.valueuom))='MG/DL')))
               AS latest_available_other_unit_rows,
           count(DISTINCT p.itemid) FILTER
             (WHERE p.charttime=t.latest_available_time AND p.storetime<=p.anchor_time)
               AS latest_available_distinct_itemids,
           count(DISTINCT upper(trim(p.valueuom))) FILTER
             (WHERE p.charttime=t.latest_available_time AND p.storetime<=p.anchor_time
                AND nullif(trim(p.valueuom),'') IS NOT NULL)
               AS latest_available_distinct_units
    FROM pre_labs p JOIN pre_times t USING (emar_id,concept)
    GROUP BY p.emar_id,p.concept
), candidate_concepts AS MATERIALIZED (
    SELECT a.emar_id,c.concept FROM candidate_anchors a
    CROSS JOIN (VALUES ('potassium'::text),('creatinine'::text)) c(concept)
), pre_events AS MATERIALIZED (
    SELECT a.emar_id,a.concept,
           coalesce(c.window_rows,0) AS window_rows,
           coalesce(c.available_rows,0) AS available_rows,
           coalesce(c.delayed_rows,0) AS delayed_rows,
           coalesce(c.missing_storetime_rows,0) AS missing_storetime_rows,
           coalesce(c.reversed_storetime_rows,0) AS reversed_storetime_rows,
           coalesce(c.latest_sample_rows,0) AS latest_sample_rows,
           coalesce(c.latest_available_rows,0) AS latest_available_rows,
           coalesce(c.latest_available_finite_rows,0) AS latest_available_finite_rows,
           coalesce(c.latest_available_expected_unit_finite_rows,0)
             AS latest_available_expected_unit_finite_rows,
           coalesce(c.latest_available_missing_value_rows,0)
             AS latest_available_missing_value_rows,
           coalesce(c.latest_available_nonfinite_rows,0) AS latest_available_nonfinite_rows,
           coalesce(c.latest_available_missing_unit_rows,0) AS latest_available_missing_unit_rows,
           coalesce(c.latest_available_other_unit_rows,0) AS latest_available_other_unit_rows,
           coalesce(c.latest_available_distinct_itemids,0) AS latest_available_distinct_itemids,
           coalesce(c.latest_available_distinct_units,0) AS latest_available_distinct_units,
           CASE WHEN coalesce(c.window_rows,0)=0 THEN 'no_window_sample'
                WHEN coalesce(c.available_rows,0)=0
                  THEN 'window_sample_none_available_by_anchor'
                WHEN coalesce(c.latest_available_finite_rows,0)=0
                  THEN 'latest_available_no_finite_value'
                ELSE 'latest_available_has_finite_value' END AS pre_lab_status
    FROM candidate_concepts a LEFT JOIN pre_counts c USING (emar_id,concept)
), common_post_times AS MATERIALIZED (
    SELECT a.emar_id,a.subject_id,a.hadm_id,a.charttime AS anchor_time,
           (SELECT l.charttime FROM mimiciv_hosp.labevents l
            WHERE l.subject_id=a.subject_id AND l.hadm_id=a.hadm_id
              AND l.itemid=50971 AND l.charttime>a.charttime
            ORDER BY l.charttime LIMIT 1) AS common_next_time
    FROM candidate_anchors a
), rare_post_times AS MATERIALIZED (
    SELECT a.emar_id,min(l.charttime) AS rare_next_time
    FROM candidate_anchors a LEFT JOIN rare_labs l
      ON l.subject_id=a.subject_id AND l.hadm_id=a.hadm_id
     AND l.itemid=52610 AND l.charttime>a.charttime
    GROUP BY a.emar_id
), post_times AS MATERIALIZED (
    SELECT c.emar_id,c.subject_id,c.hadm_id,c.anchor_time,
           CASE WHEN c.common_next_time IS NULL THEN r.rare_next_time
                WHEN r.rare_next_time IS NULL THEN c.common_next_time
                ELSE least(c.common_next_time,r.rare_next_time) END AS next_sample_time
    FROM common_post_times c JOIN rare_post_times r USING (emar_id)
), common_post_labs AS MATERIALIZED (
    SELECT p.emar_id,p.anchor_time,p.next_sample_time,l.labevent_id,l.itemid,
           l.charttime,l.storetime,l.valuenum,l.valueuom
    FROM post_times p CROSS JOIN LATERAL (
        SELECT labevent_id,itemid,charttime,storetime,valuenum,valueuom
        FROM mimiciv_hosp.labevents l
        WHERE l.subject_id=p.subject_id AND l.hadm_id=p.hadm_id
          AND l.itemid=50971 AND l.charttime=p.next_sample_time OFFSET 0
    ) l
), rare_post_labs AS MATERIALIZED (
    SELECT p.emar_id,p.anchor_time,p.next_sample_time,l.labevent_id,l.itemid,
           l.charttime,l.storetime,l.valuenum,l.valueuom
    FROM post_times p JOIN rare_labs l
      ON l.subject_id=p.subject_id AND l.hadm_id=p.hadm_id
     AND l.itemid=52610 AND l.charttime=p.next_sample_time
), post_labs AS MATERIALIZED (
    SELECT * FROM common_post_labs
    UNION ALL
    SELECT * FROM rare_post_labs
), post_counts AS MATERIALIZED (
    SELECT emar_id,
           count(*) AS lab_rows,
           count(*) FILTER (WHERE valuenum IS NOT NULL
              AND valuenum::text NOT IN ('NaN','Infinity','-Infinity')) AS finite_rows,
           count(*) FILTER (WHERE valuenum IS NOT NULL
              AND valuenum::text NOT IN ('NaN','Infinity','-Infinity')
              AND upper(trim(valueuom))='MEQ/L') AS expected_unit_finite_rows,
           count(*) FILTER (WHERE valuenum IS NULL) AS missing_value_rows,
           count(*) FILTER (WHERE valuenum::text IN ('NaN','Infinity','-Infinity'))
              AS nonfinite_rows,
           count(*) FILTER (WHERE nullif(trim(valueuom),'') IS NULL) AS missing_unit_rows,
           count(*) FILTER (WHERE nullif(trim(valueuom),'') IS NOT NULL
              AND upper(trim(valueuom))<>'MEQ/L') AS other_unit_rows,
           count(*) FILTER (WHERE storetime IS NULL) AS missing_storetime_rows,
           count(*) FILTER (WHERE storetime<charttime) AS reversed_storetime_rows,
           count(DISTINCT itemid) AS distinct_itemids,
           count(DISTINCT upper(trim(valueuom))) FILTER
             (WHERE nullif(trim(valueuom),'') IS NOT NULL) AS distinct_units
    FROM post_labs GROUP BY emar_id
), post_events AS MATERIALIZED (
    SELECT a.emar_id,t.next_sample_time,
           coalesce(c.lab_rows,0) AS lab_rows,
           coalesce(c.finite_rows,0) AS finite_rows,
           coalesce(c.expected_unit_finite_rows,0) AS expected_unit_finite_rows,
           coalesce(c.missing_value_rows,0) AS missing_value_rows,
           coalesce(c.nonfinite_rows,0) AS nonfinite_rows,
           coalesce(c.missing_unit_rows,0) AS missing_unit_rows,
           coalesce(c.other_unit_rows,0) AS other_unit_rows,
           coalesce(c.missing_storetime_rows,0) AS missing_storetime_rows,
           coalesce(c.reversed_storetime_rows,0) AS reversed_storetime_rows,
           coalesce(c.distinct_itemids,0) AS distinct_itemids,
           coalesce(c.distinct_units,0) AS distinct_units,
           CASE WHEN t.next_sample_time IS NULL OR coalesce(c.lab_rows,0)=0
                  THEN 'no_post_anchor_sample'
                WHEN coalesce(c.finite_rows,0)=0
                  THEN 'first_timestamp_no_finite_value'
                ELSE 'first_timestamp_has_finite_value' END AS post_k_status,
           CASE WHEN t.next_sample_time IS NULL THEN 'no_post_anchor_sample'
                WHEN t.next_sample_time<=a.charttime+interval '3 hours' THEN '(0,3]h'
                WHEN t.next_sample_time<=a.charttime+interval '6 hours' THEN '(3,6]h'
                WHEN t.next_sample_time<=a.charttime+interval '24 hours' THEN '(6,24]h'
                ELSE '>24h' END AS lag_bucket
    FROM candidate_anchors a JOIN post_times t USING (emar_id)
    LEFT JOIN post_counts c USING (emar_id)
), intersection_base AS MATERIALIZED (
    SELECT a.emar_id,a.subject_id,a.hadm_id,a.product_component_sum_meq,
           a.component_sum_bucket,a.component_structure,a.completeness_evidence,
           a.paper_action_relation,p.anchor_point_status,w.pre4h_window_status,
           k.pre_lab_status AS pre_k_status,k.window_rows AS pre_k_window_rows,
           k.available_rows AS pre_k_available_rows,
           k.latest_available_rows AS pre_k_latest_rows,
           k.latest_available_finite_rows AS pre_k_finite_rows,
           k.latest_available_expected_unit_finite_rows AS pre_k_expected_finite_rows,
           k.latest_sample_rows AS pre_k_latest_sample_rows,
           k.delayed_rows AS pre_k_delayed_rows,
           k.missing_storetime_rows AS pre_k_missing_storetime_rows,
           k.reversed_storetime_rows AS pre_k_reversed_storetime_rows,
           k.latest_available_missing_value_rows AS pre_k_missing_value_rows,
           k.latest_available_nonfinite_rows AS pre_k_nonfinite_rows,
           k.latest_available_missing_unit_rows AS pre_k_missing_unit_rows,
           k.latest_available_other_unit_rows AS pre_k_other_unit_rows,
           k.latest_available_distinct_itemids AS pre_k_distinct_itemids,
           k.latest_available_distinct_units AS pre_k_distinct_units,
           r.pre_lab_status AS pre_creatinine_status,
           r.window_rows AS pre_creatinine_window_rows,
           r.available_rows AS pre_creatinine_available_rows,
           r.latest_available_rows AS pre_creatinine_latest_rows,
           r.latest_available_finite_rows AS pre_creatinine_finite_rows,
           r.latest_available_expected_unit_finite_rows AS pre_creatinine_expected_finite_rows,
           r.latest_sample_rows AS pre_creatinine_latest_sample_rows,
           r.delayed_rows AS pre_creatinine_delayed_rows,
           r.missing_storetime_rows AS pre_creatinine_missing_storetime_rows,
           r.reversed_storetime_rows AS pre_creatinine_reversed_storetime_rows,
           r.latest_available_missing_value_rows AS pre_creatinine_missing_value_rows,
           r.latest_available_nonfinite_rows AS pre_creatinine_nonfinite_rows,
           r.latest_available_missing_unit_rows AS pre_creatinine_missing_unit_rows,
           r.latest_available_other_unit_rows AS pre_creatinine_other_unit_rows,
           r.latest_available_distinct_itemids AS pre_creatinine_distinct_itemids,
           r.latest_available_distinct_units AS pre_creatinine_distinct_units,
           o.post_k_status,o.lag_bucket,o.lab_rows AS post_k_rows,
           o.finite_rows AS post_k_finite_rows,
           o.expected_unit_finite_rows AS post_k_expected_finite_rows,
           o.missing_value_rows AS post_k_missing_value_rows,
           o.nonfinite_rows AS post_k_nonfinite_rows,
           o.missing_unit_rows AS post_k_missing_unit_rows,
           o.other_unit_rows AS post_k_other_unit_rows,
           o.missing_storetime_rows AS post_k_missing_storetime_rows,
           o.reversed_storetime_rows AS post_k_reversed_storetime_rows,
           o.distinct_itemids AS post_k_distinct_itemids,
           o.distinct_units AS post_k_distinct_units
    FROM candidate_anchors a JOIN anchor_points p USING (emar_id)
    JOIN window_locations w USING (emar_id)
    JOIN pre_events k ON k.emar_id=a.emar_id AND k.concept='potassium'
    JOIN pre_events r ON r.emar_id=a.emar_id AND r.concept='creatinine'
    JOIN post_events o ON o.emar_id=a.emar_id
), intersection_flags AS MATERIALIZED (
    SELECT *,
           paper_action_relation='matches_positive_paper_action_value' AS paper_value_ok,
           anchor_point_status='non_icu_provisional' AS anchor_point_ok,
           pre4h_window_status='complete_single_named_non_icu_provisional' AS pre4h_ok,
           pre_k_window_rows>0 AS pre_k_window_ok,
           pre_k_available_rows>0 AS pre_k_available_ok,
           pre_k_finite_rows>0 AS pre_k_finite_ok,
           pre_creatinine_window_rows>0 AS pre_creatinine_window_ok,
           pre_creatinine_available_rows>0 AS pre_creatinine_available_ok,
           pre_creatinine_finite_rows>0 AS pre_creatinine_finite_ok,
           post_k_rows>0 AS post_k_sample_ok,
           post_k_finite_rows>0 AS post_k_finite_ok
    FROM intersection_base
), intersection AS MATERIALIZED (
    SELECT *,CASE
      WHEN NOT paper_value_ok THEN 'outside_positive_paper_action_values'
      WHEN NOT anchor_point_ok THEN 'anchor_point_not_non_icu_provisional'
      WHEN NOT pre4h_ok THEN 'pre4h_window_not_complete_single_named_non_icu_provisional'
      WHEN NOT pre_k_window_ok THEN 'pre_k_no_window_sample'
      WHEN NOT pre_k_available_ok THEN 'pre_k_none_available_by_anchor'
      WHEN NOT pre_k_finite_ok THEN 'pre_k_latest_available_no_finite_value'
      WHEN NOT pre_creatinine_window_ok THEN 'pre_creatinine_no_window_sample'
      WHEN NOT pre_creatinine_available_ok THEN 'pre_creatinine_none_available_by_anchor'
      WHEN NOT pre_creatinine_finite_ok THEN 'pre_creatinine_latest_available_no_finite_value'
      WHEN NOT post_k_sample_ok THEN 'no_post_anchor_k_sample'
      WHEN NOT post_k_finite_ok THEN 'first_post_anchor_k_timestamp_no_finite_value'
      ELSE 'clear_under_diagnostic_any_finite_intersection' END AS first_blocker
    FROM intersection_flags
), flow_stages(stage_order,stage_name) AS (
    VALUES (1,'source_dose_candidate'),
           (2,'matches_positive_paper_action_value'),
           (3,'anchor_and_pre4h_non_icu_diagnostics'),
           (4,'pre_k_window_sample'),
           (5,'pre_k_available_by_anchor'),
           (6,'pre_k_latest_available_has_finite_value'),
           (7,'pre_creatinine_window_sample'),
           (8,'pre_creatinine_available_by_anchor'),
           (9,'pre_creatinine_latest_available_has_finite_value'),
           (10,'post_anchor_k_timestamp'),
           (11,'first_post_anchor_k_timestamp_has_finite_value')
), flow_memberships AS MATERIALIZED (
    SELECT s.stage_order,s.stage_name,i.emar_id,i.subject_id,i.hadm_id,
           CASE s.stage_order
             WHEN 1 THEN true
             WHEN 2 THEN i.paper_value_ok
             WHEN 3 THEN i.paper_value_ok AND i.anchor_point_ok AND i.pre4h_ok
             WHEN 4 THEN i.paper_value_ok AND i.anchor_point_ok AND i.pre4h_ok
                           AND i.pre_k_window_ok
             WHEN 5 THEN i.paper_value_ok AND i.anchor_point_ok AND i.pre4h_ok
                           AND i.pre_k_window_ok AND i.pre_k_available_ok
             WHEN 6 THEN i.paper_value_ok AND i.anchor_point_ok AND i.pre4h_ok
                           AND i.pre_k_window_ok AND i.pre_k_available_ok AND i.pre_k_finite_ok
             WHEN 7 THEN i.paper_value_ok AND i.anchor_point_ok AND i.pre4h_ok
                           AND i.pre_k_window_ok AND i.pre_k_available_ok AND i.pre_k_finite_ok
                           AND i.pre_creatinine_window_ok
             WHEN 8 THEN i.paper_value_ok AND i.anchor_point_ok AND i.pre4h_ok
                           AND i.pre_k_window_ok AND i.pre_k_available_ok AND i.pre_k_finite_ok
                           AND i.pre_creatinine_window_ok AND i.pre_creatinine_available_ok
             WHEN 9 THEN i.paper_value_ok AND i.anchor_point_ok AND i.pre4h_ok
                           AND i.pre_k_window_ok AND i.pre_k_available_ok AND i.pre_k_finite_ok
                           AND i.pre_creatinine_window_ok AND i.pre_creatinine_available_ok
                           AND i.pre_creatinine_finite_ok
             WHEN 10 THEN i.paper_value_ok AND i.anchor_point_ok AND i.pre4h_ok
                           AND i.pre_k_window_ok AND i.pre_k_available_ok AND i.pre_k_finite_ok
                           AND i.pre_creatinine_window_ok AND i.pre_creatinine_available_ok
                           AND i.pre_creatinine_finite_ok AND i.post_k_sample_ok
             WHEN 11 THEN i.paper_value_ok AND i.anchor_point_ok AND i.pre4h_ok
                           AND i.pre_k_window_ok AND i.pre_k_available_ok AND i.pre_k_finite_ok
                           AND i.pre_creatinine_window_ok AND i.pre_creatinine_available_ok
                           AND i.pre_creatinine_finite_ok AND i.post_k_sample_ok
                           AND i.post_k_finite_ok
           END AS passes
    FROM flow_stages s CROSS JOIN intersection i
), profiles AS (
    SELECT 'candidate_intersection_summary'::text AS profile_section,
           jsonb_build_object(
             'selection','194 provisional source-dose candidates in the same fixed SYSTEM 1% page sample',
             'intersection_semantics','single-statement event-level diagnostic') AS dimensions,
           count(*) AS source_rows,count(DISTINCT emar_id) AS emar_events,
           jsonb_build_object(
             'sampled_emar_rows',(SELECT count(*) FROM sampled),
             'selected_potassium_heads',(SELECT count(*) FROM events),
             'source_candidate_events',(SELECT count(*) FROM candidate_anchors),
             'intersection_events',count(*),
             'source_candidates_missing_intersection',
                (SELECT count(*) FROM candidate_anchors)-count(*),
             'candidate_distinct_subjects',count(DISTINCT subject_id),
             'candidate_distinct_admissions',count(DISTINCT (subject_id,hadm_id)),
             'matches_positive_paper_action_value_events',count(*) FILTER (WHERE paper_value_ok),
             'outside_positive_paper_action_value_events',count(*) FILTER (WHERE NOT paper_value_ok),
             'explicit_negative_parent_flag_events',count(*) FILTER
                (WHERE completeness_evidence='explicit_negative_parent_flags'),
             'unknown_completeness_events',count(*) FILTER
                (WHERE completeness_evidence<>'explicit_negative_parent_flags'),
             'stage_03_location_events',count(*) FILTER
                (WHERE paper_value_ok AND anchor_point_ok AND pre4h_ok),
             'stage_04_pre_k_window_events',count(*) FILTER
                (WHERE paper_value_ok AND anchor_point_ok AND pre4h_ok AND pre_k_window_ok),
             'stage_05_pre_k_available_events',count(*) FILTER
                (WHERE paper_value_ok AND anchor_point_ok AND pre4h_ok
                   AND pre_k_window_ok AND pre_k_available_ok),
             'stage_06_pre_k_finite_events',count(*) FILTER
                (WHERE paper_value_ok AND anchor_point_ok AND pre4h_ok
                   AND pre_k_window_ok AND pre_k_available_ok AND pre_k_finite_ok),
             'stage_09_both_pre_labs_finite_events',count(*) FILTER
                (WHERE paper_value_ok AND anchor_point_ok AND pre4h_ok
                   AND pre_k_window_ok AND pre_k_available_ok AND pre_k_finite_ok
                   AND pre_creatinine_window_ok AND pre_creatinine_available_ok
                   AND pre_creatinine_finite_ok),
             'stage_11_diagnostic_any_finite_intersection_events',count(*) FILTER
                (WHERE paper_value_ok AND anchor_point_ok AND pre4h_ok
                   AND pre_k_window_ok AND pre_k_available_ok AND pre_k_finite_ok
                   AND pre_creatinine_window_ok AND pre_creatinine_available_ok
                   AND pre_creatinine_finite_ok AND post_k_sample_ok AND post_k_finite_ok),
             'all_three_lab_observations_unique_finite_expected_unit_events',count(*) FILTER
                (WHERE pre_k_latest_rows=1 AND pre_k_expected_finite_rows=1
                   AND pre_creatinine_latest_rows=1 AND pre_creatinine_expected_finite_rows=1
                   AND post_k_rows=1 AND post_k_expected_finite_rows=1)) AS counters
    FROM intersection
    UNION ALL
    SELECT 'candidate_diagnostic_flow',
           jsonb_build_object('stage_order',s.stage_order,'stage_name',s.stage_name,
                              'diagnostic_only',true),
           count(f.emar_id) FILTER (WHERE f.passes),
           count(DISTINCT f.emar_id) FILTER (WHERE f.passes),
           jsonb_build_object(
             'distinct_subjects',count(DISTINCT f.subject_id) FILTER (WHERE f.passes),
             'distinct_admissions',count(DISTINCT (f.subject_id,f.hadm_id))
                FILTER (WHERE f.passes),
             'nested_cumulative',true)
    FROM flow_stages s LEFT JOIN flow_memberships f
      ON f.stage_order=s.stage_order AND f.stage_name=s.stage_name
    GROUP BY s.stage_order,s.stage_name
    UNION ALL
    SELECT 'candidate_first_blocker',
           jsonb_build_object('diagnostic_flow_status',first_blocker),
           count(*),count(DISTINCT emar_id),
           jsonb_build_object(
             'distinct_subjects',count(DISTINCT subject_id),
             'distinct_admissions',count(DISTINCT (subject_id,hadm_id)),
             'explicit_negative_parent_flag_events',count(*) FILTER
                (WHERE completeness_evidence='explicit_negative_parent_flags'),
             'unknown_completeness_events',count(*) FILTER
                (WHERE completeness_evidence<>'explicit_negative_parent_flags'),
             'first_blocker_is_mutually_exclusive',true)
    FROM intersection GROUP BY first_blocker
    UNION ALL
    SELECT 'candidate_intersection_matrix',
           jsonb_build_object(
             'completeness_evidence',completeness_evidence,
             'paper_action_relation',paper_action_relation,
             'component_sum_bucket',component_sum_bucket,
             'component_structure',component_structure,
             'anchor_point_status',anchor_point_status,
             'pre4h_window_status',pre4h_window_status,
             'pre_k_status',pre_k_status,
             'pre_creatinine_status',pre_creatinine_status,
             'post_k_status',post_k_status,
             'post_k_lag_bucket',lag_bucket),
           count(*),count(DISTINCT emar_id),
           jsonb_build_object(
             'distinct_subjects',count(DISTINCT subject_id),
             'distinct_admissions',count(DISTINCT (subject_id,hadm_id)),
             'pre_k_latest_tie_events',count(*) FILTER (WHERE pre_k_latest_rows>1),
             'pre_creatinine_latest_tie_events',count(*) FILTER
                (WHERE pre_creatinine_latest_rows>1),
             'post_k_first_timestamp_tie_events',count(*) FILTER (WHERE post_k_rows>1),
             'pre_k_unique_finite_expected_unit_events',count(*) FILTER
                (WHERE pre_k_latest_rows=1 AND pre_k_expected_finite_rows=1),
             'pre_creatinine_unique_finite_expected_unit_events',count(*) FILTER
                (WHERE pre_creatinine_latest_rows=1 AND pre_creatinine_expected_finite_rows=1),
             'post_k_unique_finite_expected_unit_events',count(*) FILTER
                (WHERE post_k_rows=1 AND post_k_expected_finite_rows=1))
    FROM intersection
    GROUP BY completeness_evidence,paper_action_relation,component_sum_bucket,
             component_structure,anchor_point_status,pre4h_window_status,
             pre_k_status,pre_creatinine_status,post_k_status,lag_bucket
    UNION ALL
    SELECT 'candidate_pre_anchor_lab_shape',
           jsonb_build_object(
             'concept',e.concept,
             'pre_lab_status',e.pre_lab_status,
             'completeness_evidence',a.completeness_evidence,
             'paper_action_relation',a.paper_action_relation,
             'latest_available_has_ties',e.latest_available_rows>1,
             'latest_available_has_any_finite',e.latest_available_finite_rows>0,
             'latest_available_has_expected_unit_finite',
                e.latest_available_expected_unit_finite_rows>0,
             'latest_available_is_unique_finite_expected_unit',
                e.latest_available_rows=1
                AND e.latest_available_expected_unit_finite_rows=1),
           count(*),count(DISTINCT e.emar_id),
           jsonb_build_object(
             'distinct_subjects',count(DISTINCT a.subject_id),
             'distinct_admissions',count(DISTINCT (a.subject_id,a.hadm_id)),
             'window_lab_rows',sum(e.window_rows),
             'available_by_anchor_rows',sum(e.available_rows),
             'delayed_after_anchor_rows',sum(e.delayed_rows),
             'missing_storetime_rows',sum(e.missing_storetime_rows),
             'storetime_before_sample_rows',sum(e.reversed_storetime_rows),
             'latest_sample_rows',sum(e.latest_sample_rows),
             'latest_available_rows',sum(e.latest_available_rows),
             'latest_available_finite_rows',sum(e.latest_available_finite_rows),
             'latest_available_expected_unit_finite_rows',
                sum(e.latest_available_expected_unit_finite_rows),
             'latest_available_missing_value_rows',sum(e.latest_available_missing_value_rows),
             'latest_available_nonfinite_rows',sum(e.latest_available_nonfinite_rows),
             'latest_available_missing_unit_rows',sum(e.latest_available_missing_unit_rows),
             'latest_available_other_unit_rows',sum(e.latest_available_other_unit_rows),
             'latest_available_distinct_itemid_total',sum(e.latest_available_distinct_itemids),
             'latest_available_distinct_unit_total',sum(e.latest_available_distinct_units))
    FROM pre_events e JOIN candidate_anchors a USING (emar_id)
    GROUP BY e.concept,e.pre_lab_status,a.completeness_evidence,a.paper_action_relation,
             e.latest_available_rows>1,e.latest_available_finite_rows>0,
             e.latest_available_expected_unit_finite_rows>0,
             e.latest_available_rows=1 AND e.latest_available_expected_unit_finite_rows=1
    UNION ALL
    SELECT 'candidate_post_anchor_k_shape',
           jsonb_build_object(
             'post_k_status',e.post_k_status,
             'lag_bucket',e.lag_bucket,
             'completeness_evidence',a.completeness_evidence,
             'paper_action_relation',a.paper_action_relation,
             'first_timestamp_has_ties',e.lab_rows>1,
             'first_timestamp_has_any_finite',e.finite_rows>0,
             'first_timestamp_has_expected_unit_finite',e.expected_unit_finite_rows>0,
             'first_timestamp_is_unique_finite_expected_unit',
                e.lab_rows=1 AND e.expected_unit_finite_rows=1),
           count(*),count(DISTINCT e.emar_id),
           jsonb_build_object(
             'distinct_subjects',count(DISTINCT a.subject_id),
             'distinct_admissions',count(DISTINCT (a.subject_id,a.hadm_id)),
             'first_timestamp_lab_rows',sum(e.lab_rows),
             'finite_value_rows',sum(e.finite_rows),
             'expected_unit_finite_rows',sum(e.expected_unit_finite_rows),
             'missing_value_rows',sum(e.missing_value_rows),
             'nonfinite_value_rows',sum(e.nonfinite_rows),
             'missing_unit_rows',sum(e.missing_unit_rows),
             'other_unit_rows',sum(e.other_unit_rows),
             'missing_storetime_rows',sum(e.missing_storetime_rows),
             'storetime_before_sample_rows',sum(e.reversed_storetime_rows),
             'distinct_itemid_total',sum(e.distinct_itemids),
             'distinct_unit_total',sum(e.distinct_units))
    FROM post_events e JOIN candidate_anchors a USING (emar_id)
    GROUP BY e.post_k_status,e.lag_bucket,a.completeness_evidence,a.paper_action_relation,
             e.lab_rows>1,e.finite_rows>0,e.expected_unit_finite_rows>0,
             e.lab_rows=1 AND e.expected_unit_finite_rows=1
)
SELECT profile_section,dimensions,source_rows,emar_events,
       counters || jsonb_build_object(
         'system_sample_percent',1.0,
         'sample_seed',20261011,
         'page_sample_is_representative',false,
         'event_intersection_key','same emar_id with matching non-null subject_id and hadm_id',
         'charttime_semantics','administration-record anchor; not validated infusion start',
         'lab_availability_semantics','pre-anchor storetime at or before anchor; selected time precedes finite-value and unit checks',
         'post_k_semantics','first specimen timestamp strictly after charttime anchor; no maximum lag; not post-infusion',
         'expected_unit_diagnostic','potassium mEq/L; creatinine mg/dL; no unit conversion applied',
         'diagnostic_flow_uses_any_finite_value',true,
         'diagnostic_flow_requires_unique_selected_row',false,
         'diagnostic_flow_requires_expected_unit',false,
         'diagnostic_flow_excludes_reversed_storetime',false,
         'formal_cohort',false,
         'formal_non_icu_rule',false,
         'formal_action_mapping',false,
         'source_candidate_is_actual_action',false,
         'provisional_is_actual_dose',false,
         'actual_dose_defined',false,
         'zero_action_constructed',false,
         'formal_feature_rule',false,
         'formal_label_rule',false,
         'observed_treatment_start_defined',false,
         'observed_treatment_end_defined',false) AS counters
FROM profiles
ORDER BY profile_section,source_rows DESC,dimensions;
