-- Reproducible 1 percent SYSTEM page sample of ORDERS, not administrations.
-- Product, formulation, route and dose-unit vocabulary for candidate discovery.
WITH sampled AS MATERIALIZED (
    SELECT drug, drug_type, prod_strength, dose_unit_rx, route
    FROM mimiciv_hosp.prescriptions TABLESAMPLE SYSTEM (1) REPEATABLE (20261011)
), candidate AS (
    SELECT * FROM sampled
    WHERE lower(drug) LIKE '%potassium%'
       OR lower(drug) LIKE '%kcl%'
       OR lower(drug) LIKE '%sodium chloride%'
       OR lower(drug) LIKE '%hypertonic%'
       OR lower(drug) LIKE '%saline%'
       OR lower(drug) LIKE '%nacl%'
)
SELECT drug, drug_type, prod_strength, dose_unit_rx, route,
       count(*) AS sampled_order_rows,
       (SELECT count(*) FROM sampled) AS total_sampled_rows,
       1.0 AS system_sample_percent, 20261011 AS sample_seed
FROM candidate
GROUP BY drug, drug_type, prod_strength, dose_unit_rx, route
ORDER BY sampled_order_rows DESC, drug, route, prod_strength;
