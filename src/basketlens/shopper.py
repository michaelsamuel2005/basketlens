"""Shopper decomposition and customer journeys (trial, repeat, lapse, switching) for one supplier in one category."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .ctx import Ctx


def logmean(a: float, b: float) -> float:
    return a if abs(a - b) < 1e-12 else (a - b) / (math.log(a) - math.log(b))


def lmdi(row0: pd.Series, row1: pd.Series) -> dict:
    """sales = buyers x trips per buyer x sales per trip. Log-mean Divisia: contributions add exactly to the change."""
    f = lambda r: (r.buyers, r.trips / r.buyers, r.net_sales / r.trips)
    (b0, f0, v0), (b1, f1, v1) = f(row0), f(row1)
    L = logmean(row1.net_sales, row0.net_sales)
    out = {"buyers": L * math.log(b1 / b0), "frequency": L * math.log(f1 / f0), "spend_per_trip": L * math.log(v1 / v0)}
    out["change"] = row1.net_sales - row0.net_sales
    out["check"] = out["buyers"] + out["frequency"] + out["spend_per_trip"] - out["change"]
    return out


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def decomposition(ctx: Ctx) -> dict:
    d = ctx.q("10_shopper.sql")
    d["penetration"] = d.buyers / d.households
    d["trips_per_buyer"] = d.trips / d.buyers
    d["sales_per_trip"] = d.net_sales / d.trips
    cat = d[d.entity == "category"].set_index(["grain", "period"]).net_sales
    d["share"] = [r.net_sales / cat[(r.grain, r.period)] for r in d.itertuples()]
    d["discount_share"] = d.sales_on_discount / d.net_sales
    rows = []
    for ent in ("supplier", "private label", "other brands", "category"):
        e = d[(d.entity == ent) & (d.grain == "half")].set_index("period")
        r = lmdi(e.loc[1], e.loc[2])
        rows.append({"entity": ent, "sales_h1": e.loc[1].net_sales, "sales_h2": e.loc[2].net_sales, **r})
    dec = pd.DataFrame(rows)
    return {"periods": d, "decomposition": dec}


def km_second_purchase(first: pd.Series, second: pd.Series, end: pd.Timestamp, horizon_days: int = 84) -> pd.DataFrame:
    """Kaplan-Meier on a 7-day grid: share of triers who have NOT yet bought the supplier a second time."""
    t = (second.fillna(end) - first).dt.days.to_numpy()
    event = second.notna().to_numpy()
    cens = (end - first).dt.days.to_numpy()
    t = np.where(event, t, cens)
    surv, rows = 1.0, []
    for lo in range(0, horizon_days, 7):
        hi = lo + 7
        at_risk = int((t > lo).sum())
        ev = int(((t > lo) & (t <= hi) & event).sum())
        surv *= 1 - (ev / at_risk if at_risk else 0)
        rows.append({"days": hi, "at_risk": at_risk, "events": ev, "repeat_by_now": 1 - surv})
    return pd.DataFrame(rows)


def journeys(ctx: Ctx) -> dict:
    j = ctx.q("20_journeys.sql")
    j["first_day"] = pd.to_datetime(j.first_day)
    j["second_day"] = pd.to_datetime(j.second_day)
    end = pd.to_datetime(j.data_end.iloc[0])
    n_cat = len(j)
    buyers = j[j.supplier_trips > 0]
    funnel = pd.DataFrame({
        "stage": ["category buyers", "bought the supplier", "2 or more trips", "4 or more trips", "8 or more trips"],
        "households": [n_cat, len(buyers), int((j.supplier_trips >= 2).sum()), int((j.supplier_trips >= 4).sum()),
                       int((j.supplier_trips >= 8).sum())]})
    funnel["share_of_previous"] = funnel.households / funnel.households.shift(1)
    # trial: first supplier purchase in week 15 or later = no supplier purchase in the 13 weeks before (weeks 2-14)
    trial = buyers[buyers.first_week >= 15].copy()
    full = trial[trial.first_day <= end - pd.Timedelta(days=84)]          # 12 weeks of follow-up observed
    full_repeat = (full.second_day - full.first_day).dt.days.le(84) & full.second_day.notna()
    rep = {"triers": len(trial), "with_12w_followup": len(full), "repeated_12w": int(full_repeat.sum())}
    rep["repeat_rate"] = rep["repeated_12w"] / max(1, rep["with_12w_followup"])
    rep["repeat_ci"] = wilson(rep["repeated_12w"], rep["with_12w_followup"])
    by_disc = {}
    for flag, name in ((1, "first purchase on discount"), (0, "first purchase at full price")):
        sub = full[full.first_on_discount == flag]
        r = ((sub.second_day - sub.first_day).dt.days.le(84) & sub.second_day.notna())
        by_disc[name] = {"n": len(sub), "repeat_rate": float(r.mean()) if len(sub) else float("nan"),
                         "ci": wilson(int(r.sum()), len(sub))}
    km = km_second_purchase(trial.first_day, trial.second_day, end)
    # lapse: >= 4 supplier trips in weeks 2-27 (so a 13-week silence is unlikely by chance), none in weeks 41-53, and still
    # buying the category in weeks 41-53. Chance silences are estimated from each buyer's own H1 rate and reported.
    est = j[j.supplier_trips_h1 >= 4]
    lapsed = est[(est.supplier_trips_q4 == 0) & (est.cat_trips_q4 > 0)]
    gone = est[(est.supplier_trips_q4 == 0) & (est.cat_trips_q4 == 0)]
    kept = est[est.supplier_trips_q4 > 0]
    chance = float(np.exp(-13 * est.supplier_trips_h1 / 26.0).sum())      # expected silences if buying were steady
    life = {"established": len(est), "kept": len(kept), "lapsed_to_others": len(lapsed), "left_category": len(gone),
            "lapse_rate": len(lapsed) / max(1, len(est)), "lapse_ci": wilson(len(lapsed), len(est)),
            "chance_silences_expected": chance, "excess_lapsed": max(0.0, len(lapsed) + len(gone) - chance)}
    # where the lapsed households' category money went. Households are selected on a zero supplier spend in Q4, so
    # dollar changes are descriptive; the mix of what they bought instead is compared with their own H1 mix without the
    # supplier, and with all households.
    fl = ctx.q("21_flows.sql", w1_from=2, w1_to=27, w2_from=41, w2_to=53)
    allsum = fl.groupby("win")[["supplier", "private_label", "other_brands"]].sum()
    fl = fl[fl.household_id.isin(lapsed.household_id)]
    pv = fl.groupby("win")[["supplier", "private_label", "other_brands"]].sum()
    wk = pd.DataFrame({"H1": pv.loc[1] / 26, "Q4": pv.loc[2] / 13})
    wk["change_per_week"] = wk.Q4 - wk.H1
    switching = wk.reset_index().rename(columns={"index": "entity"})
    pl_share = lambda s: s["private_label"] / (s["private_label"] + s["other_brands"])
    flows = {"supplier_per_week_h1": float(wk.loc["supplier", "H1"]),
             "category_per_week_h1": float(wk["H1"].sum()), "category_per_week_q4": float(wk["Q4"].sum()),
             "pl_share_of_rest_q4": float(pl_share(pv.loc[2])), "pl_share_of_rest_h1": float(pl_share(pv.loc[1])),
             "pl_share_of_rest_all_households_q4": float(pl_share(allsum.loc[2])),
             "annualised_value_of_lapsed": float(wk.loc["supplier", "H1"] * 52)}
    return {"funnel": funnel, "trial": rep, "repeat_by_deal": by_disc, "km": km, "lifecycle": life,
            "switching": switching, "flows": flows, "households": j}
