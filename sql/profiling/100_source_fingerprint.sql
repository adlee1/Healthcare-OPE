-- Exact counts of small source relations only. This is a consistency fingerprint,
-- not independent proof of the MIMIC release, and not an APRIL cohort count.
SELECT 'mimiciv_hosp.patients' AS relation_name, count(*) AS exact_rows FROM mimiciv_hosp.patients
UNION ALL
SELECT 'mimiciv_hosp.admissions', count(*) FROM mimiciv_hosp.admissions
UNION ALL
SELECT 'mimiciv_icu.icustays', count(*) FROM mimiciv_icu.icustays
UNION ALL
SELECT 'mimiciv_hosp.d_labitems', count(*) FROM mimiciv_hosp.d_labitems
UNION ALL
SELECT 'mimiciv_icu.d_items', count(*) FROM mimiciv_icu.d_items;
