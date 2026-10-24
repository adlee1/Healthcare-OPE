-- Query 200 event-evidence shard.  The runner replaces the nine discovery
-- fragments and the two integer bucket parameters with validated values.  Head
-- and order-head candidates are assigned from the eMAR head subject.  Selected
-- detail rows are provisionally assigned from their own subject so the indexed
-- detail scan can be partitioned before the eMAR join; an explicit zero-violation
-- guard below proves that this assignment is identical to the eMAR head subject
-- assignment.  This is an aggregate-only SELECT; it emits no identifiers.
-- Merge contract: for the four event sections and two admission diagnostics,
-- group on (section,
-- dimensions), treat a missing group as zero, sum records and numeric event
-- counters, and require nonnumeric counters to be identical.  In
-- event_conservation, query199_prior_real_audit_reference_heads is also an
-- identical constant, not a sum.  closure_bucket_metadata is one control row
-- per bucket: require a complete 0..bucket_count-1 set, one common bucket_count,
-- zero assignment/detail-identity/duplicate violations, a complete admission
-- link-status partition, and true
-- primary-key guards.
-- Its candidate/subject/logical-admission/query199/null-subject and admission
-- anomaly counts are additive because the shard key is subject_id;
-- source dictionary and full-component order counts must be identical.
WITH
bucket_config AS MATERIALIZED (
    SELECT bucket_index,bucket_count,
           bucket_count>0 AND bucket_index>=0 AND bucket_index<bucket_count
             AS bucket_parameters_valid
    FROM (VALUES (__BUCKET_INDEX__::integer,__BUCKET_COUNT__::integer))
         v(bucket_index,bucket_count)
),
discovery_metadata(non_null_emar_medication_names,non_null_detail_product_descriptions,non_null_pharmacy_medication_names,identity_consistent_lexical_detail_product_rows,identity_consistent_lexical_detail_events) AS (
    VALUES (__DISCOVERY_COUNTS__)
),
indexed_lexical_names(source_type,raw_name) AS MATERIALIZED (
__INDEXED_LEXICAL_NAMES__
),
prescription_lexical_names(raw_name) AS MATERIALIZED (
__PRESCRIPTION_NAMES__
),
discovered_seed_product_codes(product_code,lexical_detail_rows,lexical_emar_events,lexical_descriptions) AS MATERIALIZED (
__SEED_PRODUCT_CODES__
),
detail_code_name_flags(raw_name,focal_kcl_hint,phosphate_or_acetate_hint,other_potassium_salt_hint,active_drug_hint,unresolved_hint) AS MATERIALIZED (
__DETAIL_CODE_NAME_FLAGS__
),
emar_lexical_name_flags AS MATERIALIZED (
    SELECT raw_name,
           raw_name ~* 'potassium|(^|[^[:alnum:]])kcl([^[:alnum:]]|$)'
             AS query199_head_scope
    FROM indexed_lexical_names
    WHERE source_type='emar_medication'
),
prescription_lexical_rows AS MATERIALIZED (
    SELECT p.pharmacy_id,p.subject_id,p.hadm_id,p.poe_id,p.drug
    FROM mimiciv_hosp.prescriptions p
    WHERE p.drug = ANY (__PRESCRIPTION_NAME_ARRAY__)
),
direct_rows AS MATERIALIZED (
    SELECT e.emar_id,e.subject_id,e.hadm_id,e.emar_seq,e.pharmacy_id,e.poe_id,
           e.medication,e.event_txt,n.query199_head_scope
    FROM mimiciv_hosp.emar e
    JOIN emar_lexical_name_flags n ON n.raw_name=e.medication
    CROSS JOIN bucket_config b
    WHERE e.medication = ANY (__EMAR_NAME_ARRAY__)
      AND CASE WHEN b.bucket_parameters_valid THEN
            CASE WHEN e.subject_id IS NULL THEN 0::bigint
                 ELSE ((hashint8extended(e.subject_id::bigint,0)
                         % b.bucket_count::bigint + b.bucket_count::bigint)
                        % b.bucket_count::bigint)
            END = b.bucket_index::bigint
          ELSE false END
),
seed_product_codes AS MATERIALIZED (
    -- Stage A established these seeds using the full detail-event identity gate
    -- in this same snapshot.  Do not repeat that expensive eMAR join in stage B.
    SELECT product_code,lexical_detail_rows,lexical_emar_events,lexical_descriptions
    FROM discovered_seed_product_codes
),
selected_detail_rows AS MATERIALIZED (
    -- Constant arrays let PostgreSQL combine the description and local-code
    -- indexes into one BitmapOr heap visit.  VALUES/decode remains only for
    -- private dictionary reporting because it is not constant-foldable.
    SELECT matched.*
    FROM (
        SELECT d.emar_id,d.subject_id,d.emar_seq,d.pharmacy_id,
               d.product_code,d.product_description,
               d.product_description = ANY (__DETAIL_NAME_ARRAY__) AS text_match,
               d.product_code = ANY (__SEED_PRODUCT_CODE_ARRAY__) AS code_match
        FROM mimiciv_hosp.emar_detail d
        CROSS JOIN bucket_config b
        WHERE d.parent_field_ordinal IS NOT NULL
          AND CASE WHEN b.bucket_parameters_valid THEN
                CASE WHEN d.subject_id IS NULL THEN 0::bigint
                     ELSE ((hashint8extended(d.subject_id::bigint,0)
                             % b.bucket_count::bigint + b.bucket_count::bigint)
                            % b.bucket_count::bigint)
                END = b.bucket_index::bigint
              ELSE false END
    ) matched
    WHERE matched.text_match OR matched.code_match
),
detail_text_rows_raw AS MATERIALIZED (
    SELECT emar_id,subject_id,emar_seq,pharmacy_id,
           product_code,product_description
    FROM selected_detail_rows
    WHERE text_match
),
detail_code_rows AS MATERIALIZED (
    SELECT d.emar_id,d.subject_id,d.emar_seq,
           d.product_code,d.product_description,count(*) AS source_rows
    FROM selected_detail_rows d
    WHERE d.code_match
    GROUP BY d.emar_id,d.subject_id,d.emar_seq,
             d.product_code,d.product_description
),
pharmacy_name_rows AS MATERIALIZED (
    SELECT p.pharmacy_id,p.subject_id,p.hadm_id,p.poe_id,p.medication
    FROM mimiciv_hosp.pharmacy p
    WHERE p.medication = ANY (__PHARMACY_NAME_ARRAY__)
),
source_names(source_type,evidence_path,raw_name) AS MATERIALIZED (
    -- Stage A already proved these exact dictionaries unique in this snapshot;
    -- do not rescan and DISTINCT the large retrieved fact CTEs just to rebuild
    -- the same name map.  The code closure alone can introduce new/NULL names.
    SELECT source_type,
           CASE source_type
             WHEN 'emar_medication' THEN 'head_text'
             WHEN 'detail_product_description' THEN 'detail_text_seed'
             WHEN 'pharmacy_medication' THEN 'pharmacy_name'
           END,
           raw_name
    FROM indexed_lexical_names
    UNION ALL
    SELECT 'prescription_drug','prescription_name',raw_name
    FROM prescription_lexical_names
    UNION ALL
    SELECT DISTINCT 'detail_product_description','detail_local_code_closure',
                    product_description::text
    FROM detail_code_rows
),
name_flags AS MATERIALIZED (
    SELECT source_type,evidence_path,raw_name,
           lower(regexp_replace(trim(raw_name),'[[:space:]]+',' ','g'))
             AS normalized_name,
           raw_name ~* 'potassium[[:space:]-]+(chloride|chl)([^[:alpha:]]|$)|(^|[^[:alnum:]])kcl([^[:alnum:]]|$)'
             AS focal_kcl_hint,
           raw_name ~* 'potassium[[:space:]-]+phosph|(^|[^[:alnum:]])k[ -]?phos([^[:alnum:]]|$)'
             AS phosphate_hint,
           raw_name ~* 'potassium[[:space:]-]+acetate' AS acetate_hint,
           raw_name ~* 'potassium[[:space:]-]+(citrate|bicarbonate|gluconate|iodide|permanganate|perchlorate|tartrate)'
             AS other_potassium_salt_hint,
           raw_name ~* 'losartan|penicillin|amoxicillin|clavulan|diclofenac|clorazepate'
             AS non_repletion_active_drug_hint
    FROM source_names
),
classified_names AS MATERIALIZED (
    SELECT *,
           focal_kcl_hint OR phosphate_hint OR acetate_hint
             AS broader_repletion_hint,
           NOT coalesce(focal_kcl_hint,false)
             AND NOT coalesce(phosphate_hint,false)
             AND NOT coalesce(acetate_hint,false)
             AND NOT coalesce(other_potassium_salt_hint,false)
             AND NOT coalesce(non_repletion_active_drug_hint,false)
             AS unresolved_name_hint,
           CASE
             WHEN non_repletion_active_drug_hint
               THEN 'non_repletion_active_drug_hint'
             WHEN focal_kcl_hint THEN 'focal_kcl_repletion_hint'
             WHEN phosphate_hint OR acetate_hint
               THEN 'broader_phosphate_or_acetate_repletion_hint'
             WHEN other_potassium_salt_hint
               THEN 'other_potassium_salt_review'
             ELSE 'unresolved_name_or_local_code_review'
           END AS source_review_stratum
    FROM name_flags
),
detail_code_dictionary_guard AS MATERIALIZED (
    -- The global-detail stage classified this same one-hop dictionary in the
    -- current snapshot.  Reclassification remains local to preserve the fast
    -- bucket plan, while this small distinct-name join proves exact agreement.
    SELECT count(*) FILTER (
             WHERE f.unresolved_hint IS NULL
                OR coalesce(n.focal_kcl_hint,false)
                     IS DISTINCT FROM f.focal_kcl_hint
                OR (coalesce(n.phosphate_hint,false)
                    OR coalesce(n.acetate_hint,false))
                     IS DISTINCT FROM f.phosphate_or_acetate_hint
                OR coalesce(n.other_potassium_salt_hint,false)
                     IS DISTINCT FROM f.other_potassium_salt_hint
                OR coalesce(n.non_repletion_active_drug_hint,false)
                     IS DISTINCT FROM f.active_drug_hint
                OR coalesce(n.unresolved_name_hint,true)
                     IS DISTINCT FROM f.unresolved_hint)
             AS detail_code_dictionary_miss_names
    FROM classified_names n
    LEFT JOIN detail_code_name_flags f
      ON f.raw_name IS NOT DISTINCT FROM n.raw_name
    WHERE n.source_type='detail_product_description'
      AND n.evidence_path='detail_local_code_closure'
),
classified_detail_code_rows AS MATERIALIZED (
    -- Use ordinary equality for non-NULL descriptions so PostgreSQL can hash
    -- this million-row closure join.  A NULL description has exactly the
    -- unresolved classification produced by classified_names for its NULL row.
    SELECT d.*,
           coalesce(n.focal_kcl_hint,false) AS focal_kcl_hint,
           coalesce(n.phosphate_hint,false)
             OR coalesce(n.acetate_hint,false) AS phosphate_or_acetate_hint,
           coalesce(n.other_potassium_salt_hint,false)
             AS other_potassium_salt_hint,
           coalesce(n.non_repletion_active_drug_hint,false) AS active_drug_hint,
           coalesce(n.unresolved_name_hint,true) AS unresolved_hint,
           coalesce(n.source_review_stratum,
                    'unresolved_name_or_local_code_review') AS source_review_stratum
    FROM detail_code_rows d
    LEFT JOIN classified_names n
      ON n.source_type='detail_product_description'
     AND n.evidence_path='detail_local_code_closure'
     AND n.raw_name=d.product_description
),
direct_by_event AS MATERIALIZED (
    -- eMAR has one row per emar_id and the exact head-name dictionary is
    -- unique, so this path is already one-to-one and needs no large GROUP BY.
    SELECT d.emar_id,1::bigint AS source_rows,d.query199_head_scope,
           n.focal_kcl_hint,
           n.phosphate_hint OR n.acetate_hint AS phosphate_or_acetate_hint,
           n.other_potassium_salt_hint,
           n.non_repletion_active_drug_hint AS active_drug_hint,
           n.unresolved_name_hint AS unresolved_hint
    FROM direct_rows d
    JOIN classified_names n
      ON n.source_type='emar_medication' AND n.evidence_path='head_text'
     AND n.raw_name=d.medication
),
detail_text_by_event AS MATERIALIZED (
    SELECT d.emar_id,count(*) AS source_rows,
           count(DISTINCT d.subject_id) AS source_subjects,
           min(d.subject_id) AS source_subject,
           count(*) FILTER (WHERE d.subject_id IS NULL) AS missing_subject_rows,
           count(DISTINCT d.emar_seq) AS source_sequences,
           min(d.emar_seq) AS source_sequence,
           count(*) FILTER (WHERE d.emar_seq IS NULL) AS missing_sequence_rows,
           bool_or(n.focal_kcl_hint) AS focal_kcl_hint,
           bool_or(n.phosphate_hint OR n.acetate_hint) AS phosphate_or_acetate_hint,
           bool_or(n.other_potassium_salt_hint) AS other_potassium_salt_hint,
           bool_or(n.non_repletion_active_drug_hint) AS active_drug_hint,
           bool_or(n.unresolved_name_hint) AS unresolved_hint
    FROM detail_text_rows_raw d
    JOIN classified_names n
      ON n.source_type='detail_product_description'
     AND n.evidence_path='detail_text_seed'
     AND n.raw_name=d.product_description
    GROUP BY d.emar_id
),
detail_code_by_event AS MATERIALIZED (
    SELECT d.emar_id,sum(d.source_rows) AS source_rows,
           count(DISTINCT d.subject_id) AS source_subjects,
           min(d.subject_id) AS source_subject,
           count(*) FILTER (WHERE d.subject_id IS NULL) AS missing_subject_rows,
           count(DISTINCT d.emar_seq) AS source_sequences,
           min(d.emar_seq) AS source_sequence,
           count(*) FILTER (WHERE d.emar_seq IS NULL) AS missing_sequence_rows,
           bool_or(d.focal_kcl_hint) AS focal_kcl_hint,
           bool_or(d.phosphate_or_acetate_hint) AS phosphate_or_acetate_hint,
           bool_or(d.other_potassium_salt_hint) AS other_potassium_salt_hint,
           bool_or(d.active_drug_hint) AS active_drug_hint,
           bool_or(d.unresolved_hint) AS unresolved_hint
    FROM classified_detail_code_rows d
    GROUP BY d.emar_id
),
pharmacy_signal_by_key AS MATERIALIZED (
    SELECT p.pharmacy_id,count(*) AS source_rows,
           count(DISTINCT p.subject_id) AS source_subjects,
           min(p.subject_id) AS source_subject,
           count(*) FILTER (WHERE p.subject_id IS NULL) AS source_missing_subject_rows,
           count(DISTINCT p.hadm_id) AS source_admissions,
           min(p.hadm_id) AS source_admission,
           count(*) FILTER (WHERE p.hadm_id IS NULL) AS source_missing_admission_rows,
           count(DISTINCT nullif(trim(p.poe_id),'')) AS source_poe_keys,
           min(nullif(trim(p.poe_id),'')) AS source_poe_key,
           count(*) FILTER (WHERE nullif(trim(p.poe_id),'') IS NULL)
             AS source_missing_poe_rows,
           bool_or(n.focal_kcl_hint) AS focal_kcl_hint,
           bool_or(n.phosphate_hint OR n.acetate_hint) AS phosphate_or_acetate_hint,
           bool_or(n.other_potassium_salt_hint) AS other_potassium_salt_hint,
           bool_or(n.non_repletion_active_drug_hint) AS active_drug_hint,
           bool_or(n.unresolved_name_hint) AS unresolved_hint
    FROM pharmacy_name_rows p
    JOIN classified_names n
      ON n.source_type='pharmacy_medication'
     AND n.evidence_path='pharmacy_name' AND n.raw_name=p.medication
    GROUP BY p.pharmacy_id
),
pharmacy_by_key AS MATERIALIZED (
    -- pharmacy_id is the audited single-column primary key, so the lexical row
    -- is already the complete component set for that key.
    SELECT s.pharmacy_id,s.source_rows,s.source_rows AS full_component_rows,
           s.source_subjects,s.source_subject,s.source_missing_subject_rows,
           s.source_admissions,s.source_admission,s.source_missing_admission_rows,
           s.source_poe_keys,s.source_poe_key,s.source_missing_poe_rows,
           s.focal_kcl_hint,s.phosphate_or_acetate_hint,
           s.other_potassium_salt_hint,s.active_drug_hint,s.unresolved_hint
    FROM pharmacy_signal_by_key s
),
prescription_signal_by_key AS MATERIALIZED (
    SELECT p.pharmacy_id,count(*) AS source_rows,
           bool_or(n.focal_kcl_hint) AS focal_kcl_hint,
           bool_or(n.phosphate_hint OR n.acetate_hint) AS phosphate_or_acetate_hint,
           bool_or(n.other_potassium_salt_hint) AS other_potassium_salt_hint,
           bool_or(n.non_repletion_active_drug_hint) AS active_drug_hint,
           bool_or(n.unresolved_name_hint) AS unresolved_hint
    FROM prescription_lexical_rows p
    JOIN classified_names n
      ON n.source_type='prescription_drug'
     AND n.evidence_path='prescription_name' AND n.raw_name=p.drug
    GROUP BY p.pharmacy_id
),
prescription_by_key AS MATERIALIZED (
    SELECT s.pharmacy_id,max(s.source_rows) AS source_rows,
           count(p.pharmacy_id) AS full_component_rows,
           count(DISTINCT p.subject_id) AS source_subjects,
           min(p.subject_id) AS source_subject,
           count(*) FILTER (WHERE p.subject_id IS NULL) AS source_missing_subject_rows,
           count(DISTINCT p.hadm_id) AS source_admissions,
           min(p.hadm_id) AS source_admission,
           count(*) FILTER (WHERE p.hadm_id IS NULL) AS source_missing_admission_rows,
           count(DISTINCT nullif(trim(p.poe_id),'')) AS source_poe_keys,
           min(nullif(trim(p.poe_id),'')) AS source_poe_key,
           count(*) FILTER (WHERE nullif(trim(p.poe_id),'') IS NULL)
             AS source_missing_poe_rows,
           bool_or(s.focal_kcl_hint) AS focal_kcl_hint,
           bool_or(s.phosphate_or_acetate_hint) AS phosphate_or_acetate_hint,
           bool_or(s.other_potassium_salt_hint) AS other_potassium_salt_hint,
           bool_or(s.active_drug_hint) AS active_drug_hint,
           bool_or(s.unresolved_hint) AS unresolved_hint
    FROM prescription_signal_by_key s
    JOIN mimiciv_hosp.prescriptions p
      ON p.pharmacy_id::numeric=s.pharmacy_id::numeric
    GROUP BY s.pharmacy_id
),
order_keys AS MATERIALIZED (
    SELECT pharmacy_id FROM pharmacy_by_key
    UNION
    SELECT pharmacy_id FROM prescription_by_key
),
order_detail_links AS MATERIALIZED (
    -- Reverse order-key discovery through the indexed product-row pharmacy key.
    -- Parent detail rows are excluded: in the audited K sample their pharmacy
    -- key is commonly NULL and they are not product evidence.  As with lexical
    -- detail rows, provisional detail-subject partitioning is accepted only if
    -- the explicit canonical-head guard below sums to zero across all buckets.
    SELECT d.emar_id,d.subject_id,d.emar_seq,d.pharmacy_id
    FROM order_keys k
    CROSS JOIN bucket_config b
    JOIN mimiciv_hosp.emar_detail d
      ON d.pharmacy_id::numeric=k.pharmacy_id::numeric
    WHERE d.parent_field_ordinal IS NOT NULL
      AND CASE WHEN b.bucket_parameters_valid THEN
            CASE WHEN d.subject_id IS NULL THEN 0::bigint
                 ELSE ((hashint8extended(d.subject_id::bigint,0)
                         % b.bucket_count::bigint + b.bucket_count::bigint)
                        % b.bucket_count::bigint)
            END = b.bucket_index::bigint
          ELSE false END
),
detail_pharmacy_by_event AS MATERIALIZED (
    SELECT d.emar_id,count(*) AS link_rows,
           count(DISTINCT d.subject_id) AS detail_subjects,
           min(d.subject_id) AS detail_subject,
           count(*) FILTER (WHERE d.subject_id IS NULL) AS detail_missing_subject_rows,
           count(DISTINCT d.emar_seq) AS detail_sequences,
           min(d.emar_seq) AS detail_sequence,
           count(*) FILTER (WHERE d.emar_seq IS NULL) AS detail_missing_sequence_rows,
           bool_and(p.source_subjects=1 AND p.source_missing_subject_rows=0
                    AND p.source_admissions=1 AND p.source_missing_admission_rows=0)
             AS every_order_key_identity_unique,
           count(DISTINCT p.source_subject) AS order_subjects,
           min(p.source_subject) AS order_subject,
           count(DISTINCT p.source_admission) AS order_admissions,
           min(p.source_admission) AS order_admission,
           count(DISTINCT p.source_poe_key) AS order_poe_keys,
           min(p.source_poe_key) AS order_poe_key,
           bool_or(p.source_poe_keys<>1 OR p.source_missing_poe_rows>0)
             AS order_poe_issue,
           bool_or(p.focal_kcl_hint) AS focal_kcl_hint,
           bool_or(p.phosphate_or_acetate_hint) AS phosphate_or_acetate_hint,
           bool_or(p.other_potassium_salt_hint) AS other_potassium_salt_hint,
           bool_or(p.active_drug_hint) AS active_drug_hint,
           bool_or(p.unresolved_hint) AS unresolved_hint
    FROM order_detail_links d JOIN pharmacy_by_key p USING (pharmacy_id)
    GROUP BY d.emar_id
),
detail_prescription_by_event AS MATERIALIZED (
    SELECT d.emar_id,count(*) AS link_rows,
           count(DISTINCT d.subject_id) AS detail_subjects,
           min(d.subject_id) AS detail_subject,
           count(*) FILTER (WHERE d.subject_id IS NULL) AS detail_missing_subject_rows,
           count(DISTINCT d.emar_seq) AS detail_sequences,
           min(d.emar_seq) AS detail_sequence,
           count(*) FILTER (WHERE d.emar_seq IS NULL) AS detail_missing_sequence_rows,
           bool_and(p.source_subjects=1 AND p.source_missing_subject_rows=0
                    AND p.source_admissions=1 AND p.source_missing_admission_rows=0)
             AS every_order_key_identity_unique,
           count(DISTINCT p.source_subject) AS order_subjects,
           min(p.source_subject) AS order_subject,
           count(DISTINCT p.source_admission) AS order_admissions,
           min(p.source_admission) AS order_admission,
           count(DISTINCT p.source_poe_key) AS order_poe_keys,
           min(p.source_poe_key) AS order_poe_key,
           bool_or(p.source_poe_keys<>1 OR p.source_missing_poe_rows>0)
             AS order_poe_issue,
           bool_or(p.focal_kcl_hint) AS focal_kcl_hint,
           bool_or(p.phosphate_or_acetate_hint) AS phosphate_or_acetate_hint,
           bool_or(p.other_potassium_salt_hint) AS other_potassium_salt_hint,
           bool_or(p.active_drug_hint) AS active_drug_hint,
           bool_or(p.unresolved_hint) AS unresolved_hint
    FROM order_detail_links d JOIN prescription_by_key p USING (pharmacy_id)
    GROUP BY d.emar_id
),
order_head_events AS MATERIALIZED (
    SELECT e.emar_id,e.subject_id,e.hadm_id,e.emar_seq,e.pharmacy_id,e.poe_id,
           e.medication,e.event_txt
    FROM order_keys k
    CROSS JOIN bucket_config b
    JOIN mimiciv_hosp.emar e
      ON e.pharmacy_id::numeric=k.pharmacy_id::numeric
    WHERE CASE WHEN b.bucket_parameters_valid THEN
            CASE WHEN e.subject_id IS NULL THEN 0::bigint
                 ELSE ((hashint8extended(e.subject_id::bigint,0)
                         % b.bucket_count::bigint + b.bucket_count::bigint)
                        % b.bucket_count::bigint)
            END = b.bucket_index::bigint
          ELSE false END
),
head_candidate_events AS MATERIALIZED (
    SELECT emar_id,subject_id,hadm_id,emar_seq,pharmacy_id,poe_id,
           medication,event_txt
    FROM direct_rows
    UNION ALL
    SELECT o.emar_id,o.subject_id,o.hadm_id,o.emar_seq,o.pharmacy_id,o.poe_id,
           o.medication,o.event_txt
    FROM order_head_events o
    LEFT JOIN direct_by_event h USING (emar_id)
    WHERE h.emar_id IS NULL
),
detail_candidate_keys AS MATERIALIZED (
    SELECT emar_id FROM detail_text_by_event
    UNION
    SELECT emar_id FROM detail_code_by_event
    UNION
    SELECT emar_id FROM detail_pharmacy_by_event
    UNION
    SELECT emar_id FROM detail_prescription_by_event
),
detail_candidate_heads AS MATERIALIZED (
    -- One primary-key lookup per candidate supplies the canonical partition key
    -- and is reused by both candidate recovery and the detail partition guard.
    SELECT k.emar_id AS candidate_emar_id,e.emar_id AS head_emar_id,
           e.subject_id,e.hadm_id,e.emar_seq,e.pharmacy_id,e.poe_id,
           e.medication,e.event_txt
    FROM detail_candidate_keys k
    LEFT JOIN mimiciv_hosp.emar e ON e.emar_id=k.emar_id
),
candidate_events AS MATERIALIZED (
    SELECT emar_id,subject_id,hadm_id,emar_seq,pharmacy_id,poe_id,
           medication,event_txt
    FROM head_candidate_events
    UNION ALL
    SELECT e.head_emar_id,e.subject_id,e.hadm_id,e.emar_seq,e.pharmacy_id,e.poe_id,
           e.medication,e.event_txt
    FROM detail_candidate_heads e
    CROSS JOIN bucket_config b
    LEFT JOIN head_candidate_events h ON h.emar_id=e.head_emar_id
    WHERE e.head_emar_id IS NOT NULL
      AND h.emar_id IS NULL
      AND CASE WHEN b.bucket_parameters_valid THEN
            CASE WHEN e.subject_id IS NULL THEN 0::bigint
                 ELSE ((hashint8extended(e.subject_id::bigint,0)
                         % b.bucket_count::bigint + b.bucket_count::bigint)
                        % b.bucket_count::bigint)
            END = b.bucket_index::bigint
          ELSE false END
),
joined AS MATERIALIZED (
    SELECT e.*,
           h.source_rows AS head_rows,
           h.query199_head_scope,
           h.focal_kcl_hint AS head_kcl,
           h.phosphate_or_acetate_hint AS head_broader,
           h.other_potassium_salt_hint AS head_other_salt,
           h.active_drug_hint AS head_active,
           h.unresolved_hint AS head_unresolved,
           t.source_rows AS text_rows,t.source_subjects AS text_subjects,
           t.source_subject AS text_subject,
           t.missing_subject_rows AS text_missing_subject_rows,
           t.source_sequences AS text_sequences,
           t.missing_sequence_rows AS text_missing_sequence_rows,
           t.source_sequence AS text_sequence,t.focal_kcl_hint AS text_kcl,
           t.phosphate_or_acetate_hint AS text_broader,
           t.other_potassium_salt_hint AS text_other_salt,
           t.active_drug_hint AS text_active,t.unresolved_hint AS text_unresolved,
           c.source_rows AS code_rows,c.source_subjects AS code_subjects,
           c.source_subject AS code_subject,
           c.missing_subject_rows AS code_missing_subject_rows,
           c.source_sequences AS code_sequences,
           c.missing_sequence_rows AS code_missing_sequence_rows,
           c.source_sequence AS code_sequence,c.focal_kcl_hint AS code_kcl,
           c.phosphate_or_acetate_hint AS code_broader,
           c.other_potassium_salt_hint AS code_other_salt,
           c.active_drug_hint AS code_active,c.unresolved_hint AS code_unresolved,
           p.source_rows AS pharmacy_rows,p.source_subjects AS pharmacy_subjects,
           p.source_subject AS pharmacy_subject,
           p.source_missing_subject_rows AS pharmacy_missing_subject_rows,
           p.source_admissions AS pharmacy_admissions,
           p.source_missing_admission_rows AS pharmacy_missing_admission_rows,
           p.source_admission AS pharmacy_admission,
           p.source_poe_keys AS pharmacy_poe_keys,p.source_poe_key AS pharmacy_poe_key,
           p.source_missing_poe_rows AS pharmacy_missing_poe_rows,
           p.focal_kcl_hint AS pharmacy_kcl,
           p.phosphate_or_acetate_hint AS pharmacy_broader,
           p.other_potassium_salt_hint AS pharmacy_other_salt,
           p.active_drug_hint AS pharmacy_active,p.unresolved_hint AS pharmacy_unresolved,
           r.source_rows AS prescription_rows,r.source_subjects AS prescription_subjects,
           r.source_subject AS prescription_subject,
           r.source_missing_subject_rows AS prescription_missing_subject_rows,
           r.source_admissions AS prescription_admissions,
           r.source_missing_admission_rows AS prescription_missing_admission_rows,
           r.source_admission AS prescription_admission,
           r.source_poe_keys AS prescription_poe_keys,
           r.source_poe_key AS prescription_poe_key,
           r.source_missing_poe_rows AS prescription_missing_poe_rows,
           r.focal_kcl_hint AS prescription_kcl,
           r.phosphate_or_acetate_hint AS prescription_broader,
           r.other_potassium_salt_hint AS prescription_other_salt,
           r.active_drug_hint AS prescription_active,r.unresolved_hint AS prescription_unresolved,
           dp.link_rows AS detail_pharmacy_link_rows,
           dp.detail_subjects AS detail_pharmacy_detail_subjects,
           dp.detail_subject AS detail_pharmacy_detail_subject,
           dp.detail_missing_subject_rows AS detail_pharmacy_missing_subject_rows,
           dp.detail_sequences AS detail_pharmacy_detail_sequences,
           dp.detail_sequence AS detail_pharmacy_detail_sequence,
           dp.detail_missing_sequence_rows AS detail_pharmacy_missing_sequence_rows,
           dp.every_order_key_identity_unique AS detail_pharmacy_keys_unique,
           dp.order_subjects AS detail_pharmacy_order_subjects,
           dp.order_subject AS detail_pharmacy_order_subject,
           dp.order_admissions AS detail_pharmacy_order_admissions,
           dp.order_admission AS detail_pharmacy_order_admission,
           dp.order_poe_keys AS detail_pharmacy_poe_keys,
           dp.order_poe_key AS detail_pharmacy_poe_key,
           dp.order_poe_issue AS detail_pharmacy_poe_issue,
           dp.focal_kcl_hint AS detail_pharmacy_kcl,
           dp.phosphate_or_acetate_hint AS detail_pharmacy_broader,
           dp.other_potassium_salt_hint AS detail_pharmacy_other_salt,
           dp.active_drug_hint AS detail_pharmacy_active,
           dp.unresolved_hint AS detail_pharmacy_unresolved,
           dr.link_rows AS detail_prescription_link_rows,
           dr.detail_subjects AS detail_prescription_detail_subjects,
           dr.detail_subject AS detail_prescription_detail_subject,
           dr.detail_missing_subject_rows AS detail_prescription_missing_subject_rows,
           dr.detail_sequences AS detail_prescription_detail_sequences,
           dr.detail_sequence AS detail_prescription_detail_sequence,
           dr.detail_missing_sequence_rows AS detail_prescription_missing_sequence_rows,
           dr.every_order_key_identity_unique AS detail_prescription_keys_unique,
           dr.order_subjects AS detail_prescription_order_subjects,
           dr.order_subject AS detail_prescription_order_subject,
           dr.order_admissions AS detail_prescription_order_admissions,
           dr.order_admission AS detail_prescription_order_admission,
           dr.order_poe_keys AS detail_prescription_poe_keys,
           dr.order_poe_key AS detail_prescription_poe_key,
           dr.order_poe_issue AS detail_prescription_poe_issue,
           dr.focal_kcl_hint AS detail_prescription_kcl,
           dr.phosphate_or_acetate_hint AS detail_prescription_broader,
           dr.other_potassium_salt_hint AS detail_prescription_other_salt,
           dr.active_drug_hint AS detail_prescription_active,
           dr.unresolved_hint AS detail_prescription_unresolved
    FROM candidate_events e
    LEFT JOIN direct_by_event h USING (emar_id)
    LEFT JOIN detail_text_by_event t USING (emar_id)
    LEFT JOIN detail_code_by_event c USING (emar_id)
    LEFT JOIN pharmacy_by_key p USING (pharmacy_id)
    LEFT JOIN prescription_by_key r USING (pharmacy_id)
    LEFT JOIN detail_pharmacy_by_event dp USING (emar_id)
    LEFT JOIN detail_prescription_by_event dr USING (emar_id)
),
validated_paths AS MATERIALIZED (
    SELECT j.*,
           head_rows IS NOT NULL AS head_raw,
           text_rows IS NOT NULL AS text_raw,
           code_rows IS NOT NULL AS code_raw,
           pharmacy_rows IS NOT NULL AS head_pharmacy_raw,
           prescription_rows IS NOT NULL AS head_prescription_raw,
           detail_pharmacy_link_rows IS NOT NULL AS detail_pharmacy_raw,
           detail_prescription_link_rows IS NOT NULL AS detail_prescription_raw,
           head_rows IS NOT NULL AS head_valid,
           coalesce(text_rows IS NOT NULL AND text_subjects=1
                    AND text_missing_subject_rows=0
                    AND text_sequences=1 AND text_subject=subject_id
                    AND text_missing_sequence_rows=0
                    AND text_sequence=emar_seq,false) AS text_valid,
           coalesce(code_rows IS NOT NULL AND code_subjects=1
                    AND code_missing_subject_rows=0
                    AND code_sequences=1 AND code_subject=subject_id
                    AND code_missing_sequence_rows=0
                    AND code_sequence=emar_seq,false) AS code_valid,
           coalesce(pharmacy_rows IS NOT NULL AND pharmacy_subjects=1
                    AND pharmacy_missing_subject_rows=0
                    AND pharmacy_admissions=1
                    AND pharmacy_missing_admission_rows=0 AND hadm_id IS NOT NULL
                    AND pharmacy_subject=subject_id
                    AND pharmacy_admission=hadm_id,false) AS head_pharmacy_valid,
           coalesce(prescription_rows IS NOT NULL AND prescription_subjects=1
                    AND prescription_missing_subject_rows=0
                    AND prescription_admissions=1
                    AND prescription_missing_admission_rows=0 AND hadm_id IS NOT NULL
                    AND prescription_subject=subject_id
                    AND prescription_admission=hadm_id,false) AS head_prescription_valid,
           coalesce(detail_pharmacy_link_rows IS NOT NULL
                    AND detail_pharmacy_detail_subjects=1
                    AND detail_pharmacy_missing_subject_rows=0
                    AND detail_pharmacy_detail_subject=subject_id
                    AND detail_pharmacy_detail_sequences=1
                    AND detail_pharmacy_missing_sequence_rows=0
                    AND detail_pharmacy_detail_sequence=emar_seq
                    AND detail_pharmacy_keys_unique
                    AND detail_pharmacy_order_subjects=1
                    AND detail_pharmacy_order_subject=subject_id
                    AND detail_pharmacy_order_admissions=1
                    AND hadm_id IS NOT NULL
                    AND detail_pharmacy_order_admission=hadm_id,false)
             AS detail_pharmacy_valid,
           coalesce(detail_prescription_link_rows IS NOT NULL
                    AND detail_prescription_detail_subjects=1
                    AND detail_prescription_missing_subject_rows=0
                    AND detail_prescription_detail_subject=subject_id
                    AND detail_prescription_detail_sequences=1
                    AND detail_prescription_missing_sequence_rows=0
                    AND detail_prescription_detail_sequence=emar_seq
                    AND detail_prescription_keys_unique
                    AND detail_prescription_order_subjects=1
                    AND detail_prescription_order_subject=subject_id
                    AND detail_prescription_order_admissions=1
                    AND hadm_id IS NOT NULL
                    AND detail_prescription_order_admission=hadm_id,false)
             AS detail_prescription_valid
    FROM joined j
),
validated AS MATERIALIZED (
    SELECT p.*,
           head_pharmacy_raw OR detail_pharmacy_raw AS pharmacy_raw,
           head_prescription_raw OR detail_prescription_raw AS prescription_raw,
           head_pharmacy_valid OR detail_pharmacy_valid AS pharmacy_valid,
           head_prescription_valid OR detail_prescription_valid AS prescription_valid,
           coalesce((head_pharmacy_valid AND pharmacy_poe_keys=1
             AND pharmacy_missing_poe_rows=0 AND pharmacy_poe_key=poe_id)
             OR (detail_pharmacy_valid AND detail_pharmacy_poe_keys=1
             AND NOT detail_pharmacy_poe_issue
             AND detail_pharmacy_poe_key=poe_id),false) AS pharmacy_strict_poe_valid,
           coalesce((head_prescription_valid AND prescription_poe_keys=1
             AND prescription_missing_poe_rows=0 AND prescription_poe_key=poe_id)
             OR (detail_prescription_valid AND detail_prescription_poe_keys=1
             AND NOT detail_prescription_poe_issue
             AND detail_prescription_poe_key=poe_id),false)
             AS prescription_strict_poe_valid
    FROM validated_paths p
),
masked AS MATERIALIZED (
    SELECT v.*,
           head_raw::int + 2*text_raw::int + 4*code_raw::int
             + 8*pharmacy_raw::int + 16*prescription_raw::int AS raw_source_mask,
           head_valid::int + 2*text_valid::int + 4*code_valid::int
             + 8*pharmacy_valid::int + 16*prescription_valid::int AS valid_source_mask,
           coalesce(head_kcl,false)
             OR (text_valid AND coalesce(text_kcl,false))
             OR (code_valid AND coalesce(code_kcl,false))
             OR (head_pharmacy_valid AND coalesce(pharmacy_kcl,false))
             OR (detail_pharmacy_valid AND coalesce(detail_pharmacy_kcl,false))
             OR (head_prescription_valid AND coalesce(prescription_kcl,false))
             OR (detail_prescription_valid AND coalesce(detail_prescription_kcl,false))
             AS valid_kcl_hint,
           coalesce(head_broader,false)
             OR (text_valid AND coalesce(text_broader,false))
             OR (code_valid AND coalesce(code_broader,false))
             OR (head_pharmacy_valid AND coalesce(pharmacy_broader,false))
             OR (detail_pharmacy_valid AND coalesce(detail_pharmacy_broader,false))
             OR (head_prescription_valid AND coalesce(prescription_broader,false))
             OR (detail_prescription_valid AND coalesce(detail_prescription_broader,false))
             AS valid_phosphate_or_acetate_hint,
           coalesce(head_other_salt,false)
             OR (text_valid AND coalesce(text_other_salt,false))
             OR (code_valid AND coalesce(code_other_salt,false))
             OR (head_pharmacy_valid AND coalesce(pharmacy_other_salt,false))
             OR (detail_pharmacy_valid AND coalesce(detail_pharmacy_other_salt,false))
             OR (head_prescription_valid AND coalesce(prescription_other_salt,false))
             OR (detail_prescription_valid AND coalesce(detail_prescription_other_salt,false))
             AS valid_other_salt_hint,
           coalesce(head_active,false)
             OR (text_valid AND coalesce(text_active,false))
             OR (code_valid AND coalesce(code_active,false))
             OR (head_pharmacy_valid AND coalesce(pharmacy_active,false))
             OR (detail_pharmacy_valid AND coalesce(detail_pharmacy_active,false))
             OR (head_prescription_valid AND coalesce(prescription_active,false))
             OR (detail_prescription_valid AND coalesce(detail_prescription_active,false))
             AS valid_active_hint,
           coalesce(head_unresolved,false)
             OR (text_valid AND coalesce(text_unresolved,false))
             OR (code_valid AND coalesce(code_unresolved,false))
             OR (head_pharmacy_valid AND coalesce(pharmacy_unresolved,false))
             OR (detail_pharmacy_valid AND coalesce(detail_pharmacy_unresolved,false))
             OR (head_prescription_valid AND coalesce(prescription_unresolved,false))
             OR (detail_prescription_valid AND coalesce(detail_prescription_unresolved,false))
             AS valid_unresolved_hint
    FROM validated v
),
assessed AS MATERIALIZED (
    SELECT m.*,
           head_raw::int + 2*(text_raw OR code_raw)::int
             + 4*(pharmacy_raw OR prescription_raw)::int AS coarse_raw_source_mask,
           head_valid::int + 2*(text_valid OR code_valid)::int
             + 4*(pharmacy_valid OR prescription_valid)::int
             AS coarse_valid_source_mask,
           head_valid::int + 2*text_valid::int + 4*code_valid::int
             + 8*pharmacy_strict_poe_valid::int
             + 16*prescription_strict_poe_valid::int AS strict_poe_source_mask,
           head_valid::int + 2*(text_valid OR code_valid)::int
             + 4*(pharmacy_strict_poe_valid OR prescription_strict_poe_valid)::int
             AS coarse_strict_poe_source_mask,
           valid_kcl_hint::int + 2*valid_phosphate_or_acetate_hint::int
             + 4*valid_other_salt_hint::int + 8*valid_active_hint::int
             + 16*valid_unresolved_hint::int AS valid_review_family_mask,
           CASE WHEN medication IS NULL THEN 'missing_head_name'
                WHEN nullif(trim(medication),'') IS NULL THEN 'blank_head_name'
                WHEN head_raw THEN 'declared_lexical_head_name'
                ELSE 'nonlexical_head_name' END AS head_name_pattern,
           CASE WHEN valid_source_mask=0 THEN 'identity_unresolved_only'
                WHEN valid_active_hint
                     AND (valid_kcl_hint OR valid_phosphate_or_acetate_hint
                          OR valid_other_salt_hint)
                  THEN 'mixed_repletion_and_nonrepletion_hints'
                WHEN (valid_kcl_hint::int + valid_phosphate_or_acetate_hint::int
                      + valid_other_salt_hint::int + valid_unresolved_hint::int)>1
                  THEN 'mixed_repletion_or_unresolved_hints'
                WHEN valid_kcl_hint THEN 'focal_kcl_repletion_hint'
                WHEN valid_phosphate_or_acetate_hint
                  THEN 'broader_phosphate_or_acetate_repletion_hint'
                WHEN valid_active_hint THEN 'non_repletion_active_drug_hint'
                WHEN valid_other_salt_hint THEN 'other_potassium_salt_review'
                ELSE 'unresolved_name_or_local_code_review' END AS review_pattern,
           CASE WHEN head_raw THEN 'direct_head_evidence_present'
                WHEN valid_source_mask>0 THEN 'recovered_without_direct_head_evidence'
                ELSE 'linked_evidence_identity_unresolved' END AS recovery_pattern,
           CASE WHEN event_txt='Administered' THEN 'administered_exact'
                WHEN event_txt='Partial Administered' THEN 'partial_administered'
                WHEN event_txt='Delayed Administered' THEN 'delayed_administered'
                WHEN event_txt IN ('Started','Delayed Started','Restarted')
                  THEN 'start_or_restart_control'
                WHEN event_txt IN ('Not Given','Not Given per Sliding Scale','Hold Dose')
                  THEN 'not_given_or_hold'
                WHEN event_txt IN ('Stopped','Stopped - Unscheduled','Confirmed',
                                   'Flushed','Not Flushed')
                  THEN 'other_control_record'
                WHEN event_txt IS NULL THEN 'missing_status'
                ELSE 'other_status' END AS event_status_class
    FROM masked m
),
admission_checked AS MATERIALIZED (
    -- Preserve every candidate head.  admissions.hadm_id is checked below as a
    -- physical primary key, while the scientific admission identity remains
    -- the logical (subject_id,hadm_id) pair.  Nonexact links are classified and
    -- reported; this source-closure query neither repairs nor excludes them.
    SELECT a.*,
           CASE
             WHEN a.subject_id IS NULL AND a.hadm_id IS NULL
               THEN 'missing_subject_and_hadm'
             WHEN a.subject_id IS NULL THEN 'missing_subject_id'
             WHEN a.hadm_id IS NULL THEN 'missing_hadm_id'
             WHEN h.hadm_id IS NULL THEN 'nonnull_hadm_absent_from_admissions'
             WHEN h.subject_id IS DISTINCT FROM a.subject_id
               THEN 'hadm_subject_mismatch'
             ELSE 'exact_subject_hadm_match'
           END AS admission_link_status
    FROM assessed a
    LEFT JOIN mimiciv_hosp.admissions h ON h.hadm_id=a.hadm_id
),
detail_subject_partition_guard AS MATERIALIZED (
    -- The detail index scan is provisionally partitioned by emar_detail.subject_id.
    -- A zero violation count proves that every selected text/code event has one
    -- non-NULL detail subject equal to its canonical eMAR head subject and belongs
    -- to this same bucket.  The merge rejects every run with a nonzero count.
    SELECT count(*) AS detail_subject_partition_groups_checked,
           count(*) FILTER (
             WHERE h.head_emar_id IS NULL
                OR d.source_subjects<>1
                OR d.missing_subject_rows>0
                OR d.source_subject IS NULL
                OR h.subject_id IS DISTINCT FROM d.source_subject
                OR NOT CASE WHEN b.bucket_parameters_valid THEN
                     CASE WHEN h.subject_id IS NULL THEN 0::bigint
                          ELSE ((hashint8extended(h.subject_id::bigint,0)
                                  % b.bucket_count::bigint + b.bucket_count::bigint)
                                 % b.bucket_count::bigint)
                     END = b.bucket_index::bigint
                   ELSE false END)
             AS detail_subject_partition_identity_violations
    FROM (
        SELECT emar_id,source_subjects,source_subject,missing_subject_rows
        FROM detail_text_by_event
        UNION ALL
        SELECT emar_id,source_subjects,source_subject,missing_subject_rows
        FROM detail_code_by_event
    ) d
    CROSS JOIN bucket_config b
    LEFT JOIN detail_candidate_heads h ON h.candidate_emar_id=d.emar_id
),
order_detail_subject_partition_guard AS MATERIALIZED (
    SELECT count(*) AS order_detail_subject_partition_groups_checked,
           count(*) FILTER (
             WHERE h.head_emar_id IS NULL
                OR d.detail_subjects<>1
                OR d.detail_missing_subject_rows>0
                OR d.detail_subject IS NULL
                OR h.subject_id IS DISTINCT FROM d.detail_subject
                OR NOT CASE WHEN b.bucket_parameters_valid THEN
                     CASE WHEN h.subject_id IS NULL THEN 0::bigint
                          ELSE ((hashint8extended(h.subject_id::bigint,0)
                                  % b.bucket_count::bigint + b.bucket_count::bigint)
                                 % b.bucket_count::bigint)
                     END = b.bucket_index::bigint
                   ELSE false END)
             AS order_detail_subject_partition_identity_violations
    FROM (
        SELECT emar_id,detail_subjects,detail_subject,
               detail_missing_subject_rows
        FROM detail_pharmacy_by_event
        UNION ALL
        SELECT emar_id,detail_subjects,detail_subject,
               detail_missing_subject_rows
        FROM detail_prescription_by_event
    ) d
    CROSS JOIN bucket_config b
    LEFT JOIN detail_candidate_heads h ON h.candidate_emar_id=d.emar_id
),
bucket_integrity AS MATERIALIZED (
    SELECT count(*) FILTER (
             WHERE NOT CASE WHEN b.bucket_parameters_valid THEN
               CASE WHEN a.subject_id IS NULL THEN 0::bigint
                    ELSE ((hashint8extended(a.subject_id::bigint,0)
                            % b.bucket_count::bigint + b.bucket_count::bigint)
                           % b.bucket_count::bigint)
               END = b.bucket_index::bigint
             ELSE false END)
             AS bucket_assignment_violations,
           count(*) FILTER (WHERE a.subject_id IS NULL)
             AS null_subject_candidate_heads,
           count(*) FILTER (WHERE admission_link_status=
             'exact_subject_hadm_match') AS admission_exact_match_heads,
           count(*) FILTER (WHERE admission_link_status=
             'missing_subject_and_hadm')
             AS admission_missing_subject_and_hadm_heads,
           count(*) FILTER (WHERE admission_link_status='missing_subject_id')
             AS admission_missing_subject_id_heads,
           count(*) FILTER (WHERE admission_link_status='missing_hadm_id')
             AS admission_missing_hadm_id_heads,
           count(*) FILTER (WHERE admission_link_status=
             'nonnull_hadm_absent_from_admissions')
             AS admission_hadm_absent_from_admissions_heads,
           count(*) FILTER (WHERE admission_link_status=
             'hadm_subject_mismatch') AS admission_subject_mismatch_heads,
           count(*) FILTER (WHERE admission_link_status<>
             'exact_subject_hadm_match') AS nonexact_admission_link_heads,
           count(DISTINCT subject_id) FILTER (WHERE admission_link_status<>
             'exact_subject_hadm_match') AS nonexact_admission_link_subjects,
           count(DISTINCT (subject_id,hadm_id)) FILTER (
             WHERE admission_link_status<>'exact_subject_hadm_match'
               AND subject_id IS NOT NULL AND hadm_id IS NOT NULL)
             AS nonexact_admission_link_pairs,
           count(DISTINCT hadm_id) FILTER (WHERE admission_link_status<>
             'exact_subject_hadm_match' AND hadm_id IS NOT NULL)
             AS nonexact_admission_link_hadm_ids_within_partition,
           count(*)-count(DISTINCT a.emar_id) AS duplicate_candidate_emar_heads
    FROM admission_checked a
    CROSS JOIN bucket_config b
),
schema_guards AS MATERIALIZED (
    SELECT EXISTS (
             SELECT 1
             FROM pg_catalog.pg_index i
             JOIN pg_catalog.pg_class t ON t.oid=i.indrelid
             JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace
             JOIN pg_catalog.pg_attribute a
               ON a.attrelid=t.oid AND a.attnum=i.indkey[0]
             WHERE n.nspname='mimiciv_hosp' AND t.relname='emar'
               AND i.indisprimary AND i.indisvalid AND i.indisready
               AND i.indnkeyatts=1 AND a.attname='emar_id')
             AS emar_id_primary_key_confirmed,
           EXISTS (
             SELECT 1
             FROM pg_catalog.pg_index i
             JOIN pg_catalog.pg_class t ON t.oid=i.indrelid
             JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace
             JOIN pg_catalog.pg_attribute a
               ON a.attrelid=t.oid AND a.attnum=i.indkey[0]
             WHERE n.nspname='mimiciv_hosp' AND t.relname='admissions'
               AND i.indisprimary AND i.indisvalid AND i.indisready
               AND i.indnkeyatts=1 AND a.attname='hadm_id')
             AS admissions_hadm_id_primary_key_confirmed,
           EXISTS (
             SELECT 1
             FROM pg_catalog.pg_index i
             JOIN pg_catalog.pg_class t ON t.oid=i.indrelid
             JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace
             JOIN pg_catalog.pg_attribute a
               ON a.attrelid=t.oid AND a.attnum=i.indkey[0]
             WHERE n.nspname='mimiciv_hosp' AND t.relname='pharmacy'
               AND i.indisprimary AND i.indisvalid AND i.indisready
               AND i.indnkeyatts=1 AND a.attname='pharmacy_id')
             AS pharmacy_id_primary_key_confirmed,
           (SELECT count(*)=4
                   AND bool_and(a.atttypid IN (
                         'pg_catalog.int2'::regtype,
                         'pg_catalog.int4'::regtype,
                         'pg_catalog.int8'::regtype))
            FROM pg_catalog.pg_class t
            JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace
            JOIN pg_catalog.pg_attribute a ON a.attrelid=t.oid
            WHERE n.nspname='mimiciv_hosp'
              AND t.relname IN ('pharmacy','prescriptions','emar','emar_detail')
              AND t.relkind IN ('r','p')
              AND a.attname='pharmacy_id'
              AND a.attnum>0 AND NOT a.attisdropped)
             AS pharmacy_id_integer_types_confirmed
)
SELECT 'closure_bucket_metadata'::text AS section,
       jsonb_build_object('bucket_index',b.bucket_index,
                          'bucket_count',b.bucket_count) AS dimensions,
       (SELECT count(*) FROM admission_checked) AS records,
       jsonb_build_object(
         'merge_protocol_version',1,
         'bucket_index',b.bucket_index,
         'bucket_count',b.bucket_count,
         'bucket_parameters_valid',b.bucket_parameters_valid,
         'bucket_assignment_basis','emar_head_subject_id',
         'bucket_hash_function','hashint8extended(subject_id::bigint,0)',
         'bucket_remainder_normalization','((hash % count)+count)%count',
         'null_subject_bucket',0,
         'candidate_emar_heads',(SELECT count(DISTINCT emar_id) FROM admission_checked),
         'subjects',(SELECT count(DISTINCT subject_id) FROM admission_checked),
         'admissions',(SELECT count(DISTINCT (subject_id,hadm_id))
                       FROM admission_checked
                       WHERE subject_id IS NOT NULL AND hadm_id IS NOT NULL),
         'query199_head_scope_distinct_heads',(SELECT count(*) FROM admission_checked
                                               WHERE query199_head_scope),
         'bucket_assignment_violations',i.bucket_assignment_violations,
         'detail_subject_partition_groups_checked',
           d.detail_subject_partition_groups_checked,
         'detail_subject_partition_identity_violations',
           d.detail_subject_partition_identity_violations,
         'order_detail_subject_partition_groups_checked',
           o.order_detail_subject_partition_groups_checked,
         'order_detail_subject_partition_identity_violations',
           o.order_detail_subject_partition_identity_violations,
         'null_subject_candidate_heads',i.null_subject_candidate_heads,
         'admission_exact_match_heads',i.admission_exact_match_heads,
         'admission_missing_subject_and_hadm_heads',
           i.admission_missing_subject_and_hadm_heads,
         'admission_missing_subject_id_heads',
           i.admission_missing_subject_id_heads,
         'admission_missing_hadm_id_heads',i.admission_missing_hadm_id_heads,
         'admission_hadm_absent_from_admissions_heads',
           i.admission_hadm_absent_from_admissions_heads,
         'admission_subject_mismatch_heads',i.admission_subject_mismatch_heads,
         'nonexact_admission_link_heads',i.nonexact_admission_link_heads,
         'nonexact_admission_link_subjects',i.nonexact_admission_link_subjects,
         'nonexact_admission_link_pairs',i.nonexact_admission_link_pairs
       ) || jsonb_build_object(
         'duplicate_candidate_emar_heads',i.duplicate_candidate_emar_heads,
         'emar_id_primary_key_confirmed',g.emar_id_primary_key_confirmed,
         'admissions_hadm_id_primary_key_confirmed',
           g.admissions_hadm_id_primary_key_confirmed,
         'pharmacy_id_primary_key_confirmed',
           g.pharmacy_id_primary_key_confirmed,
         'pharmacy_id_integer_types_confirmed',
           g.pharmacy_id_integer_types_confirmed,
         'selected_detail_rows_in_bucket',
           (SELECT count(*) FROM selected_detail_rows),
         'detail_text_rows_in_bucket',
           (SELECT count(*) FROM detail_text_rows_raw),
         'detail_code_rows_in_bucket',
           (SELECT coalesce(sum(source_rows),0) FROM detail_code_rows),
         'order_detail_link_rows_in_bucket',
           (SELECT count(*) FROM order_detail_links),
         'detail_code_dictionary_miss_names',
           dc.detail_code_dictionary_miss_names,
         'supplied_detail_code_dictionary_names',
           (SELECT count(*) FROM detail_code_name_flags),
         'selected_pharmacy_keys_global',(SELECT count(*) FROM pharmacy_by_key),
         'selected_pharmacy_full_component_rows_global',
           (SELECT coalesce(sum(full_component_rows),0) FROM pharmacy_by_key),
         'selected_prescription_keys_global',
           (SELECT count(*) FROM prescription_by_key),
         'selected_prescription_full_component_rows_global',
           (SELECT coalesce(sum(full_component_rows),0) FROM prescription_by_key),
         'non_null_emar_medication_names',
           (SELECT non_null_emar_medication_names FROM discovery_metadata),
         'non_null_detail_product_descriptions',
           (SELECT non_null_detail_product_descriptions FROM discovery_metadata),
         'non_null_pharmacy_medication_names',
           (SELECT non_null_pharmacy_medication_names FROM discovery_metadata),
         'identity_consistent_lexical_detail_product_rows',
           (SELECT identity_consistent_lexical_detail_product_rows
            FROM discovery_metadata),
         'identity_consistent_lexical_detail_events',
           (SELECT identity_consistent_lexical_detail_events
            FROM discovery_metadata),
         'seed_local_product_codes',(SELECT count(*) FROM seed_product_codes),
         'event_sections_additive_by_exact_dimensions',true,
         'missing_dimension_rows_merge_as_zero',true,
         'constant_fields_require_exact_equality',true,
         'admission_count_uses_nonnull_subject_hadm_pairs',true,
         'logical_admission_pairs_additive_by_subject_partition',true,
         'admission_link_status_partition_complete',true,
         'admission_link_anomalies_reported_not_repaired',true,
         'raw_identifiers_times_or_patient_text_emitted',false) AS counters
