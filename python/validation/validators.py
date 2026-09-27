"""Reusable data-quality checks.

Each check operates on a long-format observations dataframe joined to its series
metadata (so every row carries its series_id, frequency, measure_type and unit)
and returns a `ValidationResult`. Results are severity-graded so downstream
tooling can decide what blocks a load versus what is merely informational.

Design principle: a check never mutates the data. It only inspects and reports.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

# Severity ordering used for summarising a report.
SEVERITY_ORDER = {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

# Expected spacing between observations, in days, per declared frequency.
FREQUENCY_DAYS = {"daily": 1, "weekly": 7, "monthly": 31, "quarterly": 92}
# Multiplier beyond which a gap is considered unexpected.
GAP_TOLERANCE = 1.6
# Days after which the newest observation is considered stale, per frequency.
STALE_DAYS = {"daily": 14, "weekly": 21, "monthly": 75, "quarterly": 200}


@dataclass
class ValidationResult:
    rule: str
    status: str  # PASS | WARN | FAIL
    records_affected: int
    severity: str  # INFO | LOW | MEDIUM | HIGH | CRITICAL
    recommended_action: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "status": self.status,
            "records_affected": self.records_affected,
            "severity": self.severity,
            "recommended_action": self.recommended_action,
            "details": "; ".join(f"{k}={v}" for k, v in self.details.items()),
        }


def check_required_columns(df: pd.DataFrame, required: list[str]) -> ValidationResult:
    missing = [c for c in required if c not in df.columns]
    if missing:
        return ValidationResult(
            rule="Schema: required columns present",
            status="FAIL",
            records_affected=len(missing),
            severity="CRITICAL",
            recommended_action=f"Restore missing columns before loading: {missing}",
            details={"missing_columns": missing},
        )
    return ValidationResult(
        rule="Schema: required columns present",
        status="PASS",
        records_affected=0,
        severity="INFO",
        recommended_action="None",
        details={"columns_checked": len(required)},
    )


def check_missing_values(df: pd.DataFrame) -> ValidationResult:
    n_missing = int(df["value"].isna().sum())
    if n_missing == 0:
        status, severity, action = "PASS", "INFO", "None"
    else:
        status, severity = "WARN", "LOW"
        action = "Confirm these are genuine source suppressions/holidays, not load errors."
    return ValidationResult(
        rule="Missing observations (null values)",
        status=status,
        records_affected=n_missing,
        severity=severity,
        recommended_action=action,
        details={"pct_missing": round(100 * n_missing / max(len(df), 1), 3)},
    )


def check_duplicates(df: pd.DataFrame) -> ValidationResult:
    dup_mask = df.duplicated(subset=["series_id", "observation_date"], keep=False)
    n_dup = int(dup_mask.sum())
    if n_dup == 0:
        return ValidationResult(
            rule="Duplicate series/date combinations",
            status="PASS",
            records_affected=0,
            severity="INFO",
            recommended_action="None",
        )
    return ValidationResult(
        rule="Duplicate series/date combinations",
        status="FAIL",
        records_affected=n_dup,
        severity="HIGH",
        recommended_action="De-duplicate on (series_id, observation_date) before loading.",
        details={"affected_series": df.loc[dup_mask, "series_id"].nunique()},
    )


def check_invalid_dates(df: pd.DataFrame) -> ValidationResult:
    parsed = pd.to_datetime(df["observation_date"], errors="coerce")
    n_bad = int(parsed.isna().sum())
    status = "PASS" if n_bad == 0 else "FAIL"
    severity = "INFO" if n_bad == 0 else "HIGH"
    return ValidationResult(
        rule="Invalid / unparseable dates",
        status=status,
        records_affected=n_bad,
        severity=severity,
        recommended_action="None" if n_bad == 0 else "Investigate source date formatting.",
    )


def check_future_dates(df: pd.DataFrame, as_of: pd.Timestamp | None = None) -> ValidationResult:
    as_of = as_of or pd.Timestamp.utcnow().tz_localize(None)
    parsed = pd.to_datetime(df["observation_date"], errors="coerce")
    n_future = int((parsed > as_of).sum())
    status = "PASS" if n_future == 0 else "WARN"
    severity = "INFO" if n_future == 0 else "MEDIUM"
    return ValidationResult(
        rule="Observation dates in the future",
        status=status,
        records_affected=n_future,
        severity=severity,
        recommended_action="None" if n_future == 0 else "Reject future-dated observations.",
    )


def check_negative_balances(df: pd.DataFrame) -> ValidationResult:
    """Balances must be non-negative. Rates may legitimately be low but not < 0
    for the products tracked here, so negatives are flagged for review."""
    mask = df["value"].notna() & (df["value"] < 0)
    n_neg = int(mask.sum())
    status = "PASS" if n_neg == 0 else "WARN"
    severity = "INFO" if n_neg == 0 else "MEDIUM"
    return ValidationResult(
        rule="Negative values in balance/rate series",
        status=status,
        records_affected=n_neg,
        severity=severity,
        recommended_action="None" if n_neg == 0 else "Review sign of affected observations.",
        details={"affected_series": df.loc[mask, "series_id"].nunique() if n_neg else 0},
    )


def check_unit_consistency(df: pd.DataFrame) -> ValidationResult:
    """Each series must carry exactly one unit across all its observations."""
    if "unit" not in df.columns:
        return ValidationResult(
            rule="Unit consistency per series",
            status="WARN",
            records_affected=0,
            severity="LOW",
            recommended_action="Unit metadata not joined; cannot verify.",
        )
    per_series = df.groupby("series_id")["unit"].nunique()
    offenders = per_series[per_series > 1]
    n = int(offenders.sum())
    status = "PASS" if offenders.empty else "FAIL"
    severity = "INFO" if offenders.empty else "HIGH"
    return ValidationResult(
        rule="Unit consistency per series",
        status=status,
        records_affected=n,
        severity=severity,
        recommended_action="None" if offenders.empty else "Reconcile mixed units per series.",
        details={"series_with_mixed_units": list(offenders.index)} if not offenders.empty else {},
    )


def check_frequency_gaps(df: pd.DataFrame) -> ValidationResult:
    """Flag unexpected gaps for weekly/monthly/quarterly series.

    Daily series are excluded because weekend/holiday gaps are normal and not a
    quality problem.
    """
    total_gaps = 0
    affected: dict[str, int] = {}
    dfx = df.copy()
    dfx["observation_date"] = pd.to_datetime(dfx["observation_date"], errors="coerce")
    for series_id, grp in dfx.dropna(subset=["observation_date"]).groupby("series_id"):
        freq = grp["frequency"].iloc[0] if "frequency" in grp.columns else None
        if freq not in {"weekly", "monthly", "quarterly"}:
            continue
        dates = grp["observation_date"].sort_values()
        diffs = dates.diff().dropna().dt.days
        threshold = FREQUENCY_DAYS[freq] * GAP_TOLERANCE
        gaps = int((diffs > threshold).sum())
        if gaps:
            affected[series_id] = gaps
            total_gaps += gaps
    status = "PASS" if total_gaps == 0 else "WARN"
    severity = "INFO" if total_gaps == 0 else "LOW"
    return ValidationResult(
        rule="Unexpected frequency gaps",
        status=status,
        records_affected=total_gaps,
        severity=severity,
        recommended_action="None" if total_gaps == 0 else "Review gaps; may reflect source revisions/holidays.",
        details={"series_with_gaps": len(affected)} if affected else {},
    )


def check_extreme_values(df: pd.DataFrame, z_threshold: float = 6.0) -> ValidationResult:
    """Informational scan for statistically extreme points (|z| > threshold).

    This is a *data-quality* smell test (e.g., a stray 10x value from a unit
    error), not the analytical monitoring engine. A high threshold keeps it
    conservative so normal market moves are not flagged here.
    """
    total = 0
    affected: dict[str, int] = {}
    for series_id, grp in df.groupby("series_id"):
        vals = pd.to_numeric(grp["value"], errors="coerce").dropna()
        if len(vals) < 12 or vals.std(ddof=0) == 0:
            continue
        z = (vals - vals.mean()) / vals.std(ddof=0)
        n = int((z.abs() > z_threshold).sum())
        if n:
            affected[series_id] = n
            total += n
    status = "PASS" if total == 0 else "WARN"
    severity = "INFO" if total == 0 else "LOW"
    return ValidationResult(
        rule=f"Extreme values (|z| > {z_threshold})",
        status=status,
        records_affected=total,
        severity=severity,
        recommended_action="None" if total == 0 else "Confirm extreme points are real, not unit errors.",
        details={"series_flagged": len(affected)} if affected else {},
    )


def check_stale_data(df: pd.DataFrame, as_of: pd.Timestamp | None = None) -> ValidationResult:
    """Flag series whose most recent observation is older than expected."""
    as_of = as_of or pd.Timestamp.utcnow().tz_localize(None)
    dfx = df.copy()
    dfx["observation_date"] = pd.to_datetime(dfx["observation_date"], errors="coerce")
    stale: dict[str, int] = {}
    for series_id, grp in dfx.dropna(subset=["observation_date"]).groupby("series_id"):
        freq = grp["frequency"].iloc[0] if "frequency" in grp.columns else "monthly"
        max_date = grp["observation_date"].max()
        age = (as_of - max_date).days
        if age > STALE_DAYS.get(freq, 75):
            stale[series_id] = age
    status = "PASS" if not stale else "WARN"
    severity = "INFO" if not stale else "MEDIUM"
    return ValidationResult(
        rule="Stale data (latest observation older than expected)",
        status=status,
        records_affected=len(stale),
        severity=severity,
        recommended_action="None" if not stale else "Confirm source has not paused publication.",
        details={"stale_series": len(stale)} if stale else {},
    )


# The default battery run against every source.
DEFAULT_CHECKS = [
    lambda df: check_required_columns(df, ["source", "series_id", "observation_date", "value"]),
    check_missing_values,
    check_duplicates,
    check_invalid_dates,
    check_future_dates,
    check_negative_balances,
    check_unit_consistency,
    check_frequency_gaps,
    check_extreme_values,
    check_stale_data,
]


def run_checks(df: pd.DataFrame, checks=None) -> list[ValidationResult]:
    """Run a battery of checks, catching per-check failures gracefully."""
    checks = checks or DEFAULT_CHECKS
    results: list[ValidationResult] = []
    for check in checks:
        try:
            results.append(check(df))
        except Exception as exc:  # a broken check must not crash the report
            results.append(
                ValidationResult(
                    rule=getattr(check, "__name__", "unknown check"),
                    status="FAIL",
                    records_affected=0,
                    severity="HIGH",
                    recommended_action=f"Check raised an exception: {exc}",
                )
            )
    return results


def worst_severity(results: list[ValidationResult]) -> str:
    if not results:
        return "INFO"
    return max(results, key=lambda r: SEVERITY_ORDER.get(r.severity, 0)).severity
