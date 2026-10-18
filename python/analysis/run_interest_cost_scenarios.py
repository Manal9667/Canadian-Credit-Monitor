"""Generate reproducible interest-cost examples from the selected snapshot."""
from __future__ import annotations

import pandas as pd

from ..common.config import PROCESSED_DIR, PROJECT_ROOT
from .interest_cost_scenarios import ScenarioInputs, calculate_interest_cost

REPORT_PATH = PROJECT_ROOT / "reports" / "interest_cost_scenario_examples.csv"
BALANCE_ID = "V122667758"
RATE_ID = "V122667809"


def run() -> pd.DataFrame:
    fact = pd.read_csv(PROCESSED_DIR / "fact_observations.csv", parse_dates=["observation_date"])
    metadata = pd.read_csv(PROCESSED_DIR / "dim_series.csv")
    data = fact.merge(metadata, on="series_id", how="left")
    latest = data.sort_values("observation_date").groupby("series_id").tail(1).set_index("series_id")
    balance = float(latest.loc[BALANCE_ID, "value"])
    rate = float(latest.loc[RATE_ID, "value"])
    balance_date = latest.loc[BALANCE_ID, "observation_date"].date().isoformat()
    rate_date = latest.loc[RATE_ID, "observation_date"].date().isoformat()
    retrieval = ""
    snapshot_id = ""
    balance_freshness_status = "not available"
    rate_freshness_status = "not available"
    expected_next_publication = ""
    overdue_after = ""
    freshness_path = PROCESSED_DIR / "series_freshness.csv"
    if freshness_path.exists():
        freshness = pd.read_csv(freshness_path)
        match = freshness.loc[freshness.series_id == BALANCE_ID]
        if not match.empty:
            source_row = match.iloc[0]
            retrieval = str(source_row["retrieval_timestamp_utc"])
            snapshot_id = str(source_row["snapshot_id"])
            balance_freshness_status = str(source_row["freshness_status"])
            expected_next_publication = str(source_row["expected_next_publication_date"])
            overdue_after = str(source_row["overdue_after_date"])
        rate_match = freshness.loc[freshness.series_id == RATE_ID]
        if not rate_match.empty:
            rate_freshness_status = str(rate_match.iloc[0]["freshness_status"])

    rows = []
    specs = [(f"full_mechanical_{shock}bp", shock, 1, 1, 1, 12, "start") for shock in (25, 50, 100, 200)]
    specs.append(("illustrative_partial_100bp", 100, .6, .5, .5, 12, "uniform"))
    for name, shock, exposure, through, repriced, horizon, timing in specs:
        inputs = ScenarioInputs(balance, shock, exposure, through, repriced, horizon, timing)
        result = calculate_interest_cost(inputs)
        rows.append({
            "scenario": name,
            "balance_series_id": BALANCE_ID,
            "balance_millions_cad": balance,
            "balance_observation_date": balance_date,
            "balance_snapshot_retrieved_utc": retrieval,
            "source_snapshot_id": snapshot_id,
            "balance_freshness_status_as_of_validation": balance_freshness_status,
            "rate_freshness_status_as_of_validation": rate_freshness_status,
            "configured_expected_next_publication_date": expected_next_publication,
            "configured_overdue_after_date": overdue_after,
            "paired_effective_rate_series_id": RATE_ID,
            "observed_effective_rate_pct_context_only": rate,
            "effective_rate_observation_date": rate_date,
            "policy_shock_bp": shock,
            "exposure_share": exposure,
            "pass_through_multiple": through,
            "repriced_share_of_exposed": repriced,
            "horizon_months": horizon,
            "timing": timing,
            "borrowing_rate_change_bp": result.borrowing_rate_change_bp,
            "partial_balance_millions_cad": result.partial_balance_millions_cad,
            "partial_annualized_millions_cad_per_year": result.partial_annualized_millions_cad,
            "partial_cumulative_millions_cad": result.partial_cumulative_millions_cad,
            "mechanical_annualized_millions_cad_per_year": result.mechanical_annualized_millions_cad,
            "mechanical_cumulative_millions_cad": result.mechanical_cumulative_millions_cad,
        })
    out = pd.DataFrame(rows)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(REPORT_PATH, index=False)
    return out


if __name__ == "__main__":
    result = run()
    print(f"Wrote {len(result)} reproducible scenario rows to {REPORT_PATH}")
