-- Discovery only: a repeatable 1 percent SYSTEM page sample of eMAR events.
-- Case-sensitive exact medication names after trim; all event statuses retained.
-- This is not a uniform patient sample, a potassium cohort, or a dose mapping.
-- Complete detail rows are joined ONLY by emar_id, never by pharmacy_id, so
-- parent rows with NULL pharmacy and products with another pharmacy survive.
-- No individual identifier, timestamp, dose value, or narrative is output.
-- Descriptions/statuses/routes are grouped vocabulary, not clinical narratives.
-- A timeout is failure, not evidence that events have no detail rows.
WITH sampled AS MATERIALIZED (
    SELECT emar_id, subject_id, hadm_id, pharmacy_id, medication, event_txt,
           charttime, storetime
    FROM mimiciv_hosp.emar TABLESAMPLE SYSTEM (1) REPEATABLE (20261011)
), events AS MATERIALIZED (
    SELECT emar_id, subject_id, hadm_id, pharmacy_id, trim(medication) AS medication,
           event_txt, charttime, storetime
    FROM sampled
    WHERE trim(medication) IN (
        'Potassium Chloride',
        'Potassium Chloride Replacement (Critical Care and Oncology)'
    )
), details AS MATERIALIZED (
    SELECT e.emar_id AS event_key, e.medication AS event_medication, e.event_txt,
           e.subject_id AS event_subject, e.pharmacy_id AS event_pharmacy, d.*
    FROM events e
    JOIN mimiciv_hosp.emar_detail d ON d.emar_id = e.emar_id
), event_shapes AS MATERIALIZED (
    SELECT e.emar_id, e.medication, e.event_txt,
           e.hadm_id IS NULL AS missing_hadm,
           e.pharmacy_id IS NULL AS missing_event_pharmacy,
           e.charttime IS NULL AS missing_charttime,
           e.storetime IS NULL AS missing_storetime,
           e.storetime < e.charttime AS store_before_chart,
           count(d.emar_id) AS detail_rows,
           count(d.emar_id) FILTER (WHERE d.parent_field_ordinal IS NULL) AS parent_rows,
           count(d.emar_id) FILTER (WHERE d.parent_field_ordinal IS NOT NULL) AS product_rows,
           count(d.emar_id) FILTER (WHERE d.pharmacy_id IS NULL) AS missing_detail_pharmacy_rows,
           count(d.emar_id) FILTER (WHERE d.parent_field_ordinal IS NULL
                                   AND d.pharmacy_id IS NULL) AS parents_with_missing_pharmacy,
           count(d.emar_id) FILTER (WHERE d.pharmacy_id IS NOT NULL AND e.pharmacy_id IS NOT NULL
                                   AND d.pharmacy_id <> e.pharmacy_id) AS nonnull_other_pharmacy_rows,
           count(d.emar_id) FILTER (WHERE d.pharmacy_id IS NOT NULL
                                   AND e.pharmacy_id IS NULL) AS known_detail_unknown_event_pharmacy_rows,
           count(d.emar_id) FILTER (WHERE d.subject_id IS NULL) AS missing_detail_subject_rows,
           count(d.emar_id) FILTER (WHERE d.subject_id IS DISTINCT FROM e.subject_id) AS subject_disagreement_rows
    FROM events e
    LEFT JOIN details d ON d.event_key = e.emar_id
    GROUP BY e.emar_id, e.medication, e.event_txt, e.hadm_id, e.pharmacy_id,
             e.charttime, e.storetime
), profiles AS (
    SELECT 'sample_summary' AS profile_section,
           jsonb_build_object('sample_method', 'SYSTEM page sample',
                              'selection', 'exact trimmed medication; all statuses') AS dimensions,
           (SELECT count(*) FROM sampled) AS source_rows,
           (SELECT count(DISTINCT emar_id) FROM events) AS emar_events,
           jsonb_build_object(
               'sampled_emar_rows', (SELECT count(*) FROM sampled),
               'sampled_distinct_emar_ids', (SELECT count(DISTINCT emar_id) FROM sampled),
               'selected_emar_rows', (SELECT count(*) FROM events),
               'selected_distinct_emar_ids', (SELECT count(DISTINCT emar_id) FROM events),
               'complete_detail_rows', (SELECT count(*) FROM details),
               'events_without_details', count(*) FILTER (WHERE detail_rows = 0),
               'events_without_parent', count(*) FILTER (WHERE parent_rows = 0),
               'events_with_one_parent', count(*) FILTER (WHERE parent_rows = 1),
               'events_with_multiple_parents', count(*) FILTER (WHERE parent_rows > 1),
               'events_without_products', count(*) FILTER (WHERE product_rows = 0),
               'events_missing_hadm', count(*) FILTER (WHERE missing_hadm),
               'events_missing_pharmacy', count(*) FILTER (WHERE missing_event_pharmacy),
               'events_missing_charttime', count(*) FILTER (WHERE missing_charttime),
               'events_missing_storetime', count(*) FILTER (WHERE missing_storetime),
               'events_store_before_chart', count(*) FILTER (WHERE store_before_chart)
           ) AS counters
    FROM event_shapes
    UNION ALL
    SELECT 'detail_vocabulary',
           jsonb_build_object(
               'emar_medication', event_medication, 'event_txt', event_txt,
               'detail_role', CASE WHEN parent_field_ordinal IS NULL THEN 'parent' ELSE 'product' END,
               'product_description', product_description, 'administration_type', administration_type,
               'route', route, 'dose_given_unit', dose_given_unit,
               'product_unit', product_unit, 'infusion_rate_unit', infusion_rate_unit
           ), count(*), count(DISTINCT event_key),
           jsonb_build_object(
               'dose_given_present', count(*) FILTER (WHERE nullif(trim(dose_given), '') IS NOT NULL),
               'dose_given_simple_numeric', count(*) FILTER (WHERE trim(dose_given) ~ '^[0-9]+([.][0-9]+)?$'),
               'product_amount_present', count(*) FILTER (WHERE nullif(trim(product_amount_given), '') IS NOT NULL),
               'product_amount_simple_numeric', count(*) FILTER (WHERE trim(product_amount_given) ~ '^[0-9]+([.][0-9]+)?$'),
               'infusion_rate_present', count(*) FILTER (WHERE nullif(trim(infusion_rate), '') IS NOT NULL),
               'infusion_rate_simple_numeric', count(*) FILTER (WHERE trim(infusion_rate) ~ '^[0-9]+([.][0-9]+)?$'),
               'prior_infusion_rate_present', count(*) FILTER (WHERE nullif(trim(prior_infusion_rate), '') IS NOT NULL),
               'prior_infusion_rate_simple_numeric', count(*) FILTER (WHERE trim(prior_infusion_rate) ~ '^[0-9]+([.][0-9]+)?$'),
               'completion_interval_present', count(*) FILTER (WHERE nullif(trim(completion_interval), '') IS NOT NULL),
               'infusion_complete_yes', count(*) FILTER (WHERE infusion_complete = 'Y'),
               'new_iv_bag_yes', count(*) FILTER (WHERE new_iv_bag_hung = 'Y'),
               'missing_route', count(*) FILTER (WHERE nullif(trim(route), '') IS NULL),
               'missing_administration_type', count(*) FILTER (WHERE nullif(trim(administration_type), '') IS NULL),
               'missing_product_description', count(*) FILTER (WHERE nullif(trim(product_description), '') IS NULL),
               'missing_detail_pharmacy_rows', count(*) FILTER (WHERE pharmacy_id IS NULL),
               'nonnull_other_pharmacy_rows', count(*) FILTER (WHERE pharmacy_id IS NOT NULL
                       AND event_pharmacy IS NOT NULL AND pharmacy_id <> event_pharmacy),
               'known_detail_unknown_event_pharmacy_rows', count(*) FILTER (
                       WHERE pharmacy_id IS NOT NULL AND event_pharmacy IS NULL),
               'missing_detail_subject_rows', count(*) FILTER (WHERE subject_id IS NULL),
               'subject_disagreement_rows', count(*) FILTER (WHERE subject_id IS DISTINCT FROM event_subject)
           )
    FROM details
    GROUP BY event_medication, event_txt, parent_field_ordinal IS NULL, product_description,
             administration_type, route, dose_given_unit, product_unit, infusion_rate_unit
    UNION ALL
    SELECT 'event_shape',
           jsonb_build_object(
               'emar_medication', medication, 'event_txt', event_txt,
               'missing_hadm', missing_hadm, 'missing_event_pharmacy', missing_event_pharmacy,
               'detail_rows', detail_rows, 'parent_rows', parent_rows, 'product_rows', product_rows,
               'missing_detail_pharmacy_rows', missing_detail_pharmacy_rows,
               'parents_with_missing_pharmacy', parents_with_missing_pharmacy,
               'nonnull_other_pharmacy_rows', nonnull_other_pharmacy_rows,
               'known_detail_unknown_event_pharmacy_rows', known_detail_unknown_event_pharmacy_rows,
               'missing_detail_subject_rows', missing_detail_subject_rows,
               'subject_disagreement_rows', subject_disagreement_rows
           ), sum(detail_rows)::bigint, count(*),
           jsonb_build_object(
               'events_missing_charttime', count(*) FILTER (WHERE missing_charttime),
               'events_missing_storetime', count(*) FILTER (WHERE missing_storetime),
               'events_store_before_chart', count(*) FILTER (WHERE store_before_chart)
           )
    FROM event_shapes
    GROUP BY medication, event_txt, missing_hadm, missing_event_pharmacy,
             detail_rows, parent_rows, product_rows, missing_detail_pharmacy_rows,
             parents_with_missing_pharmacy, nonnull_other_pharmacy_rows,
             known_detail_unknown_event_pharmacy_rows, missing_detail_subject_rows,
             subject_disagreement_rows
)
SELECT profile_section, dimensions, source_rows, emar_events,
       counters || jsonb_build_object(
           'total_sampled_emar_rows', (SELECT count(*) FROM sampled),
           'total_selected_emar_events', (SELECT count(DISTINCT emar_id) FROM events),
           'system_sample_percent', 1.0, 'sample_seed', 20261011,
           'numeric_check', 'nonnegative plain decimal; other formats remain unclassified'
       ) AS counters
FROM profiles
ORDER BY profile_section, source_rows DESC, dimensions;
