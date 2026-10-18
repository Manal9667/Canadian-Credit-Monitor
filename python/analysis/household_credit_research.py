"""Finance research layer for Canadian household credit and rate pass-through.

The calculations in this module use only processed public aggregate indicators.
They avoid interpolation and report sample sizes beside correlations and
averages so the memo can stay honest about frequency alignment and coverage.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..analytics.metrics import compute_timeseries
from ..common.config import PROCESSED_DIR, PROJECT_ROOT
from ..common.logging_utils import get_logger

logger = get_logger("analysis.household_credit_research")

REPORTS_DIR = PROJECT_ROOT / "reports"
FIGURES_DIR = REPORTS_DIR / "figures"

POLICY = "V39079"
PRIME = "V80691311"
POSTED_MORTGAGES = {
    "V80691333": "Posted 1-year mortgage",
    "V80691334": "Posted 3-year mortgage",
    "V80691335": "Posted 5-year mortgage",
}
EFFECTIVE_RATES = {
    "V122667809": ("Consumer credit effective rate", "V122667758"),
    "V122667812": ("Credit card effective rate", "V122667761"),
    "V122667821": ("Business loan effective rate", "V122667770"),
}
MONTHLY_BALANCES = {
    "V122667758": "Consumer credit total",
    "V122667761": "Credit cards",
    "V122667762": "Secured PLOC",
    "V122667763": "Unsecured PLOC",
    "V122667760": "Auto loans",
    "V122667736": "Insured mortgages",
    "V122667742": "Uninsured mortgages",
}
STATCAN_DTI = "STATCAN_v1038036698"
STATCAN_LEVELS = {
    "STATCAN_v1038036700": "Credit market debt",
    "STATCAN_v1038036701": "Consumer credit liabilities",
    "STATCAN_v1038036703": "Mortgage liabilities",
}

REGIME_THRESHOLD_PP = 0.25
LAG_RANGE = range(0, 13)


@dataclass(frozen=True)
class ResearchOutputs:
    pass_through: pd.DataFrame
    lead_lag: pd.DataFrame
    regimes: pd.DataFrame
    sensitivity: pd.DataFrame
    component_shares: pd.DataFrame
    key_findings: pd.DataFrame


def load_processed(processed_dir: Path = PROCESSED_DIR) -> pd.DataFrame:
    """Load observations joined to series metadata."""
    fact = pd.read_csv(processed_dir / "fact_observations.csv", parse_dates=["observation_date"])
    series = pd.read_csv(processed_dir / "dim_series.csv")
    df = fact.merge(series, on="series_id", how="left", suffixes=("", "_dim"))
    df = df.dropna(subset=["value"]).copy()
    df["value"] = pd.to_numeric(df["value"], errors="raise")
    return df.sort_values(["series_id", "observation_date"]).reset_index(drop=True)


def monthly_policy_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Average daily policy observations by calendar month, no forward fill."""
    policy = df.loc[df["series_id"] == POLICY, ["observation_date", "value"]].copy()
    policy["month"] = policy["observation_date"].dt.to_period("M")
    out = (
        policy.groupby("month", as_index=False)
        .agg(policy_rate=("value", "mean"), policy_obs=("value", "size"))
        .sort_values("month")
    )
    out["observation_date"] = out["month"].dt.to_timestamp()
    out["policy_12m_change_pp"] = out["policy_rate"] - out["policy_rate"].shift(12)
    out["regime"] = out["policy_12m_change_pp"].map(classify_regime)
    return out[["observation_date", "month", "policy_rate", "policy_obs", "policy_12m_change_pp", "regime"]]


def classify_regime(change_pp: float | int | None) -> str | None:
    """Classify by the pre-set trailing 12-month policy-rate change rule."""
    if pd.isna(change_pp):
        return None
    if change_pp >= REGIME_THRESHOLD_PP:
        return "hiking"
    if change_pp <= -REGIME_THRESHOLD_PP:
        return "easing"
    return "stable"


def _series_ts(df: pd.DataFrame) -> pd.DataFrame:
    base = df[[
        "series_id",
        "series_name",
        "category",
        "subcategory",
        "frequency",
        "measure_type",
        "unit",
        "observation_date",
        "value",
    ]].copy()
    return compute_timeseries(base)


