-- D003/D005 discovery audit only: start/restart eMAR heads are anchors, not
-- reconstructed infusions, decision events, or a final non-ICU cohort.
-- Audit window is [anchor - 4 hours, anchor); available means non-NULL
-- storetime <= anchor. These are explicit candidate rules, not frozen choices.
-- Next lab means earliest sampling time strictly AFTER the anchor, without a
-- maximum lag and without skipping missing numeric values. Keep EVERY tie.
-- No claim is made about actual infusion end or end + 3 hours.
-- Existing subject/hadm/item/charttime partial Na index supports parameterized
-- LATERAL lookups. LIMIT 1 below retrieves a timestamp only, never a lab value.
WITH icu_units(careunit) AS (
    VALUES ('Cardiac Vascular Intensive Care Unit (CVICU)'),
           ('Coronary Care Unit (CCU)'), ('Intensive Care Unit (ICU)'),
           ('Medical Intensive Care Unit (MICU)'),
           ('Medical/Surgical Intensive Care Unit (MICU/SICU)'),
           ('Neuro Surgical Intensive Care Unit (Neuro SICU)'),
           ('Surgical Intensive Care Unit (SICU)'), ('Trauma SICU (TSICU)')
), orders AS MATERIALIZED (
    SELECT pharmacy_id, min(subject_id) AS order_subject_id,
           min(hadm_id) AS order_hadm_id,
           count(DISTINCT subject_id) AS order_subjects,
           count(DISTINCT hadm_id) AS order_admissions,
           count(*) FILTER (WHERE subject_id IS NULL OR hadm_id IS NULL) AS missing_order_ids
    FROM mimiciv_hosp.prescriptions
    WHERE drug = 'Sodium Chloride 3% (Hypertonic)'
    GROUP BY pharmacy_id
), anchors AS MATERIALIZED (
    SELECT e.emar_id, e.subject_id, e.hadm_id, e.charttime, e.event_txt,
           CASE WHEN e.subject_id IS NULL OR e.hadm_id IS NULL THEN 'missing_event_identity'
                WHEN o.order_subjects <> 1 OR o.order_admissions <> 1 OR o.missing_order_ids > 0
                    THEN 'ambiguous_order_identity'
                WHEN e.subject_id IS DISTINCT FROM o.order_subject_id
                  OR e.hadm_id IS DISTINCT FROM o.order_hadm_id THEN 'identity_conflict'
                ELSE 'consistent' END AS identity_status
    FROM orders o JOIN mimiciv_hosp.emar e ON e.pharmacy_id = o.pharmacy_id
    WHERE e.event_txt IN ('Started', 'Delayed Started', 'Restarted')
), located AS MATERIALIZED (
    SELECT a.*, x.invalid_intervals > 0 AS admission_has_invalid_intervals,
           CASE WHEN x.active_intervals = 0 THEN 'unknown_no_active_interval'
                WHEN x.active_intervals > 1 THEN 'conflict_multiple_active_intervals'
                WHEN x.active_icu_intervals = 1 THEN 'icu'
                WHEN x.active_named_non_icu_intervals = 1 THEN 'non_icu_provisional'
                ELSE 'unknown_careunit' END AS location_status
    FROM anchors a
    CROSS JOIN LATERAL (
        SELECT count(*) FILTER (WHERE a.charttime >= t.intime AND a.charttime < t.outtime) AS active_intervals,
               count(*) FILTER (WHERE a.charttime >= t.intime AND a.charttime < t.outtime
                                 AND u.careunit IS NOT NULL) AS active_icu_intervals,
               count(*) FILTER (WHERE a.charttime >= t.intime AND a.charttime < t.outtime
                                 AND u.careunit IS NULL AND nullif(trim(t.careunit), '') IS NOT NULL
                                 AND t.careunit <> 'UNKNOWN') AS active_named_non_icu_intervals,
               count(*) FILTER (WHERE t.intime IS NULL OR t.outtime IS NULL OR t.outtime <= t.intime) AS invalid_intervals
        FROM mimiciv_hosp.transfers t LEFT JOIN icu_units u ON u.careunit = t.careunit
        WHERE t.subject_id = a.subject_id AND t.hadm_id = a.hadm_id
          AND t.eventtype <> 'discharge'
    ) x
    WHERE a.identity_status = 'consistent' AND a.charttime IS NOT NULL
), pre_labs AS MATERIALIZED (
    SELECT a.emar_id, a.charttime AS anchor_time, l.*
    FROM located a CROSS JOIN LATERAL (
        SELECT l.labevent_id, l.itemid, l.charttime, l.storetime, l.valuenum, l.valueuom
        FROM mimiciv_hosp.labevents l
        WHERE l.subject_id = a.subject_id AND l.hadm_id = a.hadm_id
          AND l.itemid IN (50983, 52623)
          AND l.charttime >= a.charttime - interval '4 hours' AND l.charttime < a.charttime
        OFFSET 0
    ) l
), pre_times AS MATERIALIZED (
    SELECT emar_id, max(charttime) AS latest_sample_time,
           max(charttime) FILTER (WHERE storetime <= anchor_time) AS latest_available_time
    FROM pre_labs GROUP BY emar_id
), post_times AS MATERIALIZED (
    SELECT a.emar_id, a.subject_id, a.hadm_id, a.charttime AS anchor_time,
           min(n.next_time) AS next_sample_time
    FROM located a CROSS JOIN LATERAL (
        SELECT (
            SELECT l.charttime FROM mimiciv_hosp.labevents l
            WHERE l.subject_id = a.subject_id AND l.hadm_id = a.hadm_id
              AND l.itemid = candidates.itemid AND l.itemid IN (50983, 52623)
              AND l.charttime > a.charttime
            ORDER BY l.charttime LIMIT 1
        ) AS next_time
        FROM (VALUES (50983), (52623)) candidates(itemid)
    ) n
    GROUP BY a.emar_id, a.subject_id, a.hadm_id, a.charttime
), post_labs AS MATERIALIZED (
    SELECT a.emar_id, a.anchor_time, l.*
    FROM post_times a CROSS JOIN LATERAL (
        SELECT l.labevent_id, l.itemid, l.charttime, l.storetime, l.valuenum, l.valueuom
        FROM mimiciv_hosp.labevents l
        WHERE l.subject_id = a.subject_id AND l.hadm_id = a.hadm_id
          AND l.itemid IN (50983, 52623) AND l.charttime = a.next_sample_time
        OFFSET 0
    ) l
), lab_roles AS MATERIALIZED (
    SELECT 'pre_window_all'::text AS lab_role, p.* FROM pre_labs p
    UNION ALL
    SELECT 'pre_latest_sample', p.* FROM pre_labs p JOIN pre_times t USING (emar_id)
    WHERE p.charttime = t.latest_sample_time
    UNION ALL
    SELECT 'pre_latest_available', p.* FROM pre_labs p JOIN pre_times t USING (emar_id)
    WHERE p.charttime = t.latest_available_time AND p.storetime <= p.anchor_time
    UNION ALL
    SELECT 'post_first_sample', p.* FROM post_labs p
), role_counts AS MATERIALIZED (
    SELECT emar_id,
           count(*) FILTER (WHERE lab_role = 'pre_window_all') AS pre_window_rows,
           count(*) FILTER (WHERE lab_role = 'pre_window_all' AND storetime <= anchor_time) AS pre_available_window_rows,
           count(*) FILTER (WHERE lab_role = 'pre_latest_sample') AS pre_latest_sample_rows,
           count(*) FILTER (WHERE lab_role = 'pre_latest_available') AS pre_latest_available_rows,
           count(*) FILTER (WHERE lab_role = 'post_first_sample') AS post_first_sample_rows
    FROM lab_roles GROUP BY emar_id
), coverage AS MATERIALIZED (
    SELECT a.*, coalesce(c.pre_window_rows, 0) AS pre_window_rows,
           coalesce(c.pre_available_window_rows, 0) AS pre_available_window_rows,
           coalesce(c.pre_latest_sample_rows, 0) AS pre_latest_sample_rows,
           coalesce(c.pre_latest_available_rows, 0) AS pre_latest_available_rows,
           coalesce(c.post_first_sample_rows, 0) AS post_first_sample_rows
    FROM located a LEFT JOIN role_counts c USING (emar_id)
), lab_profile AS MATERIALIZED (
    SELECT l.*, a.event_txt, a.location_status,
           abs(extract(epoch FROM (l.charttime - l.anchor_time))) / 3600 AS anchor_lag_hours,
           CASE WHEN abs(extract(epoch FROM (l.charttime - l.anchor_time))) <= 10800 THEN '0_to_3h_inclusive'
                WHEN abs(extract(epoch FROM (l.charttime - l.anchor_time))) <= 21600 THEN 'over_3_to_6h_inclusive'
                WHEN abs(extract(epoch FROM (l.charttime - l.anchor_time))) <= 86400 THEN 'over_6_to_24h_inclusive'
                ELSE 'over_24h' END AS lag_bucket
    FROM lab_roles l JOIN located a USING (emar_id)
)
SELECT 'anchor_inventory'::text AS profile_section,
       jsonb_build_object('event_txt', event_txt, 'identity_status', identity_status,
                          'missing_anchor_time', charttime IS NULL) AS dimensions,
       jsonb_build_object('candidate_anchor_rows', count(*), 'subjects', count(DISTINCT subject_id),
                          'admissions', count(DISTINCT hadm_id)) AS counters
