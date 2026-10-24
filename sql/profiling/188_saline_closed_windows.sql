-- D003/D005 diagnostic only; closed order-linked segments are not validated
-- treatment episodes, actual volumes, actions, or a frozen non-ICU cohort.
-- Candidate construction from WITH orders through classified is byte-identical
-- to 185_saline_sequence_audit.sql. New anchors are recovered by emar_id below.
-- Transfer windows are half-open; stop and post-end-lab point locations are separate.
-- The treatment-to-first-post-end-lab window exists only when that lab exists;
-- report its denominator independently, never count absent labs as clean coverage.
-- Every cutpoint is evaluated, so ICU/gap/overlap between ward endpoints survives.
-- Invalid admission intervals are reported; a potentially intersecting invalid
-- interval prevents a clean-window classification. Unknown-time invalid rows
-- cannot be localized and are conservatively potentially intersecting.
-- Labs use same subject/admission and Na candidates 50983/52623, strictly after
-- each anchor; timestamp LIMIT retrieves no value and all first-time ties remain.
-- Other starts cover this exact prescription drug only, not all cointerventions.
-- Unique order identity can associate missing/conflicting eMAR identity with an
-- admission for an anomaly flag, never as a valid extra treatment.
-- First-lab mEq/L is the current candidate unit; other nonempty units are flagged
-- unconfirmed, with no implicit conversion. Invalid-at-point intervals are
-- separately flagged even when they only touch the end of a half-open window.
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
), segments AS MATERIALIZED (
    SELECT c.*, s.pharmacy_id, s.charttime AS segment_start, s.endpoint_time AS segment_end
    FROM classified c JOIN starts s USING (emar_id)
), icu_units(careunit) AS (
    VALUES ('Cardiac Vascular Intensive Care Unit (CVICU)'),
           ('Coronary Care Unit (CCU)'), ('Intensive Care Unit (ICU)'),
           ('Medical Intensive Care Unit (MICU)'),
           ('Medical/Surgical Intensive Care Unit (MICU/SICU)'),
           ('Neuro Surgical Intensive Care Unit (Neuro SICU)'),
           ('Surgical Intensive Care Unit (SICU)'), ('Trauma SICU (TSICU)')
), admission_transfers AS MATERIALIZED (
    SELECT a.subject_id, a.hadm_id, t.eventtype, t.careunit, t.intime, t.outtime,
           (t.eventtype IS NOT NULL AND t.intime IS NOT NULL AND t.outtime IS NOT NULL
             AND t.outtime > t.intime) AS valid_interval,
           u.careunit IS NOT NULL AS is_icu,
           (u.careunit IS NULL AND nullif(trim(t.careunit),'') IS NOT NULL
             AND upper(trim(t.careunit)) <> 'UNKNOWN') AS is_named_non_icu
    FROM (SELECT DISTINCT subject_id, hadm_id FROM segments) a
    JOIN mimiciv_hosp.transfers t ON t.subject_id = a.subject_id AND t.hadm_id = a.hadm_id
    LEFT JOIN icu_units u ON u.careunit = t.careunit
    WHERE t.eventtype IS DISTINCT FROM 'discharge'
), post_times AS MATERIALIZED (
    SELECT s.emar_id, s.subject_id, s.hadm_id, s.segment_start, s.segment_end,
           a.lab_role, a.anchor_time, min(n.next_time) AS next_sample_time
    FROM segments s CROSS JOIN LATERAL (VALUES
        ('post_start'::text,s.segment_start), ('post_end'::text,s.segment_end)
    ) a(lab_role,anchor_time)
    CROSS JOIN LATERAL (
        SELECT (SELECT l.charttime FROM mimiciv_hosp.labevents l
                WHERE l.subject_id = s.subject_id AND l.hadm_id = s.hadm_id
                  AND l.itemid = candidates.itemid AND l.itemid IN (50983,52623)
                  AND l.charttime > a.anchor_time
                ORDER BY l.charttime LIMIT 1) AS next_time
        FROM (VALUES (50983),(52623)) candidates(itemid)
    ) n
    GROUP BY s.emar_id,s.subject_id,s.hadm_id,s.segment_start,s.segment_end,a.lab_role,a.anchor_time
), windows AS MATERIALIZED (
    SELECT s.emar_id, s.subject_id, s.hadm_id, s.integral_computable,
           x.window_role, x.window_start, x.window_end
    FROM segments s CROSS JOIN LATERAL (VALUES
        ('treatment'::text, s.segment_start, s.segment_end),
        ('context_and_treatment'::text, s.segment_start - interval '4 hours', s.segment_end)
    ) x(window_role, window_start, window_end)
    UNION ALL
    SELECT s.emar_id,s.subject_id,s.hadm_id,s.integral_computable,
           'treatment_to_post_end_lab',s.segment_start,p.next_sample_time
    FROM segments s JOIN post_times p USING (emar_id)
    WHERE p.lab_role='post_end' AND p.next_sample_time IS NOT NULL
), cutpoints AS MATERIALIZED (
    SELECT emar_id, window_role, window_start AS cutpoint FROM windows
    UNION
    SELECT emar_id, window_role, window_end FROM windows
    UNION
    SELECT w.emar_id, w.window_role, greatest(w.window_start, t.intime)
    FROM windows w JOIN admission_transfers t USING (subject_id, hadm_id)
    WHERE t.valid_interval AND t.intime < w.window_end AND t.outtime > w.window_start
    UNION
    SELECT w.emar_id, w.window_role, least(w.window_end, t.outtime)
    FROM windows w JOIN admission_transfers t USING (subject_id, hadm_id)
    WHERE t.valid_interval AND t.intime < w.window_end AND t.outtime > w.window_start
), atoms_base AS MATERIALIZED (
    -- Do not repeatedly evaluate the cutpoint window function for every window.
    -- Closed-segment cardinality is underestimated by the upstream sequence plan.
    SELECT emar_id, window_role, cutpoint AS atom_start,
           lead(cutpoint) OVER (PARTITION BY emar_id, window_role ORDER BY cutpoint) AS atom_end
    FROM cutpoints
), atoms AS MATERIALIZED (
    SELECT w.*, a.atom_start, a.atom_end,
           extract(epoch FROM (a.atom_end - a.atom_start)) AS seconds,
           count(t.intime) AS active_intervals,
           count(*) FILTER (WHERE t.is_icu) AS active_icu_intervals,
           count(*) FILTER (WHERE t.is_named_non_icu) AS active_named_non_icu_intervals
    FROM atoms_base a JOIN windows w USING (emar_id, window_role)
    LEFT JOIN admission_transfers t ON t.subject_id = w.subject_id AND t.hadm_id = w.hadm_id
      AND t.valid_interval AND t.intime <= a.atom_start AND t.outtime >= a.atom_end
    WHERE a.atom_end > a.atom_start AND w.window_end > w.window_start
    GROUP BY w.emar_id, w.subject_id, w.hadm_id, w.integral_computable,
             w.window_role, w.window_start, w.window_end, a.atom_start, a.atom_end
), atom_summary AS MATERIALIZED (
    SELECT emar_id, window_role, count(*) AS atoms,
           sum(seconds) AS evaluated_seconds,
           sum(seconds) FILTER (WHERE active_intervals = 0) AS gap_seconds,
           sum(seconds) FILTER (WHERE active_intervals > 1) AS overlap_seconds,
           sum(seconds) FILTER (WHERE active_icu_intervals > 0) AS icu_seconds,
           sum(seconds) FILTER (WHERE active_intervals = 1 AND active_named_non_icu_intervals = 1) AS single_named_non_icu_seconds,
           sum(seconds) FILTER (WHERE active_intervals = 1 AND active_icu_intervals = 0
                                AND active_named_non_icu_intervals = 0) AS unknown_unit_seconds
    FROM atoms GROUP BY emar_id, window_role
), invalid_summary AS MATERIALIZED (
    SELECT w.emar_id, w.window_role,
           count(*) FILTER (WHERE t.valid_interval IS FALSE) AS invalid_admission_rows,
           count(*) FILTER (WHERE t.valid_interval IS FALSE AND
             (t.intime IS NULL OR t.outtime IS NULL OR
              (greatest(t.intime,t.outtime) >= w.window_start
               AND least(t.intime,t.outtime) < w.window_end))) AS potentially_intersecting_invalid_rows
    FROM windows w LEFT JOIN admission_transfers t USING (subject_id, hadm_id)
    GROUP BY w.emar_id, w.window_role
), window_status AS MATERIALIZED (
    SELECT w.*, coalesce(a.atoms,0) AS atoms, coalesce(a.evaluated_seconds,0) AS evaluated_seconds,
           coalesce(a.gap_seconds,0) AS gap_seconds, coalesce(a.overlap_seconds,0) AS overlap_seconds,
           coalesce(a.icu_seconds,0) AS icu_seconds,
           coalesce(a.unknown_unit_seconds,0) AS unknown_unit_seconds,
           coalesce(a.single_named_non_icu_seconds,0) AS single_named_non_icu_seconds,
           i.invalid_admission_rows, i.potentially_intersecting_invalid_rows,
           CASE WHEN w.window_end <= w.window_start THEN 'invalid_window_duration'
                WHEN a.icu_seconds > 0 THEN 'contains_icu'
                WHEN a.overlap_seconds > 0 THEN 'contains_overlap'
                WHEN a.gap_seconds > 0 THEN 'contains_gap'
                WHEN a.unknown_unit_seconds > 0 THEN 'contains_unknown_careunit'
                WHEN i.potentially_intersecting_invalid_rows > 0 THEN 'potential_invalid_transfer'
                WHEN a.evaluated_seconds = extract(epoch FROM (w.window_end - w.window_start))
                 AND a.single_named_non_icu_seconds = a.evaluated_seconds
                    THEN 'complete_single_named_non_icu_provisional'
                ELSE 'unexplained_coverage' END AS location_status
    FROM windows w LEFT JOIN atom_summary a USING (emar_id,window_role)
    JOIN invalid_summary i USING (emar_id,window_role)
), endpoint_points AS MATERIALIZED (
    SELECT emar_id,subject_id,hadm_id,'stop'::text AS point_role,segment_end AS point_time FROM segments
    UNION ALL
    SELECT emar_id,subject_id,hadm_id,'post_end_lab',next_sample_time
    FROM post_times WHERE lab_role='post_end' AND next_sample_time IS NOT NULL
), endpoint_location AS MATERIALIZED (
    SELECT s.emar_id,s.point_role,
           (SELECT count(*) FROM admission_transfers b
            WHERE b.subject_id=s.subject_id AND b.hadm_id=s.hadm_id AND b.valid_interval IS FALSE
              AND (b.intime IS NULL OR b.outtime IS NULL OR
                  (s.point_time >= least(b.intime,b.outtime) AND s.point_time <= greatest(b.intime,b.outtime)))) AS invalid_at_point_rows,
           CASE WHEN count(t.intime) = 0 THEN 'unknown_no_active_interval'
                WHEN count(t.intime) > 1 THEN 'conflict_multiple_active_intervals'
                WHEN count(*) FILTER (WHERE t.is_icu) = 1 THEN 'icu'
                WHEN count(*) FILTER (WHERE t.is_named_non_icu) = 1 THEN 'non_icu_provisional'
                ELSE 'unknown_careunit' END AS point_status
    FROM endpoint_points s LEFT JOIN admission_transfers t
      ON t.subject_id = s.subject_id AND t.hadm_id = s.hadm_id AND t.valid_interval
     AND t.intime <= s.point_time AND t.outtime > s.point_time
    GROUP BY s.emar_id,s.point_role,s.subject_id,s.hadm_id,s.point_time
), first_labs AS MATERIALIZED (
    -- Fixed item branches use the full (subject,admission,item,time) index key.
    -- This is the same candidate set and preserves all rows/ties in both items.
    SELECT p.*, l.* FROM post_times p
    CROSS JOIN (VALUES (50983),(52623)) candidates(itemid)
    CROSS JOIN LATERAL (
        SELECT l.labevent_id,l.itemid,l.charttime,l.storetime,l.valuenum,l.valueuom
        FROM mimiciv_hosp.labevents l
        WHERE l.subject_id = p.subject_id AND l.hadm_id = p.hadm_id
          AND l.itemid = candidates.itemid AND l.itemid IN (50983,52623)
          AND l.charttime = p.next_sample_time
        OFFSET 0
    ) l
), lab_summary AS MATERIALIZED (
    SELECT p.emar_id,p.lab_role,p.next_sample_time,
           count(l.labevent_id) AS lab_rows,
           count(*) FILTER (WHERE l.labevent_id IS NOT NULL AND l.valuenum IS NOT NULL
               AND l.valuenum::text NOT IN ('NaN','Infinity','-Infinity')) AS finite_numeric_rows,
           count(*) FILTER (WHERE l.labevent_id IS NOT NULL AND nullif(trim(l.valueuom),'') IS NULL) AS missing_unit_rows,
           count(DISTINCT l.valueuom) AS distinct_units,
           count(*) FILTER (WHERE l.labevent_id IS NOT NULL AND nullif(trim(l.valueuom),'') IS NOT NULL
                            AND l.valueuom IS DISTINCT FROM 'mEq/L') AS unconfirmed_unit_rows,
           count(*) FILTER (WHERE l.labevent_id IS NOT NULL AND l.storetime IS NULL) AS missing_storetime_rows,
           count(*) FILTER (WHERE l.storetime < l.charttime) AS reversed_storetime_rows
    FROM post_times p LEFT JOIN first_labs l USING (emar_id,lab_role)
    GROUP BY p.emar_id,p.lab_role,p.next_sample_time
), associated_start_events AS MATERIALIZED (
    -- Actual eMAR identity OR a unique, complete prescription identity associates
    -- an anomaly with an admission. Conflicting/missing event identity is only a
    -- warning; it never counts as an identity-valid additional administration.
    SELECT e.*,o.order_subject,o.order_hadm,
           (o.subjects=1 AND o.admissions=1 AND o.missing_ids=0) AS unique_order_identity
    FROM events e JOIN orders o USING (pharmacy_id)
    WHERE e.event_txt IN ('Started','Delayed Started','Restarted')
), other_starts AS MATERIALIZED (
    SELECT s.emar_id,
           count(*) FILTER (WHERE e.identity_ok AND e.charttime = s.segment_start) AS at_start,
           count(*) FILTER (WHERE e.identity_ok AND e.charttime > s.segment_start AND e.charttime < s.segment_end) AS inside_segment,
           count(*) FILTER (WHERE e.identity_ok AND e.charttime = s.segment_end) AS at_end,
           count(*) FILTER (WHERE e.identity_ok AND e.charttime > s.segment_end AND e.charttime < l.next_sample_time) AS after_end_before_lab,
           count(*) FILTER (WHERE e.identity_ok AND e.charttime = l.next_sample_time) AS at_lab,
           count(*) FILTER (WHERE e.identity_ok AND e.charttime >= s.segment_start AND e.charttime <= l.next_sample_time
                             AND e.pharmacy_id = s.pharmacy_id) AS same_pharmacy_start_through_lab,
           count(*) FILTER (WHERE e.identity_ok AND e.charttime >= s.segment_start AND e.charttime <= l.next_sample_time
                             AND e.pharmacy_id <> s.pharmacy_id) AS other_pharmacy_start_through_lab,
           count(*) FILTER (WHERE e.identity_ok AND e.emar_id IS NOT NULL AND e.charttime IS NULL) AS unknown_time_in_admission,
           count(*) FILTER (WHERE e.identity_ok IS NOT TRUE AND e.emar_id IS NOT NULL) AS identity_anomaly_in_admission
    FROM segments s JOIN lab_summary l ON l.emar_id = s.emar_id AND l.lab_role = 'post_end'
    LEFT JOIN associated_start_events e ON
      ((e.subject_id = s.subject_id AND e.hadm_id = s.hadm_id)
       OR (e.unique_order_identity AND e.order_subject=s.subject_id AND e.order_hadm=s.hadm_id))
      AND e.event_txt IN ('Started','Delayed Started','Restarted') AND e.emar_id <> s.emar_id
    GROUP BY s.emar_id
), segment_treatment_location AS MATERIALIZED (
    -- Keep each keyed association materialized: upstream estimates are one row
    -- versus >1000 actual rows. One large join lets nested-loop plans repeatedly
    -- recompute already joined subtrees; this staging preserves identical rows.
    SELECT s.*,w.location_status AS treatment_location
    FROM segments s JOIN window_status w ON w.emar_id=s.emar_id AND w.window_role='treatment'
), segment_context_location AS MATERIALIZED (
    SELECT s.*,c.location_status AS context_treatment_location
    FROM segment_treatment_location s JOIN window_status c
      ON c.emar_id=s.emar_id AND c.window_role='context_and_treatment'
), segment_stop_location AS MATERIALIZED (
    SELECT s.*,e.point_status AS stop_point_status,e.invalid_at_point_rows AS stop_point_invalid_rows
    FROM segment_context_location s JOIN endpoint_location e ON e.emar_id=s.emar_id AND e.point_role='stop'
), segment_lab_location AS MATERIALIZED (
    SELECT s.*,e.point_status AS lab_point_status,e.invalid_at_point_rows AS lab_point_invalid_rows
    FROM segment_stop_location s LEFT JOIN endpoint_location e ON e.emar_id=s.emar_id AND e.point_role='post_end_lab'
), segment_observation_location AS MATERIALIZED (
    SELECT s.*,v.location_status AS treatment_to_lab_location
    FROM segment_lab_location s LEFT JOIN window_status v
      ON v.emar_id=s.emar_id AND v.window_role='treatment_to_post_end_lab'
), segment_start_labs AS MATERIALIZED (
    SELECT s.*,b.next_sample_time AS start_next_lab_time,b.lab_rows AS start_lab_rows
    FROM segment_observation_location s JOIN lab_summary b ON b.emar_id=s.emar_id AND b.lab_role='post_start'
), segment_end_labs AS MATERIALIZED (
    SELECT s.*,l.next_sample_time AS end_next_lab_time,l.lab_rows AS end_lab_rows,
           l.finite_numeric_rows AS end_finite_rows,l.missing_unit_rows AS end_missing_unit_rows,
           l.unconfirmed_unit_rows AS end_unconfirmed_unit_rows,
           l.missing_storetime_rows AS end_missing_storetime_rows,
           l.reversed_storetime_rows AS end_reversed_storetime_rows
    FROM segment_start_labs s JOIN lab_summary l ON l.emar_id=s.emar_id AND l.lab_role='post_end'
), segment_audit AS MATERIALIZED (
    SELECT s.*,o.at_start,o.inside_segment,o.at_end,o.after_end_before_lab,o.at_lab,
           o.same_pharmacy_start_through_lab,o.other_pharmacy_start_through_lab,
           o.unknown_time_in_admission,o.identity_anomaly_in_admission,
           CASE WHEN NOT s.integral_computable THEN '01_integral_not_computable'
                WHEN s.treatment_location <> 'complete_single_named_non_icu_provisional' THEN '02_treatment_window_not_clean'
                WHEN s.context_treatment_location <> 'complete_single_named_non_icu_provisional' THEN '03_context_treatment_window_not_clean'
                WHEN s.treatment_to_lab_location <> 'complete_single_named_non_icu_provisional' THEN '03b_treatment_to_lab_window_not_clean'
                WHEN s.lab_point_status <> 'non_icu_provisional' THEN '03c_lab_point_not_single_named_non_icu'
                WHEN s.lab_point_invalid_rows > 0 THEN '03d_lab_point_invalid_transfer'
                WHEN s.end_lab_rows = 0 THEN '04_no_post_end_sample'
                WHEN s.end_lab_rows > 1 THEN '05_post_end_ties'
                WHEN s.end_finite_rows = 0 THEN '06_post_end_nonfinite_or_missing_value'
                WHEN s.end_missing_unit_rows > 0 THEN '07_post_end_missing_unit'
                WHEN s.end_unconfirmed_unit_rows > 0 THEN '07b_post_end_unconfirmed_unit'
                WHEN o.at_start + o.inside_segment + o.at_end + o.after_end_before_lab + o.at_lab > 0
                    THEN '08_other_exact_drug_start_at_or_between_boundaries'
                WHEN s.end_missing_storetime_rows + s.end_reversed_storetime_rows > 0 THEN '08b_post_end_storetime_anomaly'
                WHEN o.unknown_time_in_admission + o.identity_anomaly_in_admission > 0
                    THEN '09_other_start_time_or_identity_uncertain'
                ELSE '10_clear_under_diagnostics_not_accepted_cohort' END AS diagnostic_flow
    FROM segment_end_labs s JOIN other_starts o ON o.emar_id=s.emar_id
)
SELECT 'candidate_summary'::text AS section, '{}'::jsonb AS dimensions, count(*) AS records,
       jsonb_build_object('subjects',count(DISTINCT subject_id),'admissions',count(DISTINCT hadm_id),
           'integral_computable',count(*) FILTER (WHERE integral_computable)) AS counters
