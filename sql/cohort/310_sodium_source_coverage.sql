-- AGGREGATE ONLY. Read only; set statement_timeout <= 120000 ms in the runner.
-- Full record scope for the exact aliases present in complete Query 201:
-- emar.medication, detail.product_description, pharmacy.medication, rx.drug.
-- product_description_other additionally uses adjacent explicit 3% saline text.
-- Respiratory formulations are inventoried, NOT accepted as IV treatment.
-- Candidate/source memberships are not administered doses or episodes.
-- A pharmacy association is reported as an association, not drug identity proof.
-- Other free text is represented by a canonical label, never returned verbatim.
-- One full detail pass retains all details of order/head seeds plus independent
-- named product hits. For a product-only new head, its unmatched sibling details
-- are not read; detail_scope explicitly distinguishes that route/identity limit.
-- No samples, dose/plan/bag fields, patient IDs, dates, or clinical values output.
WITH names(source, drug_name, formulation) AS (
    VALUES
    ('prescriptions.drug','Sodium Chloride 3% (Hypertonic)','nonrespiratory_name'),
    ('prescriptions.drug','Sodium Chloride 3% (Hy 500mL BAG','nonrespiratory_name'),
    ('prescriptions.drug','Sodium Chloride 3%','nonrespiratory_name'),
    ('prescriptions.drug','Sodium Chloride 3% Inhalation Soln','respiratory_name'),
    ('prescriptions.drug','Sodium Chloride 3% nebulizer','respiratory_name'),
    ('pharmacy.medication','Sodium Chloride 3% (Hypertonic)','nonrespiratory_name'),
    ('pharmacy.medication','Sodium Chloride 3% (Hy 500mL BAG','nonrespiratory_name'),
    ('pharmacy.medication','Sodium Chloride 3% Inhalation Soln','respiratory_name'),
    ('pharmacy.medication','Sodium Chloride 3% nebulizer','respiratory_name'),
    ('emar.medication','sodium chloride 3 %','nonrespiratory_name'),
    ('emar.medication','Sodium Chloride 3% Inhalation Soln','respiratory_name'),
    ('emar_detail.product_description','Sodium Chloride 3% Inhalation Soln 15 mL Neb Vial','respiratory_name'),
    ('emar_detail.product_description','Sodium Chloride 3% Inhalation Soln 4 mL Neb Vial','respiratory_name')
), order_rows AS MATERIALIZED (
    SELECT n.*, p.pharmacy_id, p.subject_id, p.hadm_id,
           nullif(upper(trim(p.route)),'') AS route
    FROM names n JOIN mimiciv_hosp.prescriptions p ON p.drug = n.drug_name
    WHERE n.source = 'prescriptions.drug'
    UNION ALL
    SELECT n.*, p.pharmacy_id, p.subject_id, p.hadm_id,
           nullif(upper(trim(p.route)),'') AS route
    FROM names n JOIN mimiciv_hosp.pharmacy p ON p.medication = n.drug_name
    WHERE n.source = 'pharmacy.medication'
), exact_pharmacies AS MATERIALIZED (
    SELECT DISTINCT pharmacy_id FROM order_rows
    WHERE source = 'prescriptions.drug' AND drug_name = 'Sodium Chloride 3% (Hypertonic)'
      AND pharmacy_id IS NOT NULL
), order_pharmacies AS MATERIALIZED (
    SELECT DISTINCT pharmacy_id FROM order_rows WHERE pharmacy_id IS NOT NULL
), seed_heads AS MATERIALIZED (
    SELECT e.emar_id, e.emar_seq, e.subject_id, e.hadm_id, e.pharmacy_id,
           e.medication, e.event_txt
    FROM order_pharmacies o JOIN mimiciv_hosp.emar e USING (pharmacy_id)
    UNION
    SELECT e.emar_id, e.emar_seq, e.subject_id, e.hadm_id, e.pharmacy_id,
           e.medication, e.event_txt
    FROM names n JOIN mimiciv_hosp.emar e ON e.medication = n.drug_name
    WHERE n.source = 'emar.medication'
), detail_scope AS MATERIALIZED (
    SELECT d.emar_id, d.emar_seq, d.subject_id, d.pharmacy_id,
           d.product_description, d.product_description_other,
           nullif(upper(trim(d.route)),'') AS route,
           s.emar_id IS NOT NULL AS complete_seed_detail_scope,
           n.drug_name AS matched_product_name, n.formulation AS product_formulation,
           coalesce(d.product_description_other ~*
             '(^|[^[:alnum:]])(sodium[[:space:]]+chloride|nacl|saline)[[:space:](]*3([.]0+)?[[:space:]]*%|(^|[^[:digit:].])3([.]0+)?[[:space:]]*%[[:space:])]*(hypertonic[[:space:]]+)?(sodium[[:space:]]+chloride|nacl|saline)([^[:alpha:]]|$)',
             false) AS other_explicit_three_percent
    FROM mimiciv_hosp.emar_detail d
    LEFT JOIN seed_heads s ON s.emar_id = d.emar_id
    LEFT JOIN names n ON n.source = 'emar_detail.product_description'
                    AND n.drug_name = d.product_description
    WHERE s.emar_id IS NOT NULL OR n.drug_name IS NOT NULL
       OR d.product_description_other ~*
          '(^|[^[:alnum:]])(sodium[[:space:]]+chloride|nacl|saline)[[:space:](]*3([.]0+)?[[:space:]]*%|(^|[^[:digit:].])3([.]0+)?[[:space:]]*%[[:space:])]*(hypertonic[[:space:]]+)?(sodium[[:space:]]+chloride|nacl|saline)([^[:alpha:]]|$)'
), product_hits AS MATERIALIZED (
    SELECT DISTINCT 'emar_detail.product_description'::text AS source,
           matched_product_name AS drug_name, product_formulation AS formulation, emar_id
    FROM detail_scope WHERE matched_product_name IS NOT NULL
    UNION
    SELECT DISTINCT 'emar_detail.product_description_other',
           CASE WHEN product_description_other ~* 'inhal|nebul|(^|[^[:alpha:]])neb([^[:alpha:]]|$)|nasal'
                THEN '3% sodium chloride/saline (respiratory free-text match)'
                ELSE '3% sodium chloride/saline (free-text match)' END,
           CASE WHEN product_description_other ~* 'inhal|nebul|(^|[^[:alpha:]])neb([^[:alpha:]]|$)|nasal'
                THEN 'respiratory_name' ELSE 'free_text_form_unresolved' END, emar_id
    FROM detail_scope WHERE other_explicit_three_percent
), all_heads AS MATERIALIZED (
    SELECT * FROM seed_heads
    UNION
    SELECT e.emar_id, e.emar_seq, e.subject_id, e.hadm_id, e.pharmacy_id,
           e.medication, e.event_txt
    FROM (SELECT DISTINCT emar_id FROM product_hits WHERE emar_id IS NOT NULL) k
    JOIN mimiciv_hosp.emar e USING (emar_id)
), memberships AS MATERIALIZED (
    SELECT DISTINCT o.source, o.drug_name, o.formulation, e.emar_id
    FROM order_rows o JOIN all_heads e ON e.pharmacy_id = o.pharmacy_id
    UNION
    SELECT n.source, n.drug_name, n.formulation, e.emar_id
    FROM names n JOIN all_heads e ON e.medication = n.drug_name
    WHERE n.source = 'emar.medication'
    UNION
    SELECT source, drug_name, formulation, emar_id FROM product_hits
), detail_context AS MATERIALIZED (
    SELECT d.emar_id, bool_or(d.complete_seed_detail_scope) AS complete_seed_detail_scope,
           bool_or(d.route IN ('IV','IV DRIP')) AS any_detail_iv,
           bool_or(d.route NOT IN ('IV','IV DRIP')) AS any_detail_other_route,
           string_agg(DISTINCT d.route, ',' ORDER BY d.route) AS detail_routes,
           bool_or(d.subject_id IS DISTINCT FROM e.subject_id
                OR d.emar_seq IS DISTINCT FROM e.emar_seq
                OR (d.pharmacy_id IS NOT NULL AND d.pharmacy_id IS DISTINCT FROM e.pharmacy_id))
                AS detail_identity_problem
    FROM detail_scope d LEFT JOIN all_heads e ON e.emar_id = d.emar_id
    GROUP BY d.emar_id
), order_context AS MATERIALIZED (
    SELECT e.emar_id, bool_or(o.route IN ('IV','IV DRIP')) AS any_order_iv,
           bool_or(o.route NOT IN ('IV','IV DRIP')) AS any_order_other_route,
           string_agg(DISTINCT o.route, ',' ORDER BY o.route) AS order_routes,
           bool_or(o.subject_id IS NULL OR o.hadm_id IS NULL
                   OR o.subject_id IS DISTINCT FROM e.subject_id
                   OR o.hadm_id IS DISTINCT FROM e.hadm_id) AS order_identity_problem
    FROM all_heads e JOIN order_rows o ON o.pharmacy_id = e.pharmacy_id
    GROUP BY e.emar_id
), head_context AS MATERIALIZED (
    SELECT e.*, x.pharmacy_id IS NOT NULL AS covered_by_exact_rx,
           CASE WHEN coalesce(d.any_detail_iv,false) OR coalesce(o.any_order_iv,false)
                THEN CASE WHEN coalesce(d.any_detail_other_route,false)
                                 OR coalesce(o.any_order_other_route,false)
                          THEN 'iv_and_other_route' ELSE 'iv_evidence_only' END
                WHEN coalesce(d.any_detail_other_route,false) OR coalesce(o.any_order_other_route,false)
                THEN 'other_route_only' ELSE 'route_missing' END AS route_pattern,
           'detail=' || coalesce(d.detail_routes,'missing') ||
              ';named_order=' || coalesce(o.order_routes,'missing') AS route_values,
           CASE WHEN s.emar_id IS NOT NULL THEN 'all_seed_head_details'
                ELSE 'matched_product_details_only' END AS detail_scope,
           CASE WHEN nullif(trim(e.medication),'') IS NULL THEN 'missing_head'
                WHEN e.medication IN ('sodium chloride 3 %','Sodium Chloride 3%',
                     'Sodium Chloride 3% (Hy 500mL BAG','Sodium Chloride 3% (Hypertonic)')
                     THEN 'nonrespiratory_3pct_head'
                WHEN e.medication IN ('Sodium Chloride 3% Inhalation Soln',
                     'Sodium Chloride 3% nebulizer') THEN 'respiratory_3pct_head'
                ELSE 'other_nonempty_head' END AS head_name_class,
           coalesce(d.detail_identity_problem,false) OR coalesce(o.order_identity_problem,false)
             OR e.subject_id IS NULL OR e.hadm_id IS NULL AS identity_problem
    FROM all_heads e LEFT JOIN exact_pharmacies x USING (pharmacy_id)
    LEFT JOIN detail_context d USING (emar_id)
    LEFT JOIN order_context o USING (emar_id)
    LEFT JOIN seed_heads s USING (emar_id)
), head_facts AS MATERIALIZED (
    SELECT m.source, m.drug_name, m.formulation, h.*
    FROM memberships m JOIN head_context h USING (emar_id)
    UNION ALL
    SELECT '_candidate_head_union', 'all inventoried candidate heads',
           CASE WHEN bool_or(m.formulation = 'nonrespiratory_name') THEN 'has_nonrespiratory_name'
                WHEN bool_or(m.formulation = 'free_text_form_unresolved') THEN 'has_unresolved_free_text'
                ELSE 'respiratory_names_only' END, h.*
    FROM memberships m JOIN head_context h USING (emar_id)
    GROUP BY h.emar_id,h.emar_seq,h.subject_id,h.hadm_id,h.pharmacy_id,h.medication,h.event_txt,
             h.covered_by_exact_rx,h.route_pattern,h.route_values,h.detail_scope,h.head_name_class,h.identity_problem
), result AS (
    SELECT 'emar_source_memberships'::text AS record_kind, source, drug_name, formulation,
           route_pattern, route_values, coalesce(event_txt,'<NULL>') AS administration_status,
           covered_by_exact_rx, detail_scope, head_name_class,
           count(*) AS candidate_records, count(DISTINCT emar_id) AS distinct_heads,
           count(DISTINCT pharmacy_id) AS distinct_pharmacies,
           count(DISTINCT subject_id) AS distinct_subjects,
           count(DISTINCT (subject_id,hadm_id)) FILTER
             (WHERE subject_id IS NOT NULL AND hadm_id IS NOT NULL) AS distinct_admissions,
           count(*) FILTER (WHERE identity_problem) AS identity_problem_heads
    FROM head_facts
    GROUP BY source,drug_name,formulation,route_pattern,route_values,event_txt,
             covered_by_exact_rx,detail_scope,head_name_class
    UNION ALL
    SELECT 'order_source_rows', o.source, o.drug_name, o.formulation,
           CASE WHEN o.route IN ('IV','IV DRIP') THEN 'iv_evidence_only'
                WHEN o.route IS NOT NULL THEN 'other_route_only' ELSE 'route_missing' END,
           coalesce(o.route,'missing'), 'not_an_emar_record',
           x.pharmacy_id IS NOT NULL, 'not_applicable', 'not_applicable',
           count(*), NULL::bigint, count(DISTINCT o.pharmacy_id), count(DISTINCT o.subject_id),
           count(DISTINCT (o.subject_id,o.hadm_id)) FILTER
             (WHERE o.subject_id IS NOT NULL AND o.hadm_id IS NOT NULL), NULL::bigint
    FROM order_rows o LEFT JOIN exact_pharmacies x USING (pharmacy_id)
    GROUP BY o.source,o.drug_name,o.formulation,o.route,x.pharmacy_id IS NOT NULL
    UNION ALL
    SELECT 'orphan_product_memberships', p.source,p.drug_name,p.formulation,
           'unresolved','not_assessed','no_matching_emar_head',false,
           'matched_product_details_only','no_matching_emar_head',
           count(*),0,0,0,0,count(*)
    FROM product_hits p LEFT JOIN all_heads e USING (emar_id)
    WHERE e.emar_id IS NULL GROUP BY p.source,p.drug_name,p.formulation
)
SELECT * FROM result
ORDER BY record_kind,source,drug_name,covered_by_exact_rx,route_pattern,
         route_values,administration_status,detail_scope,head_name_class;
