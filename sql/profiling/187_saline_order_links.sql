-- Cross-order DIAGNOSTIC, not an infusion reconstruction rule.
-- Exact prescription-name candidates only. Neither common POE nor temporal
-- proximity proves continuity. POE discontinue pointers describe order actions,
-- never actual administration stop times. No NULL POE is pooled into a stream.
-- Events with unknown statuses remain controls; ties/omissions remain visible.
WITH prescription_source AS MATERIALIZED (
    SELECT pharmacy_id, subject_id, hadm_id, nullif(trim(poe_id), '') AS poe_id
    FROM mimiciv_hosp.prescriptions
    WHERE drug = 'Sodium Chloride 3% (Hypertonic)'
), rx AS MATERIALIZED (
    SELECT pharmacy_id, min(subject_id) AS order_subject, min(hadm_id) AS order_hadm,
           count(*) AS prescription_rows, count(DISTINCT subject_id) AS subjects,
           count(DISTINCT hadm_id) AS admissions,
           count(*) FILTER (WHERE subject_id IS NULL OR hadm_id IS NULL) AS missing_ids,
           count(DISTINCT nullif(trim(poe_id), '')) AS rx_poe_count,
           count(*) FILTER (WHERE nullif(trim(poe_id), '') IS NULL) AS missing_rx_poe,
           min(nullif(trim(poe_id), '')) AS rx_poe
    FROM prescription_source
    GROUP BY pharmacy_id
), orders AS MATERIALIZED (
    SELECT r.*, p.pharmacy_id IS NOT NULL AS pharmacy_found,
           p.subject_id AS pharmacy_subject, p.hadm_id AS pharmacy_hadm,
           nullif(trim(p.poe_id), '') AS pharmacy_poe,
           p.subject_id = r.order_subject AND p.hadm_id = r.order_hadm AS pharmacy_identity_ok
    FROM rx r LEFT JOIN LATERAL (
        SELECT p.pharmacy_id, p.subject_id, p.hadm_id, p.poe_id
        FROM mimiciv_hosp.pharmacy p WHERE p.pharmacy_id = r.pharmacy_id OFFSET 0
    ) p ON true
), event_base AS MATERIALIZED (
    SELECT e.emar_id, e.subject_id, e.hadm_id, e.pharmacy_id, e.event_txt, e.charttime,
           nullif(trim(e.poe_id), '') AS event_poe, o.rx_poe_count, o.missing_rx_poe,
           o.rx_poe, o.pharmacy_poe, o.pharmacy_found, o.pharmacy_identity_ok,
           (e.subject_id IS NOT NULL AND e.hadm_id IS NOT NULL
            AND e.subject_id = o.order_subject AND e.hadm_id = o.order_hadm
            AND o.subjects = 1 AND o.admissions = 1 AND o.missing_ids = 0) AS identity_ok
    FROM orders o JOIN LATERAL (
        SELECT e.emar_id, e.subject_id, e.hadm_id, e.pharmacy_id, e.poe_id,
               e.event_txt, e.charttime
        FROM mimiciv_hosp.emar e WHERE e.pharmacy_id = o.pharmacy_id OFFSET 0
    ) e ON true
), events AS MATERIALIZED (
    SELECT e.*, p.poe_id IS NOT NULL AS poe_found,
           p.subject_id = e.subject_id AND p.hadm_id = e.hadm_id AS poe_identity_ok,
           (e.identity_ok AND e.pharmacy_identity_ok
            AND e.event_poe IS NOT NULL AND e.rx_poe_count = 1 AND e.missing_rx_poe = 0
            AND e.event_poe = e.rx_poe AND e.event_poe = e.pharmacy_poe
            AND p.subject_id = e.subject_id AND p.hadm_id = e.hadm_id) IS TRUE AS poe_link_ok
    FROM event_base e LEFT JOIN LATERAL (
        SELECT p.poe_id, p.subject_id, p.hadm_id
        FROM mimiciv_hosp.poe p WHERE p.poe_id = e.event_poe OFFSET 0
    ) p ON true
), pharmacy_issues AS MATERIALIZED (
    SELECT pharmacy_id, count(*) FILTER (WHERE identity_ok IS NOT TRUE) AS excluded_identity,
           count(*) FILTER (WHERE charttime IS NULL) AS missing_time
    FROM events GROUP BY pharmacy_id
), poe_issue_rows AS MATERIALIZED (
    -- Use all three identifier hints only to FLAG omissions. A missing/wrong
    -- eMAR POE in an otherwise associated pharmacy must not silently disappear
    -- and leave an apparently clean same-POE endpoint. No extra event is merged.
    SELECT event_poe AS issue_poe, emar_id, poe_link_ok, charttime FROM events WHERE event_poe IS NOT NULL
    UNION SELECT rx_poe, emar_id, poe_link_ok, charttime FROM events WHERE rx_poe IS NOT NULL
    UNION SELECT pharmacy_poe, emar_id, poe_link_ok, charttime FROM events WHERE pharmacy_poe IS NOT NULL
), poe_issues AS MATERIALIZED (
    SELECT issue_poe AS event_poe, count(*) FILTER (WHERE poe_link_ok IS NOT TRUE) AS excluded_identity,
           count(*) FILTER (WHERE charttime IS NULL) AS missing_time
    FROM poe_issue_rows GROUP BY issue_poe
), admission_issues AS MATERIALIZED (
    SELECT subject_id, hadm_id, count(*) FILTER (WHERE identity_ok IS NOT TRUE) AS excluded_identity,
           count(*) FILTER (WHERE charttime IS NULL) AS missing_time
    FROM events WHERE subject_id IS NOT NULL AND hadm_id IS NOT NULL
    GROUP BY subject_id, hadm_id
), stream_events AS MATERIALIZED (
    SELECT 'pharmacy'::text AS stream_kind, e.pharmacy_id::text AS stream_key,
           e.*, i.excluded_identity, i.missing_time
    FROM events e JOIN pharmacy_issues i USING (pharmacy_id)
    WHERE e.identity_ok AND e.charttime IS NOT NULL
    UNION ALL
    SELECT 'poe', e.event_poe, e.*, i.excluded_identity, i.missing_time
    FROM events e JOIN poe_issues i USING (event_poe)
    WHERE e.poe_link_ok AND e.charttime IS NOT NULL
    UNION ALL
    SELECT 'admission_temporal_only', e.hadm_id::text, e.*, i.excluded_identity, i.missing_time
    FROM events e JOIN admission_issues i USING (subject_id, hadm_id)
    WHERE e.identity_ok AND e.charttime IS NOT NULL
), numbered AS MATERIALIZED (
    SELECT s.*, row_number() OVER w AS position,
           count(*) OVER (PARTITION BY stream_kind, stream_key, subject_id, hadm_id, charttime) AS simultaneous
    FROM stream_events s
    WINDOW w AS (PARTITION BY stream_kind, stream_key, subject_id, hadm_id ORDER BY charttime, emar_id)
), sequenced AS MATERIALIZED (
    SELECT s.*, min(position) FILTER (WHERE event_txt IS DISTINCT FROM 'Confirmed') OVER
             (PARTITION BY stream_kind, stream_key, subject_id, hadm_id ORDER BY position
              ROWS BETWEEN 1 FOLLOWING AND UNBOUNDED FOLLOWING) AS next_control,
           sum((simultaneous > 1)::integer) OVER
             (PARTITION BY stream_kind, stream_key, subject_id, hadm_id ORDER BY position) AS ties_through
    FROM numbered s
), endpoints AS MATERIALIZED (
    SELECT s.*, c.emar_id AS end_key, c.event_txt AS end_status,
           c.pharmacy_id AS end_pharmacy, c.charttime AS end_time,
           c.ties_through - s.ties_through + (s.simultaneous > 1)::integer AS segment_tied_rows
    FROM sequenced s LEFT JOIN sequenced c
      ON c.stream_kind = s.stream_kind AND c.stream_key = s.stream_key
     AND c.subject_id = s.subject_id AND c.hadm_id = s.hadm_id AND c.position = s.next_control
    WHERE s.event_txt IN ('Started', 'Delayed Started', 'Restarted')
), comparison AS MATERIALIZED (
    SELECT p.*, q.emar_id IS NOT NULL AS poe_stream_eligible,
           q.end_key AS poe_end_key, q.end_status AS poe_end_status,
           q.end_pharmacy AS poe_end_pharmacy, q.segment_tied_rows AS poe_tied_rows,
           q.excluded_identity AS poe_excluded_identity, q.missing_time AS poe_missing_time,
           a.end_key AS admission_end_key, a.end_status AS admission_end_status,
           a.end_pharmacy AS admission_end_pharmacy, a.segment_tied_rows AS admission_tied_rows
    FROM endpoints p LEFT JOIN endpoints q ON q.emar_id = p.emar_id AND q.stream_kind = 'poe'
    LEFT JOIN endpoints a ON a.emar_id = p.emar_id AND a.stream_kind = 'admission_temporal_only'
    WHERE p.stream_kind = 'pharmacy'
), order_poe_groups AS MATERIALIZED (
    SELECT rx_poe, count(*) AS pharmacy_ids, count(DISTINCT order_subject) AS subjects,
           count(DISTINCT order_hadm) AS admissions,
           count(*) FILTER (WHERE subjects <> 1 OR admissions <> 1 OR missing_ids > 0) AS bad_order_identity
    FROM orders WHERE rx_poe_count = 1 AND missing_rx_poe = 0 GROUP BY rx_poe
), poe_keys AS MATERIALIZED (
    SELECT poe_id FROM prescription_source WHERE poe_id IS NOT NULL
    UNION SELECT pharmacy_poe FROM orders WHERE pharmacy_poe IS NOT NULL
    UNION SELECT event_poe FROM events WHERE event_poe IS NOT NULL
), poe_rows AS MATERIALIZED (
    SELECT k.poe_id AS candidate_key, p.*
    FROM poe_keys k LEFT JOIN LATERAL (
        SELECT p.poe_id, p.subject_id, p.hadm_id, p.transaction_type,
               p.discontinue_of_poe_id, p.discontinued_by_poe_id
        FROM mimiciv_hosp.poe p WHERE p.poe_id = k.poe_id OFFSET 0
    ) p ON true
), poe_links AS MATERIALIZED (
    SELECT p.subject_id, p.hadm_id, p.poe_id, x.direction, x.target,
           q.poe_id IS NOT NULL AS target_found, q.transaction_type AS target_transaction,
           q.subject_id = p.subject_id AND q.hadm_id = p.hadm_id AS target_identity_ok,
           q.subject_id IS NULL OR q.hadm_id IS NULL AS target_missing_identity,
           coalesce(g.pharmacy_ids, 0) AS target_candidate_pharmacies
    FROM poe_rows p CROSS JOIN LATERAL (VALUES
        ('discontinue_of', nullif(trim(p.discontinue_of_poe_id), '')),
        ('discontinued_by', nullif(trim(p.discontinued_by_poe_id), ''))
    ) x(direction, target)
    LEFT JOIN LATERAL (
        SELECT q.poe_id, q.subject_id, q.hadm_id, q.transaction_type
        FROM mimiciv_hosp.poe q WHERE q.poe_id = x.target OFFSET 0
    ) q ON true
    LEFT JOIN order_poe_groups g ON g.rx_poe = x.target
    WHERE p.poe_id IS NOT NULL AND x.target IS NOT NULL
), poe_expanded AS MATERIALIZED (
    -- Coverage only. Additional heads are NOT promoted into any endpoint stream.
    SELECT p.subject_id AS order_subject, p.hadm_id AS order_hadm,
           e.subject_id, e.hadm_id, e.event_txt, e.pharmacy_id,
           o.pharmacy_id IS NOT NULL AS candidate_pharmacy,
           e.subject_id = p.subject_id AND e.hadm_id = p.hadm_id AS identity_ok
    FROM poe_rows p JOIN LATERAL (
        SELECT e.subject_id, e.hadm_id, e.event_txt, e.pharmacy_id
        FROM mimiciv_hosp.emar e WHERE e.poe_id = p.poe_id OFFSET 0
    ) e ON true
    LEFT JOIN orders o ON o.pharmacy_id = e.pharmacy_id
    WHERE p.poe_id IS NOT NULL
)
SELECT 'order_poe_consistency' AS section,
       jsonb_build_object('rx_poe_count', rx_poe_count, 'missing_rx_poe', missing_rx_poe > 0,
           'pharmacy_found', pharmacy_found, 'pharmacy_identity_ok', pharmacy_identity_ok,
           'missing_pharmacy_poe', pharmacy_poe IS NULL,
           'rx_matches_pharmacy_poe', rx_poe = pharmacy_poe) AS dimensions,
       count(*) AS records, jsonb_build_object('prescription_rows', sum(prescription_rows)) AS counters
