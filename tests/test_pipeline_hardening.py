from __future__ import annotations

import io
import json
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd
import requests

from python.common.io_utils import (
    dataframe_writer, publish_output_bundle, read_latest_pointer, update_latest_pointer,
)
from python.ingestion.bank_of_canada import ingest_all as ingest_bank_of_canada
from python.ingestion.statistics_canada import StatCanError, _download_table_csv
from python.transformation.transform import _load_latest


class OutputBundleTests(unittest.TestCase):
    def test_writer_failure_preserves_existing_outputs(self) -> None:
        with TemporaryDirectory() as tmp:
            first = Path(tmp) / "first.csv"
            second = Path(tmp) / "second.csv"
            first.write_text("old first", encoding="utf-8")
            second.write_text("old second", encoding="utf-8")

            def fail(_path: Path) -> None:
                raise OSError("simulated interrupted refresh")

            with self.assertRaisesRegex(OSError, "simulated interrupted"):
                publish_output_bundle({
                    first: lambda path: path.write_text("new first", encoding="utf-8"),
                    second: fail,
                })

            self.assertEqual(first.read_text(encoding="utf-8"), "old first")
            self.assertEqual(second.read_text(encoding="utf-8"), "old second")

    def test_bundle_rerun_replaces_outputs_without_appending_duplicates(self) -> None:
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "observations.csv"
            frame = pd.DataFrame({"series_id": ["A"], "date": ["2024-01-01"], "value": [1]})
            for _ in range(2):
                publish_output_bundle({target: dataframe_writer(frame)})
            result = pd.read_csv(target)
            self.assertEqual(len(result), 1)
            self.assertEqual(result.loc[0, "value"], 1)


class SnapshotGuardTests(unittest.TestCase):
    def test_selected_snapshot_requires_manifest_and_consistent_count(self) -> None:
        with TemporaryDirectory() as tmp:
            snapshot = Path(tmp)
            pd.DataFrame({
                "source": ["bank_of_canada"], "series_id": ["A"],
                "observation_date": ["2024-01-01"], "value": [1.0],
            }).to_csv(snapshot / "observations.csv", index=False)
            pd.DataFrame({
                "source": ["bank_of_canada"], "series_id": ["A"],
                "series_name": ["A"], "category": ["Rates"], "subcategory": ["A"],
                "unit": ["percent"], "frequency": ["daily"], "measure_type": ["rate"],
            }).to_csv(snapshot / "series_metadata.csv", index=False)
            (snapshot / "metadata.json").write_text(json.dumps({
                "source": "bank_of_canada", "observation_count": 2,
            }), encoding="utf-8")
            with patch("python.transformation.transform.latest_snapshot_dir", return_value=snapshot):
                with self.assertRaisesRegex(ValueError, "observation count mismatch"):
                    _load_latest("bank_of_canada")

    def test_transform_refuses_missing_required_source(self) -> None:
        with patch("python.transformation.transform.latest_snapshot_dir", return_value=None):
            with self.assertRaisesRegex(FileNotFoundError, "refusing partial transform"):
                _load_latest("statistics_canada")

    def test_failed_refresh_is_recorded_and_keeps_last_good_pointer(self) -> None:
        with TemporaryDirectory() as tmp:
            raw_dir = Path(tmp) / "raw"
            with patch("python.common.io_utils.RAW_DIR", raw_dir):
                update_latest_pointer("bank_of_canada", "known-good")
                with patch(
                    "python.ingestion.bank_of_canada._ingest_all",
                    side_effect=RuntimeError("source unavailable"),
                ):
                    with self.assertRaisesRegex(RuntimeError, "source unavailable"):
                        ingest_bank_of_canada()
                self.assertEqual(read_latest_pointer("bank_of_canada"), "known-good")
                state = json.loads(
                    (raw_dir / "bank_of_canada" / "last_refresh.json").read_text(encoding="utf-8")
                )
                self.assertEqual(state["status"], "FAILED")


class StatCanRetryTests(unittest.TestCase):
    def test_permanent_http_failure_is_not_retried(self) -> None:
        error = requests.HTTPError("403")
        error.response = type("Response", (), {"status_code": 403})()
        with (
            patch("python.ingestion.statistics_canada.load_series_config", return_value={
                "statistics_canada": {"api_base": "https://example.invalid"}
            }),
            patch("python.ingestion.statistics_canada.get_setting", side_effect=lambda key, default=None: {
                "max_retries": 3, "retry_backoff_seconds": 0, "request_timeout_seconds": 1,
                "user_agent": "test",
            }.get(key, default)),
            patch("python.ingestion.statistics_canada._get_json", side_effect=error) as get_json,
        ):
            with self.assertRaises(StatCanError):
                _download_table_csv("123")
        self.assertEqual(get_json.call_count, 1)

    def test_transient_http_failure_retries_then_succeeds(self) -> None:
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w") as archive:
            archive.writestr("123.csv", "REF_DATE,VALUE\n2024-01,1\n")
        response = type("Response", (), {
            "content": archive_buffer.getvalue(),
            "raise_for_status": lambda self: None,
        })()
        error = requests.HTTPError("503")
        error.response = type("Response", (), {"status_code": 503})()
        with (
            patch("python.ingestion.statistics_canada.load_series_config", return_value={
                "statistics_canada": {"api_base": "https://example.invalid"}
            }),
            patch("python.ingestion.statistics_canada.get_setting", side_effect=lambda key, default=None: {
                "max_retries": 3, "retry_backoff_seconds": 0, "request_timeout_seconds": 1,
                "user_agent": "test",
            }.get(key, default)),
            patch("python.ingestion.statistics_canada._get_json", return_value={
                "status": "SUCCESS", "object": "https://example.invalid/table.zip"
            }),
            patch("python.ingestion.statistics_canada.requests.get", side_effect=[error, response]),
            patch("python.ingestion.statistics_canada.time.sleep"),
        ):
            result = _download_table_csv("123")
        self.assertEqual(result.loc[0, "REF_DATE"], "2024-01")
        self.assertEqual(result.loc[0, "VALUE"], "1")


if __name__ == "__main__":
    unittest.main()
