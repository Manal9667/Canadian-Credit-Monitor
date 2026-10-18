from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from python.analytics.metrics import compute_timeseries
from python.db.duckdb_runner import build_connection, query
from python.ingestion.bank_of_canada import ValetAPIError, fetch_series, ingest_all as ingest_bank_of_canada
from python.ingestion.statistics_canada import (
    StatCanError,
    _extract_filtered_series,
    ingest_all as ingest_statistics_canada,
)
from python.transformation.transform import _normalize_dates, build_fact_observations
from python.validation.engine import validate_candidate_snapshot
from python.validation.validators import _freshness_schedule, build_series_freshness, check_stale_data
from python.common.io_utils import read_latest_pointer, update_latest_pointer


class ComputeTimeseriesTests(unittest.TestCase):
    def test_yoy_matches_calendar_date_across_missing_observation(self) -> None:
        dates = pd.to_datetime(
            ["2020-01-01"]
            + [f"2020-{month:02d}-01" for month in range(3, 13)]
            + ["2021-01-01", "2021-02-01"]
        )
        frame = pd.DataFrame(
            {
                "series_id": "monthly-series",
                "series_name": "Monthly series",
                "category": "Credit",
                "subcategory": "Consumer",
                "frequency": "monthly",
                "measure_type": "balance",
                "unit": "millions_cad",
                "observation_date": dates,
                "value": range(100, 100 + len(dates)),
            }
        )

        result = compute_timeseries(frame)

        self.assertEqual(result.loc[11, "value_year_ago"], 100)
        self.assertEqual(result.loc[11, "yoy_abs_change"], 11)
        self.assertEqual(result.loc[11, "yoy_pct_change"], 11)
        self.assertTrue(pd.isna(result.loc[12, "value_year_ago"]))

    def test_yoy_rejects_duplicate_series_dates(self) -> None:
        frame = pd.DataFrame(
            {
                "series_id": ["monthly-series", "monthly-series"],
                "series_name": ["Monthly series"] * 2,
                "category": ["Credit"] * 2,
                "subcategory": ["Consumer"] * 2,
                "frequency": ["monthly"] * 2,
                "measure_type": ["balance"] * 2,
                "unit": ["millions_cad"] * 2,
                "observation_date": pd.to_datetime(["2020-01-01", "2020-01-01"]),
                "value": [1, 2],
            }
        )

        with self.assertRaisesRegex(ValueError, "Duplicate observation dates"):
            compute_timeseries(frame)


