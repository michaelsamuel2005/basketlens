-- 60_campaigns.sql: for each eligible campaign, every household's spend before and during the campaign.
-- Window: the campaign weeks (capped at 13), compared with the same number of weeks just before it (pre) and the same
-- number again before that (prepre, for a placebo test). A campaign is eligible when it has at least 3 weeks, a full pre
-- window inside the data, and at least 3 of the supplier's products on its coupon list.
-- Parameters: {{mfr}}
WITH camp AS (
    SELECT campaign_id, campaign_type, start_week AS s,
           LEAST(COALESCE(end_week, 53), start_week + 12) - start_week + 1 AS l
    FROM campaign WHERE start_week IS NOT NULL),
allc AS (
    SELECT c.campaign_id, COALESCE(c.start_week, 1) AS s0, COALESCE(c.end_week, 53) AS e0,
           (SELECT COUNT(*) FROM coupon_product cp JOIN dim_product p ON p.product_id = cp.product_id
             WHERE cp.campaign_id = c.campaign_id AND p.manufacturer_id = '{{mfr}}') AS n_sup
    FROM campaign c),
elig AS (
    SELECT c.*, a.n_sup AS n_sup_coupon_products,
           -- other campaigns carrying the supplier's products that ran during this campaign's pre window
           (SELECT COUNT(*) FROM allc o WHERE o.campaign_id <> c.campaign_id AND o.n_sup >= 3
              AND o.s0 <= c.s - 1 AND o.e0 >= c.s - c.l) AS pre_overlap
    FROM camp c JOIN allc a ON a.campaign_id = c.campaign_id WHERE c.l >= 3 AND c.s - c.l >= 2),
elig2 AS (SELECT * FROM elig WHERE n_sup_coupon_products >= 3),
lines AS (
    SELECT e.campaign_id, s.household_id,
           CASE WHEN s.week BETWEEN e.s - 2 * e.l AND e.s - e.l - 1 THEN 'prepre'
                WHEN s.week BETWEEN e.s - e.l AND e.s - 1 THEN 'pre'
                WHEN s.week BETWEEN e.s AND e.s + e.l - 1 THEN 'post'
                WHEN s.week BETWEEN e.s - 26 AND e.s - 2 * e.l - 1 THEN 'early' END AS win,
           s.net_sales, (s.manufacturer_id = '{{mfr}}') AS is_sup,
           (s.manufacturer_id = '{{mfr}}' AND cp.product_id IS NOT NULL) AS is_cpn,
           s.coupon_disc, s.coupon_match_disc
    FROM sale s JOIN elig2 e ON s.week BETWEEN GREATEST(e.s - 26, 2) AND e.s + e.l - 1
    LEFT JOIN coupon_product cp ON cp.campaign_id = e.campaign_id AND cp.product_id = s.product_id),
agg AS (
    SELECT campaign_id, household_id,
           SUM(CASE WHEN win = 'pre' THEN net_sales ELSE 0 END) AS pre_total,
           SUM(CASE WHEN win = 'post' THEN net_sales ELSE 0 END) AS post_total,
           SUM(CASE WHEN win = 'prepre' THEN net_sales ELSE 0 END) AS prepre_total,
           SUM(CASE WHEN win = 'pre' AND is_sup THEN net_sales ELSE 0 END) AS pre_sup,
           SUM(CASE WHEN win = 'post' AND is_sup THEN net_sales ELSE 0 END) AS post_sup,
           SUM(CASE WHEN win = 'prepre' AND is_sup THEN net_sales ELSE 0 END) AS prepre_sup,
           SUM(CASE WHEN win = 'pre' AND is_cpn THEN net_sales ELSE 0 END) AS pre_cpn,
           SUM(CASE WHEN win = 'post' AND is_cpn THEN net_sales ELSE 0 END) AS post_cpn,
           SUM(CASE WHEN win = 'prepre' AND is_cpn THEN net_sales ELSE 0 END) AS prepre_cpn,
           SUM(CASE WHEN win = 'early' THEN net_sales ELSE 0 END) AS early_total,
           SUM(CASE WHEN win = 'early' AND is_sup THEN net_sales ELSE 0 END) AS early_sup,
           SUM(CASE WHEN win = 'post' AND is_sup THEN coupon_disc ELSE 0 END) AS post_coupon_disc,
           SUM(CASE WHEN win = 'post' AND is_sup THEN coupon_match_disc ELSE 0 END) AS post_coupon_match
    FROM lines WHERE win IS NOT NULL GROUP BY campaign_id, household_id)
SELECT e.campaign_id, e.campaign_type, e.s AS start_week, e.l AS weeks, e.n_sup_coupon_products, e.pre_overlap, h.household_id,
       (ch.household_id IS NOT NULL) AS targeted, COALESCE(ch.redeemed, FALSE) AS redeemed,
       COALESCE(a.pre_total, 0) AS pre_total, COALESCE(a.post_total, 0) AS post_total,
       COALESCE(a.prepre_total, 0) AS prepre_total,
       COALESCE(a.pre_sup, 0) AS pre_sup, COALESCE(a.post_sup, 0) AS post_sup, COALESCE(a.prepre_sup, 0) AS prepre_sup,
       COALESCE(a.pre_cpn, 0) AS pre_cpn, COALESCE(a.post_cpn, 0) AS post_cpn, COALESCE(a.prepre_cpn, 0) AS prepre_cpn,
       COALESCE(a.early_total, 0) AS early_total, COALESCE(a.early_sup, 0) AS early_sup,
       COALESCE(a.post_coupon_disc, 0) AS post_coupon_disc, COALESCE(a.post_coupon_match, 0) AS post_coupon_match,
       (e.s - 2 * e.l >= 2) AS has_prepre,
       (GREATEST(e.s - 2 * e.l - 1, 1) - GREATEST(e.s - 26, 2) + 1) AS early_weeks
FROM elig2 e CROSS JOIN dim_household h
LEFT JOIN campaign_hh ch ON ch.campaign_id = e.campaign_id AND ch.household_id = h.household_id
LEFT JOIN agg a ON a.campaign_id = e.campaign_id AND a.household_id = h.household_id;
