-- Complete matching dictionary entries, including non-blood entries so specimen
-- type is explicitly reviewed. This does not select final outcome item IDs.
SELECT itemid, label, fluid, category
FROM mimiciv_hosp.d_labitems
WHERE lower(label) IN ('potassium', 'sodium', 'creatinine')
ORDER BY label, fluid, category, itemid;
