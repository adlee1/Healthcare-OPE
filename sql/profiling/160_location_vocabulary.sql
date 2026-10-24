-- Exact vocabulary/counts over transfers, a modest source table. This is NOT
-- a patient count or a frozen non-ICU classification.
SELECT eventtype, careunit, count(*) AS transfer_rows,
       count(*) FILTER (WHERE hadm_id IS NULL) AS missing_admission,
       count(*) FILTER (WHERE intime IS NULL) AS missing_intime,
       count(*) FILTER (WHERE outtime IS NULL) AS missing_outtime,
       count(*) FILTER (WHERE outtime < intime) AS reversed_intervals
FROM mimiciv_hosp.transfers
GROUP BY eventtype, careunit
ORDER BY eventtype, careunit;
