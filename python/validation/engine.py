"""Validation engine: load a source's latest raw snapshot, run the check
battery, and render both a machine-readable CSV and a human-readable report.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from ..common.config import DOCS_DIR, PROCESSED_DIR, RAW_DIR
from ..common.io_utils import (
    dataframe_writer, latest_snapshot_dir, publish_output_bundle, utc_now_iso,
)
from ..common.logging_utils import get_logger
from .validators import ValidationResult, build_series_freshness, run_checks, worst_severity

logger = get_logger("validation.engine")

VALIDATION_RESULTS_CSV = PROCESSED_DIR / "validation_results.csv"
VALIDATION_REPORT_MD = DOCS_DIR / "validation_report.md"
SERIES_FRESHNESS_CSV = PROCESSED_DIR / "series_freshness.csv"
SOURCE_HEALTH_CSV = PROCESSED_DIR / "source_health.csv"


def load_source_frame(source: str, snapshot: Path | None = None) -> pd.DataFrame:
    """Load a source's latest observations joined to its series metadata."""
    snap = snapshot or latest_snapshot_dir(source)
    if snap is None:
        raise FileNotFoundError(
            f"No raw snapshot for {source}. Run ingestion before validation."
        )
    obs = pd.read_csv(snap / "observations.csv")
    meta = pd.read_csv(snap / "series_metadata.csv")
    meta_cols = ["series_id", "series_name", "frequency", "unit", "measure_type", "category"]
    meta_cols = [c for c in meta_cols if c in meta.columns]
    return obs.merge(meta[meta_cols], on="series_id", how="left")


def validate_candidate_snapshot(
    observations: pd.DataFrame,
    metadata: pd.DataFrame,
    source: str,
    expected_series_ids: set[str],
) -> dict[str, int]:
    """Preflight a complete source candidate before its latest pointer moves."""
    if observations.empty:
        raise ValueError("Candidate snapshot has no observations")
    if metadata["series_id"].isna().any() or metadata["series_id"].duplicated().any():
        raise ValueError("Candidate series metadata has missing or duplicate IDs")
    observation_columns = {"source", "series_id", "observation_date", "value"}
    missing_observation_columns = observation_columns - set(observations.columns)
    if missing_observation_columns:
        raise ValueError(
            f"Candidate observations are missing columns: {sorted(missing_observation_columns)}"
        )
    unexpected_observation_columns = set(observations.columns) - observation_columns
    if unexpected_observation_columns:
        raise ValueError(
            "Candidate observations have unexpected columns: "
            f"{sorted(unexpected_observation_columns)}"
        )
    parsed_dates = pd.to_datetime(observations["observation_date"], errors="coerce")
    if parsed_dates.isna().any():
        raise ValueError("Candidate observations contain malformed dates")
    numeric_values = pd.to_numeric(observations["value"], errors="coerce")
    invalid_values = observations["value"].notna() & numeric_values.isna()
    if invalid_values.any():
        raise ValueError("Candidate observations contain non-numeric values")
    if observations["series_id"].isna().any():
        raise ValueError("Candidate observations contain missing series IDs")
    actual_series_ids = set(metadata["series_id"].astype(str))
    if actual_series_ids != expected_series_ids:
        missing = sorted(expected_series_ids - actual_series_ids)
        unexpected = sorted(actual_series_ids - expected_series_ids)
        raise ValueError(f"Candidate series mismatch; missing={missing}, unexpected={unexpected}")
    observation_series_ids = set(observations["series_id"].dropna().astype(str))
    if observation_series_ids != expected_series_ids:
        missing = sorted(expected_series_ids - observation_series_ids)
        unexpected = sorted(observation_series_ids - expected_series_ids)
        raise ValueError(
            f"Candidate observations mismatch; missing={missing}, unexpected={unexpected}"
        )
    if observations["source"].isna().any() or set(observations["source"].astype(str)) != {source}:
        raise ValueError(f"Candidate observations do not all belong to {source}")

    metadata_columns = [
        "series_id", "series_name", "frequency", "unit", "measure_type", "category"
    ]
    missing_columns = set(metadata_columns) - set(metadata.columns)
    if missing_columns:
        raise ValueError(f"Candidate metadata is missing columns: {sorted(missing_columns)}")
    frame = observations.merge(
        metadata[metadata_columns], on="series_id", how="left", validate="many_to_one"
    )
    results = run_checks(frame)
    blocking = [result.rule for result in results if result.status != "PASS"]
    if blocking:
        raise ValueError(f"Candidate snapshot has validation warnings or failures: {blocking}")
    return {
        "checks_run": len(results),
        "checks_passed": sum(result.status == "PASS" for result in results),
        "checks_warned": sum(result.status == "WARN" for result in results),
    }


