"""Run every analysis for one supplier and category, write the tables, and return the results."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import campaigns, promotions, ranging, segments, shopper
from .ctx import Ctx
from .recommend import recommendations


def power_for_holdout(ctx: Ctx) -> dict:
    """How big a random holdout would need to be to see a lift in supplier spend, from the observed spread."""
    df = ctx.q("60_campaigns.sql")
    c = df[~df.targeted]
    delta = (c.post_sup - c.pre_sup)
    sd, mean_post = float(delta.std()), float(c.post_sup.mean())
    z = 1.96 + 0.8416
    out = {"sd_change_per_household": sd, "mean_spend_per_household_per_window": mean_post}
    for lift in (0.10, 0.20):
        d = lift * mean_post
        out[f"n_per_arm_for_{int(lift*100)}pct_lift"] = int(np.ceil(2 * (z * sd / d) ** 2))
    n1, n2 = 1100, 1400
    out["mde_with_1100_vs_1400"] = float(z * sd * np.sqrt(1 / n1 + 1 / n2))
    out["mde_pct_with_1100_vs_1400"] = 100 * out["mde_with_1100_vs_1400"] / mean_post
    return out


def run_all(ctx: Ctx, out_dir: Path | None = None, draws: int = 300) -> dict:
    res = {"supplier": ctx.mfr, "category": ctx.cat}
    res["shopper"] = shopper.decomposition(ctx)
    res["journeys"] = shopper.journeys(ctx)
    res["segments"] = segments.segmentation(ctx)
    res["promotions"] = promotions.run(ctx)
    res["ranging"] = ranging.run(ctx)
    res["campaigns"] = campaigns.run(ctx, draws=draws)
    res["holdout"] = power_for_holdout(ctx)
    res["peers"] = ctx.q("70_peers.sql")
    res["recommendations"] = recommendations(res)
    if out_dir:
        write(res, out_dir)
    return res


def _jsonable(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, pd.DataFrame):
        return o.replace({np.nan: None}).to_dict("records")
    if isinstance(o, pd.Series):
        return o.to_dict()
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, float) and np.isnan(o):
        return None
    return o


def write(res: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    t = out / "tables"
    t.mkdir(exist_ok=True)
    res["shopper"]["periods"].to_csv(t / "shopper_periods.csv", index=False)
    res["shopper"]["decomposition"].to_csv(t / "shopper_decomposition.csv", index=False)
    j = res["journeys"]
    j["funnel"].to_csv(t / "journey_funnel.csv", index=False)
    j["km"].to_csv(t / "journey_second_purchase.csv", index=False)
    j["switching"].to_csv(t / "journey_lapsed_switching.csv", index=False)
    s = res["segments"]
    s["segments"].to_csv(t / "segments.csv", index=False)
    s["centroids"].to_csv(t / "segment_centroids.csv")
    s["households"][["household_id", "segment", "sales", "trips", "supplier_sales", "category_sales"]].to_csv(
        t / "household_segments.csv", index=False)
    p = res["promotions"]
    p["coefs_category"].to_csv(t / "promo_coefs_category.csv", index=False)
    p["coefs_supplier"].to_csv(t / "promo_coefs_supplier.csv", index=False)
    r = res["ranging"]
    r["skus"].to_csv(t / "range_skus.csv", index=False)
    r["scenarios"].to_csv(t / "range_delist_scenarios.csv", index=False)
    r["single"].to_csv(t / "range_top_sku_protection.csv", index=False)
    c = res["campaigns"]
    c["campaigns"].to_csv(t / "campaigns.csv", index=False)
    for (oc, kind), v in c["estimates"].items():
        v["by_campaign"].to_csv(t / f"campaign_effect_{oc}_{kind}.csv", index=False)
    res["peers"].to_csv(t / "peers.csv", index=False)
    slim = {k: v for k, v in res.items() if k not in ("shopper", "journeys", "segments", "ranging", "campaigns", "promotions")}
    slim["facts"] = {
        "decomposition": res["shopper"]["decomposition"], "funnel": j["funnel"], "trial": j["trial"],
        "repeat_by_deal": j["repeat_by_deal"], "lifecycle": j["lifecycle"], "flows": j["flows"],
        "segments": s["segments"], "segmentation": {"k": s["k"], "silhouette": s["silhouette"], "stability_ari": s["stability_ari"]},
        "promotions": {k: v for k, v in p.items() if k not in ("coefs_category", "coefs_supplier")},
        "promo_coefs_supplier": p["coefs_supplier"], "promo_coefs_category": p["coefs_category"],
        "ranging": {k: v for k, v in r.items() if k not in ("skus", "tail", "single", "scenarios")},
        "range_scenarios": r["scenarios"], "campaign_summary": c["summary"], "campaign_table": c["campaigns"],
        "campaign_by": {f"{oc}|{kind}": v["pooled"] for (oc, kind), v in c["estimates"].items()},
    }
    (out / "results.json").write_text(json.dumps(_jsonable(slim), indent=1, default=str))
