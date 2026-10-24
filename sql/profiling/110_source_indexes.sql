-- Catalog only. Inspect bounded-access possibilities before joining fact tables.
SELECT n.nspname AS schema_name, t.relname AS table_name,
       i.relname AS index_name, x.indisvalid, x.indisunique,
       pg_catalog.pg_get_indexdef(i.oid) AS index_definition
FROM pg_catalog.pg_index x
JOIN pg_catalog.pg_class t ON t.oid = x.indrelid
JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace
JOIN pg_catalog.pg_class i ON i.oid = x.indexrelid
WHERE n.nspname IN ('mimiciv_hosp', 'mimiciv_icu')
  AND t.relname IN ('patients', 'admissions', 'emar', 'emar_detail', 'pharmacy',
      'prescriptions', 'poe', 'poe_detail', 'labevents', 'transfers', 'icustays', 'omr', 'chartevents')
ORDER BY n.nspname, t.relname, i.relname;
