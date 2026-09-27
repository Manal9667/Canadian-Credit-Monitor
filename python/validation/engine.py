"""Validation engine: load a source's latest raw snapshot, run the check
battery, and render both a machine-readable CSV and a human-readable report.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ..common.config import DOCS_DIR, PROCESSED_DIR
from ..common.io_utils import latest_snapshot_dir, utc_now_iso
from ..common.logging_utils import get_logger
from .validators import ValidationResult, run_checks, worst_severity

logger = get_logger("validation.engine")

VALIDATION_RESULTS_CSV = PROCESSED_DIR / "validation_results.csv"
VALIDATION_REPORT_MD = DOCS_DIR / "validation_report.md"


def load_source_frame(source: str) -> pd.DataFrame:
    """Load a source's latest observations joined to its series metadata."""
    snap = latest_snapshot_dir(source)
    if snap is None:
        raise FileNotFoundError(
            f"No raw snapshot for {source}. Run ingestion before validation."
        )
    obs = pd.read_csv(snap / "observations.csv")
    meta = pd.read_csv(snap / "series_metadata.csv")
    meta_cols = ["series_id", "frequency", "unit", "measure_type", "category"]
    meta_cols = [c for c in meta_cols if c in meta.columns]
    return obs.merge(meta[meta_cols], on="series_id", how="left")


def validate_source(source: str) -> tuple[list[ValidationResult], dict[str, Any]]:
    """Run the check battery for one source and return results + a summary."""
    df = load_source_frame(source)
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
    md_sections: list[str] = []
    summaries: list[dict[str, Any]] = []
    any_fail = False

    for source in sources:
        try:
            results, summary = validate_source(source)
        except FileNotFoundError as exc:
            logger.warning("Skipping %s: %s", source, exc)
            continue
        summaries.append(summary)
        md_sections.append(_render_source_section(source, results, summary))
        any_fail = any_fail or summary["checks_failed"] > 0
        for r in results:
            row = r.to_row()
            row["source"] = source
            all_rows.append(row)

    if not all_rows:
        raise RuntimeError("No sources could be validated. Run ingestion first.")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(all_rows).to_csv(VALIDATION_RESULTS_CSV, index=False)

    header = [
        "# Data Quality Validation Report",
        "",
        f"_Generated: {utc_now_iso()}_",
        "",
        "This report is produced automatically by the validation framework "
        "(`python/validation`). Each rule records its status, the number of "
        "records affected, a severity grade, and a recommended action.",
        "",
        f"**Overall gate:** {'FAIL - review required' if any_fail else 'PASS - safe to load'}",
        "",
        "---",
        "",
    ]
    report = "\n".join(header) + "\n\n".join(md_sections)
    VALIDATION_REPORT_MD.write_text(report, encoding="utf-8")
    logger.info("Validation report written to %s", VALIDATION_REPORT_MD)

    return {
        "sources": summaries,
        "any_fail": any_fail,
        "results_csv": str(VALIDATION_RESULTS_CSV),
        "report_md": str(VALIDATION_REPORT_MD),
    }
