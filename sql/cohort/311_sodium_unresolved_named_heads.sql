-- PRIVATE blocker rows; same 53-column interface as 306, no dose reconstruction.
-- Query 310 found three additional heads with this explicit nonrespiratory name
-- and no route evidence. Missing route is not evidence of absent IV exposure.
-- Read only; <=120000 ms. This is a separate extraction/snapshot from 306/310.
-- Exclude 306's exact-prescription pharmacy scope to prevent source duplication.
-- No detail/order identity or route is newly asserted: unassessed fields are NULL.
-- Every retained head normalizes as relevant=true, supported=false, dose/rate=None.
-- A stop in this source cannot certify treatment completion or resolve exposure.
-- Window counts below describe ONLY this retained blocker scope, not full streams.
WITH exact_orders AS MATERIALIZED (
    SELECT DISTINCT pharmacy_id FROM mimiciv_hosp.prescriptions
    WHERE drug = 'Sodium Chloride 3% (Hypertonic)' AND pharmacy_id IS NOT NULL
), heads AS MATERIALIZED (
    SELECT e.emar_id, e.emar_seq, e.subject_id, e.hadm_id, e.pharmacy_id,
           e.charttime, e.storetime, e.event_txt
    FROM mimiciv_hosp.emar e
    WHERE e.medication = 'sodium chloride 3 %'
      AND NOT EXISTS (SELECT 1 FROM exact_orders o WHERE o.pharmacy_id = e.pharmacy_id)
)
SELECT 'sodium_unresolved_named_heads_v1'::text AS definition_version,
       subject_id, hadm_id, pharmacy_id, emar_id, emar_seq,
       event_txt AS administration_status, charttime AS anchor_time, storetime AS emar_storetime,
       NULL::integer AS source_order_subject_id, NULL::integer AS source_order_hadm_id,
       NULL::bigint AS order_subjects, NULL::bigint AS order_admissions, NULL::bigint AS order_missing_ids,
       NULL::boolean AS identity_ok, NULL::boolean AS identity_bad,
       'explicit_3pct_head_unresolved_route'::text AS head_source,
       false AS known_other_head, NULL::boolean AS head_identity_bad,
       'unresolved_route_blocker_only'::text AS route_class, true AS route_bad,
       NULL::bigint AS order_iv_route_rows, NULL::bigint AS order_other_route_rows,
       NULL::bigint AS detail_iv_route_rows, NULL::bigint AS detail_other_route_rows,
       NULL::boolean AS route_conflict,
       NULL::bigint AS parent_rows, NULL::bigint AS product_rows, NULL::bigint AS bad_detail_identity_rows,
       'not_assessed_blocker_only'::text AS parent_rate_class, NULL::text AS parent_rate_unit,
       NULL::numeric AS parent_rate_ml_per_hour,
       count(*) FILTER (WHERE charttime IS NULL) OVER
         (PARTITION BY subject_id,hadm_id,coalesce(pharmacy_id::text,'unlinked:' || emar_id))
         AS stream_missing_time_heads,
       NULL::bigint AS pharmacy_identity_problem_heads,
       count(*) OVER
         (PARTITION BY subject_id,hadm_id,coalesce(pharmacy_id::text,'unlinked:' || emar_id),charttime)
         AS same_time_head_count,
       charttime IS NULL AS missing_charttime, storetime IS NULL AS missing_storetime,
       coalesce(storetime < charttime,false) AS reversed_storetime,
       NULL::boolean AS complete_yes, NULL::bigint AS incomplete_dose_yes_rows,
       NULL::text AS product_dose_unit_classes, NULL::bigint AS product_dose_present_rows,
       NULL::bigint AS product_dose_numeric_rows, NULL::bigint AS product_positive_known_unit_rows,
       NULL::bigint AS product_nonpositive_rows, NULL::bigint AS product_unparsed_rows,
       NULL::bigint AS product_positive_unknown_unit_rows,
       NULL::numeric AS product_volume_sum_ml_diagnostic,
       'unresolved_named_head_blocker_only'::text AS administered_volume_class,
       NULL::numeric AS single_administered_volume_ml, NULL::numeric AS single_administered_sodium_meq,
       'explicit_nonrespiratory_head_outside_exact_rx_scope'::text AS source_scope,
       false AS zero_action_assigned
FROM heads ORDER BY subject_id,hadm_id,pharmacy_id,charttime NULLS LAST,emar_id;
