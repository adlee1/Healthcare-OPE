-- Candidate positive-event extraction, project implementation v1 (D003/D005).
-- Read only. Replace both bucket tokens with validated integer literals:
-- BUCKET_COUNT >= 1 and 0 <= BUCKET_ID < BUCKET_COUNT. Every matched head in
-- the deterministic subject bucket is returned, including excluded records.
-- A head is an administration-record anchor, not a proven infusion episode.
-- No dose_due is used. Product dose_given in mEq is summed once per head;
-- parent records are never added. Named non-potassium mEq components reject
-- the event; missing component names retain the named-head assumption and flag. mmol phosphate is NOT converted to K mEq.
-- Missing completion flags are reported, never interpreted as explicit 'No'.
-- Only indexed serum K item 50971 is used here: 52610 and other item coverage
-- remain incomplete. Pre: latest available sample in [anchor-4h, anchor].
-- Post: FIRST sample in (anchor, anchor+24h], before quality checks; a bad first
-- sample is not skipped. These are project choices, not recovered paper code.
-- No proxy infusion end is used. An output gap is measured from the anchor.
-- All patient-level output must stay in the private, ignored data directory.
WITH heads AS MATERIALIZED (
    SELECT e.emar_id, e.emar_seq, e.subject_id, e.hadm_id, e.pharmacy_id,
           e.charttime, e.storetime,
           CASE
             WHEN e.medication ~* 'losartan|penicillin|amoxicillin|clavulan|diclofenac|clorazepate'
               THEN 'other_active_drug_potassium_salt'
             WHEN e.medication ~* 'potassium[[:space:]-]+(chloride|chl)([^[:alpha:]]|$)|(^|[^[:alnum:]])kcl([^[:alnum:]]|$)'
               THEN 'potassium_chloride'
             WHEN e.medication ~* 'potassium[[:space:]-]+acetate'
               THEN 'potassium_acetate'
             WHEN e.medication ~* 'potassium[[:space:]-]+phosph|(^|[^[:alnum:]])k[ -]?phos([^[:alnum:]]|$)'
               THEN 'potassium_phosphate'
             WHEN e.medication ~* 'potassium[[:space:]-]+(citrate|bicarbonate|gluconate|iodide|permanganate|perchlorate|tartrate)'
               THEN 'other_named_potassium_salt'
             ELSE 'unresolved_potassium_name'
           END AS medication_family,
           CASE lower(trim(e.event_txt))
             WHEN 'administered' THEN 'administered'
             WHEN 'partial administered' THEN 'partial_administered'
             WHEN 'started' THEN 'started'
             WHEN 'stopped' THEN 'stopped'
             WHEN 'not given' THEN 'not_given'
             ELSE CASE WHEN nullif(trim(e.event_txt), '') IS NULL
                       THEN 'missing' ELSE 'other' END
           END AS administration_status
    FROM mimiciv_hosp.emar e
    WHERE (mod(e.subject_id, __BUCKET_COUNT__) = __BUCKET_ID__
           OR (e.subject_id IS NULL AND __BUCKET_ID__ = 0))
      AND e.medication ~* 'potassium|(^|[^[:alnum:]])k[ -]?phos([^[:alnum:]]|$)|(^|[^[:alnum:]])kcl([^[:alnum:]]|$)'
), details AS MATERIALIZED (
    SELECT h.emar_id AS head_id, h.emar_seq AS head_seq,
           h.subject_id AS head_subject, h.hadm_id AS head_hadm,
           d.subject_id, d.emar_seq, d.pharmacy_id, d.parent_field_ordinal,
           d.route, d.dose_given_unit, d.product_unit,
           CASE WHEN trim(d.dose_given) ~ '^[0-9]+([.][0-9]+)?$'
                THEN trim(d.dose_given)::numeric END AS dose_numeric,
           CASE WHEN upper(trim(d.complete_dose_not_given)) IN ('Y', 'YES')
                  THEN 'yes'
                WHEN upper(trim(d.complete_dose_not_given)) IN ('N', 'NO')
                  THEN 'no'
                WHEN nullif(trim(d.complete_dose_not_given), '') IS NULL
                  THEN 'missing' ELSE 'unrecognized' END AS incomplete_flag,
           CASE WHEN upper(trim(d.will_remainder_of_dose_be_given)) IN ('Y', 'YES')
                  THEN 'yes'
                WHEN upper(trim(d.will_remainder_of_dose_be_given)) IN ('N', 'NO')
                  THEN 'no'
                WHEN nullif(trim(d.will_remainder_of_dose_be_given), '') IS NULL
                  THEN 'missing' ELSE 'unrecognized' END AS remainder_flag,
           coalesce(d.product_description ~* 'losartan|penicillin|amoxicillin|clavulan|diclofenac|clorazepate', false)
             AS other_active_drug_component,
           coalesce(d.product_description ~* 'potassium[[:space:]-]+(chloride|chl|acetate|phosph)|(^|[^[:alnum:]])k[ -]?phos([^[:alnum:]]|$)|(^|[^[:alnum:]])kcl([^[:alnum:]]|$)', false)
             AS product_potassium_salt_name,
           nullif(trim(d.product_description), '') IS NULL AS product_name_missing,
           d.subject_id IS NOT DISTINCT FROM h.subject_id
             AND d.emar_seq IS NOT DISTINCT FROM h.emar_seq
             AND h.subject_id IS NOT NULL AND h.emar_seq IS NOT NULL AS identity_ok
    -- One join allows a single hash/sequence scan if emar_id is not indexed.
    -- Do not force an unindexed per-head LATERAL scan of emar_detail.
    FROM heads h JOIN mimiciv_hosp.emar_detail d ON d.emar_id = h.emar_id
), detail_summary AS MATERIALIZED (
    SELECT head_id,
           count(*) AS detail_rows,
           count(*) FILTER (WHERE parent_field_ordinal IS NULL) AS parent_rows,
           count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL) AS product_rows,
           count(*) FILTER (WHERE NOT identity_ok) AS identity_bad_rows,
           count(DISTINCT trim(parent_field_ordinal))
             FILTER (WHERE parent_field_ordinal IS NOT NULL) AS distinct_product_ordinals,
           count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL
             AND NOT (trim(parent_field_ordinal) ~ '^[0-9]+([.][0-9]+)?$'))
             AS unparsed_product_ordinals,
           count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL
             AND dose_numeric > 0 AND upper(trim(dose_given_unit)) = 'MEQ')
             AS positive_meq_product_rows,
           count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL
             AND upper(trim(dose_given_unit)) IN ('MMOL', 'MILLIMOLE', 'MILLIMOLES'))
             AS mmol_product_rows,
           count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL
             AND dose_numeric > 0 AND upper(trim(dose_given_unit)) = 'MEQ'
             AND NOT product_name_missing AND NOT product_potassium_salt_name)
             AS non_potassium_named_meq_product_rows,
           sum(dose_numeric) FILTER (WHERE parent_field_ordinal IS NOT NULL
             AND upper(trim(dose_given_unit)) = 'MEQ') AS recorded_product_sum_meq,
           count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL
             AND upper(trim(product_unit)) IN ('TAB', 'TABLET', 'PKT', 'PACKET'))
             AS enteral_product_rows,
           count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL
             AND other_active_drug_component) AS other_active_drug_product_rows,
           count(*) FILTER (WHERE parent_field_ordinal IS NOT NULL
             AND product_name_missing) AS missing_product_name_rows,
           count(*) FILTER (WHERE incomplete_flag = 'yes' OR remainder_flag = 'yes')
             AS affirmative_incomplete_rows,
           count(*) FILTER (WHERE incomplete_flag = 'unrecognized'
                                  OR remainder_flag = 'unrecognized') AS unknown_flag_rows,
           count(*) FILTER (WHERE parent_field_ordinal IS NULL
             AND incomplete_flag = 'no' AND remainder_flag = 'no')
             AS explicit_complete_parent_rows
    FROM details GROUP BY head_id
), pharmacy_keys AS MATERIALIZED (
    SELECT emar_id AS head_id, subject_id AS head_subject, hadm_id AS head_hadm,
           pharmacy_id
    FROM heads WHERE pharmacy_id IS NOT NULL
    UNION
    SELECT head_id, head_subject, head_hadm, pharmacy_id
    FROM details WHERE pharmacy_id IS NOT NULL AND identity_ok
), route_evidence AS MATERIALIZED (
    SELECT head_id, route, identity_ok FROM details
    UNION ALL
    SELECT k.head_id, p.route,
           p.subject_id IS NOT DISTINCT FROM k.head_subject
             AND p.hadm_id IS NOT DISTINCT FROM k.head_hadm
             AND k.head_subject IS NOT NULL AND k.head_hadm IS NOT NULL
    FROM pharmacy_keys k CROSS JOIN LATERAL (
        SELECT subject_id, hadm_id, route FROM mimiciv_hosp.pharmacy p
        WHERE p.pharmacy_id = k.pharmacy_id OFFSET 0
    ) p
    UNION ALL
    SELECT k.head_id, p.route,
           p.subject_id IS NOT DISTINCT FROM k.head_subject
             AND p.hadm_id IS NOT DISTINCT FROM k.head_hadm
             AND k.head_subject IS NOT NULL AND k.head_hadm IS NOT NULL
    FROM pharmacy_keys k CROSS JOIN LATERAL (
        SELECT subject_id, hadm_id, route FROM mimiciv_hosp.prescriptions p
        WHERE p.pharmacy_id = k.pharmacy_id OFFSET 0
    ) p
), routes AS MATERIALIZED (
    SELECT head_id, identity_ok,
           CASE WHEN nullif(trim(route), '') IS NULL THEN 'missing'
                WHEN upper(trim(route)) IN ('IV', 'INTRAVENOUS', 'IV DRIP', 'IV BOLUS', 'IVP')
                  THEN 'iv'
                WHEN upper(trim(route)) IN
                  ('PO', 'ORAL', 'NG', 'OG', 'PO/NG', 'G TUBE', 'J TUBE', 'PEG', 'ENTERAL',
                   'IM', 'SC', 'SQ', 'SUBQ', 'SUBCUTANEOUS', 'TOP', 'TOPICAL', 'PR', 'RECTAL')
                  THEN 'non_iv'
                ELSE 'unmapped' END AS route_class
    FROM route_evidence
), route_summary AS MATERIALIZED (
    SELECT head_id, count(*) FILTER (WHERE NOT identity_ok) AS identity_bad_rows,
           count(*) FILTER (WHERE identity_ok AND route_class = 'iv') AS iv_rows,
           count(*) FILTER (WHERE identity_ok AND route_class = 'non_iv') AS non_iv_rows,
           count(*) FILTER (WHERE identity_ok AND route_class = 'unmapped') AS unmapped_rows
    FROM routes GROUP BY head_id
), event_evidence AS MATERIALIZED (
    SELECT h.*,
           coalesce(d.detail_rows, 0) AS detail_rows,
           coalesce(d.parent_rows, 0) AS parent_rows,
           coalesce(d.product_rows, 0) AS product_rows,
           coalesce(d.identity_bad_rows, 0) AS detail_identity_bad_rows,
           coalesce(r.identity_bad_rows, 0) AS route_identity_bad_rows,
           coalesce(d.distinct_product_ordinals, 0) AS distinct_product_ordinals,
           coalesce(d.unparsed_product_ordinals, 0) AS unparsed_product_ordinals,
           coalesce(d.positive_meq_product_rows, 0) AS positive_meq_product_rows,
           coalesce(d.mmol_product_rows, 0) AS mmol_product_rows,
           coalesce(d.enteral_product_rows, 0) AS enteral_product_rows,
           coalesce(d.other_active_drug_product_rows, 0) AS other_active_drug_product_rows,
           coalesce(d.missing_product_name_rows, 0) AS missing_product_name_rows,
           coalesce(d.non_potassium_named_meq_product_rows, 0) AS non_potassium_named_meq_product_rows,
           CASE WHEN d.product_rows > 0
                  AND d.positive_meq_product_rows = d.product_rows
                  AND d.distinct_product_ordinals = d.product_rows
                  AND d.unparsed_product_ordinals = 0
                  AND d.non_potassium_named_meq_product_rows = 0
                THEN d.recorded_product_sum_meq END AS recorded_component_dose_meq,
           CASE WHEN coalesce(d.affirmative_incomplete_rows, 0) > 0
                  THEN 'affirmative_incomplete_or_remainder'
                WHEN coalesce(d.unknown_flag_rows, 0) > 0 THEN 'unrecognized_flags'
                WHEN d.parent_rows > 0 AND d.explicit_complete_parent_rows = d.parent_rows
                  THEN 'explicit_negative_parent_flags'
                ELSE 'unknown_missing_flags' END AS completeness_class,
           CASE WHEN coalesce(r.iv_rows, 0) > 0 AND coalesce(r.non_iv_rows, 0) > 0
                  THEN 'iv_non_iv_conflict'
                WHEN coalesce(r.unmapped_rows, 0) > 0 THEN 'unmapped_evidence'
                WHEN coalesce(r.iv_rows, 0) > 0 THEN 'iv_only'
                WHEN coalesce(r.non_iv_rows, 0) > 0 THEN 'non_iv_only'
                ELSE 'missing' END AS route_class
    FROM heads h
    LEFT JOIN detail_summary d ON d.head_id = h.emar_id
    LEFT JOIN route_summary r ON r.head_id = h.emar_id
), clinical_evidence AS MATERIALIZED (
    SELECT e.*, a.admission_rows, a.subject_match_rows,
           t.active_transfer_rows, t.active_icu_rows, t.active_named_non_icu_rows,
           t.invalid_transfer_rows,
           pre.lab_time AS pre_lab_time, pre.lab_rows AS pre_lab_rows,
           pre.lab_ids AS pre_labevent_ids, pre.valid_rows AS pre_valid_rows,
           pre.distinct_values AS pre_distinct_values, pre.lab_value AS pre_lab_value,
           pre.latest_storetime AS pre_latest_storetime,
           post.lab_time AS post_lab_time, post.lab_rows AS post_lab_rows,
           post.lab_ids AS post_labevent_ids, post.valid_rows AS post_valid_rows,
           post.distinct_values AS post_distinct_values, post.lab_value AS post_lab_value,
           post.latest_storetime AS post_latest_storetime
    FROM event_evidence e
    CROSS JOIN LATERAL (
        SELECT count(*) AS admission_rows,
               count(*) FILTER (WHERE subject_id = e.subject_id) AS subject_match_rows
        FROM mimiciv_hosp.admissions a WHERE a.hadm_id = e.hadm_id OFFSET 0
    ) a
    CROSS JOIN LATERAL (
        SELECT count(*) FILTER (WHERE intime <= e.charttime AND e.charttime < outtime)
                 AS active_transfer_rows,
               count(*) FILTER (WHERE intime <= e.charttime AND e.charttime < outtime
                 AND careunit IN ('Cardiac Vascular Intensive Care Unit (CVICU)',
                   'Coronary Care Unit (CCU)', 'Intensive Care Unit (ICU)',
                   'Medical Intensive Care Unit (MICU)',
                   'Medical/Surgical Intensive Care Unit (MICU/SICU)',
                   'Neuro Surgical Intensive Care Unit (Neuro SICU)',
                   'Surgical Intensive Care Unit (SICU)', 'Trauma SICU (TSICU)')) AS active_icu_rows,
               count(*) FILTER (WHERE intime <= e.charttime AND e.charttime < outtime
                 AND nullif(trim(careunit), '') IS NOT NULL AND upper(trim(careunit)) <> 'UNKNOWN'
                 AND careunit NOT IN ('Cardiac Vascular Intensive Care Unit (CVICU)',
                   'Coronary Care Unit (CCU)', 'Intensive Care Unit (ICU)',
                   'Medical Intensive Care Unit (MICU)',
                   'Medical/Surgical Intensive Care Unit (MICU/SICU)',
                   'Neuro Surgical Intensive Care Unit (Neuro SICU)',
                   'Surgical Intensive Care Unit (SICU)', 'Trauma SICU (TSICU)'))
                 AS active_named_non_icu_rows,
               count(*) FILTER (WHERE
                 (intime IS NULL AND (outtime IS NULL OR e.charttime < outtime))
                 OR (outtime IS NULL AND intime <= e.charttime)
                 OR (outtime <= intime AND e.charttime BETWEEN outtime AND intime))
                 AS invalid_transfer_rows
        FROM mimiciv_hosp.transfers t
        WHERE t.subject_id = e.subject_id AND t.hadm_id = e.hadm_id
          AND t.eventtype IS DISTINCT FROM 'discharge' OFFSET 0
    ) t
    -- Availability, not value quality, selects the pre timestamp.
    CROSS JOIN LATERAL (
        SELECT max(charttime) AS lab_time FROM mimiciv_hosp.labevents l
        WHERE l.subject_id = e.subject_id AND l.hadm_id = e.hadm_id AND l.itemid = 50971
          AND l.charttime >= e.charttime - interval '4 hours' AND l.charttime <= e.charttime
          AND l.storetime <= e.charttime OFFSET 0
    ) pre_time
    CROSS JOIN LATERAL (
        SELECT min(charttime) AS lab_time, count(*) AS lab_rows,
               jsonb_agg(labevent_id ORDER BY labevent_id) AS lab_ids,
               count(*) FILTER (WHERE valuenum > 0
                 AND valuenum::text NOT IN ('NaN', 'Infinity', '-Infinity')
                 AND upper(trim(valueuom)) IN ('MEQ/L', 'MMOL/L')
                 AND storetime >= charttime AND storetime <= e.charttime) AS valid_rows,
               count(DISTINCT valuenum) AS distinct_values,
               min(valuenum) AS lab_value, max(storetime) AS latest_storetime
        FROM mimiciv_hosp.labevents l
        WHERE l.subject_id = e.subject_id AND l.hadm_id = e.hadm_id AND l.itemid = 50971
          AND l.charttime = pre_time.lab_time AND l.storetime <= e.charttime OFFSET 0
    ) pre
    CROSS JOIN LATERAL (
        SELECT min(charttime) AS lab_time FROM mimiciv_hosp.labevents l
        WHERE l.subject_id = e.subject_id AND l.hadm_id = e.hadm_id AND l.itemid = 50971
          AND l.charttime > e.charttime AND l.charttime <= e.charttime + interval '24 hours'
        OFFSET 0
    ) post_time
    CROSS JOIN LATERAL (
        SELECT min(charttime) AS lab_time, count(*) AS lab_rows,
               jsonb_agg(labevent_id ORDER BY labevent_id) AS lab_ids,
               count(*) FILTER (WHERE valuenum > 0
                 AND valuenum::text NOT IN ('NaN', 'Infinity', '-Infinity')
                 AND upper(trim(valueuom)) IN ('MEQ/L', 'MMOL/L')
                 AND (storetime IS NULL OR storetime >= charttime)) AS valid_rows,
               count(DISTINCT valuenum) AS distinct_values,
               min(valuenum) AS lab_value, max(storetime) AS latest_storetime
        FROM mimiciv_hosp.labevents l
        WHERE l.subject_id = e.subject_id AND l.hadm_id = e.hadm_id AND l.itemid = 50971
          AND l.charttime = post_time.lab_time OFFSET 0
    ) post
), classified AS MATERIALIZED (
    SELECT *,
           CASE WHEN invalid_transfer_rows > 0 THEN 'invalid_transfer_evidence'
                WHEN active_transfer_rows = 0 THEN 'no_active_transfer'
                WHEN active_icu_rows > 0 THEN 'icu'
                WHEN active_transfer_rows > 1 THEN 'overlapping_transfers'
                WHEN active_named_non_icu_rows = 1 THEN 'non_icu'
                ELSE 'unknown_careunit' END AS anchor_location_class,
           CASE WHEN pre_lab_rows = 0 THEN 'missing'
                WHEN pre_valid_rows <> pre_lab_rows THEN 'invalid_value_unit_or_time'
                WHEN pre_distinct_values <> 1 THEN 'conflicting_values_at_timestamp'
                ELSE 'usable' END AS pre_lab_class,
           CASE WHEN post_lab_rows = 0 THEN 'missing_within_24h'
                WHEN post_valid_rows <> post_lab_rows THEN 'invalid_value_unit_or_time'
                WHEN post_distinct_values <> 1 THEN 'conflicting_values_at_timestamp'
                ELSE 'usable' END AS post_lab_class
    FROM clinical_evidence
), gated AS MATERIALIZED (
    SELECT *, CASE
      WHEN subject_id IS NULL OR hadm_id IS NULL OR emar_id IS NULL OR emar_seq IS NULL
        OR admission_rows <> 1 OR subject_match_rows <> 1 THEN 'head_admission_identity'
      WHEN charttime IS NULL OR storetime < charttime THEN 'head_time'
      WHEN medication_family NOT IN ('potassium_chloride', 'potassium_acetate', 'potassium_phosphate')
        THEN 'unsupported_medication_family'
      WHEN administration_status <> 'administered' THEN 'not_administered_status'
      WHEN detail_identity_bad_rows > 0 OR route_identity_bad_rows > 0 THEN 'linked_identity_conflict'
      WHEN route_class <> 'iv_only' THEN 'non_iv_unknown_or_conflicting_route'
      WHEN enteral_product_rows > 0 OR other_active_drug_product_rows > 0
        OR non_potassium_named_meq_product_rows > 0 THEN 'product_identity_or_form_conflict'
      WHEN completeness_class IN ('affirmative_incomplete_or_remainder', 'unrecognized_flags')
        THEN 'incomplete_or_unrecognized_completion'
      WHEN product_rows = 0 THEN 'no_recorded_product_components'
      WHEN distinct_product_ordinals <> product_rows OR unparsed_product_ordinals > 0
        THEN 'ambiguous_product_structure'
      WHEN positive_meq_product_rows <> product_rows THEN 'component_dose_not_positive_meq'
      WHEN recorded_component_dose_meq NOT IN (10, 20, 40) THEN 'outside_positive_paper_action_set'
      WHEN anchor_location_class <> 'non_icu' THEN 'not_confirmed_non_icu_at_anchor'
      WHEN pre_lab_class <> 'usable' THEN 'pre_lab_unusable'
      WHEN post_lab_class <> 'usable' THEN 'first_post_lab_unusable'
      ELSE NULL END AS exclusion_reason
    FROM classified
)
SELECT 'potassium_positive_candidate_v1'::text AS extraction_version,
       emar_id, emar_seq, subject_id, hadm_id, pharmacy_id,
       charttime AS anchor_time, storetime AS emar_storetime,
       medication_family, administration_status, route_class, completeness_class,
       detail_rows, parent_rows, product_rows, distinct_product_ordinals,
       detail_identity_bad_rows, route_identity_bad_rows, missing_product_name_rows,
       non_potassium_named_meq_product_rows,
       mmol_product_rows, recorded_component_dose_meq,
       CASE WHEN recorded_component_dose_meq IN (10, 20, 40)
            THEN recorded_component_dose_meq::integer END AS positive_action_value,
       anchor_location_class, active_transfer_rows, active_icu_rows,
       pre_lab_class, pre_labevent_ids, pre_lab_rows, pre_lab_time, pre_latest_storetime,
       CASE WHEN pre_lab_class = 'usable' THEN pre_lab_value END AS pre_potassium_meq_l,
       post_lab_class, post_labevent_ids, post_lab_rows, post_lab_time, post_latest_storetime,
       CASE WHEN post_lab_class = 'usable' THEN post_lab_value END AS post_potassium_meq_l,
       extract(epoch FROM (post_lab_time - charttime)) / 3600.0 AS post_gap_from_anchor_hours,
       '50971_only_52610_not_covered'::text AS potassium_lab_scope,
       exclusion_reason, exclusion_reason IS NULL AS eligible_positive_candidate
FROM gated
ORDER BY subject_id, hadm_id, charttime, emar_id, emar_seq;
