-- Diagnostic only: an order-linked stream is not a clinical treatment episode.
-- Confirmed records may update rates; they are not new independent treatments.
-- End a candidate segment at the NEXT non-Confirmed record, never skip another
-- start/unknown status to find a convenient stop. Ties remain disqualifying.
-- Rate integrals assume piecewise-constant charted rates and are NOT actual dose.
WITH orders AS MATERIALIZED (
    SELECT pharmacy_id, min(subject_id) AS order_subject, min(hadm_id) AS order_hadm,
           count(DISTINCT subject_id) AS subjects, count(DISTINCT hadm_id) AS admissions,
           count(*) FILTER (WHERE subject_id IS NULL OR hadm_id IS NULL) AS missing_ids
    FROM mimiciv_hosp.prescriptions
    WHERE drug = 'Sodium Chloride 3% (Hypertonic)'
    GROUP BY pharmacy_id
), events AS MATERIALIZED (
    SELECT e.*, (e.subject_id IS NOT NULL AND e.hadm_id IS NOT NULL
           AND e.subject_id = o.order_subject AND e.hadm_id = o.order_hadm
           AND o.subjects = 1 AND o.admissions = 1 AND o.missing_ids = 0) AS identity_ok
    FROM orders o JOIN mimiciv_hosp.emar e ON e.pharmacy_id = o.pharmacy_id
), details AS MATERIALIZED (
    SELECT e.emar_id AS event_key, e.event_txt, e.subject_id AS event_subject,
           e.pharmacy_id AS event_pharmacy, d.*
    FROM events e JOIN mimiciv_hosp.emar_detail d ON d.emar_id = e.emar_id
), shapes AS (
    SELECT e.emar_id,
           count(*) FILTER (WHERE d.emar_id IS NOT NULL AND parent_field_ordinal IS NULL) AS parent_rows,
           count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL) AS product_rows,
           count(*) FILTER (WHERE d.subject_id IS DISTINCT FROM e.subject_id
                             AND d.emar_id IS NOT NULL) AS subject_mismatches,
           count(*) FILTER (WHERE d.emar_seq IS DISTINCT FROM e.emar_seq
                             AND d.emar_id IS NOT NULL) AS sequence_mismatches,
           count(*) FILTER (WHERE d.pharmacy_id IS NOT NULL AND d.pharmacy_id <> e.pharmacy_id) AS other_pharmacy,
           min(infusion_rate) FILTER (WHERE parent_field_ordinal IS NULL) AS rate_raw,
           min(infusion_rate_unit) FILTER (WHERE parent_field_ordinal IS NULL) AS rate_unit,
           min(prior_infusion_rate) FILTER (WHERE parent_field_ordinal IS NULL) AS prior_raw,
           bool_or(new_iv_bag_hung = 'Y') AS new_bag,
           bool_or(infusion_complete = 'Y') AS infusion_complete,
           count(*) FILTER (WHERE nullif(trim(product_description), '') IS NOT NULL) AS described_products
    FROM events e LEFT JOIN details d ON d.event_key = e.emar_id
    GROUP BY e.emar_id
), parsed_base AS (
    SELECT e.*, s.parent_rows, s.product_rows, s.subject_mismatches, s.other_pharmacy,
           s.sequence_mismatches,
           s.rate_raw, s.rate_unit, s.prior_raw, s.new_bag, s.infusion_complete, s.described_products,
           CASE WHEN trim(rate_raw) ~ '^[0-9]+([.][0-9]+)?$' THEN trim(rate_raw)::numeric END AS rate,
           CASE WHEN trim(prior_raw) ~ '^[0-9]+([.][0-9]+)?$' THEN trim(prior_raw)::numeric END AS prior_rate
    FROM events e JOIN shapes s USING (emar_id)
), parsed AS MATERIALIZED (
    -- An unknown-time control or identity-conflicting event must not disappear
    -- silently and leave an apparently clean integral in the remaining stream.
    SELECT p.*,
           count(*) FILTER (WHERE charttime IS NULL) OVER
               (PARTITION BY subject_id, hadm_id, pharmacy_id) AS stream_missing_charttime,
           count(*) FILTER (WHERE identity_ok IS NOT TRUE) OVER
               (PARTITION BY pharmacy_id) AS pharmacy_identity_bad_records
    FROM parsed_base p
), sequenced AS MATERIALIZED (
    SELECT p.*, row_number() OVER w AS position,
           count(*) OVER (PARTITION BY subject_id, hadm_id, pharmacy_id, charttime) AS simultaneous,
           lead(event_txt) OVER w AS next_status,
           lead(charttime) OVER w AS next_time,
           lead(prior_raw) OVER w AS next_prior_raw,
           lead(prior_rate) OVER w AS next_prior_rate
    FROM parsed p WHERE identity_ok AND charttime IS NOT NULL
    WINDOW w AS (PARTITION BY subject_id, hadm_id, pharmacy_id ORDER BY charttime, emar_id)
), control AS MATERIALIZED (
    SELECT s.*, min(position) FILTER (WHERE event_txt IS DISTINCT FROM 'Confirmed')
           OVER (PARTITION BY subject_id, hadm_id, pharmacy_id ORDER BY position
                 ROWS BETWEEN 1 FOLLOWING AND UNBOUNDED FOLLOWING) AS next_control_position
    FROM sequenced s
), starts AS MATERIALIZED (
    SELECT s.*, c.event_txt AS endpoint_status, c.charttime AS endpoint_time,
           c.position AS endpoint_position, c.infusion_complete AS endpoint_complete
    FROM control s LEFT JOIN control c
      ON c.subject_id = s.subject_id AND c.hadm_id = s.hadm_id
     AND c.pharmacy_id = s.pharmacy_id AND c.position = s.next_control_position
    WHERE s.event_txt IN ('Started', 'Delayed Started', 'Restarted')
), closed AS MATERIALIZED (
    SELECT s.emar_id, s.subject_id, s.hadm_id, s.event_txt, s.endpoint_status,
           s.endpoint_complete, extract(epoch FROM (s.endpoint_time - s.charttime))/3600 AS hours,
           count(*) FILTER (WHERE r.event_txt = 'Confirmed') AS confirmations,
           count(*) FILTER (WHERE r.simultaneous > 1) AS tied_rows,
           count(*) FILTER (WHERE r.parent_rows <> 1 OR r.product_rows <> 1
                             OR r.subject_mismatches > 0 OR r.other_pharmacy > 0
                             OR r.sequence_mismatches > 0) AS shape_issues,
           count(*) FILTER (WHERE r.sequence_mismatches > 0) AS detail_sequence_issues,
           max(r.stream_missing_charttime) AS stream_missing_charttime,
           max(r.pharmacy_identity_bad_records) AS pharmacy_identity_bad_records,
           count(*) FILTER (WHERE r.position < s.endpoint_position
                             AND (r.rate IS NULL OR r.rate_unit IS DISTINCT FROM 'mL/hr')) AS bad_rate_intervals,
           count(*) FILTER (WHERE r.position < s.endpoint_position AND r.rate = 0) AS zero_rate_intervals,
           count(*) FILTER (WHERE r.position < s.endpoint_position
                             AND nullif(trim(r.next_prior_raw), '') IS NOT NULL
                             AND (r.next_prior_rate IS NULL OR r.next_prior_rate IS DISTINCT FROM r.rate)) AS prior_disagreements,
           count(*) FILTER (WHERE r.new_bag) AS new_bags,
           count(*) FILTER (WHERE r.storetime < r.charttime OR r.storetime IS NULL) AS store_time_issues,
           sum(r.rate * extract(epoch FROM (r.next_time - r.charttime))/3600)
               FILTER (WHERE r.position < s.endpoint_position) AS provisional_integral_ml
    FROM starts s JOIN sequenced r
      ON r.subject_id = s.subject_id AND r.hadm_id = s.hadm_id AND r.pharmacy_id = s.pharmacy_id
     AND r.position BETWEEN s.position AND s.endpoint_position
    WHERE s.endpoint_status IN ('Stopped', 'Stopped - Unscheduled')
    GROUP BY s.emar_id, s.subject_id, s.hadm_id, s.event_txt, s.endpoint_status,
             s.endpoint_complete, s.endpoint_time, s.charttime
), classified AS (
    SELECT c.*, (hours > 0 AND tied_rows = 0 AND shape_issues = 0
                 AND bad_rate_intervals = 0 AND prior_disagreements = 0
                 AND store_time_issues = 0 AND stream_missing_charttime = 0
                 AND pharmacy_identity_bad_records = 0) AS integral_computable,
           CASE WHEN hours <= 0 THEN 'nonpositive' WHEN hours <= 4 THEN '(0,4]h'
                WHEN hours <= 24 THEN '(4,24]h' ELSE '>24h' END AS duration_bin
    FROM closed c
)
SELECT 'source_summary' AS section, '{}'::jsonb AS dimensions, count(*) AS records,
       jsonb_build_object('identity_ok', count(*) FILTER (WHERE identity_ok),
          'missing_charttime', count(*) FILTER (WHERE charttime IS NULL),
          'subjects', count(DISTINCT subject_id), 'admissions', count(DISTINCT hadm_id),
          'pharmacy_ids', count(DISTINCT pharmacy_id),
          'start_like_records', count(*) FILTER (WHERE event_txt IN ('Started','Delayed Started','Restarted'))) AS counters
