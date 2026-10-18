import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from basketlens import campaigns, ranging, shopper, twin
from basketlens.ctx import Ctx
from basketlens.load import build_from_parquet
from basketlens.recommend import _d
from basketlens.sqlrun import render, statements


@pytest.fixture(scope="module")
def small(tmp_path_factory):
    d = tmp_path_factory.mktemp("twin")
    raw, key, arr = twin.generate(twin.TwinConfig(seed=3, n_households=400, n_stores=10))
    twin.write(raw, key, arr, d)
    # the analysis sees only the parquet files: copy them to a folder with no answer key
    only = d / "only"
    only.mkdir()
    for f in (d / "parquet").glob("*.parquet"):
        (only / f.name).write_bytes(f.read_bytes())
    con = build_from_parquet(only, d / "w.duckdb")
    return raw, key, d, Ctx(con, twin.SUPPLIER, twin.CATEGORY)


def test_twin_is_deterministic_and_key_is_hashed(small, tmp_path):
    raw, key, d, _ = small
    raw2, key2, arr2 = twin.generate(twin.TwinConfig(seed=3, n_households=400, n_stores=10))
    assert json.dumps(key, default=float) == json.dumps(key2, default=float)
    m = twin.write(raw2, key2, arr2, tmp_path)
    assert len(m["answer_key_sha256"]) == 64
    assert key["truth"]["display_uplift_pct_at_full"] == 120.0


def test_sql_templating_requires_every_parameter():
    assert render("a {{x}} b", x=1) == "a 1 b"
    with pytest.raises(KeyError):
        render("a {{x}} {{y}}", x=1)
    assert len(statements("select 1;\n-- ;;\nselect 2;")) == 2


def test_warehouse_matches_pandas(small):
    raw, _, _, ctx = small
    tx = raw["transactions"]
    want = tx[(tx.sales_value > 0) & tx.quantity.between(1, 99)].sales_value.sum()
    got = ctx.con.execute("SELECT SUM(net_sales) FROM sale").fetchone()[0]
    assert abs(want - got) < 1e-6 * want
    assert ctx.con.execute("SELECT COUNT(*) FROM fact_line").fetchone()[0] == len(tx)


def test_analysis_runs_without_the_answer_key(small):
    _, _, d, ctx = small
    assert not (d / "only" / "answer_key.json").exists()
    dec = shopper.decomposition(ctx)["decomposition"]
    assert dec.check.abs().max() < 1e-6                       # buyers x frequency x spend adds exactly
    j = shopper.journeys(ctx)
    assert j["funnel"].households.is_monotonic_decreasing


def test_lmdi_identity_on_random_inputs():
    rng = np.random.default_rng(1)
    for _ in range(50):
        a = pd.Series(dict(buyers=rng.integers(50, 500), trips=rng.integers(500, 5000), net_sales=rng.uniform(1e3, 1e5)))
        b = pd.Series(dict(buyers=rng.integers(50, 500), trips=rng.integers(500, 5000), net_sales=rng.uniform(1e3, 1e5)))
        assert abs(shopper.lmdi(a, b)["check"]) < 1e-6


def test_wilson_interval_contains_estimate():
    lo, hi = shopper.wilson(40, 100)
    assert lo < 0.4 < hi and 0 < lo and hi < 1


def test_delist_arithmetic_by_hand():
    # one household buys X (spend 10) and another product Y of the same type from the supplier (spend 30): repertoire buyer.
    rep = pd.DataFrame({"household_id": ["h", "h", "k"], "product_id": ["X", "Y", "X"], "ptype": ["T"] * 3,
                        "manufacturer_id": ["S", "S", "S"], "is_private": [False] * 3, "spend": [10.0, 30.0, 5.0]})
    sku = pd.DataFrame({"product_id": ["X", "Y", "Z"], "ptype": ["T"] * 3, "net_sales": [15.0, 30.0, 70.0],
                        "is_supplier": [True, True, False]})
    r = ranging.delist_impact(rep, sku, {"X"}, tau_rep=0.8, tau_excl=0.4, supplier="S")
    # h: 10 * 0.8 * 1.0 (all alternatives are the supplier's) = 8 kept. k exclusive: 5 * 0.4 * (30/100 supplier share of others) = 0.6
    assert r["delisted_sales"] == 15.0
    assert abs(r["kept_by_supplier"] - 8.6) < 1e-9
    assert abs(r["lost_to_category"] - (2.0 + 3.0)) < 1e-9


def test_matched_did_removes_selection_but_naive_does_not():
    rng = np.random.default_rng(0)
    rows = []
    for cid in ("1", "2"):
        n = 4000
        level = rng.gamma(2, 1, n)                              # persistent household level
        tgt = rng.random(n) < 1 / (1 + np.exp(-(level - 2)))    # high spenders are targeted
        f = lambda: rng.poisson(level)
        pre, post, prepre, early = f(), f(), f(), f()           # no true effect
        rows.append(pd.DataFrame({"campaign_id": cid, "campaign_type": "Type A", "household_id": [f"{cid}-{i}" for i in range(n)],
                                  "targeted": tgt, "pre_total": pre, "post_total": post, "prepre_total": prepre, "early_total": early,
                                  "pre_sup": pre, "post_sup": post, "prepre_sup": prepre, "early_sup": early,
                                  "pre_cpn": pre, "post_cpn": post, "prepre_cpn": prepre, "has_prepre": True, "early_weeks": 8}))
    df = pd.concat(rows)
    est = campaigns.estimate(df, None, "supplier_all")
    assert (est.naive_per_household > 1.0).all()                # the plain comparison sees a big 'effect'
    assert (est.effect_per_household.abs() < 0.25).all()        # the matched design does not


def test_money_format_handles_negative():
    assert _d(-58.2) == "-$58" and _d(1234.5) == "$1,234"


@pytest.mark.slow
def test_full_scorecard_mostly_passes(tmp_path):
    from basketlens import scorecard
    r = scorecard.run(7, tmp_path / "out", draws=150, work=tmp_path)
    assert r["summary"]["passed"] >= r["summary"]["total"] - 6