FROM segments
UNION ALL
SELECT 'window_coverage',jsonb_build_object('window_role',window_role,'location_status',location_status,
       'integral_computable',integral_computable),count(*),
       jsonb_build_object('subjects',count(DISTINCT subject_id),'admissions',count(DISTINCT hadm_id),
           'with_gap',count(*) FILTER (WHERE gap_seconds>0),'with_overlap',count(*) FILTER (WHERE overlap_seconds>0),
           'with_icu',count(*) FILTER (WHERE icu_seconds>0),'with_unknown_unit',count(*) FILTER (WHERE unknown_unit_seconds>0),
           'with_invalid_admission_transfer',count(*) FILTER (WHERE invalid_admission_rows>0),
           'with_potential_invalid_transfer',count(*) FILTER (WHERE potentially_intersecting_invalid_rows>0),
           'evaluated_hours',sum(evaluated_seconds)/3600,'gap_hours',sum(gap_seconds)/3600,
           'overlap_hours',sum(overlap_seconds)/3600,'icu_hours',sum(icu_seconds)/3600,
           'single_named_non_icu_hours',sum(single_named_non_icu_seconds)/3600)
FROM window_status GROUP BY window_role,location_status,integral_computable
UNION ALL
SELECT 'segment_lab_coverage',jsonb_build_object('integral_computable',integral_computable,
       'treatment_location',treatment_location,'context_treatment_location',context_treatment_location,
       'stop_point_status',stop_point_status,'lab_point_status',lab_point_status,
       'treatment_to_lab_location',treatment_to_lab_location,'has_post_start',start_lab_rows>0,'has_post_end',end_lab_rows>0,
       'post_end_ties',end_lab_rows>1,'post_start_at_or_before_end',start_next_lab_time<=segment_end),count(*),
       jsonb_build_object('subjects',count(DISTINCT subject_id),'admissions',count(DISTINCT hadm_id),
           'post_start_lab_rows',sum(start_lab_rows),'post_end_lab_rows',sum(end_lab_rows),
           'same_first_sample',count(*) FILTER (WHERE start_next_lab_time=end_next_lab_time),
           'post_end_finite_rows',sum(end_finite_rows),'post_end_missing_unit_rows',sum(end_missing_unit_rows),
           'post_end_missing_storetime_rows',sum(end_missing_storetime_rows),
           'post_end_reversed_storetime_rows',sum(end_reversed_storetime_rows),
           'post_end_unconfirmed_unit_rows',sum(end_unconfirmed_unit_rows),
           'stop_point_invalid_rows',sum(stop_point_invalid_rows),
           'lab_point_invalid_rows',sum(lab_point_invalid_rows),
           'min_end_to_lab_hours',min(extract(epoch FROM (end_next_lab_time-segment_end))/3600),
           'median_end_to_lab_hours',percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM (end_next_lab_time-segment_end))/3600),
           'max_end_to_lab_hours',max(extract(epoch FROM (end_next_lab_time-segment_end))/3600),
           'min_vs_end_plus_3h_hours',min(extract(epoch FROM (end_next_lab_time-segment_end))/3600-3),
           'max_vs_end_plus_3h_hours',max(extract(epoch FROM (end_next_lab_time-segment_end))/3600-3))
