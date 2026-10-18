"""Score the analyses against the simulated twin's sealed answer key.

    python -m basketlens.scorecard --seed 7 --out outputs/twin_seed7

The analysis code never opens answer_key.json; this module does, after the analysis has run. A check passes when the
estimate meets the stated standard against what was planted. Failures are printed, never hidden.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.metrics import adjusted_rand_score

from . import report, twin
from .ctx import Ctx
from .load import build_from_parquet


def _ci_has(ci_low: float, ci_high: float, truth: float) -> bool:
    return ci_low <= truth <= ci_high


def run(seed: int = 7, out: Path | None = None, draws: int = 300, work: Path = Path("data")) -> dict:
    tdir = work / f"twin_seed{seed}"
    raw, key, arrays = twin.generate(twin.TwinConfig(seed=seed))
    manifest = twin.write(raw, key, arrays, tdir)
    con = build_from_parquet(tdir / "parquet", work / f"twin{seed}.duckdb")
    ctx = Ctx(con, twin.SUPPLIER, twin.CATEGORY, seed=1729)
    res = report.run_all(ctx, out, draws=draws)
    # ---- the answer key is opened only now ----
    key = json.loads((tdir / "answer_key.json").read_text())
    arr = np.load(tdir / "key_arrays.npz", allow_pickle=True)
    T = key["truth"]
    checks: list[dict] = []

    def add(group, name, planted, found, ok, standard):
        checks.append({"group": group, "check": name, "planted": planted, "found": found, "pass": bool(ok), "standard": standard})

    # --- warehouse and SQL against an independent pandas recomputation
    tx = raw["transactions"]
    n_line = con.execute("SELECT COUNT(*) FROM fact_line").fetchone()[0]
    add("SQL", "fact_line keeps every raw line", len(tx), n_line, n_line == len(tx), "equal")
    sale_sum = con.execute("SELECT SUM(net_sales) FROM sale").fetchone()[0]
    pd_sum = tx[(tx.sales_value > 0) & tx.quantity.between(1, 99)].sales_value.sum()
    add("SQL", "sale table net sales match pandas", round(pd_sum, 2), round(sale_sum, 2), abs(sale_sum - pd_sum) < 1e-6 * pd_sum, "within 1e-6")
    prods = raw["products"].set_index("product_id")
    cer = tx[tx.product_id.map(prods.product_category) == twin.CATEGORY].copy()
    cer["q"] = 1 + np.minimum(3, np.floor((cer.week - 2) / 13)).astype(int)
    sp = res["shopper"]["periods"]
    qb = sp[(sp.grain == "quarter") & (sp.entity == "category")].set_index("period").buyers
    pb = cer.groupby("q").household_id.nunique()
    add("SQL", "category buyers by quarter match pandas", pb.tolist(), qb.tolist(), (qb.to_numpy() == pb.to_numpy()).all(), "equal")
    ent = sp[(sp.grain == "half") & (sp.entity != "category")].groupby("period").net_sales.sum()
    cat = sp[(sp.grain == "half") & (sp.entity == "category")].set_index("period").net_sales
    add("SQL", "supplier + private label + other brands = category", cat.round(2).tolist(), ent.round(2).tolist(),
        np.allclose(ent.to_numpy(), cat.to_numpy()), "equal")
    dec = res["shopper"]["decomposition"]
    add("Decomposition", "buyers x frequency x spend per trip adds exactly to the change", 0.0, float(dec.check.abs().max()),
        dec.check.abs().max() < 1e-6, "|residual| < 1e-6")

    # --- promotions: planted effects inside the 95% interval
    pc, pcat = res["promotions"]["coefs_supplier"].set_index("term"), res["promotions"]["coefs_category"].set_index("term")
    pct = lambda x: 100 * (math.exp(x) - 1)
    planted = {"disp": T["display_uplift_pct_at_full"], "mail": T["mailer_uplift_pct_at_full"],
               "after1": pct(T["after_feature_week1_effect"]), "after2": pct(T["after_feature_weeks2_3_effect"]),
               "sib": pct(T["sibling_feature_effect"]), "comp": pct(T["competitor_feature_effect"])}
    label = {"disp": "display uplift (%)", "mail": "mailer uplift (%)", "after1": "week after a feature (%)",
             "after2": "weeks 2-3 after a feature (%)", "sib": "cannibalisation by own products (%)", "comp": "competitor features (%)"}
    for t, v in planted.items():
        r = pc.loc[t]
        add("Promotions", f"supplier model: {label[t]}", round(v, 1), f"{r.pct_effect:.1f} [{r.ci_low:.1f}, {r.ci_high:.1f}]",
            _ci_has(r.ci_low, r.ci_high, v), "planted value inside 95% interval")
    for t in ("disp", "mail"):
        r = pcat.loc[t]
        add("Promotions", f"category model: {label[t]}", round(planted[t], 1), f"{r.pct_effect:.1f} [{r.ci_low:.1f}, {r.ci_high:.1f}]",
            _ci_has(r.ci_low, r.ci_high, planted[t]), "planted value inside 95% interval")

    # --- journeys
    j = res["journeys"]
    hh = j["households"]
    est = hh[hh.supplier_trips_h1 >= 4]
    lapsed = set(est[(est.supplier_trips_q4 == 0) & (est.cat_trips_q4 > 0)].household_id)
    truth_l = set(key["lapsed_households"])
    detectable = truth_l & set(est.household_id)          # planted lapsers who bought often enough in H1 to be seen
    tp = len(lapsed & truth_l)
    prec, rec = tp / max(1, len(lapsed)), len(lapsed & detectable) / max(1, len(detectable))
    add("Journeys", "lapsed buyers found: precision", f"{len(truth_l)} planted lapsers", f"{prec:.2f}", prec >= 0.6, ">= 0.60")
    add("Journeys", "lapsed buyers found: recall among planted lapsers with 4+ trips in H1", f"{len(detectable)} detectable", f"{rec:.2f}", rec >= 0.6, ">= 0.60")
    f = j["flows"]
    sal = pd.read_parquet(tdir / "parquet" / "transactions.parquet")
    sal = sal.assign(cat=sal.product_id.map(prods.product_category), mf=sal.product_id.map(prods.manufacturer_id))
    q4 = sal[(sal.cat == twin.CATEGORY) & (sal.week >= 41) & sal.household_id.isin(truth_l) & (sal.mf != twin.SUPPLIER)]
    pl_true = q4[q4.mf == twin.PLM].sales_value.sum() / max(1e-9, q4.sales_value.sum())
    add("Journeys", "where lapsed buyers went: private-label share of what they bought instead", f"{pl_true:.2f}",
        f"{f['pl_share_of_rest_q4']:.2f}", abs(pl_true - f["pl_share_of_rest_q4"]) < 0.06, "within 0.06")
    g, tau = T["habit_gamma"], T["habit_tau_weeks"]
    lam = arr["lam_sup_base"]
    hid_idx = {h: i for i, h in enumerate(arr["household_ids"])}
    end = pd.Timestamp(hh.data_end.iloc[0])
    tri = hh[(hh.first_week >= 15) & hh.supplier_trips.gt(0)].copy()
    tri["first_day"] = pd.to_datetime(tri.first_day)
    tri = tri[tri.first_day <= end - pd.Timedelta(days=84)]
    pr = []
    for r in tri.itertuples():
        i, f0 = hid_idx[r.household_id], int(r.first_week)
        hz = 0.5 * lam[i, f0] + sum(lam[i, f0 + a] * (1 + (g - 1) * math.exp(-a / tau)) for a in range(1, 13) if f0 + a <= 53)
        pr.append(1 - math.exp(-hz))
    oracle = float(np.mean(pr))
    lo, hi = j["trial"]["repeat_ci"]
    add("Journeys", "12-week repeat rate of new buyers", f"{oracle:.3f} (expected from planted rates)",
        f"{j['trial']['repeat_rate']:.3f} [{lo:.3f}, {hi:.3f}]", _ci_has(lo, hi, oracle), "expected rate inside 95% interval")

    # --- segments
    sg = res["segments"]
    h = sg["households"].copy()
    h["true_seg"] = h.household_id.map(key["segment_of_household"])
    ari = adjusted_rand_score(h.true_seg, h.segment)
    add("Segments", "adjusted Rand index against the four planted classes", ">= 0.5", f"{ari:.2f}", ari >= 0.5, ">= 0.50")
    drift = h[h.true_seg == 3]
    purity = (drift.segment == drift.segment.value_counts().index[0]).mean()
    add("Segments", "planted 'stops shopping' class lands in one segment", "share of class in modal segment", f"{purity:.2f}", purity >= 0.7, ">= 0.70")
    add("Segments", "segment stability (mean ARI across 80% subsamples)", ">= 0.7", f"{sg['stability_ari']:.2f}", sg["stability_ari"] >= 0.7, ">= 0.70")
    segs = sg["segments"].set_index("segment")
    own = h[h.true_seg == 1].segment.value_counts().index[0]
    others = segs.drop(index=own).supplier_share_of_segment_category
    add("Segments", "segment holding the own-label class has the lowest supplier share", f"{segs.loc[own].supplier_share_of_segment_category:.2f}",
        f"others {others.min():.2f}-{others.max():.2f}", segs.loc[own].supplier_share_of_segment_category < others.min(), "lowest of all segments")

    # --- campaigns
    cs = res["campaigns"]
    cb = cs["estimates"][("supplier_all", "main")]["by_campaign"].copy()
    cb["campaign_id"] = cb.campaign_id.astype(str)
    kc = pd.DataFrame(key["campaigns"]).set_index("campaign_id")
    cb = cb.join(kc[["true_lift", "expected_incremental_sales"]], on="campaign_id")
    cov = [(_ci_has(r.total_low, r.total_high, r.expected_incremental_sales)) for r in cb.itertuples()]
    tr_sum = float(kc.expected_incremental_sales.sum())
    sm = cs["summary"]
    add("Campaigns", "pooled incremental sales: planted total inside 95% interval", round(tr_sum, 0),
        f"{sm['incremental_sales']:.0f} [{sm['incremental_low']:.0f}, {sm['incremental_high']:.0f}]",
        _ci_has(sm["incremental_low"], sm["incremental_high"], tr_sum), "inside 95% interval")
    add("Campaigns", "a plain targeted-vs-untargeted comparison overstates the effect", round(tr_sum, 0), round(sm["naive_incremental"], 0),
        sm["naive_incremental"] > 3 * tr_sum, "naive > 3 x planted")
    add("Campaigns", "campaigns whose interval covers the planted effect", f"{len(cov)} of {len(cov)}", f"{sum(cov)} of {len(cov)}",
        sum(cov) >= len(cov) - 1, "all but at most one")
    miss = [r.campaign_id for r, c in zip(cb.itertuples(), cov) if not c]
    po = cs["campaigns"].set_index(cs["campaigns"].campaign_id.astype(str)).pre_overlap
    add("Campaigns", "every campaign that misses was flagged as overlapping another in its pre window", "misses flagged",
        f"misses {miss or 'none'}; flagged {[m for m in miss if po[m] > 0]}", all(po[m] > 0 for m in miss), "no unflagged miss")
    dud = cb[cb.true_lift == 1.0]
    clean_dud = dud[[po[c] == 0 for c in dud.campaign_id]]
    add("Campaigns", "a campaign with no planted effect and a clean pre window is not credited with one", "interval includes 0",
        "none to test" if clean_dud.empty else f"{len(clean_dud)} tested", clean_dud.empty or all(r.total_low <= 0 <= r.total_high for r in clean_dud.itertuples()),
        "interval includes 0")

    # --- ranging: delist the tail the analysis picked, on a twin where those products never existed (same seed)
    rg = res["ranging"]
    tail_ids = list(rg["tail"].product_id)
    rawB, keyB, arrB = twin.generate(twin.TwinConfig(seed=seed, delist_ids=tuple(tail_ids)))
    def sup_sales(r):
        t = r["transactions"]
        pm = r["products"].set_index("product_id")
        m = (t.product_id.map(pm.product_category) == twin.CATEGORY) & (t.product_id.map(pm.manufacturer_id) == twin.SUPPLIER) & (t.week >= 2)
        return float(t[m].sales_value.sum())
    sA, sB = sup_sales(raw), sup_sales(rawB)
    real_loss = sA - sB
    scn = rg["scenarios"].set_index("scenario")
    c_loss = float(scn.loc["central", "net_loss_to_supplier"])
    lo_l, hi_l = float(scn.loc["full transfer", "net_loss_to_supplier"]), float(scn.loc["low transfer", "net_loss_to_supplier"])
    add("Ranging", "delist the tail: realised loss inside the low-to-high transfer range", f"{real_loss:.0f}", f"{lo_l:.0f} to {hi_l:.0f}",
        lo_l <= real_loss <= hi_l, "inside range")
    add("Ranging", "delist the tail: central estimate (planted transfer rates) close to the realised loss", f"{real_loss:.0f}", f"{c_loss:.0f}",
        abs(c_loss - real_loss) <= 0.25 * real_loss, "within 25%")

    df = pd.DataFrame(checks)
    summary = {"seed": seed, "passed": int(df["pass"].sum()), "total": int(len(df)), "answer_key_sha256": manifest["answer_key_sha256"],
               "households": int(raw["demographics"].shape[0] and len(key["segment_of_household"])), "lines": int(len(tx))}
    if out:
        out.mkdir(parents=True, exist_ok=True)
        df.to_csv(out / "scorecard.csv", index=False)
        (out / "scorecard.md").write_text(to_markdown(df, summary))
        (out / "scorecard.json").write_text(json.dumps({"summary": summary, "checks": checks}, default=str, indent=1))
    return {"checks": df, "summary": summary, "results": res}


def to_markdown(df: pd.DataFrame, s: dict) -> str:
    lines = [f"# Scorecard: twin seed {s['seed']}", "",
             f"**{s['passed']} of {s['total']} checks pass.** Answer key sha256 `{s['answer_key_sha256'][:16]}...` "
             f"({s['lines']:,} simulated lines, {s['households']:,} households).", "",
             "| group | check | planted | found | standard | result |", "|---|---|---|---|---|---|"]
    for _, r in df.iterrows():
        lines.append(f"| {r['group']} | {r['check']} | {r['planted']} | {r['found']} | {r['standard']} | {'PASS' if r['pass'] else 'FAIL'} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=None)
    ap.add_argument("--draws", type=int, default=300)
    a = ap.parse_args()
    r = run(a.seed, Path(a.out or f"outputs/twin_seed{a.seed}"), a.draws)
    d = r["checks"]
    print(d[["group", "check", "planted", "found", "pass"]].to_string())
    print(f"{r['summary']['passed']} of {r['summary']['total']} pass")
