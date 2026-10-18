-- 01_warehouse.sql: raw_* tables -> the warehouse every analysis reads.
-- Plain SQL (CREATE TABLE AS, joins, window functions, CTEs). Statements are separated by `-- ;;`.
-- Facts verified against the data, not assumed (see docs/DATA_NOTES.md):
--   sales_value is net of the loyalty-card discount: sales_value + retail_disc is the shelf value (median ratio to the
--   same product, store and week at full price = 1.00; sales_value alone = 0.90).
--   a "sale" line has sales_value > 0 and a quantity from 1 to 99; the rest are coupon-only lines and quantity glitches.
--   weeks run Tuesday to Monday; week 1 is a two-day stub (1-2 Jan 2017), so analysis windows use weeks 2 to 53.

CREATE TABLE dim_product AS
SELECT product_id, manufacturer_id, department, brand, product_category AS category, product_type AS ptype,
       package_size, (brand = 'Private') AS is_private
FROM raw_products;
-- ;;
CREATE TABLE dim_household AS
SELECT h.household_id, d.age, d.income, d.home_ownership, d.marital_status, d.household_size, d.household_comp,
       d.kids_count, (d.household_id IS NOT NULL) AS has_demographics
FROM (SELECT DISTINCT household_id FROM raw_transactions) h
LEFT JOIN raw_demographics d ON d.household_id = h.household_id;
-- ;;
CREATE TABLE fact_line AS
SELECT household_id, store_id, basket_id, product_id, quantity AS units, sales_value AS net_sales, retail_disc,
       coupon_disc, coupon_match_disc, sales_value + retail_disc AS shelf_value, week,
       CAST(transaction_timestamp AS DATE) AS day,
       (sales_value > 0 AND quantity BETWEEN 1 AND 99) AS is_sale
FROM raw_transactions;
-- ;;
-- one row per sale line with the product attributes alongside (the table most analyses read)
CREATE TABLE sale AS
SELECT f.household_id, f.store_id, f.basket_id, f.product_id, f.units, f.net_sales, f.retail_disc, f.coupon_disc,
       f.coupon_match_disc, f.shelf_value, f.week, f.day,
       p.manufacturer_id, p.department, p.category, p.ptype, p.is_private
FROM fact_line f JOIN dim_product p ON p.product_id = f.product_id
WHERE f.is_sale;
-- ;;
-- day -> week, using the week that holds most of that day's lines (a week boundary falls inside a day)
CREATE TABLE calendar AS
SELECT day, week FROM (
    SELECT day, week, ROW_NUMBER() OVER (PARTITION BY day ORDER BY COUNT(*) DESC, week) AS rn
    FROM fact_line GROUP BY day, week) WHERE rn = 1;
-- ;;
-- ranging: a product is "ranged" in a store-week when it sold there or was featured there
CREATE TABLE ranging AS
SELECT product_id, store_id, week, MAX(sold) AS sold, MAX(featured) AS featured FROM (
    SELECT product_id, store_id, week, 1 AS sold, 0 AS featured FROM sale GROUP BY product_id, store_id, week
    UNION ALL
    SELECT product_id, store_id, week, 0 AS sold, 1 AS featured FROM raw_promotions GROUP BY product_id, store_id, week
) GROUP BY product_id, store_id, week;
-- ;;
-- promotion flags per product-store-week, from the retailer's promotions table (it lists featured weeks only)
CREATE TABLE promo_flag AS
SELECT product_id, store_id, week,
       MAX(CASE WHEN display_location <> '0' THEN 1 ELSE 0 END) AS on_display,
       MAX(CASE WHEN mailer_location <> '0' THEN 1 ELSE 0 END) AS in_mailer
FROM raw_promotions GROUP BY product_id, store_id, week;
-- ;;
CREATE TABLE promo_store AS SELECT DISTINCT store_id FROM raw_promotions;
-- ;;
CREATE TABLE campaign AS
SELECT d.campaign_id, d.campaign_type, d.start_date, d.end_date,
       cs.week AS start_week, ce.week AS end_week,
       (SELECT MIN(day) FROM calendar) AS data_start, (SELECT MAX(day) FROM calendar) AS data_end
FROM raw_campaign_descriptions d
LEFT JOIN calendar cs ON cs.day = d.start_date
LEFT JOIN calendar ce ON ce.day = d.end_date;
-- ;;
CREATE TABLE campaign_hh AS
SELECT c.campaign_id, c.household_id,
       COALESCE(r.n_redemptions, 0) AS n_redemptions, (r.n_redemptions IS NOT NULL) AS redeemed
FROM raw_campaigns c
LEFT JOIN (SELECT campaign_id, household_id, COUNT(*) AS n_redemptions FROM raw_coupon_redemptions
           GROUP BY campaign_id, household_id) r
  ON r.campaign_id = c.campaign_id AND r.household_id = c.household_id;
-- ;;
CREATE TABLE coupon_product AS
SELECT DISTINCT campaign_id, product_id FROM raw_coupons;
