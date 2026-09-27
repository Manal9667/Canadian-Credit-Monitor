"""Monitoring / anomaly engine.

Purpose: flag observations that deserve an analyst's attention. This is a
transparent, explainable statistical monitor - not a machine-learning model and
not a risk or fraud classifier. Every flag carries a plain-language reason.

Methods (all transparent):
  1. Rolling z-score   - value vs its own trailing mean/standard deviation.
  2. Percentage-change - period change vs the series' own typical change size.
  3. Historical range  - value in the extreme tail of its full history.

Language is deliberately neutral: "monitoring alert", "unusual movement",
"historical deviation", "requires investigation". Nothing here asserts a cause
or labels a real-world risk event.

Outputs:
    data/processed/monitoring_alerts.csv   latest-observation alerts (dashboard)
    data/processed/monitoring_history.csv  every flagged point over time
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..common.config import PROCESSED_DIR
from ..common.logging_utils import get_logger

logger = get_logger("analytics.anomaly_detection")

FACT_CSV = PROCESSED_DIR / "fact_observations.csv"
SERIES_CSV = PROCESSED_DIR / "dim_series.csv"
ALERTS_OUT = PROCESSED_DIR / "monitoring_alerts.csv"
HISTORY_OUT = PROCESSED_DIR / "monitoring_history.csv"

# Trailing window (observations) used for rolling statistics.
ROLLING_WINDOW = 12
MIN_HISTORY = 8
# z-score thresholds.
Z_MEDIUM = 2.0
Z_HIGH = 3.0
# Percentage-change alert: flag when a period change exceeds this many standard
# deviations of the series' own historical period changes.
PCT_CHANGE_SIGMA = 3.0
# Historical-range alert: flag values in the top/bottom this-percent tail.
TAIL_PCT = 2.5


def load_processed() -> pd.DataFrame:
    fact = pd.read_csv(FACT_CSV, parse_dates=["observation_date"])
    series = pd.read_csv(SERIES_CSV)
    df = fact.merge(series, on="series_id", how="left")
    return df.dropna(subset=["value"]).sort_values(
        ["series_id", "observation_date"]
    ).reset_index(drop=True)


def _classify(abs_z: float) -> str:
    if not np.isfinite(abs_z):
        return "NORMAL"
    if abs_z >= Z_HIGH:
        return "HIGH"
    if abs_z >= Z_MEDIUM:
        return "MEDIUM"
    return "NORMAL"


def detect_series(sub: pd.DataFrame) -> pd.DataFrame:
    """Compute per-observation monitoring signals for a single series."""
    sub = sub.sort_values("observation_date").copy()
    vals = sub["value"]

    # Trailing stats computed on data strictly before the current point to avoid
    # the current observation influencing its own baseline.
    prev = vals.shift(1)
    roll_mean = prev.rolling(ROLLING_WINDOW, min_periods=MIN_HISTORY).mean()
    roll_std = prev.rolling(ROLLING_WINDOW, min_periods=MIN_HISTORY).std()
    sub["rolling_mean"] = roll_mean.round(4)
    sub["rolling_std"] = roll_std.round(4)
    sub["zscore"] = ((vals - roll_mean) / roll_std.replace(0, np.nan)).round(3)

    # Period percentage change and its own historical volatility.
    pct = (100.0 * (vals - prev) / prev.abs().replace(0, np.nan))
    sub["pct_change"] = pct.round(4)
    pct_sigma = pct.expanding(min_periods=MIN_HISTORY).std()
    sub["pct_change_flag"] = (pct.abs() > (PCT_CHANGE_SIGMA * pct_sigma)) & pct_sigma.notna()

    # Historical-range (tail) flag using full-history percentiles.
    lo = np.nanpercentile(vals, TAIL_PCT)
    hi = np.nanpercentile(vals, 100 - TAIL_PCT)
    sub["tail_flag"] = (vals <= lo) | (vals >= hi)

    sub["severity"] = sub["zscore"].abs().apply(_classify)
    return sub


def _reason(row: pd.Series) -> str:
    reasons = []
    if row["severity"] in {"MEDIUM", "HIGH"} and pd.notna(row["zscore"]):
        direction = "above" if row["zscore"] > 0 else "below"
        reasons.append(
            f"latest value is {abs(row['zscore']):.2f} standard deviations {direction} "
            f"its trailing {ROLLING_WINDOW}-period average"
        )
    if bool(row.get("pct_change_flag")) and pd.notna(row["pct_change"]):
        reasons.append(
            f"period change of {row['pct_change']:.2f}% is unusually large for this series"
        )
    if bool(row.get("tail_flag")):
        reasons.append("value sits in the extreme tail of its full historical range")
    if not reasons:
        return "within normal historical range"
    return "; ".join(reasons)


def run() -> dict[str, Any]:
    """Run monitoring across all series; persist latest alerts and history."""
    df = load_processed()
    flagged = (
        df.groupby("series_id", group_keys=False)[df.columns.tolist()]
        .apply(detect_series)
        .reset_index(drop=True)
    )
    flagged["reason"] = flagged.apply(_reason, axis=1)

    keep_cols = [
        "series_id", "series_name", "category", "unit", "frequency",
        "observation_date", "value", "rolling_mean", "rolling_std", "zscore",
        "pct_change", "pct_change_flag", "tail_flag", "severity", "reason",
    ]
    flagged = flagged[keep_cols]

    # Any point that tripped at least one method, over the whole history.
    history = flagged[
        (flagged["severity"] != "NORMAL")
        | (flagged["pct_change_flag"])
        | (flagged["tail_flag"])
    ].copy()
    history.to_csv(HISTORY_OUT, index=False)

    # Latest observation per series -> the "requires investigation" list.
    latest = flagged.sort_values("observation_date").groupby("series_id").tail(1).copy()
    latest["is_alert"] = (
        (latest["severity"] != "NORMAL") | latest["pct_change_flag"] | latest["tail_flag"]
    )
    latest = latest.sort_values("zscore", key=lambda s: s.abs(), ascending=False)
    latest.to_csv(ALERTS_OUT, index=False)

    n_alerts = int(latest["is_alert"].sum())
    logger.info(
        "Monitoring complete: %s series scanned, %s latest-period alert(s), "
        "%s flagged points in history.",
        flagged["series_id"].nunique(), n_alerts, len(history),
    )
    return {
        "series_scanned": int(flagged["series_id"].nunique()),
        "latest_alerts": n_alerts,
        "history_flags": int(len(history)),
        "outputs": [ALERTS_OUT.name, HISTORY_OUT.name],
    }


if __name__ == "__main__":
    run()
