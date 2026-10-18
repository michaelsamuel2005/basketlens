"""Shared run context: connection, supplier, category, seed."""
from __future__ import annotations

from dataclasses import dataclass

import duckdb

from .sqlrun import query


def esc(s: str) -> str:
    return str(s).replace("'", "''")


@dataclass
class Ctx:
    con: duckdb.DuckDBPyConnection
    mfr: str
    cat: str
    seed: int = 1729

    def q(self, name: str, **kw):
        return query(self.con, name, mfr=esc(self.mfr), cat=esc(self.cat), **kw)

    def sql(self, text: str):
        return self.con.execute(text).df()


def default_category(con, mfr: str) -> str:
    return con.execute(
        "SELECT category FROM sale WHERE manufacturer_id = ? GROUP BY category ORDER BY SUM(net_sales) DESC LIMIT 1",
        [mfr]).fetchone()[0]
