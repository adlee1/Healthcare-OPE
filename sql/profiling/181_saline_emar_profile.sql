-- This exact prescription label defines a discovery set, not the final cohort.
-- Deduplicate prescription components BEFORE linking eMAR to avoid multiplying events.
WITH orders AS MATERIALIZED (
    SELECT pharmacy_id,
           count(*) AS matching_prescription_rows,
           bool_or(route = 'IV') AS any_iv_prescription,
           bool_or(route IS NOT NULL AND route <> 'IV') AS any_non_iv_prescription,
           count(DISTINCT subject_id) AS order_subjects,
           count(DISTINCT hadm_id) AS order_admissions,
           min(subject_id) AS order_subject_id, min(hadm_id) AS order_hadm_id
    FROM mimiciv_hosp.prescriptions
    WHERE drug = 'Sodium Chloride 3% (Hypertonic)'
    GROUP BY pharmacy_id
)
SELECT e.medication, e.event_txt, o.any_iv_prescription, o.any_non_iv_prescription,
       count(*) AS emar_rows, count(DISTINCT e.emar_id) AS emar_events,
       count(DISTINCT e.subject_id) AS subjects,
       count(DISTINCT e.hadm_id) AS admissions,
       count(DISTINCT e.pharmacy_id) AS pharmacy_orders,
       count(*) FILTER (WHERE e.hadm_id IS NULL) AS missing_hadm,
       count(*) FILTER (WHERE e.charttime IS NULL) AS missing_charttime,
       count(*) FILTER (WHERE e.storetime IS NULL) AS missing_storetime,
       count(*) FILTER (WHERE e.storetime < e.charttime) AS store_before_chart,
       count(*) FILTER (WHERE e.subject_id IS DISTINCT FROM o.order_subject_id
                       OR o.order_subjects <> 1) AS order_subject_disagreement,
       count(*) FILTER (WHERE e.hadm_id IS DISTINCT FROM o.order_hadm_id
                       OR o.order_admissions <> 1) AS order_admission_disagreement,
       count(*) FILTER (WHERE o.matching_prescription_rows > 1) AS events_with_multiple_prescription_components
FROM orders o
JOIN mimiciv_hosp.emar e ON e.pharmacy_id = o.pharmacy_id
GROUP BY e.medication, e.event_txt, o.any_iv_prescription, o.any_non_iv_prescription
ORDER BY emar_rows DESC, e.medication, e.event_txt;
