"""Bank of Canada Valet API ingestion.

The Valet API is public and requires no API key. This module retrieves the
curated set of series defined in config/series_config.json, one series at a
time so that a single failing series never aborts the whole run or corrupts
previously retrieved data.

Output (per run):
  data/raw/bank_of_canada/<timestamp>/observations.csv   long format
  data/raw/bank_of_canada/<timestamp>/series_metadata.csv one row per series
  data/raw/bank_of_canada/<timestamp>/metadata.json       run-level metadata

Canonical observation columns: source, series_id, observation_date, value
"""
from __future__ import annotations

import time
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

logger = get_logger("ingestion.bank_of_canada")

SOURCE = "bank_of_canada"


class ValetAPIError(RuntimeError):
    """Raised when the Valet API cannot be reached or returns bad data."""


def _request_with_retry(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """GET a Valet JSON endpoint with bounded retries and clear errors."""
    timeout = int(get_setting("request_timeout_seconds", 30))
    max_retries = int(get_setting("max_retries", 3))
    backoff = float(get_setting("retry_backoff_seconds", 2))
    headers = {"User-Agent": str(get_setting("user_agent", "credit-intelligence-platform"))}

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(
                url, params=params, headers=headers, timeout=timeout, verify=ssl_verify()
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:  # network + JSON errors
            last_error = exc
            logger.warning(
                "Valet request failed (attempt %s/%s) for %s: %s",
                attempt, max_retries, url, exc,
            )
            if attempt < max_retries:
                time.sleep(backoff * attempt)
    raise ValetAPIError(f"Failed to retrieve {url} after {max_retries} attempts: {last_error}")


def fetch_series(series_id: str, start_date: str | None = None) -> pd.DataFrame:
    """Fetch one Valet series into a long dataframe.

    Returns columns: source, series_id, observation_date, value
    Raises ValetAPIError on network failure or unexpected payload shape.
    """
    cfg = load_series_config()["bank_of_canada"]
    base = cfg["api_base"].rstrip("/")
    url = f"{base}/observations/{series_id}/json"
    params = {"start_date": start_date} if start_date else None

    payload = _request_with_retry(url, params)

    if "observations" not in payload:
        raise ValetAPIError(f"Series {series_id}: response missing 'observations' block")

    records: list[dict[str, Any]] = []
    for obs in payload["observations"]:
        date_str = obs.get("d")
        cell = obs.get(series_id)
        if date_str is None or cell is None:
            continue
        raw_value = cell.get("v")
        # Valet reports suppressed / missing values as "" - preserve as NaN.
        value = pd.to_numeric(raw_value, errors="coerce") if raw_value not in (None, "") else pd.NA
        records.append(
            {
                "source": SOURCE,
                "series_id": series_id,
                "observation_date": date_str,
                "value": value,
            }
        )

    if not records:
        raise ValetAPIError(f"Series {series_id}: no usable observations returned")

    df = pd.DataFrame.from_records(records)
    logger.info("Fetched %s (%s observations)", series_id, len(df))
    return df


def ingest_all() -> dict[str, Any]:
    """Ingest every configured Bank of Canada series into a raw snapshot.

    A failure on one series is recorded and skipped; the run still produces a
    valid snapshot for the series that succeeded. Returns run metadata.
    """
    cfg = load_series_config()["bank_of_canada"]
    start_date = get_setting("start_date")
    stamp = run_stamp()
    snapshot = raw_snapshot_dir(SOURCE, stamp)

    frames: list[pd.DataFrame] = []
    series_meta: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    for spec in cfg["series"]:
        series_id = spec["series_id"]
        try:
            df = fetch_series(series_id, start_date=start_date)
        except ValetAPIError as exc:
            logger.error("Skipping %s: %s", series_id, exc)
            failures.append({"series_id": series_id, "error": str(exc)})
            continue

        frames.append(df)
        series_meta.append(
            {
                "source": SOURCE,
                "series_id": series_id,
                "series_name": spec["name"],
                "category": spec["category"],
                "subcategory": spec["subcategory"],
                "unit": spec["unit"],
                "frequency": spec["frequency"],
                "measure_type": spec["measure_type"],
                "observation_count": len(df),
                "min_date": df["observation_date"].min(),
                "max_date": df["observation_date"].max(),
            }
        )

    if not frames:
        raise ValetAPIError(
            "No Bank of Canada series could be retrieved; leaving previous "
            "snapshots untouched to avoid corrupting historical data."
        )

    observations = pd.concat(frames, ignore_index=True)
    meta_df = pd.DataFrame.from_records(series_meta)

    write_raw_dataframe(observations, snapshot, "observations.csv")
    write_raw_dataframe(meta_df, snapshot, "series_metadata.csv")

    run_metadata = {
        "source": SOURCE,
        "api_base": cfg["api_base"],
        "retrieved_utc": utc_now_iso(),
        "snapshot": stamp,
        "series_requested": len(cfg["series"]),
        "series_succeeded": len(frames),
        "series_failed": len(failures),
        "failures": failures,
        "observation_count": int(len(observations)),
        "requires_api_key": False,
        "terms_url": "https://www.bankofcanada.ca/terms/",
    }
    write_metadata(run_metadata, snapshot)
    update_latest_pointer(SOURCE, stamp)

    logger.info(
        "Bank of Canada ingestion complete: %s/%s series, %s observations -> %s",
        len(frames), len(cfg["series"]), len(observations), snapshot,
    )
    return run_metadata


if __name__ == "__main__":
    ingest_all()
