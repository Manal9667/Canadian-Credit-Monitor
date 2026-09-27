"""Filesystem helpers for the raw / processed / reference data layers.

Design rules enforced here:
  * Raw source data is written to timestamped, immutable snapshot folders so
    a new ingestion run never silently overwrites previously retrieved data.
  * Every raw snapshot is accompanied by a metadata sidecar recording the
    source, retrieval timestamp, series/table identifiers and frequency.
  * A stable "latest" pointer file records which snapshot is current, so
    downstream stages are reproducible without guessing folder names.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .config import RAW_DIR


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def run_stamp() -> str:
    """Return a filesystem-safe UTC timestamp used to name snapshot folders."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def raw_snapshot_dir(source: str, stamp: str) -> Path:
    """Return (and create) an immutable raw snapshot directory for a source."""
    path = RAW_DIR / source / stamp
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_raw_dataframe(df: pd.DataFrame, directory: Path, filename: str) -> Path:
    """Persist a raw dataframe to CSV inside a snapshot directory."""
    target = directory / filename
    df.to_csv(target, index=False, encoding="utf-8")
    return target


def write_metadata(metadata: dict[str, Any], directory: Path, filename: str = "metadata.json") -> Path:
    """Write a metadata sidecar describing a raw snapshot."""
    target = directory / filename
    with target.open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2, ensure_ascii=False)
    return target


def update_latest_pointer(source: str, stamp: str) -> Path:
    """Record which snapshot is the current one for a source."""
    pointer = RAW_DIR / source / "latest.json"
    pointer.parent.mkdir(parents=True, exist_ok=True)
    with pointer.open("w", encoding="utf-8") as handle:
        json.dump({"latest_snapshot": stamp, "updated_utc": utc_now_iso()}, handle, indent=2)
    return pointer


def read_latest_pointer(source: str) -> str | None:
    """Return the current snapshot stamp for a source, or None if never run."""
    pointer = RAW_DIR / source / "latest.json"
    if not pointer.exists():
        return None
    with pointer.open("r", encoding="utf-8") as handle:
        return json.load(handle).get("latest_snapshot")


def latest_snapshot_dir(source: str) -> Path | None:
    """Resolve the directory of the current snapshot for a source."""
    stamp = read_latest_pointer(source)
    if stamp is None:
        return None
    path = RAW_DIR / source / stamp
    return path if path.exists() else None
