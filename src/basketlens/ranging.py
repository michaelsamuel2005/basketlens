"""Ranging: SKU productivity and what happens to the supplier's sales if SKUs are delisted (transferable demand).

Nothing in this data shows a delist happening, so transfer is modelled, not observed, and reported as a range:
  repertoire buyers (bought another product of the same type in the year): a share tau_rep of the delisted SKU's spend
     moves to the other products they already buy, in proportion to what they spend on them; the rest leaves the category;
  exclusive buyers (bought nothing else of that type): a share tau_excl moves to the other products of the type in
     proportion to the type's sales; the rest leaves the category.
Scenarios (tau_rep, tau_excl): low transfer (0.5, 0.0), central (0.8, 0.4), full transfer (1.0, 1.0: nobody leaves the
category, the upper bound on transfer). These are assumptions. Observed purchases understate each household's repertoire, so
some 'exclusive' buyers are not; the central case is therefore cautious.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .ctx import Ctx

SCENARIOS = {"low transfer": (0.5, 0.0), "central": (0.8, 0.4), "full transfer": (1.0, 1.0)}


def delist_impact(rep: pd.DataFrame, sku: pd.DataFrame, delist: set[str], tau_rep: float, tau_excl: float,
                  supplier: str) -> dict:
    """Supplier sales lost, kept by its other SKUs, moved to other brands, and lost to the category."""
    d = rep[rep.product_id.isin(delist)]
    keep_rep = rep[~rep.product_id.isin(delist)]
    type_sales = sku[~sku.product_id.isin(delist)].groupby("ptype").apply(
        lambda g: pd.Series({"all": g.net_sales.sum(), "sup": g[g.is_supplier].net_sales.sum()}), include_groups=False)
    alt = keep_rep.groupby(["household_id", "ptype"]).apply(
        lambda g: pd.Series({"alt_all": g.spend.sum(), "alt_sup": g[g.manufacturer_id == supplier].spend.sum()}),
        include_groups=False)
    out = {"delisted_sales": 0.0, "kept_by_supplier": 0.0, "moved_to_others": 0.0, "lost_to_category": 0.0}
    sup_d = d[d.manufacturer_id == supplier]
    for r in sup_d.itertuples():
        s = r.spend
        out["delisted_sales"] += s
        key = (r.household_id, r.ptype)
        if key in alt.index and alt.loc[key, "alt_all"] > 0:
            tau, sup_share = tau_rep, alt.loc[key, "alt_sup"] / alt.loc[key, "alt_all"]
        else:
            ts = type_sales.loc[r.ptype] if r.ptype in type_sales.index else None
            tau = tau_excl
            sup_share = (ts["sup"] / ts["all"]) if ts is not None and ts["all"] > 0 else 0.0
        out["kept_by_supplier"] += s * tau * sup_share
        out["moved_to_others"] += s * tau * (1 - sup_share)
        out["lost_to_category"] += s * (1 - tau)
    out["net_loss_to_supplier"] = out["delisted_sales"] - out["kept_by_supplier"]
    out["transfer_rate_to_supplier"] = out["kept_by_supplier"] / out["delisted_sales"] if out["delisted_sales"] else float("nan")
    return out


def run(ctx: Ctx, tail_share: float = 0.10) -> dict:
    sku = ctx.q("50_ranging.sql")
    sku["net_sales"] = sku.net_sales.astype(float)
    rep = ctx.q("51_repertoire.sql")
    sup = sku[sku.is_supplier].copy()
    sup["sales_per_ranged_store_week"] = sup.net_sales / sup.ranged_store_weeks.replace(0, np.nan)
    sup = sup.sort_values("net_sales", ascending=False).reset_index(drop=True)
    sup["cum_share"] = sup.net_sales.cumsum() / sup.net_sales.sum()
    n = len(sup)
    pareto = {"skus": n, "skus_for_80pct_of_sales": int((sup.cum_share < 0.8).sum() + 1),
              "top10_share": float(sup.net_sales.head(10).sum() / sup.net_sales.sum()),
              "bottom_half_share": float(sup.net_sales.tail(n // 2).sum() / sup.net_sales.sum())}
    # exclusive buyers per SKU: bought no other product of the same type in the year
    cnt = rep.groupby(["household_id", "ptype"]).product_id.transform("nunique")
    rep2 = rep.assign(exclusive=(cnt == 1))
    ex = rep2[rep2.manufacturer_id == ctx.mfr].groupby("product_id").apply(
        lambda g: pd.Series({"exclusive_buyer_share": g.exclusive.mean(), "exclusive_spend_share": g[g.exclusive].spend.sum() / g.spend.sum()}),
        include_groups=False).reset_index()
    sup = sup.merge(ex, on="product_id", how="left")
    # delist ranking: lowest sales per ranged store-week first; tail = the lowest SKUs holding tail_share of sales
    rank = sup.sort_values("sales_per_ranged_store_week")
    cum = rank.net_sales.cumsum() / rank.net_sales.sum()
    tail = rank[cum <= tail_share]
    tail_ids = set(tail.product_id)
    scen = []
    for name, (tr, te) in SCENARIOS.items():
        r = delist_impact(rep, sku, tail_ids, tr, te, ctx.mfr)
        scen.append({"scenario": name, "tau_repertoire": tr, "tau_exclusive": te, **r,
                     "net_loss_pct_of_supplier_category_sales": 100 * r["net_loss_to_supplier"] / sup.net_sales.sum()})
    scen = pd.DataFrame(scen)
    # single-SKU view for the top-selling SKUs (central): how protected is each by the rest of the range
    single = []
    for pid in sup.head(15).product_id:
        r = delist_impact(rep, sku, {pid}, *SCENARIOS["central"], ctx.mfr)
        single.append({"product_id": pid, **r})
    single = pd.DataFrame(single).merge(sup[["product_id", "ptype", "package_size", "net_sales", "buyers"]], on="product_id")
    return {"skus": sup, "pareto": pareto, "tail": tail, "tail_n": len(tail), "tail_sales": float(tail.net_sales.sum()),
            "tail_sales_share": float(tail.net_sales.sum() / sup.net_sales.sum()), "scenarios": scen, "single": single,
            "supplier_sales": float(sup.net_sales.sum())}