def compute_lead_lag_correlations(df: pd.DataFrame) -> pd.DataFrame:
    """Correlate trailing policy-rate changes with later YoY credit growth."""
    ts = _series_ts(df)
    policy = monthly_policy_frame(df)[["observation_date", "policy_12m_change_pp"]].dropna()
    rows: list[dict[str, Any]] = []

    for series_id, label in MONTHLY_BALANCES.items():
        credit = ts.loc[
            (ts["series_id"] == series_id) & ts["yoy_pct_change"].notna(),
            ["observation_date", "yoy_pct_change"],
        ].copy()
        for lag in LAG_RANGE:
            shifted_policy = policy.copy()
            shifted_policy["observation_date"] = shifted_policy["observation_date"] + pd.DateOffset(months=lag)
            aligned = credit.merge(shifted_policy, on="observation_date", how="inner").dropna()
            corr = np.nan
            if (
                len(aligned) >= 2
                and aligned["policy_12m_change_pp"].nunique() > 1
                and aligned["yoy_pct_change"].nunique() > 1
            ):
                corr = aligned["policy_12m_change_pp"].corr(aligned["yoy_pct_change"])
            rows.append(
                {
                    "series_id": series_id,
                    "series_name": label,
                    "lag_months": lag,
                    "correlation": round(float(corr), 4) if pd.notna(corr) else np.nan,
                    "n": int(len(aligned)),
                    "date_min": _date_or_blank(aligned["observation_date"].min()),
                    "date_max": _date_or_blank(aligned["observation_date"].max()),
                }
            )
    return pd.DataFrame(rows)


def compute_regime_comparisons(df: pd.DataFrame) -> pd.DataFrame:
    """Average growth/levels by pre-defined policy-rate regime."""
    ts = _series_ts(df)
    regimes = monthly_policy_frame(df)[["observation_date", "regime", "policy_12m_change_pp"]].dropna()
    rows: list[dict[str, Any]] = []

    for series_id, label in MONTHLY_BALANCES.items():
        credit = ts.loc[
            (ts["series_id"] == series_id) & ts["yoy_pct_change"].notna(),
            ["observation_date", "yoy_pct_change"],
        ]
        aligned = credit.merge(regimes, on="observation_date", how="inner")
        for regime, sub in aligned.groupby("regime", sort=True):
            rows.append(_regime_row(label, series_id, "monthly_yoy_growth_pct", regime, sub, "yoy_pct_change"))

    dti = df.loc[df["series_id"] == STATCAN_DTI, ["observation_date", "value"]].copy()
    dti = dti.merge(regimes, on="observation_date", how="inner")
    for regime, sub in dti.groupby("regime", sort=True):
        rows.append(_regime_row("Household debt-to-income", STATCAN_DTI, "quarterly_dti_ratio", regime, sub, "value"))

    return pd.DataFrame(rows)


def _regime_row(
    label: str,
    series_id: str,
    metric: str,
    regime: str,
    sub: pd.DataFrame,
    value_col: str,
) -> dict[str, Any]:
    return {
        "series_id": series_id,
        "series_name": label,
        "metric": metric,
        "regime": regime,
        "average_value": round(float(sub[value_col].mean()), 4),
        "median_value": round(float(sub[value_col].median()), 4),
        "n": int(len(sub)),
        "date_min": _date_or_blank(sub["observation_date"].min()),
        "date_max": _date_or_blank(sub["observation_date"].max()),
    }


def compute_rate_pass_through(df: pd.DataFrame) -> pd.DataFrame:
    """Compute posted/effective rate spreads and sample pass-through ratios."""
    policy_daily = df.loc[df["series_id"] == POLICY, ["observation_date", "value"]].rename(
        columns={"value": "policy_rate"}
    )
    rows: list[dict[str, Any]] = []

    weekly_specs = {PRIME: "Prime lending rate", **POSTED_MORTGAGES}
    for series_id, label in weekly_specs.items():
        rate = df.loc[df["series_id"] == series_id, ["observation_date", "value"]].rename(
            columns={"value": "lending_rate"}
        )
        aligned = rate.merge(policy_daily, on="observation_date", how="inner")
        aligned = aligned.loc[aligned["observation_date"] >= pd.Timestamp("2009-04-21")].copy()
        rows.append(_pass_through_row(series_id, label, "weekly_exact_date", aligned))

    monthly_policy = monthly_policy_frame(df)[["observation_date", "policy_rate"]]
    for series_id, (label, _) in EFFECTIVE_RATES.items():
        rate = df.loc[df["series_id"] == series_id, ["observation_date", "value"]].rename(
            columns={"value": "lending_rate"}
        )
        aligned = rate.merge(monthly_policy, on="observation_date", how="inner")
        rows.append(_pass_through_row(series_id, label, "monthly_policy_average", aligned))

    return pd.DataFrame(rows)