FROM bucket_config b
CROSS JOIN bucket_integrity i
CROSS JOIN detail_subject_partition_guard d
CROSS JOIN order_detail_subject_partition_guard o
CROSS JOIN schema_guards g
CROSS JOIN detail_code_dictionary_guard dc
UNION ALL
SELECT 'admission_link_status',
       jsonb_build_object('bucket_index',b.bucket_index,
                          'bucket_count',b.bucket_count),
       (SELECT count(*) FROM admission_checked),
       jsonb_build_object(
         'candidate_emar_heads',(SELECT count(DISTINCT emar_id)
                                 FROM admission_checked),
         'subjects',(SELECT count(DISTINCT subject_id) FROM admission_checked),
         'admissions',(SELECT count(DISTINCT (subject_id,hadm_id))
                       FROM admission_checked
                       WHERE subject_id IS NOT NULL AND hadm_id IS NOT NULL),
         'admission_exact_match_heads',i.admission_exact_match_heads,
         'admission_missing_subject_and_hadm_heads',
           i.admission_missing_subject_and_hadm_heads,
         'admission_missing_subject_id_heads',
           i.admission_missing_subject_id_heads,
         'admission_missing_hadm_id_heads',i.admission_missing_hadm_id_heads,
         'admission_hadm_absent_from_admissions_heads',
           i.admission_hadm_absent_from_admissions_heads,
         'admission_subject_mismatch_heads',i.admission_subject_mismatch_heads,
         'nonexact_admission_link_heads',i.nonexact_admission_link_heads,
         'nonexact_admission_link_subjects',i.nonexact_admission_link_subjects,
         'nonexact_admission_link_pairs',i.nonexact_admission_link_pairs,
         'nonexact_admission_link_hadm_ids_within_partition',
           i.nonexact_admission_link_hadm_ids_within_partition,
         'formal_cohort',false)
