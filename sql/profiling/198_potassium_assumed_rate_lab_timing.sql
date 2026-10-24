-- D003 fixed-rate potassium clock and lab-timing sensitivity diagnostic only.
-- This statement exactly recomputes the conservative 194 source candidates over
-- the same fixed SYSTEM (1) eMAR page sample, then limits proxy-clock analysis to
-- the 10/20/40 mEq component sums that match the paper's positive action values.
-- No identifier, timestamp, raw laboratory value, free text or product code is
-- emitted; all outputs are aggregate strata and aggregate distribution summaries.
--
-- eMAR charttime remains an administration-record anchor, not observed treatment
-- start. The 10 mEq/hour rate, anchor+dose/rate proxy end, and proxy-end+3-hour
-- target are explicit unobserved assumptions. They do not define an episode,
-- actual dose/action, observed end, feature, label, cohort or non-ICU rule.
--
-- The first-after and nearest selectors choose labevents charttime before value,
-- unit or storetime quality is examined. Every lab row tied at a chosen timestamp
-- is retained, and nearest-to-target retains every equidistant timestamp group.
-- The two latest-valid-available selectors alone use their declared availability
-- gate (charttime <= target, storetime <= target, storetime >= charttime), with
-- no-end-gate and strict-post-proxy-end variants kept separate. There is no
-- maximum lag. The fixed page sample is not a representative or shared snapshot.
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
)
, proxy_anchors AS MATERIALIZED (
    SELECT emar_id,subject_id,hadm_id,charttime AS anchor_time,
           product_component_sum_meq AS proxy_dose_meq,
           charttime + (product_component_sum_meq::double precision / 10.0)
                         * interval '1 hour' AS proxy_end_time,
           charttime + (product_component_sum_meq::double precision / 10.0 + 3.0)
                         * interval '1 hour' AS target_time,
           completeness_evidence,paper_action_relation
    FROM candidate_anchors
    WHERE product_component_sum_meq IN (10,20,40)
      AND paper_action_relation='matches_positive_paper_action_value'
), proxy_admissions AS MATERIALIZED (
    SELECT DISTINCT subject_id,hadm_id FROM proxy_anchors
), proxy_intervening_candidate_counts AS MATERIALIZED (
    -- Use every conservative source candidate in this fixed SYSTEM 1 percent
    -- page sample, including 60/80 mEq candidates, as incomplete competing
    -- treatment-record context around each 10/20/40 focal clock. These counts
    -- neither recover candidates outside the page sample, merge or exclude
    -- events, nor establish treatment continuity or an episode.
    SELECT p.emar_id,p.subject_id,p.hadm_id,p.proxy_dose_meq,
           p.completeness_evidence,p.paper_action_relation,
           count(c.emar_id) FILTER (
             WHERE c.charttime>p.anchor_time
               AND c.charttime<=p.proxy_end_time) AS anchor_to_proxy_end_candidates,
           count(c.emar_id) FILTER (
             WHERE c.charttime>p.proxy_end_time
               AND c.charttime<=p.target_time) AS proxy_end_to_target_candidates,
           count(c.emar_id) FILTER (
             WHERE c.charttime>p.anchor_time
               AND c.charttime<=p.proxy_end_time
               AND c.paper_action_relation='matches_positive_paper_action_value')
               AS anchor_to_proxy_end_paper_value_candidates,
           count(c.emar_id) FILTER (
             WHERE c.charttime>p.anchor_time
               AND c.charttime<=p.proxy_end_time
               AND c.paper_action_relation<>'matches_positive_paper_action_value')
               AS anchor_to_proxy_end_outside_paper_value_candidates,
           count(c.emar_id) FILTER (
             WHERE c.charttime>p.proxy_end_time
               AND c.charttime<=p.target_time
               AND c.paper_action_relation='matches_positive_paper_action_value')
               AS proxy_end_to_target_paper_value_candidates,
           count(c.emar_id) FILTER (
             WHERE c.charttime>p.proxy_end_time
               AND c.charttime<=p.target_time
               AND c.paper_action_relation<>'matches_positive_paper_action_value')
               AS proxy_end_to_target_outside_paper_value_candidates
    FROM proxy_anchors p LEFT JOIN candidate_anchors c
      ON c.subject_id=p.subject_id AND c.hadm_id=p.hadm_id
     AND c.emar_id<>p.emar_id
    GROUP BY p.emar_id,p.subject_id,p.hadm_id,p.proxy_dose_meq,
             p.completeness_evidence,p.paper_action_relation
), rare_potassium_labs AS MATERIALIZED (
    -- 52610 lacks the useful 50971 partial index. Scan it once, restricted to
    -- admissions containing a fixed-page-sample proxy candidate.
    SELECT l.labevent_id,l.subject_id,l.hadm_id,l.itemid,
           l.charttime AS lab_time,l.storetime,l.valuenum,l.valueuom
    FROM mimiciv_hosp.labevents l JOIN proxy_admissions a
      ON a.subject_id=l.subject_id AND a.hadm_id=l.hadm_id
    WHERE l.itemid=52610
), common_potassium_labs AS MATERIALIZED (
    -- Keep itemid=50971 as a literal inside the LATERAL lookup so the existing
    -- partial index remains usable. Each candidate admission is fetched once.
    SELECT l.labevent_id,a.subject_id,a.hadm_id,l.itemid,
           l.charttime AS lab_time,l.storetime,l.valuenum,l.valueuom
    FROM proxy_admissions a CROSS JOIN LATERAL (
        SELECT labevent_id,itemid,charttime,storetime,valuenum,valueuom
        FROM mimiciv_hosp.labevents l
        WHERE l.subject_id=a.subject_id AND l.hadm_id=a.hadm_id
          AND l.itemid=50971
        OFFSET 0
    ) l
), potassium_labs AS MATERIALIZED (
    SELECT * FROM common_potassium_labs
    UNION ALL
    SELECT * FROM rare_potassium_labs
), selector_names(selector_order,selector_name,selection_policy) AS (
    VALUES
      (1,'first_strictly_after_anchor',
         'minimum specimen charttime strictly after administration-record anchor'),
      (2,'first_strictly_after_proxy_end',
         'minimum specimen charttime strictly after assumed proxy end'),
      (3,'first_strictly_after_target',
         'minimum specimen charttime strictly after assumed target'),
      (4,'nearest_to_target_strict_post_end',
         'all specimen charttime groups at minimum absolute target lag, restricted strictly after proxy end'),
      (5,'latest_valid_available_by_target_no_end_gate',
         'maximum specimen charttime by target with valid storetime availability; no proxy-end gate'),
      (6,'latest_valid_available_by_target_strict_post_end',
         'maximum specimen charttime by target with valid storetime availability, strictly after proxy end')
), selector_time_metrics AS MATERIALIZED (
    SELECT a.emar_id,a.subject_id,a.hadm_id,a.proxy_dose_meq,
           a.anchor_time,a.proxy_end_time,a.target_time,
           a.completeness_evidence,a.paper_action_relation,
           min(l.lab_time) FILTER (WHERE l.lab_time>a.anchor_time)
               AS first_after_anchor_time,
           min(l.lab_time) FILTER (WHERE l.lab_time>a.proxy_end_time)
               AS first_after_proxy_end_time,
           min(l.lab_time) FILTER (WHERE l.lab_time>a.target_time)
               AS first_after_target_time,
           min(abs(extract(epoch FROM (l.lab_time-a.target_time))))
               FILTER (WHERE l.lab_time>a.proxy_end_time)
               AS nearest_post_end_target_distance_seconds,
           max(l.lab_time) FILTER (
               WHERE l.lab_time<=a.target_time
                 AND l.storetime<=a.target_time
                 AND l.storetime>=l.lab_time)
               AS latest_available_no_end_time,
           max(l.lab_time) FILTER (
               WHERE l.lab_time>a.proxy_end_time
                 AND l.lab_time<=a.target_time
                 AND l.storetime<=a.target_time
                 AND l.storetime>=l.lab_time)
               AS latest_available_post_end_time
    FROM proxy_anchors a LEFT JOIN potassium_labs l
      ON l.subject_id=a.subject_id AND l.hadm_id=a.hadm_id
    GROUP BY a.emar_id,a.subject_id,a.hadm_id,a.proxy_dose_meq,
             a.anchor_time,a.proxy_end_time,a.target_time,
             a.completeness_evidence,a.paper_action_relation
), single_selected_timestamps AS MATERIALIZED (
    SELECT m.emar_id,m.subject_id,m.hadm_id,m.proxy_dose_meq,
           m.anchor_time,m.proxy_end_time,m.target_time,
           m.completeness_evidence,m.paper_action_relation,
           v.selector_name,v.selected_time
    FROM selector_time_metrics m CROSS JOIN LATERAL (
      VALUES
        ('first_strictly_after_anchor'::text,m.first_after_anchor_time),
        ('first_strictly_after_proxy_end'::text,m.first_after_proxy_end_time),
        ('first_strictly_after_target'::text,m.first_after_target_time),
        ('latest_valid_available_by_target_no_end_gate'::text,
             m.latest_available_no_end_time),
        ('latest_valid_available_by_target_strict_post_end'::text,
             m.latest_available_post_end_time)
    ) v(selector_name,selected_time)
    WHERE v.selected_time IS NOT NULL
), nearest_selected_timestamps AS MATERIALIZED (
    -- DISTINCT preserves all equidistant timestamp groups while collapsing the
    -- multiple lab rows at a timestamp only until the subsequent tie expansion.
    SELECT DISTINCT m.emar_id,m.subject_id,m.hadm_id,m.proxy_dose_meq,
           m.anchor_time,m.proxy_end_time,m.target_time,
           m.completeness_evidence,m.paper_action_relation,
           'nearest_to_target_strict_post_end'::text AS selector_name,
           l.lab_time AS selected_time
    FROM selector_time_metrics m JOIN potassium_labs l
      ON l.subject_id=m.subject_id AND l.hadm_id=m.hadm_id
     AND l.lab_time>m.proxy_end_time
     AND abs(extract(epoch FROM (l.lab_time-m.target_time)))
           =m.nearest_post_end_target_distance_seconds
    WHERE m.nearest_post_end_target_distance_seconds IS NOT NULL
), raw_selected_timestamps AS MATERIALIZED (
    SELECT * FROM single_selected_timestamps
    UNION ALL
    SELECT * FROM nearest_selected_timestamps
), selected_timestamp_intervening_counts AS MATERIALIZED (
    -- For every selected timestamp group, retain incomplete competing
    -- source-candidate counts from the same fixed SYSTEM 1 percent page sample
    -- in (proxy_end, selected_time]. A selected time at/before proxy end has no
    -- forward interval and is kept explicitly with a zero count.
    SELECT s.emar_id,s.subject_id,s.hadm_id,s.proxy_dose_meq,
           s.completeness_evidence,s.paper_action_relation,s.selector_name,
           s.selected_time,s.proxy_end_time,s.target_time,
           count(c.emar_id) FILTER (
             WHERE s.selected_time>s.proxy_end_time
               AND c.charttime>s.proxy_end_time
               AND c.charttime<=s.selected_time)
               AS proxy_end_to_selected_candidates,
           count(c.emar_id) FILTER (
             WHERE s.selected_time>s.proxy_end_time
               AND c.charttime>s.proxy_end_time
               AND c.charttime<=s.selected_time
               AND c.paper_action_relation='matches_positive_paper_action_value')
               AS proxy_end_to_selected_paper_value_candidates,
           count(c.emar_id) FILTER (
             WHERE s.selected_time>s.proxy_end_time
               AND c.charttime>s.proxy_end_time
               AND c.charttime<=s.selected_time
               AND c.paper_action_relation<>'matches_positive_paper_action_value')
               AS proxy_end_to_selected_outside_paper_value_candidates
    FROM raw_selected_timestamps s LEFT JOIN candidate_anchors c
      ON c.subject_id=s.subject_id AND c.hadm_id=s.hadm_id
     AND c.emar_id<>s.emar_id
    GROUP BY s.emar_id,s.subject_id,s.hadm_id,s.proxy_dose_meq,
             s.completeness_evidence,s.paper_action_relation,s.selector_name,
             s.selected_time,s.proxy_end_time,s.target_time
), candidate_selectors AS MATERIALIZED (
    SELECT a.emar_id,a.subject_id,a.hadm_id,a.proxy_dose_meq,
           a.anchor_time,a.proxy_end_time,a.target_time,
           a.completeness_evidence,a.paper_action_relation,
           s.selector_order,s.selector_name,s.selection_policy
    FROM proxy_anchors a CROSS JOIN selector_names s
), selected_group_shapes AS MATERIALIZED (
    -- Selection has already occurred. All itemid rows tied at each selected
    -- specimen timestamp are now restored, and quality is evaluated afterward.
    SELECT s.emar_id,s.subject_id,s.hadm_id,s.proxy_dose_meq,
           s.anchor_time,s.proxy_end_time,s.target_time,
           s.completeness_evidence,s.paper_action_relation,
           n.selector_order,s.selector_name,n.selection_policy,s.selected_time,
           CASE WHEN s.selected_time<=s.anchor_time THEN 'at_or_before_anchor'
                WHEN s.selected_time<=s.proxy_end_time
                  THEN 'post_anchor_through_proxy_end'
                WHEN s.selected_time<s.target_time
                  THEN 'post_proxy_end_before_target'
                WHEN s.selected_time=s.target_time THEN 'at_target'
                ELSE 'after_target' END AS selected_phase,
           extract(epoch FROM (s.selected_time-s.anchor_time))/3600.0
               AS anchor_lag_hours,
           extract(epoch FROM (s.selected_time-s.proxy_end_time))/3600.0
               AS proxy_end_lag_hours,
           extract(epoch FROM (s.selected_time-s.target_time))/3600.0
               AS target_lag_hours,
           abs(extract(epoch FROM (s.selected_time-s.target_time)))/3600.0
               AS absolute_target_lag_hours,
           CASE WHEN s.selector_name='first_strictly_after_anchor'
                  THEN 'anchor_lag'
                WHEN s.selector_name='first_strictly_after_proxy_end'
                  THEN 'proxy_end_lag'
                WHEN s.selector_name='first_strictly_after_target'
                  THEN 'target_lag'
                ELSE 'absolute_target_lag' END AS selector_lag_reference,
           CASE WHEN s.selector_name='first_strictly_after_anchor'
                  THEN 'strictly_after_anchor'
                WHEN s.selector_name='first_strictly_after_proxy_end'
                  THEN 'strictly_after_proxy_end'
                WHEN s.selector_name='first_strictly_after_target'
                  THEN 'strictly_after_target'
                WHEN s.selector_name='nearest_to_target_strict_post_end'
                  THEN CASE WHEN s.selected_time<s.target_time THEN 'before_target'
                            WHEN s.selected_time=s.target_time THEN 'at_target'
                            ELSE 'after_target' END
                ELSE CASE WHEN s.selected_time<=s.anchor_time
                            THEN 'at_or_before_anchor'
                          WHEN s.selected_time<=s.proxy_end_time
                            THEN 'post_anchor_through_proxy_end'
                          WHEN s.selected_time<s.target_time
                            THEN 'post_proxy_end_before_target'
                          WHEN s.selected_time=s.target_time THEN 'at_target'
                          ELSE 'after_target' END
                END AS selector_lag_direction,
           CASE
             WHEN s.selector_name='first_strictly_after_anchor' THEN
               CASE WHEN extract(epoch FROM (s.selected_time-s.anchor_time))/3600.0<=0
                        THEN 'unexpected_nonpositive'
                    WHEN extract(epoch FROM (s.selected_time-s.anchor_time))/3600.0<=3
                        THEN '(0,3]h'
                    WHEN extract(epoch FROM (s.selected_time-s.anchor_time))/3600.0<=6
                        THEN '(3,6]h'
                    WHEN extract(epoch FROM (s.selected_time-s.anchor_time))/3600.0<=24
                        THEN '(6,24]h' ELSE '>24h' END
             WHEN s.selector_name='first_strictly_after_proxy_end' THEN
               CASE WHEN extract(epoch FROM (s.selected_time-s.proxy_end_time))/3600.0<=0
                        THEN 'unexpected_nonpositive'
                    WHEN extract(epoch FROM (s.selected_time-s.proxy_end_time))/3600.0<=3
                        THEN '(0,3]h'
                    WHEN extract(epoch FROM (s.selected_time-s.proxy_end_time))/3600.0<=6
                        THEN '(3,6]h'
                    WHEN extract(epoch FROM (s.selected_time-s.proxy_end_time))/3600.0<=24
                        THEN '(6,24]h' ELSE '>24h' END
             WHEN s.selector_name='first_strictly_after_target' THEN
               CASE WHEN extract(epoch FROM (s.selected_time-s.target_time))/3600.0<=0
                        THEN 'unexpected_nonpositive'
                    WHEN extract(epoch FROM (s.selected_time-s.target_time))/3600.0<=3
                        THEN '(0,3]h'
                    WHEN extract(epoch FROM (s.selected_time-s.target_time))/3600.0<=6
                        THEN '(3,6]h'
                    WHEN extract(epoch FROM (s.selected_time-s.target_time))/3600.0<=24
                        THEN '(6,24]h' ELSE '>24h' END
             ELSE
               CASE WHEN abs(extract(epoch FROM (s.selected_time-s.target_time)))=0
                        THEN '0h'
                    WHEN abs(extract(epoch FROM (s.selected_time-s.target_time)))/3600.0<=1
                        THEN '(0,1]h'
                    WHEN abs(extract(epoch FROM (s.selected_time-s.target_time)))/3600.0<=3
                        THEN '(1,3]h'
                    WHEN abs(extract(epoch FROM (s.selected_time-s.target_time)))/3600.0<=6
                        THEN '(3,6]h'
                    WHEN abs(extract(epoch FROM (s.selected_time-s.target_time)))/3600.0<=24
                        THEN '(6,24]h' ELSE '>24h' END
           END AS selector_lag_bucket,
           count(*) AS lab_rows,
           count(DISTINCT l.itemid) AS distinct_itemids,
           CASE WHEN count(*) FILTER (WHERE l.itemid=50971)>0
                      AND count(*) FILTER (WHERE l.itemid=52610)>0 THEN 'both'
                WHEN count(*) FILTER (WHERE l.itemid=50971)>0 THEN '50971_only'
                ELSE '52610_only' END AS itemid_pattern,
           count(*) FILTER (WHERE l.valuenum IS NOT NULL
              AND l.valuenum::text NOT IN ('NaN','Infinity','-Infinity'))
              AS finite_value_rows,
           count(*) FILTER (WHERE l.valuenum IS NULL)
              AS missing_value_rows,
           count(*) FILTER (WHERE l.valuenum IS NOT NULL
              AND l.valuenum::text IN ('NaN','Infinity','-Infinity'))
              AS nonfinite_value_rows,
           count(*) FILTER (WHERE l.valuenum IS NULL
              OR l.valuenum::text IN ('NaN','Infinity','-Infinity'))
              AS missing_or_nonfinite_value_rows,
           count(DISTINCT l.valuenum) FILTER (WHERE l.valuenum IS NOT NULL
              AND l.valuenum::text NOT IN ('NaN','Infinity','-Infinity'))
              AS distinct_finite_values,
           count(*) FILTER (WHERE upper(trim(l.valueuom))='MEQ/L')
              AS expected_unit_rows,
           count(*) FILTER (WHERE l.valuenum IS NOT NULL
              AND l.valuenum::text NOT IN ('NaN','Infinity','-Infinity')
              AND upper(trim(l.valueuom))='MEQ/L')
              AS finite_expected_unit_rows,
           count(DISTINCT l.valuenum) FILTER (WHERE l.valuenum IS NOT NULL
              AND l.valuenum::text NOT IN ('NaN','Infinity','-Infinity')
              AND upper(trim(l.valueuom))='MEQ/L')
              AS distinct_finite_expected_unit_values,
           count(*) FILTER (WHERE nullif(trim(l.valueuom),'') IS NULL)
              AS missing_unit_rows,
           count(*) FILTER (WHERE nullif(trim(l.valueuom),'') IS NOT NULL
              AND upper(trim(l.valueuom))<>'MEQ/L')
              AS other_unit_rows,
           count(*) FILTER (WHERE l.storetime IS NULL)
              AS missing_storetime_rows,
           count(*) FILTER (WHERE l.storetime<l.lab_time)
              AS reversed_storetime_rows,
           count(*) FILTER (WHERE l.storetime>=l.lab_time)
              AS valid_storetime_order_rows,
           count(*) FILTER (WHERE l.storetime>=l.lab_time
              AND l.storetime<=s.target_time)
              AS valid_available_by_target_rows,
           count(*) FILTER (WHERE l.storetime>s.target_time)
              AS storetime_after_target_rows
    FROM raw_selected_timestamps s JOIN selector_names n
      ON n.selector_name=s.selector_name
    JOIN potassium_labs l
      ON l.subject_id=s.subject_id AND l.hadm_id=s.hadm_id
     AND l.lab_time=s.selected_time
    GROUP BY s.emar_id,s.subject_id,s.hadm_id,s.proxy_dose_meq,
             s.anchor_time,s.proxy_end_time,s.target_time,
             s.completeness_evidence,s.paper_action_relation,
             n.selector_order,s.selector_name,n.selection_policy,s.selected_time
), selector_event_base AS MATERIALIZED (
    SELECT c.emar_id,c.subject_id,c.hadm_id,c.proxy_dose_meq,
           c.completeness_evidence,c.paper_action_relation,
           c.selector_order,c.selector_name,c.selection_policy,
           count(g.selected_time) AS selected_timestamp_groups,
           coalesce(sum(g.lab_rows),0) AS selected_lab_rows,
           count(g.selected_time) FILTER (WHERE g.lab_rows>1)
              AS tied_timestamp_groups,
           coalesce(sum(g.finite_value_rows),0) AS finite_value_rows,
           coalesce(sum(g.missing_value_rows),0) AS missing_value_rows,
           coalesce(sum(g.nonfinite_value_rows),0) AS nonfinite_value_rows,
           coalesce(sum(g.expected_unit_rows),0) AS expected_unit_rows,
           coalesce(sum(g.finite_expected_unit_rows),0)
              AS finite_expected_unit_rows,
           coalesce(sum(g.missing_or_nonfinite_value_rows),0)
              AS missing_or_nonfinite_value_rows,
           coalesce(sum(g.missing_unit_rows),0) AS missing_unit_rows,
           coalesce(sum(g.other_unit_rows),0) AS other_unit_rows,
           coalesce(sum(g.missing_storetime_rows),0) AS missing_storetime_rows,
           coalesce(sum(g.reversed_storetime_rows),0) AS reversed_storetime_rows,
           coalesce(sum(g.valid_available_by_target_rows),0)
              AS valid_available_by_target_rows,
           coalesce(sum(g.storetime_after_target_rows),0)
              AS storetime_after_target_rows
    FROM candidate_selectors c LEFT JOIN selected_group_shapes g
      ON g.emar_id=c.emar_id AND g.selector_name=c.selector_name
    GROUP BY c.emar_id,c.subject_id,c.hadm_id,c.proxy_dose_meq,
             c.completeness_evidence,c.paper_action_relation,
             c.selector_order,c.selector_name,c.selection_policy
), selector_event_shapes AS MATERIALIZED (
    SELECT b.*,
           CASE WHEN selected_timestamp_groups=0 THEN 'no_selected_timestamp'
                WHEN selected_timestamp_groups>1
                  THEN 'multiple_equidistant_timestamp_groups'
                WHEN tied_timestamp_groups>0 THEN 'one_timestamp_with_tied_rows'
                ELSE 'one_timestamp_one_row' END AS selector_status
    FROM selector_event_base b
), selector_timestamp_counts AS MATERIALIZED (
    SELECT c.emar_id,c.selector_order,c.selector_name,
           count(r.selected_time) AS selected_timestamp_groups
    FROM candidate_selectors c LEFT JOIN raw_selected_timestamps r
      ON r.emar_id=c.emar_id AND r.selector_name=c.selector_name
    GROUP BY c.emar_id,c.selector_order,c.selector_name
), selector_pair_overlap_counts AS MATERIALIZED (
    SELECT l.emar_id,l.selector_name AS left_selector,
           r.selector_name AS right_selector,count(*) AS overlap_timestamp_groups
    FROM raw_selected_timestamps l JOIN raw_selected_timestamps r
      ON r.emar_id=l.emar_id AND r.selected_time=l.selected_time
    JOIN selector_names ln ON ln.selector_name=l.selector_name
    JOIN selector_names rn ON rn.selector_name=r.selector_name
    WHERE ln.selector_order<rn.selector_order
    GROUP BY l.emar_id,l.selector_name,r.selector_name
), selector_pair_shapes AS MATERIALIZED (
    SELECT a.emar_id,a.subject_id,a.hadm_id,a.proxy_dose_meq,
           a.completeness_evidence,a.paper_action_relation,
           l.selector_name AS left_selector,r.selector_name AS right_selector,
           lc.selected_timestamp_groups AS left_timestamp_groups,
           rc.selected_timestamp_groups AS right_timestamp_groups,
           coalesce(o.overlap_timestamp_groups,0) AS overlap_timestamp_groups,
           CASE WHEN lc.selected_timestamp_groups=0
                      AND rc.selected_timestamp_groups=0 THEN 'both_none'
                WHEN lc.selected_timestamp_groups=0 THEN 'left_none'
                WHEN rc.selected_timestamp_groups=0 THEN 'right_none'
                WHEN coalesce(o.overlap_timestamp_groups,0)
                       =lc.selected_timestamp_groups
                 AND coalesce(o.overlap_timestamp_groups,0)
                       =rc.selected_timestamp_groups THEN 'identical_nonempty_sets'
                WHEN coalesce(o.overlap_timestamp_groups,0)>0
                  THEN 'partial_overlap'
                ELSE 'disjoint' END AS overlap_status
    FROM proxy_anchors a
    JOIN selector_names l ON true
    JOIN selector_names r ON l.selector_order<r.selector_order
    JOIN selector_timestamp_counts lc
      ON lc.emar_id=a.emar_id AND lc.selector_name=l.selector_name
    JOIN selector_timestamp_counts rc
      ON rc.emar_id=a.emar_id AND rc.selector_name=r.selector_name
    LEFT JOIN selector_pair_overlap_counts o
      ON o.emar_id=a.emar_id AND o.left_selector=l.selector_name
     AND o.right_selector=r.selector_name
), candidate_anchor_groups AS MATERIALIZED (
    SELECT subject_id,hadm_id,anchor_time,count(*) AS candidate_events,
           count(DISTINCT proxy_dose_meq) AS distinct_proxy_doses,
           min(proxy_dose_meq) AS minimum_proxy_dose_meq,
           max(proxy_dose_meq) AS maximum_proxy_dose_meq
    FROM proxy_anchors
    GROUP BY subject_id,hadm_id,anchor_time
), candidate_interval_pairs AS MATERIALIZED (
    -- Half-open assumed intervals [anchor,proxy_end); emar_id is used only as an
    -- internal stable pair key and is never emitted.
    SELECT a.subject_id,a.hadm_id,
           least(a.proxy_dose_meq,b.proxy_dose_meq) AS lower_proxy_dose_meq,
           greatest(a.proxy_dose_meq,b.proxy_dose_meq) AS higher_proxy_dose_meq,
           CASE WHEN a.anchor_time=b.anchor_time THEN 'same_anchor'
                WHEN greatest(a.anchor_time,b.anchor_time)
                       <least(a.proxy_end_time,b.proxy_end_time)
                  THEN 'positive_proxy_interval_overlap'
                WHEN greatest(a.anchor_time,b.anchor_time)
                       =least(a.proxy_end_time,b.proxy_end_time)
                  THEN 'boundary_touch'
                ELSE 'disjoint' END AS interval_relation,
           extract(epoch FROM (
             least(a.proxy_end_time,b.proxy_end_time)
             -greatest(a.anchor_time,b.anchor_time)))/3600.0
             AS signed_intersection_hours
    FROM proxy_anchors a JOIN proxy_anchors b
      ON b.subject_id=a.subject_id AND b.hadm_id=a.hadm_id
     AND b.emar_id>a.emar_id
), selected_timestamp_reuse_groups AS MATERIALIZED (
    SELECT selector_name,subject_id,hadm_id,selected_time,
           count(*) AS candidate_selections,
           count(DISTINCT emar_id) AS distinct_candidate_events,
           count(DISTINCT proxy_dose_meq) AS distinct_proxy_doses
    FROM raw_selected_timestamps
    GROUP BY selector_name,subject_id,hadm_id,selected_time
), profiles(profile_section,dimensions,source_rows,emar_events,counters) AS (
    SELECT 'assumed_rate_summary',
           jsonb_build_object(
             'analysis_scope','fixed-page-sample conservative source candidates',
             'proxy_scope','paper positive values 10/20/40 mEq',
             'assumed_rate_meq_per_hour',10,
             'target_offset_after_proxy_end_hours',3),
           count(*)::bigint,count(*)::bigint,
           jsonb_build_object(
             'distinct_subjects',count(DISTINCT subject_id),
             'distinct_admissions',count(DISTINCT (subject_id,hadm_id)),
             'source_candidate_events',(SELECT count(*) FROM candidate_anchors),
             'proxy_analysis_events',count(*),
             'outside_proxy_analysis_events',
                 (SELECT count(*) FROM candidate_anchors)-count(*),
             'paper_value_candidate_events',
                 (SELECT count(*) FROM candidate_anchors
                   WHERE paper_action_relation='matches_positive_paper_action_value'),
             'expected_candidate_selector_rows',count(*)*6,
             'candidate_selector_rows',(SELECT count(*) FROM selector_event_shapes),
             'selected_timestamp_groups',(SELECT count(*) FROM selected_group_shapes),
             'selected_lab_rows',
                 (SELECT coalesce(sum(lab_rows),0) FROM selected_group_shapes),
             'repeated_candidate_anchor_groups',
                 (SELECT count(*) FROM candidate_anchor_groups
                   WHERE candidate_events>1),
             'candidate_interval_pairs',(SELECT count(*) FROM candidate_interval_pairs),
             'positive_overlap_or_same_anchor_pairs',
                 (SELECT count(*) FROM candidate_interval_pairs
                   WHERE interval_relation IN
                     ('same_anchor','positive_proxy_interval_overlap')),
             'focal_events_with_other_candidate_in_anchor_to_proxy_end',
                 (SELECT count(*) FROM proxy_intervening_candidate_counts
                   WHERE anchor_to_proxy_end_candidates>0),
             'focal_events_with_other_candidate_in_proxy_end_to_target',
                 (SELECT count(*) FROM proxy_intervening_candidate_counts
                   WHERE proxy_end_to_target_candidates>0),
             'reused_selected_timestamp_groups',
                 (SELECT count(*) FROM selected_timestamp_reuse_groups
                   WHERE distinct_candidate_events>1))
    FROM proxy_anchors
    UNION ALL
    SELECT 'paper_scope_conservation',
           jsonb_build_object(
             'paper_action_relation',paper_action_relation,
             'included_in_proxy_analysis',product_component_sum_meq IN (10,20,40),
             'component_sum_bucket',component_sum_bucket,
             'completeness_evidence',completeness_evidence),
           count(*)::bigint,count(*)::bigint,
           jsonb_build_object(
             'distinct_subjects',count(DISTINCT subject_id),
             'distinct_admissions',count(DISTINCT (subject_id,hadm_id)),
             'candidate_events',count(*))
    FROM candidate_anchors
    GROUP BY paper_action_relation,product_component_sum_meq IN (10,20,40),
             component_sum_bucket,completeness_evidence
    UNION ALL
    SELECT 'dose_clock_shape',
           jsonb_build_object(
             'proxy_dose_meq',proxy_dose_meq,
             'assumed_rate_meq_per_hour',10,
             'assumed_duration_hours',proxy_dose_meq/10.0,
             'target_lag_from_anchor_hours',proxy_dose_meq/10.0+3.0,
             'completeness_evidence',completeness_evidence),
           count(*)::bigint,count(*)::bigint,
           jsonb_build_object(
             'distinct_subjects',count(DISTINCT subject_id),
             'distinct_admissions',count(DISTINCT (subject_id,hadm_id)))
    FROM proxy_anchors
    GROUP BY proxy_dose_meq,completeness_evidence
    UNION ALL
    SELECT 'selector_status',
           jsonb_build_object(
             'selector_name',selector_name,
             'selection_policy',selection_policy,
             'selector_status',selector_status,
             'proxy_dose_meq',proxy_dose_meq,
             'completeness_evidence',completeness_evidence),
           count(*)::bigint,count(*)::bigint,
           jsonb_build_object(
             'distinct_subjects',count(DISTINCT subject_id),
             'distinct_admissions',count(DISTINCT (subject_id,hadm_id)),
             'selected_timestamp_groups',sum(selected_timestamp_groups),
             'selected_lab_rows',sum(selected_lab_rows),
             'tied_timestamp_groups',sum(tied_timestamp_groups))
    FROM selector_event_shapes
    GROUP BY selector_name,selection_policy,selector_status,
             proxy_dose_meq,completeness_evidence
    UNION ALL
    SELECT 'selector_phase',
           jsonb_build_object(
             'selector_name',selector_name,
             'selected_phase',selected_phase,
             'proxy_dose_meq',proxy_dose_meq,
             'timestamp_group_tied',lab_rows>1,
             'completeness_evidence',completeness_evidence),
           count(*)::bigint,count(DISTINCT emar_id)::bigint,
           jsonb_build_object(
             'selected_timestamp_groups',count(*),
             'selected_lab_rows',sum(lab_rows),
             'distinct_subjects',count(DISTINCT subject_id),
             'distinct_admissions',count(DISTINCT (subject_id,hadm_id)))
    FROM selected_group_shapes
    GROUP BY selector_name,selected_phase,proxy_dose_meq,
             lab_rows>1,completeness_evidence
    UNION ALL
    SELECT 'selector_lag_summary',
           jsonb_build_object(
             'selector_name',selector_name,
             'selected_phase',selected_phase,
             'denominator','selected_timestamp_groups_only',
             'no_selected_timestamp_accounted_in','selector_status',
             'proxy_dose_meq',proxy_dose_meq,
             'completeness_evidence',completeness_evidence),
           count(*)::bigint,count(DISTINCT emar_id)::bigint,
           jsonb_build_object(
             'selected_timestamp_groups',count(*),
             'candidate_events_with_selected_timestamp',count(DISTINCT emar_id),
             'no_selected_timestamp_rows_included',0,
             'denominator_is_all_proxy_candidate_events',false,
             'minimum_anchor_lag_hours',min(anchor_lag_hours),
             'median_anchor_lag_hours',percentile_cont(0.5)
                WITHIN GROUP (ORDER BY anchor_lag_hours),
             'maximum_anchor_lag_hours',max(anchor_lag_hours),
             'minimum_proxy_end_lag_hours',min(proxy_end_lag_hours),
             'median_proxy_end_lag_hours',percentile_cont(0.5)
                WITHIN GROUP (ORDER BY proxy_end_lag_hours),
             'maximum_proxy_end_lag_hours',max(proxy_end_lag_hours),
             'minimum_target_lag_hours',min(target_lag_hours),
             'median_target_lag_hours',percentile_cont(0.5)
                WITHIN GROUP (ORDER BY target_lag_hours),
             'maximum_target_lag_hours',max(target_lag_hours),
             'minimum_absolute_target_lag_hours',min(absolute_target_lag_hours),
             'median_absolute_target_lag_hours',percentile_cont(0.5)
                WITHIN GROUP (ORDER BY absolute_target_lag_hours),
             'maximum_absolute_target_lag_hours',max(absolute_target_lag_hours))
    FROM selected_group_shapes
    GROUP BY selector_name,selected_phase,proxy_dose_meq,completeness_evidence
    UNION ALL
    SELECT 'selector_lag_bucket',
           jsonb_build_object(
             'selector_name',selector_name,
             'lag_reference',selector_lag_reference,
             'lag_direction_or_phase',selector_lag_direction,
             'fixed_lag_bucket',selector_lag_bucket,
             'denominator','selected_timestamp_groups_only',
             'no_selected_timestamp_accounted_in','selector_status',
             'proxy_dose_meq',proxy_dose_meq,
             'completeness_evidence',completeness_evidence),
           count(*)::bigint,count(DISTINCT emar_id)::bigint,
           jsonb_build_object(
             'selected_timestamp_groups',count(*),
             'candidate_events_with_selected_timestamp',count(DISTINCT emar_id),
             'no_selected_timestamp_rows_included',0,
             'denominator_is_all_proxy_candidate_events',false,
             'selected_lab_rows',sum(lab_rows),
             'distinct_subjects',count(DISTINCT subject_id),
             'distinct_admissions',count(DISTINCT (subject_id,hadm_id)),
             'timestamp_group_ties',count(*) FILTER (WHERE lab_rows>1))
    FROM selected_group_shapes
    GROUP BY selector_name,selector_lag_reference,selector_lag_direction,
             selector_lag_bucket,proxy_dose_meq,completeness_evidence
    UNION ALL
    SELECT 'selector_quality_shape',
           jsonb_build_object(
             'selector_name',selector_name,
             'selected_phase',selected_phase,
             'proxy_dose_meq',proxy_dose_meq,
             'timestamp_group_tied',lab_rows>1,
             'itemid_pattern',itemid_pattern,
             'has_finite_value',finite_value_rows>0,
             'finite_value_conflict_class',
                 CASE WHEN distinct_finite_values=0 THEN 'no_finite_value'
                      WHEN distinct_finite_values=1 THEN 'one_distinct_finite_value'
                      ELSE 'multiple_distinct_finite_values' END,
             'has_expected_unit',expected_unit_rows>0,
             'has_finite_expected_unit',finite_expected_unit_rows>0,
             'finite_expected_unit_value_conflict_class',
                 CASE WHEN distinct_finite_expected_unit_values=0
                        THEN 'no_finite_expected_unit_value'
                      WHEN distinct_finite_expected_unit_values=1
                        THEN 'one_distinct_finite_expected_unit_value'
                      ELSE 'multiple_distinct_finite_expected_unit_values' END,
             'value_row_partition_holds',
                 lab_rows=finite_value_rows+missing_value_rows+nonfinite_value_rows,
             'missing_or_nonfinite_partition_holds',
                 missing_or_nonfinite_value_rows=missing_value_rows+nonfinite_value_rows,
             'all_rows_valid_available_by_target',
                 valid_available_by_target_rows=lab_rows,
             'has_missing_storetime',missing_storetime_rows>0,
             'has_reversed_storetime',reversed_storetime_rows>0,
             'has_storetime_after_target',storetime_after_target_rows>0,
             'completeness_evidence',completeness_evidence),
           count(*)::bigint,count(DISTINCT emar_id)::bigint,
           jsonb_build_object(
             'selected_timestamp_groups',count(*),
             'selected_lab_rows',sum(lab_rows),
             'finite_value_rows',sum(finite_value_rows),
             'missing_value_rows',sum(missing_value_rows),
             'nonfinite_value_rows',sum(nonfinite_value_rows),
             'expected_unit_rows',sum(expected_unit_rows),
             'finite_expected_unit_rows',sum(finite_expected_unit_rows),
             'missing_or_nonfinite_value_rows',
                 sum(missing_or_nonfinite_value_rows),
             'maximum_distinct_finite_values_in_timestamp_group',
                 max(distinct_finite_values),
             'maximum_distinct_finite_expected_unit_values_in_timestamp_group',
                 max(distinct_finite_expected_unit_values),
             'finite_value_conflict_timestamp_groups',
                 count(*) FILTER (WHERE distinct_finite_values>1),
             'finite_expected_unit_value_conflict_timestamp_groups',
                 count(*) FILTER (WHERE distinct_finite_expected_unit_values>1),
             'value_partition_failure_timestamp_groups',
                 count(*) FILTER (WHERE lab_rows<>
                   finite_value_rows+missing_value_rows+nonfinite_value_rows),
             'missing_or_nonfinite_partition_failure_timestamp_groups',
                 count(*) FILTER (WHERE missing_or_nonfinite_value_rows<>
                   missing_value_rows+nonfinite_value_rows),
             'missing_unit_rows',sum(missing_unit_rows),
             'other_unit_rows',sum(other_unit_rows),
             'missing_storetime_rows',sum(missing_storetime_rows),
             'reversed_storetime_rows',sum(reversed_storetime_rows),
             'valid_available_by_target_rows',
                 sum(valid_available_by_target_rows),
             'storetime_after_target_rows',sum(storetime_after_target_rows),
             'multiple_itemid_timestamp_groups',
                 count(*) FILTER (WHERE distinct_itemids>1))
    FROM selected_group_shapes
    GROUP BY selector_name,selected_phase,proxy_dose_meq,lab_rows>1,itemid_pattern,
             finite_value_rows>0,
             CASE WHEN distinct_finite_values=0 THEN 'no_finite_value'
                  WHEN distinct_finite_values=1 THEN 'one_distinct_finite_value'
                  ELSE 'multiple_distinct_finite_values' END,
             expected_unit_rows>0,
             finite_expected_unit_rows>0,
             CASE WHEN distinct_finite_expected_unit_values=0
                    THEN 'no_finite_expected_unit_value'
                  WHEN distinct_finite_expected_unit_values=1
                    THEN 'one_distinct_finite_expected_unit_value'
                  ELSE 'multiple_distinct_finite_expected_unit_values' END,
             lab_rows=finite_value_rows+missing_value_rows+nonfinite_value_rows,
             missing_or_nonfinite_value_rows=missing_value_rows+nonfinite_value_rows,
             valid_available_by_target_rows=lab_rows,
             missing_storetime_rows>0,reversed_storetime_rows>0,
             storetime_after_target_rows>0,completeness_evidence
    UNION ALL
    SELECT 'candidate_proxy_clock_intervening_shape',
           jsonb_build_object(
             'intervening_candidate_scope',
                 'fixed SYSTEM 1 percent page-sample source candidates only',
             'intervening_candidate_coverage_complete',false,
             'proxy_dose_meq',proxy_dose_meq,
             'anchor_to_proxy_end_candidate_count_class',
                 CASE WHEN anchor_to_proxy_end_candidates=0 THEN 'none'
                      WHEN anchor_to_proxy_end_candidates=1 THEN 'one'
                      ELSE 'multiple' END,
             'proxy_end_to_target_candidate_count_class',
                 CASE WHEN proxy_end_to_target_candidates=0 THEN 'none'
                      WHEN proxy_end_to_target_candidates=1 THEN 'one'
                      ELSE 'multiple' END,
             'has_outside_paper_value_candidate_in_anchor_to_proxy_end',
                 anchor_to_proxy_end_outside_paper_value_candidates>0,
             'has_outside_paper_value_candidate_in_proxy_end_to_target',
                 proxy_end_to_target_outside_paper_value_candidates>0,
             'completeness_evidence',completeness_evidence),
           count(*)::bigint,count(*)::bigint,
           jsonb_build_object(
             'distinct_subjects',count(DISTINCT subject_id),
             'distinct_admissions',count(DISTINCT (subject_id,hadm_id)),
             'anchor_to_proxy_end_candidate_events',
                 sum(anchor_to_proxy_end_candidates),
             'anchor_to_proxy_end_paper_value_candidate_events',
                 sum(anchor_to_proxy_end_paper_value_candidates),
             'anchor_to_proxy_end_outside_paper_value_candidate_events',
                 sum(anchor_to_proxy_end_outside_paper_value_candidates),
             'proxy_end_to_target_candidate_events',
                 sum(proxy_end_to_target_candidates),
             'proxy_end_to_target_paper_value_candidate_events',
                 sum(proxy_end_to_target_paper_value_candidates),
             'proxy_end_to_target_outside_paper_value_candidate_events',
                 sum(proxy_end_to_target_outside_paper_value_candidates))
    FROM proxy_intervening_candidate_counts
    GROUP BY proxy_dose_meq,
             CASE WHEN anchor_to_proxy_end_candidates=0 THEN 'none'
                  WHEN anchor_to_proxy_end_candidates=1 THEN 'one'
                  ELSE 'multiple' END,
             CASE WHEN proxy_end_to_target_candidates=0 THEN 'none'
                  WHEN proxy_end_to_target_candidates=1 THEN 'one'
                  ELSE 'multiple' END,
             anchor_to_proxy_end_outside_paper_value_candidates>0,
             proxy_end_to_target_outside_paper_value_candidates>0,
             completeness_evidence
    UNION ALL
    SELECT 'selected_timestamp_intervening_shape',
           jsonb_build_object(
             'intervening_candidate_scope',
                 'fixed SYSTEM 1 percent page-sample source candidates only',
             'intervening_candidate_coverage_complete',false,
             'selector_name',selector_name,
             'proxy_dose_meq',proxy_dose_meq,
             'selected_time_relation',
                 CASE WHEN selected_time<=proxy_end_time
                        THEN 'at_or_before_proxy_end_no_forward_interval'
                      WHEN selected_time<=target_time
                        THEN 'post_proxy_end_through_target'
                      ELSE 'after_target' END,
             'proxy_end_to_selected_candidate_count_class',
                 CASE WHEN proxy_end_to_selected_candidates=0 THEN 'none'
                      WHEN proxy_end_to_selected_candidates=1 THEN 'one'
                      ELSE 'multiple' END,
             'has_outside_paper_value_candidate',
                 proxy_end_to_selected_outside_paper_value_candidates>0,
             'completeness_evidence',completeness_evidence),
           count(*)::bigint,count(DISTINCT emar_id)::bigint,
           jsonb_build_object(
             'selected_timestamp_groups',count(*),
             'distinct_subjects',count(DISTINCT subject_id),
             'distinct_admissions',count(DISTINCT (subject_id,hadm_id)),
             'proxy_end_to_selected_candidate_events',
                 sum(proxy_end_to_selected_candidates),
             'proxy_end_to_selected_paper_value_candidate_events',
                 sum(proxy_end_to_selected_paper_value_candidates),
             'proxy_end_to_selected_outside_paper_value_candidate_events',
                 sum(proxy_end_to_selected_outside_paper_value_candidates))
    FROM selected_timestamp_intervening_counts
    GROUP BY selector_name,proxy_dose_meq,
             CASE WHEN selected_time<=proxy_end_time
                    THEN 'at_or_before_proxy_end_no_forward_interval'
                  WHEN selected_time<=target_time
                    THEN 'post_proxy_end_through_target'
                  ELSE 'after_target' END,
             CASE WHEN proxy_end_to_selected_candidates=0 THEN 'none'
                  WHEN proxy_end_to_selected_candidates=1 THEN 'one'
                  ELSE 'multiple' END,
             proxy_end_to_selected_outside_paper_value_candidates>0,
             completeness_evidence
    UNION ALL
    SELECT 'selector_pair_overlap',
           jsonb_build_object(
             'left_selector',left_selector,
             'right_selector',right_selector,
             'overlap_status',overlap_status,
             'left_timestamp_group_class',
                 CASE WHEN left_timestamp_groups=0 THEN 'none'
                      WHEN left_timestamp_groups=1 THEN 'one' ELSE 'multiple' END,
             'right_timestamp_group_class',
                 CASE WHEN right_timestamp_groups=0 THEN 'none'
                      WHEN right_timestamp_groups=1 THEN 'one' ELSE 'multiple' END,
             'proxy_dose_meq',proxy_dose_meq,
             'completeness_evidence',completeness_evidence),
           count(*)::bigint,count(*)::bigint,
           jsonb_build_object(
             'distinct_subjects',count(DISTINCT subject_id),
             'distinct_admissions',count(DISTINCT (subject_id,hadm_id)),
             'left_selected_timestamp_groups',sum(left_timestamp_groups),
             'right_selected_timestamp_groups',sum(right_timestamp_groups),
             'overlap_timestamp_groups',sum(overlap_timestamp_groups))
    FROM selector_pair_shapes
    GROUP BY left_selector,right_selector,overlap_status,
             CASE WHEN left_timestamp_groups=0 THEN 'none'
                  WHEN left_timestamp_groups=1 THEN 'one' ELSE 'multiple' END,
             CASE WHEN right_timestamp_groups=0 THEN 'none'
                  WHEN right_timestamp_groups=1 THEN 'one' ELSE 'multiple' END,
             proxy_dose_meq,completeness_evidence
    UNION ALL
    SELECT 'candidate_anchor_group_shape',
           jsonb_build_object(
             'candidate_count_class',
                 CASE WHEN candidate_events=1 THEN 'one' ELSE 'multiple' END,
             'distinct_proxy_dose_class',
                 CASE WHEN distinct_proxy_doses=1 THEN 'one' ELSE 'multiple' END,
             'minimum_proxy_dose_meq',minimum_proxy_dose_meq,
             'maximum_proxy_dose_meq',maximum_proxy_dose_meq),
           count(*)::bigint,sum(candidate_events)::bigint,
           jsonb_build_object(
             'anchor_timestamp_groups',count(*),
             'candidate_events',sum(candidate_events),
             'distinct_subjects',count(DISTINCT subject_id),
             'distinct_admissions',count(DISTINCT (subject_id,hadm_id)))
    FROM candidate_anchor_groups
    GROUP BY CASE WHEN candidate_events=1 THEN 'one' ELSE 'multiple' END,
             CASE WHEN distinct_proxy_doses=1 THEN 'one' ELSE 'multiple' END,
             minimum_proxy_dose_meq,maximum_proxy_dose_meq
    UNION ALL
    SELECT 'candidate_proxy_interval_pair_shape',
           jsonb_build_object(
             'interval_semantics','half-open assumed [anchor, proxy_end)',
             'interval_relation',interval_relation,
             'lower_proxy_dose_meq',lower_proxy_dose_meq,
             'higher_proxy_dose_meq',higher_proxy_dose_meq),
           count(*)::bigint,count(*)::bigint,
           jsonb_build_object(
             'candidate_pairs',count(*),
             'distinct_subjects',count(DISTINCT subject_id),
             'distinct_admissions',count(DISTINCT (subject_id,hadm_id)),
             'minimum_signed_intersection_hours',
                 min(signed_intersection_hours),
             'median_signed_intersection_hours',percentile_cont(0.5)
                 WITHIN GROUP (ORDER BY signed_intersection_hours),
             'maximum_signed_intersection_hours',
                 max(signed_intersection_hours))
    FROM candidate_interval_pairs
    GROUP BY interval_relation,lower_proxy_dose_meq,higher_proxy_dose_meq
    UNION ALL
    SELECT 'selected_timestamp_reuse_shape',
           jsonb_build_object(
             'selector_name',selector_name,
             'candidate_reuse_class',
                 CASE WHEN distinct_candidate_events=1 THEN 'one_candidate'
                      ELSE 'multiple_candidates' END,
             'candidate_selection_count_class',
                 CASE WHEN candidate_selections=1 THEN 'one'
                      WHEN candidate_selections=2 THEN 'two' ELSE 'three_or_more' END,
             'distinct_proxy_dose_class',
                 CASE WHEN distinct_proxy_doses=1 THEN 'one' ELSE 'multiple' END),
           count(*)::bigint,sum(candidate_selections)::bigint,
           jsonb_build_object(
             'selected_timestamp_groups',count(*),
             'candidate_selections',sum(candidate_selections),
             'reused_timestamp_groups',count(*) FILTER (
                 WHERE distinct_candidate_events>1),
             'distinct_subjects',count(DISTINCT subject_id),
             'distinct_admissions',count(DISTINCT (subject_id,hadm_id)))
    FROM selected_timestamp_reuse_groups
    GROUP BY selector_name,
             CASE WHEN distinct_candidate_events=1 THEN 'one_candidate'
                  ELSE 'multiple_candidates' END,
             CASE WHEN candidate_selections=1 THEN 'one'
                  WHEN candidate_selections=2 THEN 'two' ELSE 'three_or_more' END,
             CASE WHEN distinct_proxy_doses=1 THEN 'one' ELSE 'multiple' END
)
SELECT profile_section,dimensions,source_rows,emar_events,
       counters || jsonb_build_object(
         'system_sample_percent',1.0,
         'sample_seed',20261011,
         'shared_snapshot',false,
         'page_sample_is_representative',false,
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
         'proxy_rate_is_observed',false,
         'proxy_end_is_observed',false,
         'target_time_is_observed_label_time',false,
         'maximum_lag_applied',false,
         'lab_value_used_to_select_timestamp',false,
         'lab_unit_used_to_select_timestamp',false,
         'storetime_used_for_charttime_only_selectors',false,
         'latest_available_selector_uses_declared_storetime_gate',true,
         'nearest_selector_retains_all_equidistant_timestamp_groups',true,
         'timestamp_ties_retain_all_lab_rows',true,
         'next_observed_context_recovered',false,
         'nearest_target_is_paper_label',false,
         'latest_available_is_outcome',false,
         'counterfactual_clock_constructed',false,
         'intervening_candidate_coverage_complete',false,
         'intervening_treatment_excluded',false,
         'episode_overlap_resolved',false,
         'selected_lab_uniqueness_established',false,
         'paper_label_selector_recovered',false,
         'one_selector_adopted_as_label',false,
         'tie_broken_by_id',false,
         'missing_result_imputed',false,
         'llm_prediction_run',false,
         'reward_computed',false,
         'raw_identifiers_times_values_emitted',false,
         'proxy_clock_rule','10 mEq/hour from eMAR administration-record anchor; target is proxy end plus 3 hours')
         AS counters
FROM profiles
ORDER BY profile_section,source_rows DESC,dimensions;
