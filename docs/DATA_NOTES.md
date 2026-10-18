# Data notes: what was checked rather than assumed

Source: The Complete Journey, 84.51° (data arm of a US grocery retailer), via the `completejourney` R package v1.1.1, licence CC0.
2,469 households, 1,469,307 lines, one year (1 Jan 2017 to 1 Jan 2018). American, 2017, dollars. Not Nectar, not Sainsbury's.

| Question | How it was settled | Answer |
|---|---|---|
| Is `sales_value` before or after the loyalty-card discount? | For lines bought singly, compared with the median full-price line of the same product, store and week (588 lines) | `sales_value + retail_disc` matches the shelf price (median ratio 1.00); `sales_value` alone is 0.90. So `sales_value` is net of the loyalty discount |
| Sign of discounts | Minimum of `retail_disc` and `coupon_disc` | Stored positive |
| What is a sale? | 8,869 lines have quantity 0, 11,226 have `sales_value` 0 (coupon-only lines), a few have quantities in the thousands | A sale = `sales_value` > 0 and quantity 1 to 99 (1,444,490 lines, $4.23m) |
| Weeks | First and last timestamp per week | Weeks run Tuesday to Monday; week 1 is a two-day stub (1 to 2 Jan); weeks 2 to 53 are analysed |
| What does `promotions` contain? | Counts of codes | Only featured product-store-weeks (every row has a display or a mailer code), for 112 stores that hold 98.7% of all lines. Not-listed means not featured, not unranged |
| Ranging | Not in the data | Derived: a product is ranged in a store-week if it sold or was featured |
| Campaigns | `campaign_descriptions` | 27 campaigns; 24, 25 and 26 started in 2016; 15, 20, 21, 22 and 23 run past the data. Redemptions come only from targeted households |
| Demographics | Row counts | 801 of 2,469 households only |
| Manufacturer ids | Sales by manufacturer | Anonymised numbers. 69 is the retailer's private label (898k of 4.6m dollars) |

The supplier in the case study, manufacturer 794, is chosen because it has 139 products selling in the largest of its categories (cold
cereal), a private-label rival, 192 products on coupon, and enough buyers (1,280) for the intervals to mean something.
