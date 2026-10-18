from __future__ import annotations

import unittest

import pandas as pd

from python.analysis.household_credit_research import (
    REGIME_THRESHOLD_PP,
    classify_regime,
    compute_lead_lag_correlations,
    compute_sensitivity,
)
from python.analysis.credit_regime_extensions import prepare_credit_panel, summarize_regimes, lagged_correlations


class ResearchAnalysisTests(unittest.TestCase):
    def test_extended_panel_uses_calendar_alignment_and_does_not_bridge_missing_month(self) -> None:
        dates = pd.date_range("2019-01-01", periods=30, freq="MS").delete(18)
        rows=[]
        for i, date in enumerate(pd.date_range("2018-01-01", periods=42, freq="MS")):
            rows.append(_row("V39079", "Policy", "Policy Rate", "Overnight", "daily", "rate", "percent", date, 1 + .1*(i//12)))
        for i,date in enumerate(dates):
            rows.append(_row("V122667758", "Consumer credit", "Household Credit", "Total", "monthly", "balance", "millions_cad", date, 100+i))
        panel=prepare_credit_panel(pd.DataFrame(rows))
        month=pd.Period("2020-07",freq="M")
        row=panel.loc[panel.month==month].iloc[0]
        self.assertTrue(pd.isna(row.value))
        self.assertTrue(pd.isna(row.growth_yoy_pct))
        self.assertEqual(panel.month.nunique(), len(panel))

    def test_extended_summary_stats_and_lag_date_alignment(self) -> None:
        dates=pd.date_range("2019-01-01",periods=40,freq="MS")
        rows=[]
        for i,date in enumerate(dates):
            rows.extend([
                _row("V39079","Policy","Policy Rate","Overnight","daily","rate","percent",date,1 if i<20 else 2),
                _row("V122667758","Consumer credit","Household Credit","Total","monthly","balance","millions_cad",date,100+i),
            ])
        panel=prepare_credit_panel(pd.DataFrame(rows))
        stats=summarize_regimes(panel,reps=25)
        self.assertIn("sd_pct",stats.columns)
        self.assertIn("hac12_ci95_low",stats.columns)
        self.assertIn("block12_ci95_high",stats.columns)
        lags=lagged_correlations(panel,2)
        self.assertEqual(lags.loc[lags.lag_months==0,"n"].iloc[0],lags.loc[lags.lag_months==1,"n"].iloc[0]+1)
        self.assertEqual(lags.loc[lags.lag_months==1,"date_max"].iloc[0],"2022-03")

    def test_summary_core_mean_median_and_sample_sd(self) -> None:
        panel=pd.DataFrame({
            "observation_date":pd.date_range("2024-01-01",periods=3,freq="MS"),
            "month":pd.period_range("2024-01",periods=3,freq="M"),
            "growth_yoy_pct":[1.0,3.0,2.0],
            "regime_baseline":["hiking","hiking","stable"],
        })
        result=summarize_regimes(panel,reps=20).set_index("regime")
        self.assertEqual(result.loc["hiking","mean_pct"],2.0)
        self.assertEqual(result.loc["hiking","median_pct"],2.0)
        self.assertAlmostEqual(result.loc["hiking","sd_pct"],2**0.5)

    def test_regime_rule_uses_fixed_25bp_threshold(self) -> None:
        self.assertEqual(REGIME_THRESHOLD_PP, 0.25)
        self.assertEqual(classify_regime(0.25), "hiking")
        self.assertEqual(classify_regime(-0.25), "easing")
        self.assertEqual(classify_regime(0.24), "stable")
        self.assertEqual(classify_regime(-0.24), "stable")
        self.assertIsNone(classify_regime(None))

    def test_lead_lag_uses_changes_not_levels_and_reports_n(self) -> None:
        rows = []
        for i, date in enumerate(pd.date_range("2019-01-01", periods=36, freq="MS")):
            policy = 1.0 if i < 12 else 2.0
            balance = 100.0 + i
            if i >= 12:
                balance = 100.0 + i + 10.0 * (policy - 1.0)
            rows.extend(
                [
                    _row("V39079", "Policy", "Policy Rate", "Overnight", "daily", "rate", "percent", date, policy),
                    _row("V122667758", "Consumer credit", "Household Credit", "Consumer credit total", "monthly", "balance", "millions_cad", date, balance),
                ]
            )
        frame = pd.DataFrame(rows)

        result = compute_lead_lag_correlations(frame)
        subset = result.loc[result["series_id"] == "V122667758"]

        self.assertEqual(subset["lag_months"].min(), 0)
        self.assertEqual(subset["lag_months"].max(), 12)
        self.assertTrue((subset["n"] > 0).any())
        self.assertIn("correlation", subset.columns)

    def test_sensitivity_is_balance_times_rate_shock(self) -> None:
        frame = pd.DataFrame(
            [
                _row("V122667758", "Consumer credit", "Household Credit", "Total", "monthly", "balance", "millions_cad", "2024-01-01", 1000.0),
                _row("V122667809", "Consumer rate", "Effective Lending Rate", "Total", "monthly", "rate", "percent", "2024-01-01", 7.0),
                _row("V122667761", "Cards", "Household Credit", "Cards", "monthly", "balance", "millions_cad", "2024-01-01", 200.0),
                _row("V122667812", "Card rate", "Effective Lending Rate", "Cards", "monthly", "rate", "percent", "2024-01-01", 20.0),
                _row("V122667770", "Business", "Business Credit", "Business", "monthly", "balance", "millions_cad", "2024-01-01", 500.0),
                _row("V122667821", "Business rate", "Effective Lending Rate", "Business", "monthly", "rate", "percent", "2024-01-01", 5.0),
            ]
        )

        result = compute_sensitivity(frame)
        consumer_100 = result.loc[
            (result["product"] == "Consumer credit") & (result["rate_shock_bp"] == 100)
        ].iloc[0]
        consumer_200 = result.loc[
            (result["product"] == "Consumer credit") & (result["rate_shock_bp"] == 200)
        ].iloc[0]

        self.assertEqual(consumer_100["incremental_annual_interest_millions_cad"], 10.0)
        self.assertEqual(consumer_100["rate_shock_pct_of_balance"], 1.0)
        self.assertEqual(consumer_200["incremental_annual_interest_millions_cad"], 20.0)
        self.assertEqual(consumer_200["rate_shock_pct_of_balance"], 2.0)


def _row(
    series_id: str,
    series_name: str,
    category: str,
    subcategory: str,
    frequency: str,
    measure_type: str,
    unit: str,
    date: str | pd.Timestamp,
    value: float,
) -> dict[str, object]:
    return {
        "series_id": series_id,
        "series_name": series_name,
        "category": category,
        "subcategory": subcategory,
        "frequency": frequency,
        "measure_type": measure_type,
        "unit": unit,
        "observation_date": pd.Timestamp(date),
        "value": value,
    }

