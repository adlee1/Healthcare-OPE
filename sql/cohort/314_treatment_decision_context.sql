-- PRIVATE ROW OUTPUT. Event-anchored clinical context for K / Na decisions.
-- Read only; caller validates VALUES and lab item ID, uses <=120000 ms.
-- Project D003 choice: non-ICU at anchor; pre lab in [anchor-4h,anchor]
-- when already available; FIRST post lab in (outcome_after,outcome_after+24h]
-- no later than discharge. Bad first groups are retained, never skipped.
-- K recorded administrations / zero decisions can have anchor=outcome_after;
-- observed complete Na infusions use actual start and observed end.
-- Pre-lab absence / invalidity is retained but is NOT an eligibility gate:
-- the paper's listed 15 policy features do not require this electrolyte.
-- This query does not decide actions or check other treatment exposure.
WITH requested(decision_id, subject_id, hadm_id, anchor_time, outcome_after_time, input_parse_problem) AS (
    VALUES __DECISION_KEYS__
), decisions AS MATERIALIZED (
    SELECT decision_id::text AS decision_id, subject_id::integer AS subject_id,
           hadm_id::integer AS hadm_id, anchor_time::timestamp AS anchor_time,
           outcome_after_time::timestamp AS outcome_after_time, input_parse_problem::text AS input_parse_problem
    FROM requested
), admission_evidence AS MATERIALIZED (
    SELECT e.*, a.admission_rows, a.subject_match_rows, a.admittime, a.dischtime
    FROM decisions e CROSS JOIN LATERAL (
        SELECT count(*) AS admission_rows,
               count(*) FILTER (WHERE a.subject_id = e.subject_id) AS subject_match_rows,
               min(admittime) FILTER (WHERE a.subject_id = e.subject_id) AS admittime,
               min(dischtime) FILTER (WHERE a.subject_id = e.subject_id) AS dischtime
        FROM mimiciv_hosp.admissions a WHERE a.hadm_id = e.hadm_id
    ) a
), clock_classified AS MATERIALIZED (
    SELECT *, outcome_after_time + interval '24 hours' AS outcome_deadline,
           CASE WHEN nullif(input_parse_problem,'') IS NOT NULL THEN 'invalid_input_field'
                WHEN subject_id IS NULL OR hadm_id IS NULL THEN 'missing_patient_or_admission'
                WHEN admission_rows = 0 THEN 'missing_admission'
                WHEN admission_rows <> 1 THEN 'admission_not_unique'
                WHEN subject_match_rows <> 1 THEN 'admission_subject_mismatch'
                WHEN admittime IS NULL OR dischtime IS NULL
                  OR NOT isfinite(admittime) OR NOT isfinite(dischtime) OR dischtime <= admittime
                  THEN 'invalid_admission_times'
                WHEN anchor_time IS NULL OR outcome_after_time IS NULL THEN 'missing_decision_time'
                WHEN NOT isfinite(anchor_time) OR NOT isfinite(outcome_after_time)
                  OR outcome_after_time < anchor_time THEN 'invalid_decision_times'
                WHEN anchor_time < admittime OR outcome_after_time > dischtime THEN 'decision_outside_admission'
                ELSE NULL END AS decision_context_exclusion
    FROM admission_evidence
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
    FROM clock_classified e
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
SELECT 'treatment_decision_context_v1'::text AS extraction_version,
       decision_id, subject_id, hadm_id, anchor_time, outcome_after_time, input_parse_problem,
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
FROM gated ORDER BY decision_id;
