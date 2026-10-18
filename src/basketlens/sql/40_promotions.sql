-- 40_promotions.sql: product x week panel for one category, for stores that report promotions (112 stores).
-- n_ranged = stores where the product sold or was featured at any time in the year; n_display / n_mailer / n_feat =
-- stores featuring it that week (display, mailer, either). Zero-sale weeks are kept (cross join with weeks).
-- Parameters: {{cat}}
WITH prod AS (
    SELECT product_id, manufacturer_id, ptype, is_private, brand FROM dim_product WHERE category = '{{cat}}'),
rng AS (
    SELECT r.product_id, COUNT(DISTINCT r.store_id) AS n_ranged
    FROM ranging r JOIN prod ON prod.product_id = r.product_id JOIN promo_store ps ON ps.store_id = r.store_id
    GROUP BY r.product_id),
wk AS (SELECT DISTINCT week FROM calendar WHERE week >= 2),
sold AS (
    SELECT s.product_id, s.week, SUM(s.units) AS units, SUM(s.net_sales) AS net_sales, SUM(s.shelf_value) AS shelf_value,
           SUM(s.retail_disc) AS retail_disc
    FROM sale s JOIN promo_store ps ON ps.store_id = s.store_id
    WHERE s.category = '{{cat}}' AND s.week >= 2 GROUP BY s.product_id, s.week),
pf AS (
    SELECT f.product_id, f.week, SUM(f.on_display) AS n_display, SUM(f.in_mailer) AS n_mailer, COUNT(*) AS n_feat
    FROM promo_flag f JOIN prod ON prod.product_id = f.product_id WHERE f.week >= 2 GROUP BY f.product_id, f.week)
SELECT p.product_id, p.manufacturer_id, p.ptype, p.is_private, w.week, r.n_ranged,
       COALESCE(s.units, 0) AS units, COALESCE(s.net_sales, 0) AS net_sales, COALESCE(s.shelf_value, 0) AS shelf_value,
       COALESCE(s.retail_disc, 0) AS retail_disc,
       COALESCE(f.n_display, 0) AS n_display, COALESCE(f.n_mailer, 0) AS n_mailer, COALESCE(f.n_feat, 0) AS n_feat
FROM prod p JOIN rng r ON r.product_id = p.product_id CROSS JOIN wk w
LEFT JOIN sold s ON s.product_id = p.product_id AND s.week = w.week
LEFT JOIN pf f ON f.product_id = p.product_id AND f.week = w.week;
