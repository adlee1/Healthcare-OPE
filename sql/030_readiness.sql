-- Structural preflight only. These are expected hospital-module table names,
-- not a frozen extraction specification. All names/types must be reviewed
-- against 020_column_inventory.sql and the paper before cohort SQL is written.
-- Candidate schemas are discovered from relations, not a schema-name pattern.
-- Do not mix relations across schemas/releases to make these checks pass.
-- A missing medication source requires review; the paper has not established
-- which available medication tables are sufficient for its event definition.
WITH expected(relation_name, purpose, requirement) AS (
    VALUES
        ('patients', 'Patient identity and demographic mapping', 'core'),
        ('admissions', 'Admission identity and encounter boundaries', 'core'),
        ('transfers', 'Care-location timeline and non-ICU assessment', 'core'),
        ('labevents', 'Electrolyte measurements and timestamps', 'core'),
        ('d_labitems', 'Lab item dictionary and unit review', 'core'),
        ('diagnoses_icd', 'Diagnosis code availability, temporal eligibility pending', 'supporting'),
        ('d_icd_diagnoses', 'Diagnosis code dictionary', 'supporting'),
        ('prescriptions', 'Medication orders, not proof of administration', 'medication_source_review'),
        ('pharmacy', 'Medication formulation and order metadata', 'medication_source_review'),
        ('emar', 'Medication administration records', 'medication_source_review'),
        ('emar_detail', 'Medication administration details', 'medication_source_review')
), candidates AS (
    SELECT DISTINCT n.oid AS schema_oid, n.nspname AS schema_name
    FROM pg_catalog.pg_namespace AS n
    JOIN pg_catalog.pg_class AS c ON c.relnamespace = n.oid
    WHERE n.nspname <> 'information_schema'
      AND n.nspname !~ '^pg_'
      AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
      AND c.relname IN ('patients', 'admissions', 'labevents')
), candidates_or_missing AS (
    SELECT schema_oid, schema_name::text FROM candidates
    UNION ALL
    SELECT NULL::oid, NULL::text WHERE NOT EXISTS (SELECT 1 FROM candidates)
)
SELECT
    s.schema_name,
    e.relation_name AS expected_relation,
    e.purpose,
    e.requirement,
    c.oid IS NOT NULL AS relation_present,
    CASE
        WHEN s.schema_oid IS NULL THEN 'NO_CANDIDATE_SCHEMA'
        WHEN c.oid IS NULL THEN 'MISSING'
        WHEN NOT has_schema_privilege(s.schema_oid, 'USAGE')
            THEN 'NO_SCHEMA_USAGE'
        WHEN NOT has_table_privilege(c.oid, 'SELECT') THEN 'NO_TABLE_SELECT'
        ELSE 'PRESENT_REQUIRES_COLUMN_REVIEW'
    END AS structural_status
FROM candidates_or_missing AS s
CROSS JOIN expected AS e
LEFT JOIN pg_catalog.pg_class AS c
    ON c.relnamespace = s.schema_oid
   AND c.relname = e.relation_name
   AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
ORDER BY s.schema_name NULLS FIRST, e.requirement, e.relation_name;
