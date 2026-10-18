"""Campaign effectiveness: targeted households against matched untargeted households, before and during each campaign.

The retailer did not target at random: in the real data targeted households spend two to three times as much with the
supplier even before a campaign starts. So a plain comparison of the two groups overstates the effect. Instead, for each
campaign:
  1. households are put in strata by their store spend (quintiles) and whether they bought from the supplier in the
     weeks before the pre window and the pre window itself (never the windows being compared);
  2. untargeted households are re-weighted so each stratum has as many as the targeted group (strata with no one on either
     side are dropped);
  3. the effect is the targeted group's change in spend (campaign window minus the same number of weeks before) minus the
     weighted untargeted group's change (difference in differences);
  4. a placebo repeats step 3 one window earlier, where there should be no effect;
  5. intervals come from resampling households (the same households appear in several campaigns, so they are resampled
     together).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .ctx import Ctx

OUTCOMES = {"supplier_all": ("pre_sup", "post_sup", "prepre_sup"),
            "supplier_couponed": ("pre_cpn", "post_cpn", "prepre_cpn"),
            "store_total": ("pre_total", "post_total", "prepre_total")}


def _strata(d: pd.DataFrame, placebo: bool = False) -> pd.Series:
    """Strata from spend BEFORE the two windows being compared (never the windows themselves, which would build regression
    to the mean into the comparison): main = early + prepre windows, placebo = early window only."""
    tot = d.early_total if placebo else d.early_total + d.prepre_total
    sup = d.early_sup if placebo else d.early_sup + d.prepre_sup
    q = pd.qcut(tot.rank(method="first"), 5, labels=False)
    return q.astype(int) * 2 + (sup > 0).astype(int)


def _did(d: pd.DataFrame, w: np.ndarray, a: str, b: str, strata: np.ndarray) -> tuple[float, float, int, float]:
    """(effect per targeted household, naive difference per targeted household, matched targeted n, control-weight check)."""
    t = d.targeted.to_numpy()
    wt, wc = w * t, w * (~t)
    delta = (d[b] - d[a]).to_numpy()
    num_t = den_t = num_c = den_c = 0.0
    n_match = 0.0
    for s in np.unique(strata):
        m = strata == s
        nt, nc = wt[m].sum(), wc[m].sum()
        if nt <= 0 or nc <= 0:
            continue
        n_match += nt
        mt = (wt[m] * delta[m]).sum() / nt
        mc = (wc[m] * delta[m]).sum() / nc
        num_t += nt * mt
        num_c += nt * mc
    eff = (num_t - num_c) / n_match if n_match else float("nan")
    post = d[b].to_numpy()
    naive = (wt * post).sum() / max(wt.sum(), 1e-9) - (wc * post).sum() / max(wc.sum(), 1e-9)
    return eff, naive, int(round(n_match)), 0.0


def estimate(df: pd.DataFrame, mult: pd.Series | None = None, outcome: str = "supplier_all", placebo: bool = False,
             clean: set | None = None) -> pd.DataFrame:
    pre, post, prepre = OUTCOMES[outcome]
    rows = []
    for cid, d in df.groupby("campaign_id"):
        d = d.reset_index(drop=True)
        if placebo and (not d.has_prepre.iloc[0] or d.early_weeks.iloc[0] < 4):
            continue
        w = np.ones(len(d)) if mult is None else d.household_id.map(mult).fillna(0).to_numpy()
        strata = _strata(d, placebo).to_numpy()
        a, b = (prepre, pre) if placebo else (pre, post)
        eff, naive, n, _ = _did(d, w, a, b, strata)
        rows.append({"campaign_id": cid, "campaign_type": d.campaign_type.iloc[0], "effect_per_household": eff,
                     "naive_per_household": naive, "matched_targeted": n})
    return pd.DataFrame(rows)


def run(ctx: Ctx, draws: int = 300) -> dict:
    df = ctx.q("60_campaigns.sql")
    hh = df.household_id.unique()
    rng = np.random.default_rng(ctx.seed)
    camp_info = df.groupby("campaign_id").agg(
        campaign_type=("campaign_type", "first"), start_week=("start_week", "first"), weeks=("weeks", "first"),
        supplier_coupon_products=("n_sup_coupon_products", "first"), pre_overlap=("pre_overlap", "first"),
        targeted=("targeted", "sum"), redeemed=("redeemed", "sum")).reset_index()
    cost = df[df.targeted].groupby("campaign_id").agg(
        supplier_sales_targeted=("post_sup", "sum"), coupon_disc=("post_coupon_disc", "sum"),
        coupon_match=("post_coupon_match", "sum")).reset_index()
    camp_info = camp_info.merge(cost, on="campaign_id")
    out = {"campaigns": camp_info, "estimates": {}}
    for oc in OUTCOMES:
        for placebo in (False, True):
            pt = estimate(df, None, oc, placebo)
            boots = []
            for _ in range(draws):
                m = pd.Series(np.bincount(rng.integers(0, len(hh), len(hh)), minlength=len(hh)), index=hh)
                boots.append(estimate(df, m, oc, placebo).set_index("campaign_id").effect_per_household)
            B = pd.concat(boots, axis=1)
            pt = pt.set_index("campaign_id")
            pt["ci_low"] = B.quantile(0.025, axis=1)
            pt["ci_high"] = B.quantile(0.975, axis=1)
            pt["total_effect"] = pt.effect_per_household * pt.matched_targeted
            pt["total_low"] = pt.ci_low * pt.matched_targeted
            pt["total_high"] = pt.ci_high * pt.matched_targeted
            pt["naive_total"] = pt.naive_per_household * pt.matched_targeted
            # pooled over campaigns (sum of total effects), resampled together
            tot = (B.mul(pt.matched_targeted, axis=0)).sum(axis=0)
            pooled = {"total_effect": float(pt.total_effect.sum()), "ci_low": float(tot.quantile(0.025)),
                      "ci_high": float(tot.quantile(0.975)), "naive_total": float(pt.naive_total.sum()),
                      "targeted_household_campaigns": int(pt.matched_targeted.sum())}
            clean_ids = set(camp_info[camp_info.pre_overlap == 0].campaign_id)
            cl = pt.index.isin(clean_ids)
            pooled["clean_campaigns"] = int(cl.sum())
            if cl.any():
                tot_c = (B.loc[cl].mul(pt.matched_targeted[cl], axis=0)).sum(axis=0)
                pooled.update(clean_total_effect=float(pt.total_effect[cl].sum()), clean_ci_low=float(tot_c.quantile(0.025)),
                              clean_ci_high=float(tot_c.quantile(0.975)), clean_naive_total=float(pt.naive_total[cl].sum()))
            out["estimates"][(oc, "placebo" if placebo else "main")] = {"by_campaign": pt.reset_index(), "pooled": pooled}
    main = out["estimates"][("supplier_all", "main")]["pooled"]
    pl = out["estimates"][("supplier_all", "placebo")]["pooled"]
    cost_tot = float(camp_info.coupon_disc.sum() + camp_info.coupon_match.sum())
    sales_t = float(camp_info.supplier_sales_targeted.sum())
    out["summary"] = {
        "campaigns_eligible": int(len(camp_info)), "campaigns_total": 27,
        "supplier_sales_targeted_in_windows": sales_t, "supplier_coupon_value_in_windows": cost_tot,
        "coupon_value_pct_of_targeted_sales": 100 * cost_tot / sales_t if sales_t else float("nan"),
        "incremental_sales": main["total_effect"], "incremental_low": main["ci_low"], "incremental_high": main["ci_high"],
        "naive_incremental": main["naive_total"],
        "clean_campaigns": main.get("clean_campaigns", 0),
        "clean_incremental": main.get("clean_total_effect"), "clean_low": main.get("clean_ci_low"), "clean_high": main.get("clean_ci_high"),
        "clean_naive": main.get("clean_naive_total"),
        "placebo_effect": pl["total_effect"], "placebo_low": pl["ci_low"], "placebo_high": pl["ci_high"],
        "sales_per_coupon_dollar": main["total_effect"] / cost_tot if cost_tot else float("nan"),
        "sales_per_coupon_dollar_high": main["ci_high"] / cost_tot if cost_tot else float("nan"),
        "breakeven_margin_if_effect_at_upper_bound": cost_tot / main["ci_high"] if main["ci_high"] > 0 else float("nan"),
    }
    return out
