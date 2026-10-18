from __future__ import annotations

import math
import unittest

from python.analysis.interest_cost_scenarios import ScenarioInputs, calculate_interest_cost


class InterestCostScenarioTests(unittest.TestCase):
    def inputs(self, **overrides):
        values = dict(eligible_balance_millions_cad=1_000.0, policy_shock_bp=100,
                      exposure_share=1.0, pass_through=1.0, repriced_share=1.0,
                      horizon_months=12, timing="start")
        values.update(overrides)
        return ScenarioInputs(**values)

    def test_zero_shock_and_zero_balance(self):
        self.assertEqual(calculate_interest_cost(self.inputs(policy_shock_bp=0)).partial_annualized_millions_cad, 0)
        self.assertEqual(calculate_interest_cost(self.inputs(eligible_balance_millions_cad=0)).mechanical_cumulative_millions_cad, 0)

    def test_basis_point_conversion_and_full_repricing_hand_calculation(self):
        result = calculate_interest_cost(self.inputs(policy_shock_bp=25))
        self.assertAlmostEqual(result.borrowing_rate_change_bp, 25)
        self.assertAlmostEqual(result.partial_annualized_millions_cad, 2.5)
        self.assertAlmostEqual(result.mechanical_cumulative_millions_cad, 2.5)

    def test_verified_repository_balance_reproduces_mechanical_100bp_sensitivity(self):
        result = calculate_interest_cost(ScenarioInputs(704_582, 100, 1, 1, 1, 12, "start"))
        self.assertAlmostEqual(result.mechanical_annualized_millions_cad, 7_045.82)
        self.assertAlmostEqual(result.mechanical_cumulative_millions_cad, 7_045.82)

    def test_partial_exposure_pass_through_and_repricing_are_separate_shares(self):
        result = calculate_interest_cost(self.inputs(exposure_share=.6, pass_through=.5,
                                                      repriced_share=.5, timing="start"))
        self.assertAlmostEqual(result.borrowing_rate_change_bp, 50)
        self.assertAlmostEqual(result.partial_balance_millions_cad, 300)
        self.assertAlmostEqual(result.partial_annualized_millions_cad, 1.5)

    def test_uniform_repricing_has_half_horizon_cumulative_cost(self):
        result = calculate_interest_cost(self.inputs(policy_shock_bp=200, horizon_months=6, timing="uniform"))
        self.assertAlmostEqual(result.partial_annualized_millions_cad, 20)
        self.assertAlmostEqual(result.partial_cumulative_millions_cad, 5)

    def test_short_horizon_and_immediate_timing(self):
        result = calculate_interest_cost(self.inputs(policy_shock_bp=100, horizon_months=3, timing="start"))
        self.assertAlmostEqual(result.partial_annualized_millions_cad, 10)
        self.assertAlmostEqual(result.partial_cumulative_millions_cad, 2.5)

    def test_negative_shock_reduces_interest_cost(self):
        result = calculate_interest_cost(self.inputs(policy_shock_bp=-50))
        self.assertAlmostEqual(result.partial_annualized_millions_cad, -5)

    def test_invalid_and_extreme_inputs_fail_safely(self):
        invalid = [
            {"eligible_balance_millions_cad": -1}, {"eligible_balance_millions_cad": math.inf},
            {"eligible_balance_millions_cad": 1e99}, {"policy_shock_bp": 10_001},
            {"exposure_share": 1.01}, {"pass_through": -0.1}, {"pass_through": 5.1},
            {"repriced_share": -0.01}, {"horizon_months": 0}, {"horizon_months": 121},
            {"horizon_months": 1.5}, {"timing": "unknown"},
        ]
        for update in invalid:
            with self.subTest(update=update), self.assertRaises(ValueError):
                calculate_interest_cost(self.inputs(**update))

    def test_boundary_values_are_accepted(self):
        result = calculate_interest_cost(self.inputs(
            eligible_balance_millions_cad=1e9, policy_shock_bp=-10_000,
            exposure_share=0, pass_through=5, repriced_share=1,
            horizon_months=120, timing="uniform"))
        self.assertEqual(result.partial_annualized_millions_cad, 0)
        self.assertEqual(result.mechanical_annualized_millions_cad, -1e9)


if __name__ == "__main__":
    unittest.main()
