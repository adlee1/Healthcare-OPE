-- Concept discovery only. Specimen and method must be adjudicated before use.
SELECT itemid, label, fluid, category
FROM mimiciv_hosp.d_labitems
WHERE lower(label) LIKE '%potassium%'
   OR lower(label) LIKE '%sodium%'
   OR lower(label) LIKE '%creatinine%'
ORDER BY label, fluid, category, itemid;
