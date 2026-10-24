-- PRIVATE ROW OUTPUT. Candidate zero-decision clinical context.
-- Read only. Use existing render_opportunities with validated admission keys.
-- Project D003/D005 choice: admission-aligned grid t=admittime+4h*n, n>=1;
-- require t+4h<=dischtime. This four-hour cell selects zero opportunities;
-- it is NOT a dose accumulation window. No zero action is assigned here.
-- outcome_after_time=t; same pre/post/location rules as query 314.
-- Pre electrolyte may be missing/invalid and does not exclude a candidate.
-- Invalid/nonunique admission identity or clocks cannot produce a grid.
-- Caller checks treatment activity and new exposure through the selected lab.
WITH requested_admissions(subject_id, hadm_id) AS (
    VALUES __ADMISSION_KEYS__
), requested_keys AS MATERIALIZED (
    SELECT DISTINCT subject_id::integer AS subject_id, hadm_id::integer AS hadm_id
    FROM requested_admissions
), admission_evidence AS MATERIALIZED (
    SELECT k.subject_id, k.hadm_id, count(a.hadm_id) AS admission_rows,
           count(*) FILTER (WHERE a.subject_id = k.subject_id) AS subject_match_rows,
           min(a.admittime) FILTER (WHERE a.subject_id = k.subject_id) AS admittime,
           min(a.dischtime) FILTER (WHERE a.subject_id = k.subject_id) AS dischtime
    FROM requested_keys k
    LEFT JOIN mimiciv_hosp.admissions a ON a.hadm_id = k.hadm_id
    GROUP BY k.subject_id, k.hadm_id
), usable_admissions AS MATERIALIZED (
    SELECT *
    FROM admission_evidence
    WHERE subject_id IS NOT NULL AND hadm_id IS NOT NULL
      AND admission_rows = 1 AND subject_match_rows = 1
      AND admittime IS NOT NULL AND dischtime IS NOT NULL
      AND isfinite(admittime) AND isfinite(dischtime)
      AND dischtime >= admittime + interval '8 hours'
), opportunities AS MATERIALIZED (
    SELECT a.*, g.opportunity_index, g.anchor_time,
           g.anchor_time + interval '4 hours' AS action_end,
           g.anchor_time AS outcome_after_time,
           ''::text AS input_parse_problem,
           NULL::text AS decision_context_exclusion,
           g.anchor_time + interval '24 hours' AS outcome_deadline
    FROM usable_admissions a
    CROSS JOIN LATERAL generate_series(
        a.admittime + interval '4 hours',
        a.dischtime - interval '4 hours',
        interval '4 hours'
    ) WITH ORDINALITY AS g(anchor_time, opportunity_index)
), icu_units(careunit) AS (
    VALUES ('Cardiac Vascular Intensive Care Unit (CVICU)'),
           ('Coronary Care Unit (CCU)'), ('Intensive Care Unit (ICU)'),
           ('Medical Intensive Care Unit (MICU)'),
           ('Medical/Surgical Intensive Care Unit (MICU/SICU)'),
           ('Neuro Surgical Intensive Care Unit (Neuro SICU)'),
           ('Surgical Intensive Care Unit (SICU)'), ('Trauma SICU (TSICU)')
), evidence AS MATERIALIZED (
    SELECT e.*, t.active_transfer_rows, t.active_icu_rows, t.active_named_non_icu_rows,
           t.invalid_transfer_rows, pre.lab_time AS pre_lab_time, pre.lab_rows AS pre_lab_rows,
           pre.lab_ids AS pre_labevent_ids, pre.valid_rows AS pre_valid_rows,
           pre.distinct_values AS pre_distinct_values, pre.lab_value AS pre_lab_value,
           pre.latest_storetime AS pre_latest_storetime,
           post.lab_time AS post_lab_time, post.lab_rows AS post_lab_rows,
           post.lab_ids AS post_labevent_ids, post.valid_rows AS post_valid_rows,
           post.distinct_values AS post_distinct_values, post.lab_value AS post_lab_value,
           post.latest_storetime AS post_latest_storetime,
           post.missing_storetime_rows AS post_missing_storetime_rows,
           post.reversed_storetime_rows AS post_reversed_storetime_rows
    FROM opportunities e
    CROSS JOIN LATERAL (
        SELECT count(*) FILTER (WHERE t.intime <= e.anchor_time AND e.anchor_time < t.outtime) AS active_transfer_rows,
               count(*) FILTER (WHERE t.intime <= e.anchor_time AND e.anchor_time < t.outtime
                 AND u.careunit IS NOT NULL) AS active_icu_rows,
               count(*) FILTER (WHERE t.intime <= e.anchor_time AND e.anchor_time < t.outtime
                 AND u.careunit IS NULL AND nullif(trim(t.careunit),'') IS NOT NULL
                 AND upper(trim(t.careunit)) <> 'UNKNOWN') AS active_named_non_icu_rows,
               count(*) FILTER (WHERE
                 (t.intime IS NULL AND (t.outtime IS NULL OR e.anchor_time < t.outtime))
                 OR (t.outtime IS NULL AND t.intime <= e.anchor_time)
                 OR (t.outtime <= t.intime AND e.anchor_time BETWEEN t.outtime AND t.intime))
                 AS invalid_transfer_rows
        FROM mimiciv_hosp.transfers t LEFT JOIN icu_units u ON u.careunit = t.careunit
        WHERE e.decision_context_exclusion IS NULL
          AND t.subject_id = e.subject_id AND t.hadm_id = e.hadm_id
          AND t.eventtype IS DISTINCT FROM 'discharge'
        OFFSET 0
    ) t
    CROSS JOIN LATERAL (
        SELECT max(charttime) AS lab_time FROM mimiciv_hosp.labevents l
        WHERE e.decision_context_exclusion IS NULL
          AND l.subject_id = e.subject_id AND l.hadm_id = e.hadm_id AND l.itemid = __LAB_ITEM_ID__
          AND l.charttime >= e.anchor_time - interval '4 hours'
          AND l.charttime <= e.anchor_time AND l.storetime <= e.anchor_time
        OFFSET 0
    ) pre_time
    CROSS JOIN LATERAL (
        SELECT min(charttime) AS lab_time, count(*) AS lab_rows,
               jsonb_agg(labevent_id ORDER BY labevent_id) AS lab_ids,
               count(*) FILTER (WHERE valuenum > 0
                 AND valuenum::text NOT IN ('NaN','Infinity','-Infinity')
                 AND upper(trim(valueuom)) IN ('MEQ/L','MMOL/L')
                 AND storetime >= charttime AND storetime <= e.anchor_time) AS valid_rows,
               count(DISTINCT valuenum) AS distinct_values,
               min(valuenum) AS lab_value, max(storetime) AS latest_storetime
        FROM mimiciv_hosp.labevents l
        WHERE l.subject_id = e.subject_id AND l.hadm_id = e.hadm_id
          AND l.itemid = __LAB_ITEM_ID__ AND l.charttime = pre_time.lab_time AND l.storetime <= e.anchor_time
        OFFSET 0
    ) pre
    CROSS JOIN LATERAL (
        SELECT min(charttime) AS lab_time FROM mimiciv_hosp.labevents l
        WHERE e.decision_context_exclusion IS NULL
          AND l.subject_id = e.subject_id AND l.hadm_id = e.hadm_id AND l.itemid = __LAB_ITEM_ID__
          AND l.charttime > e.outcome_after_time AND l.charttime <= e.outcome_deadline
          AND l.charttime <= e.dischtime
        OFFSET 0
    ) post_time
    CROSS JOIN LATERAL (
        SELECT min(charttime) AS lab_time, count(*) AS lab_rows,
               jsonb_agg(labevent_id ORDER BY labevent_id) AS lab_ids,
               count(*) FILTER (WHERE valuenum > 0
                 AND valuenum::text NOT IN ('NaN','Infinity','-Infinity')
                 AND upper(trim(valueuom)) IN ('MEQ/L','MMOL/L')
                 AND (storetime IS NULL OR storetime >= charttime)) AS valid_rows,
               count(DISTINCT valuenum) AS distinct_values,
               min(valuenum) AS lab_value, max(storetime) AS latest_storetime,
               count(*) FILTER (WHERE storetime IS NULL) AS missing_storetime_rows,
               count(*) FILTER (WHERE storetime < charttime) AS reversed_storetime_rows
        FROM mimiciv_hosp.labevents l
        WHERE l.subject_id = e.subject_id AND l.hadm_id = e.hadm_id
          AND l.itemid = __LAB_ITEM_ID__ AND l.charttime = post_time.lab_time
        OFFSET 0
    ) post
), classified AS MATERIALIZED (
    SELECT *,
           CASE WHEN decision_context_exclusion IS NOT NULL THEN 'not_assessed_invalid_decision_context'
                WHEN invalid_transfer_rows > 0 THEN 'invalid_transfer_evidence'
                WHEN active_transfer_rows = 0 THEN 'no_active_transfer'
                WHEN active_icu_rows > 0 THEN 'icu'
                WHEN active_transfer_rows > 1 THEN 'overlapping_transfers'
                WHEN active_named_non_icu_rows = 1 THEN 'non_icu'
                ELSE 'unknown_careunit' END AS anchor_location_class,
           CASE WHEN decision_context_exclusion IS NOT NULL THEN 'not_assessed_invalid_decision_context'
                WHEN pre_lab_rows = 0 THEN 'missing'
                WHEN pre_valid_rows <> pre_lab_rows THEN 'invalid_value_unit_or_time'
                WHEN pre_distinct_values <> 1 THEN 'conflicting_values_at_timestamp'
                ELSE 'usable' END AS pre_lab_class,
           CASE WHEN decision_context_exclusion IS NOT NULL THEN 'not_assessed_invalid_decision_context'
                WHEN post_lab_rows = 0 THEN 'missing_after_outcome_after'
                WHEN post_valid_rows <> post_lab_rows THEN 'invalid_value_unit_or_time'
                WHEN post_distinct_values <> 1 THEN 'conflicting_values_at_timestamp'
                ELSE 'usable' END AS post_lab_class
    FROM evidence
), gated AS (
    SELECT *, CASE WHEN decision_context_exclusion IS NOT NULL THEN decision_context_exclusion
                  WHEN anchor_location_class <> 'non_icu' THEN 'not_confirmed_non_icu_at_anchor'
                  WHEN post_lab_class <> 'usable' THEN 'first_post_lab_unusable'
                  ELSE NULL END AS clinical_exclusion
    FROM classified
)
SELECT 'zero_decision_context_v1'::text AS extraction_version,
       subject_id, hadm_id, opportunity_index, anchor_time, action_end,
       outcome_after_time, input_parse_problem,
       admittime, dischtime, admission_rows, subject_match_rows, outcome_deadline,
       decision_context_exclusion, __LAB_ITEM_ID__::integer AS lab_item_id,
       anchor_location_class, active_transfer_rows, active_icu_rows,
       active_named_non_icu_rows, invalid_transfer_rows,
       pre_lab_class, pre_labevent_ids, pre_lab_rows, pre_valid_rows, pre_distinct_values,
       pre_lab_time, pre_latest_storetime,
       CASE WHEN pre_lab_class = 'usable' THEN pre_lab_value END AS pre_lab_value,
       post_lab_class, post_labevent_ids, post_lab_rows, post_valid_rows, post_distinct_values,
       post_lab_time, post_latest_storetime, post_missing_storetime_rows, post_reversed_storetime_rows,
       CASE WHEN post_lab_class = 'usable' THEN post_lab_value END AS post_lab_value,
       extract(epoch FROM (post_lab_time - outcome_after_time)) / 3600.0 AS post_gap_from_outcome_after_hours,
       clinical_exclusion, clinical_exclusion IS NULL AS clinical_eligible
FROM gated ORDER BY subject_id, hadm_id, anchor_time;
