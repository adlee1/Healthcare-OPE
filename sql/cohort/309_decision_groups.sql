-- Retrospective cohort labels only; NEVER pre-treatment predictor features.
-- Input: the decision-key VALUES input = (event_id, subject_id, hadm_id, decision_time).
-- Diagnosis codes belong to the same subject AND admission. They have no
-- reliable pre-decision availability time, so no temporal feature claim is made.
-- Project rule retrospective-diagnosis-groups-v1; APRIL does not disclose ICDs.
-- Renal disease: MIT-LCP Charlson renal_disease algorithm, inspected 2026-10-20:
-- https://raw.githubusercontent.com/MIT-LCP/mimic-code/main/mimic-iv/concepts/comorbidity/charlson.sql
-- Cirrhosis is an explicit-code subset, not the Charlson mild-liver category:
-- ICD-9-CM exact 5712/5715/5716, AHRQ v4.3 PDI18 p2 (code definitions only):
-- https://qualityindicators.ahrq.gov/Downloads/Modules/PDI/V43/TechSpecs/PDI%2018%20Urinary%20Tract%20Infection%20Admission%20Rate.pdf
-- ICD-10-CM prefixes K703/K743/K744/K745/K746; CMS v37 definitions:
-- https://www.cms.gov/icd10m/version37-fullcode-cms/fullcode_cms/P0177.html
-- Pure fibrosis, hepatitis, liver failure, and portal hypertension alone do
-- not establish this conservative cirrhosis label. No diagnosis means NULL,
-- not false. An uninterpretable diagnosis cannot establish a negative label.
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
), admission_keys AS MATERIALIZED (
    SELECT DISTINCT subject_id, hadm_id
    FROM decisions WHERE decision_key_valid
), diagnosis_source AS MATERIALIZED (
    SELECT k.subject_id, k.hadm_id, d.icd_version,
           upper(replace(trim(d.icd_code), '.', '')) AS code
    FROM admission_keys k CROSS JOIN LATERAL (
        SELECT icd_version, icd_code
        FROM mimiciv_hosp.diagnoses_icd d
        WHERE d.subject_id = k.subject_id AND d.hadm_id = k.hadm_id
        OFFSET 0
    ) d
), diagnosis_matches AS MATERIALIZED (
    SELECT *,
           CASE WHEN icd_version = 9 THEN
                  code ~ '^[0-9EV][0-9]{2,4}$'
                WHEN icd_version = 10 THEN
                  code ~ '^[A-Z][0-9][0-9A-Z]{1,5}$'
                ELSE false END AS interpretable,
           CASE
             WHEN icd_version = 9 THEN
               left(code, 3) IN ('582', '585', '586', 'V56')
               OR left(code, 4) IN ('5880', 'V420', 'V451')
               OR left(code, 4) BETWEEN '5830' AND '5837'
               OR left(code, 5) IN (
                   '40301', '40311', '40391', '40402', '40403',
                   '40412', '40413', '40492', '40493')
             WHEN icd_version = 10 THEN
               left(code, 3) IN ('N18', 'N19')
               OR left(code, 4) IN (
                   'I120', 'I131', 'N032', 'N033', 'N034', 'N035', 'N036', 'N037',
                   'N052', 'N053', 'N054', 'N055', 'N056', 'N057', 'N250',
                   'Z490', 'Z491', 'Z492', 'Z940', 'Z992')
             ELSE false
           END AS renal_match,
           CASE
             WHEN icd_version = 9 THEN code IN ('5712', '5715', '5716')
             WHEN icd_version = 10 THEN left(code, 4) IN ('K703', 'K743', 'K744', 'K745', 'K746')
             ELSE false
           END AS cirrhosis_match
    FROM diagnosis_source
), diagnosis_summary AS MATERIALIZED (
    SELECT subject_id, hadm_id, count(*) AS diagnosis_rows,
           count(*) FILTER (WHERE interpretable IS NOT TRUE) AS uninterpretable_diagnosis_rows,
           bool_or(renal_match AND interpretable) AS renal_positive,
           bool_or(cirrhosis_match AND interpretable) AS cirrhosis_positive
    FROM diagnosis_matches GROUP BY subject_id, hadm_id
)
SELECT 'retrospective-diagnosis-groups-v1'::text AS grouping_rules_version,
       d.event_id, d.subject_id, d.hadm_id, d.decision_time,
       d.decision_key_valid, d.input_rows,
       CASE WHEN NOT d.decision_key_valid OR coalesce(s.diagnosis_rows, 0) = 0 THEN NULL
            WHEN s.renal_positive THEN true
            WHEN s.uninterpretable_diagnosis_rows > 0 THEN NULL
            ELSE false END AS renal_disease,
       CASE WHEN NOT d.decision_key_valid OR coalesce(s.diagnosis_rows, 0) = 0 THEN NULL
            WHEN s.cirrhosis_positive THEN true
            WHEN s.uninterpretable_diagnosis_rows > 0 THEN NULL
            ELSE false END AS cirrhosis,
       CASE WHEN d.decision_key_valid THEN coalesce(s.diagnosis_rows, 0)
            ELSE 0 END AS diagnosis_rows,
       CASE WHEN d.decision_key_valid THEN coalesce(s.uninterpretable_diagnosis_rows, 0)
            ELSE 0 END AS uninterpretable_diagnosis_rows,
       true AS diagnosis_labels_are_retrospective,
       false AS diagnosis_labels_are_predictor_features
FROM decisions d
LEFT JOIN diagnosis_summary s
  ON s.subject_id = d.subject_id AND s.hadm_id = d.hadm_id
ORDER BY d.event_id;
