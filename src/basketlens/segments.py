"""Behavioural segmentation of households (k-means on seven shopping behaviours) and the supplier's brand index."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler

from .ctx import Ctx

FEATURES = ["log_sales", "log_trips", "log_basket", "recency_weeks", "pl_share", "deal_depth", "fresh_share"]


def features(h: pd.DataFrame) -> pd.DataFrame:
    x = pd.DataFrame({
        "log_sales": np.log(h.sales), "log_trips": np.log(h.trips), "log_basket": np.log(h.basket_value),
        "recency_weeks": h.recency_weeks.astype(float), "pl_share": h.pl_share, "deal_depth": h.deal_depth,
        "fresh_share": h.fresh_share}, index=h.index).fillna(0.0)
    return x


def choose_k(Z: np.ndarray, seed: int, ks=range(3, 8)) -> tuple[int, dict]:
    sil = {}
    for k in ks:
        lab = KMeans(k, n_init=10, random_state=seed).fit_predict(Z)
        sil[k] = float(silhouette_score(Z, lab, sample_size=min(2000, len(Z)), random_state=seed))
    best = max(sil, key=sil.get)
    return best, sil


def stability(Z: np.ndarray, k: int, labels: np.ndarray, seed: int, reps: int = 20) -> float:
    rng = np.random.default_rng(seed)
    aris = []
    for _ in range(reps):
        idx = rng.choice(len(Z), int(0.8 * len(Z)), replace=False)
        lab = KMeans(k, n_init=5, random_state=int(rng.integers(1e6))).fit_predict(Z[idx])
        aris.append(adjusted_rand_score(labels[idx], lab))
    return float(np.mean(aris))


def name_segments(cent: pd.DataFrame) -> dict[int, str]:
    """Plain-English names from the centroid z-scores, by fixed rules (so a re-run gives names that match the numbers):
    spend tier from log_sales, then the strongest behaviour if it is clearly above average."""
    names, used = {}, set()
    for c, r in cent.iterrows():
        if r.recency_weeks > 0.8 and r.log_sales < 0:
            base = "Drifting away"
        else:
            tier = "High-spend" if r.log_sales >= 0.4 else ("Low-spend" if r.log_sales <= -0.4 else "Mid-spend")
            cand = {"own-label leaning": r.pl_share, "deal-led": r.deal_depth, "fresh-led": r.fresh_share,
                    "big-basket": r.log_basket - 0.4 * r.log_trips, "frequent top-up": r.log_trips - 0.4 * r.log_basket}
            flav = max(cand, key=cand.get)
            base = f"{tier}, {flav}" if cand[flav] >= 0.3 else f"{tier}, all-round"
        nm, i = base, 2
        while nm in used:
            nm, i = f"{base} ({i})", i + 1
        used.add(nm)
        names[c] = nm
    return names


def segmentation(ctx: Ctx, k: int | None = None) -> dict:
    h = ctx.q("30_segments.sql").reset_index(drop=True)
    X = features(h)
    Z = StandardScaler().fit_transform(X.to_numpy())
    best, sil = choose_k(Z, ctx.seed)
    k = k or best
    km = KMeans(k, n_init=20, random_state=ctx.seed).fit(Z)
    lab = km.labels_
    cent = pd.DataFrame(km.cluster_centers_, columns=FEATURES)
    names = name_segments(cent)
    h["segment"] = [names[i] for i in lab]
    stab = stability(Z, k, lab, ctx.seed)
    tot_sales, tot_sup, tot_cat = h.sales.sum(), h.supplier_sales.sum(), h.category_sales.sum()
    g = h.groupby("segment")
    seg = pd.DataFrame({
        "households": g.size(), "share_of_households": g.size() / len(h),
        "sales_per_household": g.sales.mean(), "trips_per_household": g.trips.mean(),
        "private_label_share": g.pl_share.mean(), "deal_depth": g.deal_depth.mean(), "fresh_share": g.fresh_share.mean(),
        "supplier_buyers": g.supplier_sales.apply(lambda v: int((v > 0).sum())),
        "supplier_sales": g.supplier_sales.sum(),
    })
    seg["supplier_penetration"] = seg.supplier_buyers / seg.households
    seg["supplier_sales_per_buyer"] = seg.supplier_sales / seg.supplier_buyers.replace(0, np.nan)
    seg["share_of_store_sales"] = g.sales.sum() / tot_sales
    seg["share_of_supplier_sales"] = seg.supplier_sales / tot_sup
    seg["share_of_category_sales"] = g.category_sales.sum() / tot_cat
    seg["brand_index"] = 100 * seg.share_of_supplier_sales / seg.share_of_store_sales
    seg["category_index"] = 100 * seg.share_of_category_sales / seg.share_of_store_sales
    # supplier share of the category inside each segment
    seg["supplier_share_of_segment_category"] = seg.supplier_sales / g.category_sales.sum()
    seg = seg.sort_values("share_of_supplier_sales", ascending=False).reset_index()
    cent["segment"] = [names[i] for i in cent.index]
    # demographics where we have them (801 of 2,469 households)
    dm = h[h.has_demographics]
    demo = pd.crosstab(dm.segment, dm.income.map(income_band), normalize="index").round(3) if len(dm) else pd.DataFrame()
    return {"segments": seg, "centroids": cent.set_index("segment"), "households": h, "k": k, "silhouette": sil,
            "stability_ari": stab, "demographic_households": int(len(dm)), "income_mix": demo}


def income_band(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "unknown"
    lo = str(v).replace("K", "").replace("Under ", "0-").replace("+", "-999")
    try:
        first = int(lo.split("-")[0])
    except ValueError:
        return "unknown"
    return "under 35K" if first < 35 else ("35K-74K" if first < 75 else "75K and over")
