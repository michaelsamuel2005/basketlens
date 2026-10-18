# Tableau Public: build guide for the basketlens dashboard (about 3 hours)

Files are in `tableau/`. Connect each as a text file (Data > New Data Source > Text file). Do not join them; each sheet uses one source.

## 1. Segment view (`segments.csv`)
1. Drag `segment` to Rows, `supplier_share_of_segment_category` to Columns. Sort descending. Format > Percentage, 0 decimals.
2. Drag `brand_index` to Color (diverging, centre 100). Add `share_of_households` to Label.
3. Create a **parameter** `Measure` (String): list = "Supplier share of segment cereal spend", "Brand index", "Supplier buyers". Show the control.
4. Calculated field `Selected measure`:
   `CASE [Measure] WHEN "Brand index" THEN SUM([brand_index]) WHEN "Supplier buyers" THEN SUM([supplier_penetration]) ELSE SUM([supplier_share_of_segment_category]) END`
   Put it on Columns instead of the field in step 1.

## 2. Weekly share trend (`weekly_entity.csv`)
1. Columns `week` (continuous), Rows `net_sales`, Color `entity`. Mark type: Line.
2. Calculated field `Share` (table calculation): `SUM([net_sales]) / TOTAL(SUM([net_sales]))` computed along `entity`. Switch Rows to `Share` for the supplier only with a filter on `entity`.
3. Add a **level-of-detail** reference: `{ FIXED [entity] : AVG([net_sales]) }` as a dashed reference line to show each entity's weekly average.

## 3. Promotion weeks (`product_week_promo.csv`)
1. Columns `week`, Rows `SUM([units])`, Color: calculated field `Featured` = `[feat_share] >= 0.25`.
2. Filter `is_supplier` = True. Add a dual axis with `AVG([feat_share])` as an area mark at 30% opacity.

## 4. Campaigns: plain comparison vs matched (`campaign_effect.csv`)
1. Rows `campaign_id`; Columns `naive_total` and `total_effect` (Measure Names / Measure Values, bars side by side).
2. Add `total_low` and `total_high` as a reference band per campaign (Analytics > Reference line > Band).
3. Title the sheet with the honest reading: "targeted households already spent more before the campaign".

## 5. Range (`range_skus.csv`)
1. Rows `net_sales` (descending), Columns `product_id` as a Pareto: add a table calculation `Running total` of `SUM([net_sales])` as % of total, dual axis, line.

## Dashboard
Size: Automatic. Layout: sheet 1 top left, sheet 2 top right, sheets 3 and 4 below, a text box with the three recommendations (copy from the deck, slide 10). Add the Source line from the deck footer in a text box. Add a filter action from sheet 1 to the others on `segment` where the field exists.

## Publish
File > Save to Tableau Public As... Sign in, name it "Basketlens: cold cereal supplier review". Open the link in a private window to check a stranger can see it, then add the URL to the CV only after that works.