FROM orders GROUP BY rx_poe_count, missing_rx_poe > 0, pharmacy_found, pharmacy_identity_ok,
    pharmacy_poe IS NULL, rx_poe = pharmacy_poe
UNION ALL
SELECT 'event_poe_consistency', jsonb_build_object('identity_ok', identity_ok,
       'missing_event_poe', event_poe IS NULL, 'event_matches_rx_poe', event_poe = rx_poe,
       'event_matches_pharmacy_poe', event_poe = pharmacy_poe, 'poe_found', poe_found,
       'poe_identity_ok', poe_identity_ok, 'poe_link_ok', poe_link_ok), count(*),
       jsonb_build_object('start_like_rows', count(*) FILTER
           (WHERE event_txt IN ('Started', 'Delayed Started', 'Restarted')))
FROM events GROUP BY identity_ok, event_poe IS NULL, event_poe = rx_poe,
    event_poe = pharmacy_poe, poe_found, poe_identity_ok, poe_link_ok
UNION ALL
SELECT 'poe_cardinality', jsonb_build_object('candidate_pharmacy_count', pharmacy_ids,
       'subject_count', subjects, 'admission_count', admissions,
       'has_bad_order_identity', bad_order_identity > 0), count(*),
       jsonb_build_object('candidate_pharmacies', sum(pharmacy_ids))
