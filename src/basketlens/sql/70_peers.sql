-- 70_peers.sql: the supplier against the other manufacturers in the category (and private label as one entity).
-- Parameters: {{cat}}
WITH s AS (
    SELECT household_id, basket_id, units, net_sales, shelf_value, retail_disc, product_id,
           CASE WHEN is_private THEN 'PRIVATE LABEL' ELSE manufacturer_id END AS entity
    FROM sale WHERE category = '{{cat}}' AND week >= 2),
tot AS (SELECT SUM(net_sales) AS cat_sales, COUNT(DISTINCT household_id) AS cat_buyers FROM s)
SELECT entity, SUM(net_sales) AS net_sales, SUM(net_sales) / MAX(t.cat_sales) AS share,
       COUNT(DISTINCT household_id) AS buyers, COUNT(DISTINCT household_id) * 1.0 / MAX(t.cat_buyers) AS penetration,
       COUNT(DISTINCT basket_id) * 1.0 / COUNT(DISTINCT household_id) AS trips_per_buyer,
       SUM(net_sales) / COUNT(DISTINCT household_id) AS sales_per_buyer,
       SUM(CASE WHEN retail_disc > 0 THEN net_sales ELSE 0 END) / SUM(net_sales) AS discount_share,
       SUM(shelf_value) / SUM(units) AS shelf_price_per_unit, COUNT(DISTINCT product_id) AS skus
FROM s CROSS JOIN tot t GROUP BY entity ORDER BY net_sales DESC;
