-- 51_repertoire.sql: what each household bought in the category (spend by product), for delist transfer estimates.
-- Parameters: {{cat}}
SELECT household_id, product_id, ptype, manufacturer_id, is_private, SUM(net_sales) AS spend
FROM sale WHERE category = '{{cat}}' AND week >= 2 GROUP BY household_id, product_id, ptype, manufacturer_id, is_private;
