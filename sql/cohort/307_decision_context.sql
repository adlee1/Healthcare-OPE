-- Ten non-medication context features for declared common decision times.
-- Input: validated VALUES tuples the decision-key VALUES input with the four typed columns.
-- D004 project choices: latest available dynamic time, conflicting tied values
-- => NULL; no future-value fallback. Static OMR history has no year limit, but
-- chartdate must be STRICTLY BEFORE the decision date; OMR has no storetime.
-- ICU chartevents can supply recent history (including a recent ICU discharge),
-- not general ward coverage. Never read all-stay derived aggregates.
-- Vital IDs independently checked against MIT-LCP's published vitalsign.sql:
-- https://github.com/MIT-LCP/mimic-code/blob/main/mimic-iv/concepts/measurement/vitalsign.sql
-- Runtime d_items must also match label, unit and chartevents source.
-- SBP/DBP use non-invasive 220179/220180 only, matching the local partial index.
-- Creatinine uses the verified Blood/Chemistry 50912 primary; 52546 omitted.
WITH input_keys(event_id, subject_id, hadm_id, decision_time) AS (
    VALUES __DECISION_KEYS__
), decisions AS MATERIALIZED (
    SELECT event_id, min(subject_id)::integer AS subject_id, min(hadm_id)::integer AS hadm_id,
           min(decision_time)::timestamp AS decision_time,
           count(*) AS input_rows,
           count(DISTINCT (subject_id, hadm_id, decision_time)) = 1
             AND bool_and(subject_id IS NOT NULL AND hadm_id IS NOT NULL AND decision_time IS NOT NULL)
             AND event_id IS NOT NULL AND nullif(trim(event_id), '') IS NOT NULL AS decision_key_valid
    FROM input_keys GROUP BY event_id
), admission_bounds AS MATERIALIZED (
    SELECT subject_id, hadm_id, min(decision_time) - interval '4 hours' AS first_time,
           max(decision_time) AS last_time
    FROM decisions WHERE decision_key_valid GROUP BY subject_id, hadm_id
), subject_bounds AS MATERIALIZED (
    SELECT subject_id, max(decision_time)::date AS last_date
    FROM decisions WHERE decision_key_valid GROUP BY subject_id
), patient_rows AS MATERIALIZED (
    SELECT p.subject_id, p.anchor_age, p.anchor_year, p.gender
    FROM subject_bounds b CROSS JOIN LATERAL (
        SELECT subject_id, anchor_age, anchor_year, gender FROM mimiciv_hosp.patients p
        WHERE p.subject_id = b.subject_id OFFSET 0
    ) p
), patient_summary AS MATERIALIZED (
    SELECT subject_id, count(*) AS patient_rows, min(anchor_age) AS anchor_age,
           min(anchor_year) AS anchor_year, min(gender) AS gender
    FROM patient_rows GROUP BY subject_id
), omr_rows AS MATERIALIZED (
    SELECT o.subject_id, o.chartdate, o.seq_num,
           CASE o.result_name WHEN 'Weight (Lbs)' THEN 'weight_kg' ELSE 'height_cm' END AS feature,
           CASE WHEN length(trim(o.result_value)) BETWEEN 1 AND 64
                      AND trim(o.result_value) ~ '^[0-9]+([.][0-9]+)?$'
                THEN trim(o.result_value)::numeric *
                     CASE o.result_name WHEN 'Weight (Lbs)' THEN 0.45359237 ELSE 2.54 END END AS value
    -- OMR has no subject index locally: one ordinary join permits one scan.
    FROM subject_bounds b JOIN mimiciv_hosp.omr o ON o.subject_id = b.subject_id
    WHERE o.chartdate < b.last_date
      AND o.result_name IN ('Weight (Lbs)', 'Height (Inches)')
), static_selections AS MATERIALIZED (
    SELECT d.event_id, d.subject_id, f.feature, chosen.chartdate, chosen.seq_num
    FROM decisions d CROSS JOIN (VALUES ('weight_kg'), ('height_cm')) AS f(feature)
    LEFT JOIN LATERAL (
        SELECT o.chartdate, o.seq_num FROM omr_rows o
        WHERE d.decision_key_valid AND o.subject_id = d.subject_id AND o.feature = f.feature
          AND o.chartdate < d.decision_time::date
        ORDER BY o.chartdate DESC, o.seq_num DESC NULLS LAST LIMIT 1
    ) chosen ON true
), static_groups AS MATERIALIZED (
    SELECT s.event_id, s.feature, s.chartdate, s.seq_num,
           count(o.subject_id) AS source_rows,
           count(o.subject_id) FILTER (WHERE o.value > 0) AS valid_rows,
           count(DISTINCT o.value) AS distinct_values, min(o.value) AS value
    FROM static_selections s LEFT JOIN omr_rows o
      ON o.subject_id = s.subject_id AND o.feature = s.feature AND o.chartdate = s.chartdate
     AND o.seq_num IS NOT DISTINCT FROM s.seq_num
    GROUP BY s.event_id, s.feature, s.chartdate, s.seq_num
), static_values AS MATERIALIZED (
    SELECT *, CASE WHEN source_rows = 0 THEN 'missing_prior_explicit_unit_history'
                   WHEN valid_rows <> source_rows THEN 'invalid_latest_value'
                   WHEN distinct_values <> 1 THEN 'conflicting_latest_values'
                   ELSE 'available_date_only_no_storetime' END AS value_status
    FROM static_groups
), static_wide AS MATERIALIZED (
    SELECT event_id,
           max(value) FILTER (WHERE feature = 'weight_kg' AND value_status = 'available_date_only_no_storetime') AS weight_kg,
           max(value) FILTER (WHERE feature = 'height_cm' AND value_status = 'available_date_only_no_storetime') AS height_cm,
           jsonb_object_agg(feature, jsonb_build_object('status', value_status,
             'source', 'hosp.omr', 'chartdate', chartdate, 'seq_num', seq_num,
             'source_rows', source_rows, 'available_time', NULL)) AS static_evidence
    FROM static_values GROUP BY event_id
), vital_spec(feature, itemid, label_pattern, expected_unit) AS (
    VALUES ('heart_rate', 220045, 'heart rate', 'bpm'),
           ('respiratory_rate', 220210, 'respiratory rate', 'insp/min'),
           ('respiratory_rate', 224690, 'respiratory rate', 'insp/min'),
           ('spo2', 220277, 'pulseox|spo2|o2 saturation', '%'),
           ('sbp', 220179, 'non invasive blood pressure.*systolic', 'mmHg'),
           ('dbp', 220180, 'non invasive blood pressure.*diastolic', 'mmHg')
), verified_vitals AS MATERIALIZED (
    SELECT DISTINCT s.feature, s.itemid FROM vital_spec s JOIN mimiciv_icu.d_items d USING (itemid)
    WHERE d.linksto = 'chartevents' AND d.label ~* s.label_pattern
      AND upper(trim(d.unitname)) = upper(s.expected_unit)
), verified_creatinine AS MATERIALIZED (
    SELECT DISTINCT itemid FROM mimiciv_hosp.d_labitems
    WHERE itemid = 50912 AND lower(trim(label)) = 'creatinine'
      AND lower(trim(fluid)) = 'blood' AND lower(trim(category)) = 'chemistry'
), chart_rows AS MATERIALIZED (
    SELECT b.subject_id, b.hadm_id, v.feature, c.itemid, c.stay_id,
           c.charttime, c.storetime, c.valuenum, upper(regexp_replace(trim(c.valueuom), '[[:space:]]+', '', 'g')) AS unit
    FROM admission_bounds b CROSS JOIN LATERAL (
        SELECT itemid, stay_id, charttime, storetime, valuenum, valueuom
        FROM mimiciv_icu.chartevents c
        WHERE c.subject_id = b.subject_id AND c.hadm_id = b.hadm_id
          AND c.charttime >= b.first_time AND c.charttime <= b.last_time
          AND c.storetime >= c.charttime AND c.storetime <= b.last_time
          AND c.itemid IN (220045, 220179, 220180, 220210, 220277, 224690)
        OFFSET 0
    ) c JOIN verified_vitals v USING (itemid)
), laboratory_rows AS MATERIALIZED (
    SELECT b.subject_id, b.hadm_id, l.labevent_id, l.itemid, l.charttime, l.storetime,
           l.valuenum, upper(regexp_replace(trim(l.valueuom), '[[:space:]]+', '', 'g')) AS unit
    FROM admission_bounds b CROSS JOIN LATERAL (
        SELECT labevent_id, itemid, charttime, storetime, valuenum, valueuom
        FROM mimiciv_hosp.labevents l
        WHERE l.subject_id = b.subject_id AND l.hadm_id = b.hadm_id AND l.itemid = 50912
          AND l.charttime >= b.first_time AND l.charttime <= b.last_time
          AND l.storetime >= l.charttime AND l.storetime <= b.last_time OFFSET 0
    ) l JOIN verified_creatinine v USING (itemid)
), dynamic_rows AS MATERIALIZED (
    SELECT subject_id, hadm_id, feature, itemid, stay_id, NULL::bigint AS labevent_id,
           charttime, storetime,
           CASE WHEN valuenum > 0 AND valuenum::text NOT IN ('NaN', 'Infinity', '-Infinity')
                      AND CASE feature
                        WHEN 'heart_rate' THEN unit IN ('BPM', 'BEATS/MIN', 'BEATS/MINUTE')
                        WHEN 'respiratory_rate' THEN unit IN ('INSP/MIN', 'BREATHS/MIN', 'BREATHS/MINUTE', 'BPM')
                        WHEN 'spo2' THEN unit IN ('%', 'PERCENT') AND valuenum <= 100
                        ELSE unit = 'MMHG' END
                THEN valuenum::numeric END AS value
    FROM chart_rows
    UNION ALL
    SELECT subject_id, hadm_id, 'creatinine', itemid, NULL::integer, labevent_id,
           charttime, storetime,
           CASE WHEN valuenum > 0 AND valuenum::text NOT IN ('NaN', 'Infinity', '-Infinity')
                      AND unit = 'MG/DL' THEN valuenum::numeric END
    FROM laboratory_rows
), dynamic_selections AS MATERIALIZED (
    -- One ordinary join allows hashing by patient/admission/feature instead
    -- of rescanning the materialized measurements for every event x feature.
    SELECT d.event_id, d.subject_id, d.hadm_id, d.decision_time, f.feature,
           max(r.charttime) AS charttime
    FROM decisions d CROSS JOIN (VALUES ('heart_rate'), ('respiratory_rate'), ('spo2'),
                                       ('sbp'), ('dbp'), ('creatinine')) AS f(feature)
    LEFT JOIN dynamic_rows r
      ON d.decision_key_valid AND r.subject_id = d.subject_id AND r.hadm_id = d.hadm_id
     AND r.feature = f.feature AND r.charttime >= d.decision_time - interval '4 hours'
     AND r.charttime <= d.decision_time AND r.storetime <= d.decision_time
    GROUP BY d.event_id, d.subject_id, d.hadm_id, d.decision_time, f.feature
), dynamic_groups AS MATERIALIZED (
    SELECT s.event_id, s.feature, s.charttime, max(r.storetime) AS latest_storetime,
           count(r.subject_id) AS source_rows, count(r.value) AS valid_rows,
           count(DISTINCT r.value) AS distinct_values, min(r.value) AS value,
           jsonb_agg(DISTINCT r.itemid) FILTER (WHERE r.itemid IS NOT NULL) AS itemids,
           jsonb_agg(DISTINCT r.stay_id) FILTER (WHERE r.stay_id IS NOT NULL) AS stay_ids,
           jsonb_agg(DISTINCT r.labevent_id) FILTER (WHERE r.labevent_id IS NOT NULL) AS labevent_ids
    FROM dynamic_selections s LEFT JOIN dynamic_rows r
      ON r.subject_id = s.subject_id AND r.hadm_id = s.hadm_id AND r.feature = s.feature
     AND r.charttime = s.charttime AND r.storetime <= s.decision_time
    GROUP BY s.event_id, s.feature, s.charttime
), dynamic_values AS MATERIALIZED (
    SELECT *, CASE WHEN source_rows = 0 THEN 'no_available_measurement_in_window'
                   WHEN valid_rows <> source_rows THEN 'invalid_latest_value_or_unit'
                   WHEN distinct_values <> 1 THEN 'conflicting_latest_values'
                   ELSE 'available' END AS value_status
    FROM dynamic_groups
), dynamic_wide AS MATERIALIZED (
    SELECT event_id,
           max(value) FILTER (WHERE feature = 'heart_rate' AND value_status = 'available') AS heart_rate,
           max(value) FILTER (WHERE feature = 'respiratory_rate' AND value_status = 'available') AS respiratory_rate,
           max(value) FILTER (WHERE feature = 'spo2' AND value_status = 'available') AS spo2,
           max(value) FILTER (WHERE feature = 'sbp' AND value_status = 'available') AS sbp,
           max(value) FILTER (WHERE feature = 'dbp' AND value_status = 'available') AS dbp,
           max(value) FILTER (WHERE feature = 'creatinine' AND value_status = 'available') AS creatinine,
           jsonb_object_agg(feature, jsonb_build_object('status', value_status,
             'source', CASE WHEN feature = 'creatinine' THEN 'hosp.labevents' ELSE 'icu.chartevents' END,
             'charttime', charttime, 'latest_storetime', latest_storetime,
             'source_rows', source_rows, 'itemids', itemids, 'stay_ids', stay_ids,
             'labevent_ids', labevent_ids)) AS dynamic_evidence
    FROM dynamic_values GROUP BY event_id
), dictionary_evidence AS (
    SELECT (SELECT jsonb_agg(itemid ORDER BY itemid) FROM verified_vitals) AS verified_vital_itemids,
           (SELECT count(*) = 6 FROM verified_vitals) AS all_vital_ids_verified,
           EXISTS (SELECT 1 FROM verified_creatinine) AS creatinine_id_verified
)
SELECT 'decision_context_v1'::text AS extraction_version,
       d.event_id, d.subject_id, d.hadm_id, d.decision_time, d.decision_key_valid,
       CASE WHEN d.decision_key_valid AND p.patient_rows = 1
              AND p.anchor_age IS NOT NULL AND p.anchor_year IS NOT NULL
            THEN p.anchor_age + extract(year FROM d.decision_time)::integer - p.anchor_year END AS age,
       CASE WHEN d.decision_key_valid AND p.patient_rows = 1 THEN p.gender END AS gender,
       CASE WHEN p.patient_rows = 1 THEN p.anchor_age >= 91 END AS age_is_deidentified_topcode,
       coalesce(p.patient_rows, 0) AS patient_source_rows,
       s.weight_kg, s.height_cm, v.heart_rate, v.respiratory_rate, v.spo2, v.sbp, v.dbp, v.creatinine,
       s.static_evidence, v.dynamic_evidence,
       x.verified_vital_itemids, x.all_vital_ids_verified, x.creatinine_id_verified,
       'icu_recent_history_nibp_only_not_complete_ward_coverage'::text AS vital_source_scope,
       '50912_only_52546_not_included'::text AS creatinine_source_scope
FROM decisions d LEFT JOIN patient_summary p ON p.subject_id = d.subject_id
LEFT JOIN static_wide s ON s.event_id = d.event_id
LEFT JOIN dynamic_wide v ON v.event_id = d.event_id
CROSS JOIN dictionary_evidence x
ORDER BY d.event_id;