FROM bucket_config b
CROSS JOIN bucket_integrity i
UNION ALL
SELECT 'admission_link_evidence',jsonb_build_object(
         'bucket_index',b.bucket_index,
         'bucket_count',b.bucket_count,
         'admission_link_status',admission_link_status,
         'recovery_pattern',recovery_pattern,
         'coarse_raw_source_mask',coarse_raw_source_mask),
       count(*),
       jsonb_build_object('candidate_emar_heads',count(*),
                          'formal_cohort',false)
FROM admission_checked
CROSS JOIN bucket_config b
GROUP BY b.bucket_index,b.bucket_count,admission_link_status,
         recovery_pattern,coarse_raw_source_mask
UNION ALL
SELECT 'event_evidence_mask',jsonb_build_object(
         'raw_source_mask',raw_source_mask,
         'identity_valid_source_mask',valid_source_mask,
         'strict_poe_source_mask',strict_poe_source_mask,
         'coarse_raw_source_mask',coarse_raw_source_mask,
         'coarse_identity_valid_source_mask',coarse_valid_source_mask,
         'coarse_strict_poe_source_mask',coarse_strict_poe_source_mask,
         'valid_review_family_mask',valid_review_family_mask,
         'head_name_pattern',head_name_pattern,
         'recovery_pattern',recovery_pattern,
         'review_pattern',review_pattern),
       count(*),
       jsonb_build_object(
         'emar_heads',count(DISTINCT emar_id),
         'subjects',count(DISTINCT subject_id),
         'admissions',count(DISTINCT (subject_id,hadm_id)) FILTER (
             WHERE subject_id IS NOT NULL AND hadm_id IS NOT NULL),
         'head_raw_heads',count(*) FILTER (WHERE head_raw),
         'detail_text_raw_heads',count(*) FILTER (WHERE text_raw),
         'detail_code_raw_heads',count(*) FILTER (WHERE code_raw),
         'pharmacy_raw_heads',count(*) FILTER (WHERE pharmacy_raw),
         'prescription_raw_heads',count(*) FILTER (WHERE prescription_raw),
         'detail_text_identity_valid_heads',count(*) FILTER (WHERE text_valid),
         'detail_code_identity_valid_heads',count(*) FILTER (WHERE code_valid),
         'pharmacy_identity_valid_heads',count(*) FILTER (WHERE pharmacy_valid),
         'prescription_identity_valid_heads',count(*) FILTER (WHERE prescription_valid),
         'pharmacy_strict_poe_valid_heads',count(*) FILTER (
             WHERE pharmacy_strict_poe_valid),
         'prescription_strict_poe_valid_heads',count(*) FILTER (
             WHERE prescription_strict_poe_valid),
         'administered_exact_heads',count(*) FILTER (
             WHERE event_status_class='administered_exact'),
         'partial_administered_heads',count(*) FILTER (
             WHERE event_status_class='partial_administered'),
         'delayed_administered_heads',count(*) FILTER (
             WHERE event_status_class='delayed_administered'),
         'start_or_restart_control_heads',count(*) FILTER (
             WHERE event_status_class='start_or_restart_control'),
         'not_given_or_hold_heads',count(*) FILTER (
             WHERE event_status_class='not_given_or_hold'),
         'other_control_record_heads',count(*) FILTER (
             WHERE event_status_class='other_control_record'),
         'missing_status_heads',count(*) FILTER (
             WHERE event_status_class='missing_status'),
         'other_status_heads',count(*) FILTER (
             WHERE event_status_class='other_status'),
         'formal_action',false)
