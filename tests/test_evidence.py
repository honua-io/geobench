import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from k6_results import validation_failures  # noqa: E402


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.data = {"metrics": {
            "http_reqs": {"count": 100, "rate": 10},
            "checks": {"value": 1, "passes": 200, "fails": 0},
            "errors": {"value": 0},
            "http_req_failed": {"value": 0},
            "http_req_duration": {"med": 1, "p(95)": 2, "p(99)": 3},
        }}

    def test_accepts_valid_zero_in_both_summary_formats(self):
        self.assertEqual([], validation_failures(self.data))
        for name in ("checks", "errors", "http_req_failed"):
            metric = self.data["metrics"][name]
            metric["rate"] = metric.pop("value")
        self.assertEqual([], validation_failures(self.data))

    def test_rejects_missing_errors_failed_checks_and_no_traffic(self):
        for field in ("errors", "http_req_failed", "checks", "http_reqs"):
            data = copy.deepcopy(self.data)
            del data["metrics"][field]
            self.assertTrue(validation_failures(data), field)
        self.data["metrics"]["checks"]["fails"] = 1
        self.assertTrue(validation_failures(self.data))

    def test_rejects_negative_or_nonfinite_latencies(self):
        for value in (-85.265, float("nan"), float("inf")):
            self.data["metrics"]["http_req_duration"]["min"] = value
            self.assertTrue(validation_failures(self.data))

    def test_historical_failed_campaign_cannot_be_promoted_or_reported(self):
        directory = ROOT / "results/releases/v2026.1-rc.0"
        gate = load_script("check-regression")
        failures = gate.validate_results_complete(directory, "honua", ["attribute-filter"], 3, None)
        self.assertTrue(any("INVALID" in reason for reason in failures))
        report = load_script("generate-report")
        data = json.loads((directory / "honua-attribute-filter-run1.json").read_text())
        self.assertEqual(({}, None), report.parse_k6_summary(data, "attribute-filter"))

    def test_one_bad_run_cannot_hide_behind_median(self):
        gate = load_script("check-regression")
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            for run in range(1, 4):
                data = copy.deepcopy(self.data)
                if run == 3:
                    data["metrics"]["errors"]["value"] = 0.9
                (directory / f"honua-attribute-filter-run{run}.json").write_text(json.dumps(data))
            failures = gate.validate_results_complete(directory, "honua", ["attribute-filter"], 3, None)
            self.assertTrue(any("run3" in reason for reason in failures))

    def test_report_shows_zero_errors_for_valid_legacy_summary(self):
        report = load_script("generate-report")
        metrics = self.data["metrics"]
        metrics["http_reqs{query_type:equality}"] = metrics["http_reqs"]
        metrics["http_req_duration{query_type:equality}"] = metrics["http_req_duration"]
        scenarios, _ = report.parse_k6_summary(self.data, "attribute-filter")
        self.assertEqual(0, scenarios["equality"]["error_rate_pct"])

    def test_cli_refuses_to_overwrite_baseline_with_archived_failures(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "baseline.json"
            output.write_text("original baseline")
            result = subprocess.run([
                sys.executable, str(ROOT / "scripts/check-regression.py"),
                "--results-dir", str(ROOT / "results/releases/v2026.1-rc.0"),
                "--server", "honua", "--tests", "attribute-filter", "--expected-runs", "3",
                "--save-baseline", str(output),
            ], capture_output=True, text=True, check=False)
            self.assertNotEqual(0, result.returncode)
            self.assertEqual("original baseline", output.read_text())

    def test_report_marks_missing_runs_invalid(self):
        report = load_script("generate-report")
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / "benchmark-metadata.json").write_text(json.dumps({
                "servers": ["honua"], "tests": {"attribute-filter": {}},
            }))
            report.generate_report(temp, str(directory / "report.md"), 3, ["honua"])
            data = json.loads((directory / "report.json").read_text())
            self.assertFalse(data["valid"])
            self.assertEqual(3, len(data["invalid_runs"]))


if __name__ == "__main__":
    unittest.main()
