-- 50_ranging.sql: one row per product in the category: sales, buyers and how widely and how long it was ranged.
-- Ranged store-weeks = store-weeks where the product sold or was featured, in stores that report promotions.
-- Parameters: {{mfr}}, {{cat}}
WITH prod AS (
    SELECT product_id, manufacturer_id, ptype, is_private, package_size FROM dim_product WHERE category = '{{cat}}'),
sales AS (
    SELECT product_id, SUM(net_sales) AS net_sales, SUM(units) AS units, COUNT(DISTINCT household_id) AS buyers
    FROM sale WHERE category = '{{cat}}' AND week >= 2 GROUP BY product_id),
rg AS (
    SELECT r.product_id, COUNT(DISTINCT r.store_id) AS ranged_stores, COUNT(*) AS ranged_store_weeks
    FROM ranging r JOIN prod ON prod.product_id = r.product_id JOIN promo_store ps ON ps.store_id = r.store_id
    WHERE r.week >= 2 GROUP BY r.product_id)
SELECT p.product_id, p.manufacturer_id, p.ptype, p.is_private, p.package_size,
       (p.manufacturer_id = '{{mfr}}') AS is_supplier,
       COALESCE(s.net_sales, 0) AS net_sales, COALESCE(s.units, 0) AS units, COALESCE(s.buyers, 0) AS buyers,
       COALESCE(g.ranged_stores, 0) AS ranged_stores, COALESCE(g.ranged_store_weeks, 0) AS ranged_store_weeks
FROM prod p LEFT JOIN sales s ON s.product_id = p.product_id LEFT JOIN rg g ON g.product_id = p.product_id
WHERE COALESCE(s.net_sales, 0) > 0;
