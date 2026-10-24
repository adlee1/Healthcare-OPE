-- D005-K-QUERY202-PREADJUDICATION-EVIDENCE-v2, stage 202c.
-- Private aggregate-only pharmacy/prescription and two-path order evidence for
-- one preregistered subject bucket.  No ID or timestamp is projected.
WITH
bucket_config AS MATERIALIZED (
    SELECT __BUCKET_INDEX__::integer AS bucket_index, 64::integer AS bucket_count
),
bucket_pharmacy_base AS MATERIALIZED (
    SELECT p.*
    FROM mimiciv_hosp.pharmacy p CROSS JOIN bucket_config b
    WHERE CASE WHEN p.subject_id IS NULL THEN 0
               ELSE mod((('x' || substr(md5(
                    'D005-K-QUERY202-PREADJUDICATION-EVIDENCE-v2|'
                    || p.subject_id::bigint::text), 1, 15))::bit(60)::bigint),
                    64)::integer
          END = b.bucket_index
),
bucket_prescriptions AS MATERIALIZED (
    SELECT r.*
    FROM mimiciv_hosp.prescriptions r CROSS JOIN bucket_config b
    WHERE CASE WHEN r.subject_id IS NULL THEN 0
               ELSE mod((('x' || substr(md5(
                    'D005-K-QUERY202-PREADJUDICATION-EVIDENCE-v2|'
                    || r.subject_id::bigint::text), 1, 15))::bit(60)::bigint),
                    64)::integer
          END = b.bucket_index
),
bucket_heads AS MATERIALIZED (
    SELECT h.*
    FROM mimiciv_hosp.emar h CROSS JOIN bucket_config b
    WHERE CASE WHEN h.subject_id IS NULL THEN 0
               ELSE mod((('x' || substr(md5(
                    'D005-K-QUERY202-PREADJUDICATION-EVIDENCE-v2|'
                    || h.subject_id::bigint::text), 1, 15))::bit(60)::bigint),
                    64)::integer
          END = b.bucket_index
),
bucket_details AS MATERIALIZED (
    SELECT d.*
    FROM mimiciv_hosp.emar_detail d CROSS JOIN bucket_config b
    WHERE CASE WHEN d.subject_id IS NULL THEN 0
               ELSE mod((('x' || substr(md5(
                    'D005-K-QUERY202-PREADJUDICATION-EVIDENCE-v2|'
                    || d.subject_id::bigint::text), 1, 15))::bit(60)::bigint),
                    64)::integer
          END = b.bucket_index
),
bucket_inputs AS MATERIALIZED (
    SELECT 'pharmacy'::text AS source_relation, subject_id FROM bucket_pharmacy_base
    UNION ALL
    SELECT 'prescriptions', subject_id FROM bucket_prescriptions
    UNION ALL
    SELECT 'emar', subject_id FROM bucket_heads
    UNION ALL
    SELECT 'emar_detail', subject_id FROM bucket_details
),
selected_pharmacy AS MATERIALIZED (
    SELECT p.*
    FROM bucket_pharmacy_base p
    WHERE p.medication IS NOT NULL
       OR EXISTS (SELECT 1 FROM mimiciv_hosp.prescriptions r
                  WHERE r.pharmacy_id = p.pharmacy_id)
       OR EXISTS (SELECT 1 FROM mimiciv_hosp.emar h
                  WHERE h.pharmacy_id = p.pharmacy_id)
       OR EXISTS (SELECT 1 FROM mimiciv_hosp.emar_detail d
                  WHERE d.pharmacy_id = p.pharmacy_id)
),
pharmacy_payloads AS MATERIALIZED (
    SELECT medication, proc_type, status, route, frequency, disp_sched,
           infusion_type, sliding_scale, lockout_interval,
           basal_rate::text AS basal_rate, one_hr_max,
           doses_per_24_hrs::text AS doses_per_24_hrs,
           duration::text AS duration, duration_interval,
           expiration_value::text AS expiration_value, expiration_unit,
           dispensation, fill_quantity
    FROM selected_pharmacy
),
pharmacy_counts AS MATERIALIZED (
    SELECT medication, proc_type, status, route, frequency, disp_sched,
           infusion_type, sliding_scale, lockout_interval, basal_rate,
           one_hr_max, doses_per_24_hrs, duration, duration_interval,
           expiration_value, expiration_unit, dispensation, fill_quantity,
           count(*)::bigint AS multiplicity
    FROM pharmacy_payloads
    GROUP BY medication, proc_type, status, route, frequency, disp_sched,
             infusion_type, sliding_scale, lockout_interval, basal_rate,
             one_hr_max, doses_per_24_hrs, duration, duration_interval,
             expiration_value, expiration_unit, dispensation, fill_quantity
),
pharmacy_grouped AS MATERIALIZED (
    SELECT jsonb_build_object(
        'medication', medication,
        'proc_type', proc_type,
        'status', status,
        'route', route,
        'frequency', frequency,
        'disp_sched', disp_sched,
        'infusion_type', infusion_type,
        'sliding_scale', sliding_scale,
        'lockout_interval', lockout_interval,
        'basal_rate', basal_rate,
        'one_hr_max', one_hr_max,
        'doses_per_24_hrs', doses_per_24_hrs,
        'duration', duration,
        'duration_interval', duration_interval,
        'expiration_value', expiration_value,
        'expiration_unit', expiration_unit,
        'dispensation', dispensation,
        'fill_quantity', fill_quantity
    ) AS payload,
    multiplicity
    FROM pharmacy_counts
),
prescription_payloads AS MATERIALIZED (
    SELECT drug_type, drug, formulary_drug_cd, gsn, ndc, prod_strength,
           form_rx, dose_val_rx, dose_unit_rx, form_val_disp, form_unit_disp,
           doses_per_24_hrs::text AS doses_per_24_hrs, route
    FROM bucket_prescriptions
),
prescription_counts AS MATERIALIZED (
    SELECT drug_type, drug, formulary_drug_cd, gsn, ndc, prod_strength,
           form_rx, dose_val_rx, dose_unit_rx, form_val_disp, form_unit_disp,
           doses_per_24_hrs, route,
           count(*)::bigint AS multiplicity
    FROM prescription_payloads
    GROUP BY drug_type, drug, formulary_drug_cd, gsn, ndc, prod_strength,
             form_rx, dose_val_rx, dose_unit_rx, form_val_disp, form_unit_disp,
             doses_per_24_hrs, route
),
prescription_grouped AS MATERIALIZED (
    SELECT jsonb_build_object(
        'drug_type', drug_type,
        'drug', drug,
        'formulary_drug_cd', formulary_drug_cd,
        'gsn', gsn,
        'ndc', ndc,
        'prod_strength', prod_strength,
        'form_rx', form_rx,
        'dose_val_rx', dose_val_rx,
        'dose_unit_rx', dose_unit_rx,
        'form_val_disp', form_val_disp,
        'form_unit_disp', form_unit_disp,
        'doses_per_24_hrs', doses_per_24_hrs,
        'route', route
    ) AS payload,
    multiplicity
    FROM prescription_counts
),
pharmacy_prescription_rows AS MATERIALIZED (
    SELECT r.*,
           p.medication AS pharmacy_medication,
           p.route AS pharmacy_route,
           CASE WHEN p.pharmacy_row_matched IS NULL THEN 'pharmacy_missing'
                WHEN p.subject_id IS NULL OR r.subject_id IS NULL THEN 'subject_missing'
                WHEN p.subject_id <> r.subject_id THEN 'subject_conflict'
                WHEN p.hadm_id IS NULL OR r.hadm_id IS NULL THEN 'hadm_missing'
                WHEN p.hadm_id <> r.hadm_id THEN 'hadm_conflict'
                ELSE 'exact'
           END::text AS link_identity_state,
           CASE WHEN p.poe_id IS NOT NULL AND r.poe_id IS NOT NULL
                          AND p.poe_id <> r.poe_id THEN 'conflict'
                WHEN p.poe_id IS NULL OR r.poe_id IS NULL THEN 'missing'
                ELSE 'exact'
           END::text AS poe_auxiliary_state
    FROM bucket_prescriptions r
    LEFT JOIN (
        SELECT source.*, true AS pharmacy_row_matched
        FROM mimiciv_hosp.pharmacy source
    ) p ON p.pharmacy_id = r.pharmacy_id
),
pharmacy_prescription_payloads AS MATERIALIZED (
    SELECT link_identity_state, poe_auxiliary_state, pharmacy_medication,
           pharmacy_route, drug_type, drug, formulary_drug_cd, gsn, ndc,
           prod_strength, form_rx, dose_val_rx, dose_unit_rx, form_val_disp,
           form_unit_disp, doses_per_24_hrs::text AS doses_per_24_hrs, route
    FROM pharmacy_prescription_rows
),
pharmacy_prescription_counts AS MATERIALIZED (
    SELECT link_identity_state, poe_auxiliary_state, pharmacy_medication,
           pharmacy_route, drug_type, drug, formulary_drug_cd, gsn, ndc,
           prod_strength, form_rx, dose_val_rx, dose_unit_rx, form_val_disp,
           form_unit_disp, doses_per_24_hrs, route,
           count(*)::bigint AS multiplicity
    FROM pharmacy_prescription_payloads
    GROUP BY link_identity_state, poe_auxiliary_state, pharmacy_medication,
             pharmacy_route, drug_type, drug, formulary_drug_cd, gsn, ndc,
             prod_strength, form_rx, dose_val_rx, dose_unit_rx, form_val_disp,
             form_unit_disp, doses_per_24_hrs, route
),
pharmacy_prescription_grouped AS MATERIALIZED (
    SELECT jsonb_build_object(
        'link_identity_state', link_identity_state,
        'poe_auxiliary_state', poe_auxiliary_state,
        'pharmacy_medication', pharmacy_medication,
        'pharmacy_route', pharmacy_route,
        'drug_type', drug_type,
        'drug', drug,
        'formulary_drug_cd', formulary_drug_cd,
        'gsn', gsn,
        'ndc', ndc,
        'prod_strength', prod_strength,
        'form_rx', form_rx,
        'dose_val_rx', dose_val_rx,
        'dose_unit_rx', dose_unit_rx,
        'form_val_disp', form_val_disp,
        'form_unit_disp', form_unit_disp,
        'doses_per_24_hrs', doses_per_24_hrs,
        'route', route
    ) AS payload,
    multiplicity
    FROM pharmacy_prescription_counts
),
pharmacy_no_prescription_payloads AS MATERIALIZED (
    SELECT p.medication, p.proc_type, p.status, p.route, p.frequency,
           p.disp_sched, p.infusion_type, p.sliding_scale, p.lockout_interval,
           p.basal_rate::text AS basal_rate, p.one_hr_max,
           p.doses_per_24_hrs::text AS doses_per_24_hrs,
           p.duration::text AS duration, p.duration_interval,
           p.expiration_value::text AS expiration_value, p.expiration_unit,
           p.dispensation, p.fill_quantity,
           'no_prescription_component'::text AS prescription_match_state
    FROM selected_pharmacy p
    WHERE NOT EXISTS (
        SELECT 1 FROM mimiciv_hosp.prescriptions r
        WHERE r.pharmacy_id = p.pharmacy_id
    )
),
pharmacy_no_prescription_counts AS MATERIALIZED (
    SELECT medication, proc_type, status, route, frequency, disp_sched,
           infusion_type, sliding_scale, lockout_interval, basal_rate,
           one_hr_max, doses_per_24_hrs, duration, duration_interval,
           expiration_value, expiration_unit, dispensation, fill_quantity,
           prescription_match_state,
           count(*)::bigint AS multiplicity
    FROM pharmacy_no_prescription_payloads
    GROUP BY medication, proc_type, status, route, frequency, disp_sched,
             infusion_type, sliding_scale, lockout_interval, basal_rate,
             one_hr_max, doses_per_24_hrs, duration, duration_interval,
             expiration_value, expiration_unit, dispensation, fill_quantity,
             prescription_match_state
),
pharmacy_no_prescription_grouped AS MATERIALIZED (
    SELECT jsonb_build_object(
        'medication', medication,
        'proc_type', proc_type,
        'status', status,
        'route', route,
        'frequency', frequency,
        'disp_sched', disp_sched,
        'infusion_type', infusion_type,
        'sliding_scale', sliding_scale,
        'lockout_interval', lockout_interval,
        'basal_rate', basal_rate,
        'one_hr_max', one_hr_max,
        'doses_per_24_hrs', doses_per_24_hrs,
        'duration', duration,
        'duration_interval', duration_interval,
        'expiration_value', expiration_value,
        'expiration_unit', expiration_unit,
        'dispensation', dispensation,
        'fill_quantity', fill_quantity,
        'prescription_match_state', prescription_match_state
    ) AS payload,
    multiplicity
    FROM pharmacy_no_prescription_counts
),
head_order_rows AS MATERIALIZED (
    SELECT h.medication AS head_medication,
           p.medication AS pharmacy_medication,
           p.route AS pharmacy_route,
           r.drug_type, r.drug, r.formulary_drug_cd, r.gsn, r.ndc,
           r.prod_strength, r.form_rx, r.dose_val_rx, r.dose_unit_rx,
           r.form_val_disp, r.form_unit_disp, r.doses_per_24_hrs,
           r.route,
           CASE WHEN p.pharmacy_row_matched IS NULL THEN 'pharmacy_missing'
                WHEN r.prescription_row_matched IS NULL THEN 'prescription_missing'
                WHEN p.subject_id IS NULL OR h.subject_id IS NULL
                    THEN 'pharmacy_subject_missing'
                WHEN p.subject_id <> h.subject_id THEN 'pharmacy_subject_conflict'
                WHEN r.subject_id IS NULL THEN 'prescription_subject_missing'
                WHEN r.subject_id <> h.subject_id THEN 'prescription_subject_conflict'
                WHEN h.hadm_id IS NULL OR p.hadm_id IS NULL THEN 'pharmacy_hadm_missing'
                WHEN h.hadm_id <> p.hadm_id THEN 'pharmacy_hadm_conflict'
                WHEN r.hadm_id IS NULL THEN 'prescription_hadm_missing'
                WHEN h.hadm_id <> r.hadm_id OR p.hadm_id <> r.hadm_id
                    THEN 'prescription_hadm_conflict'
                ELSE 'exact'
           END::text AS link_identity_state,
           CASE WHEN (h.poe_id IS NOT NULL AND p.poe_id IS NOT NULL
                           AND h.poe_id <> p.poe_id)
                       OR (h.poe_id IS NOT NULL AND r.poe_id IS NOT NULL
                           AND h.poe_id <> r.poe_id)
                       OR (p.poe_id IS NOT NULL AND r.poe_id IS NOT NULL
                           AND p.poe_id <> r.poe_id) THEN 'conflict'
                WHEN h.poe_id IS NULL OR p.poe_id IS NULL OR r.poe_id IS NULL
                    THEN 'missing'
                ELSE 'exact'
           END::text AS poe_auxiliary_state
    FROM bucket_heads h
    LEFT JOIN (
        SELECT source.*, true AS pharmacy_row_matched
        FROM mimiciv_hosp.pharmacy source
    ) p ON p.pharmacy_id = h.pharmacy_id
    LEFT JOIN (
        SELECT source.*, true AS prescription_row_matched
        FROM mimiciv_hosp.prescriptions source
    ) r ON r.pharmacy_id = h.pharmacy_id
    WHERE h.pharmacy_id IS NOT NULL
),
head_order_payloads AS MATERIALIZED (
    SELECT link_identity_state, poe_auxiliary_state, head_medication,
           pharmacy_medication, pharmacy_route, drug_type, drug,
           formulary_drug_cd, gsn, ndc, prod_strength, form_rx, dose_val_rx,
           dose_unit_rx, form_val_disp, form_unit_disp,
           doses_per_24_hrs::text AS doses_per_24_hrs, route
    FROM head_order_rows
),
head_order_counts AS MATERIALIZED (
    SELECT link_identity_state, poe_auxiliary_state, head_medication,
           pharmacy_medication, pharmacy_route, drug_type, drug,
           formulary_drug_cd, gsn, ndc, prod_strength, form_rx, dose_val_rx,
           dose_unit_rx, form_val_disp, form_unit_disp, doses_per_24_hrs,
           route, count(*)::bigint AS multiplicity
    FROM head_order_payloads
    GROUP BY link_identity_state, poe_auxiliary_state, head_medication,
             pharmacy_medication, pharmacy_route, drug_type, drug,
             formulary_drug_cd, gsn, ndc, prod_strength, form_rx, dose_val_rx,
             dose_unit_rx, form_val_disp, form_unit_disp, doses_per_24_hrs,
             route
),
head_order_grouped AS MATERIALIZED (
    SELECT jsonb_build_object(
        'link_identity_state', link_identity_state,
        'poe_auxiliary_state', poe_auxiliary_state,
        'head_medication', head_medication,
        'pharmacy_medication', pharmacy_medication,
        'pharmacy_route', pharmacy_route,
        'drug_type', drug_type,
        'drug', drug,
        'formulary_drug_cd', formulary_drug_cd,
        'gsn', gsn,
        'ndc', ndc,
        'prod_strength', prod_strength,
        'form_rx', form_rx,
        'dose_val_rx', dose_val_rx,
        'dose_unit_rx', dose_unit_rx,
        'form_val_disp', form_val_disp,
        'form_unit_disp', form_unit_disp,
        'doses_per_24_hrs', doses_per_24_hrs,
        'route', route
    ) AS payload,
    multiplicity
    FROM head_order_counts
),
detail_order_rows AS MATERIALIZED (
    SELECT CASE WHEN d.parent_field_ordinal IS NULL THEN 'parent'
                ELSE 'product' END::text AS row_role,
           d.parent_field_ordinal, d.product_description,
           d.product_description_other, d.product_code,
           d.route AS detail_route, d.dose_due_unit, d.dose_given_unit,
           d.product_unit, d.infusion_rate_unit,
           p.medication AS pharmacy_medication,
           p.route AS pharmacy_route,
           r.drug_type, r.drug, r.formulary_drug_cd, r.gsn, r.ndc,
           r.prod_strength, r.form_rx, r.dose_val_rx, r.dose_unit_rx,
           r.form_val_disp, r.form_unit_disp, r.doses_per_24_hrs,
           r.route,
           CASE WHEN p.pharmacy_row_matched IS NULL THEN 'pharmacy_missing'
                WHEN r.prescription_row_matched IS NULL THEN 'prescription_missing'
                WHEN p.subject_id IS NULL OR d.subject_id IS NULL
                    THEN 'pharmacy_subject_missing'
                WHEN p.subject_id <> d.subject_id THEN 'pharmacy_subject_conflict'
                WHEN r.subject_id IS NULL THEN 'prescription_subject_missing'
                WHEN r.subject_id <> d.subject_id THEN 'prescription_subject_conflict'
                WHEN p.hadm_id IS NULL OR r.hadm_id IS NULL THEN 'hadm_missing'
                WHEN p.hadm_id <> r.hadm_id THEN 'hadm_conflict'
                ELSE 'exact'
           END::text AS link_identity_state,
           CASE WHEN p.poe_id IS NOT NULL AND r.poe_id IS NOT NULL
                          AND p.poe_id <> r.poe_id THEN 'conflict'
                WHEN p.poe_id IS NULL OR r.poe_id IS NULL THEN 'missing'
                ELSE 'exact'
           END::text AS poe_auxiliary_state
    FROM bucket_details d
    LEFT JOIN (
        SELECT source.*, true AS pharmacy_row_matched
        FROM mimiciv_hosp.pharmacy source
    ) p ON p.pharmacy_id = d.pharmacy_id
    LEFT JOIN (
        SELECT source.*, true AS prescription_row_matched
        FROM mimiciv_hosp.prescriptions source
    ) r ON r.pharmacy_id = d.pharmacy_id
    WHERE d.pharmacy_id IS NOT NULL
),
detail_order_payloads AS MATERIALIZED (
    SELECT link_identity_state, poe_auxiliary_state, row_role,
           parent_field_ordinal, product_description,
           product_description_other, product_code, detail_route,
           dose_due_unit, dose_given_unit, product_unit, infusion_rate_unit,
           pharmacy_medication, pharmacy_route, drug_type, drug,
           formulary_drug_cd, gsn, ndc, prod_strength, form_rx, dose_val_rx,
           dose_unit_rx, form_val_disp, form_unit_disp,
           doses_per_24_hrs::text AS doses_per_24_hrs, route
    FROM detail_order_rows
),
detail_order_counts AS MATERIALIZED (
    SELECT link_identity_state, poe_auxiliary_state, row_role,
           parent_field_ordinal, product_description,
           product_description_other, product_code, detail_route,
           dose_due_unit, dose_given_unit, product_unit, infusion_rate_unit,
           pharmacy_medication, pharmacy_route, drug_type, drug,
           formulary_drug_cd, gsn, ndc, prod_strength, form_rx, dose_val_rx,
           dose_unit_rx, form_val_disp, form_unit_disp, doses_per_24_hrs,
           route, count(*)::bigint AS multiplicity
    FROM detail_order_payloads
    GROUP BY link_identity_state, poe_auxiliary_state, row_role,
             parent_field_ordinal, product_description,
             product_description_other, product_code, detail_route,
             dose_due_unit, dose_given_unit, product_unit, infusion_rate_unit,
             pharmacy_medication, pharmacy_route, drug_type, drug,
             formulary_drug_cd, gsn, ndc, prod_strength, form_rx, dose_val_rx,
             dose_unit_rx, form_val_disp, form_unit_disp, doses_per_24_hrs,
             route
),
detail_order_grouped AS MATERIALIZED (
    SELECT jsonb_build_object(
        'link_identity_state', link_identity_state,
        'poe_auxiliary_state', poe_auxiliary_state,
        'row_role', row_role,
        'parent_field_ordinal', parent_field_ordinal,
        'product_description', product_description,
        'product_description_other', product_description_other,
        'product_code', product_code,
        'detail_route', detail_route,
        'dose_due_unit', dose_due_unit,
        'dose_given_unit', dose_given_unit,
        'product_unit', product_unit,
        'infusion_rate_unit', infusion_rate_unit,
        'pharmacy_medication', pharmacy_medication,
        'pharmacy_route', pharmacy_route,
        'drug_type', drug_type,
        'drug', drug,
        'formulary_drug_cd', formulary_drug_cd,
        'gsn', gsn,
        'ndc', ndc,
        'prod_strength', prod_strength,
        'form_rx', form_rx,
        'dose_val_rx', dose_val_rx,
        'dose_unit_rx', dose_unit_rx,
        'form_val_disp', form_val_disp,
        'form_unit_disp', form_unit_disp,
        'doses_per_24_hrs', doses_per_24_hrs,
        'route', route
    ) AS payload,
    multiplicity
    FROM detail_order_counts
),
ndc_handoff_payloads AS MATERIALIZED (
    SELECT *
    FROM prescription_payloads
    WHERE ndc IS NOT NULL
),
ndc_handoff_counts AS MATERIALIZED (
    SELECT drug_type, drug, formulary_drug_cd, gsn, ndc, prod_strength,
           form_rx, dose_val_rx, dose_unit_rx, form_val_disp, form_unit_disp,
           doses_per_24_hrs, route,
           count(*)::bigint AS multiplicity
    FROM ndc_handoff_payloads
    GROUP BY drug_type, drug, formulary_drug_cd, gsn, ndc, prod_strength,
             form_rx, dose_val_rx, dose_unit_rx, form_val_disp, form_unit_disp,
             doses_per_24_hrs, route
),
ndc_handoff_grouped AS MATERIALIZED (
    SELECT jsonb_build_object(
        'drug_type', drug_type,
        'drug', drug,
        'formulary_drug_cd', formulary_drug_cd,
        'gsn', gsn,
        'ndc', ndc,
        'prod_strength', prod_strength,
        'form_rx', form_rx,
        'dose_val_rx', dose_val_rx,
        'dose_unit_rx', dose_unit_rx,
        'form_val_disp', form_val_disp,
        'form_unit_disp', form_unit_disp,
        'doses_per_24_hrs', doses_per_24_hrs,
        'route', route
    ) AS payload,
    multiplicity
    FROM ndc_handoff_counts
),
tuple_rows AS MATERIALIZED (
    SELECT 'pharmacy_product_context'::text AS tuple_kind,
           payload, multiplicity
    FROM pharmacy_grouped
    UNION ALL
    SELECT 'pharmacy_no_prescription_component', payload, multiplicity
    FROM pharmacy_no_prescription_grouped
),
controls(control_name, control_value) AS MATERIALIZED (
    SELECT 'bucket_assignment_violations',
           count(*) FILTER (WHERE CASE WHEN subject_id IS NULL THEN 0
               ELSE mod((('x' || substr(md5(
                    'D005-K-QUERY202-PREADJUDICATION-EVIDENCE-v2|'
                    || subject_id::bigint::text), 1, 15))::bit(60)::bigint),
                    64)::integer END <> (SELECT bucket_index FROM bucket_config))
    FROM bucket_pharmacy_base
    UNION ALL
    SELECT 'null_subject_outside_bucket_zero',
           count(*)::bigint
    FROM bucket_pharmacy_base source CROSS JOIN bucket_config b
    WHERE source.subject_id IS NULL AND b.bucket_index <> 0
    UNION ALL
    SELECT 'bucket_input_rows', count(*)::bigint FROM bucket_pharmacy_base
    UNION ALL
    SELECT 'bucket_output_multiplicity', coalesce(sum(multiplicity), 0)::bigint
    FROM tuple_rows
    UNION ALL
    SELECT 'pharmacy_product_context_input_rows', count(*)::bigint FROM pharmacy_payloads
    UNION ALL
    SELECT 'pharmacy_product_context_tuple_multiplicity', coalesce(sum(multiplicity), 0)::bigint
    FROM pharmacy_grouped
    UNION ALL
    SELECT 'pharmacy_no_prescription_component_input_rows', count(*)::bigint FROM pharmacy_no_prescription_payloads
    UNION ALL
    SELECT 'pharmacy_no_prescription_component_tuple_multiplicity', coalesce(sum(multiplicity), 0)::bigint
    FROM pharmacy_no_prescription_grouped
)
SELECT 2::integer AS schema_version,
       '202c_pharmacy_context'::text AS stage,
       b.bucket_index,
       'tuple'::text AS record_kind,
       t.tuple_kind,
       replace(encode(convert_to(t.payload::text, 'UTF8'), 'base64'), E'\n', '')
           AS tuple_json_base64,
       t.multiplicity,
       ''::text AS control_name,
       NULL::bigint AS control_value,
       current_setting('transaction_isolation') AS transaction_isolation,
       current_setting('transaction_read_only') AS transaction_read_only,
       pg_current_snapshot()::text AS snapshot_token
FROM tuple_rows t CROSS JOIN bucket_config b
UNION ALL
SELECT 2, '202c_pharmacy_context', b.bucket_index, 'control', '', '', NULL::bigint,
       c.control_name, c.control_value,
       current_setting('transaction_isolation'),
       current_setting('transaction_read_only'),
       pg_current_snapshot()::text
FROM controls c CROSS JOIN bucket_config b;