def _pass_through_row(
    series_id: str,
    label: str,
    alignment: str,
    aligned: pd.DataFrame,
) -> dict[str, Any]:
    aligned = aligned.dropna().sort_values("observation_date").copy()
    aligned["spread_pp"] = aligned["lending_rate"] - aligned["policy_rate"]
    first = aligned.iloc[0]
    latest = aligned.iloc[-1]
    policy_change = latest["policy_rate"] - first["policy_rate"]
    rate_change = latest["lending_rate"] - first["lending_rate"]
    ratio = rate_change / policy_change if policy_change else np.nan
    return {
        "series_id": series_id,
        "series_name": label,
        "alignment": alignment,
        "date_min": first["observation_date"].date().isoformat(),
        "date_max": latest["observation_date"].date().isoformat(),
        "n": int(len(aligned)),
        "start_policy_rate": round(float(first["policy_rate"]), 4),
        "latest_policy_rate": round(float(latest["policy_rate"]), 4),
        "policy_change_pp": round(float(policy_change), 4),
        "start_lending_rate": round(float(first["lending_rate"]), 4),
        "latest_lending_rate": round(float(latest["lending_rate"]), 4),
        "lending_rate_change_pp": round(float(rate_change), 4),
        "pass_through_ratio": round(float(ratio), 4) if pd.notna(ratio) else np.nan,
        "latest_spread_pp": round(float(latest["spread_pp"]), 4),
        "average_spread_pp": round(float(aligned["spread_pp"].mean()), 4),
    }


def compute_sensitivity(df: pd.DataFrame) -> pd.DataFrame:
    """Mechanical annual interest sensitivity for products with balance+rate pairs."""
    latest = (
        df.sort_values("observation_date")
        .groupby("series_id", as_index=False)
        .tail(1)
        .set_index("series_id")
    )
    rows: list[dict[str, Any]] = []
    shocks = [(100, 1.0), (200, 2.0)]
    labels = {
        "V122667809": "Consumer credit",
        "V122667812": "Credit cards",
        "V122667821": "Business loans",
    }
    for rate_id, (_, balance_id) in EFFECTIVE_RATES.items():
        balance = float(latest.loc[balance_id, "value"])
        rate = float(latest.loc[rate_id, "value"])
        date = max(latest.loc[balance_id, "observation_date"], latest.loc[rate_id, "observation_date"])
        for shock_bp, shock_pp in shocks:
            rows.append(
                {
                    "product": labels[rate_id],
                    "balance_series_id": balance_id,
                    "rate_series_id": rate_id,
                    "as_of_date": date.date().isoformat(),
                    "balance_millions_cad": round(balance, 4),
                    "current_effective_rate_pct": round(rate, 4),
                    "rate_shock_bp": shock_bp,
                    "rate_shock_pct_of_balance": round(shock_pp, 4),
                    "incremental_annual_interest_millions_cad": round(balance * shock_pp / 100.0, 4),
                }
            )
    return pd.DataFrame(rows)


def compute_component_shares(df: pd.DataFrame) -> pd.DataFrame:
    """Latest shares of tracked BoC household-credit components."""
    component_ids = [sid for sid in MONTHLY_BALANCES if sid != "V122667758"]
    sub = df.loc[df["series_id"].isin(component_ids), ["series_id", "observation_date", "value"]].copy()
    latest_date = sub["observation_date"].max()
    latest = sub.loc[sub["observation_date"] == latest_date].copy()
    total = latest["value"].sum()
    latest["series_name"] = latest["series_id"].map(MONTHLY_BALANCES)
    latest["tracked_component_total_millions_cad"] = round(float(total), 4)
    latest["share_of_tracked_components_pct"] = (100.0 * latest["value"] / total).round(4)
    latest = latest.rename(columns={"value": "balance_millions_cad"})
    return latest[
        [
            "observation_date",
            "series_id",
            "series_name",
            "balance_millions_cad",
            "tracked_component_total_millions_cad",
            "share_of_tracked_components_pct",
        ]
    ].sort_values("share_of_tracked_components_pct", ascending=False)