FROM order_poe_groups GROUP BY pharmacy_ids, subjects, admissions, bad_order_identity > 0
UNION ALL
SELECT 'stream_endpoint', jsonb_build_object('stream_kind', stream_kind,
       'start', event_txt, 'next_control', end_status, 'has_next_control', end_key IS NOT NULL,
       'changes_pharmacy', end_pharmacy IS DISTINCT FROM pharmacy_id AND end_key IS NOT NULL,
       'has_ties', segment_tied_rows > 0, 'has_excluded_records', excluded_identity > 0,
       'has_missing_time', missing_time > 0), count(*),
       jsonb_build_object('subjects', count(DISTINCT subject_id), 'admissions', count(DISTINCT hadm_id),
           'hours_min', min(extract(epoch FROM (end_time-charttime))/3600),
           'hours_max', max(extract(epoch FROM (end_time-charttime))/3600))
FROM endpoints GROUP BY stream_kind, event_txt, end_status, end_key IS NOT NULL,
    end_pharmacy IS DISTINCT FROM pharmacy_id AND end_key IS NOT NULL,
    segment_tied_rows > 0, excluded_identity > 0, missing_time > 0
UNION ALL
SELECT 'endpoint_comparison', jsonb_build_object('pharmacy_next', end_status,
       'pharmacy_has_control', end_key IS NOT NULL, 'poe_eligible', poe_stream_eligible,
       'poe_next', poe_end_status, 'poe_has_control', poe_end_key IS NOT NULL,
       'poe_endpoint_changed', poe_end_key IS DISTINCT FROM end_key,
       'poe_cross_pharmacy', poe_end_pharmacy IS DISTINCT FROM pharmacy_id AND poe_end_key IS NOT NULL,
       'poe_has_ties', poe_tied_rows > 0, 'poe_has_omitted_records',
           poe_excluded_identity > 0 OR poe_missing_time > 0,
       'admission_next', admission_end_status, 'admission_has_control', admission_end_key IS NOT NULL,
       'admission_cross_pharmacy', admission_end_pharmacy IS DISTINCT FROM pharmacy_id
           AND admission_end_key IS NOT NULL, 'admission_has_ties', admission_tied_rows > 0), count(*), '{}'::jsonb