FROM segment_audit GROUP BY integral_computable,treatment_location,context_treatment_location,stop_point_status,lab_point_status,treatment_to_lab_location,
    start_lab_rows>0,end_lab_rows>0,end_lab_rows>1,start_next_lab_time<=segment_end
UNION ALL
SELECT 'first_lab_profile',jsonb_build_object('lab_role',l.lab_role,'itemid',l.itemid,'valueuom',l.valueuom,
       'treatment_location',a.treatment_location,'integral_computable',a.integral_computable,
       'end_lag_bucket',CASE WHEN l.charttime <= l.segment_end THEN 'at_or_before_end'
            WHEN l.charttime <= l.segment_end+interval '3 hours' THEN '(0,3]h'
            WHEN l.charttime <= l.segment_end+interval '6 hours' THEN '(3,6]h'
            WHEN l.charttime <= l.segment_end+interval '24 hours' THEN '(6,24]h' ELSE '>24h' END),count(*),
       jsonb_build_object('segments',count(DISTINCT l.emar_id),'subjects',count(DISTINCT l.subject_id),
          'admissions',count(DISTINCT l.hadm_id),'missing_valuenum',count(*) FILTER (WHERE l.valuenum IS NULL),
          'nonfinite_valuenum',count(*) FILTER (WHERE l.valuenum::text IN ('NaN','Infinity','-Infinity')),
          'missing_storetime',count(*) FILTER (WHERE l.storetime IS NULL),
          'storetime_before_sample',count(*) FILTER (WHERE l.storetime<l.charttime))
