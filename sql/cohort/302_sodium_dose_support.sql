-- Mainline preparation: full exact-prescription sodium 3% source, aggregate only.
-- Run in a READ ONLY transaction with statement_timeout <= 120000 ms.
-- Scope is all eMAR heads linked to the distinct pharmacy IDs of the known
-- exact prescription name; there is no physical sample or LIMIT truncation.
-- This is complete for that declared source, not a synonym-completeness claim.
--
-- Existing query 181 evidence has missing medication on almost all such heads;
-- its one named non-saline head proves that pharmacy linkage alone is not
-- proof of product identity. We therefore preserve missing / exact / other
-- head classes. No raw medication, product, route, ID, timestamp or amount is
-- returned. Dose support means field availability, not verified actual dose.
-- Parent and product amounts are never added. Planned dose_due is never
-- substituted for dose_given; product_amount_given on continuous statuses is
-- never accumulated. A 500 mL product field is not 500 mEq.
--
-- Deterministic maximum output: 1 + (6*3) + (3*6*2*4) + (6*2*4)
-- + (6*2*4*4) + (6*3*11) = 601 rows. Counters across sections are overlapping.
WITH orders AS MATERIALIZED (
    SELECT pharmacy_id,
           count(*) AS prescription_rows,
           min(subject_id) AS order_subject,
           min(hadm_id) AS order_hadm,
           count(DISTINCT subject_id) AS order_subjects,
           count(DISTINCT (subject_id, hadm_id)) FILTER (WHERE subject_id IS NOT NULL AND hadm_id IS NOT NULL) AS order_admissions,
           count(*) FILTER (WHERE subject_id IS NULL OR hadm_id IS NULL) AS order_missing_ids
    FROM mimiciv_hosp.prescriptions
    WHERE drug = 'Sodium Chloride 3% (Hypertonic)'
    GROUP BY pharmacy_id
), events AS MATERIALIZED (
    SELECT e.emar_id, e.subject_id, e.hadm_id, e.emar_seq, e.pharmacy_id,
           e.charttime, e.storetime,
           CASE WHEN e.event_txt = 'Administered' THEN 'administered'
                WHEN e.event_txt IN ('Started', 'Delayed Started', 'Restarted') THEN 'start_like'
                WHEN e.event_txt = 'Confirmed' THEN 'confirmed'
                WHEN e.event_txt IN ('Stopped', 'Stopped - Unscheduled') THEN 'stop_like'
                WHEN e.event_txt = 'Not Given' THEN 'not_given'
                ELSE 'other_or_missing' END AS status_class,
           CASE WHEN nullif(trim(e.medication), '') IS NULL THEN 'head_name_missing'
                WHEN e.medication = 'Sodium Chloride 3% (Hypertonic)' THEN 'exact_saline_head'
                ELSE 'other_head_name' END AS head_class,
           (e.subject_id IS NOT NULL AND e.hadm_id IS NOT NULL
            AND o.order_subjects = 1 AND o.order_admissions = 1
            AND o.order_missing_ids = 0
            AND e.subject_id = o.order_subject AND e.hadm_id = o.order_hadm) AS identity_ok
    FROM orders o
    JOIN mimiciv_hosp.emar e ON e.pharmacy_id = o.pharmacy_id
), details AS MATERIALIZED (
    SELECT e.emar_id AS event_key, e.status_class, e.head_class, e.identity_ok,
           CASE WHEN d.parent_field_ordinal IS NULL THEN 'parent' ELSE 'product' END AS role_class,
           (d.subject_id IS DISTINCT FROM e.subject_id
            OR d.emar_seq IS DISTINCT FROM e.emar_seq
            OR (d.pharmacy_id IS NOT NULL AND d.pharmacy_id <> e.pharmacy_id)) AS detail_link_bad,
           d.dose_given, d.dose_given_unit, d.dose_due, d.dose_due_unit,
           d.product_amount_given, d.product_unit, d.infusion_rate, d.infusion_rate_unit,
           CASE WHEN upper(trim(d.infusion_complete)) IN ('Y', 'YES') THEN 'yes'
                WHEN upper(trim(d.infusion_complete)) IN ('N', 'NO') THEN 'no'
                WHEN nullif(trim(d.infusion_complete), '') IS NULL THEN 'missing'
                ELSE 'other' END AS complete_class,
           CASE WHEN upper(trim(d.complete_dose_not_given)) IN ('Y', 'YES') THEN 'yes'
                WHEN upper(trim(d.complete_dose_not_given)) IN ('N', 'NO') THEN 'no'
                WHEN nullif(trim(d.complete_dose_not_given), '') IS NULL THEN 'missing'
                ELSE 'other' END AS incomplete_class,
           upper(trim(d.new_iv_bag_hung)) IN ('Y', 'YES') AS new_bag_yes,
           nullif(trim(d.product_description), '') IS NOT NULL AS product_description_present
    FROM events e
    JOIN mimiciv_hosp.emar_detail d ON d.emar_id = e.emar_id
), quantities AS MATERIALIZED (
    SELECT d.event_key, d.status_class, d.head_class, d.identity_ok, d.role_class,
           d.detail_link_bad, d.complete_class, d.incomplete_class, d.new_bag_yes,
           q.quantity_kind,
           CASE WHEN upper(trim(q.unit_raw)) = 'ML' THEN 'mL'
                WHEN upper(trim(q.unit_raw)) = 'MEQ' THEN 'mEq'
                WHEN nullif(trim(q.unit_raw), '') IS NULL THEN 'missing'
                ELSE 'other' END AS unit_class,
           nullif(trim(q.quantity_raw), '') IS NOT NULL AS quantity_present,
           CASE WHEN length(trim(q.quantity_raw)) BETWEEN 1 AND 64
                     AND trim(q.quantity_raw) ~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)$'
                THEN trim(q.quantity_raw)::numeric END AS quantity_numeric
    FROM details d
    CROSS JOIN LATERAL (VALUES
        ('dose_given', d.dose_given, d.dose_given_unit),
        ('dose_due_planned', d.dose_due, d.dose_due_unit),
        ('product_amount', d.product_amount_given, d.product_unit)
    ) q(quantity_kind, quantity_raw, unit_raw)
), rates AS MATERIALIZED (
    SELECT d.*,
           CASE WHEN upper(trim(infusion_rate_unit)) = 'ML/HR' THEN 'mL_per_hour'
                WHEN upper(trim(infusion_rate_unit)) = 'MEQ/HR' THEN 'mEq_per_hour'
                WHEN nullif(trim(infusion_rate_unit), '') IS NULL THEN 'missing'
                ELSE 'other' END AS rate_unit_class,
           nullif(trim(infusion_rate), '') IS NOT NULL AS rate_present,
           CASE WHEN length(trim(infusion_rate)) BETWEEN 1 AND 64
                     AND trim(infusion_rate) ~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)$'
                THEN trim(infusion_rate)::numeric END AS rate_numeric
    FROM details d
), shapes AS MATERIALIZED (
    SELECT event_key,
           count(*) AS detail_rows,
           count(*) FILTER (WHERE role_class = 'parent') AS parent_rows,
           count(*) FILTER (WHERE role_class = 'product') AS product_rows,
           bool_or(detail_link_bad) AS any_bad_detail_link,
           bool_or(product_description_present) AS any_product_description,
           bool_or(complete_class = 'yes') AS any_complete_yes,
           bool_or(incomplete_class = 'yes') AS any_incomplete_yes,
           bool_or(rate_numeric > 0 AND rate_unit_class IN ('mL_per_hour', 'mEq_per_hour')) AS known_positive_rate
    FROM rates
    GROUP BY event_key
), amount_support AS MATERIALIZED (
    SELECT event_key,
           bool_or(quantity_kind = 'dose_given' AND role_class = 'parent'
                   AND quantity_numeric > 0 AND unit_class IN ('mL', 'mEq')) AS known_parent_dose,
           bool_or(quantity_kind = 'dose_given' AND role_class = 'product'
                   AND quantity_numeric > 0 AND unit_class IN ('mL', 'mEq')) AS known_product_dose,
           bool_or(quantity_kind = 'product_amount' AND role_class = 'product'
                   AND quantity_numeric > 0 AND unit_class IN ('mL', 'mEq')) AS known_product_amount,
           bool_or(quantity_kind = 'dose_due_planned' AND quantity_present) AS planned_dose_present
    FROM quantities
    GROUP BY event_key
), event_support AS MATERIALIZED (
    SELECT e.*, s.detail_rows, s.parent_rows, s.product_rows,
           s.any_bad_detail_link, s.any_product_description,
           s.any_complete_yes, s.any_incomplete_yes,
           a.known_parent_dose, a.known_product_dose, a.known_product_amount,
           s.known_positive_rate, a.planned_dose_present,
           CASE WHEN e.head_class = 'other_head_name' THEN 'other_head_requires_identity_resolution'
                WHEN e.identity_ok IS NOT TRUE THEN 'head_order_identity_problem'
                WHEN coalesce(s.detail_rows, 0) = 0 THEN 'no_detail_rows'
                WHEN s.any_bad_detail_link OR s.parent_rows <> 1 OR s.product_rows <> 1
                     THEN 'detail_link_or_shape_problem'
                WHEN s.any_incomplete_yes THEN 'explicit_incomplete_dose'
                WHEN a.known_parent_dose THEN 'positive_parent_dose_given_known_unit'
                WHEN a.known_product_dose THEN 'positive_product_dose_given_known_unit'
                WHEN a.known_product_amount THEN 'product_amount_without_dose_given'
                WHEN s.known_positive_rate THEN 'charted_rate_without_direct_amount'
                WHEN a.planned_dose_present THEN 'planned_quantity_only'
                ELSE 'no_recognized_positive_quantity_or_rate' END AS support_class
    FROM events e
    LEFT JOIN shapes s ON s.event_key = e.emar_id
    LEFT JOIN amount_support a ON a.event_key = e.emar_id
)
SELECT 'source_summary' AS section, '{}'::jsonb AS dimensions,
       count(*) AS records,
       jsonb_build_object(
           'subjects', count(DISTINCT subject_id),
           'admissions', count(DISTINCT (subject_id, hadm_id)) FILTER (WHERE subject_id IS NOT NULL AND hadm_id IS NOT NULL),
           'emar_ids', count(DISTINCT emar_id),
           'prescription_rows', (SELECT coalesce(sum(prescription_rows), 0) FROM orders),
           'pharmacy_ids', (SELECT count(*) FROM orders WHERE pharmacy_id IS NOT NULL),
           'orders_with_null_pharmacy_id', (SELECT count(*) FROM orders WHERE pharmacy_id IS NULL),
           'detail_rows', (SELECT count(*) FROM details),
           'dose_support_is_actual_dose_verification', false,
           'dose_due_used_as_actual_dose', false,
           'product_amounts_summed_across_events', false,
           'action_mapping_performed', false) AS counters
