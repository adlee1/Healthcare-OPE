-- Reproducible 1 percent SYSTEM page sample: exploratory, not a population count.
-- Broad lexical screening intentionally includes oral and non-3-percent products.
-- Medication names and event statuses only, no patient/event identifiers.
WITH sampled AS MATERIALIZED (
    SELECT medication, event_txt, hadm_id, charttime, storetime
    FROM mimiciv_hosp.emar TABLESAMPLE SYSTEM (1) REPEATABLE (20261011)
), candidate AS (
    SELECT * FROM sampled
    WHERE lower(medication) LIKE '%potassium%'
       OR lower(medication) LIKE '%kcl%'
       OR lower(medication) LIKE '%sodium chloride%'
       OR lower(medication) LIKE '%hypertonic%'
       OR lower(medication) LIKE '%saline%'
       OR lower(medication) LIKE '%nacl%'
)
SELECT medication, event_txt, count(*) AS sampled_rows,
       count(*) FILTER (WHERE hadm_id IS NULL) AS missing_admission,
       count(*) FILTER (WHERE charttime IS NULL) AS missing_charttime,
       count(*) FILTER (WHERE storetime IS NULL) AS missing_storetime,
       count(*) FILTER (WHERE storetime < charttime) AS storetime_before_charttime,
       (SELECT count(*) FROM sampled) AS total_sampled_rows,
       1.0 AS system_sample_percent, 20261011 AS sample_seed
FROM candidate
GROUP BY medication, event_txt
ORDER BY sampled_rows DESC, medication, event_txt;