FROM anchors GROUP BY event_txt, identity_status, charttime IS NULL
UNION ALL
SELECT 'anchor_coverage',
       jsonb_build_object('event_txt', event_txt, 'location_status', location_status,
           'admission_has_invalid_intervals', admission_has_invalid_intervals,
           'has_pre_window_lab', pre_window_rows > 0,
           'has_pre_available_lab', pre_latest_available_rows > 0,
           'has_post_first_sample', post_first_sample_rows > 0,
           'pre_latest_sample_has_ties', pre_latest_sample_rows > 1,
           'pre_latest_available_has_ties', pre_latest_available_rows > 1,
           'post_first_sample_has_ties', post_first_sample_rows > 1),
       jsonb_build_object('candidate_anchor_rows', count(*), 'subjects', count(DISTINCT subject_id),
           'admissions', count(DISTINCT hadm_id), 'pre_window_lab_rows', sum(pre_window_rows),
           'pre_available_window_lab_rows', sum(pre_available_window_rows),
           'pre_latest_sample_rows', sum(pre_latest_sample_rows),
           'pre_latest_available_rows', sum(pre_latest_available_rows),
           'post_first_sample_rows', sum(post_first_sample_rows))
FROM coverage GROUP BY event_txt, location_status, admission_has_invalid_intervals,
    pre_window_rows > 0, pre_latest_available_rows > 0, post_first_sample_rows > 0,
    pre_latest_sample_rows > 1, pre_latest_available_rows > 1, post_first_sample_rows > 1
