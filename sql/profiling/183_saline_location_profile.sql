-- Location audit of candidate eMAR records, not final non-ICU eligibility.
-- Exact careunit vocabulary reviewed from query160, including CCU (not ICU substring).
-- Half-open [intime,outtime); discharge records are not active-location intervals.
-- Orders are not substituted for missing eMAR hadm_id; no inferred cross-admission join.
WITH icu_units(careunit) AS (
    VALUES ('Cardiac Vascular Intensive Care Unit (CVICU)'),
           ('Coronary Care Unit (CCU)'), ('Intensive Care Unit (ICU)'),
           ('Medical Intensive Care Unit (MICU)'),
           ('Medical/Surgical Intensive Care Unit (MICU/SICU)'),
           ('Neuro Surgical Intensive Care Unit (Neuro SICU)'),
           ('Surgical Intensive Care Unit (SICU)'), ('Trauma SICU (TSICU)')
), orders AS MATERIALIZED (
    SELECT pharmacy_id, min(subject_id) AS order_subject_id, min(hadm_id) AS order_hadm_id,
           count(DISTINCT subject_id) AS order_subjects, count(DISTINCT hadm_id) AS order_admissions
    FROM mimiciv_hosp.prescriptions
    WHERE drug = 'Sodium Chloride 3% (Hypertonic)'
    GROUP BY pharmacy_id
), events AS MATERIALIZED (
    SELECT e.*,
           e.subject_id IS DISTINCT FROM o.order_subject_id OR o.order_subjects <> 1 AS order_subject_disagreement,
           e.hadm_id IS DISTINCT FROM o.order_hadm_id OR o.order_admissions <> 1 AS order_admission_disagreement
    FROM orders o JOIN mimiciv_hosp.emar e ON e.pharmacy_id = o.pharmacy_id
), target_admissions AS MATERIALIZED (
    SELECT DISTINCT subject_id, hadm_id FROM events WHERE hadm_id IS NOT NULL
), icu_evidence AS MATERIALIZED (
    SELECT i.* FROM mimiciv_icu.icustays i
    JOIN target_admissions a ON a.hadm_id = i.hadm_id AND a.subject_id = i.subject_id
), located AS (
    SELECT e.*, x.active_intervals, x.active_icu_intervals,
           x.active_named_non_icu_intervals, x.active_unknown_intervals,
           x.invalid_intervals, x.admission_has_icu_transfer,
           EXISTS (SELECT 1 FROM icu_evidence i WHERE i.hadm_id = e.hadm_id
                   AND i.subject_id = e.subject_id) AS admission_has_icustay,
           EXISTS (SELECT 1 FROM icu_evidence i WHERE i.hadm_id = e.hadm_id
                   AND i.subject_id = e.subject_id
                   AND e.charttime >= i.intime AND e.charttime < i.outtime) AS active_icustay
    FROM events e
    CROSS JOIN LATERAL (
        SELECT count(*) FILTER (WHERE e.charttime >= t.intime AND e.charttime < t.outtime) AS active_intervals,
               count(*) FILTER (WHERE e.charttime >= t.intime AND e.charttime < t.outtime
                                 AND u.careunit IS NOT NULL) AS active_icu_intervals,
               count(*) FILTER (WHERE e.charttime >= t.intime AND e.charttime < t.outtime
                                 AND u.careunit IS NULL AND nullif(trim(t.careunit), '') IS NOT NULL
                                 AND t.careunit <> 'UNKNOWN') AS active_named_non_icu_intervals,
               count(*) FILTER (WHERE e.charttime >= t.intime AND e.charttime < t.outtime
                                 AND (nullif(trim(t.careunit), '') IS NULL OR t.careunit = 'UNKNOWN')) AS active_unknown_intervals,
               count(*) FILTER (WHERE t.intime IS NULL OR t.outtime IS NULL OR t.outtime <= t.intime) AS invalid_intervals,
               coalesce(bool_or(u.careunit IS NOT NULL), false) AS admission_has_icu_transfer
        FROM mimiciv_hosp.transfers t LEFT JOIN icu_units u ON u.careunit = t.careunit
        WHERE t.hadm_id = e.hadm_id AND t.subject_id = e.subject_id AND t.eventtype <> 'discharge'
    ) x
)
SELECT event_txt, hadm_id IS NULL AS missing_hadm,
       order_subject_disagreement, order_admission_disagreement,
       active_intervals, active_icu_intervals, active_named_non_icu_intervals,
       active_unknown_intervals, invalid_intervals > 0 AS admission_has_invalid_intervals,
       admission_has_icu_transfer, admission_has_icustay, active_icustay,
       count(*) AS candidate_emar_rows, count(DISTINCT subject_id) AS subjects,
       count(DISTINCT hadm_id) AS admissions
FROM located
GROUP BY event_txt, hadm_id IS NULL, order_subject_disagreement, order_admission_disagreement,
         active_intervals, active_icu_intervals,
         active_named_non_icu_intervals, active_unknown_intervals, invalid_intervals > 0,
         admission_has_icu_transfer, admission_has_icustay, active_icustay
ORDER BY candidate_emar_rows DESC, event_txt;
