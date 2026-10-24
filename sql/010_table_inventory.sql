-- Catalog/statistics queries only: no COUNT(*) against clinical tables.
-- Includes all non-system schemas, without assuming mimiciv_hosp or a versioned
-- schema name. Schemas with no relations are retained in the result.
-- Estimates may be stale or absent. A partitioned parent's estimate is not a
-- reliable sum of its children; neither estimate is a cohort/patient count.
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    CASE c.relkind
        WHEN 'r' THEN 'table'
        WHEN 'p' THEN 'partitioned_table'
        WHEN 'v' THEN 'view'
        WHEN 'm' THEN 'materialized_view'
        WHEN 'f' THEN 'foreign_table'
    END AS relation_kind,
    c.relispartition AS is_partition,
    CASE WHEN c.relkind IN ('r', 'p', 'm', 'f') AND c.reltuples >= 0
        THEN c.reltuples::bigint
    END AS planner_estimated_rows,
    s.n_live_tup AS statistics_estimated_live_rows,
    s.last_analyze,
    s.last_autoanalyze,
    has_schema_privilege(n.oid, 'USAGE') AS has_schema_usage,
    CASE WHEN c.oid IS NOT NULL
        THEN has_table_privilege(c.oid, 'SELECT')
    END AS has_table_select
FROM pg_catalog.pg_namespace AS n
LEFT JOIN pg_catalog.pg_class AS c
    ON c.relnamespace = n.oid
   AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
LEFT JOIN pg_catalog.pg_stat_user_tables AS s ON s.relid = c.oid
WHERE n.nspname <> 'information_schema'
  AND n.nspname !~ '^pg_'
ORDER BY n.nspname, c.relname;
