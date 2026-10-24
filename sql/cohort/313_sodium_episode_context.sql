-- PRIVATE ROW OUTPUT. Independent positive-episode clinical-context diagnostic.
-- Read only; caller supplies validated episode VALUES and uses <=120000 ms.
-- Preserve every request, including missing identity, admission, or episode time.
-- Non-ICU is assessed at actual start, using the existing 305 transfer rule.
-- Pre: latest available Na in [start-4h,start]. Post: FIRST Na in
-- (observed end,end+24h], no later than discharge. Bad first groups are retained.
-- No zero action, dose discretization, or additional-treatment check is done.
WITH requested(episode_id, subject_id, hadm_id, start_time, end_time, input_parse_problem) AS (
    VALUES __EPISODE_KEYS__
), episodes AS MATERIALIZED (
    SELECT episode_id::text AS episode_id, subject_id::integer AS subject_id,
           hadm_id::integer AS hadm_id, start_time::timestamp AS start_time,
           end_time::timestamp AS end_time, input_parse_problem::text AS input_parse_problem
    FROM requested
), admission_evidence AS MATERIALIZED (
    SELECT e.*, a.admission_rows, a.subject_match_rows, a.admittime, a.dischtime
    FROM episodes e CROSS JOIN LATERAL (
        SELECT count(*) AS admission_rows,
               count(*) FILTER (WHERE a.subject_id = e.subject_id) AS subject_match_rows,
               min(admittime) FILTER (WHERE a.subject_id = e.subject_id) AS admittime,
               min(dischtime) FILTER (WHERE a.subject_id = e.subject_id) AS dischtime
        FROM mimiciv_hosp.admissions a WHERE a.hadm_id = e.hadm_id
    ) a
), clock_classified AS MATERIALIZED (
    SELECT *, end_time + interval '24 hours' AS outcome_deadline,
           CASE WHEN nullif(input_parse_problem,'') IS NOT NULL THEN 'invalid_input_field'
                WHEN subject_id IS NULL OR hadm_id IS NULL THEN 'missing_patient_or_admission'
                WHEN admission_rows = 0 THEN 'missing_admission'
                WHEN admission_rows <> 1 THEN 'admission_not_unique'
                WHEN subject_match_rows <> 1 THEN 'admission_subject_mismatch'
                WHEN admittime IS NULL OR dischtime IS NULL
                  OR NOT isfinite(admittime) OR NOT isfinite(dischtime) OR dischtime <= admittime
                  THEN 'invalid_admission_times'
                WHEN start_time IS NULL OR end_time IS NULL THEN 'missing_episode_time'
                WHEN NOT isfinite(start_time) OR NOT isfinite(end_time)
                  OR end_time <= start_time THEN 'invalid_episode_times'
                WHEN start_time < admittime OR end_time > dischtime THEN 'episode_outside_admission'
                ELSE NULL END AS episode_context_exclusion
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
        SELECT count(*) FILTER (WHERE t.intime <= e.start_time AND e.start_time < t.outtime) AS active_transfer_rows,
               count(*) FILTER (WHERE t.intime <= e.start_time AND e.start_time < t.outtime
                 AND u.careunit IS NOT NULL) AS active_icu_rows,
               count(*) FILTER (WHERE t.intime <= e.start_time AND e.start_time < t.outtime
                 AND u.careunit IS NULL AND nullif(trim(t.careunit),'') IS NOT NULL
                 AND upper(trim(t.careunit)) <> 'UNKNOWN') AS active_named_non_icu_rows,
               count(*) FILTER (WHERE
                 (t.intime IS NULL AND (t.outtime IS NULL OR e.start_time < t.outtime))
                 OR (t.outtime IS NULL AND t.intime <= e.start_time)
                 OR (t.outtime <= t.intime AND e.start_time BETWEEN t.outtime AND t.intime))
                 AS invalid_transfer_rows
        FROM mimiciv_hosp.transfers t LEFT JOIN icu_units u ON u.careunit = t.careunit
        WHERE e.episode_context_exclusion IS NULL
          AND t.subject_id = e.subject_id AND t.hadm_id = e.hadm_id
          AND t.eventtype IS DISTINCT FROM 'discharge'
        OFFSET 0
    ) t
    CROSS JOIN LATERAL (
        SELECT max(charttime) AS lab_time FROM mimiciv_hosp.labevents l
        WHERE e.episode_context_exclusion IS NULL
          AND l.subject_id = e.subject_id AND l.hadm_id = e.hadm_id AND l.itemid = 50983
          AND l.charttime >= e.start_time - interval '4 hours'
          AND l.charttime <= e.start_time AND l.storetime <= e.start_time
        OFFSET 0
    ) pre_time
    CROSS JOIN LATERAL (
        SELECT min(charttime) AS lab_time, count(*) AS lab_rows,
               jsonb_agg(labevent_id ORDER BY labevent_id) AS lab_ids,
               count(*) FILTER (WHERE valuenum > 0
                 AND valuenum::text NOT IN ('NaN','Infinity','-Infinity')
                 AND upper(trim(valueuom)) IN ('MEQ/L','MMOL/L')
                 AND storetime >= charttime AND storetime <= e.start_time) AS valid_rows,
               count(DISTINCT valuenum) AS distinct_values,
               min(valuenum) AS lab_value, max(storetime) AS latest_storetime
        FROM mimiciv_hosp.labevents l
        WHERE l.subject_id = e.subject_id AND l.hadm_id = e.hadm_id
          AND l.itemid = 50983 AND l.charttime = pre_time.lab_time AND l.storetime <= e.start_time
        OFFSET 0
    ) pre
    CROSS JOIN LATERAL (
        SELECT min(charttime) AS lab_time FROM mimiciv_hosp.labevents l
        WHERE e.episode_context_exclusion IS NULL
          AND l.subject_id = e.subject_id AND l.hadm_id = e.hadm_id AND l.itemid = 50983
          AND l.charttime > e.end_time AND l.charttime <= e.outcome_deadline
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
          AND l.itemid = 50983 AND l.charttime = post_time.lab_time
        OFFSET 0
    ) post
), classified AS MATERIALIZED (
    SELECT *,
           CASE WHEN episode_context_exclusion IS NOT NULL THEN 'not_assessed_invalid_episode_context'
                WHEN invalid_transfer_rows > 0 THEN 'invalid_transfer_evidence'
                WHEN active_transfer_rows = 0 THEN 'no_active_transfer'
                WHEN active_icu_rows > 0 THEN 'icu'
                WHEN active_transfer_rows > 1 THEN 'overlapping_transfers'
                WHEN active_named_non_icu_rows = 1 THEN 'non_icu'
                ELSE 'unknown_careunit' END AS start_location_class,
           CASE WHEN episode_context_exclusion IS NOT NULL THEN 'not_assessed_invalid_episode_context'
                WHEN pre_lab_rows = 0 THEN 'missing'
                WHEN pre_valid_rows <> pre_lab_rows THEN 'invalid_value_unit_or_time'
                WHEN pre_distinct_values <> 1 THEN 'conflicting_values_at_timestamp'
                ELSE 'usable' END AS pre_lab_class,
           CASE WHEN episode_context_exclusion IS NOT NULL THEN 'not_assessed_invalid_episode_context'
                WHEN post_lab_rows = 0 THEN 'missing_after_observed_end'
                WHEN post_valid_rows <> post_lab_rows THEN 'invalid_value_unit_or_time'
                WHEN post_distinct_values <> 1 THEN 'conflicting_values_at_timestamp'
                ELSE 'usable' END AS post_lab_class
    FROM evidence
), gated AS (
    SELECT *, CASE WHEN episode_context_exclusion IS NOT NULL THEN episode_context_exclusion
                  WHEN start_location_class <> 'non_icu' THEN 'not_confirmed_non_icu_at_start'
                  WHEN pre_lab_class <> 'usable' THEN 'pre_lab_unusable'
                  WHEN post_lab_class <> 'usable' THEN 'first_post_lab_unusable'
                  ELSE NULL END AS clinical_exclusion
    FROM classified
)
SELECT 'sodium_episode_context_v1'::text AS extraction_version,
       episode_id, subject_id, hadm_id, start_time, end_time, input_parse_problem,
       admittime, dischtime, admission_rows, subject_match_rows, outcome_deadline,
       episode_context_exclusion, 50983::integer AS lab_item_id,
       start_location_class, active_transfer_rows, active_icu_rows,
       active_named_non_icu_rows, invalid_transfer_rows,
       pre_lab_class, pre_labevent_ids, pre_lab_rows, pre_valid_rows, pre_distinct_values,
       pre_lab_time, pre_latest_storetime,
       CASE WHEN pre_lab_class = 'usable' THEN pre_lab_value END AS pre_lab_value,
       post_lab_class, post_labevent_ids, post_lab_rows, post_valid_rows, post_distinct_values,
       post_lab_time, post_latest_storetime, post_missing_storetime_rows, post_reversed_storetime_rows,
       CASE WHEN post_lab_class = 'usable' THEN post_lab_value END AS post_lab_value,
       extract(epoch FROM (post_lab_time - end_time)) / 3600.0 AS post_gap_from_observed_end_hours,
       clinical_exclusion, clinical_exclusion IS NULL AS clinical_eligible
FROM gated ORDER BY episode_id;
