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
import hashlib
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from .config import RAW_DIR


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def run_stamp() -> str:
    """Return a filesystem-safe UTC timestamp used to name snapshot folders."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def publish_output_bundle(writers: dict[Path, Callable[[Path], None]]) -> None:
    """Prepare a set of output files, then publish them with rollback on error.

    Each staged file is created beside its destination so replacement stays on
    the same filesystem. A failed writer or replacement restores every prior
    file. This protects normal interrupted/exceptional refreshes; a machine
    power loss during the short multi-file publish window is not a filesystem
    transaction and remains a limitation of the flat-file layout.
    """
    staged: dict[Path, Path] = {}
    backups: dict[Path, Path] = {}
    published: list[Path] = []
    try:
        for destination, writer in writers.items():
            destination.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(
                prefix=f".{destination.name}.", suffix=".staged", dir=destination.parent
            )
            os.close(fd)
            temporary = Path(temp_name)
            staged[destination] = temporary
            writer(temporary)

        for destination in writers:
            if destination.exists():
                fd, backup_name = tempfile.mkstemp(
                    prefix=f".{destination.name}.", suffix=".backup", dir=destination.parent
                )
                os.close(fd)
                backup = Path(backup_name)
                backup.unlink()
                os.replace(destination, backup)
                backups[destination] = backup
            os.replace(staged[destination], destination)
            published.append(destination)
    except Exception:
        for destination in reversed(published):
            destination.unlink(missing_ok=True)
        for destination, backup in backups.items():
            if backup.exists():
                os.replace(backup, destination)
        raise
    finally:
        for path in [*staged.values(), *backups.values()]:
            path.unlink(missing_ok=True)


def dataframe_writer(frame: pd.DataFrame) -> Callable[[Path], None]:
    """Return a staged CSV writer for an output bundle."""
    return lambda path: frame.to_csv(path, index=False, encoding="utf-8")


def json_writer(value: dict[str, Any]) -> Callable[[Path], None]:
    """Return a staged JSON writer for an output bundle."""
    def write(path: Path) -> None:
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    return write


def sha256_file(path: Path) -> str:
    """Return a stable SHA-256 digest for a persisted source snapshot file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_refresh_status(source: str, status: str, error: Exception | None = None) -> Path:
    """Persist the latest ingestion attempt independently of the selected snapshot."""
    path = RAW_DIR / source / "last_refresh.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "source": source,
        "status": status,
        "attempted_utc": utc_now_iso(),
    }
    if error is not None:
        payload["error_type"] = type(error).__name__
        payload["error"] = str(error)
    fd, temp_name = tempfile.mkstemp(prefix=".last_refresh.", suffix=".tmp", dir=path.parent)
    os.close(fd)
    temporary = Path(temp_name)
    try:
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


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
    temporary = pointer.with_name(f".{pointer.name}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump({"latest_snapshot": stamp, "updated_utc": utc_now_iso()}, handle, indent=2)
        handle.flush()
    temporary.replace(pointer)
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
