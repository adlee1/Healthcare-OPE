-- D003 candidate record-chain and endpoint-signal audit only. The conservative
-- 194 component-dose rule is recomputed over the same fixed 1% eMAR page sample.
-- Each resulting candidate then opens complete eMAR streams by its validated
-- pharmacy_id and, only when every order identifier agrees, by a strict POE key.
-- Stream neighbors come from the full eMAR table, not from the page sample.
--
-- Previous, anchor, and next evidence are timestamp groups. Every simultaneous
-- row is retained; emar_id, emar_seq, storetime, and scheduletime never break a
-- clinical tie. The next group is the first strictly later linked timestamp even
-- when its status is Confirmed, another administration/start, nonterminal, or
-- unknown. This query never skips ahead to find a convenient Stopped record.
--
-- Prescription/pharmacy times, POE pointers, completion flags, rates, new-bag,
-- continuation, and restart fields remain diagnostics. No group becomes an
-- episode, observed start/end, duration, rate integral, actual action, label, or
-- formal cohort. Raw identifiers, timestamps, free text, and values are internal
-- only; all emitted rows are controlled aggregate categories.
WITH sampled AS MATERIALIZED (
    SELECT emar_id, emar_seq, subject_id, hadm_id, poe_id, pharmacy_id, medication,
           event_txt, charttime, scheduletime, storetime
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
        SELECT pharmacy_id, subject_id, hadm_id, poe_id, starttime, stoptime, route
        FROM mimiciv_hosp.pharmacy p
        WHERE p.pharmacy_id = k.pharmacy_id OFFSET 0
    ) p ON true
), prescriptions AS MATERIALIZED (
    SELECT p.* FROM pharmacy_keys k
    JOIN LATERAL (
        SELECT pharmacy_id, subject_id, hadm_id, poe_id, poe_seq, starttime, stoptime, route
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
    SELECT emar_id AS candidate_key, emar_seq AS candidate_sequence,
           subject_id, hadm_id, pharmacy_id,
           nullif(trim(poe_id), '') AS event_poe,
           charttime AS anchor_time, scheduletime AS scheduled_time,
           storetime AS recorded_time, product_component_sum_meq,
           component_sum_bucket, paper_action_relation,
           completeness_evidence
    FROM classified
    WHERE provisional_component_dose_candidate
), candidate_detail_role_shapes AS MATERIALIZED (
    SELECT c.candidate_key, c.subject_id, c.hadm_id,
           c.paper_action_relation, c.completeness_evidence,
           CASE WHEN d.parent_field_ordinal IS NULL
                THEN 'parent' ELSE 'product' END AS detail_role,
           count(*) AS detail_rows,
           count(*) FILTER (WHERE nullif(trim(d.completion_interval), '') IS NOT NULL)
               AS completion_interval_rows,
           count(DISTINCT nullif(trim(d.completion_interval), ''))
               AS completion_interval_distinct,
           count(*) FILTER (WHERE upper(trim(d.infusion_complete)) IN ('Y','YES'))
               AS infusion_complete_yes_rows,
           count(*) FILTER (WHERE upper(trim(d.infusion_complete)) IN ('N','NO'))
               AS infusion_complete_no_rows,
           count(*) FILTER (WHERE nullif(trim(d.infusion_complete), '') IS NOT NULL
                              AND upper(trim(d.infusion_complete)) NOT IN ('Y','YES','N','NO'))
               AS infusion_complete_other_rows,
           count(DISTINCT upper(trim(d.infusion_complete))) FILTER
               (WHERE nullif(trim(d.infusion_complete), '') IS NOT NULL)
               AS infusion_complete_distinct,
           count(*) FILTER (WHERE nullif(trim(d.infusion_rate), '') IS NOT NULL)
               AS infusion_rate_rows,
           count(*) FILTER (WHERE trim(d.infusion_rate) ~ '^[0-9]+([.][0-9]+)?$')
               AS infusion_rate_simple_numeric_rows,
           count(DISTINCT nullif(trim(d.infusion_rate), '')) AS infusion_rate_distinct,
           count(*) FILTER (WHERE nullif(trim(d.prior_infusion_rate), '') IS NOT NULL)
               AS prior_infusion_rate_rows,
           count(*) FILTER (WHERE trim(d.prior_infusion_rate) ~ '^[0-9]+([.][0-9]+)?$')
               AS prior_infusion_rate_simple_numeric_rows,
           count(DISTINCT nullif(trim(d.prior_infusion_rate), ''))
               AS prior_infusion_rate_distinct,
           count(*) FILTER (WHERE nullif(trim(d.infusion_rate_adjustment), '') IS NOT NULL)
               AS rate_adjustment_rows,
           count(*) FILTER (WHERE nullif(trim(d.infusion_rate_adjustment_amount), '') IS NOT NULL)
               AS rate_adjustment_amount_rows,
           count(*) FILTER (WHERE nullif(trim(d.infusion_rate_unit), '') IS NOT NULL)
               AS infusion_rate_unit_rows,
           count(DISTINCT nullif(upper(trim(d.infusion_rate_unit)), ''))
               AS infusion_rate_unit_distinct,
           count(*) FILTER (WHERE upper(trim(d.new_iv_bag_hung)) IN ('Y','YES'))
               AS new_bag_yes_rows,
           count(*) FILTER (WHERE upper(trim(d.continued_infusion_in_other_location))
                                  IN ('Y','YES'))
               AS continued_other_location_yes_rows,
           count(*) FILTER (WHERE nullif(trim(d.restart_interval), '') IS NOT NULL)
               AS restart_interval_rows
    FROM candidate_anchors c
    JOIN details d ON d.event_key = c.candidate_key
    GROUP BY c.candidate_key, c.subject_id, c.hadm_id,
             c.paper_action_relation, c.completeness_evidence,
             d.parent_field_ordinal IS NULL
), candidate_pharmacy_link_shapes AS MATERIALIZED (
    SELECT c.candidate_key,
           count(p.pharmacy_id) AS pharmacy_rows,
           count(p.pharmacy_id) FILTER
             (WHERE p.subject_id IS NOT DISTINCT FROM c.subject_id
                AND p.hadm_id IS NOT DISTINCT FROM c.hadm_id)
               AS identity_ok_rows,
           count(p.pharmacy_id) FILTER
             (WHERE p.subject_id IS DISTINCT FROM c.subject_id
                 OR p.hadm_id IS DISTINCT FROM c.hadm_id)
               AS identity_bad_rows,
           count(p.pharmacy_id) FILTER
             (WHERE p.subject_id IS NOT DISTINCT FROM c.subject_id
                AND p.hadm_id IS NOT DISTINCT FROM c.hadm_id
                AND nullif(trim(p.poe_id), '') IS NULL) AS identity_ok_missing_poe_rows,
           count(DISTINCT nullif(trim(p.poe_id), '')) FILTER
             (WHERE p.subject_id IS NOT DISTINCT FROM c.subject_id
                AND p.hadm_id IS NOT DISTINCT FROM c.hadm_id) AS identity_ok_distinct_poe,
           min(nullif(trim(p.poe_id), '')) FILTER
             (WHERE p.subject_id IS NOT DISTINCT FROM c.subject_id
                AND p.hadm_id IS NOT DISTINCT FROM c.hadm_id) AS identity_ok_poe,
           count(p.pharmacy_id) FILTER
             (WHERE p.subject_id IS NOT DISTINCT FROM c.subject_id
                AND p.hadm_id IS NOT DISTINCT FROM c.hadm_id
                AND nullif(trim(p.poe_id), '') IS NOT DISTINCT FROM c.event_poe)
               AS identity_ok_matching_event_poe_rows
    FROM candidate_anchors c
    LEFT JOIN pharmacies p ON p.pharmacy_id = c.pharmacy_id
    GROUP BY c.candidate_key
), candidate_rx_link_shapes AS MATERIALIZED (
    SELECT c.candidate_key,
           count(p.pharmacy_id) AS prescription_rows,
           count(p.pharmacy_id) FILTER
             (WHERE p.subject_id IS NOT DISTINCT FROM c.subject_id
                AND p.hadm_id IS NOT DISTINCT FROM c.hadm_id)
               AS identity_ok_rows,
           count(p.pharmacy_id) FILTER
             (WHERE p.subject_id IS DISTINCT FROM c.subject_id
                 OR p.hadm_id IS DISTINCT FROM c.hadm_id)
               AS identity_bad_rows,
           count(p.pharmacy_id) FILTER
             (WHERE p.subject_id IS NOT DISTINCT FROM c.subject_id
                AND p.hadm_id IS NOT DISTINCT FROM c.hadm_id
                AND nullif(trim(p.poe_id), '') IS NULL) AS identity_ok_missing_poe_rows,
           count(DISTINCT nullif(trim(p.poe_id), '')) FILTER
             (WHERE p.subject_id IS NOT DISTINCT FROM c.subject_id
                AND p.hadm_id IS NOT DISTINCT FROM c.hadm_id) AS identity_ok_distinct_poe,
           min(nullif(trim(p.poe_id), '')) FILTER
             (WHERE p.subject_id IS NOT DISTINCT FROM c.subject_id
                AND p.hadm_id IS NOT DISTINCT FROM c.hadm_id) AS identity_ok_poe,
           count(p.pharmacy_id) FILTER
             (WHERE p.subject_id IS NOT DISTINCT FROM c.subject_id
                AND p.hadm_id IS NOT DISTINCT FROM c.hadm_id
                AND p.poe_seq IS NULL) AS identity_ok_missing_poe_seq_rows,
           count(DISTINCT p.poe_seq) FILTER
             (WHERE p.subject_id IS NOT DISTINCT FROM c.subject_id
                AND p.hadm_id IS NOT DISTINCT FROM c.hadm_id) AS identity_ok_distinct_poe_seq,
           min(p.poe_seq) FILTER
             (WHERE p.subject_id IS NOT DISTINCT FROM c.subject_id
                AND p.hadm_id IS NOT DISTINCT FROM c.hadm_id) AS identity_ok_poe_seq
    FROM candidate_anchors c
    LEFT JOIN prescriptions p ON p.pharmacy_id = c.pharmacy_id
    GROUP BY c.candidate_key
), candidate_poe_rows AS MATERIALIZED (
    SELECT c.candidate_key, p.poe_id, p.poe_seq, p.subject_id, p.hadm_id,
           p.discontinue_of_poe_id, p.discontinued_by_poe_id
    FROM candidate_anchors c
    JOIN candidate_rx_link_shapes r USING (candidate_key)
    LEFT JOIN LATERAL (
        SELECT p.poe_id, p.poe_seq, p.subject_id, p.hadm_id,
               p.discontinue_of_poe_id, p.discontinued_by_poe_id
        FROM mimiciv_hosp.poe p
        WHERE p.poe_id = c.event_poe
          AND p.poe_seq = r.identity_ok_poe_seq
        OFFSET 0
    ) p ON true
), candidate_poe_shapes AS MATERIALIZED (
    SELECT c.candidate_key,
           count(p.poe_id) AS poe_rows,
           count(p.poe_id) FILTER
             (WHERE p.subject_id IS NOT DISTINCT FROM c.subject_id
                AND p.hadm_id IS NOT DISTINCT FROM c.hadm_id) AS identity_ok_rows,
           count(p.poe_id) FILTER
             (WHERE p.subject_id IS DISTINCT FROM c.subject_id
                 OR p.hadm_id IS DISTINCT FROM c.hadm_id) AS identity_bad_rows,
           count(p.poe_id) FILTER
             (WHERE nullif(trim(p.discontinue_of_poe_id), '') IS NOT NULL)
               AS discontinue_of_pointer_rows,
           count(p.poe_id) FILTER
             (WHERE nullif(trim(p.discontinued_by_poe_id), '') IS NOT NULL)
               AS discontinued_by_pointer_rows
    FROM candidate_anchors c
    LEFT JOIN candidate_poe_rows p USING (candidate_key)
    GROUP BY c.candidate_key
), candidate_link_evidence AS MATERIALIZED (
    SELECT c.*, ph.pharmacy_rows, ph.identity_ok_rows AS pharmacy_identity_ok_rows,
           ph.identity_bad_rows AS pharmacy_identity_bad_rows,
           ph.identity_ok_missing_poe_rows AS pharmacy_missing_poe_rows,
           ph.identity_ok_distinct_poe AS pharmacy_distinct_poe,
           ph.identity_ok_poe AS pharmacy_poe,
           rx.prescription_rows, rx.identity_ok_rows AS rx_identity_ok_rows,
           rx.identity_bad_rows AS rx_identity_bad_rows,
           rx.identity_ok_missing_poe_rows AS rx_missing_poe_rows,
           rx.identity_ok_distinct_poe AS rx_distinct_poe,
           rx.identity_ok_poe AS rx_poe,
           rx.identity_ok_missing_poe_seq_rows AS rx_missing_poe_seq_rows,
           rx.identity_ok_distinct_poe_seq AS rx_distinct_poe_seq,
           rx.identity_ok_poe_seq AS rx_poe_seq,
           ps.poe_rows, ps.identity_ok_rows AS poe_identity_ok_rows,
           ps.identity_bad_rows AS poe_identity_bad_rows,
           ps.discontinue_of_pointer_rows, ps.discontinued_by_pointer_rows,
           CASE
             WHEN c.event_poe IS NULL THEN 'missing_event_poe'
             WHEN ph.pharmacy_rows <> 1 OR ph.identity_ok_rows <> 1
                    OR ph.identity_bad_rows > 0
               THEN 'pharmacy_not_unique_or_identity_conflict'
             WHEN ph.identity_ok_missing_poe_rows > 0
                    OR ph.identity_ok_distinct_poe <> 1
                    OR ph.identity_ok_poe IS DISTINCT FROM c.event_poe
               THEN 'pharmacy_poe_missing_ambiguous_or_disagrees'
             WHEN rx.prescription_rows = 0 THEN 'prescription_not_found'
             WHEN rx.identity_bad_rows > 0 OR rx.identity_ok_rows <> rx.prescription_rows
               THEN 'prescription_identity_conflict'
             WHEN rx.identity_ok_missing_poe_rows > 0 OR rx.identity_ok_distinct_poe <> 1
               THEN 'prescription_poe_missing_or_ambiguous'
             WHEN rx.identity_ok_poe IS DISTINCT FROM c.event_poe
               THEN 'prescription_poe_disagrees'
             WHEN rx.identity_ok_missing_poe_seq_rows > 0
                    OR rx.identity_ok_distinct_poe_seq <> 1
               THEN 'prescription_poe_seq_missing_or_ambiguous'
             WHEN ps.poe_rows = 0 THEN 'poe_row_not_found'
             WHEN ps.poe_rows <> 1 OR ps.identity_ok_rows <> 1
                    OR ps.identity_bad_rows > 0
               THEN 'poe_row_not_unique_or_identity_conflict'
             ELSE 'strict_poe_key' END AS strict_poe_link_status,
           (c.event_poe IS NOT NULL
             AND ph.pharmacy_rows = 1 AND ph.identity_ok_rows = 1
             AND ph.identity_bad_rows = 0
             AND ph.identity_ok_missing_poe_rows = 0
             AND ph.identity_ok_distinct_poe = 1
             AND ph.identity_ok_poe IS NOT DISTINCT FROM c.event_poe
             AND rx.prescription_rows > 0
             AND rx.identity_bad_rows = 0
             AND rx.identity_ok_rows = rx.prescription_rows
             AND rx.identity_ok_missing_poe_rows = 0
             AND rx.identity_ok_distinct_poe = 1
             AND rx.identity_ok_poe IS NOT DISTINCT FROM c.event_poe
             AND rx.identity_ok_missing_poe_seq_rows = 0
             AND rx.identity_ok_distinct_poe_seq = 1
             AND ps.poe_rows = 1 AND ps.identity_ok_rows = 1
             AND ps.identity_bad_rows = 0) AS strict_poe_key
    FROM candidate_anchors c
    JOIN candidate_pharmacy_link_shapes ph USING (candidate_key)
    JOIN candidate_rx_link_shapes rx USING (candidate_key)
    JOIN candidate_poe_shapes ps USING (candidate_key)
), candidate_order_source_rows AS MATERIALIZED (
    SELECT c.candidate_key, 'pharmacy'::text AS source_kind,
           p.pharmacy_id IS NOT NULL AS row_present,
           (p.subject_id IS NOT DISTINCT FROM c.subject_id
             AND p.hadm_id IS NOT DISTINCT FROM c.hadm_id) AS identity_ok,
           p.starttime, p.stoptime
    FROM candidate_anchors c
    LEFT JOIN pharmacies p ON p.pharmacy_id = c.pharmacy_id
    UNION ALL
    SELECT c.candidate_key, 'prescription', p.pharmacy_id IS NOT NULL,
           (p.subject_id IS NOT DISTINCT FROM c.subject_id
             AND p.hadm_id IS NOT DISTINCT FROM c.hadm_id),
           p.starttime, p.stoptime
    FROM candidate_anchors c
    LEFT JOIN prescriptions p ON p.pharmacy_id = c.pharmacy_id
), candidate_order_time_shapes AS MATERIALIZED (
    SELECT c.candidate_key, c.subject_id, c.hadm_id,
           c.paper_action_relation, c.completeness_evidence, s.source_kind,
           count(*) FILTER (WHERE s.row_present) AS source_rows,
           count(*) FILTER (WHERE s.row_present AND s.identity_ok) AS identity_ok_rows,
           count(*) FILTER (WHERE s.row_present AND NOT s.identity_ok) AS identity_bad_rows,
           count(DISTINCT s.starttime) FILTER (WHERE s.row_present AND s.identity_ok)
               AS distinct_start_times,
           count(DISTINCT s.stoptime) FILTER (WHERE s.row_present AND s.identity_ok)
               AS distinct_stop_times,
           count(*) FILTER (WHERE s.row_present AND s.identity_ok
                              AND s.starttime IS NULL) AS missing_start_rows,
           count(*) FILTER (WHERE s.row_present AND s.identity_ok
                              AND s.stoptime IS NULL) AS missing_stop_rows,
           count(*) FILTER (WHERE s.row_present AND s.identity_ok
                              AND s.starttime IS NOT NULL AND s.stoptime IS NOT NULL
                              AND s.stoptime > s.starttime) AS positive_interval_rows,
           count(*) FILTER (WHERE s.row_present AND s.identity_ok
                              AND s.starttime IS NOT NULL AND s.stoptime IS NOT NULL
                              AND s.stoptime <= s.starttime) AS nonpositive_interval_rows,
           count(*) FILTER (WHERE s.row_present AND s.identity_ok
                              AND s.starttime IS NOT NULL AND s.stoptime IS NOT NULL
                              AND s.starttime < c.anchor_time
                              AND c.anchor_time < s.stoptime) AS anchor_inside_rows,
           count(*) FILTER (WHERE s.row_present AND s.identity_ok
                              AND s.starttime = c.anchor_time) AS anchor_at_start_rows,
           count(*) FILTER (WHERE s.row_present AND s.identity_ok
                              AND s.stoptime = c.anchor_time) AS anchor_at_stop_rows,
           count(*) FILTER (WHERE s.row_present AND s.identity_ok
                              AND s.starttime > c.anchor_time) AS anchor_before_start_rows,
           count(*) FILTER (WHERE s.row_present AND s.identity_ok
                              AND s.stoptime < c.anchor_time) AS anchor_after_stop_rows
    FROM candidate_anchors c
    CROSS JOIN (VALUES ('pharmacy'::text), ('prescription'::text)) kinds(source_kind)
    LEFT JOIN candidate_order_source_rows s
      ON s.candidate_key = c.candidate_key AND s.source_kind = kinds.source_kind
    GROUP BY c.candidate_key, c.subject_id, c.hadm_id,
             c.paper_action_relation, c.completeness_evidence, s.source_kind
), candidate_stream_pharmacy_keys AS MATERIALIZED (
    SELECT DISTINCT pharmacy_id
    FROM candidate_anchors
), pharmacy_stream_heads AS MATERIALIZED (
    SELECT k.pharmacy_id AS stream_pharmacy, e.*
    FROM candidate_stream_pharmacy_keys k
    JOIN LATERAL (
        SELECT subject_id, hadm_id, emar_id, emar_seq, poe_id, pharmacy_id,
               event_txt, charttime, scheduletime, storetime
        FROM mimiciv_hosp.emar e
        WHERE e.pharmacy_id = k.pharmacy_id
        OFFSET 0
    ) e ON true
), strict_poe_keys AS MATERIALIZED (
    SELECT DISTINCT event_poe
    FROM candidate_link_evidence
    WHERE strict_poe_key
), strict_poe_stream_heads AS MATERIALIZED (
    SELECT k.event_poe AS stream_poe, e.*
    FROM strict_poe_keys k
    JOIN LATERAL (
        SELECT subject_id, hadm_id, emar_id, emar_seq, poe_id, pharmacy_id,
               event_txt, charttime, scheduletime, storetime
        FROM mimiciv_hosp.emar e
        WHERE e.poe_id = k.event_poe
        OFFSET 0
    ) e ON true
), candidate_stream_base AS MATERIALIZED (
    SELECT c.*, 'same_pharmacy'::text AS stream_kind, true AS stream_eligible,
           'not_applicable'::text AS stream_link_status
    FROM candidate_link_evidence c
    UNION ALL
    SELECT c.*, 'strict_poe', c.strict_poe_key, c.strict_poe_link_status
    FROM candidate_link_evidence c
), candidate_stream_rows AS MATERIALIZED (
    SELECT c.candidate_key, c.subject_id AS candidate_subject,
           c.hadm_id AS candidate_hadm, c.pharmacy_id AS candidate_pharmacy,
           c.anchor_time, c.stream_kind, c.stream_eligible,
           c.stream_link_status, c.paper_action_relation,
           c.completeness_evidence,
           e.subject_id, e.hadm_id, e.emar_id, e.emar_seq, e.pharmacy_id,
           e.event_txt, e.charttime, e.scheduletime, e.storetime,
           (e.subject_id IS NOT DISTINCT FROM c.subject_id
             AND e.hadm_id IS NOT DISTINCT FROM c.hadm_id) AS identity_ok,
           (e.emar_id IS NOT DISTINCT FROM c.candidate_key
             AND e.emar_seq IS NOT DISTINCT FROM c.candidate_sequence) AS candidate_row
    FROM candidate_stream_base c
    JOIN pharmacy_stream_heads e ON c.stream_kind = 'same_pharmacy'
       AND e.stream_pharmacy = c.pharmacy_id
    UNION ALL
    SELECT c.candidate_key, c.subject_id, c.hadm_id, c.pharmacy_id,
           c.anchor_time, c.stream_kind, c.stream_eligible,
           c.stream_link_status, c.paper_action_relation,
           c.completeness_evidence,
           e.subject_id, e.hadm_id, e.emar_id, e.emar_seq, e.pharmacy_id,
           e.event_txt, e.charttime, e.scheduletime, e.storetime,
           (e.subject_id IS NOT DISTINCT FROM c.subject_id
             AND e.hadm_id IS NOT DISTINCT FROM c.hadm_id),
           (e.emar_id IS NOT DISTINCT FROM c.candidate_key
             AND e.emar_seq IS NOT DISTINCT FROM c.candidate_sequence)
    FROM candidate_stream_base c
    JOIN strict_poe_stream_heads e ON c.stream_kind = 'strict_poe'
       AND c.stream_eligible AND e.stream_poe = c.event_poe
), classified_stream_rows AS MATERIALIZED (
    SELECT r.*, CASE
        WHEN nullif(trim(event_txt), '') IS NULL THEN 'missing'
        WHEN upper(trim(event_txt)) = 'CONFIRMED' THEN 'confirmed'
        WHEN upper(trim(event_txt)) IN ('ADMINISTERED','PARTIAL ADMINISTERED')
          THEN 'administered_like'
        WHEN upper(trim(event_txt)) IN ('STARTED','DELAYED STARTED','RESTARTED')
          THEN 'start_like'
        WHEN upper(trim(event_txt)) IN ('STOPPED','STOPPED - UNSCHEDULED')
          THEN 'terminal_stop_like'
        WHEN upper(trim(event_txt)) IN ('STOPPED IN OTHER LOCATION','NOT STOPPED')
          THEN 'nonterminal_stop_or_transfer'
        WHEN upper(trim(event_txt)) IN ('NOT GIVEN','HELD','HOLD','DELAYED')
          THEN 'not_given_or_hold'
        ELSE 'other_nonempty' END AS status_class
    FROM candidate_stream_rows r
), stream_inventory AS MATERIALIZED (
    SELECT b.candidate_key, b.subject_id, b.hadm_id,
           b.paper_action_relation, b.completeness_evidence,
           b.stream_kind, b.stream_eligible, b.stream_link_status,
           count(r.emar_id) AS stream_rows,
           count(r.emar_id) FILTER (WHERE NOT r.identity_ok) AS identity_bad_rows,
           count(r.emar_id) FILTER (WHERE r.identity_ok AND r.charttime IS NULL)
               AS missing_charttime_rows,
           count(r.emar_id) FILTER (WHERE r.identity_ok AND r.charttime IS NOT NULL)
               AS valid_known_time_rows,
           count(r.emar_id) FILTER (WHERE r.candidate_row) AS candidate_row_occurrences,
           count(r.emar_id) FILTER (WHERE r.identity_ok AND r.charttime = b.anchor_time)
               AS anchor_timestamp_rows,
           count(r.emar_id) FILTER (WHERE r.identity_ok AND r.charttime < b.anchor_time)
               AS before_rows,
           count(r.emar_id) FILTER (WHERE r.identity_ok AND r.charttime > b.anchor_time)
               AS after_rows,
           count(r.emar_id) FILTER (WHERE r.identity_ok AND r.storetime IS NULL)
               AS missing_storetime_rows,
           count(r.emar_id) FILTER (WHERE r.identity_ok AND r.charttime IS NOT NULL
                                      AND r.storetime < r.charttime)
               AS reversed_storetime_rows
    FROM candidate_stream_base b
    LEFT JOIN classified_stream_rows r
      ON r.candidate_key = b.candidate_key AND r.stream_kind = b.stream_kind
    GROUP BY b.candidate_key, b.subject_id, b.hadm_id,
             b.paper_action_relation, b.completeness_evidence,
             b.stream_kind, b.stream_eligible, b.stream_link_status
), valid_stream_rows AS MATERIALIZED (
    SELECT * FROM classified_stream_rows
    WHERE identity_ok AND charttime IS NOT NULL
), stream_boundaries AS MATERIALIZED (
    SELECT b.candidate_key, b.subject_id, b.hadm_id,
           b.paper_action_relation, b.completeness_evidence,
           b.stream_kind, b.stream_eligible, b.stream_link_status,
           b.anchor_time,
           max(r.charttime) FILTER (WHERE r.charttime < b.anchor_time) AS previous_time,
           min(r.charttime) FILTER (WHERE r.charttime > b.anchor_time) AS next_time
    FROM candidate_stream_base b
    LEFT JOIN valid_stream_rows r
      ON r.candidate_key = b.candidate_key AND r.stream_kind = b.stream_kind
    GROUP BY b.candidate_key, b.subject_id, b.hadm_id,
             b.paper_action_relation, b.completeness_evidence,
             b.stream_kind, b.stream_eligible, b.stream_link_status, b.anchor_time
), stream_group_roles AS MATERIALIZED (
    SELECT b.*, x.group_role, x.group_time,
           CASE WHEN x.group_time IS NULL THEN NULL::double precision
                WHEN x.group_role = 'previous_timestamp_group'
                  THEN extract(epoch FROM (b.anchor_time - x.group_time))/3600.0
                WHEN x.group_role = 'next_timestamp_group'
                  THEN extract(epoch FROM (x.group_time - b.anchor_time))/3600.0
                ELSE 0::double precision END AS absolute_lag_hours
    FROM stream_boundaries b
    CROSS JOIN LATERAL (VALUES
       ('previous_timestamp_group'::text, b.previous_time),
       ('anchor_timestamp_group'::text, b.anchor_time),
       ('next_timestamp_group'::text, b.next_time)
    ) x(group_role, group_time)
), stream_group_shapes AS MATERIALIZED (
    SELECT g.candidate_key, g.subject_id, g.hadm_id,
           g.paper_action_relation, g.completeness_evidence,
           g.stream_kind, g.stream_eligible, g.stream_link_status,
           g.group_role, g.group_time, g.absolute_lag_hours,
           count(r.emar_id) AS group_rows,
           count(DISTINCT r.status_class) AS distinct_status_classes,
           coalesce(string_agg(DISTINCT r.status_class, '+' ORDER BY r.status_class),
                    'no_record') AS status_signature,
           array_agg(DISTINCT (r.emar_id || ':' || r.emar_seq::text)
                     ORDER BY (r.emar_id || ':' || r.emar_seq::text))
             FILTER (WHERE r.emar_id IS NOT NULL) AS internal_member_keys,
           count(r.emar_id) FILTER (WHERE r.candidate_row) AS candidate_rows,
           count(r.emar_id) FILTER (WHERE r.status_class = 'confirmed')
               AS confirmed_rows,
           count(r.emar_id) FILTER (WHERE r.status_class = 'administered_like')
               AS administered_like_rows,
           count(r.emar_id) FILTER (WHERE r.status_class = 'start_like')
               AS start_like_rows,
           count(r.emar_id) FILTER (WHERE r.status_class = 'terminal_stop_like')
               AS terminal_stop_like_rows,
           count(r.emar_id) FILTER (WHERE r.status_class = 'nonterminal_stop_or_transfer')
               AS nonterminal_stop_rows,
           count(r.emar_id) FILTER (WHERE r.status_class = 'not_given_or_hold')
               AS not_given_or_hold_rows,
           count(r.emar_id) FILTER (WHERE r.status_class IN ('missing','other_nonempty'))
               AS missing_or_other_status_rows,
           count(r.emar_id) FILTER (WHERE r.pharmacy_id IS NOT DISTINCT FROM
                                      (SELECT c.pharmacy_id FROM candidate_anchors c
                                       WHERE c.candidate_key = g.candidate_key))
               AS same_candidate_pharmacy_rows,
           count(r.emar_id) FILTER (WHERE r.pharmacy_id IS NULL) AS null_pharmacy_rows,
           count(r.emar_id) FILTER (WHERE r.pharmacy_id IS NOT NULL
                                      AND r.pharmacy_id IS DISTINCT FROM
                                      (SELECT c.pharmacy_id FROM candidate_anchors c
                                       WHERE c.candidate_key = g.candidate_key))
               AS other_pharmacy_rows,
           count(r.emar_id) FILTER (WHERE r.storetime IS NULL) AS missing_storetime_rows,
           count(r.emar_id) FILTER (WHERE r.storetime < r.charttime)
               AS reversed_storetime_rows,
           count(r.emar_id) FILTER (WHERE r.scheduletime IS NULL)
               AS missing_scheduletime_rows
    FROM stream_group_roles g
    LEFT JOIN valid_stream_rows r
      ON r.candidate_key = g.candidate_key AND r.stream_kind = g.stream_kind
     AND g.group_time IS NOT NULL AND r.charttime = g.group_time
    GROUP BY g.candidate_key, g.subject_id, g.hadm_id,
             g.paper_action_relation, g.completeness_evidence,
             g.stream_kind, g.stream_eligible, g.stream_link_status,
             g.group_role, g.group_time, g.absolute_lag_hours
), candidate_stream_endpoint_evidence AS MATERIALIZED (
    SELECT i.*, a.group_rows AS anchor_group_rows,
           a.distinct_status_classes AS anchor_distinct_status_classes,
           n.group_rows AS next_group_rows,
           n.distinct_status_classes AS next_distinct_status_classes,
           n.status_signature AS next_status_signature,
           n.confirmed_rows AS next_confirmed_rows,
           n.administered_like_rows AS next_administered_like_rows,
           n.start_like_rows AS next_start_like_rows,
           n.terminal_stop_like_rows AS next_terminal_stop_like_rows,
           n.nonterminal_stop_rows AS next_nonterminal_stop_rows,
           n.not_given_or_hold_rows AS next_not_given_or_hold_rows,
           n.missing_or_other_status_rows AS next_missing_or_other_status_rows,
           CASE
             WHEN NOT i.stream_eligible THEN 'identifier_or_key_not_strict'
             WHEN i.candidate_row_occurrences <> 1 THEN 'candidate_row_missing_or_duplicated'
             WHEN i.identity_bad_rows > 0 OR i.missing_charttime_rows > 0
               THEN 'stream_has_identity_or_missing_time_rows'
             WHEN a.group_rows > 1 OR n.group_rows > 1
               THEN 'candidate_or_next_timestamp_group_tied'
             WHEN n.group_rows = 0 THEN 'no_later_linked_record'
             WHEN n.administered_like_rows > 0 OR n.start_like_rows > 0
               THEN 'next_is_administered_or_start_like'
             WHEN n.nonterminal_stop_rows > 0 OR n.not_given_or_hold_rows > 0
               THEN 'next_is_explicit_nonterminal_or_not_given'
             WHEN n.confirmed_rows = n.group_rows THEN 'next_is_confirmed'
             WHEN n.terminal_stop_like_rows = n.group_rows
               THEN 'next_is_unique_terminal_stop_like_diagnostic'
             ELSE 'next_is_missing_other_or_mixed_status' END AS first_next_evidence_status
    FROM stream_inventory i
    JOIN stream_group_shapes a ON a.candidate_key = i.candidate_key
      AND a.stream_kind = i.stream_kind
      AND a.group_role = 'anchor_timestamp_group'
    JOIN stream_group_shapes n ON n.candidate_key = i.candidate_key
      AND n.stream_kind = i.stream_kind
      AND n.group_role = 'next_timestamp_group'
), next_group_comparison AS MATERIALIZED (
    SELECT p.candidate_key, p.subject_id, p.hadm_id,
           p.paper_action_relation, p.completeness_evidence,
           q.stream_eligible AS strict_poe_eligible,
           q.stream_link_status AS strict_poe_link_status,
           p.group_time AS pharmacy_next_time, q.group_time AS poe_next_time,
           p.group_rows AS pharmacy_next_rows, q.group_rows AS poe_next_rows,
           p.status_signature AS pharmacy_status_signature,
           q.status_signature AS poe_status_signature,
           p.internal_member_keys AS pharmacy_members,
           q.internal_member_keys AS poe_members,
           q.other_pharmacy_rows AS poe_other_pharmacy_rows,
           CASE
             WHEN NOT q.stream_eligible THEN 'strict_poe_unavailable'
             WHEN p.group_rows = 0 AND q.group_rows = 0 THEN 'both_have_no_next_group'
             WHEN p.group_rows = 0 OR q.group_rows = 0 THEN 'only_one_stream_has_next_group'
             WHEN p.group_time IS NOT DISTINCT FROM q.group_time
                  AND p.internal_member_keys IS NOT DISTINCT FROM q.internal_member_keys
               THEN 'same_timestamp_and_member_set'
             WHEN p.group_time IS NOT DISTINCT FROM q.group_time
               THEN 'same_timestamp_different_member_set'
             ELSE 'different_next_timestamp' END AS comparison_status
    FROM stream_group_shapes p
    JOIN stream_group_shapes q USING (candidate_key)
    WHERE p.stream_kind = 'same_pharmacy'
      AND q.stream_kind = 'strict_poe'
      AND p.group_role = 'next_timestamp_group'
      AND q.group_role = 'next_timestamp_group'
), candidate_admission_boundaries AS MATERIALIZED (
    SELECT c.candidate_key, c.subject_id, c.hadm_id,
           c.paper_action_relation, c.completeness_evidence,
           c.anchor_time,
           max(o.anchor_time) FILTER (WHERE o.anchor_time < c.anchor_time) AS previous_time,
           min(o.anchor_time) FILTER (WHERE o.anchor_time > c.anchor_time) AS next_time
    FROM candidate_anchors c
    LEFT JOIN candidate_anchors o
      ON o.subject_id = c.subject_id AND o.hadm_id = c.hadm_id
    GROUP BY c.candidate_key, c.subject_id, c.hadm_id,
             c.paper_action_relation, c.completeness_evidence, c.anchor_time
), candidate_admission_group_roles AS MATERIALIZED (
    SELECT b.*, x.group_role, x.group_time
    FROM candidate_admission_boundaries b
    CROSS JOIN LATERAL (VALUES
      ('previous_sampled_candidate_group'::text, b.previous_time),
      ('next_sampled_candidate_group'::text, b.next_time)
    ) x(group_role, group_time)
), candidate_admission_group_shapes AS MATERIALIZED (
    SELECT g.candidate_key, g.subject_id, g.hadm_id,
           g.paper_action_relation, g.completeness_evidence,
           g.group_role, count(o.candidate_key) AS group_candidates,
           count(DISTINCT o.pharmacy_id) AS distinct_pharmacy_ids,
           count(o.candidate_key) FILTER (WHERE o.pharmacy_id IS NOT DISTINCT FROM c.pharmacy_id)
               AS same_pharmacy_candidates,
           count(o.candidate_key) FILTER (WHERE o.pharmacy_id IS DISTINCT FROM c.pharmacy_id)
               AS other_pharmacy_candidates,
           count(DISTINCT o.paper_action_relation) AS distinct_action_relations,
           CASE WHEN g.group_time IS NULL THEN NULL::double precision
                ELSE abs(extract(epoch FROM (g.group_time - g.anchor_time))/3600.0)
                END AS absolute_lag_hours
    FROM candidate_admission_group_roles g
    JOIN candidate_anchors c ON c.candidate_key = g.candidate_key
    LEFT JOIN candidate_anchors o
      ON o.subject_id = g.subject_id AND o.hadm_id = g.hadm_id
     AND g.group_time IS NOT NULL AND o.anchor_time = g.group_time
    GROUP BY g.candidate_key, g.subject_id, g.hadm_id,
             g.paper_action_relation, g.completeness_evidence,
             g.group_role, g.group_time, g.anchor_time, c.pharmacy_id
), profiles AS (
    SELECT 'candidate_record_chain_summary'::text AS profile_section,
           jsonb_build_object(
             'source_rule','recomputed 194 provisional component-dose candidate',
             'stream_scope','full eMAR rows for candidate pharmacy and strict POE keys')
               AS dimensions,
           count(*) AS source_rows, count(*) AS emar_events,
           jsonb_build_object(
             'sampled_emar_rows',(SELECT count(*) FROM sampled),
             'selected_exact_name_emar_rows',(SELECT count(*) FROM events),
             'source_candidate_events',count(*),
             'distinct_subjects',count(DISTINCT subject_id),
             'distinct_admissions',count(DISTINCT (subject_id,hadm_id)),
             'paper_positive_value_events',count(*) FILTER
               (WHERE product_component_sum_meq IN (10,20,40)),
             'outside_paper_positive_value_events',count(*) FILTER
               (WHERE product_component_sum_meq NOT IN (10,20,40)),
             'explicit_negative_completeness_events',count(*) FILTER
               (WHERE completeness_evidence='explicit_negative_parent_flags'),
             'unknown_completeness_events',count(*) FILTER
               (WHERE completeness_evidence<>'explicit_negative_parent_flags'),
             'strict_poe_key_events',(SELECT count(*) FROM candidate_link_evidence
                                      WHERE strict_poe_key),
             'same_pharmacy_inventory_events',(SELECT count(*) FROM stream_inventory
                                      WHERE stream_kind='same_pharmacy'),
             'strict_poe_inventory_events',(SELECT count(*) FROM stream_inventory
                                      WHERE stream_kind='strict_poe'),
             'timestamp_group_rows',(SELECT count(*) FROM stream_group_shapes),
             'next_evidence_status_rows',(SELECT count(*)
                                           FROM candidate_stream_endpoint_evidence),
             'sampled_admission_sequence_rows',(SELECT count(*)
                                                FROM candidate_admission_group_shapes))
               AS counters
    FROM candidate_anchors
    UNION ALL
    SELECT 'candidate_detail_signal_shape',
           jsonb_build_object(
             'detail_role',detail_role,
             'paper_action_relation',paper_action_relation,
             'completeness_evidence',completeness_evidence,
             'has_completion_interval',completion_interval_rows>0,
             'completion_interval_conflict',completion_interval_distinct>1,
             'has_infusion_complete_yes',infusion_complete_yes_rows>0,
             'has_infusion_complete_no',infusion_complete_no_rows>0,
             'has_infusion_complete_other',infusion_complete_other_rows>0,
             'infusion_complete_conflict',infusion_complete_distinct>1,
             'has_infusion_rate',infusion_rate_rows>0,
             'infusion_rate_conflict',infusion_rate_distinct>1,
             'has_prior_infusion_rate',prior_infusion_rate_rows>0,
             'prior_infusion_rate_conflict',prior_infusion_rate_distinct>1,
             'has_rate_adjustment',rate_adjustment_rows>0,
             'has_rate_adjustment_amount',rate_adjustment_amount_rows>0,
             'has_new_bag_yes',new_bag_yes_rows>0,
             'has_continued_other_location_yes',continued_other_location_yes_rows>0,
             'has_restart_interval',restart_interval_rows>0),
           count(*), count(*),
           jsonb_build_object(
             'distinct_subjects',count(DISTINCT subject_id),
             'distinct_admissions',count(DISTINCT (subject_id,hadm_id)),
             'detail_rows',sum(detail_rows),
             'completion_interval_rows',sum(completion_interval_rows),
             'infusion_complete_yes_rows',sum(infusion_complete_yes_rows),
             'infusion_complete_no_rows',sum(infusion_complete_no_rows),
             'infusion_complete_other_rows',sum(infusion_complete_other_rows),
             'infusion_rate_rows',sum(infusion_rate_rows),
             'infusion_rate_simple_numeric_rows',sum(infusion_rate_simple_numeric_rows),
             'prior_infusion_rate_rows',sum(prior_infusion_rate_rows),
             'prior_infusion_rate_simple_numeric_rows',
                sum(prior_infusion_rate_simple_numeric_rows),
             'rate_adjustment_rows',sum(rate_adjustment_rows),
             'rate_adjustment_amount_rows',sum(rate_adjustment_amount_rows),
             'infusion_rate_unit_rows',sum(infusion_rate_unit_rows),
             'new_bag_yes_rows',sum(new_bag_yes_rows),
             'continued_other_location_yes_rows',sum(continued_other_location_yes_rows),
             'restart_interval_rows',sum(restart_interval_rows))
    FROM candidate_detail_role_shapes
    GROUP BY detail_role,paper_action_relation,completeness_evidence,
             completion_interval_rows>0,completion_interval_distinct>1,
             infusion_complete_yes_rows>0,infusion_complete_no_rows>0,
             infusion_complete_other_rows>0,infusion_complete_distinct>1,
             infusion_rate_rows>0,infusion_rate_distinct>1,
             prior_infusion_rate_rows>0,prior_infusion_rate_distinct>1,
             rate_adjustment_rows>0,rate_adjustment_amount_rows>0,
             new_bag_yes_rows>0,continued_other_location_yes_rows>0,
             restart_interval_rows>0
    UNION ALL
    SELECT 'candidate_identifier_link_shape',
           jsonb_build_object(
             'strict_poe_link_status',strict_poe_link_status,
             'strict_poe_key',strict_poe_key,
             'paper_action_relation',paper_action_relation,
             'completeness_evidence',completeness_evidence),
           count(*),count(*),
           jsonb_build_object(
             'distinct_subjects',count(DISTINCT subject_id),
             'distinct_admissions',count(DISTINCT (subject_id,hadm_id)),
             'pharmacy_rows',sum(pharmacy_rows),
             'pharmacy_identity_bad_rows',sum(pharmacy_identity_bad_rows),
             'prescription_rows',sum(prescription_rows),
             'prescription_identity_bad_rows',sum(rx_identity_bad_rows),
             'poe_rows',sum(poe_rows),
             'poe_identity_bad_rows',sum(poe_identity_bad_rows),
             'events_with_discontinue_of_pointer',count(*) FILTER
               (WHERE discontinue_of_pointer_rows>0),
             'events_with_discontinued_by_pointer',count(*) FILTER
               (WHERE discontinued_by_pointer_rows>0))
    FROM candidate_link_evidence
    GROUP BY strict_poe_link_status,strict_poe_key,
             paper_action_relation,completeness_evidence
    UNION ALL
    SELECT 'candidate_planned_order_time_shape',
           jsonb_build_object(
             'source_kind',source_kind,
             'row_count_class',CASE WHEN source_rows=0 THEN 'none'
                                    WHEN source_rows=1 THEN 'one' ELSE 'multiple' END,
             'has_identity_conflict',identity_bad_rows>0,
             'start_time_shape',CASE WHEN distinct_start_times=0 THEN 'none'
                                     WHEN distinct_start_times=1 THEN 'one_distinct'
                                     ELSE 'multiple_distinct' END,
             'stop_time_shape',CASE WHEN distinct_stop_times=0 THEN 'none'
                                    WHEN distinct_stop_times=1 THEN 'one_distinct'
                                    ELSE 'multiple_distinct' END,
             'has_positive_interval',positive_interval_rows>0,
             'has_nonpositive_interval',nonpositive_interval_rows>0,
             'anchor_inside_any_open_interval',anchor_inside_rows>0,
             'anchor_on_any_order_boundary',anchor_at_start_rows>0 OR anchor_at_stop_rows>0,
             'paper_action_relation',paper_action_relation,
             'completeness_evidence',completeness_evidence),
           count(*),count(*),
           jsonb_build_object(
             'distinct_subjects',count(DISTINCT subject_id),
             'distinct_admissions',count(DISTINCT (subject_id,hadm_id)),
             'source_rows',sum(source_rows),
             'identity_ok_rows',sum(identity_ok_rows),
             'identity_bad_rows',sum(identity_bad_rows),
             'missing_start_rows',sum(missing_start_rows),
             'missing_stop_rows',sum(missing_stop_rows),
             'positive_interval_rows',sum(positive_interval_rows),
             'nonpositive_interval_rows',sum(nonpositive_interval_rows),
             'anchor_inside_rows',sum(anchor_inside_rows),
             'anchor_at_start_rows',sum(anchor_at_start_rows),
             'anchor_at_stop_rows',sum(anchor_at_stop_rows),
             'anchor_before_start_rows',sum(anchor_before_start_rows),
             'anchor_after_stop_rows',sum(anchor_after_stop_rows))
    FROM candidate_order_time_shapes
    GROUP BY source_kind,
             CASE WHEN source_rows=0 THEN 'none' WHEN source_rows=1 THEN 'one'
                  ELSE 'multiple' END,
             identity_bad_rows>0,
             CASE WHEN distinct_start_times=0 THEN 'none'
                  WHEN distinct_start_times=1 THEN 'one_distinct' ELSE 'multiple_distinct' END,
             CASE WHEN distinct_stop_times=0 THEN 'none'
                  WHEN distinct_stop_times=1 THEN 'one_distinct' ELSE 'multiple_distinct' END,
             positive_interval_rows>0,nonpositive_interval_rows>0,
             anchor_inside_rows>0,anchor_at_start_rows>0 OR anchor_at_stop_rows>0,
             paper_action_relation,completeness_evidence
    UNION ALL
    SELECT 'candidate_stream_inventory',
           jsonb_build_object(
             'stream_kind',stream_kind,
             'stream_eligible',stream_eligible,
             'stream_link_status',stream_link_status,
             'stream_row_count_class',CASE WHEN stream_rows=0 THEN 'none'
                                           WHEN stream_rows=1 THEN 'one'
                                           ELSE 'multiple' END,
             'has_identity_conflict',identity_bad_rows>0,
             'has_missing_charttime',missing_charttime_rows>0,
             'candidate_row_occurrence_class',CASE WHEN candidate_row_occurrences=0 THEN 'none'
                                         WHEN candidate_row_occurrences=1 THEN 'one'
                                         ELSE 'multiple' END,
             'paper_action_relation',paper_action_relation,
             'completeness_evidence',completeness_evidence),
           count(*),count(*),
           jsonb_build_object(
             'distinct_subjects',count(DISTINCT subject_id),
             'distinct_admissions',count(DISTINCT (subject_id,hadm_id)),
             'stream_rows',sum(stream_rows),
             'identity_bad_rows',sum(identity_bad_rows),
             'missing_charttime_rows',sum(missing_charttime_rows),
             'valid_known_time_rows',sum(valid_known_time_rows),
             'anchor_timestamp_rows',sum(anchor_timestamp_rows),
             'before_rows',sum(before_rows),'after_rows',sum(after_rows),
             'missing_storetime_rows',sum(missing_storetime_rows),
             'reversed_storetime_rows',sum(reversed_storetime_rows))
    FROM stream_inventory
    GROUP BY stream_kind,stream_eligible,stream_link_status,
             CASE WHEN stream_rows=0 THEN 'none' WHEN stream_rows=1 THEN 'one'
                  ELSE 'multiple' END,
             identity_bad_rows>0,missing_charttime_rows>0,
             CASE WHEN candidate_row_occurrences=0 THEN 'none'
                  WHEN candidate_row_occurrences=1 THEN 'one' ELSE 'multiple' END,
             paper_action_relation,completeness_evidence
    UNION ALL
    SELECT 'candidate_adjacent_timestamp_group',
           jsonb_build_object(
             'stream_kind',stream_kind,
             'group_role',group_role,
             'stream_eligible',stream_eligible,
             'stream_link_status',stream_link_status,
             'group_presence',group_rows>0,
             'group_row_count_class',CASE WHEN group_rows=0 THEN 'none'
                                          WHEN group_rows=1 THEN 'one'
                                          ELSE 'multiple' END,
             'timestamp_group_tied',group_rows>1,
             'status_signature',status_signature,
             'paper_action_relation',paper_action_relation,
             'completeness_evidence',completeness_evidence),
           count(*),count(*),
           jsonb_build_object(
             'distinct_subjects',count(DISTINCT subject_id),
             'distinct_admissions',count(DISTINCT (subject_id,hadm_id)),
             'group_rows',sum(group_rows),
             'candidate_rows',sum(candidate_rows),
             'confirmed_rows',sum(confirmed_rows),
             'administered_like_rows',sum(administered_like_rows),
             'start_like_rows',sum(start_like_rows),
             'terminal_stop_like_rows',sum(terminal_stop_like_rows),
             'nonterminal_stop_rows',sum(nonterminal_stop_rows),
             'not_given_or_hold_rows',sum(not_given_or_hold_rows),
             'missing_or_other_status_rows',sum(missing_or_other_status_rows),
             'same_candidate_pharmacy_rows',sum(same_candidate_pharmacy_rows),
             'other_pharmacy_rows',sum(other_pharmacy_rows),
             'null_pharmacy_rows',sum(null_pharmacy_rows),
             'missing_storetime_rows',sum(missing_storetime_rows),
             'reversed_storetime_rows',sum(reversed_storetime_rows),
             'missing_scheduletime_rows',sum(missing_scheduletime_rows),
             'minimum_absolute_lag_hours',min(absolute_lag_hours),
             'median_absolute_lag_hours',percentile_cont(0.5)
                 WITHIN GROUP (ORDER BY absolute_lag_hours),
             'maximum_absolute_lag_hours',max(absolute_lag_hours))
    FROM stream_group_shapes
    GROUP BY stream_kind,group_role,stream_eligible,stream_link_status,
             group_rows>0,
             CASE WHEN group_rows=0 THEN 'none' WHEN group_rows=1 THEN 'one'
                  ELSE 'multiple' END,
             group_rows>1,status_signature,paper_action_relation,completeness_evidence
    UNION ALL
    SELECT 'candidate_next_evidence_status',
           jsonb_build_object(
             'stream_kind',stream_kind,
             'stream_eligible',stream_eligible,
             'stream_link_status',stream_link_status,
             'first_next_evidence_status',first_next_evidence_status,
             'paper_action_relation',paper_action_relation,
             'completeness_evidence',completeness_evidence),
           count(*),count(*),
           jsonb_build_object(
             'distinct_subjects',count(DISTINCT subject_id),
             'distinct_admissions',count(DISTINCT (subject_id,hadm_id)),
             'stream_rows',sum(stream_rows),
             'identity_bad_rows',sum(identity_bad_rows),
             'missing_charttime_rows',sum(missing_charttime_rows),
             'anchor_group_rows',sum(anchor_group_rows),
             'next_group_rows',sum(next_group_rows),
             'next_confirmed_rows',sum(next_confirmed_rows),
             'next_administered_like_rows',sum(next_administered_like_rows),
             'next_start_like_rows',sum(next_start_like_rows),
             'next_terminal_stop_like_rows',sum(next_terminal_stop_like_rows),
             'next_nonterminal_stop_rows',sum(next_nonterminal_stop_rows),
             'next_not_given_or_hold_rows',sum(next_not_given_or_hold_rows),
             'next_missing_or_other_status_rows',sum(next_missing_or_other_status_rows))
    FROM candidate_stream_endpoint_evidence
    GROUP BY stream_kind,stream_eligible,stream_link_status,
             first_next_evidence_status,paper_action_relation,completeness_evidence
    UNION ALL
    SELECT 'candidate_stream_comparison',
           jsonb_build_object(
             'comparison_status',comparison_status,
             'strict_poe_eligible',strict_poe_eligible,
             'strict_poe_link_status',strict_poe_link_status,
             'pharmacy_status_signature',pharmacy_status_signature,
             'poe_status_signature',poe_status_signature,
             'poe_next_has_other_pharmacy',poe_other_pharmacy_rows>0,
             'paper_action_relation',paper_action_relation,
             'completeness_evidence',completeness_evidence),
           count(*),count(*),
           jsonb_build_object(
             'distinct_subjects',count(DISTINCT subject_id),
             'distinct_admissions',count(DISTINCT (subject_id,hadm_id)),
             'pharmacy_next_group_rows',sum(pharmacy_next_rows),
             'poe_next_group_rows',sum(poe_next_rows),
             'poe_other_pharmacy_rows',sum(poe_other_pharmacy_rows))
    FROM next_group_comparison
    GROUP BY comparison_status,strict_poe_eligible,strict_poe_link_status,
             pharmacy_status_signature,poe_status_signature,
             poe_other_pharmacy_rows>0,paper_action_relation,completeness_evidence
    UNION ALL
    SELECT 'candidate_anchor_admission_sequence',
           jsonb_build_object(
             'sequence_scope','fixed-page-sample candidates within same admission',
             'group_role',group_role,
             'group_presence',group_candidates>0,
             'group_count_class',CASE WHEN group_candidates=0 THEN 'none'
                                      WHEN group_candidates=1 THEN 'one'
                                      ELSE 'multiple' END,
             'same_pharmacy_present',same_pharmacy_candidates>0,
             'other_pharmacy_present',other_pharmacy_candidates>0,
             'multiple_action_relations',distinct_action_relations>1,
             'paper_action_relation',paper_action_relation,
             'completeness_evidence',completeness_evidence),
           count(*),count(*),
           jsonb_build_object(
             'distinct_subjects',count(DISTINCT subject_id),
             'distinct_admissions',count(DISTINCT (subject_id,hadm_id)),
             'group_candidates',sum(group_candidates),
             'same_pharmacy_candidates',sum(same_pharmacy_candidates),
             'other_pharmacy_candidates',sum(other_pharmacy_candidates),
             'minimum_absolute_lag_hours',min(absolute_lag_hours),
             'median_absolute_lag_hours',percentile_cont(0.5)
                 WITHIN GROUP (ORDER BY absolute_lag_hours),
             'maximum_absolute_lag_hours',max(absolute_lag_hours))
    FROM candidate_admission_group_shapes
    GROUP BY group_role,group_candidates>0,
             CASE WHEN group_candidates=0 THEN 'none'
                  WHEN group_candidates=1 THEN 'one' ELSE 'multiple' END,
             same_pharmacy_candidates>0,other_pharmacy_candidates>0,
             distinct_action_relations>1,paper_action_relation,completeness_evidence
    UNION ALL
    SELECT 'candidate_poe_pointer_shape',
           jsonb_build_object(
             'strict_poe_link_status',strict_poe_link_status,
             'strict_poe_key',strict_poe_key,
             'has_discontinue_of_pointer',discontinue_of_pointer_rows>0,
             'has_discontinued_by_pointer',discontinued_by_pointer_rows>0,
             'paper_action_relation',paper_action_relation,
             'completeness_evidence',completeness_evidence),
           count(*),count(*),
           jsonb_build_object(
             'distinct_subjects',count(DISTINCT subject_id),
             'distinct_admissions',count(DISTINCT (subject_id,hadm_id)),
             'poe_rows',sum(poe_rows),
             'discontinue_of_pointer_rows',sum(discontinue_of_pointer_rows),
             'discontinued_by_pointer_rows',sum(discontinued_by_pointer_rows))
    FROM candidate_link_evidence
    GROUP BY strict_poe_link_status,strict_poe_key,
             discontinue_of_pointer_rows>0,discontinued_by_pointer_rows>0,
             paper_action_relation,completeness_evidence
)
SELECT profile_section,dimensions,source_rows,emar_events,
       counters || jsonb_build_object(
         'system_sample_percent',1.0,
         'sample_seed',20261011,
         'full_stream_rows_use_page_sample',false,
         'formal_cohort',false,
         'formal_episode_rule',false,
         'formal_action_mapping',false,
         'candidate_is_actual_action',false,
         'component_sum_is_actual_dose',false,
         'actual_dose_defined',false,
         'zero_action_constructed',false,
         'formal_non_icu_rule',false,
         'formal_feature_rule',false,
         'formal_label_rule',false,
         'observed_treatment_start_defined',false,
         'observed_treatment_end_defined',false,
         'next_timestamp_group_is_endpoint',false,
         'terminal_stop_like_is_observed_end',false,
         'prescription_stoptime_is_endpoint',false,
         'pharmacy_stoptime_is_endpoint',false,
         'completion_interval_is_endpoint',false,
         'infusion_complete_is_timestamped_endpoint',false,
         'poe_discontinue_is_endpoint',false,
         'scheduletime_is_observed_time',false,
         'storetime_is_observed_endpoint',false,
         'prompt_rate_end_is_observed',false,
         'rate_integral_or_delivered_dose_defined',false,
         'cross_order_continuity_assumed',false,
         'confirmed_skipping_applied',false,
         'gap_threshold_applied',false,
         'candidate_admission_sequence_is_complete_medication_history',false,
         'page_sample_is_representative',false,
         'timestamp_group_rule',
           'all rows at previous max, anchor, or next min charttime; no ID tie-break',
         'next_group_rule',
           'first strictly later linked timestamp group regardless of status; no skipping')
         AS counters
FROM profiles
ORDER BY profile_section,source_rows DESC,dimensions;
