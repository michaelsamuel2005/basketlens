# basketlens

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
| Shopper decomposition | Supplier is rank 1 with 30% of category sales; 69% of category buyers bought it. Sales fell $480 from H1 to H2 ($9,803 to $9,322); buyers -$328, trips per buyer -$438, sales per trip $285 (adds exactly) |
| Journeys | 616 new buyers; 40% bought again within 12 weeks (95% interval 36% to 44%). Of 215 established buyers (4+ trips in H1), 42 stopped buying the supplier but kept buying cereal (about 15 silences expected by chance). Private label was 18% of what they bought instead, against 27% for all households: they went to other national brands |
| Segments | k = 4 (silhouette 0.18: cuts of a continuum; stability ARI 0.83). Supplier share of segment cereal spend runs from 23% (Mid-spend, own-label leaning) to 34% (Low-spend, all-round) |
| Promotions | In weeks featured in 25%+ of a product's stores, about 74% of units were incremental. Display and price cut move together (cut 33% vs 11%). No clear cannibalisation of the supplier's own range or post-feature dip |
| Ranging | 43 of 139 products make 80% of sales. Delisting the 77-product tail (10% of sales) costs $1,203 to $1,592 a year (central $1,372); transfer is modelled, not observed |
| Campaigns | 7 of 27 campaigns evaluable. A plain comparison credits $7,724; matched on past spend: -$58 (95% interval -$2,154 to $1,838). Redeemed supplier coupons total $122. Detecting a 20% lift needs about 2,939 households per arm |

Recommendations (computed in `recommend.py` from these results): Win share among mid-spend, own-label leaning households; Win back lapsed buyers before they settle elsewhere; Run the next campaign with a random holdout.

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

**Scorecard (seed 7): 23 of 28 checks pass** (`outputs/twin_seed7/scorecard.md`). The ones that fail:

- **supplier model: week after a feature (%)**: planted -22.1, found -18.1 [-20.9, -15.2].
- **campaigns whose interval covers the planted effect**: planted 6 of 6, found 4 of 6.
- **every campaign that misses was flagged as overlapping another in its pre window**: planted misses flagged, found misses ['1', '2']; flagged ['2'].
- **delist the tail: realised loss inside the low-to-high transfer range**: planted 1357, found 1699 to 1910.
- **delist the tail: central estimate (planted transfer rates) close to the realised loss**: planted 1357, found 1786.

The two delist failures are one fault: the loss estimate runs about 32% too high on the twin. The likely cause (not tested) is that observed purchases show only part of a household's repertoire, so some buyers
look exclusive when they are not. Read the delist loss as cautious. One campaign interval missed without its pre-window overlap flag
being raised; across seeds the pooled interval covered the planted total in 6 of 7.

**Calibration across seeds [1, 2, 3, 4, 5, 6, 7]:** the planted value lay inside the 95% interval for 39 of 42
promotion estimates; segment ARI 0.93 to 0.97 (the twin's segments are far
better separated than the real ones, so that ARI flatters the method).

## Run it

```
pip install -e ".[dev]"
python -m basketlens.cli load                      # download the CC0 files and build data/warehouse.duckdb
python -m basketlens.cli run --manufacturer 794    # any manufacturer id; category defaults to its largest
python -m basketlens.cli deck --manufacturer 794
python -m basketlens.cli tableau --manufacturer 794
python -m basketlens.cli twin --seed 7             # simulated twin and scorecard
pytest -q                                          # fast tests (about 10 seconds); add -m slow for the full scorecard
```

Layout: `src/basketlens/sql/` (01 warehouse; 10 shopper; 20-21 journeys; 30 segments; 40 promotions; 50-51 ranging; 60 campaigns; 70 peers),
Python in `src/basketlens/`, `docs/DATA_NOTES.md` (what was checked in the data), `docs/SNOWFLAKE.md`, `outputs/`.
