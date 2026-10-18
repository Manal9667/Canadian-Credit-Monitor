from __future__ import annotations

import unittest

import pandas as pd

from python.transformation.transform import build_dim_series, build_fact_observations
from python.validation.validators import (
    check_duplicates,
    check_future_dates,
    check_invalid_dates,
    check_negative_balances,
)


class DataQualityEdgeCaseTests(unittest.TestCase):
    def test_validation_rules_flag_duplicates_invalid_future_and_negative_data(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "series_id": "A",
                    "observation_date": "2024-01-01",
                    "value": 100.0,
                    "frequency": "monthly",
                },
                {
                    "series_id": "A",
                    "observation_date": "2024-01-01",
                    "value": 110.0,
                    "frequency": "monthly",
                },
                {
                    "series_id": "A",
                    "observation_date": "bad-date",
                    "value": 50.0,
                    "frequency": "monthly",
                },
                {
                    "series_id": "B",
                    "observation_date": "2025-01-01",
                    "value": -2.0,
                    "frequency": "monthly",
                },
            ]
        )

        self.assertEqual(check_duplicates(df).status, "FAIL")
        self.assertEqual(check_invalid_dates(df).status, "FAIL")
        self.assertEqual(check_future_dates(df, as_of=pd.Timestamp("2024-12-31")).status, "WARN")
        self.assertEqual(check_negative_balances(df).status, "WARN")

    def test_transformation_rejects_duplicate_keys_and_non_numeric_values(self) -> None:
        all_meta = pd.DataFrame(
            [
                {
                    "series_id": "A",
                    "series_name": "Alpha",
                    "category": "Credit",
                    "subcategory": "Consumer",
                    "unit": "millions",
                    "frequency": "monthly",
                    "measure_type": "balance",
                    "source": "bank_of_canada",
                },
            ]
        )
        dim_series = build_dim_series(all_meta)

        obs_dup = pd.DataFrame(
            [
                {"series_id": "A", "observation_date": pd.Timestamp("2024-01-01"), "value": 1.0},
                {"series_id": "A", "observation_date": pd.Timestamp("2024-01-01"), "value": 2.0},
            ]
        )
        with self.assertRaisesRegex(ValueError, "Duplicate series/date observations"):
            build_fact_observations(obs_dup, dim_series)

        obs_non_numeric = pd.DataFrame(
            [
                {"series_id": "A", "observation_date": pd.Timestamp("2024-01-01"), "value": "not-a-number"},
            ]
        )
        with self.assertRaisesRegex(ValueError, "Non-numeric observation values"):
            build_fact_observations(obs_non_numeric, dim_series)


if __name__ == "__main__":
    unittest.main()