UNION ALL
SELECT 'lab_value_time_profile',
       jsonb_build_object('lab_role', lab_role, 'event_txt', event_txt,
           'location_status', location_status, 'itemid', itemid, 'valueuom', valueuom,
           'anchor_lag_bucket', lag_bucket),
       jsonb_build_object('lab_rows', count(*), 'candidate_anchor_rows', count(DISTINCT emar_id),
           'missing_valuenum', count(*) FILTER (WHERE valuenum IS NULL),
           'finite_valuenum', count(*) FILTER (WHERE valuenum IS NOT NULL
                   AND valuenum::text NOT IN ('NaN', 'Infinity', '-Infinity')),
           'finite_valuenum_min', min(valuenum) FILTER (WHERE valuenum::text NOT IN ('NaN', 'Infinity', '-Infinity')),
           'finite_valuenum_max', max(valuenum) FILTER (WHERE valuenum::text NOT IN ('NaN', 'Infinity', '-Infinity')),
           'missing_unit', count(*) FILTER (WHERE nullif(trim(valueuom), '') IS NULL),
           'missing_storetime', count(*) FILTER (WHERE storetime IS NULL),
           'storetime_after_anchor', count(*) FILTER (WHERE storetime > anchor_time),
           'storetime_before_sample', count(*) FILTER (WHERE storetime < charttime),
           'min_anchor_lag_hours', min(anchor_lag_hours), 'max_anchor_lag_hours', max(anchor_lag_hours),
           'min_store_minus_sample_hours', min(extract(epoch FROM (storetime - charttime)) / 3600),
           'max_store_minus_sample_hours', max(extract(epoch FROM (storetime - charttime)) / 3600))
FROM lab_profile GROUP BY lab_role, event_txt, location_status, itemid, valueuom, lag_bucket
ORDER BY profile_section, dimensions;
