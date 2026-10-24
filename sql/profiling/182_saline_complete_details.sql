-- All detail rows for the exact-name order-linked eMAR set, including other
-- pharmacy IDs. This may scan emar_detail: a timeout is failure, not partial evidence.
-- Aggregate only. Parent rows and product rows are never summed as one dose.
WITH orders AS MATERIALIZED (
    SELECT DISTINCT pharmacy_id FROM mimiciv_hosp.prescriptions
    WHERE drug = 'Sodium Chloride 3% (Hypertonic)'
), events AS MATERIALIZED (
    SELECT e.emar_id, e.subject_id, e.pharmacy_id, e.event_txt
    FROM orders o JOIN mimiciv_hosp.emar e ON e.pharmacy_id = o.pharmacy_id
), details AS MATERIALIZED (
    SELECT e.emar_id AS event_key, e.event_txt, e.subject_id AS event_subject,
           e.pharmacy_id AS event_pharmacy, d.*
    FROM events e JOIN mimiciv_hosp.emar_detail d ON d.emar_id = e.emar_id
), event_shapes AS (
    SELECT e.emar_id, e.event_txt, count(d.emar_id) AS detail_rows,
           count(d.emar_id) FILTER (WHERE d.parent_field_ordinal IS NULL) AS parent_rows,
           count(d.emar_id) FILTER (WHERE d.parent_field_ordinal IS NOT NULL) AS product_rows,
           count(d.emar_id) FILTER (WHERE d.pharmacy_id IS DISTINCT FROM e.pharmacy_id) AS other_pharmacy_rows,
           count(d.emar_id) FILTER (WHERE d.pharmacy_id IS NULL) AS missing_detail_pharmacy_rows,
           count(d.emar_id) FILTER (WHERE d.pharmacy_id IS NOT NULL AND e.pharmacy_id IS NOT NULL
                                   AND d.pharmacy_id <> e.pharmacy_id) AS nonnull_other_pharmacy_rows,
           count(d.emar_id) FILTER (WHERE d.subject_id IS DISTINCT FROM e.subject_id) AS subject_mismatch_rows
    FROM events e LEFT JOIN details d ON d.event_key = e.emar_id
    GROUP BY e.emar_id, e.event_txt
)
SELECT 'detail_vocabulary' AS profile_section,
       jsonb_build_object(
           'event_txt', event_txt,
           'detail_role', CASE WHEN parent_field_ordinal IS NULL THEN 'parent' ELSE 'product' END,
           'product_description', product_description, 'administration_type', administration_type,
           'route', route, 'dose_given_unit', dose_given_unit, 'product_unit', product_unit,
           'infusion_rate_unit', infusion_rate_unit
       ) AS dimensions,
       count(*) AS source_rows, count(DISTINCT event_key) AS emar_events,
       jsonb_build_object(
           'dose_given_present', count(*) FILTER (WHERE nullif(trim(dose_given), '') IS NOT NULL),
           'dose_given_numeric', count(*) FILTER (WHERE trim(dose_given) ~ '^[0-9]+([.][0-9]+)?$'),
           'product_amount_present', count(*) FILTER (WHERE nullif(trim(product_amount_given), '') IS NOT NULL),
           'infusion_rate_present', count(*) FILTER (WHERE nullif(trim(infusion_rate), '') IS NOT NULL),
           'infusion_rate_numeric', count(*) FILTER (WHERE trim(infusion_rate) ~ '^[0-9]+([.][0-9]+)?$'),
           'prior_infusion_rate_present', count(*) FILTER (WHERE nullif(trim(prior_infusion_rate), '') IS NOT NULL),
           'completion_interval_present', count(*) FILTER (WHERE nullif(trim(completion_interval), '') IS NOT NULL),
           'infusion_complete_yes', count(*) FILTER (WHERE infusion_complete = 'Y'),
           'new_iv_bag_yes', count(*) FILTER (WHERE new_iv_bag_hung = 'Y'),
           'other_pharmacy_rows', count(*) FILTER (WHERE pharmacy_id IS DISTINCT FROM event_pharmacy),
           'missing_detail_pharmacy_rows', count(*) FILTER (WHERE pharmacy_id IS NULL),
           'nonnull_other_pharmacy_rows', count(*) FILTER (WHERE pharmacy_id IS NOT NULL AND event_pharmacy IS NOT NULL AND pharmacy_id <> event_pharmacy),
           'subject_mismatch_rows', count(*) FILTER (WHERE subject_id IS DISTINCT FROM event_subject)
       ) AS counters
FROM details
GROUP BY event_txt, parent_field_ordinal IS NULL, product_description, administration_type,
         route, dose_given_unit, product_unit, infusion_rate_unit
UNION ALL
SELECT 'event_shape', jsonb_build_object(
           'event_txt', event_txt, 'detail_rows', detail_rows,
           'parent_rows', parent_rows, 'product_rows', product_rows,
           'missing_detail_pharmacy_rows', missing_detail_pharmacy_rows,
           'nonnull_other_pharmacy_rows', nonnull_other_pharmacy_rows,
           'other_pharmacy_rows', other_pharmacy_rows, 'subject_mismatch_rows', subject_mismatch_rows
       ), sum(detail_rows)::bigint, count(*), '{}'::jsonb
FROM event_shapes
GROUP BY event_txt, detail_rows, parent_rows, product_rows, other_pharmacy_rows,
         missing_detail_pharmacy_rows, nonnull_other_pharmacy_rows, subject_mismatch_rows
ORDER BY profile_section, source_rows DESC, dimensions;
