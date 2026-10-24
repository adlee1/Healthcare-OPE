-- PRIVATE ROW OUTPUT. Full exact-3%-prescription pharmacy-linked eMAR timeline:
-- one row per source head, including missing time/identity, unknown statuses,
-- known-other-drug heads, stops, confirmations, and non-administration records.
-- No sampling, source-row filter, clinical lab, location, action or cohort gate.
-- Read only; runner should set statement_timeout <= 120000 ms.
-- The downstream state machine must retain anomalous/other-drug heads as stream
-- interruptions. Not Given, missing amount, or absent start does not prove zero.
-- Missing head names use the explicit same-order 3% identity assumption from 303.
-- Query 181 identified Thiamine as the one known other head. Other nonempty
-- nonmatching names remain unrecognized, rather than silently irrelevant.
-- Routes follow 303: IV / IV DRIP, or exact-order IV fallback for absent detail
-- route, with conflicting/non-whitelisted explicit routes retained as problems.
-- Current parent rate is a rate field, not an integrated or measured dose.
-- Product dose_given is parsed per product; neither product_amount_given nor
-- dose_due nor bag size is read. The product sum below is a diagnostic only.
-- A single Administered product with positive mL/mEq can provide a recorded-volume
-- candidate under the identity/route assumptions; other/multiple product cases
-- remain unresolved. mEq / 0.513 converts to 3% mL; it does not select an action.
WITH orders AS MATERIALIZED (
    SELECT pharmacy_id, min(subject_id) AS source_order_subject_id,
           min(hadm_id) AS source_order_hadm_id,
           count(DISTINCT subject_id) AS order_subjects,
           count(DISTINCT hadm_id) AS order_admissions,
           count(*) FILTER (WHERE subject_id IS NULL OR hadm_id IS NULL) AS order_missing_ids,
           count(*) FILTER (WHERE upper(trim(route)) IN ('IV','IV DRIP')) AS order_iv_route_rows,
           count(*) FILTER (WHERE nullif(trim(route),'') IS NOT NULL
               AND upper(trim(route)) NOT IN ('IV','IV DRIP')) AS order_other_route_rows
    FROM mimiciv_hosp.prescriptions
    WHERE drug = 'Sodium Chloride 3% (Hypertonic)'
    GROUP BY pharmacy_id
), events AS MATERIALIZED (
    SELECT e.emar_id, e.emar_seq, e.subject_id, e.hadm_id, e.pharmacy_id,
           e.event_txt, e.charttime, e.storetime,
           o.source_order_subject_id, o.source_order_hadm_id,
           o.order_subjects, o.order_admissions, o.order_missing_ids,
           o.order_iv_route_rows, o.order_other_route_rows,
           (e.subject_id IS NOT NULL AND e.hadm_id IS NOT NULL
            AND e.subject_id = o.source_order_subject_id AND e.hadm_id = o.source_order_hadm_id
            AND o.order_subjects = 1 AND o.order_admissions = 1 AND o.order_missing_ids = 0) AS identity_ok,
           CASE WHEN nullif(trim(e.medication),'') IS NULL THEN 'missing_head_order_assumption'
                WHEN e.medication = 'Sodium Chloride 3% (Hypertonic)' THEN 'exact_saline_head'
                WHEN e.medication = 'Thiamine' THEN 'known_other_head'
                ELSE 'unrecognized_nonempty_head' END AS head_source
    FROM orders o JOIN mimiciv_hosp.emar e ON e.pharmacy_id = o.pharmacy_id
), details AS MATERIALIZED (
    SELECT e.emar_id AS event_key, d.emar_id AS detail_emar_id, d.parent_field_ordinal,
           (d.emar_id IS NOT NULL AND
            (d.subject_id IS DISTINCT FROM e.subject_id OR d.emar_seq IS DISTINCT FROM e.emar_seq
             OR (d.pharmacy_id IS NOT NULL AND d.pharmacy_id <> e.pharmacy_id))) AS detail_identity_bad,
           d.infusion_rate, d.infusion_rate_unit, d.route, d.infusion_complete,
           nullif(trim(d.dose_given),'') IS NOT NULL AS dose_given_present,
           d.dose_given_unit,
           CASE WHEN length(trim(d.dose_given)) BETWEEN 1 AND 64
                     AND trim(d.dose_given) ~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)$'
                THEN trim(d.dose_given)::numeric END AS dose_given_numeric,
           CASE WHEN upper(trim(d.dose_given_unit)) = 'ML' THEN 'mL'
                WHEN upper(trim(d.dose_given_unit)) = 'MEQ' THEN 'mEq'
                WHEN nullif(trim(d.dose_given_unit),'') IS NULL THEN 'missing'
                ELSE 'other' END AS dose_unit_class,
           CASE WHEN upper(trim(d.complete_dose_not_given)) IN ('Y','YES') THEN 'yes'
                WHEN upper(trim(d.complete_dose_not_given)) IN ('N','NO') THEN 'no'
                WHEN nullif(trim(d.complete_dose_not_given),'') IS NULL THEN 'missing'
                ELSE 'other' END AS incomplete_dose_class
    FROM events e LEFT JOIN mimiciv_hosp.emar_detail d ON d.emar_id = e.emar_id
), products AS MATERIALIZED (
    SELECT d.*,
           CASE WHEN dose_given_numeric > 0 AND dose_unit_class = 'mL' THEN dose_given_numeric
                WHEN dose_given_numeric > 0 AND dose_unit_class = 'mEq'
                     THEN dose_given_numeric / 0.513 END AS positive_recorded_volume_ml,
           CASE WHEN dose_given_numeric > 0 AND dose_unit_class = 'mL' THEN dose_given_numeric * 0.513
                WHEN dose_given_numeric > 0 AND dose_unit_class = 'mEq'
                     THEN dose_given_numeric END AS positive_recorded_sodium_meq
    FROM details d
), shapes AS MATERIALIZED (
    SELECT event_key,
           count(detail_emar_id) FILTER (WHERE parent_field_ordinal IS NULL) AS parent_rows,
           count(detail_emar_id) FILTER (WHERE parent_field_ordinal IS NOT NULL) AS product_rows,
           count(*) FILTER (WHERE detail_identity_bad) AS bad_detail_identity_rows,
           min(infusion_rate) FILTER (WHERE parent_field_ordinal IS NULL) AS parent_rate_raw,
           min(infusion_rate_unit) FILTER (WHERE parent_field_ordinal IS NULL) AS parent_rate_unit,
           count(detail_emar_id) FILTER (WHERE upper(trim(route)) IN ('IV','IV DRIP')) AS detail_iv_route_rows,
           count(detail_emar_id) FILTER (WHERE nullif(trim(route),'') IS NOT NULL
               AND upper(trim(route)) NOT IN ('IV','IV DRIP')) AS detail_other_route_rows,
           bool_or(upper(trim(infusion_complete)) IN ('Y','YES')) AS complete_yes,
           count(*) FILTER (WHERE incomplete_dose_class = 'yes') AS incomplete_dose_yes_rows,
           min(positive_recorded_volume_ml) FILTER (WHERE parent_field_ordinal IS NOT NULL) AS sole_product_volume_ml,
           min(positive_recorded_sodium_meq) FILTER (WHERE parent_field_ordinal IS NOT NULL) AS sole_product_sodium_meq,
           count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL AND dose_given_present) AS product_dose_present_rows,
           count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL AND dose_given_numeric IS NOT NULL) AS product_dose_numeric_rows,
           count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL AND positive_recorded_volume_ml IS NOT NULL) AS product_positive_known_unit_rows,
           count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL AND dose_given_numeric <= 0) AS product_nonpositive_rows,
           count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL AND dose_given_present
                             AND dose_given_numeric IS NULL) AS product_unparsed_rows,
           count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL AND dose_given_numeric > 0
                             AND dose_unit_class NOT IN ('mL','mEq')) AS product_positive_unknown_unit_rows,
           sum(positive_recorded_volume_ml) FILTER (WHERE parent_field_ordinal IS NOT NULL) AS product_volume_sum_ml_diagnostic,
           string_agg(DISTINCT dose_unit_class, ',' ORDER BY dose_unit_class)
               FILTER (WHERE parent_field_ordinal IS NOT NULL) AS product_dose_unit_classes
    FROM products GROUP BY event_key
), parsed AS MATERIALIZED (
    SELECT e.*, s.parent_rows, s.product_rows, s.bad_detail_identity_rows,
           s.parent_rate_raw, s.parent_rate_unit, s.detail_iv_route_rows, s.detail_other_route_rows,
           s.complete_yes, s.incomplete_dose_yes_rows, s.sole_product_volume_ml, s.sole_product_sodium_meq,
           s.product_dose_present_rows, s.product_dose_numeric_rows, s.product_positive_known_unit_rows,
           s.product_nonpositive_rows, s.product_unparsed_rows, s.product_positive_unknown_unit_rows,
           s.product_volume_sum_ml_diagnostic, s.product_dose_unit_classes,
           CASE WHEN s.detail_other_route_rows > 0 THEN 'detail_non_iv_or_unrecognized'
                WHEN s.detail_iv_route_rows > 0 AND e.order_other_route_rows > 0 THEN 'detail_order_route_conflict'
                WHEN s.detail_iv_route_rows > 0 THEN 'detail_iv'
                WHEN e.order_other_route_rows > 0 THEN 'prescription_non_iv_or_unrecognized'
                WHEN e.order_iv_route_rows > 0 THEN 'prescription_iv_fallback'
                ELSE 'route_missing' END AS route_class,
           CASE WHEN length(trim(s.parent_rate_raw)) BETWEEN 1 AND 64
                     AND trim(s.parent_rate_raw) ~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)$'
                THEN trim(s.parent_rate_raw)::numeric END AS parsed_parent_rate,
           count(*) FILTER (WHERE e.charttime IS NULL) OVER
               (PARTITION BY e.subject_id, e.hadm_id, e.pharmacy_id) AS stream_missing_time_heads,
           count(*) FILTER (WHERE e.identity_ok IS NOT TRUE) OVER
               (PARTITION BY e.pharmacy_id) AS pharmacy_identity_problem_heads,
           count(*) OVER
               (PARTITION BY e.subject_id, e.hadm_id, e.pharmacy_id, e.charttime) AS same_time_head_count
    FROM events e JOIN shapes s ON s.event_key = e.emar_id
), classified AS (
    SELECT p.*,
           CASE WHEN parent_rows <> 1 THEN 'parent_not_unique'
                WHEN nullif(trim(parent_rate_raw),'') IS NULL THEN 'missing'
                WHEN parsed_parent_rate IS NULL THEN 'unparsed'
                WHEN upper(trim(parent_rate_unit)) IS DISTINCT FROM 'ML/HR' THEN 'unit_not_ml_per_hour'
                WHEN parsed_parent_rate < 0 THEN 'negative'
                ELSE 'available' END AS parent_rate_class,
           CASE WHEN event_txt IS DISTINCT FROM 'Administered' THEN 'not_administered_status'
                WHEN identity_ok IS NOT TRUE OR bad_detail_identity_rows > 0 THEN 'identity_problem'
                WHEN head_source = 'known_other_head' THEN 'known_other_head'
                WHEN head_source = 'unrecognized_nonempty_head' THEN 'unrecognized_head'
                WHEN route_class NOT IN ('detail_iv','prescription_iv_fallback') THEN 'route_not_supported_iv'
                WHEN product_rows <> 1 THEN 'product_not_unique'
                WHEN sole_product_volume_ml IS NULL THEN 'no_positive_product_ml_or_meq'
                ELSE 'single_recorded_product_under_order_assumption' END AS administered_volume_class
    FROM parsed p
)
SELECT 'sodium_action_timeline_v1'::text AS definition_version,
       subject_id, hadm_id, pharmacy_id, emar_id, emar_seq,
       event_txt AS administration_status, charttime AS anchor_time, storetime AS emar_storetime,
       source_order_subject_id, source_order_hadm_id, order_subjects, order_admissions, order_missing_ids,
       identity_ok, identity_ok IS NOT TRUE OR bad_detail_identity_rows > 0 AS identity_bad,
       head_source, head_source = 'known_other_head' AS known_other_head,
       head_source NOT IN ('exact_saline_head','missing_head_order_assumption') AS head_identity_bad,
       route_class, route_class NOT IN ('detail_iv','prescription_iv_fallback') AS route_bad,
       order_iv_route_rows, order_other_route_rows,
       detail_iv_route_rows, detail_other_route_rows,
       detail_iv_route_rows + order_iv_route_rows > 0
           AND detail_other_route_rows + order_other_route_rows > 0 AS route_conflict,
       parent_rows, product_rows, bad_detail_identity_rows,
       parent_rate_class, parent_rate_unit,
       CASE WHEN parent_rate_class = 'available' THEN parsed_parent_rate END AS parent_rate_ml_per_hour,
       stream_missing_time_heads, pharmacy_identity_problem_heads, same_time_head_count,
       charttime IS NULL AS missing_charttime, storetime IS NULL AS missing_storetime,
       coalesce(storetime < charttime, false) AS reversed_storetime,
       complete_yes, incomplete_dose_yes_rows, product_dose_unit_classes,
       product_dose_present_rows, product_dose_numeric_rows, product_positive_known_unit_rows,
       product_nonpositive_rows, product_unparsed_rows, product_positive_unknown_unit_rows,
       product_volume_sum_ml_diagnostic,
       administered_volume_class,
       CASE WHEN administered_volume_class = 'single_recorded_product_under_order_assumption'
            THEN sole_product_volume_ml END AS single_administered_volume_ml,
       CASE WHEN administered_volume_class = 'single_recorded_product_under_order_assumption'
            THEN sole_product_sodium_meq END AS single_administered_sodium_meq,
       'exact_prescription_pharmacy_link_only'::text AS source_scope,
       false AS zero_action_assigned
FROM classified
ORDER BY subject_id, hadm_id, pharmacy_id, charttime NULLS LAST, emar_id;
