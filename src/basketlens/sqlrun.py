"""Tiny SQL runner: reads sql/*.sql, replaces {{name}} parameters, splits on `-- ;;` statement markers."""
from __future__ import annotations

import re
from importlib import resources
from pathlib import Path


def sql_text(name: str) -> str:
    return (Path(__file__).parent / "sql" / name).read_text()


def render(sql: str, **params) -> str:
    def sub(m):
        k = m.group(1)
        if k not in params:
            raise KeyError(f"SQL parameter {{{{{k}}}}} not supplied")
        return str(params[k])
    return re.sub(r"\{\{(\w+)\}\}", sub, sql)


def statements(sql: str) -> list[str]:
    return [s.strip() for s in re.split(r"^\s*-- ;;\s*$", sql, flags=re.M) if s.strip()]


def run_file(con, name: str, **params) -> None:
    for s in statements(render(sql_text(name), **params)):
        con.execute(s)


def query(con, name: str, **params):
    """Run a file containing one SELECT and return a DataFrame."""
    return con.execute(render(sql_text(name), **params)).df()
