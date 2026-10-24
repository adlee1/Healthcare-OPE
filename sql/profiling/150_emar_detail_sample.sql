-- Reproducible 0.2 percent SYSTEM sample, independent of the eMAR sample.
-- Does not establish event-level parent/product completeness or final eligibility.
WITH sampled AS MATERIALIZED (
    SELECT parent_field_ordinal, administration_type, product_description,
           dose_given, dose_given_unit, product_amount_given, product_unit,
           infusion_rate, infusion_rate_unit, route, infusion_complete,
           complete_dose_not_given, completion_interval
    FROM mimiciv_hosp.emar_detail TABLESAMPLE SYSTEM (0.2) REPEATABLE (20261011)
), candidate AS (
    SELECT * FROM sampled
    WHERE lower(product_description) LIKE '%potassium%'
       OR lower(product_description) LIKE '%kcl%'
       OR lower(product_description) LIKE '%sodium chloride%'
       OR lower(product_description) LIKE '%hypertonic%'
       OR lower(product_description) LIKE '%saline%'
       OR lower(product_description) LIKE '%nacl%'
)
SELECT product_description, parent_field_ordinal, route,
       dose_given_unit, product_unit, infusion_rate_unit,
       count(*) AS sampled_detail_rows,
       count(*) FILTER (WHERE nullif(trim(dose_given), '') IS NOT NULL) AS dose_given_present,
       count(*) FILTER (WHERE trim(dose_given) ~ '^[0-9]+([.][0-9]+)?$') AS dose_given_simple_numeric,
       count(*) FILTER (WHERE nullif(trim(product_amount_given), '') IS NOT NULL) AS product_amount_present,
       count(*) FILTER (WHERE nullif(trim(infusion_rate), '') IS NOT NULL) AS infusion_rate_present,
       count(*) FILTER (WHERE infusion_complete = 'Y') AS infusion_complete_yes,
       count(*) FILTER (WHERE nullif(trim(completion_interval), '') IS NOT NULL) AS completion_interval_present,
       (SELECT count(*) FROM sampled) AS total_sampled_rows,
       0.2 AS system_sample_percent, 20261011 AS sample_seed
FROM candidate
GROUP BY product_description, parent_field_ordinal, route, dose_given_unit,
         product_unit, infusion_rate_unit
ORDER BY sampled_detail_rows DESC, product_description, parent_field_ordinal;
