"""Reproduce dependence-aware consumer-credit research outputs."""
from .household_credit_research import load_processed, REPORTS_DIR
from .credit_regime_extensions import prepare_credit_panel, summarize_regimes, lagged_correlations, sensitivity_table, hac_regression


def run() -> None:
    df = load_processed()
    panel = prepare_credit_panel(df)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    summarize_regimes(panel).to_csv(REPORTS_DIR / "credit_regime_uncertainty.csv", index=False)
    lagged_correlations(panel).to_csv(REPORTS_DIR / "credit_lagged_correlations.csv", index=False)
    sensitivity_table(panel).to_csv(REPORTS_DIR / "credit_regime_sensitivity.csv", index=False)
    hac_regression(panel).to_csv(REPORTS_DIR / "credit_hac_regression.csv", index=False)
    panel.to_csv(REPORTS_DIR / "credit_monthly_analysis_panel.csv", index=False)


if __name__ == "__main__":
    run()
