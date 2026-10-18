"""Load the processed star-schema CSVs into PostgreSQL.

Runs the DDL scripts in order, then bulk-loads the dimension and fact tables,
then creates the analytical views. Every credential is read from the
environment (see .env.example); nothing is hard-coded.

Graceful degradation: if the PostgreSQL driver is not installed or the database
is not configured, the loader logs clear guidance and exits without error so the
rest of the CSV-based pipeline (and CI) is never blocked. PostgreSQL is one
supported serving layer; the processed CSVs are the other.
"""
from __future__ import annotations

import sys
from pathlib import Path

from ..common.config import PROCESSED_DIR, PROJECT_ROOT, load_database_config
from ..common.logging_utils import get_logger

logger = get_logger("db.load_postgres")

SQL_DIR = PROJECT_ROOT / "sql"
DDL_ORDER = ["schema.sql", "tables.sql", "indexes.sql"]
VIEW_FILE = "views.sql"

# CSV -> table, in FK-safe load order. (column lists exclude generated keys)
LOAD_PLAN = [
    ("dim_source.csv", "credit.dim_source",
     ["source_key", "source_name", "service", "licence"]),
    ("dim_date.csv", "credit.dim_date",
     ["date_key", "date", "year", "quarter", "month", "month_name",
      "year_month", "year_quarter", "day_of_month", "is_month_end", "is_quarter_end"]),
    ("dim_series.csv", "credit.dim_series",
     ["series_key", "series_id", "series_name", "category", "subcategory",
      "unit", "frequency", "measure_type", "source_key"]),
    ("fact_observations.csv", "credit.fact_observations",
     ["series_key", "date_key", "observation_date", "value"]),
]


def _import_driver():
    try:
        import psycopg2  # type: ignore
        return psycopg2
    except ImportError:
        logger.error(
            "psycopg2 is not installed. Install it with `pip install psycopg2-binary` "
            "to enable PostgreSQL loading. The CSV pipeline still works without it."
        )
        return None


def _run_sql_file(cur, path: Path) -> None:
    logger.info("Executing %s", path.name)
    cur.execute(path.read_text(encoding="utf-8"))


def _copy_csv(cur, csv_path: Path, table: str, columns: list[str]) -> int:
    col_sql = ", ".join(columns)
    with csv_path.open("r", encoding="utf-8") as fh:
        cur.copy_expert(
            f"COPY {table} ({col_sql}) FROM STDIN WITH (FORMAT csv, HEADER true)", fh
        )
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    return int(cur.fetchone()[0])


def load() -> bool:
    """Return True if the load ran, False if skipped (driver/db unavailable)."""
    cfg = load_database_config()
    if not cfg.is_configured:
        logger.warning(
            "PostgreSQL is not configured (set PGHOST/PGDATABASE/PGUSER/PGPASSWORD). "
            "Skipping load. Power BI can connect to the processed CSVs instead."
        )
        return False

    psycopg2 = _import_driver()
    if psycopg2 is None:
        return False

    missing = [p for p, _, _ in LOAD_PLAN
               if not (PROCESSED_DIR / p).exists()]
    if missing:
        logger.error("Processed files missing: %s. Run the transform step first.", missing)
        return False

    conn = psycopg2.connect(
        host=cfg.host, port=cfg.port, dbname=cfg.database,
        user=cfg.user, password=cfg.password,
    )
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            for ddl in DDL_ORDER:
                _run_sql_file(cur, SQL_DIR / ddl)
            cur.execute(
                "TRUNCATE TABLE credit.fact_observations, credit.dim_series, "
                "credit.dim_date, credit.dim_source RESTART IDENTITY CASCADE"
            )
            for csv_name, table, columns in LOAD_PLAN:
                n = _copy_csv(cur, PROCESSED_DIR / csv_name, table, columns)
                logger.info("Loaded %s rows into %s", n, table)
            _run_sql_file(cur, SQL_DIR / VIEW_FILE)
        conn.commit()
        logger.info("PostgreSQL load complete.")
        return True
    except Exception:
        conn.rollback()
        logger.exception("PostgreSQL load failed; transaction rolled back.")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    ran = load()
    sys.exit(0 if ran else 0)  # skipping is not an error
