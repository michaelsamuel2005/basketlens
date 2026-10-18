-- 10_shopper.sql: who buys the supplier's products, how often, and for how much, by quarter and by half-year.
-- Parameters: {{mfr}} supplier (manufacturer_id), {{cat}} category. Entities: supplier, private label, other brands.
-- Quarters are weeks 2-14, 15-27, 28-40, 41-53 (week 1 is a two-day stub); halves are quarters 1-2 and 3-4.
WITH s AS (
    SELECT household_id, basket_id, units, net_sales, shelf_value, retail_disc,
           1 + LEAST(3, CAST(FLOOR((week - 2) / 13.0) AS INTEGER)) AS quarter,
           CASE WHEN manufacturer_id = '{{mfr}}' THEN 'supplier'
                WHEN is_private THEN 'private label' ELSE 'other brands' END AS entity
    FROM sale WHERE category = '{{cat}}' AND week >= 2),
g AS (
    SELECT 'quarter' AS grain, quarter AS period, entity, household_id, basket_id, units, net_sales, shelf_value, retail_disc FROM s
    UNION ALL
    SELECT 'half', 1 + CAST(quarter > 2 AS INTEGER), entity, household_id, basket_id, units, net_sales, shelf_value, retail_disc FROM s),
by_entity AS (
    SELECT grain, period, entity, COUNT(DISTINCT household_id) AS buyers, COUNT(DISTINCT basket_id) AS trips,
           SUM(units) AS units, SUM(net_sales) AS net_sales, SUM(shelf_value) AS shelf_value,
           SUM(CASE WHEN retail_disc > 0 THEN net_sales ELSE 0 END) AS sales_on_discount
    FROM g GROUP BY grain, period, entity),
whole AS (
    SELECT grain, period, 'category' AS entity, COUNT(DISTINCT household_id) AS buyers, COUNT(DISTINCT basket_id) AS trips,
           SUM(units) AS units, SUM(net_sales) AS net_sales, SUM(shelf_value) AS shelf_value,
           SUM(CASE WHEN retail_disc > 0 THEN net_sales ELSE 0 END) AS sales_on_discount
    FROM g GROUP BY grain, period)
SELECT u.*, (SELECT COUNT(*) FROM dim_household) AS households
FROM (SELECT * FROM by_entity UNION ALL SELECT * FROM whole) u
ORDER BY grain, period, entity;