class TransformationTests(unittest.TestCase):
    def test_normalize_dates_rejects_malformed_date(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unparseable observation dates"):
            _normalize_dates(pd.DataFrame({"observation_date": ["not-a-date"]}))

    def test_fact_rejects_duplicate_keys_and_malformed_values(self) -> None:
        series = pd.DataFrame({"series_key": [1], "series_id": ["sample"]})
        observations = pd.DataFrame(
            {
                "series_id": ["sample"],
                "observation_date": pd.to_datetime(["2024-01-01"]),
                "value": ["unknown"],
            }
        )

        with self.assertRaisesRegex(ValueError, "Non-numeric observation values"):
            build_fact_observations(observations, series)

        observations = pd.concat([observations, observations], ignore_index=True)
        with self.assertRaisesRegex(ValueError, "Duplicate series/date observations"):
            build_fact_observations(observations, series)


class FreshnessTests(unittest.TestCase):
    def test_candidate_preflight_rejects_missing_series_and_wrong_source(self) -> None:
        observations = pd.DataFrame(
            {
                "source": ["bank_of_canada"],
                "series_id": ["A"],
                "observation_date": ["2026-10-12"],
                "value": [2.25],
            }
        )
        metadata = pd.DataFrame(
            {
                "series_id": ["A"],
                "series_name": ["Alpha"],
                "frequency": ["daily"],
                "unit": ["percent"],
                "measure_type": ["rate"],
                "category": ["Policy Rate"],
            }
        )

        with self.assertRaisesRegex(ValueError, "Candidate series mismatch"):
            validate_candidate_snapshot(observations, metadata, "bank_of_canada", {"A", "B"})
        with self.assertRaisesRegex(ValueError, "do not all belong"):
            validate_candidate_snapshot(observations, metadata, "statistics_canada", {"A"})
        negative = observations.assign(value=-1.0)
        with self.assertRaisesRegex(ValueError, "validation warnings or failures"):
            validate_candidate_snapshot(negative, metadata, "bank_of_canada", {"A"})

    def test_publication_schedule_accounts_for_frequency_and_release_lag(self) -> None:
        cases = [
            ("bank_of_canada", "daily", "2026-10-09", "2026-10-12", "2026-10-14"),
            ("bank_of_canada", "weekly", "2026-10-07", "2026-10-14", "2026-10-16"),
            ("bank_of_canada", "monthly", "2026-07-01", "2026-10-30", "2026-11-06"),
            ("statistics_canada", "quarterly", "2026-04-01", "2026-12-11", "2026-12-18"),
        ]
        for source, frequency, latest, expected, overdue_after in cases:
            with self.subTest(source=source, frequency=frequency):
                schedule = _freshness_schedule(source, frequency, pd.Timestamp(latest))
                self.assertEqual(
                    tuple(value.date().isoformat() for value in schedule[:2]),
                    (expected, overdue_after),
                )

    def test_monthly_observation_is_current_until_expected_release_window_passes(self) -> None:
        frame = pd.DataFrame(
            {
                "source": ["bank_of_canada"],
                "series_id": ["V122667758"],
                "series_name": ["Consumer credit"],
                "frequency": ["monthly"],
                "observation_date": ["2026-07-01"],
            }
        )
        current = build_series_freshness(
            frame,
            "bank_of_canada",
            "snapshot-1",
            "retrieved-at",
            "processed-at",
            pd.Timestamp("2026-10-13"),
        )[0]
        overdue = check_stale_data(frame, as_of=pd.Timestamp("2026-11-07"))

        self.assertEqual(current["freshness_status"], "CURRENT")
        self.assertEqual(current["source_observation_date"], "2026-07-01")
        self.assertEqual(current["retrieval_timestamp_utc"], "retrieved-at")
        self.assertEqual(current["processing_timestamp_utc"], "processed-at")
        self.assertEqual(current["expected_next_publication_date"], "2026-10-30")
        self.assertEqual(overdue.status, "WARN")
        self.assertIn("V122667758", overdue.details["stale_series"])


class SqlViewTests(unittest.TestCase):
    def test_yoy_and_component_share_views_on_small_fixture(self) -> None:
        with TemporaryDirectory() as tmp:
            processed = Path(tmp)
            dates = pd.to_datetime(["2020-01-01", "2021-01-01"])
            date_dimension = pd.DataFrame(
                {
                    "date_key": dates.strftime("%Y%m%d").astype(int),
                    "date": dates,
                    "year": dates.year,
                    "quarter": dates.quarter,
                    "month": dates.month,
                    "month_name": dates.strftime("%B"),
                    "year_month": dates.strftime("%Y-%m"),
                    "year_quarter": dates.year.astype(str) + "-Q" + dates.quarter.astype(str),
                    "day_of_month": dates.day,
                    "is_month_end": [False, False],
                    "is_quarter_end": [False, False],
                }
            )
            pd.DataFrame(
                [{"source_key": "bank_of_canada", "source_name": "BoC", "service": "Valet", "licence": "Public"}]
            ).to_csv(processed / "dim_source.csv", index=False)
            pd.DataFrame(
                [
                    {"series_key": 1, "series_id": "TOTAL", "series_name": "Consumer credit total", "category": "Household Credit", "subcategory": "Consumer credit total", "unit": "millions_cad", "frequency": "monthly", "measure_type": "balance", "source_key": "bank_of_canada"},
                    {"series_key": 2, "series_id": "CARD", "series_name": "Credit cards", "category": "Household Credit", "subcategory": "Credit cards", "unit": "millions_cad", "frequency": "monthly", "measure_type": "balance", "source_key": "bank_of_canada"},
                    {"series_key": 3, "series_id": "AUTO", "series_name": "Auto loans", "category": "Household Credit", "subcategory": "Auto loans", "unit": "millions_cad", "frequency": "monthly", "measure_type": "balance", "source_key": "bank_of_canada"},
                ]
            ).to_csv(processed / "dim_series.csv", index=False)
            date_dimension.to_csv(processed / "dim_date.csv", index=False)
            rows = [
                {"series_key": 1, "series_id": "TOTAL", "date_key": key, "observation_date": date, "value": 200}
                for key, date in zip(date_dimension["date_key"], dates)
            ]
            for series_key, series_id, values in [(2, "CARD", [40, 50]), (3, "AUTO", [60, 70])]:
                rows.extend(
                    {"series_key": series_key, "series_id": series_id, "date_key": key, "observation_date": date, "value": value}
                    for (key, date), value in zip(zip(date_dimension["date_key"], dates), values)
                )
            pd.DataFrame(rows).to_csv(processed / "fact_observations.csv", index=False)

            connection = build_connection(processed)
            share = query(
                connection,
                "SELECT series_id, tracked_component_total, pct_of_tracked_components "
                "FROM credit.vw_category_share WHERE observation_date = DATE '2021-01-01' "
                "ORDER BY series_id",
            )
            yoy = query(
                connection,
                "SELECT value_year_ago, yoy_abs_change, yoy_pct_change "
                "FROM credit.vw_yoy_change "
                "WHERE series_id = 'CARD' AND observation_date = DATE '2021-01-01'",
            )
            connection.close()

        self.assertEqual(share["series_id"].tolist(), ["AUTO", "CARD"])
        self.assertEqual(share["tracked_component_total"].tolist(), [120, 120])
        self.assertEqual(share["pct_of_tracked_components"].tolist(), [58.333, 41.667])
        self.assertEqual(yoy.loc[0, "value_year_ago"], 40)
        self.assertEqual(yoy.loc[0, "yoy_abs_change"], 10)
        self.assertEqual(yoy.loc[0, "yoy_pct_change"], 25)


class IngestionParsingTests(unittest.TestCase):
    def test_partial_bank_refresh_does_not_advance_latest_pointer(self) -> None:
        series = [
            {
                "series_id": series_id,
                "name": series_id,
                "category": "Rates",
                "subcategory": series_id,
                "unit": "percent",
                "frequency": "daily",
                "measure_type": "rate",
            }
            for series_id in ["A", "B"]
        ]
        with TemporaryDirectory() as tmp:
            raw_dir = Path(tmp) / "raw"
            with patch("python.common.io_utils.RAW_DIR", raw_dir):
                update_latest_pointer("bank_of_canada", "validated-old")
                frame = pd.DataFrame(
                    [{"source": "bank_of_canada", "series_id": "A", "observation_date": "2026-10-12", "value": 2.0}]
                )
                with (
                    patch("python.ingestion.bank_of_canada.load_series_config", return_value={"bank_of_canada": {"series": series}}),
                    patch("python.ingestion.bank_of_canada.get_setting", return_value="2000-01-01"),
                    patch("python.ingestion.bank_of_canada.run_stamp", return_value="candidate"),
                    patch("python.ingestion.bank_of_canada.fetch_series", side_effect=[frame, ValetAPIError("offline")]),
                    patch("python.ingestion.bank_of_canada.raw_snapshot_dir") as create_snapshot,
                ):
                    with self.assertRaisesRegex(ValetAPIError, "keeping the previous snapshot selected"):
                        ingest_bank_of_canada()

                self.assertEqual(read_latest_pointer("bank_of_canada"), "validated-old")
                create_snapshot.assert_not_called()

    def test_partial_statcan_refresh_does_not_advance_latest_pointer(self) -> None:
        table = {
            "product_id": "table-1",
            "category": "Credit",
            "frequency": "quarterly",
            "row_filters": [
                {"match_column": "Categories", "match_value": "A", "series_name": "A", "subcategory": "A", "unit": "ratio", "measure_type": "ratio"},
                {"match_column": "Categories", "match_value": "B", "series_name": "B", "subcategory": "B", "unit": "ratio", "measure_type": "ratio"},
            ],
        }
        observations = pd.DataFrame(
            [{"source": "statistics_canada", "series_id": "STATCAN_A", "observation_date": "2026-04", "value": 1.0}]
        )
        metadata = [{
            "source": "statistics_canada", "series_id": "STATCAN_A", "series_name": "A", "category": "Credit",
            "subcategory": "A", "unit": "ratio", "frequency": "quarterly", "measure_type": "ratio",
        }]
        with TemporaryDirectory() as tmp:
            raw_dir = Path(tmp) / "raw"
            with patch("python.common.io_utils.RAW_DIR", raw_dir):
                update_latest_pointer("statistics_canada", "validated-old")
                with (
                    patch("python.ingestion.statistics_canada.load_series_config", return_value={"statistics_canada": {"tables": [table, {**table, "product_id": "table-2"}]}}),
                    patch("python.ingestion.statistics_canada.run_stamp", return_value="candidate"),
                    patch("python.ingestion.statistics_canada._download_table_csv", side_effect=[pd.DataFrame(), StatCanError("HTTP 403")]),
                    patch("python.ingestion.statistics_canada._extract_filtered_series", return_value=(observations, metadata, [])),
                    patch("python.ingestion.statistics_canada.raw_snapshot_dir") as create_snapshot,
                ):
                    with self.assertRaisesRegex(StatCanError, "keeping the previous snapshot selected"):
                        ingest_statistics_canada()

                self.assertEqual(read_latest_pointer("statistics_canada"), "validated-old")
                create_snapshot.assert_not_called()

    def test_bank_of_canada_preserves_zero_and_missing_cells(self) -> None:
        response = unittest.mock.Mock()
        response.json.return_value = {
            "observations": [
                {"d": "2024-01-01", "SERIES": {"v": "0"}},
                {"d": "2024-01-02", "SERIES": {"v": ""}},
                {"d": "2024-01-03"},
            ]
        }
        with patch("python.ingestion.bank_of_canada.requests.get", return_value=response):
            result = fetch_series("SERIES")

        self.assertEqual(result.loc[0, "value"], 0)
        self.assertTrue(pd.isna(result.loc[1, "value"]))
        self.assertTrue(pd.isna(result.loc[2, "value"]))

    def test_bank_of_canada_rejects_malformed_numeric_payload(self) -> None:
        response = unittest.mock.Mock()
        response.json.return_value = {
            "observations": [{"d": "2024-01-01", "SERIES": {"v": "not-numeric"}}]
        }
        with patch("python.ingestion.bank_of_canada.requests.get", return_value=response):
            with self.assertRaisesRegex(ValetAPIError, "non-numeric value"):
                fetch_series("SERIES")

    def test_statistics_canada_rejects_duplicate_dates(self) -> None:
        table_cfg = {
            "product_id": "123",
            "category": "Credit",
            "frequency": "quarterly",
            "row_filters": [
                {
                    "match_column": "Categories",
                    "match_value": "Credit balance",
                    "series_name": "Credit balance",
                    "subcategory": "Total",
                    "unit": "millions_cad",
                    "measure_type": "balance",
                }
            ],
        }
        frame = pd.DataFrame(
            {
                "Categories": ["Credit balance", "Credit balance"],
                "REF_DATE": ["2024-01", "2024-01"],
                "VALUE": ["10", "11"],
                "VECTOR": ["v1", "v1"],
            }
        )

        with self.assertRaisesRegex(StatCanError, "Ambiguous duplicate dates"):
            _extract_filtered_series(frame, table_cfg)