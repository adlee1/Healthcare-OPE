-- Exact prescription name discovered in the sample. All routes retained for audit.
-- One row per prescription component; distinct pharmacy_id is a different denominator.
-- Packaging strength and ordered dose are NOT actual administered dose.
WITH candidates AS MATERIALIZED (
    SELECT subject_id, hadm_id, pharmacy_id, drug_type, prod_strength,
           route, dose_unit_rx, starttime, stoptime
    FROM mimiciv_hosp.prescriptions
    WHERE drug = 'Sodium Chloride 3% (Hypertonic)'
)
SELECT p.drug_type, p.prod_strength, p.route AS prescription_route,
       p.dose_unit_rx, ph.medication AS pharmacy_medication,
       ph.route AS pharmacy_route,
       count(*) AS prescription_rows,
       count(DISTINCT p.pharmacy_id) AS pharmacy_orders,
       count(DISTINCT p.subject_id) AS subjects,
       count(DISTINCT p.hadm_id) AS admissions,
       count(*) FILTER (WHERE ph.pharmacy_id IS NULL) AS missing_pharmacy_rows,
       count(*) FILTER (WHERE p.starttime IS NULL) AS missing_order_start,
       count(*) FILTER (WHERE p.stoptime IS NULL) AS missing_order_stop,
       count(*) FILTER (WHERE p.stoptime < p.starttime) AS reversed_order_times,
       count(*) FILTER (WHERE EXISTS (
           SELECT 1 FROM mimiciv_hosp.emar e WHERE e.pharmacy_id = p.pharmacy_id
       )) AS prescription_rows_with_emar
FROM candidates p
LEFT JOIN mimiciv_hosp.pharmacy ph ON ph.pharmacy_id = p.pharmacy_id
GROUP BY p.drug_type, p.prod_strength, p.route, p.dose_unit_rx,
         ph.medication, ph.route
ORDER BY prescription_rows DESC, p.drug_type, p.route;
