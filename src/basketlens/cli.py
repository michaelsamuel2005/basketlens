"""basketlens command line.

    basketlens fetch                       download the Complete Journey files (CC0)
    basketlens load                        build the DuckDB warehouse
    basketlens run --manufacturer 794      run every analysis for one supplier (category defaults to its largest)
    basketlens deck --manufacturer 794     write the supplier deck (12 slides) from the results
    basketlens tableau --manufacturer 794  write the Tableau Public extracts
    basketlens twin --seed 7               generate the simulated twin and score the analyses against its answer key
"""
from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

from . import fetch as fetch_mod


def _ctx(a):
    from .ctx import Ctx, default_category
    con = duckdb.connect(a.db, read_only=True)
    cat = a.category or default_category(con, a.manufacturer)
    return Ctx(con, a.manufacturer, cat)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="basketlens")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("fetch", "load"):
        s = sub.add_parser(name); s.add_argument("--raw", default="data/raw"); s.add_argument("--db", default="data/warehouse.duckdb")
    for name in ("run", "deck", "tableau"):
        s = sub.add_parser(name)
        s.add_argument("--manufacturer", default="794"); s.add_argument("--category", default=None)
        s.add_argument("--db", default="data/warehouse.duckdb"); s.add_argument("--out", default=None)
        s.add_argument("--draws", type=int, default=300)
    s = sub.add_parser("twin"); s.add_argument("--seed", type=int, default=7); s.add_argument("--draws", type=int, default=300)
    a = ap.parse_args(argv)
    if a.cmd == "fetch":
        fetch_mod.fetch(Path(a.raw))
    elif a.cmd == "load":
        from .load import build
        fetch_mod.fetch(Path(a.raw)); build(Path(a.raw), Path(a.db))
    elif a.cmd == "twin":
        from . import scorecard
        r = scorecard.run(a.seed, Path(f"outputs/twin_seed{a.seed}"), a.draws)
        print(f"{r['summary']['passed']} of {r['summary']['total']} checks pass; see outputs/twin_seed{a.seed}/scorecard.md")
    else:
        ctx = _ctx(a)
        out = Path(a.out or f"outputs/real_{ctx.mfr}_{ctx.cat.lower().replace(' ', '_').replace('/', '_')}")
        if a.cmd == "run":
            from . import report
            report.run_all(ctx, out, a.draws); print("written", out)
        elif a.cmd == "deck":
            from . import deck
            print(deck.build(out, ctx))
        else:
            from . import tableau
            print(tableau.build(out, ctx))


if __name__ == "__main__":
    main()
