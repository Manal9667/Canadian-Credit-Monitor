"""Transformation / conforming layer.

Reads the latest raw snapshot from each source and produces the conformed,
analysis-ready star-schema tables in data/processed/:

    dim_source.csv          one row per data source
    dim_series.csv          one row per series (the series dimension)
    dim_date.csv            daily calendar dimension spanning the data
    fact_observations.csv   long fact table: one row per series per date

It also writes a reference file (data/reference/category_reference.csv) that
maps categories/subcategories for downstream joins and Power Query.

This layer is deliberately kept to *structural* conforming (typing, keys,
date normalization, dimensional split). Business metrics (changes, rolling
averages, deviations) are computed in the analytics layer and in SQL/DAX, so
each layer has a clear, non-duplicated responsibility.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from ..common.config import PROCESSED_DIR, REFERENCE_DIR, ensure_data_dirs, load_series_config
from ..common.io_utils import latest_snapshot_dir, utc_now_iso
from ..common.logging_utils import get_logger

logger = get_logger("transformation.transform")

SOURCES = ["bank_of_canada", "statistics_canada"]

SOURCE_LABELS = {
    "bank_of_canada": {
        "source_name": "Bank of Canada",
        "service": "Valet API",
        "licence": "Public data (Bank of Canada terms of use)",
    },
    "statistics_canada": {
        "source_name": "Statistics Canada",
        "service": "Web Data Service (WDS)",
        "licence": "Statistics Canada Open Licence",
    },
}


def _load_latest(source: str) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """Load observations + series metadata from a source's latest snapshot."""
    snap = latest_snapshot_dir(source)
    if snap is None:
        logger.warning("No snapshot found for %s; skipping in transform.", source)
        return None
    obs = pd.read_csv(snap / "observations.csv")
    meta = pd.read_csv(snap / "series_metadata.csv")
    return obs, meta


def _normalize_dates(obs: pd.DataFrame) -> pd.DataFrame:
    """Parse observation_date strings (daily/weekly/monthly/quarterly) to dates."""
    obs = obs.copy()
    raw = obs["observation_date"].astype(str).str.strip()
    # StatCan quarterly/monthly REF_DATE arrives as "YYYY-MM"; pad to first of
    # month so a single ISO parser handles daily, weekly, monthly and quarterly.
    raw = raw.where(~raw.str.fullmatch(r"\d{4}-\d{2}"), raw + "-01")
    parsed = pd.to_datetime(raw, format="ISO8601", errors="coerce")
    if parsed.isna().any():
        bad = obs.loc[parsed.isna(), "observation_date"].unique()[:5]
        logger.warning("Some dates could not be parsed and were dropped: %s", bad)
    obs["observation_date"] = parsed
    return obs.dropna(subset=["observation_date"])


def build_dim_source() -> pd.DataFrame:
    rows = []
    for key, label in SOURCE_LABELS.items():
        rows.append({"source_key": key, **label})
    return pd.DataFrame(rows)


def build_dim_series(all_meta: pd.DataFrame) -> pd.DataFrame:
    """Series dimension. series_id is the natural key; add a surrogate key."""
    keep = [
        "series_id", "series_name", "category", "subcategory",
        "unit", "frequency", "measure_type", "source",
    ]
    for col in keep:
        if col not in all_meta.columns:
            all_meta[col] = pd.NA
    dim = all_meta[keep].drop_duplicates(subset=["series_id"]).reset_index(drop=True)
    dim = dim.rename(columns={"source": "source_key"})
    dim.insert(0, "series_key", range(1, len(dim) + 1))
    return dim