def validate_source(
    source: str, snapshot: Path | None = None
) -> tuple[list[ValidationResult], dict[str, Any]]:
    """Run the check battery for one source and return results + a summary."""
    df = load_source_frame(source, snapshot)
    results = run_checks(df)
    summary = {
        "source": source,
        "validated_utc": utc_now_iso(),
        "observations": int(len(df)),
        "series": int(df["series_id"].nunique()),
        "checks_run": len(results),
        "checks_passed": sum(r.status == "PASS" for r in results),
        "checks_warned": sum(r.status == "WARN" for r in results),
        "checks_failed": sum(r.status == "FAIL" for r in results),
        "worst_severity": worst_severity(results),
    }
    logger.info(
        "%s validation: %s PASS / %s WARN / %s FAIL (worst severity %s)",
        source, summary["checks_passed"], summary["checks_warned"],
        summary["checks_failed"], summary["worst_severity"],
    )
    return results, summary


def _render_source_section(source: str, results: list[ValidationResult], summary: dict[str, Any]) -> str:
    lines = [
        f"## Source: {source}",
        "",
        f"- Observations checked: {summary['observations']}",
        f"- Series checked: {summary['series']}",
        f"- Result: {summary['checks_passed']} PASS / "
        f"{summary['checks_warned']} WARN / {summary['checks_failed']} FAIL",
        f"- Worst severity: {summary['worst_severity']}",
        "",
    ]
    for r in results:
        lines.append("### DATA QUALITY CHECK")
        lines.append("")
        lines.append(f"Check: {r.rule}")
        lines.append(f"Status: {r.status}")
        lines.append(f"Records affected: {r.records_affected}")
        lines.append(f"Severity: {r.severity}")
        lines.append(f"Recommended action: {r.recommended_action}")
        if r.details:
            detail_str = "; ".join(f"{k}: {v}" for k, v in r.details.items())
            lines.append(f"Details: {detail_str}")
        lines.append("")
    return "\n".join(lines)


