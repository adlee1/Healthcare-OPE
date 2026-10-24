-- PRIVATE feature rows. Supply decision-key VALUES input with validated unique
-- (event_id text, subject_id int, hadm_id int, decision_time timestamp) VALUES.
-- Paper Appendix A lists the five administered-medication features but does not
-- disclose encoding. Project choice: observed-administration binary in [t-4h,t].
-- 1 = confirmed recorded exposure; NULL = matched potential exposure unresolved;
-- 0 = neither detected by these head/product rules, not proof of non-exposure.
-- Future-storetime records do not affect values or missingness. Missing/reversed
-- times may produce NULL but never 1. No carry-in before t-4h is reconstructed.
-- One scoped eMAR scan, then ONE complete detail join; no per-key detail scans.
-- Positive dose_given (never bag/planned quantity) supports Administered.
-- Started/Delayed Started/Restarted/Confirmed need one parent with positive rate.
-- Mixed products may identify several ingredients, including a saline/D5 carrier;
-- no dose or rate is integrated, summed or compared across unlike units.
-- Product description falls back to product_description_other when empty.
-- Generic drug names only; unknown brands/local codes and nameless products are
-- outside detection. Explicit fluid concentrations, NS/D5 aliases are recognized.
-- Half-NS is not 0.9% saline. Flush/local/inhaled forms and insulin devices are
-- excluded. Other routes, including subcutaneous insulin, are retained.
WITH requested(event_id, subject_id, hadm_id, decision_time) AS (
    VALUES __DECISION_KEYS__
), keys AS MATERIALIZED (
    SELECT DISTINCT event_id::text AS event_id, subject_id::integer AS subject_id,
           hadm_id::integer AS hadm_id, decision_time::timestamp AS decision_time
    FROM requested
), specs(code, match_pattern, broad_pattern) AS (
    VALUES
      ('administered_nacl_09',
       '(^|[^0-9.])0[.]9[[:space:]]*%[[:space:]-]*(sodium[[:space:]-]+chloride|nacl)|(sodium[[:space:]-]+chloride|nacl)[[:space:]-]*0[.]9[[:space:]]*%|normal[[:space:]]+saline|(^|[^[:alnum:]])(ns|d5ns)([^[:alnum:]]|$)',
       'sodium[[:space:]-]+chloride|(^|[^[:alnum:]])(nacl|saline)([^[:alnum:]]|$)'),
      ('administered_dextrose_5',
       '(^|[^0-9.])5[[:space:]]*%[[:space:]-]*dextrose|dextrose[[:space:]-]*5[[:space:]]*%|(^|[^[:alnum:]])d5(w|ns|lr|[[:space:]]|$)',
       'dextrose'),
      ('administered_propofol', '(^|[^[:alnum:]])propofol([^[:alnum:]]|$)', 'propofol'),
      ('administered_norepinephrine', '(^|[^[:alnum:]])norepinephrine([^[:alnum:]]|$)', 'norepinephrine'),
      ('administered_insulin', '(^|[^[:alnum:]])insulin([^[:alnum:]]|$)', 'insulin')
), head_scope AS MATERIALIZED (
    SELECT e.emar_id, e.emar_seq, e.subject_id, e.hadm_id, e.pharmacy_id,
           e.charttime, e.storetime, e.event_txt,
           lower(regexp_replace(trim(coalesce(e.medication,'')), '[[:space:]]+', ' ', 'g')) AS head_name
    FROM mimiciv_hosp.emar e
    WHERE e.hadm_id IN (SELECT hadm_id FROM keys)
       OR (e.hadm_id IS NULL AND e.subject_id IN (SELECT subject_id FROM keys))
), event_windows AS MATERIALIZED (
    SELECT k.event_id, k.decision_time, e.*,
           coalesce(e.subject_id = k.subject_id AND e.hadm_id = k.hadm_id, false) AS head_identity_ok,
           coalesce(isfinite(e.charttime) AND isfinite(e.storetime)
               AND e.storetime >= e.charttime AND e.storetime <= k.decision_time, false) AS time_ok
    FROM head_scope e JOIN keys k
      ON e.hadm_id = k.hadm_id OR (e.hadm_id IS NULL AND e.subject_id = k.subject_id)
    WHERE (e.storetime IS NULL OR e.storetime <= k.decision_time)
      AND ((e.charttime >= k.decision_time - interval '4 hours' AND e.charttime <= k.decision_time)
           OR ((e.charttime IS NULL OR NOT isfinite(e.charttime))
               AND (e.storetime IS NULL OR e.storetime >= k.decision_time - interval '4 hours')))
), unique_heads AS MATERIALIZED (
    SELECT DISTINCT emar_id, emar_seq, subject_id, pharmacy_id, head_name
    FROM event_windows
), details AS MATERIALIZED (
    SELECT h.*, d.emar_id AS detail_id, d.parent_field_ordinal,
           lower(regexp_replace(trim(coalesce(nullif(trim(d.product_description),''),d.product_description_other,'')), '[[:space:]]+', ' ', 'g')) AS product_name,
           (d.emar_id IS NOT NULL AND (d.subject_id IS DISTINCT FROM h.subject_id
             OR d.emar_seq IS DISTINCT FROM h.emar_seq
             OR (d.pharmacy_id IS NOT NULL AND d.pharmacy_id <> h.pharmacy_id))) AS detail_identity_bad,
           CASE WHEN length(trim(d.dose_given)) BETWEEN 1 AND 64
                     AND trim(d.dose_given) ~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)$'
                THEN trim(d.dose_given)::numeric END AS dose_number,
           upper(trim(d.dose_given_unit)) IN ('MG','MCG','G','ML','L','UNIT','UNITS','U','MEQ','MMOL') AS dose_unit_known,
           CASE WHEN length(trim(d.infusion_rate)) BETWEEN 1 AND 64
                     AND trim(d.infusion_rate) ~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)$'
                THEN trim(d.infusion_rate)::numeric END AS rate_number,
           upper(replace(trim(d.infusion_rate_unit),' ','')) IN
               ('ML/HR','ML/H','ML/MIN','MG/HR','MG/H','MG/MIN','MCG/HR','MCG/H','MCG/MIN',
                'MCG/KG/MIN','MCG/KG/HR','MG/KG/MIN','MG/KG/HR',
                'UNIT/HR','UNITS/HR','UNITS/H','UNITS/MIN','U/HR','U/H') AS rate_unit_known
    FROM unique_heads h LEFT JOIN mimiciv_hosp.emar_detail d ON d.emar_id = h.emar_id
), named AS MATERIALIZED (
    SELECT d.*, f.code,
           head_name ~ '(flush|irrigation|nasal|ophthalmic|inhalation|inhaled|nebuliz|topical|insulin[[:space:]]+syringe|pump[[:space:]]+controller|needle)' AS head_excluded,
           product_name ~ '(flush|irrigation|nasal|ophthalmic|inhalation|inhaled|nebuliz|topical|insulin[[:space:]]+syringe|pump[[:space:]]+controller|needle)' AS product_excluded,
           head_name ~ f.match_pattern
               AND NOT (f.code = 'administered_nacl_09' AND head_name ~ '(1/2|half)[[:space:]]*(ns|normal[[:space:]]+saline)') AS head_match,
           product_name ~ f.match_pattern
               AND NOT (f.code = 'administered_nacl_09' AND product_name ~ '(1/2|half)[[:space:]]*(ns|normal[[:space:]]+saline)') AS product_match,
           head_name ~ f.broad_pattern AND head_name !~ f.match_pattern
               AND head_name !~ '([0-9]+([.][0-9]+)?[[:space:]]*%|(^|[^[:alnum:]])d[0-9]+|(1/2|half)[[:space:]]*(ns|normal[[:space:]]+saline))' AS head_ambiguous,
           product_name ~ f.broad_pattern AND product_name !~ f.match_pattern
               AND product_name !~ '([0-9]+([.][0-9]+)?[[:space:]]*%|(^|[^[:alnum:]])d[0-9]+|(1/2|half)[[:space:]]*(ns|normal[[:space:]]+saline))' AS product_ambiguous
    FROM details d CROSS JOIN specs f
), head_features AS MATERIALIZED (
    SELECT emar_id, code, bool_or(head_excluded) AS head_excluded,
           bool_or(head_match) AS head_match, bool_or(head_ambiguous) AS head_ambiguous,
           count(detail_id) FILTER (WHERE parent_field_ordinal IS NULL) AS parent_rows,
           bool_or(detail_identity_bad) AS detail_identity_bad,
           count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL AND product_name !~ '^_*$') AS named_products,
           count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL AND product_match AND NOT product_excluded) AS matching_products,
           bool_or(product_ambiguous AND NOT product_excluded) AS product_ambiguous,
           count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL AND NOT product_excluded
               AND (product_match OR (product_name ~ '^_*$' AND head_match))
               AND dose_number > 0 AND dose_unit_known) AS positive_matching_products,
           count(*) FILTER (WHERE parent_field_ordinal IS NULL AND detail_id IS NOT NULL
               AND dose_number > 0 AND dose_unit_known) AS positive_parent_doses,
           count(*) FILTER (WHERE parent_field_ordinal IS NULL AND detail_id IS NOT NULL
               AND rate_number > 0 AND rate_unit_known) AS positive_parent_rates
    FROM named GROUP BY emar_id, code
), signals AS MATERIALIZED (
    SELECT w.event_id, w.emar_id, w.charttime, w.storetime, f.code,
           CASE WHEN NOT w.head_identity_ok OR f.detail_identity_bad THEN 'identity_unknown'
                WHEN NOT w.time_ok THEN 'time_unknown'
                WHEN w.event_txt = 'Administered'
                     AND (f.positive_matching_products > 0
                          OR (f.head_match AND f.parent_rows = 1 AND f.positive_parent_doses = 1
                              AND (f.named_products = 0 OR f.matching_products > 0))) THEN 'confirmed'
                WHEN w.event_txt IN ('Started','Delayed Started','Restarted','Confirmed')
                     AND f.parent_rows = 1 AND f.positive_parent_rates = 1
                     AND (f.matching_products > 0 OR (f.head_match AND f.named_products = 0)) THEN 'confirmed'
                ELSE 'name_amount_or_status_unknown' END AS signal
    FROM event_windows w JOIN head_features f ON f.emar_id = w.emar_id
    WHERE NOT f.head_excluded
      AND (f.head_match OR f.matching_products > 0 OR f.product_ambiguous
           OR (f.head_ambiguous AND f.named_products = 0))
      AND (w.event_txt IS NULL OR w.event_txt NOT IN ('Not Given','Not Administered','Not Started'))
), reduced AS MATERIALIZED (
    SELECT event_id, code,
           count(*) FILTER (WHERE signal = 'confirmed') AS confirmed_count,
           count(*) FILTER (WHERE signal <> 'confirmed') AS uncertain_count,
           array_agg(emar_id ORDER BY emar_id) FILTER (WHERE signal = 'confirmed') AS confirmed_emar_ids,
           array_agg(emar_id ORDER BY emar_id) FILTER (WHERE signal <> 'confirmed') AS uncertain_emar_ids,
           array_agg(DISTINCT signal ORDER BY signal) FILTER (WHERE signal <> 'confirmed') AS uncertainty_kinds,
           max(charttime) FILTER (WHERE signal = 'confirmed') AS latest_confirmed_charttime,
           max(storetime) FILTER (WHERE signal = 'confirmed') AS latest_confirmed_storetime
    FROM signals GROUP BY event_id, code
), grid AS (
    SELECT k.*, s.code, r.confirmed_count, r.uncertain_count,
           r.confirmed_emar_ids, r.uncertain_emar_ids, r.uncertainty_kinds,
           r.latest_confirmed_charttime, r.latest_confirmed_storetime,
           CASE WHEN coalesce(r.confirmed_count,0) > 0 THEN 1
                WHEN coalesce(r.uncertain_count,0) > 0 THEN NULL::integer
                ELSE 0 END AS feature_value
    FROM keys k CROSS JOIN specs s LEFT JOIN reduced r ON r.event_id = k.event_id AND r.code = s.code
)
SELECT event_id, subject_id, hadm_id, decision_time,
       max(feature_value) FILTER (WHERE code = 'administered_nacl_09') AS administered_nacl_09,
       max(feature_value) FILTER (WHERE code = 'administered_dextrose_5') AS administered_dextrose_5,
       max(feature_value) FILTER (WHERE code = 'administered_propofol') AS administered_propofol,
       max(feature_value) FILTER (WHERE code = 'administered_norepinephrine') AS administered_norepinephrine,
       max(feature_value) FILTER (WHERE code = 'administered_insulin') AS administered_insulin,
       jsonb_object_agg(code, jsonb_build_object(
           'value',feature_value,'confirmed_count',coalesce(confirmed_count,0),
           'uncertain_count',coalesce(uncertain_count,0),
           'confirmed_emar_ids',coalesce(confirmed_emar_ids,ARRAY[]::text[]),
           'uncertain_emar_ids',coalesce(uncertain_emar_ids,ARRAY[]::text[]),
           'uncertainty_kinds',coalesce(uncertainty_kinds,ARRAY[]::text[]),
           'latest_confirmed_charttime',latest_confirmed_charttime,
           'latest_confirmed_storetime',latest_confirmed_storetime)) AS medication_evidence,
       'head_and_product_observed_admin_binary_v1'::text AS medication_encoding
FROM grid GROUP BY event_id, subject_id, hadm_id, decision_time
ORDER BY event_id;