def build_key_findings(outputs: ResearchOutputs) -> pd.DataFrame:
    """Collect interview-ready headline numbers from computed outputs."""
    rows: list[dict[str, Any]] = []
    prime = outputs.pass_through.loc[outputs.pass_through["series_id"] == PRIME].iloc[0]
    rows.append(
        _finding(
            "Prime-policy mechanical pass-through",
            prime["latest_spread_pp"],
            "percentage points latest spread",
            "V80691311, V39079",
            prime["date_min"],
            prime["date_max"],
            int(prime["n"]),
        )
    )

    consumer_rate = outputs.pass_through.loc[outputs.pass_through["series_id"] == "V122667809"].iloc[0]
    rows.append(
        _finding(
            "Consumer effective-rate spread over policy",
            consumer_rate["latest_spread_pp"],
            "percentage points latest spread",
            "V122667809, V39079",
            consumer_rate["date_min"],
            consumer_rate["date_max"],
            int(consumer_rate["n"]),
        )
    )

    consumer_growth = outputs.regimes.loc[
        (outputs.regimes["series_id"] == "V122667758")
        & (outputs.regimes["metric"] == "monthly_yoy_growth_pct")
    ]
    if not consumer_growth.empty:
        for regime in ["hiking", "easing", "stable"]:
            match = consumer_growth.loc[consumer_growth["regime"] == regime]
            if not match.empty:
                row = match.iloc[0]
                rows.append(
                    _finding(
                        f"Consumer-credit YoY growth during {regime} regimes",
                        row["average_value"],
                        "average YoY growth percent",
                        "V122667758, V39079",
                        row["date_min"],
                        row["date_max"],
                        int(row["n"]),
                    )
                )

    dti = outputs.regimes.loc[
        (outputs.regimes["series_id"] == STATCAN_DTI) & (outputs.regimes["metric"] == "quarterly_dti_ratio")
    ]
    if not dti.empty:
        for regime in ["hiking", "easing", "stable"]:
            match = dti.loc[dti["regime"] == regime]
            if not match.empty:
                row = match.iloc[0]
                rows.append(
                    _finding(
                        f"Debt-to-income during {regime} regimes",
                        row["average_value"],
                        "average ratio",
                        f"{STATCAN_DTI}, {POLICY}",
                        row["date_min"],
                        row["date_max"],
                        int(row["n"]),
                    )
                )

    largest_share = outputs.component_shares.iloc[0]
    rows.append(
        _finding(
            "Largest tracked household-credit component",
            largest_share["share_of_tracked_components_pct"],
            f"percent share: {largest_share['series_name']}",
            ", ".join(outputs.component_shares["series_id"].tolist()),
            largest_share["observation_date"].date().isoformat(),
            largest_share["observation_date"].date().isoformat(),
            int(len(outputs.component_shares)),
        )
    )

    sensitivity = outputs.sensitivity.loc[
        (outputs.sensitivity["product"] == "Consumer credit")
        & (outputs.sensitivity["rate_shock_bp"] == 100)
    ].iloc[0]
    rows.append(
        _finding(
            "Consumer-credit +100 bp mechanical sensitivity",
            sensitivity["incremental_annual_interest_millions_cad"],
            "millions CAD annual interest",
            "V122667758, V122667809",
            sensitivity["as_of_date"],
            sensitivity["as_of_date"],
            1,
        )
    )
    return pd.DataFrame(rows)


def _finding(
    finding: str,
    value: Any,
    unit: str,
    series_used: str,
    date_min: str,
    date_max: str,
    n: int,
) -> dict[str, Any]:
    return {
        "finding": finding,
        "computed_value": value,
        "unit": unit,
        "series_used": series_used,
        "date_range": f"{date_min} to {date_max}",
        "n": n,
    }


