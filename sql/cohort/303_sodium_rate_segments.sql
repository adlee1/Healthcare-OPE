-- PRIVATE ROW OUTPUT: keep local; never print patient rows into tool/chat logs.
-- Read only, full exact-prescription source, no sample and no LIMIT truncation.
-- Every Started / Delayed Started / Restarted head is retained, including
-- excluded starts. The next non-Confirmed control is the only possible end:
-- never skip another start or unknown status to find a later stop.
-- Mainline implementation choice: a missing head name inherits the exact
-- 3% prescription identity through its consistent pharmacy association.
-- A known different head name in the segment invalidates that estimate.
-- Piecewise-constant current parent rates * elapsed hours estimate volume.
-- No dose_due, bag amount, prescribed duration or assumed 30 mEq/h is used.
-- mEq = estimated mL * 0.513. These are estimated, not measured, quantities.
-- Product multiplicity does not invalidate a unique parent rate. Missing
-- storetime and infusion_complete do not exclude; reversed storetime is reported.
-- Non-ICU is assessed at the start point only, not over the treatment interval.
-- Routes: IV / IV DRIP are the declared IV tokens. Missing detail route may
-- use a matching exact-drug prescription with IV evidence and no other route.
-- Conflicting/non-whitelisted explicit routes or absent IV evidence exclude.
WITH icu_units(careunit) AS (
    VALUES ('Cardiac Vascular Intensive Care Unit (CVICU)'),
           ('Coronary Care Unit (CCU)'), ('Intensive Care Unit (ICU)'),
           ('Medical Intensive Care Unit (MICU)'),
           ('Medical/Surgical Intensive Care Unit (MICU/SICU)'),
           ('Neuro Surgical Intensive Care Unit (Neuro SICU)'),
           ('Surgical Intensive Care Unit (SICU)'), ('Trauma SICU (TSICU)')
), orders AS MATERIALIZED (
    SELECT pharmacy_id, min(subject_id) AS order_subject, min(hadm_id) AS order_hadm,
           count(DISTINCT subject_id) AS subjects, count(DISTINCT hadm_id) AS admissions,
           count(*) FILTER (WHERE subject_id IS NULL OR hadm_id IS NULL) AS missing_ids,
           count(*) FILTER (WHERE upper(trim(route)) IN ('IV','IV DRIP')) AS order_iv_route_rows,
           count(*) FILTER (WHERE nullif(trim(route),'') IS NOT NULL
               AND upper(trim(route)) NOT IN ('IV','IV DRIP')) AS order_other_route_rows
    FROM mimiciv_hosp.prescriptions
    WHERE drug = 'Sodium Chloride 3% (Hypertonic)'
    GROUP BY pharmacy_id
), events AS MATERIALIZED (
    SELECT e.emar_id, e.emar_seq, e.subject_id, e.hadm_id, e.pharmacy_id,
           e.event_txt, e.charttime, e.storetime, o.order_iv_route_rows, o.order_other_route_rows,
           (e.subject_id IS NOT NULL AND e.hadm_id IS NOT NULL
            AND e.subject_id = o.order_subject AND e.hadm_id = o.order_hadm
            AND o.subjects = 1 AND o.admissions = 1 AND o.missing_ids = 0) AS identity_ok,
           CASE WHEN nullif(trim(e.medication), '') IS NULL THEN 'missing_head_order_assumption'
                WHEN e.medication = 'Sodium Chloride 3% (Hypertonic)' THEN 'exact_saline_head'
                ELSE 'known_other_head' END AS head_source
    FROM orders o JOIN mimiciv_hosp.emar e ON e.pharmacy_id = o.pharmacy_id
), shapes AS MATERIALIZED (
    SELECT e.emar_id,
           count(d.emar_id) FILTER (WHERE d.parent_field_ordinal IS NULL) AS parent_rows,
           count(d.emar_id) FILTER (WHERE d.parent_field_ordinal IS NOT NULL) AS product_rows,
           count(d.emar_id) FILTER (WHERE d.subject_id IS DISTINCT FROM e.subject_id
               OR d.emar_seq IS DISTINCT FROM e.emar_seq
               OR (d.pharmacy_id IS NOT NULL AND d.pharmacy_id <> e.pharmacy_id)) AS bad_detail_identity_rows,
           min(d.infusion_rate) FILTER (WHERE d.parent_field_ordinal IS NULL) AS rate_raw,
           min(d.infusion_rate_unit) FILTER (WHERE d.parent_field_ordinal IS NULL) AS rate_unit,
           count(d.emar_id) FILTER (WHERE upper(trim(d.route)) IN ('IV','IV DRIP')) AS detail_iv_route_rows,
           count(d.emar_id) FILTER (WHERE nullif(trim(d.route),'') IS NOT NULL
               AND upper(trim(d.route)) NOT IN ('IV','IV DRIP')) AS detail_other_route_rows,
           bool_or(upper(trim(d.infusion_complete)) IN ('Y','YES')) AS complete_yes
    FROM events e LEFT JOIN mimiciv_hosp.emar_detail d ON d.emar_id = e.emar_id
    GROUP BY e.emar_id
), parsed AS MATERIALIZED (
    SELECT e.*, s.parent_rows, s.product_rows, s.bad_detail_identity_rows,
           s.rate_raw, s.rate_unit, s.complete_yes, s.detail_iv_route_rows, s.detail_other_route_rows,
           CASE WHEN s.detail_other_route_rows > 0 THEN 'detail_non_iv_or_unrecognized'
                WHEN s.detail_iv_route_rows > 0 AND e.order_other_route_rows > 0 THEN 'detail_order_route_conflict'
                WHEN s.detail_iv_route_rows > 0 THEN 'detail_iv'
                WHEN e.order_other_route_rows > 0 THEN 'prescription_non_iv_or_unrecognized'
                WHEN e.order_iv_route_rows > 0 THEN 'prescription_iv_fallback'
                ELSE 'route_missing' END AS route_class,
           CASE WHEN length(trim(s.rate_raw)) BETWEEN 1 AND 64
                     AND trim(s.rate_raw) ~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)$'
                THEN trim(s.rate_raw)::numeric END AS rate,
           count(*) FILTER (WHERE e.charttime IS NULL) OVER
               (PARTITION BY e.subject_id, e.hadm_id, e.pharmacy_id) AS stream_missing_time_heads,
           count(*) FILTER (WHERE e.identity_ok IS NOT TRUE) OVER
               (PARTITION BY e.pharmacy_id) AS pharmacy_identity_problem_heads
    FROM events e JOIN shapes s USING (emar_id)
), sequenced AS MATERIALIZED (
    SELECT p.*, row_number() OVER w AS position,
           count(*) OVER (PARTITION BY subject_id, hadm_id, pharmacy_id, charttime) AS simultaneous,
           lead(charttime) OVER w AS next_time
    FROM parsed p WHERE charttime IS NOT NULL
    WINDOW w AS (PARTITION BY subject_id, hadm_id, pharmacy_id ORDER BY charttime, emar_id)
), control AS MATERIALIZED (
    SELECT q.*, min(position) FILTER (WHERE event_txt IS DISTINCT FROM 'Confirmed')
           OVER (PARTITION BY subject_id, hadm_id, pharmacy_id ORDER BY position
                 ROWS BETWEEN 1 FOLLOWING AND UNBOUNDED FOLLOWING) AS next_control_position
    FROM sequenced q
), starts AS MATERIALIZED (
    SELECT p.*, q.position AS start_position, q.simultaneous AS start_simultaneous,
           n.emar_id AS end_emar_id, n.event_txt AS next_control_status,
           n.charttime AS end_time, n.position AS end_position,
           n.complete_yes AS end_complete_yes
    FROM parsed p
    LEFT JOIN control q ON q.emar_id = p.emar_id
    LEFT JOIN control n ON n.subject_id IS NOT DISTINCT FROM q.subject_id
         AND n.hadm_id IS NOT DISTINCT FROM q.hadm_id
         AND n.pharmacy_id = q.pharmacy_id AND n.position = q.next_control_position
    WHERE p.event_txt IN ('Started','Delayed Started','Restarted')
), closed_rollup AS MATERIALIZED (
    SELECT s.emar_id,
           count(*) AS segment_head_rows,
           count(*) FILTER (WHERE r.event_txt = 'Confirmed') AS confirmation_rows,
           count(*) FILTER (WHERE r.simultaneous > 1) AS tied_head_rows,
           count(*) FILTER (WHERE r.identity_ok IS NOT TRUE) AS identity_problem_heads,
           count(*) FILTER (WHERE r.head_source = 'known_other_head') AS other_name_heads,
           count(*) FILTER (WHERE r.head_source = 'missing_head_order_assumption') AS missing_name_heads,
           count(*) FILTER (WHERE r.route_class NOT IN ('detail_iv','prescription_iv_fallback')) AS route_problem_heads,
           count(*) FILTER (WHERE r.detail_iv_route_rows + r.order_iv_route_rows > 0
               AND r.detail_other_route_rows + r.order_other_route_rows > 0) AS route_conflict_heads,
           sum(r.detail_other_route_rows) AS other_detail_route_rows,
           count(*) FILTER (WHERE r.route_class = 'prescription_iv_fallback') AS prescription_route_fallback_heads,
           sum(r.bad_detail_identity_rows) AS bad_detail_identity_rows,
           count(*) FILTER (WHERE r.product_rows <> 1) AS nonunit_product_count_heads,
           count(*) FILTER (WHERE r.position < s.end_position AND
                (r.parent_rows <> 1 OR r.rate IS NULL OR r.rate < 0
                 OR upper(trim(r.rate_unit)) IS DISTINCT FROM 'ML/HR')) AS bad_rate_intervals,
           count(*) FILTER (WHERE r.position < s.end_position AND r.rate = 0) AS zero_rate_intervals,
           count(*) FILTER (WHERE r.storetime IS NULL) AS missing_storetime_heads,
           count(*) FILTER (WHERE r.storetime < r.charttime) AS reversed_storetime_heads,
           sum(r.rate * extract(epoch FROM (r.next_time - r.charttime)) / 3600)
               FILTER (WHERE r.position < s.end_position) AS provisional_integral_ml
    FROM starts s JOIN sequenced r
      ON r.subject_id IS NOT DISTINCT FROM s.subject_id
     AND r.hadm_id IS NOT DISTINCT FROM s.hadm_id AND r.pharmacy_id = s.pharmacy_id
     AND r.position BETWEEN s.start_position AND s.end_position
    WHERE s.next_control_status IN ('Stopped','Stopped - Unscheduled')
    GROUP BY s.emar_id
), located AS MATERIALIZED (
    SELECT s.*, x.active_intervals, x.active_icu_intervals,
           x.active_named_non_icu_intervals, x.invalid_transfer_rows,
           CASE WHEN s.charttime IS NULL THEN 'missing_start_time'
                WHEN x.active_intervals = 0 THEN 'unknown_no_active_interval'
                WHEN x.active_intervals > 1 THEN 'conflict_multiple_active_intervals'
                WHEN x.active_icu_intervals = 1 THEN 'icu'
                WHEN x.active_named_non_icu_intervals = 1 THEN 'non_icu_start_point'
                ELSE 'unknown_careunit' END AS start_location_class
    FROM starts s CROSS JOIN LATERAL (
        SELECT count(*) FILTER (WHERE s.charttime >= t.intime AND s.charttime < t.outtime) AS active_intervals,
               count(*) FILTER (WHERE s.charttime >= t.intime AND s.charttime < t.outtime
                                AND u.careunit IS NOT NULL) AS active_icu_intervals,
               count(*) FILTER (WHERE s.charttime >= t.intime AND s.charttime < t.outtime
                                AND u.careunit IS NULL AND nullif(trim(t.careunit), '') IS NOT NULL
                                AND t.careunit <> 'UNKNOWN') AS active_named_non_icu_intervals,
               count(*) FILTER (WHERE t.intime IS NULL OR t.outtime IS NULL
                                OR t.outtime <= t.intime) AS invalid_transfer_rows
        FROM mimiciv_hosp.transfers t LEFT JOIN icu_units u ON u.careunit = t.careunit
        WHERE t.subject_id = s.subject_id AND t.hadm_id = s.hadm_id
          AND t.eventtype <> 'discharge'
    ) x
), classified AS MATERIALIZED (
    SELECT s.*, r.segment_head_rows, r.confirmation_rows, r.tied_head_rows,
           r.identity_problem_heads, r.other_name_heads, r.missing_name_heads,
           r.route_problem_heads, r.route_conflict_heads, r.other_detail_route_rows, r.prescription_route_fallback_heads,
           r.bad_detail_identity_rows AS segment_bad_detail_identity_rows,
           r.nonunit_product_count_heads, r.bad_rate_intervals, r.zero_rate_intervals,
           r.missing_storetime_heads, r.reversed_storetime_heads, r.provisional_integral_ml,
           CASE WHEN s.next_control_status IN ('Stopped','Stopped - Unscheduled')
                THEN extract(epoch FROM (s.end_time - s.charttime)) / 3600 END AS segment_hours,
           CASE WHEN s.identity_ok IS NOT TRUE THEN 'start_identity_problem'
                WHEN s.charttime IS NULL THEN 'missing_start_time'
                WHEN s.pharmacy_identity_problem_heads > 0 THEN 'identity_problem_in_pharmacy'
                WHEN s.stream_missing_time_heads > 0 THEN 'unknown_time_in_stream'
                WHEN s.head_source = 'known_other_head' THEN 'known_other_start_head'
                WHEN s.route_class NOT IN ('detail_iv','prescription_iv_fallback') THEN 'start_route_not_supported_iv'
                WHEN s.end_emar_id IS NULL THEN 'no_next_control'
                WHEN s.next_control_status NOT IN ('Stopped','Stopped - Unscheduled')
                     OR s.next_control_status IS NULL THEN 'next_control_not_stop'
                WHEN s.end_time <= s.charttime THEN 'nonpositive_duration'
                WHEN r.tied_head_rows > 0 THEN 'tied_event_times'
                WHEN r.identity_problem_heads > 0 THEN 'segment_identity_problem'
                WHEN r.other_name_heads > 0 THEN 'known_other_head_in_segment'
                WHEN r.route_problem_heads > 0 THEN 'segment_route_not_supported_iv'
                WHEN r.bad_detail_identity_rows > 0 THEN 'detail_identity_problem'
                WHEN r.bad_rate_intervals > 0 THEN 'missing_ambiguous_or_invalid_rate'
                WHEN r.provisional_integral_ml IS NULL OR r.provisional_integral_ml <= 0
                     THEN 'nonpositive_integrated_volume'
                ELSE 'none' END AS dose_exclusion
    FROM located s LEFT JOIN closed_rollup r ON r.emar_id = s.emar_id
)
SELECT 'sodium_rate_segment_v1'::text AS definition_version,
       subject_id, hadm_id, pharmacy_id, emar_id AS start_emar_id, event_txt AS start_status,
       charttime AS start_time, end_emar_id AS next_control_emar_id,
       next_control_status, end_time AS next_control_time,
       CASE WHEN next_control_status IN ('Stopped','Stopped - Unscheduled') THEN end_emar_id END AS end_emar_id,
       CASE WHEN next_control_status IN ('Stopped','Stopped - Unscheduled') THEN end_time END AS end_time,
       head_source AS start_head_source, identity_ok AS start_order_identity_ok, route_class AS start_route_class,
       stream_missing_time_heads, pharmacy_identity_problem_heads,
       segment_hours, segment_head_rows, confirmation_rows,
       CASE WHEN next_control_status IN ('Stopped','Stopped - Unscheduled') THEN end_complete_yes END AS end_complete_yes,
       tied_head_rows, identity_problem_heads, other_name_heads, missing_name_heads,
       route_problem_heads, route_conflict_heads, other_detail_route_rows, prescription_route_fallback_heads,
       segment_bad_detail_identity_rows, nonunit_product_count_heads,
       bad_rate_intervals, zero_rate_intervals, missing_storetime_heads, reversed_storetime_heads,
       start_location_class, active_intervals AS start_active_transfer_intervals,
       invalid_transfer_rows AS admission_invalid_transfer_rows,
       dose_exclusion, dose_exclusion = 'none' AS rate_integral_usable,
       CASE WHEN dose_exclusion = 'none' THEN provisional_integral_ml END AS rateintegrated_ml,
       CASE WHEN dose_exclusion = 'none' THEN provisional_integral_ml * 0.513 END AS estimated_sodium_meq,
       'piecewise_constant_charted_parent_rate_estimate'::text AS quantity_basis,
       false AS measured_dose, false AS entire_segment_non_icu_verified,
       CASE WHEN dose_exclusion <> 'none' THEN dose_exclusion
            WHEN start_location_class <> 'non_icu_start_point' THEN 'start_not_single_named_non_icu'
            ELSE 'none' END AS first_exclusion,
       dose_exclusion = 'none' AND start_location_class = 'non_icu_start_point' AS eligible_estimated_segment
FROM classified
ORDER BY subject_id, hadm_id, pharmacy_id, charttime NULLS LAST, emar_id;