FROM parsed
UNION ALL
SELECT 'adjacent_status', jsonb_build_object('from', event_txt, 'to', next_status,
         'same_time', charttime = next_time, 'from_time_tied', simultaneous > 1), count(*), '{}'::jsonb
FROM sequenced GROUP BY event_txt, next_status, charttime = next_time, simultaneous > 1
UNION ALL
SELECT 'start_endpoint', jsonb_build_object('start', event_txt, 'next_control', endpoint_status), count(*),
       jsonb_build_object('subjects', count(DISTINCT subject_id), 'admissions', count(DISTINCT hadm_id))
FROM starts GROUP BY event_txt, endpoint_status
UNION ALL
SELECT 'closed_segment', jsonb_build_object('start', event_txt, 'end', endpoint_status,
       'duration', duration_bin, 'integral_computable', integral_computable), count(*),
       jsonb_build_object('subjects', count(DISTINCT subject_id), 'admissions', count(DISTINCT hadm_id),
           'with_ties', count(*) FILTER (WHERE tied_rows > 0),
           'with_shape_issues', count(*) FILTER (WHERE shape_issues > 0),
           'with_detail_sequence_issues', count(*) FILTER (WHERE detail_sequence_issues > 0),
           'with_missing_stream_charttime', count(*) FILTER (WHERE stream_missing_charttime > 0),
           'with_identity_conflict_in_pharmacy', count(*) FILTER (WHERE pharmacy_identity_bad_records > 0),
           'with_bad_rate_intervals', count(*) FILTER (WHERE bad_rate_intervals > 0),
           'with_zero_rates', count(*) FILTER (WHERE zero_rate_intervals > 0),
           'with_prior_disagreement', count(*) FILTER (WHERE prior_disagreements > 0),
           'with_new_bag', count(*) FILTER (WHERE new_bags > 0),
           'with_store_time_issues', count(*) FILTER (WHERE store_time_issues > 0),
           'end_complete_yes', count(*) FILTER (WHERE endpoint_complete),
           'integral_ml_min', min(provisional_integral_ml) FILTER (WHERE integral_computable),
           'integral_ml_median', percentile_cont(0.5) WITHIN GROUP (ORDER BY provisional_integral_ml) FILTER (WHERE integral_computable),
           'integral_ml_max', max(provisional_integral_ml) FILTER (WHERE integral_computable))
FROM classified GROUP BY event_txt, endpoint_status, duration_bin, integral_computable
UNION ALL
SELECT 'amount_fields', jsonb_build_object('status', event_txt,
         'role', CASE WHEN parent_field_ordinal IS NULL THEN 'parent' ELSE 'product' END,
         'unit', product_unit, 'new_bag', new_iv_bag_hung), count(*),
       jsonb_build_object('amount_present', count(*) FILTER (WHERE nullif(trim(product_amount_given),'') IS NOT NULL),
         'amount_numeric', count(*) FILTER (WHERE trim(product_amount_given) ~ '^[0-9]+([.][0-9]+)?$'),
         'amount_500', count(*) FILTER (WHERE trim(product_amount_given) ~ '^500([.]0+)?$'),
         'amount_zero', count(*) FILTER (WHERE trim(product_amount_given) ~ '^0([.]0+)?$'),
         'distinct_raw_amounts', count(DISTINCT product_amount_given),
         'dose_given_present', count(*) FILTER (WHERE nullif(trim(dose_given),'') IS NOT NULL))
FROM details GROUP BY event_txt, parent_field_ordinal IS NULL, product_unit, new_iv_bag_hung
ORDER BY section, records DESC, dimensions;