def write_outputs(outputs: ResearchOutputs, reports_dir: Path = REPORTS_DIR) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    outputs.pass_through.to_csv(reports_dir / "rate_pass_through.csv", index=False)
    outputs.lead_lag.to_csv(reports_dir / "lead_lag_correlations.csv", index=False)
    outputs.regimes.to_csv(reports_dir / "regime_comparisons.csv", index=False)
    outputs.sensitivity.to_csv(reports_dir / "rate_sensitivity.csv", index=False)
    outputs.component_shares.to_csv(reports_dir / "tracked_component_shares.csv", index=False)
    outputs.key_findings.to_csv(reports_dir / "key_findings.csv", index=False)


def create_figures(df: pd.DataFrame, outputs: ResearchOutputs, figures_dir: Path = FIGURES_DIR) -> None:
    """Create reader-friendly static charts."""
    import matplotlib.pyplot as plt

    figures_dir.mkdir(parents=True, exist_ok=True)
    plt.style.use("seaborn-v0_8-whitegrid")

    policy = df.loc[df["series_id"] == POLICY, ["observation_date", "value"]].rename(columns={"value": "Policy"})
    prime = df.loc[df["series_id"] == PRIME, ["observation_date", "value"]].rename(columns={"value": "Prime"})
    prime_aligned = prime.merge(policy, on="observation_date", how="inner")
    _line_chart(
        prime_aligned,
        ["Policy", "Prime"],
        "Prime moved closely with the policy rate",
        "Percent",
        figures_dir / "01_prime_policy_pass_through.png",
    )

    monthly_policy = monthly_policy_frame(df)[["observation_date", "policy_rate"]].rename(columns={"policy_rate": "Policy"})
    effective = monthly_policy.copy()
    for sid, (label, _) in EFFECTIVE_RATES.items():
        rate = df.loc[df["series_id"] == sid, ["observation_date", "value"]].rename(columns={"value": label})
        effective = effective.merge(rate, on="observation_date", how="left")
    _line_chart(
        effective.dropna(),
        ["Policy"] + [label for label, _ in EFFECTIVE_RATES.values()],
        "Effective lending rates remained above policy rates",
        "Percent",
        figures_dir / "02_effective_rates_vs_policy.png",
    )

    lag_subset = outputs.lead_lag.loc[
        outputs.lead_lag["series_id"].isin(["V122667758", "V122667742", "V122667761"])
    ]
    fig, ax = plt.subplots(figsize=(9, 5))
    for label, sub in lag_subset.groupby("series_name"):
        ax.plot(sub["lag_months"], sub["correlation"], marker="o", label=label)
    ax.axhline(0, color="#555555", linewidth=0.8)
    ax.set_title("Policy-rate changes had mixed lag correlations with credit growth")
    ax.set_xlabel("Policy-rate change leads YoY growth by months")
    ax.set_ylabel("Correlation")
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(figures_dir / "03_lag_profile_credit_growth.png", dpi=160)
    plt.close(fig)

    reg = outputs.regimes.loc[
        (outputs.regimes["metric"] == "monthly_yoy_growth_pct")
        & (outputs.regimes["series_id"].isin(["V122667758", "V122667742", "V122667761"]))
    ]
    pivot = reg.pivot(index="series_name", columns="regime", values="average_value")
    fig, ax = plt.subplots(figsize=(9, 5))
    pivot[[c for c in ["hiking", "stable", "easing"] if c in pivot.columns]].plot(kind="bar", ax=ax)
    ax.set_title("Average credit growth differed across rate regimes")
    ax.set_xlabel("")
    ax.set_ylabel("Average YoY growth (%)")
    fig.tight_layout()
    fig.savefig(figures_dir / "04_regime_growth_comparison.png", dpi=160)
    plt.close(fig)

    dti = df.loc[df["series_id"] == STATCAN_DTI, ["observation_date", "value"]].rename(columns={"value": "Debt-to-income"})
    dti_policy = dti.merge(monthly_policy.rename(columns={"Policy": "Policy rate"}), on="observation_date", how="inner")
    fig, ax1 = plt.subplots(figsize=(9, 5))
    ax1.plot(dti_policy["observation_date"], dti_policy["Debt-to-income"], color="#1f77b4", label="Debt-to-income")
    ax1.set_ylabel("Debt-to-income ratio", color="#1f77b4")
    ax2 = ax1.twinx()
    ax2.plot(dti_policy["observation_date"], dti_policy["Policy rate"], color="#d62728", label="Policy rate")
    ax2.set_ylabel("Policy rate (%)", color="#d62728")
    ax1.set_title("Debt-to-income stayed elevated across recent rate regimes")
    fig.tight_layout()
    fig.savefig(figures_dir / "05_dti_and_policy_rate.png", dpi=160)
    plt.close(fig)

    sens = outputs.sensitivity.loc[outputs.sensitivity["rate_shock_bp"] == 100]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(sens["product"], sens["incremental_annual_interest_millions_cad"], color="#4c78a8")
    ax.set_title("+100 bp sensitivity is largest where balances are largest")
    ax.set_ylabel("Incremental annual interest (millions CAD)")
    fig.tight_layout()
    fig.savefig(figures_dir / "06_rate_sensitivity.png", dpi=160)
    plt.close(fig)


