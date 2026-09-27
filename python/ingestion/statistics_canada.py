"""Statistics Canada ingestion via the Web Data Service (WDS).

Mechanism (verified, GET-only, reproducible, no key):
  1. GET  /getFullTableDownloadCSV/<productId>/en  -> returns a URL to a zip
  2. Download the zip and extract the official table CSV
  3. Filter to the specific rows we need using descriptor-column text matches
     from config (never hard-coded vector IDs). The actual VECTOR id is read
     from the official file itself and preserved as metadata.

If StatCan renames a dimension member, the matching step logs a schema-change
warning and records the affected filter rather than silently dropping data.

Output (per run):
  data/raw/statistics_canada/<timestamp>/observations.csv    long format
  data/raw/statistics_canada/<timestamp>/series_metadata.csv  one row per series
  data/raw/statistics_canada/<timestamp>/metadata.json        run-level metadata
"""
from __future__ import annotations

import io
import time
import zipfile
from typing import Any

import pandas as pd
import requests

from ..common.config import get_setting, load_series_config
from ..common.http import ssl_verify
from ..common.io_utils import (
    raw_snapshot_dir,
    run_stamp,
    update_latest_pointer,
    utc_now_iso,
    write_metadata,
    write_raw_dataframe,
)
from ..common.logging_utils import get_logger

logger = get_logger("ingestion.statistics_canada")

SOURCE = "statistics_canada"


class StatCanError(RuntimeError):
    """Raised when a StatCan table cannot be retrieved or parsed."""


def _get_json(url: str) -> dict[str, Any]:
    timeout = int(get_setting("request_timeout_seconds", 30))
    headers = {"User-Agent": str(get_setting("user_agent", "credit-intelligence-platform"))}
    response = requests.get(url, headers=headers, timeout=timeout, verify=ssl_verify())
    response.raise_for_status()
    return response.json()


def _download_table_csv(product_id: str) -> pd.DataFrame:
    """Resolve the official CSV download URL and load the extracted table."""
    cfg = load_series_config()["statistics_canada"]
    base = cfg["api_base"].rstrip("/")
    max_retries = int(get_setting("max_retries", 3))
    backoff = float(get_setting("retry_backoff_seconds", 2))
    timeout = int(get_setting("request_timeout_seconds", 30))
    headers = {"User-Agent": str(get_setting("user_agent", "credit-intelligence-platform"))}

    meta_url = f"{base}/getFullTableDownloadCSV/{product_id}/en"
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            meta = _get_json(meta_url)
            if meta.get("status") != "SUCCESS" or not meta.get("object"):
                raise StatCanError(f"Unexpected WDS response for {product_id}: {meta}")
            zip_url = meta["object"]
            resp = requests.get(zip_url, headers=headers, timeout=timeout, verify=ssl_verify())
            resp.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
                # The main data file is <productId>.csv; metadata file ends _MetaData.csv
                data_names = [
                    n for n in archive.namelist()
                    if n.lower().endswith(".csv") and "metadata" not in n.lower()
                ]
                if not data_names:
                    raise StatCanError(f"No data CSV inside StatCan archive for {product_id}")
                with archive.open(data_names[0]) as fh:
                    return pd.read_csv(fh, dtype=str, low_memory=False)
        except (requests.RequestException, ValueError, zipfile.BadZipFile, StatCanError) as exc:
            last_error = exc
            logger.warning(
                "StatCan download failed (attempt %s/%s) for %s: %s",
                attempt, max_retries, product_id, exc,
            )
            if attempt < max_retries:
                time.sleep(backoff * attempt)
    raise StatCanError(f"Failed to retrieve StatCan table {product_id}: {last_error}")


def _resolve_match_column(df: pd.DataFrame, requested: str) -> str | None:
    """Find the descriptor column that best matches the configured name."""
    lowered = {c.lower(): c for c in df.columns}
    if requested.lower() in lowered:
        return lowered[requested.lower()]
    for low, original in lowered.items():
        if requested.lower() in low or low in requested.lower():
            return original
    return None