FROM admission_checked
GROUP BY raw_source_mask,valid_source_mask,strict_poe_source_mask,
         coarse_raw_source_mask,coarse_valid_source_mask,
         coarse_strict_poe_source_mask,valid_review_family_mask,
         head_name_pattern,recovery_pattern,review_pattern
UNION ALL
SELECT 'recovered_head_vocabulary',jsonb_build_object(
         'raw_head_medication',medication,
         'normalized_head_medication',
           lower(regexp_replace(trim(medication),'[[:space:]]+',' ','g')),
         'head_name_pattern',head_name_pattern),
       count(*),
       jsonb_build_object(
         'emar_heads',count(DISTINCT emar_id),
         'subjects',count(DISTINCT subject_id),
         'admissions',count(DISTINCT (subject_id,hadm_id)) FILTER (
             WHERE subject_id IS NOT NULL AND hadm_id IS NOT NULL),
         'administered_exact_heads',count(*) FILTER (
             WHERE event_status_class='administered_exact'),
         'detail_text_identity_valid_heads',count(*) FILTER (WHERE text_valid),
         'detail_code_identity_valid_heads',count(*) FILTER (WHERE code_valid),
         'pharmacy_identity_valid_heads',count(*) FILTER (WHERE pharmacy_valid),
         'prescription_identity_valid_heads',count(*) FILTER (WHERE prescription_valid),
         'focal_kcl_review_heads',count(*) FILTER (
             WHERE review_pattern='focal_kcl_repletion_hint'),
         'broader_phosphate_or_acetate_review_heads',count(*) FILTER (
             WHERE review_pattern='broader_phosphate_or_acetate_repletion_hint'),
         'non_repletion_active_review_heads',count(*) FILTER (
             WHERE review_pattern='non_repletion_active_drug_hint'),
         'mixed_or_unresolved_review_heads',count(*) FILTER (
             WHERE review_pattern NOT IN ('focal_kcl_repletion_hint',
               'broader_phosphate_or_acetate_repletion_hint',
               'non_repletion_active_drug_hint')),
         'dictionary_value_is_patient_text',false,
         'head_name_adopted_as_source_policy',false)
