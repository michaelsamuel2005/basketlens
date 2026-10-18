"""Promotion uplift against a baseline, cannibalisation of the supplier's own range, and pull-forward.

Model (Poisson with log link, cluster-robust by product): weekly units of a product in the stores that report promotions
    log E[units] = product effect + week effect + b1*display_share + b2*mailer_share + b3*after1 + b4*after2
                   + b5*sibling_feature + b6*competitor_feature
Product effects absorb how big each product is; week effects absorb seasonality and store traffic. A "baseline" is the
fitted units with the promotion terms set to zero. display_share and mailer_share are the shares of the product's ranged
stores featuring it that week, so exp(b)-1 is the change when every ranged store features it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

from .ctx import Ctx

TERMS = ["disp", "mail", "after1", "after2", "sib", "comp"]


def build_panel(ctx: Ctx) -> pd.DataFrame:
    p = ctx.q("40_promotions.sql")
    p["disp"] = (p.n_display / p.n_ranged).clip(0, 1)
    p["mail"] = (p.n_mailer / p.n_ranged).clip(0, 1)
    p["feat"] = (p.n_feat / p.n_ranged).clip(0, 1)
    p = p.sort_values(["product_id", "week"]).reset_index(drop=True)
    p["is_sup"] = p.manufacturer_id == ctx.mfr
    g = p.groupby("product_id").feat
    prev1, prev2, prev3 = g.shift(1).fillna(0), g.shift(2).fillna(0), g.shift(3).fillna(0)
    now_off = p.feat < 0.25
    # after1: featured (in >= 25% of ranged stores) last week, not now. after2: the same, two or three weeks ago, with no
    # feature in between. A pull-forward effect would make both negative.
    p["after1"] = ((prev1 >= 0.25) & now_off).astype(float)
    p["after2"] = (((prev2 >= 0.25) & (prev1 < 0.25) & now_off) |
                   ((prev3 >= 0.25) & (prev2 < 0.25) & (prev1 < 0.25) & now_off)).astype(float)
    # sibling / competitor feature pressure: unit-weighted mean feature share of the other products in the same ptype
    w = p.groupby("product_id").units.transform("sum").astype(float) + 1.0
    p["_w"] = w
    p["_wf"] = w * p.feat
    for name, grp in (("sib", ["ptype", "manufacturer_id", "week"]), ("comp", ["ptype", "week"])):
        tot_w = p.groupby(grp)["_w"].transform("sum")
        tot_wf = p.groupby(grp)["_wf"].transform("sum")
        if name == "sib":
            den = tot_w - p["_w"]
            num = tot_wf - p["_wf"]
            p["sib"] = np.where(den > 0, num / den.where(den > 0, 1), 0.0)
        else:  # competitors = same ptype, other manufacturers
            sib_tot_w = p.groupby(["ptype", "manufacturer_id", "week"])["_w"].transform("sum")
            sib_tot_wf = p.groupby(["ptype", "manufacturer_id", "week"])["_wf"].transform("sum")
            den = tot_w - sib_tot_w
            num = tot_wf - sib_tot_wf
            p["comp"] = np.where(den > 0, num / den.where(den > 0, 1), 0.0)
    return p.drop(columns=["_w", "_wf"])


def fit(panel: pd.DataFrame, min_units: int = 20):
    keep = panel.groupby("product_id").units.transform("sum") >= min_units
    d = panel[keep].copy()
    d["pid"] = d.product_id.astype(str)
    d["wk"] = d.week.astype(str)
    f = "units ~ " + " + ".join(TERMS) + " + C(pid) + C(wk)"
    m = smf.glm(f, data=d, family=sm.families.Poisson()).fit(
        cov_type="cluster", cov_kwds={"groups": pd.factorize(d.pid)[0]}, maxiter=100)
    return m, d


def coef_table(m) -> pd.DataFrame:
    rows = []
    for t in TERMS:
        b, se = m.params[t], m.bse[t]
        rows.append({"term": t, "coef": b, "se": se, "pct_effect": 100 * (np.exp(b) - 1),
                     "ci_low": 100 * (np.exp(b - 1.96 * se) - 1), "ci_high": 100 * (np.exp(b + 1.96 * se) - 1),
                     "p_value": m.pvalues[t]})
    return pd.DataFrame(rows)


def counterfactual(m, d: pd.DataFrame, zero: list[str], rows: pd.Series, draws: int = 400, seed: int = 1729) -> dict:
    """Units in `rows` with the terms in `zero` set to 0 versus as observed, point estimate and simulated 95% interval."""
    d0 = d.copy()
    for t in zero:
        d0[t] = 0.0
    names = list(m.params.index)
    X = m.model.exog
    X0 = pd.DataFrame(X, columns=names)
    X1 = X0.copy()
    for t in zero:
        X1[t] = 0.0
    r = rows.to_numpy()
    rng = np.random.default_rng(seed)
    sims = rng.multivariate_normal(m.params.to_numpy(), m.cov_params().to_numpy(), size=draws)
    act = np.exp(X0.to_numpy()[r] @ sims.T).sum(axis=0)
    base = np.exp(X1.to_numpy()[r] @ sims.T).sum(axis=0)
    inc = act - base
    pt_act = np.exp(X0.to_numpy()[r] @ m.params.to_numpy()).sum()
    pt_base = np.exp(X1.to_numpy()[r] @ m.params.to_numpy()).sum()
    return {"fitted_units": float(pt_act), "baseline_units": float(pt_base), "incremental_units": float(pt_act - pt_base),
            "inc_low": float(np.percentile(inc, 2.5)), "inc_high": float(np.percentile(inc, 97.5)),
            "pct_of_units": float(100 * (pt_act - pt_base) / pt_act) if pt_act else float("nan")}


def run(ctx: Ctx, min_units: int = 20) -> dict:
    panel = build_panel(ctx)
    m_all, d_all = fit(panel, min_units)
    sup_panel = panel[panel.is_sup]
    m_sup, d_sup = fit(sup_panel, min_units)
    d_sup = d_sup.reset_index(drop=True)
    d_all = d_all.reset_index(drop=True)
    feat_rows = (d_sup.feat >= 0.25)
    own = ["disp", "mail"]
    res = {
        "n_products_category": d_all.product_id.nunique(), "n_products_supplier": d_sup.product_id.nunique(),
        "coefs_category": coef_table(m_all), "coefs_supplier": coef_table(m_sup),
        "gross_own": counterfactual(m_sup, d_sup, own, feat_rows),
        "net_all_features": counterfactual(m_sup, d_sup, own + ["sib"], feat_rows),
        "cannibalised_by_siblings": counterfactual(m_sup, d_sup, ["sib"], pd.Series(True, index=d_sup.index)),
        "pull_forward": counterfactual(m_sup, d_sup, ["after1", "after2"], (d_sup.after1 + d_sup.after2) > 0),
        "competitor_pressure": counterfactual(m_sup, d_sup, ["comp"], pd.Series(True, index=d_sup.index)),
    }
    fw = d_sup[feat_rows]
    res["featured_weeks"] = int(len(fw))
    res["depth_featured"] = float(fw.retail_disc.sum() / fw.shelf_value.sum()) if fw.shelf_value.sum() else float("nan")
    nf = d_sup[d_sup.feat < 0.05]
    res["depth_not_featured"] = float(nf.retail_disc.sum() / nf.shelf_value.sum()) if nf.shelf_value.sum() else float("nan")
    res["panel_rows"] = int(len(d_sup))
    # product-level view for the scorecard: promoted share of sales and share of units sold in featured weeks
    s = sup_panel.copy()
    res["supplier_share_units_in_featured_weeks"] = float(s[s.feat >= 0.25].units.sum() / max(1, s.units.sum()))
    res["converged"] = bool(m_all.converged and m_sup.converged)
    return res
