-- Catalog only: inspect actual column names/types before writing any query
-- against a clinical or dictionary relation. Never infer fields from old code.
-- declared_not_null reports the catalog constraint, not observed completeness.
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    a.attnum AS ordinal_position,
    a.attname AS column_name,
    pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
    a.attnotnull AS declared_not_null,
    has_schema_privilege(n.oid, 'USAGE') AS has_schema_usage,
    has_column_privilege(c.oid, a.attnum, 'SELECT') AS has_column_select
FROM pg_catalog.pg_namespace AS n
JOIN pg_catalog.pg_class AS c ON c.relnamespace = n.oid
JOIN pg_catalog.pg_attribute AS a ON a.attrelid = c.oid
WHERE n.nspname <> 'information_schema'
  AND n.nspname !~ '^pg_'
  AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY n.nspname, c.relname, a.attnum;