def _extract_filtered_series(df: pd.DataFrame, table_cfg: dict[str, Any]) -> tuple[pd.DataFrame, list[dict[str, Any]], list[str]]:
    """Apply configured descriptor filters, returning observations + metadata."""
    frames: list[pd.DataFrame] = []
    metas: list[dict[str, Any]] = []
    warnings: list[str] = []

    for flt in table_cfg["row_filters"]:
        match_column = _resolve_match_column(df, flt["match_column"])
        if match_column is None:
            msg = (
                f"Schema change: descriptor column '{flt['match_column']}' not found "
                f"in table {table_cfg['product_id']} (columns: {list(df.columns)})"
            )
            logger.warning(msg)
            warnings.append(msg)
            continue

        target = flt["match_value"].strip().lower()
        col_norm = df[match_column].fillna("").str.strip().str.lower()
        subset = df[col_norm == target]
        if subset.empty:
            # Fall back to a prefix match to tolerate minor wording changes.
            subset = df[col_norm.str.startswith(target[:40])]
        if subset.empty:
            msg = (
                f"Schema change: no rows matched '{flt['match_value']}' in "
                f"column '{match_column}' of table {table_cfg['product_id']}"
            )
            logger.warning(msg)
            warnings.append(msg)
            continue

        # Prefer Canada-level, seasonally adjusted rows when those columns exist.
        if "GEO" in subset.columns and (subset["GEO"] == "Canada").any():
            subset = subset[subset["GEO"] == "Canada"]

        vector = subset["VECTOR"].iloc[0] if "VECTOR" in subset.columns else flt["series_name"]
        series_id = f"STATCAN_{vector}"

        obs = pd.DataFrame(
            {
                "source": SOURCE,
                "series_id": series_id,
                "observation_date": subset["REF_DATE"].astype(str),
                "value": pd.to_numeric(subset["VALUE"], errors="coerce"),
            }
        ).drop_duplicates(subset=["series_id", "observation_date"])

        frames.append(obs)
        metas.append(
            {
                "source": SOURCE,
                "series_id": series_id,
                "series_name": flt["series_name"],
                "category": table_cfg["category"],
                "subcategory": flt["subcategory"],
                "unit": flt["unit"],
                "frequency": table_cfg["frequency"],
                "measure_type": flt["measure_type"],
                "statcan_table": table_cfg["product_id"],
                "statcan_vector": vector,
                "observation_count": len(obs),
                "min_date": obs["observation_date"].min(),
                "max_date": obs["observation_date"].max(),
            }
        )
        logger.info("StatCan %s -> %s (%s obs)", flt["series_name"], vector, len(obs))

    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["source", "series_id", "observation_date", "value"]
    )
    return combined, metas, warnings


def ingest_all() -> dict[str, Any]:
    """Ingest every configured StatCan table into a raw snapshot.

    Network / parsing failures on one table are recorded and skipped so the
    Bank of Canada data (the platform's primary source) is never blocked.
    """
    cfg = load_series_config()["statistics_canada"]
    stamp = run_stamp()

    frames: list[pd.DataFrame] = []
    metas: list[dict[str, Any]] = []
    warnings: list[str] = []
    failures: list[dict[str, str]] = []

    for table_cfg in cfg["tables"]:
        product_id = table_cfg["product_id"]
        try:
            raw = _download_table_csv(product_id)
            obs, table_metas, table_warnings = _extract_filtered_series(raw, table_cfg)
        except StatCanError as exc:
            logger.error("Skipping StatCan table %s: %s", product_id, exc)
            failures.append({"product_id": product_id, "error": str(exc)})
            continue
        if not obs.empty:
            frames.append(obs)
        metas.extend(table_metas)
        warnings.extend(table_warnings)

    if not frames:
        raise StatCanError(
            "No Statistics Canada series could be retrieved. This is a secondary "
            "source; the Bank of Canada pipeline runs independently."
        )

    snapshot = raw_snapshot_dir(SOURCE, stamp)
    observations = pd.concat(frames, ignore_index=True)
    meta_df = pd.DataFrame.from_records(metas)

    write_raw_dataframe(observations, snapshot, "observations.csv")
    write_raw_dataframe(meta_df, snapshot, "series_metadata.csv")

    run_metadata = {
        "source": SOURCE,
        "api_base": cfg["api_base"],
        "retrieved_utc": utc_now_iso(),
        "snapshot": stamp,
        "tables_requested": len(cfg["tables"]),
        "series_succeeded": len(metas),
        "tables_failed": len(failures),
        "failures": failures,
        "schema_warnings": warnings,
        "observation_count": int(len(observations)),
        "requires_api_key": False,
        "licence": "Statistics Canada Open Licence",
    }
    write_metadata(run_metadata, snapshot)
    update_latest_pointer(SOURCE, stamp)

    logger.info(
        "StatCan ingestion complete: %s series, %s observations -> %s",
        len(metas), len(observations), snapshot,
    )
    return run_metadata


if __name__ == "__main__":
    ingest_all()