FROM admission_checked
WHERE NOT head_raw
GROUP BY medication,head_name_pattern
UNION ALL
SELECT 'event_conservation','{}'::jsonb,count(*),
       jsonb_build_object(
         'candidate_emar_heads',count(DISTINCT emar_id),
         'subjects',count(DISTINCT subject_id),
         'admissions',count(DISTINCT (subject_id,hadm_id)) FILTER (
             WHERE subject_id IS NOT NULL AND hadm_id IS NOT NULL),
         'direct_head_evidence_heads',count(*) FILTER (WHERE head_raw),
         'query199_head_scope_distinct_heads',count(*) FILTER (
             WHERE query199_head_scope),
         'query199_prior_real_audit_reference_heads',559191,
         'detail_text_evidence_heads',count(*) FILTER (WHERE text_raw),
         'detail_code_evidence_heads',count(*) FILTER (WHERE code_raw),
         'pharmacy_name_evidence_heads',count(*) FILTER (WHERE pharmacy_raw),
         'prescription_name_evidence_heads',count(*) FILTER (WHERE prescription_raw),
         'pharmacy_name_evidence_via_head_key',count(*) FILTER (
             WHERE head_pharmacy_raw),
         'pharmacy_name_evidence_via_detail_key',count(*) FILTER (
             WHERE detail_pharmacy_raw),
         'prescription_name_evidence_via_head_key',count(*) FILTER (
             WHERE head_prescription_raw),
         'prescription_name_evidence_via_detail_key',count(*) FILTER (
             WHERE detail_prescription_raw),
         'pharmacy_strict_poe_valid_heads',count(*) FILTER (
             WHERE pharmacy_strict_poe_valid),
         'prescription_strict_poe_valid_heads',count(*) FILTER (
             WHERE prescription_strict_poe_valid),
         'heads_new_beyond_direct_name',count(*) FILTER (WHERE NOT head_raw),
         'missing_head_name_recovered_by_valid_nondirect_evidence',count(*) FILTER (
             WHERE NOT head_raw AND medication IS NULL AND valid_source_mask>0),
         'nonlexical_head_name_recovered_by_valid_nondirect_evidence',count(*) FILTER (
             WHERE NOT head_raw AND medication IS NOT NULL
               AND nullif(trim(medication),'') IS NOT NULL AND valid_source_mask>0),
         'identity_unresolved_only_heads',count(*) FILTER (WHERE valid_source_mask=0),
         'source_memberships_overlap_and_are_not_additive',true,
         'formal_cohort',false)
