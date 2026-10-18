-- 21_flows.sql: category spend by entity for each household in two windows, to see where lapsed buyers' money went.
-- Parameters: {{mfr}}, {{cat}}, {{w1_from}}, {{w1_to}}, {{w2_from}}, {{w2_to}}
SELECT household_id,
       CASE WHEN week BETWEEN {{w1_from}} AND {{w1_to}} THEN 1 ELSE 2 END AS win,
       SUM(CASE WHEN manufacturer_id = '{{mfr}}' THEN net_sales ELSE 0 END) AS supplier,
       SUM(CASE WHEN manufacturer_id <> '{{mfr}}' AND is_private THEN net_sales ELSE 0 END) AS private_label,
       SUM(CASE WHEN manufacturer_id <> '{{mfr}}' AND NOT is_private THEN net_sales ELSE 0 END) AS other_brands
FROM sale
WHERE category = '{{cat}}' AND (week BETWEEN {{w1_from}} AND {{w1_to}} OR week BETWEEN {{w2_from}} AND {{w2_to}})
GROUP BY household_id, CASE WHEN week BETWEEN {{w1_from}} AND {{w1_to}} THEN 1 ELSE 2 END;
