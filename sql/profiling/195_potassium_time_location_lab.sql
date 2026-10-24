-- D003/D004/D005 discovery audit only. This is the same fixed 1% eMAR page
-- sample and the same two trim-exact medication names used by 191/192. It is
-- not a potassium cohort, treatment episode, actual-dose rule, or non-ICU rule.
--
-- eMAR charttime is used only as an administration-record anchor. It is not a
-- validated infusion start. eMAR storetime is a documentation timestamp and is
-- not an infusion end. Prescription starttime/stoptime, completion_interval,
-- infusion_complete, and infusion-rate fields are presence diagnostics only;
-- none supplies an observed treatment endpoint in this query.
--
-- Transfer intervals are half-open [intime,outtime). The anchor point and the
-- complete [anchor-4h,anchor) context window are classified independently.
-- ICU, gap, overlap, unknown careunit, and potentially intersecting invalid
-- intervals never count as provisional non-ICU.
--
-- Pre-anchor K and creatinine samples use specimen charttime in
-- [anchor-4h,anchor). A result is available by the feature cutoff only when
-- storetime <= anchor. The four fixed Blood/Chemistry candidates are K
-- 50971/52610 and creatinine 50912/52546; none is silently omitted.
--
-- The post-anchor diagnostic is the earliest K specimen timestamp strictly
-- after charttime, with no maximum lag. Every row tied at that timestamp across
-- both K itemids is retained. It is not named or interpreted as post-infusion.
-- All joins require the same non-NULL subject/admission. No raw identifier,
-- timestamp, value, order text, or free-text detail is output.
WITH sampled AS MATERIALIZED (
    SELECT emar_id, emar_seq, subject_id, hadm_id, pharmacy_id, medication,
           event_txt, charttime, storetime
    FROM mimiciv_hosp.emar TABLESAMPLE SYSTEM (1) REPEATABLE (20261011)
), events AS MATERIALIZED (
    SELECT *, CASE
        WHEN trim(medication) = 'Potassium Chloride' THEN 'potassium_chloride'
        ELSE 'critical_care_oncology_replacement' END AS medication_scope
    FROM sampled
    WHERE trim(medication) IN (
        'Potassium Chloride',
        'Potassium Chloride Replacement (Critical Care and Oncology)'
    )
), valid_anchors AS MATERIALIZED (
    SELECT * FROM events
    WHERE subject_id IS NOT NULL AND hadm_id IS NOT NULL AND charttime IS NOT NULL
), detail_time_shapes AS MATERIALIZED (
    SELECT e.emar_id AS event_key,
           count(d.emar_id) AS detail_rows,
           count(*) FILTER (WHERE d.emar_id IS NOT NULL
                             AND d.parent_field_ordinal IS NULL) AS parent_rows,
           count(*) FILTER (WHERE d.parent_field_ordinal IS NOT NULL) AS product_rows,
           count(*) FILTER (WHERE nullif(trim(d.completion_interval), '') IS NOT NULL)
               AS completion_interval_rows,
           count(*) FILTER (WHERE nullif(trim(d.infusion_complete), '') IS NOT NULL)
               AS infusion_complete_nonempty_rows,
           count(*) FILTER (WHERE upper(trim(d.infusion_complete)) IN ('Y','YES'))
               AS infusion_complete_yes_rows,
           count(*) FILTER (WHERE nullif(trim(d.infusion_rate), '') IS NOT NULL)
               AS infusion_rate_rows,
           count(*) FILTER (WHERE nullif(trim(d.prior_infusion_rate), '') IS NOT NULL)
               AS prior_infusion_rate_rows,
           count(*) FILTER (WHERE d.emar_id IS NOT NULL AND
               (d.subject_id IS DISTINCT FROM e.subject_id
                OR d.emar_seq IS DISTINCT FROM e.emar_seq)) AS detail_identity_issue_rows
    -- The source inventory has no emar_detail(emar_id) index. A single ordinary
    -- scan/hash join is therefore intentional; a per-event LATERAL would repeat
    -- that full scan for every selected head.
    FROM events e LEFT JOIN mimiciv_hosp.emar_detail d ON d.emar_id=e.emar_id
    GROUP BY e.emar_id
), pharmacy_keys AS MATERIALIZED (
    SELECT DISTINCT pharmacy_id FROM events WHERE pharmacy_id IS NOT NULL
), prescription_time_rows AS MATERIALIZED (
    SELECT p.pharmacy_id, p.subject_id, p.hadm_id, p.starttime, p.stoptime
    FROM pharmacy_keys k
    JOIN LATERAL (
        SELECT pharmacy_id, subject_id, hadm_id, starttime, stoptime
        FROM mimiciv_hosp.prescriptions p
        WHERE p.pharmacy_id = k.pharmacy_id OFFSET 0
    ) p ON true
), prescription_time_shapes AS MATERIALIZED (
    SELECT pharmacy_id, count(*) AS prescription_rows,
           count(DISTINCT subject_id) AS order_subjects,
           count(DISTINCT hadm_id) AS order_admissions,
           count(*) FILTER (WHERE subject_id IS NULL OR hadm_id IS NULL) AS missing_order_ids,
           min(subject_id) AS order_subject_id, min(hadm_id) AS order_hadm_id,
           count(*) FILTER (WHERE starttime IS NOT NULL) AS starttime_rows,
           count(*) FILTER (WHERE stoptime IS NOT NULL) AS stoptime_rows,
           count(DISTINCT starttime) AS distinct_starttimes,
           count(DISTINCT stoptime) AS distinct_stoptimes,
           count(*) FILTER (WHERE starttime IS NOT NULL AND stoptime IS NOT NULL
                             AND stoptime <= starttime) AS nonpositive_order_intervals
    FROM prescription_time_rows GROUP BY pharmacy_id
), time_fields AS MATERIALIZED (
    SELECT e.*, d.*,
           coalesce(o.prescription_rows, 0) AS prescription_rows,
           coalesce(o.starttime_rows, 0) AS starttime_rows,
           coalesce(o.stoptime_rows, 0) AS stoptime_rows,
           coalesce(o.distinct_starttimes, 0) AS distinct_starttimes,
           coalesce(o.distinct_stoptimes, 0) AS distinct_stoptimes,
           coalesce(o.nonpositive_order_intervals, 0) AS nonpositive_order_intervals,
           CASE WHEN e.pharmacy_id IS NULL THEN 'missing_pharmacy_key'
                WHEN o.pharmacy_id IS NULL THEN 'prescription_not_found'
                WHEN e.subject_id IS NULL OR e.hadm_id IS NULL THEN 'missing_event_identity'
                WHEN o.order_subjects <> 1 OR o.order_admissions <> 1
                  OR o.missing_order_ids > 0 THEN 'ambiguous_order_identity'
                WHEN e.subject_id IS DISTINCT FROM o.order_subject_id
                  OR e.hadm_id IS DISTINCT FROM o.order_hadm_id THEN 'identity_conflict'
                ELSE 'identity_consistent' END AS order_link_status
    FROM events e JOIN detail_time_shapes d ON d.event_key = e.emar_id
    LEFT JOIN prescription_time_shapes o USING (pharmacy_id)
), icu_units(careunit) AS (
    VALUES ('Cardiac Vascular Intensive Care Unit (CVICU)'),
           ('Coronary Care Unit (CCU)'), ('Intensive Care Unit (ICU)'),
           ('Medical Intensive Care Unit (MICU)'),
           ('Medical/Surgical Intensive Care Unit (MICU/SICU)'),
           ('Neuro Surgical Intensive Care Unit (Neuro SICU)'),
           ('Surgical Intensive Care Unit (SICU)'), ('Trauma SICU (TSICU)')
), anchor_admissions AS MATERIALIZED (
    SELECT DISTINCT subject_id, hadm_id FROM valid_anchors
), admission_transfers AS MATERIALIZED (
    SELECT a.subject_id, a.hadm_id, t.careunit, t.intime, t.outtime,
           (t.intime IS NOT NULL AND t.outtime IS NOT NULL
             AND t.outtime > t.intime) AS valid_interval,
           u.careunit IS NOT NULL AS is_icu,
           (u.careunit IS NULL AND nullif(trim(t.careunit), '') IS NOT NULL
             AND upper(trim(t.careunit)) <> 'UNKNOWN') AS is_named_non_icu
    FROM anchor_admissions a JOIN mimiciv_hosp.transfers t
      ON t.subject_id = a.subject_id AND t.hadm_id = a.hadm_id
    LEFT JOIN icu_units u ON u.careunit = t.careunit
    WHERE t.eventtype IS DISTINCT FROM 'discharge'
), anchor_points_base AS MATERIALIZED (
    SELECT a.emar_id,
           count(*) FILTER (WHERE t.valid_interval
              AND a.charttime >= t.intime AND a.charttime < t.outtime) AS active_intervals,
           count(*) FILTER (WHERE t.valid_interval AND t.is_icu
              AND a.charttime >= t.intime AND a.charttime < t.outtime) AS active_icu_intervals,
           count(*) FILTER (WHERE t.valid_interval AND t.is_named_non_icu
              AND a.charttime >= t.intime AND a.charttime < t.outtime)
              AS active_named_non_icu_intervals,
           count(*) FILTER (WHERE t.valid_interval IS FALSE AND
              (t.intime IS NULL OR t.outtime IS NULL OR
               (a.charttime >= least(t.intime,t.outtime)
                AND a.charttime <= greatest(t.intime,t.outtime)))) AS invalid_at_anchor_rows
    FROM valid_anchors a LEFT JOIN admission_transfers t
      ON t.subject_id = a.subject_id AND t.hadm_id = a.hadm_id
    GROUP BY a.emar_id
), anchor_points AS MATERIALIZED (
    SELECT a.emar_id, b.active_intervals, b.active_icu_intervals,
           b.active_named_non_icu_intervals, b.invalid_at_anchor_rows,
           CASE WHEN b.invalid_at_anchor_rows > 0 THEN 'potential_invalid_transfer'
                WHEN b.active_intervals = 0 THEN 'gap_no_active_interval'
                WHEN b.active_intervals > 1 THEN 'overlap_multiple_active_intervals'
                WHEN b.active_icu_intervals = 1 THEN 'icu'
                WHEN b.active_named_non_icu_intervals = 1 THEN 'non_icu_provisional'
                ELSE 'unknown_careunit' END AS anchor_point_status
    FROM valid_anchors a JOIN anchor_points_base b USING (emar_id)
), context_windows AS MATERIALIZED (
    SELECT emar_id, subject_id, hadm_id, charttime - interval '4 hours' AS window_start,
           charttime AS window_end
    FROM valid_anchors
), cutpoints AS MATERIALIZED (
    SELECT emar_id, window_start AS cutpoint FROM context_windows
    UNION
    SELECT emar_id, window_end FROM context_windows
    UNION
    SELECT w.emar_id, greatest(w.window_start, t.intime)
    FROM context_windows w JOIN admission_transfers t USING (subject_id, hadm_id)
    WHERE t.valid_interval AND t.intime < w.window_end AND t.outtime > w.window_start
    UNION
    SELECT w.emar_id, least(w.window_end, t.outtime)
    FROM context_windows w JOIN admission_transfers t USING (subject_id, hadm_id)
    WHERE t.valid_interval AND t.intime < w.window_end AND t.outtime > w.window_start
), atoms_base AS MATERIALIZED (
    SELECT emar_id, cutpoint AS atom_start,
           lead(cutpoint) OVER (PARTITION BY emar_id ORDER BY cutpoint) AS atom_end
    FROM cutpoints
), atoms AS MATERIALIZED (
    SELECT w.emar_id, extract(epoch FROM (b.atom_end-b.atom_start)) AS seconds,
           count(*) FILTER (WHERE t.valid_interval) AS active_intervals,
           count(*) FILTER (WHERE t.valid_interval AND t.is_icu) AS active_icu_intervals,
           count(*) FILTER (WHERE t.valid_interval AND t.is_named_non_icu)
               AS active_named_non_icu_intervals
    FROM atoms_base b JOIN context_windows w USING (emar_id)
    LEFT JOIN admission_transfers t
      ON t.subject_id = w.subject_id AND t.hadm_id = w.hadm_id
     AND t.valid_interval AND t.intime <= b.atom_start AND t.outtime >= b.atom_end
    WHERE b.atom_end > b.atom_start
    GROUP BY w.emar_id, b.atom_start, b.atom_end
), atom_summary AS MATERIALIZED (
    SELECT emar_id, sum(seconds) AS evaluated_seconds,
           coalesce(sum(seconds) FILTER (WHERE active_intervals=0),0) AS gap_seconds,
           coalesce(sum(seconds) FILTER (WHERE active_intervals>1),0) AS overlap_seconds,
           coalesce(sum(seconds) FILTER (WHERE active_icu_intervals>0),0) AS icu_seconds,
           coalesce(sum(seconds) FILTER (WHERE active_intervals=1
               AND active_icu_intervals=0 AND active_named_non_icu_intervals=0),0)
               AS unknown_unit_seconds,
           coalesce(sum(seconds) FILTER (WHERE active_intervals=1
               AND active_named_non_icu_intervals=1),0) AS single_named_non_icu_seconds
    FROM atoms GROUP BY emar_id
), invalid_window_summary AS MATERIALIZED (
    SELECT w.emar_id,
           count(*) FILTER (WHERE t.valid_interval IS FALSE) AS invalid_admission_rows,
           count(*) FILTER (WHERE t.valid_interval IS FALSE AND
             (t.intime IS NULL OR t.outtime IS NULL OR
              (greatest(t.intime,t.outtime) >= w.window_start
               AND least(t.intime,t.outtime) < w.window_end)))
               AS potentially_intersecting_invalid_rows
    FROM context_windows w LEFT JOIN admission_transfers t USING (subject_id,hadm_id)
    GROUP BY w.emar_id
), window_locations AS MATERIALIZED (
    SELECT w.emar_id, a.evaluated_seconds, a.gap_seconds, a.overlap_seconds,
           a.icu_seconds, a.unknown_unit_seconds, a.single_named_non_icu_seconds,
           i.invalid_admission_rows, i.potentially_intersecting_invalid_rows,
           CASE WHEN a.icu_seconds > 0 THEN 'contains_icu'
                WHEN a.overlap_seconds > 0 THEN 'contains_overlap'
                WHEN a.gap_seconds > 0 THEN 'contains_gap'
                WHEN a.unknown_unit_seconds > 0 THEN 'contains_unknown_careunit'
                WHEN i.potentially_intersecting_invalid_rows > 0
                    THEN 'potential_invalid_transfer'
                WHEN a.evaluated_seconds = 14400
                  AND a.single_named_non_icu_seconds = a.evaluated_seconds
                    THEN 'complete_single_named_non_icu_provisional'
                ELSE 'unexplained_coverage' END AS pre4h_window_status
    FROM context_windows w JOIN atom_summary a USING (emar_id)
    JOIN invalid_window_summary i USING (emar_id)
), rare_labs AS MATERIALIZED (
    -- 52610/52546 have no matching subject/admission/time index in the saved
    -- source inventory. Scan their rows once, restricted to sampled admissions,
    -- rather than repeating a charttime-only bitmap scan for every anchor.
    SELECT l.labevent_id,l.subject_id,l.hadm_id,l.itemid,l.charttime,l.storetime,
           l.valuenum,l.valueuom
    FROM mimiciv_hosp.labevents l JOIN anchor_admissions a
      ON a.subject_id=l.subject_id AND a.hadm_id=l.hadm_id
    WHERE l.itemid IN (52610,52546)
), common_pre_labs AS MATERIALIZED (
    -- Constants expose the two existing partial indexes to the planner.
    SELECT a.emar_id,a.subject_id,a.hadm_id,a.charttime AS anchor_time,
           'potassium'::text AS concept,l.labevent_id,l.itemid,l.charttime,
           l.storetime,l.valuenum,l.valueuom
    FROM valid_anchors a CROSS JOIN LATERAL (
        SELECT labevent_id,itemid,charttime,storetime,valuenum,valueuom
        FROM mimiciv_hosp.labevents l
        WHERE l.subject_id=a.subject_id AND l.hadm_id=a.hadm_id
          AND l.itemid=50971
          AND l.charttime>=a.charttime-interval '4 hours'
          AND l.charttime<a.charttime OFFSET 0
    ) l
    UNION ALL
    SELECT a.emar_id,a.subject_id,a.hadm_id,a.charttime,
           'creatinine'::text,l.labevent_id,l.itemid,l.charttime,
           l.storetime,l.valuenum,l.valueuom
    FROM valid_anchors a CROSS JOIN LATERAL (
        SELECT labevent_id,itemid,charttime,storetime,valuenum,valueuom
        FROM mimiciv_hosp.labevents l
        WHERE l.subject_id=a.subject_id AND l.hadm_id=a.hadm_id
          AND l.itemid=50912
          AND l.charttime>=a.charttime-interval '4 hours'
          AND l.charttime<a.charttime OFFSET 0
    ) l
), rare_pre_labs AS MATERIALIZED (
    SELECT a.emar_id, a.subject_id, a.hadm_id, a.charttime AS anchor_time,
           CASE WHEN l.itemid=52610 THEN 'potassium'::text ELSE 'creatinine'::text END,
           l.labevent_id,l.itemid,l.charttime,l.storetime,l.valuenum,l.valueuom
    FROM valid_anchors a JOIN rare_labs l
      ON l.subject_id=a.subject_id AND l.hadm_id=a.hadm_id
     AND l.charttime>=a.charttime-interval '4 hours' AND l.charttime<a.charttime
), pre_labs AS MATERIALIZED (
    SELECT * FROM common_pre_labs
    UNION ALL
    SELECT * FROM rare_pre_labs
), pre_times AS MATERIALIZED (
    SELECT emar_id, concept, max(charttime) AS latest_sample_time,
           max(charttime) FILTER (WHERE storetime <= anchor_time) AS latest_available_time
    FROM pre_labs GROUP BY emar_id,concept
), pre_counts AS MATERIALIZED (
    SELECT p.emar_id,p.concept,count(*) AS window_rows,
           count(*) FILTER (WHERE p.storetime <= p.anchor_time) AS available_rows,
           count(*) FILTER (WHERE p.storetime > p.anchor_time) AS delayed_rows,
           count(*) FILTER (WHERE p.storetime IS NULL) AS missing_storetime_rows,
           count(*) FILTER (WHERE p.storetime < p.charttime) AS reversed_storetime_rows,
           count(*) FILTER (WHERE p.charttime=t.latest_sample_time) AS latest_sample_rows,
           count(*) FILTER (WHERE p.charttime=t.latest_available_time
                             AND p.storetime <= p.anchor_time) AS latest_available_rows
    FROM pre_labs p JOIN pre_times t USING (emar_id,concept)
    GROUP BY p.emar_id,p.concept
), anchor_concepts AS MATERIALIZED (
    SELECT a.*,c.concept FROM valid_anchors a
    CROSS JOIN (VALUES ('potassium'::text),('creatinine')) c(concept)
), pre_coverage AS MATERIALIZED (
    SELECT a.*,p.anchor_point_status,w.pre4h_window_status,
           coalesce(c.window_rows,0) AS window_rows,
           coalesce(c.available_rows,0) AS available_rows,
           coalesce(c.delayed_rows,0) AS delayed_rows,
           coalesce(c.missing_storetime_rows,0) AS missing_storetime_rows,
           coalesce(c.reversed_storetime_rows,0) AS reversed_storetime_rows,
           coalesce(c.latest_sample_rows,0) AS latest_sample_rows,
           coalesce(c.latest_available_rows,0) AS latest_available_rows
    FROM anchor_concepts a JOIN anchor_points p USING (emar_id)
    JOIN window_locations w USING (emar_id)
    LEFT JOIN pre_counts c USING (emar_id,concept)
), common_post_times AS MATERIALIZED (
    SELECT a.emar_id,a.subject_id,a.hadm_id,a.charttime AS anchor_time,
           (SELECT l.charttime FROM mimiciv_hosp.labevents l
            WHERE l.subject_id=a.subject_id AND l.hadm_id=a.hadm_id
              AND l.itemid=50971 AND l.charttime>a.charttime
            ORDER BY l.charttime LIMIT 1) AS common_next_time
    FROM valid_anchors a
), rare_post_times AS MATERIALIZED (
    SELECT a.emar_id,min(l.charttime) AS rare_next_time
    FROM valid_anchors a LEFT JOIN rare_labs l
      ON l.subject_id=a.subject_id AND l.hadm_id=a.hadm_id
     AND l.itemid=52610 AND l.charttime>a.charttime
    GROUP BY a.emar_id
), post_times AS MATERIALIZED (
    SELECT c.emar_id,c.subject_id,c.hadm_id,c.anchor_time,
           CASE WHEN c.common_next_time IS NULL THEN r.rare_next_time
                WHEN r.rare_next_time IS NULL THEN c.common_next_time
                ELSE least(c.common_next_time,r.rare_next_time) END AS next_sample_time
    FROM common_post_times c JOIN rare_post_times r USING (emar_id)
), common_post_labs AS MATERIALIZED (
    SELECT p.emar_id,p.anchor_time,p.next_sample_time,l.labevent_id,l.itemid,
           l.charttime,l.storetime,l.valuenum,l.valueuom
    FROM post_times p CROSS JOIN LATERAL (
        SELECT labevent_id,itemid,charttime,storetime,valuenum,valueuom
        FROM mimiciv_hosp.labevents l
        WHERE l.subject_id=p.subject_id AND l.hadm_id=p.hadm_id
          AND l.itemid=50971
          AND l.charttime=p.next_sample_time OFFSET 0
    ) l
), rare_post_labs AS MATERIALIZED (
    SELECT p.emar_id,p.anchor_time,p.next_sample_time,l.labevent_id,l.itemid,
           l.charttime,l.storetime,l.valuenum,l.valueuom
    FROM post_times p JOIN rare_labs l
      ON l.subject_id=p.subject_id AND l.hadm_id=p.hadm_id
     AND l.itemid=52610 AND l.charttime=p.next_sample_time
), post_labs AS MATERIALIZED (
    SELECT * FROM common_post_labs
    UNION ALL
    SELECT * FROM rare_post_labs
), post_counts AS MATERIALIZED (
    SELECT emar_id,count(*) AS lab_rows,
           count(*) FILTER (WHERE valuenum IS NULL) AS missing_valuenum_rows,
           count(*) FILTER (WHERE valuenum::text IN ('NaN','Infinity','-Infinity'))
               AS nonfinite_valuenum_rows,
           count(*) FILTER (WHERE storetime IS NULL) AS missing_storetime_rows,
           count(*) FILTER (WHERE storetime < charttime) AS reversed_storetime_rows,
           count(DISTINCT itemid) AS distinct_itemids,
           count(DISTINCT valueuom) AS distinct_nonnull_units
    FROM post_labs GROUP BY emar_id
), post_coverage AS MATERIALIZED (
    SELECT a.*,p.anchor_point_status,w.pre4h_window_status,t.next_sample_time,
           coalesce(c.lab_rows,0) AS lab_rows,
           coalesce(c.missing_valuenum_rows,0) AS missing_valuenum_rows,
           coalesce(c.nonfinite_valuenum_rows,0) AS nonfinite_valuenum_rows,
           coalesce(c.missing_storetime_rows,0) AS missing_storetime_rows,
           coalesce(c.reversed_storetime_rows,0) AS reversed_storetime_rows,
           coalesce(c.distinct_itemids,0) AS distinct_itemids,
           coalesce(c.distinct_nonnull_units,0) AS distinct_nonnull_units
    FROM valid_anchors a JOIN anchor_points p USING (emar_id)
    JOIN window_locations w USING (emar_id)
    JOIN post_times t USING (emar_id)
    LEFT JOIN post_counts c USING (emar_id)
), profiles AS (
    SELECT 'sample_summary'::text AS profile_section,
           jsonb_build_object('selection','same two trim-exact names and fixed SYSTEM 1% sample as 191/192') AS dimensions,
           count(*) AS source_rows,count(DISTINCT emar_id) AS emar_events,
           jsonb_build_object('sampled_emar_rows',(SELECT count(*) FROM sampled),
             'selected_heads',count(*),'valid_identity_and_time_anchors',
                count(*) FILTER (WHERE subject_id IS NOT NULL AND hadm_id IS NOT NULL AND charttime IS NOT NULL),
             'complete_detail_rows',(SELECT coalesce(sum(detail_rows),0) FROM detail_time_shapes),
             'matched_prescription_rows',(SELECT count(*) FROM prescription_time_rows)) AS counters
    FROM events
    UNION ALL
    SELECT 'anchor_time_inventory',
           jsonb_build_object('medication_scope',medication_scope,'event_txt',event_txt,
             'identity_status',CASE WHEN subject_id IS NULL AND hadm_id IS NULL THEN 'missing_subject_and_hadm'
                WHEN subject_id IS NULL THEN 'missing_subject' WHEN hadm_id IS NULL THEN 'missing_hadm'
                ELSE 'identity_present' END,
             'charttime_missing',charttime IS NULL,
             'storetime_class',CASE WHEN storetime IS NULL THEN 'missing'
                WHEN charttime IS NULL THEN 'present_anchor_missing'
                WHEN storetime<charttime THEN 'before_anchor'
                WHEN storetime=charttime THEN 'equal_anchor' ELSE 'after_anchor' END),
           count(*),count(DISTINCT emar_id),
           jsonb_build_object('subjects',count(DISTINCT subject_id),'admissions',count(DISTINCT hadm_id))
    FROM events GROUP BY medication_scope,event_txt,
      CASE WHEN subject_id IS NULL AND hadm_id IS NULL THEN 'missing_subject_and_hadm'
           WHEN subject_id IS NULL THEN 'missing_subject' WHEN hadm_id IS NULL THEN 'missing_hadm'
           ELSE 'identity_present' END,charttime IS NULL,
      CASE WHEN storetime IS NULL THEN 'missing' WHEN charttime IS NULL THEN 'present_anchor_missing'
           WHEN storetime<charttime THEN 'before_anchor' WHEN storetime=charttime THEN 'equal_anchor'
           ELSE 'after_anchor' END
    UNION ALL
    SELECT 'time_field_diagnostics',
           jsonb_build_object('event_txt',event_txt,'order_link_status',order_link_status,
             'has_completion_interval',completion_interval_rows>0,
             'has_infusion_complete_flag',infusion_complete_nonempty_rows>0,
             'has_infusion_rate',infusion_rate_rows>0,
             'has_prescription_starttime',starttime_rows>0,
             'has_prescription_stoptime',stoptime_rows>0),
           count(*),count(DISTINCT emar_id),
           jsonb_build_object('detail_rows',sum(detail_rows),'parent_rows',sum(parent_rows),
             'product_rows',sum(product_rows),'completion_interval_rows',sum(completion_interval_rows),
             'infusion_complete_nonempty_rows',sum(infusion_complete_nonempty_rows),
             'infusion_complete_yes_rows',sum(infusion_complete_yes_rows),
             'infusion_rate_rows',sum(infusion_rate_rows),
             'prior_infusion_rate_rows',sum(prior_infusion_rate_rows),
             'detail_identity_issue_rows',sum(detail_identity_issue_rows),
             'prescription_rows',sum(prescription_rows),'distinct_starttimes',sum(distinct_starttimes),
             'distinct_stoptimes',sum(distinct_stoptimes),
             'nonpositive_order_intervals',sum(nonpositive_order_intervals))
    FROM time_fields GROUP BY event_txt,order_link_status,completion_interval_rows>0,
      infusion_complete_nonempty_rows>0,infusion_rate_rows>0,starttime_rows>0,stoptime_rows>0
    UNION ALL
    SELECT 'anchor_location',
           jsonb_build_object('event_txt',e.event_txt,'anchor_point_status',p.anchor_point_status,
             'pre4h_window_status',w.pre4h_window_status),
           count(*),count(DISTINCT e.emar_id),
           jsonb_build_object('subjects',count(DISTINCT e.subject_id),'admissions',count(DISTINCT e.hadm_id),
             'active_intervals_at_anchor',sum(p.active_intervals),
             'invalid_at_anchor_rows',sum(p.invalid_at_anchor_rows),
             'pre4h_gap_hours',sum(w.gap_seconds)/3600,
             'pre4h_overlap_hours',sum(w.overlap_seconds)/3600,
             'pre4h_icu_hours',sum(w.icu_seconds)/3600,
             'pre4h_unknown_hours',sum(w.unknown_unit_seconds)/3600,
             'pre4h_potential_invalid_rows',sum(w.potentially_intersecting_invalid_rows))
    FROM valid_anchors e JOIN anchor_points p USING (emar_id)
    JOIN window_locations w USING (emar_id)
    GROUP BY e.event_txt,p.anchor_point_status,w.pre4h_window_status
    UNION ALL
    SELECT 'pre_lab_coverage',
           jsonb_build_object('concept',concept,'event_txt',event_txt,
             'anchor_point_status',anchor_point_status,'pre4h_window_status',pre4h_window_status,
             'has_window_sample',window_rows>0,'has_available_by_anchor',available_rows>0,
             'latest_sample_has_ties',latest_sample_rows>1,
             'latest_available_has_ties',latest_available_rows>1),
           count(*),count(DISTINCT emar_id),
           jsonb_build_object('subjects',count(DISTINCT subject_id),'admissions',count(DISTINCT hadm_id),
             'window_lab_rows',sum(window_rows),'available_by_anchor_rows',sum(available_rows),
             'delayed_after_anchor_rows',sum(delayed_rows),
             'missing_storetime_rows',sum(missing_storetime_rows),
             'storetime_before_sample_rows',sum(reversed_storetime_rows),
             'latest_sample_rows',sum(latest_sample_rows),
             'latest_available_rows',sum(latest_available_rows))
    FROM pre_coverage GROUP BY concept,event_txt,anchor_point_status,pre4h_window_status,
      window_rows>0,available_rows>0,latest_sample_rows>1,latest_available_rows>1
    UNION ALL
    SELECT 'pre_lab_profile',
           jsonb_build_object('concept',p.concept,'itemid',p.itemid,'valueuom',p.valueuom,
             'availability_class',CASE WHEN p.storetime IS NULL THEN 'missing_storetime'
                WHEN p.storetime<p.charttime THEN 'storetime_before_sample'
                WHEN p.storetime<=p.anchor_time THEN 'available_by_anchor'
                ELSE 'available_after_anchor' END,
             'is_latest_sample',p.charttime=t.latest_sample_time,
             'is_latest_available',coalesce(p.charttime=t.latest_available_time
                AND p.storetime<=p.anchor_time,false)),
           count(*),count(DISTINCT p.emar_id),
           jsonb_build_object('missing_valuenum',count(*) FILTER (WHERE p.valuenum IS NULL),
             'nonfinite_valuenum',count(*) FILTER (WHERE p.valuenum::text IN ('NaN','Infinity','-Infinity')),
             'finite_valuenum',count(*) FILTER (WHERE p.valuenum IS NOT NULL
                AND p.valuenum::text NOT IN ('NaN','Infinity','-Infinity')),
             'min_sample_before_anchor_hours',min(extract(epoch FROM (p.anchor_time-p.charttime))/3600),
             'max_sample_before_anchor_hours',max(extract(epoch FROM (p.anchor_time-p.charttime))/3600),
             'min_store_minus_sample_hours',min(extract(epoch FROM (p.storetime-p.charttime))/3600),
             'max_store_minus_sample_hours',max(extract(epoch FROM (p.storetime-p.charttime))/3600))
    FROM pre_labs p JOIN pre_times t USING (emar_id,concept)
    GROUP BY p.concept,p.itemid,p.valueuom,
      CASE WHEN p.storetime IS NULL THEN 'missing_storetime'
           WHEN p.storetime<p.charttime THEN 'storetime_before_sample'
           WHEN p.storetime<=p.anchor_time THEN 'available_by_anchor' ELSE 'available_after_anchor' END,
      p.charttime=t.latest_sample_time,
      coalesce(p.charttime=t.latest_available_time AND p.storetime<=p.anchor_time,false)
    UNION ALL
    SELECT 'post_anchor_k_coverage',
           jsonb_build_object('event_txt',event_txt,'anchor_point_status',anchor_point_status,
             'pre4h_window_status',pre4h_window_status,'has_next_k_sample',lab_rows>0,
             'next_timestamp_has_ties',lab_rows>1,'multiple_itemids_at_next_time',distinct_itemids>1,
             'multiple_nonnull_units_at_next_time',distinct_nonnull_units>1),
           count(*),count(DISTINCT emar_id),
           jsonb_build_object('subjects',count(DISTINCT subject_id),'admissions',count(DISTINCT hadm_id),
             'next_timestamp_lab_rows',sum(lab_rows),'missing_valuenum_rows',sum(missing_valuenum_rows),
             'nonfinite_valuenum_rows',sum(nonfinite_valuenum_rows),
             'missing_storetime_rows',sum(missing_storetime_rows),
             'storetime_before_sample_rows',sum(reversed_storetime_rows))
    FROM post_coverage GROUP BY event_txt,anchor_point_status,pre4h_window_status,
      lab_rows>0,lab_rows>1,distinct_itemids>1,distinct_nonnull_units>1
    UNION ALL
    SELECT 'post_anchor_k_profile',
           jsonb_build_object('itemid',itemid,'valueuom',valueuom,
             'lag_bucket',CASE WHEN charttime<=anchor_time+interval '3 hours' THEN '(0,3]h'
                WHEN charttime<=anchor_time+interval '6 hours' THEN '(3,6]h'
                WHEN charttime<=anchor_time+interval '24 hours' THEN '(6,24]h' ELSE '>24h' END,
             'storetime_class',CASE WHEN storetime IS NULL THEN 'missing'
                WHEN storetime<charttime THEN 'before_sample' ELSE 'at_or_after_sample' END),
           count(*),count(DISTINCT emar_id),
           jsonb_build_object('missing_valuenum',count(*) FILTER (WHERE valuenum IS NULL),
             'nonfinite_valuenum',count(*) FILTER (WHERE valuenum::text IN ('NaN','Infinity','-Infinity')),
             'finite_valuenum',count(*) FILTER (WHERE valuenum IS NOT NULL
                AND valuenum::text NOT IN ('NaN','Infinity','-Infinity')),
             'min_anchor_to_sample_hours',min(extract(epoch FROM (charttime-anchor_time))/3600),
             'max_anchor_to_sample_hours',max(extract(epoch FROM (charttime-anchor_time))/3600),
             'min_store_minus_sample_hours',min(extract(epoch FROM (storetime-charttime))/3600),
             'max_store_minus_sample_hours',max(extract(epoch FROM (storetime-charttime))/3600))
    FROM post_labs GROUP BY itemid,valueuom,
      CASE WHEN charttime<=anchor_time+interval '3 hours' THEN '(0,3]h'
           WHEN charttime<=anchor_time+interval '6 hours' THEN '(3,6]h'
           WHEN charttime<=anchor_time+interval '24 hours' THEN '(6,24]h' ELSE '>24h' END,
      CASE WHEN storetime IS NULL THEN 'missing' WHEN storetime<charttime THEN 'before_sample'
           ELSE 'at_or_after_sample' END
)
SELECT profile_section,dimensions,source_rows,emar_events,
       counters || jsonb_build_object(
         'system_sample_percent',1.0,'sample_seed',20261011,
         'charttime_semantics','administration-record anchor; not validated infusion start',
         'storetime_semantics','documentation/result-availability timestamp by table; not treatment end',
         'pre4h_location_semantics','every atomic time segment has exactly one named non-ICU interval; contiguous changes between named non-ICU careunits are allowed',
         'lab_availability_semantics','storetime at or before anchor only; finite numeric value eligibility remains separate',
         'observed_treatment_start_defined',false,'observed_treatment_end_defined',false,
         'post_k_semantics','next specimen timestamp strictly after charttime anchor; not post-infusion',
         'formal_cohort',false,'formal_non_icu_rule',false,'formal_label_rule',false) AS counters
FROM profiles ORDER BY profile_section,source_rows DESC,dimensions;
