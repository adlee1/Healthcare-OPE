-- Explicit-order-family DIAGNOSTIC; not a treatment-episode or dose algorithm.
-- Only exact-drug candidate POE nodes with consistent pharmacy/prescription/POE
-- identity may connect. Original discontinue pointers, not temporal proximity,
-- define edges. Components do NOT establish clinical continuity.
-- Recursive UNION removes visited (origin,node) pairs over the finite candidate
-- graph; there is no silent depth truncation. Timeout means incomplete/failure.
-- Only actual eMAR charttime is sequenced. Order times never create endpoints.
-- Shared-POE heads without an exact candidate pharmacy are coverage-only.
WITH RECURSIVE rx AS MATERIALIZED (
    SELECT pharmacy_id, min(subject_id) AS order_subject, min(hadm_id) AS order_hadm,
           count(DISTINCT subject_id) AS subjects, count(DISTINCT hadm_id) AS admissions,
           count(*) FILTER (WHERE subject_id IS NULL OR hadm_id IS NULL) AS missing_ids,
           count(DISTINCT nullif(trim(poe_id), '')) AS poe_count,
           count(*) FILTER (WHERE nullif(trim(poe_id), '') IS NULL) AS missing_poe,
           min(nullif(trim(poe_id), '')) AS rx_poe
    FROM mimiciv_hosp.prescriptions WHERE drug = 'Sodium Chloride 3% (Hypertonic)'
    GROUP BY pharmacy_id
), orders AS MATERIALIZED (
    SELECT r.*, p.poe_id AS pharmacy_poe, q.transaction_type,
           (r.subjects = 1 AND r.admissions = 1 AND r.missing_ids = 0
            AND r.poe_count = 1 AND r.missing_poe = 0 AND r.rx_poe = nullif(trim(p.poe_id), '')
            AND p.subject_id = r.order_subject AND p.hadm_id = r.order_hadm
            AND q.subject_id = r.order_subject AND q.hadm_id = r.order_hadm) IS TRUE AS node_ok,
           q.discontinue_of_poe_id, q.discontinued_by_poe_id
    FROM rx r LEFT JOIN LATERAL (
        SELECT p.poe_id, p.subject_id, p.hadm_id FROM mimiciv_hosp.pharmacy p
        WHERE p.pharmacy_id = r.pharmacy_id OFFSET 0
    ) p ON true LEFT JOIN LATERAL (
        SELECT q.subject_id, q.hadm_id, q.transaction_type,
               q.discontinue_of_poe_id, q.discontinued_by_poe_id
        FROM mimiciv_hosp.poe q WHERE q.poe_id = r.rx_poe OFFSET 0
    ) q ON true
), nodes AS MATERIALIZED (
    SELECT DISTINCT rx_poe AS poe_id, order_subject AS subject_id, order_hadm AS hadm_id,
           transaction_type, discontinue_of_poe_id, discontinued_by_poe_id
    FROM orders WHERE node_ok
), raw_links AS MATERIALIZED (
    SELECT n.*, x.direction, x.target, q.poe_id IS NOT NULL AS target_found,
           q.subject_id = n.subject_id AND q.hadm_id = n.hadm_id AS target_identity_ok,
           q.subject_id IS NULL OR q.hadm_id IS NULL AS target_missing_identity,
           q.transaction_type AS target_transaction, t.poe_id IS NOT NULL AS target_is_candidate,
           t.poe_id IS NOT NULL AND t.subject_id = n.subject_id AND t.hadm_id = n.hadm_id AS usable
    FROM nodes n CROSS JOIN LATERAL (VALUES
        ('discontinue_of', nullif(trim(n.discontinue_of_poe_id), '')),
        ('discontinued_by', nullif(trim(n.discontinued_by_poe_id), ''))
    ) x(direction, target)
    LEFT JOIN LATERAL (
        SELECT q.poe_id, q.subject_id, q.hadm_id, q.transaction_type
        FROM mimiciv_hosp.poe q WHERE q.poe_id = x.target OFFSET 0
    ) q ON true LEFT JOIN nodes t ON t.poe_id = x.target
    WHERE x.target IS NOT NULL
), normalized AS MATERIALIZED (
    SELECT CASE WHEN direction = 'discontinued_by' THEN poe_id ELSE target END AS old_poe,
           CASE WHEN direction = 'discontinued_by' THEN target ELSE poe_id END AS new_poe,
           direction
    FROM raw_links WHERE usable
), edges AS MATERIALIZED (
    SELECT old_poe, new_poe, bool_or(direction = 'discontinued_by') AS has_forward,
           bool_or(direction = 'discontinue_of') AS has_backward,
           bool_or(direction = 'discontinued_by') AND bool_or(direction = 'discontinue_of') AS reciprocal
    FROM normalized GROUP BY old_poe, new_poe
), adjacency AS MATERIALIZED (
    SELECT old_poe AS a, new_poe AS b FROM edges WHERE old_poe <> new_poe
    UNION SELECT new_poe, old_poe FROM edges WHERE old_poe <> new_poe
), reach(origin, node) AS (
    SELECT poe_id, poe_id FROM nodes
    UNION
    SELECT r.origin, a.b FROM reach r JOIN adjacency a ON a.a = r.node
), components AS MATERIALIZED (
    SELECT node AS poe_id, min(origin) AS family_id FROM reach GROUP BY node
), directed_reach(origin, node) AS (
    SELECT old_poe, new_poe FROM edges WHERE old_poe <> new_poe
    UNION
    SELECT r.origin, e.new_poe FROM directed_reach r JOIN edges e ON e.old_poe = r.node
    WHERE e.old_poe <> e.new_poe
), cycle_nodes AS MATERIALIZED (
    SELECT origin AS poe_id FROM directed_reach WHERE origin = node
), degree AS MATERIALIZED (
    SELECT n.poe_id,
           (SELECT count(*) FROM edges e WHERE e.old_poe = n.poe_id AND e.old_poe <> e.new_poe) AS out_degree,
           (SELECT count(*) FROM edges e WHERE e.new_poe = n.poe_id AND e.old_poe <> e.new_poe) AS in_degree
    FROM nodes n
), family_nodes AS MATERIALIZED (
    SELECT c.family_id, count(*) AS poe_nodes,
           count(*) FILTER (WHERE y.poe_id IS NOT NULL) AS cycle_nodes,
           count(*) FILTER (WHERE d.in_degree > 1 OR d.out_degree > 1) AS branching_nodes
    FROM components c JOIN degree d USING (poe_id) LEFT JOIN cycle_nodes y USING (poe_id)
    GROUP BY c.family_id
), family_edges AS MATERIALIZED (
    SELECT c.family_id, count(*) AS edge_count,
           count(*) FILTER (WHERE e.reciprocal) AS reciprocal_edges,
           count(*) FILTER (WHERE e.old_poe = e.new_poe) AS self_edges
    FROM edges e JOIN components c ON c.poe_id = e.old_poe GROUP BY c.family_id
), event_base AS MATERIALIZED (
    SELECT e.emar_id, e.subject_id, e.hadm_id, e.pharmacy_id, e.event_txt, e.charttime,
           nullif(trim(e.poe_id), '') AS event_poe, o.rx_poe, o.pharmacy_poe,
           (e.subject_id IS NOT NULL AND e.hadm_id IS NOT NULL
            AND e.subject_id = o.order_subject AND e.hadm_id = o.order_hadm
            AND o.subjects = 1 AND o.admissions = 1 AND o.missing_ids = 0) AS identity_ok,
           o.node_ok, c.family_id
    FROM orders o JOIN LATERAL (
        SELECT e.emar_id, e.subject_id, e.hadm_id, e.pharmacy_id, e.poe_id, e.event_txt, e.charttime
        FROM mimiciv_hosp.emar e WHERE e.pharmacy_id = o.pharmacy_id OFFSET 0
    ) e ON true LEFT JOIN components c ON c.poe_id = o.rx_poe
), events AS MATERIALIZED (
    SELECT e.*, (identity_ok AND node_ok AND event_poe = rx_poe) IS TRUE AS family_eligible
    FROM event_base e
), shared_poe_heads AS MATERIALIZED (
    SELECT c.family_id, e.event_txt, e.pharmacy_id,
           e.subject_id = n.subject_id AND e.hadm_id = n.hadm_id AS identity_ok,
           o.pharmacy_id IS NOT NULL AS exact_candidate_pharmacy,
           included.emar_id IS NOT NULL AS included_in_family_stream
    FROM nodes n JOIN components c USING (poe_id) JOIN LATERAL (
        SELECT e.emar_id, e.subject_id, e.hadm_id, e.pharmacy_id, e.event_txt
        FROM mimiciv_hosp.emar e WHERE e.poe_id = n.poe_id OFFSET 0
    ) e ON true LEFT JOIN orders o ON o.pharmacy_id = e.pharmacy_id
    LEFT JOIN events included ON included.emar_id = e.emar_id AND included.family_eligible
        AND included.family_id = c.family_id AND included.charttime IS NOT NULL
), family_extra_heads AS MATERIALIZED (
    -- Conservatively flag the whole family, not just the candidate interval.
    -- A coverage-only other-location/NULL-pharmacy/other-drug control must not
    -- disappear and leave an apparently unambiguous family endpoint.
    SELECT family_id, count(*) FILTER (WHERE NOT included_in_family_stream) AS extra_heads
    FROM shared_poe_heads GROUP BY family_id
), pharmacy_issues AS MATERIALIZED (
    SELECT pharmacy_id, count(*) FILTER (WHERE identity_ok IS NOT TRUE) AS excluded_records,
           count(*) FILTER (WHERE charttime IS NULL) AS missing_time
    FROM events GROUP BY pharmacy_id
), family_issue_rows AS MATERIALIZED (
    SELECT family_id, emar_id, family_eligible, charttime FROM events WHERE family_id IS NOT NULL
    UNION
    SELECT c.family_id, e.emar_id, e.family_eligible, e.charttime
    FROM events e JOIN components c ON c.poe_id = e.event_poe
    UNION
    SELECT c.family_id, e.emar_id, e.family_eligible, e.charttime
    FROM events e JOIN components c ON c.poe_id = nullif(trim(e.pharmacy_poe), '')
), family_issues AS MATERIALIZED (
    SELECT family_id, count(*) FILTER (WHERE family_eligible IS NOT TRUE) AS excluded_records,
           count(*) FILTER (WHERE charttime IS NULL) AS missing_time
    FROM family_issue_rows GROUP BY family_id
), streams AS MATERIALIZED (
    SELECT 'pharmacy'::text AS stream_kind, e.pharmacy_id::text AS stream_key,
           e.*, i.excluded_records, i.missing_time
    FROM events e JOIN pharmacy_issues i USING (pharmacy_id)
    WHERE e.identity_ok AND e.charttime IS NOT NULL
    UNION ALL
    SELECT 'explicit_order_family', e.family_id, e.*, i.excluded_records, i.missing_time
    FROM events e JOIN family_issues i USING (family_id)
    WHERE e.family_eligible AND e.charttime IS NOT NULL
), numbered AS MATERIALIZED (
    SELECT s.*, row_number() OVER w AS position,
           count(*) OVER (PARTITION BY stream_kind, stream_key, subject_id, hadm_id, charttime) AS simultaneous
    FROM streams s
    WINDOW w AS (PARTITION BY stream_kind, stream_key, subject_id, hadm_id ORDER BY charttime, emar_id)
), sequenced AS MATERIALIZED (
    SELECT s.*, min(position) FILTER (WHERE event_txt IS DISTINCT FROM 'Confirmed') OVER
        (PARTITION BY stream_kind, stream_key, subject_id, hadm_id ORDER BY position
         ROWS BETWEEN 1 FOLLOWING AND UNBOUNDED FOLLOWING) AS next_control,
        sum((simultaneous > 1)::integer) OVER
        (PARTITION BY stream_kind, stream_key, subject_id, hadm_id ORDER BY position) AS ties_through
    FROM numbered s
), endpoints AS MATERIALIZED (
    SELECT s.*, c.emar_id AS end_key, c.event_txt AS end_status, c.pharmacy_id AS end_pharmacy,
           c.event_poe AS end_poe, c.charttime AS end_time,
           c.ties_through - s.ties_through + (s.simultaneous > 1)::integer AS tied_rows
    FROM sequenced s LEFT JOIN sequenced c
      ON c.stream_kind = s.stream_kind AND c.stream_key = s.stream_key
     AND c.subject_id = s.subject_id AND c.hadm_id = s.hadm_id AND c.position = s.next_control
    WHERE s.event_txt IN ('Started', 'Delayed Started', 'Restarted')
), comparison AS MATERIALIZED (
    SELECT p.*, f.emar_id IS NOT NULL AS eligible, f.end_key AS family_end_key,
           f.end_status AS family_end_status, f.end_pharmacy AS family_end_pharmacy,
           f.end_poe AS family_end_poe, f.tied_rows AS family_ties,
           f.excluded_records AS family_excluded, f.missing_time AS family_missing_time,
           f.end_time AS family_end_time, n.poe_nodes, n.cycle_nodes, n.branching_nodes,
           coalesce(g.self_edges, 0) AS self_edges, coalesce(x.extra_heads, 0) AS extra_heads
    FROM endpoints p LEFT JOIN endpoints f ON f.emar_id = p.emar_id AND f.stream_kind = 'explicit_order_family'
    LEFT JOIN family_nodes n ON n.family_id = f.family_id
    LEFT JOIN family_edges g ON g.family_id = f.family_id
    LEFT JOIN family_extra_heads x ON x.family_id = f.family_id
    WHERE p.stream_kind = 'pharmacy'
), pharmacy_spans AS MATERIALIZED (
    -- These are RECORD spans, not clinical infusion intervals.
    SELECT family_id, pharmacy_id, min(charttime) AS first_record, max(charttime) AS last_record
    FROM events WHERE family_eligible AND charttime IS NOT NULL GROUP BY family_id, pharmacy_id
), overlapping_spans AS MATERIALIZED (
    SELECT a.family_id, count(*) AS overlapping_pairs
    FROM pharmacy_spans a JOIN pharmacy_spans b ON a.family_id = b.family_id AND a.pharmacy_id < b.pharmacy_id
    WHERE greatest(a.first_record, b.first_record) < least(a.last_record, b.last_record)
    GROUP BY a.family_id
), family_profile AS MATERIALIZED (
    SELECT n.*, coalesce(e.edge_count, 0) AS edge_count,
           coalesce(e.reciprocal_edges, 0) AS reciprocal_edges, coalesce(e.self_edges, 0) AS self_edges,
           coalesce(s.overlapping_pairs, 0) AS overlapping_record_pairs,
           coalesce(x.extra_heads, 0) AS extra_heads
    FROM family_nodes n LEFT JOIN family_edges e USING (family_id)
    LEFT JOIN overlapping_spans s USING (family_id)
    LEFT JOIN family_extra_heads x USING (family_id)
)
SELECT 'candidate_inventory' AS section, jsonb_build_object('node_eligible', node_ok) AS dimensions,
       count(*) AS records, jsonb_build_object('distinct_poe', count(DISTINCT rx_poe)) AS counters
