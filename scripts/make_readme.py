import json
from pathlib import Path

R = json.loads(Path("outputs/real_794_cold_cereal/results.json").read_text())
S = json.loads(Path("outputs/twin_seed7/scorecard.json").read_text())
W = json.loads(Path("outputs/sweep.json").read_text())
F = R["facts"]
d = lambda x: f"-${abs(x):,.0f}" if x < 0 else f"${x:,.0f}"
p = lambda x, n=0: f"{100*x:.{n}f}%"
peers = {x["entity"]: x for x in R["peers"]}
sup = peers[R["supplier"]]
lc, fl, tr, cs, P, rg = F["lifecycle"], F["flows"], F["trial"], F["campaign_summary"], F["promotions"], F["ranging"]
sc = {r["scenario"]: r for r in F["range_scenarios"]}
pr = {r["term"]: r for r in F["promo_coefs_supplier"]}
seg = sorted(F["segments"], key=lambda r: r["supplier_share_of_segment_category"])
h = R["holdout"]
fails = [c for c in S["checks"] if not c["pass"]]
fail_lines = "\n".join(f"- **{c['check']}**: planted {c['planted']}, found {c['found']}." for c in fails)
sw = W["rows"]
text = f"""# basketlens

Supplier analytics on loyalty-card data, built as a brand manager's review of one manufacturer: who buys it, how they behave,
which customers it is losing, whether promotions and campaigns pay, and what to do next. One DuckDB warehouse, SQL models that
avoid DuckDB-only syntax, six analyses, a 12-slide deck, Tableau Public extracts, a simulated twin with a sealed answer key, tests.

**The real data are American and from 2017.** They are The Complete Journey (84.51°, the data arm of a US grocery retailer; CC0 through the
`completejourney` R package v1.1.1): 2,469 households, 1.47 million lines, one year, dollars. They are not Nectar or Sainsbury's data, and
no figure here describes either. Manufacturer ids are anonymised, so the case study is "manufacturer 794 in cold cereal".

**Built with an AI coding assistant.** Every number in the deck, tables and this README is written by code from the result tables; the
tests and the twin scorecard check the code. The supplier SQL has been run on DuckDB only, not on Snowflake (see docs/SNOWFLAKE.md).

## What it found (manufacturer 794, cold cereal, real data)

| Analysis | Finding |
|---|---|
| Shopper decomposition | Supplier is rank 1 with {p(sup['share'])} of category sales; {p(sup['penetration'])} of category buyers bought it. Sales fell {d(abs(F['decomposition'][0]['change']))} from H1 to H2 ({d(F['decomposition'][0]['sales_h1'])} to {d(F['decomposition'][0]['sales_h2'])}); buyers {d(F['decomposition'][0]['buyers'])}, trips per buyer {d(F['decomposition'][0]['frequency'])}, sales per trip {d(F['decomposition'][0]['spend_per_trip'])} (adds exactly) |
| Journeys | {tr['triers']} new buyers; {p(tr['repeat_rate'])} bought again within 12 weeks (95% interval {p(tr['repeat_ci'][0])} to {p(tr['repeat_ci'][1])}). Of {lc['established']} established buyers (4+ trips in H1), {lc['lapsed_to_others']} stopped buying the supplier but kept buying cereal (about {lc['chance_silences_expected']:.0f} silences expected by chance). Private label was {p(fl['pl_share_of_rest_q4'])} of what they bought instead, against {p(fl['pl_share_of_rest_all_households_q4'])} for all households: they went to other national brands |
| Segments | k = {F['segmentation']['k']} (silhouette {max(F['segmentation']['silhouette'].values()):.2f}: cuts of a continuum; stability ARI {F['segmentation']['stability_ari']:.2f}). Supplier share of segment cereal spend runs from {p(seg[0]['supplier_share_of_segment_category'])} ({seg[0]['segment']}) to {p(seg[-1]['supplier_share_of_segment_category'])} ({seg[-1]['segment']}) |
| Promotions | In weeks featured in 25%+ of a product's stores, about {p(P['gross_own']['pct_of_units']/100)} of units were incremental. Display and price cut move together (cut {p(P['depth_featured'])} vs {p(P['depth_not_featured'])}). No clear cannibalisation of the supplier's own range or post-feature dip |
| Ranging | {rg['pareto']['skus_for_80pct_of_sales']} of {rg['pareto']['skus']} products make 80% of sales. Delisting the {rg['tail_n']}-product tail ({p(rg['tail_sales_share'])} of sales) costs {d(sc['full transfer']['net_loss_to_supplier'])} to {d(sc['low transfer']['net_loss_to_supplier'])} a year (central {d(sc['central']['net_loss_to_supplier'])}); transfer is modelled, not observed |
| Campaigns | {cs['campaigns_eligible']} of 27 campaigns evaluable. A plain comparison credits {d(cs['naive_incremental'])}; matched on past spend: {d(cs['incremental_sales'])} (95% interval {d(cs['incremental_low'])} to {d(cs['incremental_high'])}). Redeemed supplier coupons total {d(cs['supplier_coupon_value_in_windows'])}. Detecting a 20% lift needs about {h['n_per_arm_for_20pct_lift']:,} households per arm |

Recommendations (computed in `recommend.py` from these results): {"; ".join(r['title'] for r in R['recommendations'])}.

## Measured, assumed, not known

- **Measured:** everything in the table above except the next line.
- **Assumed:** delist transfer rates (0.5/0.0, 0.8/0.4, 1.0/1.0 for repertoire/exclusive buyers); "half the gap closed" and "a quarter of lapsed spend recovered" in the sizes of the first two recommendations.
- **Not known from this data:** margins and costs (so no profit ROI), what any campaign actually offered, effects beyond one year, anything about UK shoppers.
- **Lapsed buyers:** a silence of 13 weeks can happen by chance, so the count includes some; the excess over chance is reported.
- **Campaigns:** the matched estimate assumes targeted and untargeted households would have moved alike without the campaign. Every one of the 7 evaluable campaigns overlapped another campaign carrying the supplier's products in its pre window, so even the adjusted figure is indicative.

## The simulated twin and its scorecard

`python -m basketlens.cli twin --seed 7` generates 1,500 simulated households and 730,782 lines in the same tables, plants effects
(display +120%, mailer +35%, cannibalisation, post-feature dips, a mid-year lapse, four segments, six campaigns aimed at high spenders with
true lifts of 0% to 50%, a delist with known transfer), writes them to `answer_key.json` (sha256 in `manifest.json`), runs the same analysis,
and only then opens the key.

**Scorecard (seed 7): {S['summary']['passed']} of {S['summary']['total']} checks pass** (`outputs/twin_seed7/scorecard.md`). The ones that fail:

{fail_lines}

The two delist failures are one fault: the loss estimate runs about {100*(float(next(c for c in S['checks'] if 'central estimate' in c['check'])['found'])/float(next(c for c in S['checks'] if 'central estimate' in c['check'])['planted'])-1):.0f}% too high on the twin. The likely cause (not tested) is that observed purchases show only part of a household's repertoire, so some buyers
look exclusive when they are not. Read the delist loss as cautious. One campaign interval missed without its pre-window overlap flag
being raised; across seeds the pooled interval covered the planted total in {W['campaign_pooled_inside']} of {len(sw)}.

**Calibration across seeds {W['seeds']}:** the planted value lay inside the 95% interval for {W['promo_intervals_inside']} of {W['promo_intervals']}
promotion estimates; segment ARI {min(r['segment_ari'] for r in sw):.2f} to {max(r['segment_ari'] for r in sw):.2f} (the twin's segments are far
better separated than the real ones, so that ARI flatters the method).

## Run it

```
pip install -e ".[dev]"
python -m basketlens.cli load                      # download the CC0 files and build data/warehouse.duckdb
python -m basketlens.cli run --manufacturer 794    # any manufacturer id; category defaults to its largest
python -m basketlens.cli deck --manufacturer 794
python -m basketlens.cli tableau --manufacturer 794
python -m basketlens.cli twin --seed 7             # simulated twin and scorecard
pytest -q                                          # {"fast tests (about 10 seconds)"}; add -m slow for the full scorecard
```

Layout: `src/basketlens/sql/` (01 warehouse; 10 shopper; 20-21 journeys; 30 segments; 40 promotions; 50-51 ranging; 60 campaigns; 70 peers),
Python in `src/basketlens/`, `docs/DATA_NOTES.md` (what was checked in the data), `docs/SNOWFLAKE.md`, `outputs/`.
"""
Path("README.md").write_text(text)
print(len(text.split()), "words")
