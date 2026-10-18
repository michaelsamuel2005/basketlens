# Scorecard: twin seed 7

**23 of 28 checks pass.** Answer key sha256 `3f013abe8dc01cd4...` (730,782 simulated lines, 1,500 households).

| group | check | planted | found | standard | result |
|---|---|---|---|---|---|
| SQL | fact_line keeps every raw line | 730782 | 730782 | equal | PASS |
| SQL | sale table net sales match pandas | 2489757.82 | 2489757.82 | within 1e-6 | PASS |
| SQL | category buyers by quarter match pandas | [1416, 1383, 1264, 1256] | [1416, 1383, 1264, 1256] | equal | PASS |
| SQL | supplier + private label + other brands = category | [56821.09, 44703.64] | [56821.09, 44703.64] | equal | PASS |
| Decomposition | buyers x frequency x spend per trip adds exactly to the change | 0.0 | 8.185452315956354e-11 | |residual| < 1e-6 | PASS |
| Promotions | supplier model: display uplift (%) | 120.0 | 113.2 [92.6, 136.0] | planted value inside 95% interval | PASS |
| Promotions | supplier model: mailer uplift (%) | 35.0 | 33.9 [24.9, 43.6] | planted value inside 95% interval | PASS |
| Promotions | supplier model: week after a feature (%) | -22.1 | -18.1 [-20.9, -15.2] | planted value inside 95% interval | FAIL |
| Promotions | supplier model: weeks 2-3 after a feature (%) | -11.3 | -9.9 [-13.7, -5.9] | planted value inside 95% interval | PASS |
| Promotions | supplier model: cannibalisation by own products (%) | -25.9 | -32.2 [-40.2, -23.0] | planted value inside 95% interval | PASS |
| Promotions | supplier model: competitor features (%) | 0.0 | -1.6 [-20.2, 21.3] | planted value inside 95% interval | PASS |
| Promotions | category model: display uplift (%) | 120.0 | 126.8 [111.1, 143.7] | planted value inside 95% interval | PASS |
| Promotions | category model: mailer uplift (%) | 35.0 | 35.9 [28.9, 43.2] | planted value inside 95% interval | PASS |
| Journeys | lapsed buyers found: precision | 250 planted lapsers | 0.65 | >= 0.60 | PASS |
| Journeys | lapsed buyers found: recall among planted lapsers with 4+ trips in H1 | 151 detectable | 0.66 | >= 0.60 | PASS |
| Journeys | where lapsed buyers went: private-label share of what they bought instead | 0.12 | 0.13 | within 0.06 | PASS |
| Journeys | 12-week repeat rate of new buyers | 0.408 (expected from planted rates) | 0.393 [0.339, 0.450] | expected rate inside 95% interval | PASS |
| Segments | adjusted Rand index against the four planted classes | >= 0.5 | 0.95 | >= 0.50 | PASS |
| Segments | planted 'stops shopping' class lands in one segment | share of class in modal segment | 1.00 | >= 0.70 | PASS |
| Segments | segment stability (mean ARI across 80% subsamples) | >= 0.7 | 1.00 | >= 0.70 | PASS |
| Segments | segment holding the own-label class has the lowest supplier share | 0.19 | others 0.27-0.40 | lowest of all segments | PASS |
| Campaigns | pooled incremental sales: planted total inside 95% interval | 1205.0 | 1107 [350, 1740] | inside 95% interval | PASS |
| Campaigns | a plain targeted-vs-untargeted comparison overstates the effect | 1205.0 | 11152.0 | naive > 3 x planted | PASS |
| Campaigns | campaigns whose interval covers the planted effect | 6 of 6 | 4 of 6 | all but at most one | FAIL |
| Campaigns | every campaign that misses was flagged as overlapping another in its pre window | misses flagged | misses ['1', '2']; flagged ['2'] | no unflagged miss | FAIL |
| Campaigns | a campaign with no planted effect and a clean pre window is not credited with one | interval includes 0 | none to test | interval includes 0 | PASS |
| Ranging | delist the tail: realised loss inside the low-to-high transfer range | 1357 | 1699 to 1910 | inside range | FAIL |
| Ranging | delist the tail: central estimate (planted transfer rates) close to the realised loss | 1357 | 1786 | within 25% | FAIL |