FROM admission_checked
UNION ALL
SELECT 'scope_guards','{}'::jsonb,count(*),jsonb_build_object(
         'declared_lexical_and_one_hop_code_scope_exact',true,
         'source_bits','head=1, detail_text=2, detail_code=4, pharmacy=8, prescription=16',
         'coarse_source_bits','head=1, any_detail=2, any_order=4',
         'review_family_bits','kcl=1, phosphate_or_acetate=2, other_salt=4, active_drug=8, unresolved=16',
         'many_sides_preaggregated_before_event_join',true,
         'order_identity_and_poe_gates_use_all_selected_key_components',true,
         'null_subject_admission_or_sequence_fails_identity_validation',true,
         'detail_rows_examined',true,
         'detail_product_rows_require_subject_and_emar_seq_before_code_seed',true,
         'order_links_include_head_and_product_detail_pharmacy_keys',true,
         'strict_order_poe_mask_computed',true,
         'subject_partitioned_event_shard',true,
         'bucket_assignment_uses_emar_head_subject_id',true,
         'detail_scan_partition_uses_emar_detail_subject_id',true,
         'detail_subject_partition_identity_violations_must_sum_to_zero',true,
         'order_detail_scan_partition_uses_emar_detail_subject_id',true,
         'order_detail_subject_partition_identity_violations_must_sum_to_zero',true,
         'null_head_subject_assigned_to_bucket_zero',true,
         'pharmacy_and_prescription_full_components_unbucketed',true,
         'event_sections_additive_by_exact_dimensions',true,
         'admission_count_uses_nonnull_subject_hadm_pairs',true,
         'logical_admission_pairs_additive_by_subject_partition',true,
         'admission_link_status_partition_complete',true,
         'admission_link_anomalies_reported_not_repaired',true,
         'admission_table_link_requires_exact_subject_hadm_pair',true,
         'emar_id_primary_key_must_be_confirmed',true,
         'admissions_hadm_id_primary_key_must_be_confirmed',true,
         'pharmacy_id_primary_key_must_be_confirmed',true,
         'pharmacy_id_integer_types_must_be_confirmed',true,
         'detail_code_dictionary_matches_global_private_flags',true,
         'product_code_is_ndc',false,
         'product_code_used_for_final_product_identity',false,
         'product_identity_decided',false,
         'product_description_other_examined',false,
         'unseeded_brand_vocabulary_exhausted',false,
         'complete_intervention_coverage',false,
         'final_source_policy',false,
         'review_strata_are_inclusion_rules',false,
         'route_is_administration_proof',false,
         'delivered_dose_defined',false,
         'formal_action',false,
         'zero_action_constructed',false,
         'formal_episode',false,
         'formal_label',false,
         'formal_non_icu_rule',false,
         'formal_cohort',false,
         'raw_identifiers_times_or_patient_text_emitted',false)
FROM admission_checked
ORDER BY section,records DESC,dimensions;