FROM orders GROUP BY node_ok
UNION ALL
SELECT 'raw_order_relation', jsonb_build_object('direction', direction, 'source_transaction', transaction_type,
       'target_transaction', target_transaction, 'target_found', target_found,
       'target_missing_identity', target_missing_identity, 'target_identity_ok', target_identity_ok,
       'target_is_candidate', target_is_candidate, 'self_link', poe_id = target, 'usable', usable),
       count(*), '{}'::jsonb
FROM raw_links GROUP BY direction, transaction_type, target_transaction, target_found,
    target_missing_identity, target_identity_ok, target_is_candidate, poe_id = target, usable
UNION ALL
SELECT 'edge_reciprocity', jsonb_build_object('reciprocal', reciprocal, 'has_forward', has_forward,
       'has_backward', has_backward, 'self_link', old_poe = new_poe), count(*), '{}'::jsonb
FROM edges GROUP BY reciprocal, has_forward, has_backward, old_poe = new_poe
UNION ALL
SELECT 'family_profile', jsonb_build_object('poe_nodes', poe_nodes, 'has_cycle', cycle_nodes > 0,
       'has_branching', branching_nodes > 0, 'has_self_link', self_edges > 0,
       'has_overlapping_pharmacy_record_spans', overlapping_record_pairs > 0,
       'has_shared_poe_extra_heads', extra_heads > 0), count(*),
       jsonb_build_object('poe_nodes', sum(poe_nodes), 'directed_edges', sum(edge_count),
           'reciprocal_edges', sum(reciprocal_edges), 'overlapping_record_pairs', sum(overlapping_record_pairs))
