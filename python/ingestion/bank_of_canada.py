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
    sha256_file,
    write_refresh_status,
)
from ..common.logging_utils import get_logger
from ..validation.engine import validate_candidate_snapshot

logger = get_logger("ingestion.bank_of_canada")

SOURCE = "bank_of_canada"


class ValetAPIError(RuntimeError):
    """Raised when the Valet API cannot be reached or returns bad data."""


def _request_with_retry(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """GET a Valet JSON endpoint with bounded retries and clear errors."""
    timeout = max(1, min(120, int(get_setting("request_timeout_seconds", 30))))
    max_retries = max(1, min(5, int(get_setting("max_retries", 3))))
    backoff = max(0.0, min(30.0, float(get_setting("retry_backoff_seconds", 2))))
    headers = {"User-Agent": str(get_setting("user_agent", "credit-intelligence-platform"))}

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(
                url, params=params, headers=headers, timeout=timeout, verify=ssl_verify()
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.JSONDecodeError as exc:
            # requests' JSON decode error is also a RequestException subclass.
            last_error = exc
            break
        except requests.RequestException as exc:
            last_error = exc
            response = getattr(exc, "response", None)
            status_code = getattr(response, "status_code", None)
            transient = status_code is None or status_code == 429 or status_code >= 500
            logger.warning(
                "Valet request failed (attempt %s/%s) for %s: %s",
                attempt, max_retries, url, exc,
            )
            if transient and attempt < max_retries:
                time.sleep(backoff * attempt)
            elif not transient:
                break
        except ValueError as exc:
            # Invalid JSON is a malformed response, not a transient transport failure.
            last_error = exc
            break
    raise ValetAPIError(f"Failed to retrieve {url} after {attempt} attempt(s): {last_error}")


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

    if not isinstance(payload, dict) or "observations" not in payload:
        raise ValetAPIError(f"Series {series_id}: response missing 'observations' block")
    if not isinstance(payload["observations"], list):
        raise ValetAPIError(f"Series {series_id}: 'observations' must be a list")

    records: list[dict[str, Any]] = []
    for obs in payload["observations"]:
        if not isinstance(obs, dict):
            raise ValetAPIError(f"Series {series_id}: malformed observation record")
        date_str = obs.get("d")
        if date_str is None:
            raise ValetAPIError(f"Series {series_id}: observation is missing its date")
        cell = obs.get(series_id)
        if cell is not None and not isinstance(cell, dict):
            raise ValetAPIError(f"Series {series_id}: malformed value cell for {date_str}")
        raw_value = cell.get("v") if cell is not None else None
        # Valet may omit a cell or return an empty value for a suppressed point.
        value = pd.to_numeric(raw_value, errors="coerce") if raw_value not in (None, "") else pd.NA
        if raw_value not in (None, "") and pd.isna(value):
            raise ValetAPIError(
                f"Series {series_id}: non-numeric value {raw_value!r} for {date_str}"
            )
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


def _ingest_all() -> dict[str, Any]:
    """Ingest every configured Bank of Canada series into a raw snapshot.

    A partial result is rejected so the authoritative pointer remains on the
    last complete, preflight-validated snapshot.
    """
    cfg = load_series_config()["bank_of_canada"]
    start_date = get_setting("start_date")
    stamp = run_stamp()

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

    expected_series_ids = {spec["series_id"] for spec in cfg["series"]}
    actual_series_ids = {item["series_id"] for item in series_meta}
    if failures or actual_series_ids != expected_series_ids:
        missing = sorted(expected_series_ids - actual_series_ids)
        raise ValetAPIError(
            "Bank of Canada refresh incomplete; keeping the previous snapshot "
            f"selected. failures={failures}; missing_series={missing}"
        )

    observations = pd.concat(frames, ignore_index=True)
    meta_df = pd.DataFrame.from_records(series_meta)
    try:
        validation_summary = validate_candidate_snapshot(
            observations, meta_df, SOURCE, expected_series_ids
        )
    except ValueError as exc:
        raise ValetAPIError(
            f"Bank of Canada candidate rejected; previous snapshot remains selected: {exc}"
        ) from exc

    snapshot = raw_snapshot_dir(SOURCE, stamp)
    observations_path = write_raw_dataframe(observations, snapshot, "observations.csv")
    metadata_path = write_raw_dataframe(meta_df, snapshot, "series_metadata.csv")

    run_metadata = {
        "source": SOURCE,
        "api_base": cfg["api_base"],
        "retrieved_utc": utc_now_iso(),
        "snapshot": stamp,
        "source_identifiers": {"series_ids": sorted(expected_series_ids)},
        "series_requested": len(cfg["series"]),
        "series_succeeded": len(frames),
        "series_failed": len(failures),
        "failures": failures,
        "validation": validation_summary,
        "observation_count": int(len(observations)),
        "snapshot_sha256": {
            "observations.csv": sha256_file(observations_path),
            "series_metadata.csv": sha256_file(metadata_path),
        },
        "requires_api_key": False,
        "terms_url": "https://www.bankofcanada.ca/terms/",
    }
    write_metadata(run_metadata, snapshot)
    update_latest_pointer(SOURCE, stamp)

    logger.info(
        "Bank of Canada ingestion complete and preflight validated: %s/%s series, %s observations -> %s",
        len(frames), len(cfg["series"]), len(observations), snapshot,
    )
    return run_metadata


def ingest_all() -> dict[str, Any]:
    """Run ingestion and persist the attempt result without moving a bad pointer."""
    try:
        result = _ingest_all()
    except Exception as exc:
        write_refresh_status(SOURCE, "FAILED", exc)
        raise
    write_refresh_status(SOURCE, "SUCCEEDED")
    return result


if __name__ == "__main__":
    ingest_all()
