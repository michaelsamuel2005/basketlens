-- 20_journeys.sql: one row per household that bought the category: its path with the supplier.
-- Parameters: {{mfr}}, {{cat}}. Feeds trial / repeat / lapse in analysis (shopper.py).
WITH cs AS (
    SELECT household_id, basket_id, week, day, net_sales, retail_disc, (manufacturer_id = '{{mfr}}') AS is_sup
    FROM sale WHERE category = '{{cat}}' AND week >= 2),
sup_basket AS (
    SELECT household_id, basket_id, MIN(week) AS week, MIN(day) AS day, SUM(net_sales) AS sales,
           MAX(CASE WHEN retail_disc > 0 THEN 1 ELSE 0 END) AS on_discount
    FROM cs WHERE is_sup GROUP BY household_id, basket_id),
ranked AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY household_id ORDER BY day, basket_id) AS n FROM sup_basket),
sup AS (
    SELECT household_id,
           MAX(CASE WHEN n = 1 THEN week END) AS first_week,
           MAX(CASE WHEN n = 1 THEN day END) AS first_day,
           MAX(CASE WHEN n = 1 THEN on_discount END) AS first_on_discount,
           MAX(CASE WHEN n = 2 THEN day END) AS second_day,
           MAX(n) AS supplier_trips, MAX(week) AS supplier_last_week, SUM(sales) AS supplier_sales,
           SUM(CASE WHEN week <= 27 THEN 1 ELSE 0 END) AS supplier_trips_h1,
           SUM(CASE WHEN week >= 41 THEN 1 ELSE 0 END) AS supplier_trips_q4
    FROM ranked GROUP BY household_id),
cat_hh AS (
    SELECT household_id, COUNT(DISTINCT basket_id) AS cat_trips, SUM(net_sales) AS cat_sales,
           MAX(week) AS cat_last_week,
           COUNT(DISTINCT CASE WHEN week >= 41 THEN basket_id END) AS cat_trips_q4,
           COUNT(DISTINCT CASE WHEN week <= 27 THEN basket_id END) AS cat_trips_h1
    FROM cs GROUP BY household_id)
SELECT c.*, s.first_week, s.first_day, s.first_on_discount, s.second_day,
       COALESCE(s.supplier_trips, 0) AS supplier_trips, s.supplier_last_week, COALESCE(s.supplier_sales, 0) AS supplier_sales,
       COALESCE(s.supplier_trips_h1, 0) AS supplier_trips_h1, COALESCE(s.supplier_trips_q4, 0) AS supplier_trips_q4,
       (SELECT MAX(day) FROM calendar) AS data_end
FROM cat_hh c LEFT JOIN sup s ON s.household_id = c.household_id;
