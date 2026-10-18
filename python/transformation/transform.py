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

import json
from typing import Any

import pandas as pd

from ..common.config import PROCESSED_DIR, REFERENCE_DIR, ensure_data_dirs
from ..common.io_utils import (
    dataframe_writer, json_writer, latest_snapshot_dir, publish_output_bundle,
    sha256_file, utc_now_iso,
)
from ..common.logging_utils import get_logger

logger = get_logger("transformation.transform")

SOURCES = ["bank_of_canada", "statistics_canada"]
TRANSFORMATION_SCHEMA_VERSION = "1.1"

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
        raise FileNotFoundError(
            f"No selected snapshot for required source {source}; refusing partial transform."
        )
    obs = pd.read_csv(snap / "observations.csv")
    meta = pd.read_csv(snap / "series_metadata.csv")
    manifest_path = snap / "metadata.json"
    if not manifest_path.exists():
        raise ValueError(f"Snapshot manifest missing for {source}: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("source") != source:
        raise ValueError(f"Snapshot source mismatch for {source}: {manifest.get('source')}")
    failed_count = manifest.get("series_failed", manifest.get("tables_failed", 0))
    if failed_count or manifest.get("failures") or manifest.get("schema_warnings"):
        raise ValueError(
            f"Latest {source} snapshot is incomplete; rerun ingestion before transform. "
            f"Failures: {failed_count}; schema warnings: "
            f"{len(manifest.get('schema_warnings', []))}"
        )
    required_observation_columns = {"source", "series_id", "observation_date", "value"}
    required_metadata_columns = {
        "source", "series_id", "series_name", "category", "subcategory",
        "unit", "frequency", "measure_type",
    }
    missing_observations = required_observation_columns - set(obs.columns)
    missing_metadata = required_metadata_columns - set(meta.columns)
    if missing_observations or missing_metadata:
        raise ValueError(
            f"Unexpected raw schema for {source}: missing observation columns "
            f"{sorted(missing_observations)}; missing metadata columns "
            f"{sorted(missing_metadata)}"
        )
    expected_count = manifest.get("observation_count")
    if expected_count is not None and int(expected_count) != len(obs):
        raise ValueError(
            f"Snapshot observation count mismatch for {source}: "
            f"manifest={expected_count}, file={len(obs)}"
        )
    for filename, expected_digest in manifest.get("snapshot_sha256", {}).items():
        snapshot_file = snap / filename
        if not snapshot_file.is_file() or sha256_file(snapshot_file) != expected_digest:
            raise ValueError(f"Snapshot checksum mismatch for {source}/{filename}")
    if obs.empty or meta.empty:
        raise ValueError(f"Selected snapshot for {source} is empty")
    if obs.duplicated(["series_id", "observation_date"]).any():
        raise ValueError(f"Selected snapshot for {source} has duplicate series/date keys")
    if set(obs["source"].astype(str)) != {source}:
        raise ValueError(f"Selected snapshot observations do not belong to {source}")
    if set(obs["series_id"].dropna().astype(str)) != set(meta["series_id"].dropna().astype(str)):
        raise ValueError(f"Selected snapshot series IDs differ between observations and metadata for {source}")
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
        raise ValueError(f"Unparseable observation dates: {bad.tolist()}")
    obs["observation_date"] = parsed.dt.normalize()
    return obs


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
    if all_meta["series_id"].isna().any():
        raise ValueError("Series metadata contains a missing series_id")
    conflicting = all_meta.groupby("series_id", dropna=False)[keep[1:]].nunique(
        dropna=False
    ).gt(1).any(axis=1)
    if conflicting.any():
        conflicts = conflicting[conflicting].index
        series_ids = all_meta.loc[all_meta["series_id"].isin(conflicts), "series_id"].unique()
        raise ValueError(f"Conflicting metadata for series: {series_ids[:5].tolist()}")
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
    if obs["series_id"].isna().any():
        raise ValueError("Observations contain a missing series_id")
    unmatched = set(obs["series_id"].dropna()) - set(dim_series["series_id"].dropna())
    if unmatched:
        raise ValueError(f"Observations have no series metadata: {sorted(unmatched)[:5]}")
    duplicate_mask = obs.duplicated(subset=["series_id", "observation_date"], keep=False)
    if duplicate_mask.any():
        sample = obs.loc[duplicate_mask, ["series_id", "observation_date"]].head(5)
        raise ValueError(f"Duplicate series/date observations: {sample.to_dict('records')}")
    fact = obs.merge(
        dim_series[["series_key", "series_id"]], on="series_id", how="inner"
    )
    fact["date_key"] = fact["observation_date"].dt.strftime("%Y%m%d").astype(int)
    raw_values = fact["value"]
    fact["value"] = pd.to_numeric(raw_values, errors="coerce")
    invalid_values = (
        raw_values.notna()
        & raw_values.astype(str).str.strip().ne("")
        & fact["value"].isna()
    )
    if invalid_values.any():
        examples = raw_values.loc[invalid_values].astype(str).unique()[:5].tolist()
        raise ValueError(f"Non-numeric observation values: {examples}")
    fact = fact[["series_key", "series_id", "date_key", "observation_date", "value"]]
    fact = fact.sort_values(["series_key", "observation_date"]).reset_index(drop=True)
    return fact


def run() -> dict[str, Any]:
    """Execute the full transformation and write processed + reference outputs."""
    ensure_data_dirs()

    obs_frames: list[pd.DataFrame] = []
    meta_frames: list[pd.DataFrame] = []
    source_provenance: list[dict[str, Any]] = []
    for source in SOURCES:
        loaded = _load_latest(source)
        obs, meta = loaded
        obs_frames.append(obs)
        meta_frames.append(meta)
        snapshot = latest_snapshot_dir(source)
        manifest = json.loads((snapshot / "metadata.json").read_text(encoding="utf-8"))
        source_identifiers = manifest.get("source_identifiers", {})
        if not source_identifiers:
            if source == "bank_of_canada":
                source_identifiers = {"series_ids": sorted(meta["series_id"].astype(str).unique())}
            else:
                source_identifiers = {
                    "table_ids": sorted(meta["statcan_table"].dropna().astype(str).unique())
                    if "statcan_table" in meta else [],
                    "vector_ids": sorted(meta["statcan_vector"].dropna().astype(str).unique())
                    if "statcan_vector" in meta else [],
                }
        checksums = manifest.get("snapshot_sha256") or {
            "observations.csv": sha256_file(snapshot / "observations.csv"),
            "series_metadata.csv": sha256_file(snapshot / "series_metadata.csv"),
        }
        source_provenance.append(
            {
                "source": source,
                "snapshot": snapshot.name,
                "retrieved_utc": manifest.get("retrieved_utc"),
                "observation_count": len(obs),
                "series_count": int(meta["series_id"].nunique()),
                "source_identifiers": source_identifiers,
                "snapshot_sha256": checksums,
            }
        )

    all_obs = _normalize_dates(pd.concat(obs_frames, ignore_index=True))
    if all_obs.empty:
        raise ValueError("Raw snapshots contain no usable observations")
    if (all_obs["observation_date"] > pd.Timestamp.now().normalize()).any():
        raise ValueError("Raw snapshots contain future-dated observations")
    all_meta = pd.concat(meta_frames, ignore_index=True)

    dim_source = build_dim_source()
    dim_series = build_dim_series(all_meta)
    dim_date = build_dim_date(all_obs["observation_date"].min(), all_obs["observation_date"].max())
    fact = build_fact_observations(all_obs, dim_series)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)

    # Reference: category mapping (useful for Power Query reference-data joins).
    category_ref = (
        dim_series[["category", "subcategory", "measure_type", "unit"]]
        .drop_duplicates()
        .sort_values(["category", "subcategory"])
        .reset_index(drop=True)
    )
    summary = {
        "transformation_schema_version": TRANSFORMATION_SCHEMA_VERSION,
        "transformations": [
            "normalize observation dates to daily timestamps",
            "validate unique (series_id, observation_date) keys",
            "coerce values to numeric and reject malformed non-empty values",
            "build source, series and date dimensions with a long observation fact table",
        ],
        "transformed_utc": utc_now_iso(),
        "series_count": int(len(dim_series)),
        "observation_count": int(len(fact)),
        "date_min": str(fact["observation_date"].min().date()),
        "date_max": str(fact["observation_date"].max().date()),
        "sources": [item["source"] for item in source_provenance],
        "source_provenance": source_provenance,
        "outputs": [
            "dim_source.csv", "dim_series.csv", "dim_date.csv", "fact_observations.csv",
            "pipeline_metadata.json",
        ],
    }
    publish_output_bundle({
        PROCESSED_DIR / "dim_source.csv": dataframe_writer(dim_source),
        PROCESSED_DIR / "dim_series.csv": dataframe_writer(dim_series),
        PROCESSED_DIR / "dim_date.csv": dataframe_writer(dim_date),
        PROCESSED_DIR / "fact_observations.csv": dataframe_writer(fact),
        PROCESSED_DIR / "pipeline_metadata.json": json_writer(summary),
        REFERENCE_DIR / "category_reference.csv": dataframe_writer(category_ref),
    })
    logger.info(
        "Transform complete: %s series, %s observations (%s to %s)",
        summary["series_count"], summary["observation_count"],
        summary["date_min"], summary["date_max"],
    )
    return summary


if __name__ == "__main__":
    run()
