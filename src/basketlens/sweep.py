"""Calibration sweep: how often does the planted value fall inside the 95% interval, over several twin seeds?

    python -m basketlens.sweep 1 2 3 4 5 6 7
Promotions (6 terms) and the pooled campaign effect are scored per seed; segments by ARI.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd
from sklearn.metrics import adjusted_rand_score

from . import campaigns, promotions, segments, twin
from .ctx import Ctx
from .load import build_from_parquet


def one(seed: int, work: Path = Path("data")) -> dict:
    raw, key, arr = twin.generate(twin.TwinConfig(seed=seed))
    d = work / f"sweep{seed}"
    twin.write(raw, key, arr, d)
    con = build_from_parquet(d / "parquet", work / f"sweep{seed}.duckdb")
    ctx = Ctx(con, twin.SUPPLIER, twin.CATEGORY)
    T = key["truth"]
    pr = promotions.run(ctx)["coefs_supplier"].set_index("term")
    pct = lambda x: 100 * (math.exp(x) - 1)
    planted = {"disp": T["display_uplift_pct_at_full"], "mail": T["mailer_uplift_pct_at_full"], "after1": pct(T["after_feature_week1_effect"]),
               "after2": pct(T["after_feature_weeks2_3_effect"]), "sib": pct(T["sibling_feature_effect"]), "comp": 0.0}
    inside = {t: bool(pr.loc[t, "ci_low"] <= v <= pr.loc[t, "ci_high"]) for t, v in planted.items()}
    cs = campaigns.run(ctx, draws=150)
    tr = sum(c["expected_incremental_sales"] for c in key["campaigns"])
    s = cs["summary"]
    sg = segments.segmentation(ctx)
    h = sg["households"]
    ari = adjusted_rand_score(h.household_id.map(key["segment_of_household"]), h.segment)
    return {"seed": seed, "promo_inside": inside, "campaign_pooled_inside": bool(s["incremental_low"] <= tr <= s["incremental_high"]),
            "campaign_truth": tr, "campaign_est": s["incremental_sales"], "campaign_naive": s["naive_incremental"], "segment_ari": ari}


if __name__ == "__main__":
    seeds = [int(x) for x in sys.argv[1:]] or [1, 2, 3, 4, 5]
    rows = [one(s) for s in seeds]
    n_in = sum(sum(r["promo_inside"].values()) for r in rows)
    n = sum(len(r["promo_inside"]) for r in rows)
    out = {"seeds": seeds, "promo_intervals_inside": n_in, "promo_intervals": n,
           "campaign_pooled_inside": sum(r["campaign_pooled_inside"] for r in rows), "rows": rows}
    Path("outputs").mkdir(exist_ok=True)
    Path("outputs/sweep.json").write_text(json.dumps(out, indent=1, default=float))
    print(f"promotion intervals containing the planted value: {n_in} of {n}; pooled campaign interval: "
          f"{out['campaign_pooled_inside']} of {len(rows)}; segment ARI {[round(r['segment_ari'],2) for r in rows]}")