FROM comparison GROUP BY end_status, end_key IS NOT NULL, poe_stream_eligible, poe_end_status,
    poe_end_key IS NOT NULL, poe_end_key IS DISTINCT FROM end_key,
    poe_end_pharmacy IS DISTINCT FROM pharmacy_id AND poe_end_key IS NOT NULL,
    poe_tied_rows > 0, poe_excluded_identity > 0 OR poe_missing_time > 0,
    admission_end_status, admission_end_key IS NOT NULL,
    admission_end_pharmacy IS DISTINCT FROM pharmacy_id AND admission_end_key IS NOT NULL,
    admission_tied_rows > 0
UNION ALL
SELECT 'poe_record_inventory', jsonb_build_object('poe_found', poe_id IS NOT NULL,
       'transaction_type', transaction_type, 'missing_identity', subject_id IS NULL OR hadm_id IS NULL),
       count(*), '{}'::jsonb
FROM poe_rows GROUP BY poe_id IS NOT NULL, transaction_type, subject_id IS NULL OR hadm_id IS NULL
UNION ALL
SELECT 'poe_discontinue_relation', jsonb_build_object('direction', direction,
       'target_found', target_found, 'target_identity_ok', target_identity_ok,
       'target_missing_identity', target_missing_identity, 'self_link', poe_id = target,
       'target_transaction', target_transaction,
       'target_has_candidate_pharmacy', target_candidate_pharmacies > 0), count(*), '{}'::jsonb
FROM poe_links GROUP BY direction, target_found, target_identity_ok, target_missing_identity,
    poe_id = target, target_transaction, target_candidate_pharmacies > 0
UNION ALL
SELECT 'same_poe_head_coverage', jsonb_build_object('identity_ok', identity_ok,
       'candidate_pharmacy', candidate_pharmacy, 'missing_pharmacy', pharmacy_id IS NULL,
       'event_txt', event_txt), count(*), '{}'::jsonb
FROM poe_expanded GROUP BY identity_ok, candidate_pharmacy, pharmacy_id IS NULL, event_txt
ORDER BY section, records DESC, dimensions;
