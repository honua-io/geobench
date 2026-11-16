import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/gc-cohort-diagnostic.py"
SPEC = importlib.util.spec_from_file_location("gc_diagnostic", SCRIPT)
gc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gc)


class GcDiagnosticTests(unittest.TestCase):
    def result(self, metrics):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "honua-concurrent-run1.json").write_text(
                json.dumps({"metrics": metrics})
            )
            return gc.summarize(directory, [1], 10, 1)["levels"]["1"]

    def metrics(self):
        return {
            "http_req_duration{concurrency:1}": {"p(95)": 100, "p(99)": 150},
            "http_reqs{concurrency:1}": {"count": 200},
            "errors{concurrency:1}": {"value": 0},
            "http_req_failed{concurrency:1}": {"value": 0},
        }

    def test_missing_error_metric_cannot_meet_bar(self):
        metrics = self.metrics()
        del metrics["errors{concurrency:1}"]
        result = self.result(metrics)
        self.assertFalse(result["complete"])
        self.assertFalse(result["meets_bar"])

    def test_nonfinite_metrics_cannot_meet_bar(self):
        metrics = self.metrics()
        metrics["http_req_duration{concurrency:1}"]["p(95)"] = float("nan")
        self.assertFalse(self.result(metrics)["meets_bar"])

    def test_request_failure_rejects_otherwise_fast_run(self):
        metrics = self.metrics()
        metrics["errors{concurrency:1}"]["value"] = 0.01
        result = self.result(metrics)
        self.assertTrue(result["complete"])
        self.assertFalse(result["meets_bar"])

    def test_complete_successful_run_reports_rate(self):
        result = self.result(self.metrics())
        self.assertTrue(result["meets_bar"])
        self.assertEqual(20, result["rps_median"])

    def summary(self, rows):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "samples.jsonl"
            path.write_text("".join(json.dumps(row) + "\n" for row in rows))
            return gc.runtime_summary(path)

    def test_missing_memory_and_pause_stay_unknown(self):
        result = self.summary([{"id": "a", "load": [1, 1, 1]}])
        self.assertFalse(result["memory_evidence_complete"])
        self.assertIsNone(result["gc_pause_seconds_observed_delta"])

    def test_pause_deltas_do_not_cross_container_restarts(self):
        rows = [
            {"id": cid, "load": [1, 1, 1], "gc_pause_seconds_total": value}
            for cid, value in [("a", 2), ("a", 3), ("b", 10), ("b", 12)]
        ]
        self.assertEqual(3, self.summary(rows)["gc_pause_seconds_observed_delta"])

    def test_pause_counter_reset_does_not_report_a_delta(self):
        rows = [
            {"id": "a", "load": [1, 1, 1], "gc_pause_seconds_total": value}
            for value in [2, 5, 1, 6]
        ]
        self.assertIsNone(self.summary(rows)["gc_pause_seconds_observed_delta"])

    def test_invalid_selection_fails_before_docker_or_artifact_creation(self):
        for flag, value in [
            ("--sizes", "Unknown"),
            ("--levels", "0"),
            ("--levels", "1,1"),
            ("--max-load", "nan"),
        ]:
            with (
                self.subTest(flag=flag, value=value),
                tempfile.TemporaryDirectory() as temporary,
            ):
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--image",
                        "sha256:" + "a" * 64,
                        "--source",
                        "b" * 40,
                        flag,
                        value,
                    ],
                    check=False,
                    cwd=temporary,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(2, result.returncode, result.stderr)
                self.assertEqual([], list(Path(temporary).iterdir()))


if __name__ == "__main__":
    unittest.main()
