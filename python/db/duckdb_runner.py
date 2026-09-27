"""In-process SQL runner backed by DuckDB.

DuckDB speaks a PostgreSQL-compatible SQL dialect and needs no server, so it
lets the project *execute and verify* the analytical views in `sql/views.sql`
directly against the processed CSVs - useful for local validation, CI, and the
Python-vs-SQL reconciliation report, without requiring a PostgreSQL install.

The production target is still PostgreSQL (see sql/*.sql and db/load_postgres.py);
this runner deliberately reuses the *same* view SQL so the two stay in lock-step.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from ..common.config import PROCESSED_DIR, PROJECT_ROOT
from ..common.logging_utils import get_logger

logger = get_logger("db.duckdb_runner")

VIEWS_SQL = PROJECT_ROOT / "sql" / "views.sql"

REQUIRED_CSVS = ["dim_source.csv", "dim_series.csv", "dim_date.csv", "fact_observations.csv"]


def _strip_unsupported(sql: str) -> str:
    """Drop full-line SQL comments and Postgres-only SET search_path lines so the
    remaining text splits cleanly into executable CREATE VIEW statements."""
    kept = []
    for ln in sql.splitlines():
        stripped = ln.strip()
        if stripped.startswith("--") or not stripped:
            continue
        if stripped.upper().startswith("SET SEARCH_PATH"):
            continue
        kept.append(ln)
    return "\n".join(kept)


def _split_statements(sql: str) -> list[str]:
    """Split a SQL script on ';' while ignoring semicolons inside '...' strings."""
    statements: list[str] = []
    buf: list[str] = []
    in_str = False
    for ch in sql:
        if ch == "'":
            in_str = not in_str
            buf.append(ch)
        elif ch == ";" and not in_str:
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def build_connection():
    """Create an in-memory DuckDB with the credit schema, tables and views."""
    import duckdb  # imported lazily so the dependency is optional

    for csv in REQUIRED_CSVS:
        if not (PROCESSED_DIR / csv).exists():
            raise FileNotFoundError(
                f"{csv} not found in {PROCESSED_DIR}. Run the transform step first."
            )

    con = duckdb.connect(database=":memory:")
    con.execute("CREATE SCHEMA IF NOT EXISTS credit;")

    # Load processed CSVs as base tables (types inferred, dates parsed).
    for csv, table in [
        ("dim_source.csv", "dim_source"),
        ("dim_series.csv", "dim_series"),
        ("dim_date.csv", "dim_date"),
    ]:
        path = (PROCESSED_DIR / csv).as_posix()
        con.execute(
            f"CREATE TABLE credit.{table} AS SELECT * FROM read_csv_auto('{path}', header=true);"
        )

    # The fact table gets a generated observation_id in PostgreSQL (IDENTITY);
    # add an equivalent surrogate here so views.sql runs unchanged.
    fact_path = (PROCESSED_DIR / "fact_observations.csv").as_posix()
    con.execute(
        "CREATE TABLE credit.fact_observations AS "
        "SELECT ROW_NUMBER() OVER () AS observation_id, * "
        f"FROM read_csv_auto('{fact_path}', header=true);"
    )

    # Execute each view definition from the shared views.sql.
    script = _strip_unsupported(VIEWS_SQL.read_text(encoding="utf-8"))
    statements = _split_statements(script)
    created = 0
    for stmt in statements:
        con.execute(stmt + ";")
        if re.search(r"(?is)create\s+or\s+replace\s+view", stmt):
            created += 1
    logger.info("DuckDB: loaded 4 tables and created %s views from views.sql", created)
    return con


def query(con, sql: str) -> pd.DataFrame:
    """Run a SQL query and return a pandas DataFrame."""
    return con.execute(sql).fetchdf()


if __name__ == "__main__":
    connection = build_connection()
    for view in [
        "vw_latest_observation",
        "vw_period_changes",
        "vw_yoy_change",
        "vw_rolling_averages",
        "vw_historical_stats",
        "vw_rate_spreads",
        "vw_category_share",
        "vw_monitoring_alerts",
    ]:
        n = query(connection, f"SELECT COUNT(*) AS n FROM credit.{view}")["n"].iloc[0]
        logger.info("view %-28s rows=%s", view, n)