def build_dim_date(min_date: pd.Timestamp, max_date: pd.Timestamp) -> pd.DataFrame:
    """Daily calendar dimension with fields Power BI / SQL commonly need."""
    dates = pd.date_range(min_date.normalize(), max_date.normalize(), freq="D")
    dim = pd.DataFrame({"date": dates})
    dim["date_key"] = dim["date"].dt.strftime("%Y%m%d").astype(int)
    dim["year"] = dim["date"].dt.year
    dim["quarter"] = dim["date"].dt.quarter
    dim["month"] = dim["date"].dt.month
    dim["month_name"] = dim["date"].dt.strftime("%B")
    dim["year_month"] = dim["date"].dt.strftime("%Y-%m")
    dim["year_quarter"] = dim["year"].astype(str) + "-Q" + dim["quarter"].astype(str)
    dim["day_of_month"] = dim["date"].dt.day
    dim["is_month_end"] = dim["date"].dt.is_month_end
    dim["is_quarter_end"] = dim["date"].dt.is_quarter_end
    # Reorder so date_key leads.
    return dim[[
        "date_key", "date", "year", "quarter", "month", "month_name",
        "year_month", "year_quarter", "day_of_month", "is_month_end", "is_quarter_end",
    ]]


def build_fact_observations(obs: pd.DataFrame, dim_series: pd.DataFrame) -> pd.DataFrame:
    """Conform observations into the fact table with surrogate keys."""
    fact = obs.merge(
        dim_series[["series_key", "series_id"]], on="series_id", how="inner"
    )
    fact["date_key"] = fact["observation_date"].dt.strftime("%Y%m%d").astype(int)
    fact["value"] = pd.to_numeric(fact["value"], errors="coerce")
    fact = fact[["series_key", "series_id", "date_key", "observation_date", "value"]]
    fact = fact.sort_values(["series_key", "observation_date"]).reset_index(drop=True)
    return fact


def run() -> dict[str, Any]:
    """Execute the full transformation and write processed + reference outputs."""
    ensure_data_dirs()

    obs_frames: list[pd.DataFrame] = []
    meta_frames: list[pd.DataFrame] = []
    for source in SOURCES:
        loaded = _load_latest(source)
        if loaded is None:
            continue
        obs, meta = loaded
        obs_frames.append(obs)
        meta_frames.append(meta)

    if not obs_frames:
        raise RuntimeError(
            "No raw snapshots available to transform. Run ingestion first "
            "(python -m python.ingestion.bank_of_canada)."
        )

    all_obs = _normalize_dates(pd.concat(obs_frames, ignore_index=True))
    all_meta = pd.concat(meta_frames, ignore_index=True)

    dim_source = build_dim_source()
    dim_series = build_dim_series(all_meta)
    dim_date = build_dim_date(all_obs["observation_date"].min(), all_obs["observation_date"].max())
    fact = build_fact_observations(all_obs, dim_series)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)

    dim_source.to_csv(PROCESSED_DIR / "dim_source.csv", index=False)
    dim_series.to_csv(PROCESSED_DIR / "dim_series.csv", index=False)
    dim_date.to_csv(PROCESSED_DIR / "dim_date.csv", index=False)
    fact.to_csv(PROCESSED_DIR / "fact_observations.csv", index=False)

    # Reference: category mapping (useful for Power Query reference-data joins).
    category_ref = (
        dim_series[["category", "subcategory", "measure_type", "unit"]]
        .drop_duplicates()
        .sort_values(["category", "subcategory"])
        .reset_index(drop=True)
    )
    category_ref.to_csv(REFERENCE_DIR / "category_reference.csv", index=False)

    summary = {
        "transformed_utc": utc_now_iso(),
        "series_count": int(len(dim_series)),
        "observation_count": int(len(fact)),
        "date_min": str(fact["observation_date"].min().date()),
        "date_max": str(fact["observation_date"].max().date()),
        "sources": SOURCES,
        "outputs": [
            "dim_source.csv", "dim_series.csv", "dim_date.csv", "fact_observations.csv",
        ],
    }
    logger.info(
        "Transform complete: %s series, %s observations (%s to %s)",
        summary["series_count"], summary["observation_count"],
        summary["date_min"], summary["date_max"],
    )
    return summary


if __name__ == "__main__":
    run()