def run_all(sources: list[str]) -> dict[str, Any]:
    """Validate every source, write the CSV + markdown report, return summary."""
    all_rows: list[dict[str, Any]] = []
    freshness_rows: list[dict[str, Any]] = []
    md_sections: list[str] = []
    summaries: list[dict[str, Any]] = []
    health_rows: list[dict[str, Any]] = []
    any_fail = False
    processed_utc = utc_now_iso()
    as_of = pd.Timestamp.now(tz="UTC").tz_localize(None)

    for source in sources:
        snapshot = latest_snapshot_dir(source)
        try:
            if snapshot is None:
                raise FileNotFoundError(
                    f"No raw snapshot for {source}. Run ingestion before validation."
                )
            results, summary = validate_source(source, snapshot)
        except FileNotFoundError as exc:
            logger.error("Validation incomplete for required source %s: %s", source, exc)
            refresh_path = RAW_DIR / source / "last_refresh.json"
            refresh = json.loads(refresh_path.read_text(encoding="utf-8")) if refresh_path.exists() else {}
            health_rows.append({
                "source": source, "health_status": "FAILED", "series_count": 0,
                "observations": 0, "latest_observation_date": "",
                "snapshot_id": "", "retrieval_timestamp_utc": "",
                "last_refresh_status": refresh.get("status", "UNKNOWN"),
                "last_refresh_attempted_utc": refresh.get("attempted_utc", ""),
                "reason": refresh.get("error", str(exc)),
            })
            # Health is intentionally published separately; prior analytical
            # reports remain intact when any required source is unavailable.
            publish_output_bundle({SOURCE_HEALTH_CSV: dataframe_writer(pd.DataFrame(health_rows))})
            raise RuntimeError(
                f"Validation incomplete for required source {source}; previous reports preserved."
            ) from exc
        summaries.append(summary)
        md_sections.append(_render_source_section(source, results, summary))
        any_fail = any_fail or summary["checks_failed"] > 0
        manifest = json.loads((snapshot / "metadata.json").read_text(encoding="utf-8"))
        source_frame = load_source_frame(source, snapshot)
        freshness_rows.extend(
            build_series_freshness(
                source_frame,
                source,
                snapshot.name,
                manifest.get("retrieved_utc", ""),
                processed_utc,
                as_of,
            )
        )
        source_status = "CURRENT"
        statuses = {row["freshness_status"] for row in freshness_rows if row["source"] == source}
        if "OVERDUE" in statuses:
            source_status = "STALE"
        elif summary["checks_failed"] or summary["checks_warned"] or manifest.get("failures") or manifest.get("schema_warnings"):
            source_status = "PARTIAL"
        elif "UNKNOWN" in statuses:
            source_status = "UNKNOWN"
        refresh_path = RAW_DIR / source / "last_refresh.json"
        refresh = json.loads(refresh_path.read_text(encoding="utf-8")) if refresh_path.exists() else {}
        if refresh.get("status") == "FAILED":
            source_status = "FAILED"
        health_rows.append({
            "source": source, "health_status": source_status,
            "series_count": summary["series"], "observations": summary["observations"],
            "latest_observation_date": str(source_frame["observation_date"].max()),
            "snapshot_id": snapshot.name,
            "retrieval_timestamp_utc": manifest.get("retrieved_utc", ""),
            "last_refresh_status": refresh.get("status", "UNKNOWN"),
            "last_refresh_attempted_utc": refresh.get("attempted_utc", ""),
            "reason": refresh.get("error", "" if source_status == "CURRENT" else f"Source status derived from cadence/validation: {source_status}"),
        })
        for r in results:
            row = r.to_row()
            row["source"] = source
            all_rows.append(row)

    if not all_rows:
        raise RuntimeError("No sources could be validated. Run ingestion first.")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    header = [
        "# Data Quality Validation Report",
        "",
        f"_Generated: {utc_now_iso()}_",
        "",
        "This report is produced automatically by the validation framework "
        "(`python/validation`). Each rule records its status, the number of "
        "records affected, a severity grade, and a recommended action.",
        "",
        "Per-series source observation, snapshot retrieval, validation processing, "
        "and next expected publication dates are recorded in "
        "`data/processed/series_freshness.csv`. Expected dates are schedule "
        "projections, not guarantees.",
        "",
        f"**Overall gate:** {'FAIL - review required' if any_fail else 'PASS - safe to load'}",
        "",
        "---",
        "",
    ]
    report = "\n".join(header) + "\n\n".join(md_sections)
    results_frame = pd.DataFrame(all_rows)
    freshness_frame = pd.DataFrame(freshness_rows)
    publish_output_bundle({
        VALIDATION_RESULTS_CSV: dataframe_writer(results_frame),
        SERIES_FRESHNESS_CSV: dataframe_writer(freshness_frame),
        SOURCE_HEALTH_CSV: dataframe_writer(pd.DataFrame(health_rows)),
        VALIDATION_REPORT_MD: lambda path: path.write_text(report, encoding="utf-8"),
    })
    logger.info("Validation report written to %s", VALIDATION_REPORT_MD)

    return {
        "sources": summaries,
        "any_fail": any_fail,
        "results_csv": str(VALIDATION_RESULTS_CSV),
        "series_freshness_csv": str(SERIES_FRESHNESS_CSV),
        "report_md": str(VALIDATION_REPORT_MD),
    }


def main() -> int:
    """Validate both configured sources and return a CI-friendly exit code."""
    summary = run_all(["bank_of_canada", "statistics_canada"])
    if summary["any_fail"]:
        logger.error("Validation gate failed; review %s", summary["report_md"])
        return 1
    logger.info("Validation gate passed; review %s", summary["report_md"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