FROM family_profile GROUP BY poe_nodes, cycle_nodes > 0, branching_nodes > 0, self_edges > 0,
    overlapping_record_pairs > 0, extra_heads > 0
UNION ALL
SELECT 'endpoint_comparison', jsonb_build_object('pharmacy_next', end_status,
       'pharmacy_has_control', end_key IS NOT NULL, 'family_eligible', eligible,
       'family_next', family_end_status, 'family_has_control', family_end_key IS NOT NULL,
       'family_endpoint_changed', family_end_key IS DISTINCT FROM end_key,
       'cross_pharmacy', family_end_key IS NOT NULL AND family_end_pharmacy IS DISTINCT FROM pharmacy_id,
       'cross_poe', family_end_key IS NOT NULL AND family_end_poe IS DISTINCT FROM event_poe,
       'has_ties', family_ties > 0, 'has_omitted_records', family_excluded > 0 OR family_missing_time > 0,
       'has_cycle', cycle_nodes > 0, 'has_self_link', self_edges > 0, 'has_branching', branching_nodes > 0,
       'has_shared_poe_extra_heads', extra_heads > 0,
       'has_overlapping_pharmacy_record_spans', coalesce(s.overlapping_pairs, 0) > 0),
       count(*), jsonb_build_object('hours_min', min(extract(epoch FROM (family_end_time-charttime))/3600),
           'hours_max', max(extract(epoch FROM (family_end_time-charttime))/3600))
FROM comparison LEFT JOIN overlapping_spans s USING (family_id)
GROUP BY end_status, end_key IS NOT NULL, eligible, family_end_status,
    family_end_key IS NOT NULL, family_end_key IS DISTINCT FROM end_key,
    family_end_key IS NOT NULL AND family_end_pharmacy IS DISTINCT FROM pharmacy_id,
    family_end_key IS NOT NULL AND family_end_poe IS DISTINCT FROM event_poe,
    family_ties > 0, family_excluded > 0 OR family_missing_time > 0, cycle_nodes > 0,
    self_edges > 0, branching_nodes > 0, extra_heads > 0, coalesce(s.overlapping_pairs, 0) > 0
UNION ALL
SELECT 'shared_poe_head_coverage_only', jsonb_build_object('identity_ok', identity_ok,
       'exact_candidate_pharmacy', exact_candidate_pharmacy, 'missing_pharmacy', pharmacy_id IS NULL,
       'included_in_family_stream', included_in_family_stream, 'event_txt', event_txt), count(*), '{}'::jsonb
FROM shared_poe_heads GROUP BY identity_ok, exact_candidate_pharmacy, pharmacy_id IS NULL,
    included_in_family_stream, event_txt
ORDER BY section, records DESC, dimensions;