FROM first_labs l JOIN segment_audit a USING (emar_id)
GROUP BY l.lab_role,l.itemid,l.valueuom,a.treatment_location,a.integral_computable,
         CASE WHEN l.charttime <= l.segment_end THEN 'at_or_before_end'
            WHEN l.charttime <= l.segment_end+interval '3 hours' THEN '(0,3]h'
            WHEN l.charttime <= l.segment_end+interval '6 hours' THEN '(3,6]h'
            WHEN l.charttime <= l.segment_end+interval '24 hours' THEN '(6,24]h' ELSE '>24h' END
UNION ALL
SELECT 'other_start_coverage',jsonb_build_object('integral_computable',integral_computable,
       'treatment_location',treatment_location,'at_start',at_start>0,'inside_segment',inside_segment>0,
       'at_end',at_end>0,'after_end_before_lab',after_end_before_lab>0,'at_lab',at_lab>0,
       'post_end_sample_exists',end_lab_rows>0),count(*),
       jsonb_build_object('subjects',count(DISTINCT subject_id),'admissions',count(DISTINCT hadm_id),
         'at_start',sum(at_start),'inside_segment',sum(inside_segment),'at_end',sum(at_end),
         'after_end_before_lab',sum(after_end_before_lab),'at_lab',sum(at_lab),
         'same_pharmacy_start_through_lab',sum(same_pharmacy_start_through_lab),
         'other_pharmacy_start_through_lab',sum(other_pharmacy_start_through_lab),
         'with_unknown_time_start_in_admission',count(*) FILTER (WHERE unknown_time_in_admission>0),
         'with_identity_anomalous_start_in_admission',count(*) FILTER (WHERE identity_anomaly_in_admission>0))
FROM segment_audit GROUP BY integral_computable,treatment_location,at_start>0,inside_segment>0,
    at_end>0,after_end_before_lab>0,at_lab>0,end_lab_rows>0
UNION ALL
SELECT 'diagnostic_flow',jsonb_build_object('first_flag',diagnostic_flow),count(*),
       jsonb_build_object('subjects',count(DISTINCT subject_id),'admissions',count(DISTINCT hadm_id))
FROM segment_audit GROUP BY diagnostic_flow
ORDER BY section,dimensions;