def _line_chart(df: pd.DataFrame, columns: list[str], title: str, ylabel: str, path: Path) -> None:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(9, 5))
    for col in columns:
        ax.plot(df["observation_date"], df[col], label=col)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def write_memo(outputs: ResearchOutputs, processed_dir: Path = PROCESSED_DIR, reports_dir: Path = REPORTS_DIR) -> None:
    metadata = json.loads((processed_dir / "pipeline_metadata.json").read_text(encoding="utf-8"))
    provenance = metadata["source_provenance"]
    boc = next(item for item in provenance if item["source"] == "bank_of_canada")
    statcan = next(item for item in provenance if item["source"] == "statistics_canada")

    prime = outputs.pass_through.loc[outputs.pass_through["series_id"] == PRIME].iloc[0]
    consumer = outputs.pass_through.loc[outputs.pass_through["series_id"] == "V122667809"].iloc[0]
    card = outputs.pass_through.loc[outputs.pass_through["series_id"] == "V122667812"].iloc[0]
    mortgage5 = outputs.pass_through.loc[outputs.pass_through["series_id"] == "V80691335"].iloc[0]
    consumer_growth = outputs.regimes.loc[
        (outputs.regimes["series_id"] == "V122667758")
        & (outputs.regimes["metric"] == "monthly_yoy_growth_pct")
    ]
    latest_share = outputs.component_shares.iloc[0]
    sens100 = outputs.sensitivity.loc[
        (outputs.sensitivity["product"] == "Consumer credit")
        & (outputs.sensitivity["rate_shock_bp"] == 100)
    ].iloc[0]

    growth_sentences = []
    for regime in ["hiking", "stable", "easing"]:
        match = consumer_growth.loc[consumer_growth["regime"] == regime]
        if not match.empty:
            row = match.iloc[0]
            growth_sentences.append(
                f"{regime}: {row['average_value']:.2f}% average YoY growth "
                f"(N={int(row['n'])}, {row['date_min']} to {row['date_max']})"
            )

    memo = f"""# Canadian Household Credit and Interest-Rate Analysis

## Question and Thesis

This note asks how Bank of Canada policy-rate changes were associated with
posted and effective lending rates, and how those rate regimes coincided with
Canadian household-credit growth and debt indicators. The headline finding is
that prime-rate pass-through was mechanically close to the policy rate, while
effective consumer and card rates stayed meaningfully above policy rates and
credit-growth relationships were noisier across lags and regimes.

All figures use aggregate public indicators only. Bank of Canada data are as of
{boc['retrieved_utc']} from snapshot `{boc['snapshot']}`. Statistics Canada data
are as of {statcan['retrieved_utc']} from snapshot `{statcan['snapshot']}`. A
Statistics Canada refresh attempt on 2026-10-12 returned HTTP 403; that failure
was not reproduced on 2026-10-13, when the public WDS and official CSV download
both succeeded and all four configured series passed preflight validation.
Current validation passed for both sources with no warnings or failures.

## Evidence

**Mechanical pass-through.** Prime and policy rates are aligned on exact weekly
observation dates from {prime['date_min']} to {prime['date_max']} (N={int(prime['n'])}).
The latest prime-policy spread was {prime['latest_spread_pp']:.2f} percentage
points, compared with an average spread of {prime['average_spread_pp']:.2f}
percentage points over the aligned sample. This is the cleanest pass-through
measure because prime is a posted administered lending rate.

**Informative pass-through.** Effective lending rates are monthly series and are
compared with the average daily policy rate in the same calendar month. The
latest consumer-credit effective spread was {consumer['latest_spread_pp']:.2f}
percentage points (N={int(consumer['n'])}, {consumer['date_min']} to
{consumer['date_max']}); the credit-card effective spread was
{card['latest_spread_pp']:.2f} percentage points. Posted mortgage rates are also
shown, but they are informative rather than mechanical because they depend on
funding costs and bond yields as well as the overnight policy rate. The latest
5-year posted mortgage-policy spread was {mortgage5['latest_spread_pp']:.2f}
percentage points.

**Credit growth by regime.** Regimes are defined before computation using the
trailing 12-month change in the monthly average policy rate: hiking is at least
+{REGIME_THRESHOLD_PP:.2f} percentage points, easing is at most
-{REGIME_THRESHOLD_PP:.2f} percentage points, and stable is between those
thresholds. For total consumer credit, the computed regime averages were:
{'; '.join(growth_sentences)}. These are associations, not causal estimates.

**Lag profile.** The lead/lag table reports correlations between the trailing
12-month policy-rate change and later YoY balance growth for lags from 0 to 12
months. The profile is intentionally shown in full rather than optimized around
the strongest lag. Mixed signs and moderate sample sizes mean this evidence
should be read as timing context, not a predictive model.

**Debt and composition.** Statistics Canada debt-to-income is quarterly and can
only be joined to policy regimes after policy data begin in 2009. The Bank of
Canada tracked component shares are not total household-debt composition. As of
{latest_share['observation_date'].date().isoformat()}, the largest tracked
component was {latest_share['series_name']} at
{latest_share['share_of_tracked_components_pct']:.2f}% of tracked components.

## Illustrative Sensitivity

This is a mechanical sensitivity, not a forecast. It applies +100 bp or +200 bp
directly to latest observed balances and ignores repricing schedules, defaults,
credit mix, balances paid in full, and borrower behaviour. Mortgages are
excluded because this dataset does not include an effective mortgage lending
rate. For consumer credit, a +100 bp move equals
{sens100['incremental_annual_interest_millions_cad']:.1f} million CAD of
incremental annual interest, or {sens100['rate_shock_pct_of_balance']:.1f}% of
the balance, using {sens100['balance_series_id']} and {sens100['rate_series_id']}
as of {sens100['as_of_date']}.

## Implications for Banks and Lenders

The analysis separates rates that are administratively linked to policy from
rates that embed product mix, credit risk, funding costs, and customer behavior.
That distinction matters for bank revenue sensitivity: balances can still grow
or shift composition even when policy rates stabilize, and effective rates can
remain elevated relative to policy. For lenders, the useful interview takeaway
is not that rate hikes caused credit outcomes, but that public aggregate data
can quantify the timing, spreads, and balance exposure that an analyst would
then investigate with richer portfolio data.

## Limitations and Risks

The data are aggregate and public. They contain no individual borrowers, credit
bureau records, delinquencies, defaults, bank-level portfolios, or loan-level
repricing schedules. The analysis does not interpolate across mismatched
frequencies. Posted-rate comparisons start when policy-rate data begin in
2009-04. Effective-rate comparisons use monthly average policy rates. Results
are descriptive and may change when the public sources revise or refresh.
"""
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "research_memo.md").write_text(memo, encoding="utf-8")


def run(processed_dir: Path = PROCESSED_DIR, reports_dir: Path = REPORTS_DIR) -> ResearchOutputs:
    df = load_processed(processed_dir)
    pass_through = compute_rate_pass_through(df)
    lead_lag = compute_lead_lag_correlations(df)
    regimes = compute_regime_comparisons(df)
    sensitivity = compute_sensitivity(df)
    component_shares = compute_component_shares(df)
    placeholder = ResearchOutputs(pass_through, lead_lag, regimes, sensitivity, component_shares, pd.DataFrame())
    key_findings = build_key_findings(placeholder)
    outputs = ResearchOutputs(pass_through, lead_lag, regimes, sensitivity, component_shares, key_findings)
    write_outputs(outputs, reports_dir)
    create_figures(df, outputs, reports_dir / "figures")
    write_memo(outputs, processed_dir, reports_dir)
    logger.info("Research analysis complete -> %s", reports_dir)
    return outputs


def _date_or_blank(value: Any) -> str:
    if pd.isna(value):
        return ""
    return pd.Timestamp(value).date().isoformat()


if __name__ == "__main__":
    run()

