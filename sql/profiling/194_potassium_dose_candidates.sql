-- Audit-only potassium component-dose candidates. This query uses the same
-- fixed 1% eMAR page sample and two exact trimmed medication names as 191/192.
-- A candidate is not an observed action: no result here resolves treatment
-- completion, episode merging, non-ICU eligibility, labels, or action mapping.
--
-- dose_due is kept as the parent planned amount. Product dose_given values are
-- summed only when every product is numeric mEq. The sum is never replaced by
-- MAX, SUM(DISTINCT), rounding, capping, or truncation. Description strength x
-- product amount is only an internal consistency check against the finite 192
-- vocabulary; it is not external label/NDC verification or delivered volume.
--
-- Missing completeness flags are not negative flags. A provisional candidate
-- may have unknown completeness, but its status says so explicitly and never
-- calls the event complete. IV route evidence cannot override an enteral TAB/PKT
-- product form, and every component must be strictly positive. Raw IDs, times,
-- free text, codes, ordinals and dose strings are not emitted; all outputs are
-- aggregate controlled categories.
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
), issue_rows AS MATERIALIZED (
    SELECT c.emar_id, c.subject_id, c.hadm_id, issue.issue_reason
    FROM classified c CROSS JOIN LATERAL (VALUES
        ('non_administered_status', c.event_status_class <> 'administered'),
        ('affirmative_incomplete_or_remainder',
            c.parent_incomplete_affirmative_rows > 0
            OR c.parent_remainder_affirmative_rows > 0),
        ('product_completion_flag_anomaly', c.product_completion_flag_rows > 0),
        ('identity_issue', c.identity_issue),
        ('time_issue', c.time_issue),
        ('route_not_explicit_iv_only', c.route_pattern <> 'explicit_iv_only'),
        ('enteral_product_form_conflict', c.route_pattern = 'explicit_iv_only'
            AND c.enteral_product_form_rows > 0),
        ('pharmacy_linkage_issue', c.pharmacy_issue),
        ('parent_structure_issue', c.parent_rows <> 1),
        ('product_structure_issue', c.product_structure_issue),
        ('parent_due_non_numeric_or_non_meq', c.parent_due_numeric_meq_rows <> 1),
        ('component_non_numeric_or_non_meq', c.product_numeric_meq_rows <> c.product_rows),
        ('parent_due_component_sum_mismatch',
            c.parent_due_numeric_meq_rows = 1
            AND c.product_rows > 0
            AND c.product_numeric_meq_rows = c.product_rows
            AND c.parent_due_meq <> c.product_component_sum_meq),
        ('component_internal_consistency_failed', c.product_inconsistent_rows > 0),
        ('component_internal_consistency_unresolved',
            c.product_rows > 0 AND c.product_consistent_rows <> c.product_rows
            AND c.product_inconsistent_rows = 0),
        ('completeness_unknown', c.completeness_evidence IN
            ('unknown_unrecognized_parent_token', 'unknown_missing_or_partial_negative')),
        ('nonpositive_component_sum_not_zero_action',
            c.product_numeric_meq_rows = c.product_rows AND c.product_rows > 0
            AND c.product_component_sum_meq <= 0),
        ('nonpositive_component_present_not_zero_action',
            c.product_numeric_meq_rows = c.product_rows AND c.product_rows > 0
            AND c.nonpositive_product_component_rows > 0),
        ('component_sum_outside_positive_paper_action_values', c.paper_action_relation IN
            ('explicit_60_or_80_outside_paper_action_set',
             'other_positive_outside_paper_action_set'))
    ) issue(issue_reason, applies)
    WHERE issue.applies
), profiles AS (
    SELECT 'sample_summary'::text AS profile_section,
           '{}'::jsonb AS dimensions,
           count(*) AS source_rows, count(*) AS emar_events,
           jsonb_build_object(
               'sampled_emar_rows', (SELECT count(*) FROM sampled),
               'selected_emar_rows', count(*),
               'distinct_subjects', count(DISTINCT subject_id),
               'distinct_admissions', count(DISTINCT (subject_id, hadm_id)) FILTER
                   (WHERE subject_id IS NOT NULL AND hadm_id IS NOT NULL),
               'complete_detail_rows', (SELECT count(*) FROM details),
               'provisional_component_dose_candidates',
                   count(*) FILTER (WHERE provisional_component_dose_candidate),
               'provisional_candidate_distinct_subjects',
                   count(DISTINCT subject_id) FILTER
                     (WHERE provisional_component_dose_candidate
                        AND subject_id IS NOT NULL),
               'provisional_candidate_distinct_admissions',
                   count(DISTINCT (subject_id, hadm_id)) FILTER
                     (WHERE provisional_component_dose_candidate
                        AND subject_id IS NOT NULL AND hadm_id IS NOT NULL),
               'candidate_exact_paper_positive_events',
                   count(*) FILTER
                     (WHERE provisional_component_dose_candidate
                        AND product_component_sum_meq IN (10, 20, 40)),
               'candidate_exact_paper_positive_distinct_subjects',
                   count(DISTINCT subject_id) FILTER
                     (WHERE provisional_component_dose_candidate
                        AND product_component_sum_meq IN (10, 20, 40)
                        AND subject_id IS NOT NULL),
               'candidate_exact_paper_positive_distinct_admissions',
                   count(DISTINCT (subject_id, hadm_id)) FILTER
                     (WHERE provisional_component_dose_candidate
                        AND product_component_sum_meq IN (10, 20, 40)
                        AND subject_id IS NOT NULL AND hadm_id IS NOT NULL),
               'candidate_outside_paper_positive_events',
                   count(*) FILTER
                     (WHERE provisional_component_dose_candidate
                        AND product_component_sum_meq > 0
                        AND product_component_sum_meq NOT IN (10, 20, 40)),
               'candidate_with_explicit_negative_parent_flags',
                   count(*) FILTER (WHERE provisional_component_dose_candidate
                     AND completeness_evidence = 'explicit_negative_parent_flags'),
               'candidate_with_unknown_completeness',
                   count(*) FILTER (WHERE provisional_component_dose_candidate
                     AND completeness_evidence <> 'explicit_negative_parent_flags'),
               'single_product_candidates', count(*) FILTER
                   (WHERE provisional_component_dose_candidate AND product_rows = 1),
               'multiple_product_candidates', count(*) FILTER
                   (WHERE provisional_component_dose_candidate AND product_rows > 1),
               'events_with_parent_affirmative_incomplete', count(*) FILTER
                   (WHERE parent_incomplete_affirmative_rows > 0),
               'events_with_parent_affirmative_remainder', count(*) FILTER
                   (WHERE parent_remainder_affirmative_rows > 0),
               'events_with_product_completion_flag_anomaly', count(*) FILTER
                   (WHERE product_completion_flag_rows > 0),
               'events_with_product_due', count(*) FILTER (WHERE product_due_present_rows > 0),
               'events_with_missing_product_code', count(*) FILTER
                   (WHERE missing_product_code_rows > 0),
               'events_with_unmapped_product_description', count(*) FILTER
                   (WHERE unmapped_product_rows > 0),
               'events_with_iv_route_enteral_product_form_conflict', count(*) FILTER
                   (WHERE route_pattern = 'explicit_iv_only'
                      AND enteral_product_form_rows > 0),
               'events_with_nonpositive_product_component', count(*) FILTER
                   (WHERE nonpositive_product_component_rows > 0)
           ) AS counters
    FROM classified
    UNION ALL
    SELECT 'dose_candidate_status',
           jsonb_build_object(
               'source_dose_status', source_dose_status,
               'provisional_component_dose_candidate', provisional_component_dose_candidate,
               'completeness_evidence', completeness_evidence,
               'component_structure', component_structure,
               'component_sum_bucket', component_sum_bucket,
               'paper_action_relation', paper_action_relation),
           count(*), count(*),
           jsonb_build_object(
               'distinct_subjects', count(DISTINCT subject_id),
               'distinct_admissions', count(DISTINCT (subject_id, hadm_id)) FILTER
                   (WHERE subject_id IS NOT NULL AND hadm_id IS NOT NULL),
               'single_product_events', count(*) FILTER (WHERE product_rows = 1),
               'multiple_product_events', count(*) FILTER (WHERE product_rows > 1),
               'events_with_parent_due', count(*) FILTER (WHERE parent_due_present_rows > 0),
               'events_with_product_due', count(*) FILTER (WHERE product_due_present_rows > 0),
               'events_with_unmapped_product_description', count(*) FILTER
                   (WHERE unmapped_product_rows > 0),
               'events_with_missing_product_code', count(*) FILTER
                   (WHERE missing_product_code_rows > 0),
               'events_with_enteral_product_form', count(*) FILTER
                   (WHERE enteral_product_form_rows > 0),
               'events_with_nonpositive_product_component', count(*) FILTER
                   (WHERE nonpositive_product_component_rows > 0)
           )
    FROM classified
    GROUP BY source_dose_status, provisional_component_dose_candidate,
             completeness_evidence, component_structure, component_sum_bucket,
             paper_action_relation
    UNION ALL
    SELECT 'dose_evidence_shape',
           jsonb_build_object(
               'event_status_class', event_status_class,
               'route_pattern', route_pattern,
               'parent_due_bucket', parent_due_bucket,
               'component_sum_bucket', component_sum_bucket,
               'component_structure', component_structure,
               'parent_due_vs_component_sum', parent_due_vs_component_sum,
               'component_internal_consistency', component_internal_consistency,
               'completeness_evidence', completeness_evidence),
           count(*), count(*),
           jsonb_build_object(
               'distinct_subjects', count(DISTINCT subject_id),
               'distinct_admissions', count(DISTINCT (subject_id, hadm_id)) FILTER
                   (WHERE subject_id IS NOT NULL AND hadm_id IS NOT NULL),
               'events_with_identity_issue', count(*) FILTER (WHERE identity_issue),
               'events_with_time_issue', count(*) FILTER (WHERE time_issue),
               'events_with_pharmacy_issue', count(*) FILTER (WHERE pharmacy_issue),
               'events_with_product_structure_issue', count(*) FILTER
                   (WHERE product_structure_issue),
               'events_with_iv_route_enteral_product_form_conflict', count(*) FILTER
                   (WHERE route_pattern = 'explicit_iv_only'
                      AND enteral_product_form_rows > 0),
               'events_with_nonpositive_product_component', count(*) FILTER
                   (WHERE nonpositive_product_component_rows > 0),
               'events_with_product_due', count(*) FILTER (WHERE product_due_present_rows > 0),
               'product_rows', sum(product_rows)
           )
    FROM classified
    GROUP BY event_status_class, route_pattern, parent_due_bucket,
             component_sum_bucket, component_structure,
             parent_due_vs_component_sum, component_internal_consistency,
             completeness_evidence
    UNION ALL
    SELECT 'candidate_issue', jsonb_build_object('issue_reason', issue_reason),
           count(*), count(*), jsonb_build_object(
               'distinct_subjects', count(DISTINCT subject_id),
               'distinct_admissions', count(DISTINCT (subject_id, hadm_id)) FILTER
                   (WHERE subject_id IS NOT NULL AND hadm_id IS NOT NULL),
               'issue_marginal_may_overlap_other_issues', true)
    FROM issue_rows GROUP BY issue_reason
)
SELECT profile_section, dimensions, source_rows, emar_events,
       counters || jsonb_build_object(
           'system_sample_percent', 1.0,
           'sample_seed', 20261011,
           'formal_action_mapping', false,
           'provisional_is_actual_dose', false,
           'dose_due_is_actual_dose', false,
           'component_sum_is_actual_dose', false,
           'description_amount_is_actual_dose', false,
           'non_icu_eligibility_applied', false,
           'episode_merge_applied', false,
           'label_eligibility_applied', false,
           'completion_rule',
             'parent Y/YES affirmative; parent N/NO on both fields explicit-negative; parent missing/other unknown; any product-row completion flag is a separate anomaly',
           'strength_evidence',
             'finite observed description vocabulary only; not external label or NDC verified',
           'product_form_rule',
             'TAB/PKT conflicts with explicit-IV-only evidence and blocks a provisional candidate',
           'component_positivity_rule',
             'every numeric mEq product component must be strictly positive; zero never creates an action',
           'dose_bucket_rule',
             'exact 10/20/40/60/80; all other numeric values remain other_numeric; no rounding/capping')
           AS counters
FROM profiles
ORDER BY profile_section, source_rows DESC, dimensions;
