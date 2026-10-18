-- 30_segments.sql: one behavioural row per household (whole store, weeks 2-53), plus spend with the supplier.
-- Parameters: {{mfr}}, {{cat}}.
WITH h AS (
    SELECT household_id,
           SUM(net_sales) AS sales, COUNT(DISTINCT basket_id) AS trips, MAX(week) AS last_week,
           COUNT(DISTINCT week) AS active_weeks, COUNT(DISTINCT store_id) AS stores,
           SUM(CASE WHEN is_private THEN net_sales ELSE 0 END) AS pl_sales,
           SUM(retail_disc) AS disc, SUM(shelf_value) AS shelf,
           SUM(CASE WHEN department IN ('PRODUCE','MEAT','MEAT-PCKGD','SEAFOOD','SEAFOOD-PCKGD','DELI','PASTRY','FLORAL')
                    THEN net_sales ELSE 0 END) AS fresh_sales,
           SUM(CASE WHEN manufacturer_id = '{{mfr}}' AND category = '{{cat}}' THEN net_sales ELSE 0 END) AS supplier_sales,
           SUM(CASE WHEN category = '{{cat}}' THEN net_sales ELSE 0 END) AS category_sales,
           SUM(CASE WHEN manufacturer_id = '{{mfr}}' THEN net_sales ELSE 0 END) AS supplier_all_sales
    FROM sale WHERE week >= 2 GROUP BY household_id)
SELECT h.household_id, sales, trips, 53 - last_week AS recency_weeks, active_weeks, stores,
       sales / trips AS basket_value, pl_sales / sales AS pl_share, disc / NULLIF(shelf, 0) AS deal_depth,
       fresh_sales / sales AS fresh_share, supplier_sales, category_sales, supplier_all_sales,
       d.age, d.income, d.household_comp, d.kids_count, (d.household_id IS NOT NULL) AS has_demographics
FROM h LEFT JOIN dim_household d ON d.household_id = h.household_id
WHERE sales > 0 AND trips >= 2;
