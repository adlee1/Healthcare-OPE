-- OMR is date-level, not a treatment-relative four-hour measurement table.
-- A reproducible page sample can identify available names, not prove absence.
WITH sampled AS MATERIALIZED (
    SELECT result_name, chartdate, result_value
    FROM mimiciv_hosp.omr TABLESAMPLE SYSTEM (1) REPEATABLE (20261011)
)
SELECT result_name, count(*) AS sampled_rows,
       count(*) FILTER (WHERE chartdate IS NULL) AS missing_date,
       count(*) FILTER (WHERE nullif(trim(result_value), '') IS NULL) AS missing_value,
       (SELECT count(*) FROM sampled) AS total_sampled_rows,
       1.0 AS system_sample_percent, 20261011 AS sample_seed
FROM sampled
GROUP BY result_name
ORDER BY sampled_rows DESC, result_name;
