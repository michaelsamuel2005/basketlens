"""A simulated twin of the Complete Journey data, with a sealed answer key.

The twin has the same tables and columns as the real data, so every SQL model and analysis runs on it unchanged. Because
the data are simulated, the effects are planted and written to `answer_key.json`, which no analysis code reads; only
scorecard.py opens it, after the analysis has run.

Planted (see TRUTH): a display and a mailer uplift, cannibalisation between the supplier's own products, a dip in the
weeks after a feature, a habit effect after a first purchase, a mid-year lapse of established buyers to a rival brand,
four behavioural segments (one that stops shopping), six campaigns aimed at high spenders with true lifts from 0% to 50%,
and (in the delist variant) the transfer of a delisted product's demand to the products its buyers already use.
Nothing here describes any real retailer, supplier or shopper.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import poisson

SUPPLIER, RIVAL, PLM = "9001", "9002", "69"
CATEGORY = "SIM CEREAL"
PTYPES = ["KIDS CEREAL", "FAMILY CEREAL", "ADULT CEREAL"]
WEEK2_START = pd.Timestamp("2017-01-03")          # a Tuesday, as in the real data
WEEKS = list(range(2, 54))

TRUTH = {
    "display_uplift_pct_at_full": 120.0,           # exp(beta_display) - 1, when every store features it on display
    "mailer_uplift_pct_at_full": 35.0,
    "sibling_feature_effect": -0.30,               # log effect of the siblings' feature share on a product
    "competitor_feature_effect": 0.0,              # none planted
    "after_feature_week1_effect": -0.25,           # log effect in the week after a feature
    "after_feature_weeks2_3_effect": -0.12,
    "habit_gamma": 1.6, "habit_tau_weeks": 5.0,    # purchase rate x(1+(gamma-1)exp(-weeks since last buy/tau))
    "lapse_week": 28, "lapse_share_of_established": 0.35,
    "tau_repertoire": 0.8, "tau_exclusive": 0.4,   # delist transfer (used only in the delist variant)
    "campaign_lifts": [1.30, 1.00, 1.20, 1.50, 1.00, 1.25],     # x purchase rate of couponed supplier products
    "campaign_starts": [8, 15, 22, 35, 42, 49], "campaign_weeks": [5, 5, 5, 5, 5, 5],
    "campaign_targeted": [700, 400, 700, 300, 700, 300],
}
SEG_NAMES = ["heavy", "own-label leaning", "light", "drifting"]
SEG = {  # trips/week, lines per trip, own-label prob, deal prob, fresh prob, cereal units/week, supplier aff, PL aff
    0: dict(trips=1.8, lines=7, pl=0.14, deal=0.18, fresh=0.30, cereal=0.50, sup=1.2, pl_aff=0.6),
    1: dict(trips=1.4, lines=6, pl=0.30, deal=0.26, fresh=0.30, cereal=0.35, sup=0.7, pl_aff=1.9),
    2: dict(trips=0.8, lines=5, pl=0.18, deal=0.14, fresh=0.24, cereal=0.15, sup=1.0, pl_aff=1.0),
    3: dict(trips=0.8, lines=5, pl=0.18, deal=0.14, fresh=0.24, cereal=0.15, sup=1.0, pl_aff=1.0),
}
SEG_P = [0.35, 0.30, 0.25, 0.10]
DRIFT_STOP_WEEK = 20


@dataclass
class TwinConfig:
    seed: int = 7
    n_households: int = 1500
    n_stores: int = 24
    delist_ids: tuple = ()          # product ids removed from the range for the whole year (the delist variant)


def _products(rng):
    spec = {SUPPLIER: (5, 4, 3), RIVAL: (4, 3, 3), "9003": (2, 2, 2), "9004": (1, 1, 2), PLM: (3, 3, 2)}
    price0 = {"KIDS CEREAL": 3.6, "FAMILY CEREAL": 3.9, "ADULT CEREAL": 4.3}
    rows, n = [], 0
    for mfr, counts in spec.items():
        for t, k in zip(PTYPES, counts):
            for _ in range(k):
                n += 1
                price = price0[t] * rng.uniform(0.8, 1.25) * (0.65 if mfr == PLM else 1.0)
                rows.append(dict(product_id=f"C{n:04d}", manufacturer_id=mfr, department="GROCERY",
                                 brand="Private" if mfr == PLM else "National", product_category=CATEGORY,
                                 product_type=t, package_size=f"{int(rng.choice([12, 14, 18, 24]))} OZ",
                                 list_price=round(price, 2), pop=float(rng.lognormal(0, 0.55))))
    cereal = pd.DataFrame(rows)
    fill_cats = [("FRESH FRUIT", "PRODUCE"), ("FRESH MEAT", "MEAT"), ("DELI MEATS", "DELI"),
                 ("CANNED GOODS", "GROCERY"), ("SNACKS", "GROCERY"), ("HOUSEHOLD", "DRUG GM")]
    frows = []
    for ci, (cat, dep) in enumerate(fill_cats):
        for j in range(20):
            private = j < 6
            frows.append(dict(product_id=f"F{ci}{j:02d}", manufacturer_id=PLM if private else str(8001 + int(rng.integers(12))),
                              department=dep, brand="Private" if private else "National", product_category=cat,
                              product_type=cat, package_size="1 EA",
                              list_price=round(float(rng.lognormal(np.log(3.0), 0.5)) * (0.7 if private else 1), 2), pop=1.0))
    return cereal, pd.DataFrame(frows)


def _features(rng, cereal, S):
    P, W = len(cereal), len(WEEKS)
    d, m, u = np.zeros((P, W)), np.zeros((P, W)), np.zeros((P, W))
    store_sets = {}
    for i, r in enumerate(cereal.itertuples()):
        q = 0.25 if r.manufacturer_id == SUPPLIER else (0.12 if r.manufacturer_id == PLM else 0.15)
        w = 0
        while w < W:
            if rng.random() < q / 1.4:
                length = 1 if rng.random() < 0.6 else 2
                mm = rng.uniform(0.5, 1.0) if rng.random() < 0.7 else 0.0
                dd = rng.uniform(0.2, 1.0) if rng.random() < 0.5 else 0.0
                if mm == 0 and dd == 0:
                    mm = rng.uniform(0.5, 1.0)
                for k in range(length):
                    if w + k >= W:
                        break
                    ds = rng.choice(S, int(round(dd * S)), replace=False) if dd > 0 else np.array([], dtype=int)
                    ms = rng.choice(S, int(round(mm * S)), replace=False) if mm > 0 else np.array([], dtype=int)
                    store_sets[(i, w + k)] = (ds, ms)
                    d[i, w + k], m[i, w + k] = len(ds) / S, len(ms) / S
                    u[i, w + k] = len(set(ds) | set(ms)) / S
                w += length + 1
            else:
                w += 1
    return d, m, u, store_sets


def generate(cfg: TwinConfig = TwinConfig()):
    rng = np.random.default_rng(cfg.seed)
    N, S = cfg.n_households, cfg.n_stores
    cereal, filler = _products(rng)
    P, W = len(cereal), len(WEEKS)
    hid = np.array([str(1000 + i) for i in range(N)])
    seg = rng.choice(4, N, p=SEG_P)
    sp = {k: np.array([SEG[s][k] for s in seg]) for k in SEG[0]}
    noise = rng.lognormal(0, 0.45, N)
    trips_rate, lines_h = sp["trips"] * noise, sp["lines"]
    base_cat = sp["cereal"] * rng.lognormal(0, 0.5, N)
    home = np.stack([rng.integers(0, S, N), rng.integers(0, S, N)], axis=1)
    active = np.ones((N, W))
    active[seg == 3, DRIFT_STOP_WEEK - 1:] = 0.0
    mfr = cereal.manufacturer_id.to_numpy()
    ptype_idx = cereal.product_type.map({t: i for i, t in enumerate(PTYPES)}).to_numpy()
    is_sup, is_pl, is_riv = mfr == SUPPLIER, mfr == PLM, mfr == RIVAL
    pop = cereal["pop"].to_numpy()
    # affinities and repertoires
    aff = np.ones((N, P))
    aff[:, is_sup] = sp["sup"][:, None]
    aff[:, is_pl] = sp["pl_aff"][:, None]
    rep = np.zeros((N, P), bool)
    for t in range(3):
        idx = np.where(ptype_idx == t)[0]
        for h in range(N):
            r = int(rng.choice([1, 2, 3], p=[0.4, 0.4, 0.2]))
            wts = pop[idx] * aff[h, idx]
            rep[h, rng.choice(idx, size=min(r, len(idx)), replace=False, p=wts / wts.sum())] = True
    taste = rng.dirichlet([3, 3, 2], N)

    def shares(aff_m, delist=()):
        Wt = pop[None, :] * aff_m * np.where(rep, 1.0, 0.03)
        sh = np.zeros((N, P))
        for t in range(3):
            idx = np.where(ptype_idx == t)[0]
            sh[:, idx] = taste[:, [t]] * Wt[:, idx] / Wt[:, idx].sum(axis=1, keepdims=True)
        for x in delist:  # transfer a delisted product's demand
            t = ptype_idx[x]
            lost = sh[:, x].copy()
            sh[:, x] = 0.0
            idx = np.array([j for j in np.where(ptype_idx == t)[0] if j != x and j not in delist])
            repw = np.where(rep[:, idx], sh[:, idx], 0.0)
            has_rep = repw.sum(axis=1) > 0
            sh[np.ix_(has_rep, idx)] += TRUTH["tau_repertoire"] * lost[has_rep, None] * repw[has_rep] / repw[has_rep].sum(axis=1, keepdims=True)
            pw = pop[idx] / pop[idx].sum()
            sh[np.ix_(~has_rep, idx)] += TRUTH["tau_exclusive"] * lost[~has_rep, None] * pw[None, :]
        return sh

    delist = tuple(int(np.where(cereal.product_id == x)[0][0]) for x in cfg.delist_ids)
    sh_before = shares(aff, delist)
    sup_share = sh_before[:, is_sup].sum(axis=1)
    established = np.where(sup_share >= 0.25)[0]
    lapsed = established[rng.random(len(established)) < TRUTH["lapse_share_of_established"]]
    aff2 = aff.copy()
    aff2[np.ix_(lapsed, np.where(is_sup)[0])] *= 0.05
    aff2[np.ix_(lapsed, np.where(is_riv)[0])] *= 2.5
    sh_after = shares(aff2, delist)

    d, m, u, store_sets = _features(rng, cereal, S)
    for x in delist:                       # a delisted product is neither featured nor a source of cannibalisation
        d[x], m[x], u[x] = 0.0, 0.0, 0.0
        for key_ in [k for k in store_sets if k[0] == x]:
            del store_sets[key_]
    # price-cut depth: a feature comes with a cut (a correlate, not a planted cause)
    depth = 0.05 + np.where(u > 0, 0.10 + 0.25 * np.maximum(d, m), 0.0)
    # planted multipliers on a product-week
    wpop = pop
    sib = np.zeros((P, W))
    for i in range(P):
        sibs = [j for j in range(P) if j != i and mfr[j] == mfr[i] and ptype_idx[j] == ptype_idx[i]]
        if sibs:
            sib[i] = (wpop[sibs, None] * u[sibs]).sum(axis=0) / wpop[sibs].sum()
    comp = np.zeros((P, W))
    prev1 = np.concatenate([np.zeros((P, 1)), u[:, :-1]], axis=1)
    prev2 = np.concatenate([np.zeros((P, 2)), u[:, :-2]], axis=1)
    prev3 = np.concatenate([np.zeros((P, 3)), u[:, :-3]], axis=1)
    now_off = u < 0.25
    a1 = ((prev1 >= 0.25) & now_off).astype(float)
    a2 = (((prev2 >= 0.25) & (prev1 < 0.25) & now_off) | ((prev3 >= 0.25) & (prev2 < 0.25) & (prev1 < 0.25) & now_off)).astype(float)
    logm = (np.log(1 + TRUTH["display_uplift_pct_at_full"] / 100) * d + np.log(1 + TRUTH["mailer_uplift_pct_at_full"] / 100) * m
            + TRUTH["sibling_feature_effect"] * sib + TRUTH["after_feature_week1_effect"] * a1
            + TRUTH["after_feature_weeks2_3_effect"] * a2)
    pm = np.exp(logm)                                                   # (P, W)

    # campaigns
    sup_idx = np.where(is_sup)[0]
    score = np.log(base_cat * sup_share + 1e-6)
    score = (score - score.mean()) / score.std()
    camps, coupon_rows = [], []
    for c, (s, l, n_t, lift) in enumerate(zip(TRUTH["campaign_starts"], TRUTH["campaign_weeks"], TRUTH["campaign_targeted"],
                                              TRUTH["campaign_lifts"])):
        tgt = np.argsort(-(score + 0.7 * rng.normal(size=N)))[:n_t]
        cpn = np.concatenate([rng.choice(sup_idx, int(round(0.6 * len(sup_idx))), replace=False),
                              rng.choice(np.where(~is_sup)[0], 5, replace=False)])
        camps.append(dict(id=str(c + 1), start=s, weeks=l, targeted=tgt, coupon=cpn, lift=lift, type="Type A" if n_t >= 700 else "Type B",
                          exp_units=0.0, exp_sales=0.0))
        for j in cpn:
            coupon_rows.append(dict(coupon_upc=f"U{c+1}{j:03d}", product_id=cereal.product_id[j], campaign_id=str(c + 1)))
    tgt_mask = np.zeros((len(camps), N), bool)
    for c, cp in enumerate(camps):
        tgt_mask[c, cp["targeted"]] = True

    # simulate week by week
    last_sup = np.full(N, -99.0)
    lam_sup_base = np.zeros((N, 54), np.float32)
    lines, trips_out, redemptions = [], [], []
    next_basket = 1
    fill_cat_idx = {c: np.where(filler.product_category == c)[0] for c in filler.product_category.unique()}
    fresh_cats = ["FRESH FRUIT", "FRESH MEAT", "DELI MEATS"]
    dry_cats = ["CANNED GOODS", "SNACKS", "HOUSEHOLD"]
    for wi, w in enumerate(WEEKS):
        r_w = np.random.default_rng([cfg.seed, w])
        season = 1 + 0.15 * np.sin(2 * np.pi * w / 52)
        sh = sh_after if w >= TRUTH["lapse_week"] else sh_before
        rate = (base_cat * active[:, wi] * season)[:, None] * sh * pm[None, :, wi]
        lam_sup_base[:, w] = rate[:, is_sup].sum(axis=1)
        hab = 1 + (TRUTH["habit_gamma"] - 1) * np.exp(-(w - last_sup) / TRUTH["habit_tau_weeks"])
        hab = np.where(last_sup > 0, hab, 1.0)
        if w == TRUTH["lapse_week"]:
            last_sup[lapsed] = -99.0          # lapsing households start afresh: no habit left to decay slowly
            hab[lapsed] = 1.0
        lam = rate.copy()
        lam[:, is_sup] *= hab[:, None]
        lam_nocamp = lam.copy()
        for c, cp in enumerate(camps):
            if cp["start"] <= w < cp["start"] + cp["weeks"]:
                cols = cp["coupon"][is_sup[cp["coupon"]]]
                rows = cp["targeted"]
                lam[np.ix_(rows, cols)] *= cp["lift"]
                inc = (lam - lam_nocamp)[np.ix_(rows, cols)]
                cp["exp_units"] += float(inc.sum())
                cp["exp_sales"] += float((inc * (cereal.list_price.to_numpy()[cols] * (1 - depth[cols, wi]))[None, :]).sum())
        U = r_w.random((N, P))
        units = poisson.ppf(U, lam).astype(int)
        hs, ps = np.nonzero(units)
        bought_sup = np.zeros(N, bool)
        bought_sup[hs[is_sup[ps]]] = True
        last_sup[bought_sup] = w
        # trips and filler lines
        nt = r_w.poisson(trips_rate * active[:, wi])
        T = int(nt.sum())
        trip_h = np.repeat(np.arange(N), nt)
        first_trip = np.concatenate([[0], np.cumsum(nt)[:-1]])
        # cereal lines are attached to one of the household's trips that week, or to a new trip
        has = nt[hs] > 0
        tr_idx = np.where(has, first_trip[hs] + np.floor(r_w.random(len(hs)) * np.maximum(nt[hs], 1)).astype(int), -1)
        need = np.unique(hs[~has])
        extra_h = need
        extra_map = {h: T + k for k, h in enumerate(need)}
        tr_idx = np.where(has, tr_idx, [extra_map.get(h, -1) for h in hs])
        all_trip_h = np.concatenate([trip_h, extra_h])
        T_all = len(all_trip_h)
        basket = next_basket + np.arange(T_all)
        next_basket += T_all
        day_off = r_w.random(T_all) * 6.99
        ts = WEEK2_START + pd.to_timedelta((w - 2) * 7 + day_off, unit="D")
        store = home[all_trip_h, r_w.integers(0, 2, T_all)]
        trips_out.append(pd.DataFrame({"basket_idx": basket, "h": all_trip_h, "store": store, "ts": ts, "week": w}))
        # cereal rows
        if len(hs):
            lp = cereal.list_price.to_numpy()[ps]
            dep = depth[ps, wi]
            shelf = units[hs, ps] * lp
            disc = shelf * dep
            cdisc = np.zeros(len(hs))
            for c, cp in enumerate(camps):
                if cp["start"] <= w < cp["start"] + cp["weeks"]:
                    sel = tgt_mask[c, hs] & np.isin(ps, cp["coupon"]) & is_sup[ps]
                    red = sel & (r_w.random(len(hs)) < 0.30)
                    cdisc = np.where(red, 0.5, cdisc)
                    for k in np.nonzero(red)[0]:
                        redemptions.append(dict(household_id=hid[hs[k]], coupon_upc=f"U{cp['id']}{ps[k]:03d}",
                                                campaign_id=cp["id"], redemption_date=ts[tr_idx[k]].date() if tr_idx[k] < len(ts) else None))
            lines.append(pd.DataFrame({"basket_idx": basket[tr_idx], "h": hs, "product_id": cereal.product_id.to_numpy()[ps],
                                       "quantity": units[hs, ps].astype(float), "shelf": shelf, "retail_disc": disc,
                                       "coupon_disc": cdisc, "week": w}))
        # filler lines
        nl = 1 + r_w.poisson(np.maximum(lines_h[trip_h] - 1, 0.1))
        th = np.repeat(np.arange(T), nl)
        hh = trip_h[th]
        fresh = r_w.random(len(th)) < sp["fresh"][hh]
        cat_pick = np.where(fresh, r_w.integers(0, 3, len(th)), 3 + r_w.integers(0, 3, len(th)))
        is_private = r_w.random(len(th)) < sp["pl"][hh]
        pid = np.empty(len(th), dtype=object)
        lp = np.empty(len(th))
        for ci, cat in enumerate(fresh_cats + dry_cats):
            sel = np.where(cat_pick == ci)[0]
            if not len(sel):
                continue
            idxs = fill_cat_idx[cat]
            pl_idx = [i for i in idxs if filler.brand.iloc[i] == "Private"]
            nat_idx = [i for i in idxs if filler.brand.iloc[i] != "Private"]
            pick = np.where(is_private[sel], np.array(pl_idx)[r_w.integers(0, len(pl_idx), len(sel))],
                            np.array(nat_idx)[r_w.integers(0, len(nat_idx), len(sel))])
            pid[sel] = filler.product_id.to_numpy()[pick]
            lp[sel] = filler.list_price.to_numpy()[pick]
        q = 1 + r_w.poisson(0.25, len(th))
        deal = r_w.random(len(th)) < sp["deal"][hh]
        shelf = q * lp
        disc = shelf * np.where(deal, r_w.uniform(0.15, 0.40, len(th)), 0.03)
        lines.append(pd.DataFrame({"basket_idx": basket[th], "h": hh, "product_id": pid, "quantity": q.astype(float),
                                   "shelf": shelf, "retail_disc": disc, "coupon_disc": 0.0, "week": w}))
    trips_df = pd.concat(trips_out, ignore_index=True)
    lines_df = pd.concat(lines, ignore_index=True).merge(trips_df[["basket_idx", "store", "ts"]], on="basket_idx", how="left")
    # a cereal line whose trip index pointed past the trips list (should not happen) would have NaN ts
    assert lines_df.ts.notna().all()
    tx = pd.DataFrame({
        "household_id": hid[lines_df.h.to_numpy()], "store_id": (lines_df.store + 300).astype(str),
        "basket_id": (30000000 + lines_df.basket_idx).astype(str), "product_id": lines_df.product_id,
        "quantity": lines_df.quantity, "sales_value": (lines_df.shelf - lines_df.retail_disc - lines_df.coupon_disc).round(2),
        "retail_disc": lines_df.retail_disc.round(2), "coupon_disc": lines_df.coupon_disc, "coupon_match_disc": 0.0,
        "week": lines_df.week.astype("int32"), "transaction_timestamp": lines_df.ts})
    tx = tx[tx.sales_value > 0].reset_index(drop=True)
    stores = [str(300 + s) for s in range(S)]
    prom = {}
    for (i, wi), (ds, ms) in store_sets.items():
        for s_ in ds:
            prom.setdefault((cereal.product_id[i], stores[s_], WEEKS[wi]), ["0", "0"])[0] = "3"
        for s_ in ms:
            prom.setdefault((cereal.product_id[i], stores[s_], WEEKS[wi]), ["0", "0"])[1] = "A"
    promotions = pd.DataFrame([dict(product_id=k[0], store_id=k[1], display_location=v[0], mailer_location=v[1], week=k[2])
                               for k, v in prom.items()])
    promotions["week"] = promotions.week.astype("int32")
    products = pd.concat([cereal.drop(columns=["list_price", "pop"]), filler.drop(columns=["list_price", "pop"])], ignore_index=True)
    if cfg.delist_ids:
        pass  # delisted products simply never sell (their shares were zeroed) and are never featured
    demo_h = rng.random(N) < 0.35
    inc = rng.choice(["Under 15K", "15-24K", "25-34K", "35-49K", "50-74K", "75-99K", "100-124K", "125-149K"], N)
    demographics = pd.DataFrame({"household_id": hid[demo_h], "age": rng.choice(["19-24", "25-34", "35-44", "45-54", "55-64", "65+"], demo_h.sum()),
                                 "income": inc[demo_h], "home_ownership": "Homeowner", "marital_status": "Married",
                                 "household_size": "2", "household_comp": "2 Adults No Kids", "kids_count": "0"})
    def d_(w_):
        return (WEEK2_START + pd.Timedelta(days=(w_ - 2) * 7)).date()
    camp_desc = pd.DataFrame([dict(campaign_id=c["id"], campaign_type=c["type"], start_date=d_(c["start"]),
                                   end_date=(WEEK2_START + pd.Timedelta(days=(c["start"] + c["weeks"] - 2) * 7 - 1)).date()) for c in camps])
    campaigns = pd.DataFrame([dict(campaign_id=c["id"], household_id=hid[h]) for c in camps for h in c["targeted"]])
    coupons = pd.DataFrame(coupon_rows)
    redemptions_df = pd.DataFrame(redemptions) if redemptions else pd.DataFrame(columns=["household_id", "coupon_upc", "campaign_id", "redemption_date"])
    raw = {"transactions": tx, "promotions": promotions, "products": products, "demographics": demographics,
           "campaigns": campaigns, "campaign_descriptions": camp_desc, "coupons": coupons,
           "coupon_redemptions": redemptions_df}
    key = {
        "seed": cfg.seed, "config": asdict(cfg), "truth": TRUTH, "supplier": SUPPLIER, "category": CATEGORY,
        "segment_of_household": {hid[i]: int(seg[i]) for i in range(N)}, "segment_names": SEG_NAMES,
        "lapsed_households": [hid[i] for i in lapsed], "established_households": [hid[i] for i in established],
        "campaigns": [dict(campaign_id=c["id"], type=c["type"], start_week=c["start"], weeks=c["weeks"], true_lift=c["lift"],
                           n_targeted=int(len(c["targeted"])), expected_incremental_units=c["exp_units"],
                           expected_incremental_sales=c["exp_sales"],
                           targeted_ids=[hid[h] for h in c["targeted"]]) for c in camps],
        "delist_ids": list(cfg.delist_ids),
    }
    arrays = {"lam_sup_base": lam_sup_base, "household_ids": hid}
    return raw, key, arrays


def write(raw, key, arrays, out: Path) -> dict:
    (out / "parquet").mkdir(parents=True, exist_ok=True)
    for k, df in raw.items():
        df.to_parquet(out / "parquet" / f"{k}.parquet", index=False)
    kp = out / "answer_key.json"
    kp.write_text(json.dumps(key, default=float))
    np.savez_compressed(out / "key_arrays.npz", **arrays)
    manifest = {"answer_key_sha256": hashlib.sha256(kp.read_bytes()).hexdigest(),
                "rows": {k: int(len(v)) for k, v in raw.items()}, "seed": key["seed"]}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


if __name__ == "__main__":
    import sys
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    out = Path(sys.argv[2] if len(sys.argv) > 2 else f"data/twin_seed{seed}")
    raw, key, arrays = generate(TwinConfig(seed=seed))
    print(write(raw, key, arrays, out))
