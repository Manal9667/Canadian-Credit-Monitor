"""Analytical metrics layer.

Computes, per series, the standard set of decision-support metrics from the
processed fact table. This mirrors the SQL analytical views so the two can be
reconciled (see analytics/reconciliation via db.duckdb_runner and Phase 22).

Outputs:
    data/processed/metrics_timeseries.csv  per observation, with changes + rolling
    data/processed/metrics_summary.csv     one row per series: latest snapshot

Metric definitions are documented in documentation/methodology.md. Metrics that
are not statistically appropriate for a given series are left null rather than
forced (e.g. year-over-year is only computed for regularly-spaced monthly and
quarterly series).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..common.config import PROCESSED_DIR
from ..common.logging_utils import get_logger

logger = get_logger("analytics.metrics")

FACT_CSV = PROCESSED_DIR / "fact_observations.csv"
SERIES_CSV = PROCESSED_DIR / "dim_series.csv"

TIMESERIES_OUT = PROCESSED_DIR / "metrics_timeseries.csv"
SUMMARY_OUT = PROCESSED_DIR / "metrics_summary.csv"

# Number of observations that make up one year, by declared frequency.
PERIODS_PER_YEAR = {"monthly": 12, "quarterly": 4, "weekly": 52}
# Rolling windows (in observations) used for the moving averages.
ROLLING_SHORT = 3
ROLLING_LONG = 12


def load_processed() -> pd.DataFrame:
    """Load the fact table joined to series metadata, sorted for windowing."""
    fact = pd.read_csv(FACT_CSV, parse_dates=["observation_date"])
    series = pd.read_csv(SERIES_CSV)
    df = fact.merge(series, on="series_id", how="left", suffixes=("", "_dim"))
    df = df.dropna(subset=["value"])
    return df.sort_values(["series_id", "observation_date"]).reset_index(drop=True)


def _pct_change(curr: pd.Series, base: pd.Series) -> pd.Series:
    """Percentage change guarding against divide-by-zero."""
    base_safe = base.replace(0, np.nan)
    return (100.0 * (curr - base) / base_safe.abs()).round(4)


def compute_timeseries(df: pd.DataFrame) -> pd.DataFrame:
    """Per-observation metrics: previous value, changes, rolling averages, YoY."""
    out = df[[
        "series_id", "series_name", "category", "subcategory",
        "frequency", "measure_type", "unit", "observation_date", "value",
    ]].copy()

    grp = out.groupby("series_id", sort=False)

    out["prev_value"] = grp["value"].shift(1)
    out["abs_change"] = out["value"] - out["prev_value"]
    out["pct_change"] = _pct_change(out["value"], out["prev_value"])

    # Rolling averages over trailing N observations (min_periods=1 so early
    # points still get a partial average, matching the SQL ROWS frame).
    out["rolling_3_period_avg"] = (
        grp["value"].transform(lambda s: s.rolling(ROLLING_SHORT, min_periods=1).mean()).round(4)
    )
    out["rolling_12_period_avg"] = (
        grp["value"].transform(lambda s: s.rolling(ROLLING_LONG, min_periods=1).mean()).round(4)
    )

    # Year-over-year: only for regularly spaced monthly/quarterly series.
    def _yoy(sub: pd.DataFrame) -> pd.Series:
        freq = sub["frequency"].iloc[0]
        periods = PERIODS_PER_YEAR.get(freq)
        if freq not in {"monthly", "quarterly"} or periods is None:
            return pd.Series(np.nan, index=sub.index)
        return sub["value"].shift(periods)

    out["value_year_ago"] = grp[["value", "frequency"]].apply(
        lambda sub: _yoy(sub)
    ).reset_index(level=0, drop=True)
    out["yoy_abs_change"] = out["value"] - out["value_year_ago"]
    out["yoy_pct_change"] = _pct_change(out["value"], out["value_year_ago"])

    return out


def _percentile_rank(series_values: np.ndarray, latest: float) -> float:
    """Percentile rank of the latest value within the series' own history."""
    n = len(series_values)
    if n == 0:
        return float("nan")
    return round(100.0 * np.sum(series_values <= latest) / n, 2)


def compute_summary(df: pd.DataFrame, ts: pd.DataFrame) -> pd.DataFrame:
    """One row per series: latest snapshot with full-history context."""
    rows: list[dict[str, Any]] = []
    ts_by_series = {sid: sub for sid, sub in ts.groupby("series_id", sort=False)}

    for series_id, sub in df.groupby("series_id", sort=False):
        vals = sub["value"].to_numpy(dtype=float)
        latest_row = sub.iloc[-1]
        latest = float(latest_row["value"])
        hist_avg = float(np.mean(vals))
        hist_std = float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0

        tsub = ts_by_series[series_id].iloc[-1]
        zscore = (latest - hist_avg) / hist_std if hist_std else np.nan

        rows.append({
            "series_id": series_id,
            "series_name": latest_row["series_name"],
            "category": latest_row["category"],
            "subcategory": latest_row["subcategory"],
            "unit": latest_row["unit"],
            "frequency": latest_row["frequency"],
            "measure_type": latest_row["measure_type"],
            "latest_date": latest_row["observation_date"].date().isoformat(),
            "current_value": round(latest, 4),
            "previous_value": _round_or_none(tsub["prev_value"]),
            "abs_change": _round_or_none(tsub["abs_change"]),
            "pct_change": _round_or_none(tsub["pct_change"]),
            "yoy_abs_change": _round_or_none(tsub["yoy_abs_change"]),
            "yoy_pct_change": _round_or_none(tsub["yoy_pct_change"]),
            "rolling_3_period_avg": _round_or_none(tsub["rolling_3_period_avg"]),
            "rolling_12_period_avg": _round_or_none(tsub["rolling_12_period_avg"]),
            "hist_min": round(float(np.min(vals)), 4),
            "hist_max": round(float(np.max(vals)), 4),
            "hist_avg": round(hist_avg, 4),
            "hist_stddev": round(hist_std, 4),
            "deviation_from_avg": round(latest - hist_avg, 4),
            "latest_zscore": round(float(zscore), 3) if pd.notna(zscore) else None,
            "percentile_rank": _percentile_rank(vals, latest),
            "n_obs": int(len(vals)),
        })

    return pd.DataFrame(rows)


def _round_or_none(x: Any, ndigits: int = 4):
    return round(float(x), ndigits) if pd.notna(x) else None


def run() -> dict[str, Any]:
    """Compute and persist the metrics layer."""
    df = load_processed()
    ts = compute_timeseries(df)
    summary = compute_summary(df, ts)

    ts.to_csv(TIMESERIES_OUT, index=False)
    summary.to_csv(SUMMARY_OUT, index=False)

    logger.info(
        "Metrics computed: %s timeseries rows, %s series summarised -> %s, %s",
        len(ts), len(summary), TIMESERIES_OUT.name, SUMMARY_OUT.name,
    )
    return {
        "timeseries_rows": int(len(ts)),
        "series_summarised": int(len(summary)),
        "outputs": [TIMESERIES_OUT.name, SUMMARY_OUT.name],
    }


if __name__ == "__main__":
    run()
