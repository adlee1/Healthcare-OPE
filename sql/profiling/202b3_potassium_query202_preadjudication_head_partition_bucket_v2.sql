-- D005-K-QUERY202-PREADJUDICATION-EVIDENCE-v2, stage 202b.
-- Private aggregate-only detail/head evidence for one preregistered subject
-- bucket.  The runner replaces the single closed marker with an integer 0..63.
-- No patient/event/order identifier or timestamp is projected.
WITH
bucket_config AS MATERIALIZED (
    SELECT __BUCKET_INDEX__::integer AS bucket_index, 64::integer AS bucket_count
),
bucket_nonnull_medication_heads AS MATERIALIZED (
    SELECT h.subject_id, h.emar_id, h.emar_seq, h.medication,
           count(*)::bigint AS head_multiplicity
    FROM mimiciv_hosp.emar h
    CROSS JOIN bucket_config b
    WHERE h.medication IS NOT NULL
      AND CASE WHEN h.subject_id IS NULL THEN 0
               ELSE mod((('x' || substr(md5(
                    'D005-K-QUERY202-PREADJUDICATION-EVIDENCE-v2|'
                    || h.subject_id::bigint::text), 1, 15))::bit(60)::bigint),
                    64)::integer
          END = b.bucket_index
    GROUP BY h.subject_id, h.emar_id, h.emar_seq, h.medication
),
bucket_detail AS MATERIALIZED (
    SELECT d.*
    FROM mimiciv_hosp.emar_detail d
    CROSS JOIN bucket_config b
    WHERE CASE WHEN d.subject_id IS NULL THEN 0
               ELSE mod((('x' || substr(md5(
                    'D005-K-QUERY202-PREADJUDICATION-EVIDENCE-v2|'
                    || d.subject_id::bigint::text), 1, 15))::bit(60)::bigint),
                    64)::integer
          END = b.bucket_index
),
selected_detail AS MATERIALIZED (
    SELECT d.*,
           CASE WHEN d.parent_field_ordinal IS NULL THEN 'parent'
                ELSE 'product'
           END::text AS row_role
    FROM bucket_detail d
    WHERE d.product_description IS NOT NULL
       OR d.product_description_other IS NOT NULL
       OR d.product_code IS NOT NULL
       OR EXISTS (
            SELECT 1
            FROM mimiciv_hosp.emar h
            WHERE h.emar_id = d.emar_id
              AND h.subject_id = d.subject_id
              AND h.emar_seq = d.emar_seq
              AND h.medication IS NOT NULL
       )
),
detail_payloads AS MATERIALIZED (
    SELECT row_role, parent_field_ordinal, administration_type,
           complete_dose_not_given, dose_due, dose_due_unit, dose_given,
           dose_given_unit, will_remainder_of_dose_be_given,
           product_amount_given, product_unit, product_code,
           product_description, product_description_other, prior_infusion_rate,
           route, infusion_rate, infusion_rate_adjustment,
           infusion_rate_adjustment_amount, infusion_rate_unit,
           infusion_complete, completion_interval, new_iv_bag_hung,
           continued_infusion_in_other_location, restart_interval,
           non_formulary_visual_verification
    FROM selected_detail
),
detail_context_counts AS MATERIALIZED (
    SELECT row_role, parent_field_ordinal, administration_type,
           complete_dose_not_given, dose_due, dose_due_unit, dose_given,
           dose_given_unit, will_remainder_of_dose_be_given,
           product_amount_given, product_unit, product_code,
           product_description, product_description_other, prior_infusion_rate,
           route, infusion_rate, infusion_rate_adjustment,
           infusion_rate_adjustment_amount, infusion_rate_unit,
           infusion_complete, completion_interval, new_iv_bag_hung,
           continued_infusion_in_other_location, restart_interval,
           non_formulary_visual_verification,
           count(*)::bigint AS multiplicity
    FROM detail_payloads
    GROUP BY row_role, parent_field_ordinal, administration_type,
             complete_dose_not_given, dose_due, dose_due_unit, dose_given,
             dose_given_unit, will_remainder_of_dose_be_given,
             product_amount_given, product_unit, product_code,
             product_description, product_description_other, prior_infusion_rate,
             route, infusion_rate, infusion_rate_adjustment,
             infusion_rate_adjustment_amount, infusion_rate_unit,
             infusion_complete, completion_interval, new_iv_bag_hung,
             continued_infusion_in_other_location, restart_interval,
             non_formulary_visual_verification
),
detail_context_grouped AS MATERIALIZED (
    SELECT jsonb_build_object(
        'row_role', row_role,
        'parent_field_ordinal', parent_field_ordinal,
        'administration_type', administration_type,
        'complete_dose_not_given', complete_dose_not_given,
        'dose_due', dose_due,
        'dose_due_unit', dose_due_unit,
        'dose_given', dose_given,
        'dose_given_unit', dose_given_unit,
        'will_remainder_of_dose_be_given', will_remainder_of_dose_be_given,
        'product_amount_given', product_amount_given,
        'product_unit', product_unit,
        'product_code', product_code,
        'product_description', product_description,
        'product_description_other', product_description_other,
        'prior_infusion_rate', prior_infusion_rate,
        'route', route,
        'infusion_rate', infusion_rate,
        'infusion_rate_adjustment', infusion_rate_adjustment,
        'infusion_rate_adjustment_amount', infusion_rate_adjustment_amount,
        'infusion_rate_unit', infusion_rate_unit,
        'infusion_complete', infusion_complete,
        'completion_interval', completion_interval,
        'new_iv_bag_hung', new_iv_bag_hung,
        'continued_infusion_in_other_location', continued_infusion_in_other_location,
        'restart_interval', restart_interval,
        'non_formulary_visual_verification', non_formulary_visual_verification
    ) AS payload,
    multiplicity
    FROM detail_context_counts
),
seed_memberships AS MATERIALIZED (
    SELECT d.*,
           membership.seed_source_field,
           membership.seed_exact_raw_value
    FROM detail_payloads d
    CROSS JOIN LATERAL (VALUES
        ('mimiciv_hosp.emar_detail.product_description'::text,
         d.product_description::text),
        ('mimiciv_hosp.emar_detail.product_description_other'::text,
         d.product_description_other::text)
    ) membership(seed_source_field, seed_exact_raw_value)
    WHERE membership.seed_exact_raw_value IS NOT NULL
),
seed_membership_counts AS MATERIALIZED (
    SELECT row_role, parent_field_ordinal, administration_type,
           complete_dose_not_given, dose_due, dose_due_unit, dose_given,
           dose_given_unit, will_remainder_of_dose_be_given,
           product_amount_given, product_unit, product_code,
           product_description, product_description_other, prior_infusion_rate,
           route, infusion_rate, infusion_rate_adjustment,
           infusion_rate_adjustment_amount, infusion_rate_unit,
           infusion_complete, completion_interval, new_iv_bag_hung,
           continued_infusion_in_other_location, restart_interval,
           non_formulary_visual_verification,
           seed_source_field, seed_exact_raw_value,
           count(*)::bigint AS multiplicity
    FROM seed_memberships
    GROUP BY row_role, parent_field_ordinal, administration_type,
             complete_dose_not_given, dose_due, dose_due_unit, dose_given,
             dose_given_unit, will_remainder_of_dose_be_given,
             product_amount_given, product_unit, product_code,
             product_description, product_description_other, prior_infusion_rate,
             route, infusion_rate, infusion_rate_adjustment,
             infusion_rate_adjustment_amount, infusion_rate_unit,
             infusion_complete, completion_interval, new_iv_bag_hung,
             continued_infusion_in_other_location, restart_interval,
             non_formulary_visual_verification,
             seed_source_field, seed_exact_raw_value
),
seed_membership_grouped AS MATERIALIZED (
    SELECT jsonb_build_object(
        'row_role', row_role,
        'parent_field_ordinal', parent_field_ordinal,
        'administration_type', administration_type,
        'complete_dose_not_given', complete_dose_not_given,
        'dose_due', dose_due,
        'dose_due_unit', dose_due_unit,
        'dose_given', dose_given,
        'dose_given_unit', dose_given_unit,
        'will_remainder_of_dose_be_given', will_remainder_of_dose_be_given,
        'product_amount_given', product_amount_given,
        'product_unit', product_unit,
        'product_code', product_code,
        'product_description', product_description,
        'product_description_other', product_description_other,
        'prior_infusion_rate', prior_infusion_rate,
        'route', route,
        'infusion_rate', infusion_rate,
        'infusion_rate_adjustment', infusion_rate_adjustment,
        'infusion_rate_adjustment_amount', infusion_rate_adjustment_amount,
        'infusion_rate_unit', infusion_rate_unit,
        'infusion_complete', infusion_complete,
        'completion_interval', completion_interval,
        'new_iv_bag_hung', new_iv_bag_hung,
        'continued_infusion_in_other_location', continued_infusion_in_other_location,
        'restart_interval', restart_interval,
        'non_formulary_visual_verification', non_formulary_visual_verification,
        'seed_source_field', seed_source_field,
        'seed_exact_raw_value', seed_exact_raw_value
    ) AS payload,
    multiplicity
    FROM seed_membership_counts
),
detail_head_candidates AS MATERIALIZED (
    SELECT d.*,
           h.medication AS head_medication,
           CASE WHEN h.head_row_matched IS NULL THEN 'missing'
                WHEN h.subject_id IS NULL OR d.subject_id IS NULL
                  OR h.emar_seq IS NULL OR d.emar_seq IS NULL THEN 'missing'
                WHEN h.subject_id = d.subject_id AND h.emar_seq = d.emar_seq THEN 'exact'
                ELSE 'conflict'
           END::text AS detail_head_identity_state
    FROM selected_detail d
    LEFT JOIN (
        SELECT source.*, true AS head_row_matched
        FROM mimiciv_hosp.emar source
    ) h ON h.emar_id = d.emar_id
),
detail_head_payloads AS MATERIALIZED (
    SELECT head_medication, detail_head_identity_state,
           'with_detail'::text AS detail_match_state,
           row_role, parent_field_ordinal, administration_type,
           product_description, product_description_other, product_code,
           route, dose_due_unit, dose_given_unit, product_unit,
           infusion_rate_unit
    FROM detail_head_candidates
),
detail_head_counts AS MATERIALIZED (
    SELECT head_medication, detail_head_identity_state, detail_match_state,
           row_role, parent_field_ordinal, administration_type,
           product_description, product_description_other, product_code,
           route, dose_due_unit, dose_given_unit, product_unit,
           infusion_rate_unit,
           count(*)::bigint AS multiplicity
    FROM detail_head_payloads
    GROUP BY head_medication, detail_head_identity_state, detail_match_state,
             row_role, parent_field_ordinal, administration_type,
             product_description, product_description_other, product_code,
             route, dose_due_unit, dose_given_unit, product_unit,
             infusion_rate_unit
),
detail_head_grouped AS MATERIALIZED (
    SELECT jsonb_build_object(
        'head_medication', head_medication,
        'detail_head_identity_state', detail_head_identity_state,
        'detail_match_state', detail_match_state,
        'row_role', row_role,
        'parent_field_ordinal', parent_field_ordinal,
        'administration_type', administration_type,
        'product_description', product_description,
        'product_description_other', product_description_other,
        'product_code', product_code,
        'route', route,
        'dose_due_unit', dose_due_unit,
        'dose_given_unit', dose_given_unit,
        'product_unit', product_unit,
        'infusion_rate_unit', infusion_rate_unit
    ) AS payload,
    multiplicity
    FROM detail_head_counts
),
head_detail_identity_flags AS MATERIALIZED (
    SELECT h.medication,
           h.head_multiplicity,
           coalesce(bool_or(d.detail_row_matched IS NOT NULL), false)
               AS has_detail,
           coalesce(bool_or(
               d.detail_row_matched IS NOT NULL
               AND h.subject_id IS NOT NULL AND d.subject_id IS NOT NULL
               AND h.emar_seq IS NOT NULL AND d.emar_seq IS NOT NULL
               AND h.subject_id = d.subject_id AND h.emar_seq = d.emar_seq
           ), false) AS has_exact_identity,
           coalesce(bool_or(
               d.detail_row_matched IS NOT NULL
               AND (h.subject_id IS NULL OR d.subject_id IS NULL
                    OR h.emar_seq IS NULL OR d.emar_seq IS NULL)
           ), false) AS has_missing_identity,
           coalesce(bool_or(
               d.detail_row_matched IS NOT NULL
               AND h.subject_id IS NOT NULL AND d.subject_id IS NOT NULL
               AND h.emar_seq IS NOT NULL AND d.emar_seq IS NOT NULL
               AND (h.subject_id <> d.subject_id OR h.emar_seq <> d.emar_seq)
           ), false) AS has_conflicting_identity
    FROM bucket_nonnull_medication_heads h
    LEFT JOIN (
        SELECT source.*, true AS detail_row_matched
        FROM mimiciv_hosp.emar_detail source
    ) d ON d.emar_id = h.emar_id
    GROUP BY h.subject_id, h.emar_id, h.emar_seq, h.medication,
             h.head_multiplicity
),
head_partition_payloads AS MATERIALIZED (
    SELECT medication AS head_medication,
           CASE
                 WHEN NOT has_detail THEN 'no_detail'
                 WHEN has_exact_identity AND NOT has_missing_identity
                      AND NOT has_conflicting_identity THEN 'with_detail_exact_only'
                 WHEN NOT has_exact_identity AND has_missing_identity
                      AND NOT has_conflicting_identity THEN 'with_detail_identity_missing_only'
                 WHEN NOT has_exact_identity AND NOT has_missing_identity
                      AND has_conflicting_identity THEN 'with_detail_identity_conflict_only'
                 WHEN has_exact_identity AND has_missing_identity
                      AND NOT has_conflicting_identity THEN 'with_detail_exact_and_identity_missing'
                 WHEN has_exact_identity AND NOT has_missing_identity
                      AND has_conflicting_identity THEN 'with_detail_exact_and_identity_conflict'
                 WHEN NOT has_exact_identity AND has_missing_identity
                      AND has_conflicting_identity THEN 'with_detail_identity_missing_and_conflict'
                 WHEN has_exact_identity AND has_missing_identity
                      AND has_conflicting_identity THEN 'with_detail_exact_identity_missing_and_conflict'
                 ELSE 'invalid_unreachable_identity_partition'
               END::text AS detail_match_state,
           head_multiplicity AS multiplicity
    FROM head_detail_identity_flags
),
head_partition_counts AS MATERIALIZED (
    SELECT head_medication, detail_match_state,
           sum(multiplicity)::bigint AS multiplicity
    FROM head_partition_payloads
    GROUP BY head_medication, detail_match_state
),
head_partition_grouped AS MATERIALIZED (
    SELECT jsonb_build_object(
               'head_medication', head_medication,
               'detail_match_state', detail_match_state
           ) AS payload,
           multiplicity
    FROM head_partition_counts
),
tuple_rows AS MATERIALIZED (
    SELECT 'emar_medication_head_partition'::text AS tuple_kind,
           payload, multiplicity
    FROM head_partition_grouped
),
controls(control_name, control_value) AS MATERIALIZED (
    SELECT 'bucket_output_multiplicity', coalesce(sum(multiplicity), 0)::bigint
    FROM tuple_rows
    UNION ALL
    SELECT 'emar_medication_head_partition_input_rows',
           coalesce(sum(multiplicity), 0)::bigint FROM head_partition_payloads
    UNION ALL
    SELECT 'emar_medication_head_partition_tuple_multiplicity', coalesce(sum(multiplicity), 0)::bigint
    FROM head_partition_grouped
)
SELECT 2::integer AS schema_version,
       '202b_head_partition'::text AS stage,
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
SELECT 2, '202b_head_partition', b.bucket_index, 'control', '', '', NULL::bigint,
       c.control_name, c.control_value,
       current_setting('transaction_isolation'),
       current_setting('transaction_read_only'),
       pg_current_snapshot()::text
FROM controls c CROSS JOIN bucket_config b;