FROM events
UNION ALL
SELECT 'event_status', jsonb_build_object('status', status_class, 'head', head_class), count(*),
       jsonb_build_object(
           'subjects', count(DISTINCT subject_id), 'admissions', count(DISTINCT (subject_id, hadm_id)) FILTER (WHERE subject_id IS NOT NULL AND hadm_id IS NOT NULL),
           'identity_ok', count(*) FILTER (WHERE identity_ok),
           'missing_charttime', count(*) FILTER (WHERE charttime IS NULL),
           'missing_storetime', count(*) FILTER (WHERE storetime IS NULL),
           'store_before_chart', count(*) FILTER (WHERE storetime < charttime),
           'no_detail', count(*) FILTER (WHERE coalesce(detail_rows, 0) = 0),
           'one_parent_one_product', count(*) FILTER (WHERE parent_rows = 1 AND product_rows = 1),
           'bad_detail_link', count(*) FILTER (WHERE any_bad_detail_link),
           'product_description_present', count(*) FILTER (WHERE any_product_description),
           'complete_yes', count(*) FILTER (WHERE any_complete_yes),
           'incomplete_yes', count(*) FILTER (WHERE any_incomplete_yes))
FROM event_support GROUP BY status_class, head_class
UNION ALL
SELECT 'quantity_support',
       jsonb_build_object('field', quantity_kind, 'status', status_class,
                          'role', role_class, 'unit', unit_class), count(*),
       jsonb_build_object(
           'events', count(DISTINCT event_key),
           'field_present', count(*) FILTER (WHERE quantity_present),
           'numeric_positive', count(*) FILTER (WHERE quantity_numeric > 0),
           'numeric_zero', count(*) FILTER (WHERE quantity_numeric = 0),
           'numeric_negative', count(*) FILTER (WHERE quantity_numeric < 0),
           'present_unparsed', count(*) FILTER (WHERE quantity_present AND quantity_numeric IS NULL),
           'quantity_equals_500', count(*) FILTER (WHERE quantity_numeric = 500),
           'other_head_rows', count(*) FILTER (WHERE head_class = 'other_head_name'),
           'missing_head_rows', count(*) FILTER (WHERE head_class = 'head_name_missing'),
           'identity_problem_rows', count(*) FILTER (WHERE identity_ok IS NOT TRUE OR detail_link_bad),
           'incomplete_yes_rows', count(*) FILTER (WHERE incomplete_class = 'yes'),
           'complete_yes_rows', count(*) FILTER (WHERE complete_class = 'yes'))
