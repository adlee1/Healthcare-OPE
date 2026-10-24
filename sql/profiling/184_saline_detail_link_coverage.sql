-- A second discovery path: prescription pharmacy_id -> emar_detail -> emar_id.
-- This tests whether component orders absent from the direct eMAR link were missed.
-- Details are scoped to matched pharmacy IDs here, not complete event products.
-- OFFSET 0 is a planning fence, not a row cap: use existing pharmacy/primary-key
-- indexes for each small candidate key set instead of hashing entire source tables.
WITH orders AS MATERIALIZED (
    SELECT pharmacy_id, count(*) AS matching_prescription_rows,
           bool_or(drug_type = 'MAIN') AS has_main, bool_or(drug_type = 'BASE') AS has_base,
           bool_or(route IN ('IV', 'IV DRIP')) AS any_iv_prescription,
           min(subject_id) AS order_subject, min(hadm_id) AS order_hadm,
           count(DISTINCT subject_id) AS order_subjects,
           count(DISTINCT hadm_id) AS order_admissions
    FROM mimiciv_hosp.prescriptions
    WHERE drug = 'Sodium Chloride 3% (Hypertonic)'
    GROUP BY pharmacy_id
)
SELECT o.has_main, o.has_base, o.any_iv_prescription,
       CASE WHEN d.emar_id IS NULL THEN 'no_detail'
            WHEN d.parent_field_ordinal IS NULL THEN 'parent' ELSE 'product' END AS detail_role,
       d.product_description, e.medication, e.event_txt,
       d.pharmacy_id = e.pharmacy_id AS same_parent_pharmacy,
       EXISTS (SELECT 1 FROM orders direct WHERE direct.pharmacy_id = e.pharmacy_id) AS covered_by_direct_link,
       count(*) AS joined_rows,
       count(d.emar_id) AS matching_detail_rows,
       count(DISTINCT o.pharmacy_id) AS prescription_pharmacy_orders,
       count(DISTINCT d.emar_id) AS detail_emar_ids,
       count(DISTINCT e.emar_id) AS linked_emar_events,
       count(DISTINCT e.subject_id) AS linked_subjects,
       count(DISTINCT e.hadm_id) AS linked_admissions,
       count(d.emar_id) FILTER (WHERE e.emar_id IS NULL) AS detail_without_parent_emar,
       count(d.emar_id) FILTER (WHERE d.subject_id IS DISTINCT FROM o.order_subject OR o.order_subjects <> 1) AS detail_order_subject_disagreement,
       count(e.emar_id) FILTER (WHERE e.subject_id IS DISTINCT FROM o.order_subject OR o.order_subjects <> 1) AS emar_order_subject_disagreement,
       count(e.emar_id) FILTER (WHERE e.hadm_id IS NULL) AS emar_missing_hadm,
       count(e.emar_id) FILTER (WHERE e.hadm_id IS NOT NULL AND
          (e.hadm_id IS DISTINCT FROM o.order_hadm OR o.order_admissions <> 1)) AS emar_nonnull_order_hadm_disagreement
FROM orders o
LEFT JOIN LATERAL (
    SELECT detail.* FROM mimiciv_hosp.emar_detail detail
    WHERE detail.pharmacy_id = o.pharmacy_id OFFSET 0
) d ON true
LEFT JOIN LATERAL (
    SELECT parent.* FROM mimiciv_hosp.emar parent
    WHERE parent.emar_id = d.emar_id OFFSET 0
) e ON true
GROUP BY o.has_main, o.has_base, o.any_iv_prescription,
         CASE WHEN d.emar_id IS NULL THEN 'no_detail'
              WHEN d.parent_field_ordinal IS NULL THEN 'parent' ELSE 'product' END,
         d.product_description, e.medication, e.event_txt, d.pharmacy_id = e.pharmacy_id,
         EXISTS (SELECT 1 FROM orders direct WHERE direct.pharmacy_id = e.pharmacy_id)
ORDER BY matching_detail_rows DESC, d.product_description, e.event_txt;