FROM quantities GROUP BY quantity_kind, status_class, role_class, unit_class
UNION ALL
SELECT 'rate_support',
       jsonb_build_object('status', status_class, 'role', role_class, 'unit', rate_unit_class),
       count(*), jsonb_build_object(
           'events', count(DISTINCT event_key),
           'field_present', count(*) FILTER (WHERE rate_present),
           'numeric_positive', count(*) FILTER (WHERE rate_numeric > 0),
           'numeric_zero', count(*) FILTER (WHERE rate_numeric = 0),
           'numeric_negative', count(*) FILTER (WHERE rate_numeric < 0),
           'present_unparsed', count(*) FILTER (WHERE rate_present AND rate_numeric IS NULL),
           'other_head_rows', count(*) FILTER (WHERE head_class = 'other_head_name'),
           'identity_problem_rows', count(*) FILTER (WHERE identity_ok IS NOT TRUE OR detail_link_bad))
FROM rates GROUP BY status_class, role_class, rate_unit_class
UNION ALL
SELECT 'completion_support',
       jsonb_build_object('status', status_class, 'role', role_class,
                          'complete', complete_class, 'incomplete', incomplete_class),
       count(*), jsonb_build_object(
           'events', count(DISTINCT event_key),
           'new_bag_yes_rows', count(*) FILTER (WHERE new_bag_yes),
           'other_head_rows', count(*) FILTER (WHERE head_class = 'other_head_name'))
FROM details GROUP BY status_class, role_class, complete_class, incomplete_class
UNION ALL
SELECT 'event_quantity_support',
       jsonb_build_object('status', status_class, 'head', head_class, 'support', support_class),
       count(*), jsonb_build_object(
           'subjects', count(DISTINCT subject_id), 'admissions', count(DISTINCT (subject_id, hadm_id)) FILTER (WHERE subject_id IS NOT NULL AND hadm_id IS NOT NULL),
           'known_parent_dose', count(*) FILTER (WHERE known_parent_dose),
           'known_product_dose', count(*) FILTER (WHERE known_product_dose),
           'known_product_amount', count(*) FILTER (WHERE known_product_amount),
           'known_positive_rate', count(*) FILTER (WHERE known_positive_rate),
           'complete_yes', count(*) FILTER (WHERE any_complete_yes),
           'incomplete_yes', count(*) FILTER (WHERE any_incomplete_yes))
FROM event_support GROUP BY status_class, head_class, support_class
ORDER BY section, records DESC, dimensions;
