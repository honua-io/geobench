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
from benchmark_config import resolve_workflow_image
from k6_results import validation_failures


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

    def test_malformed_metric_objects_produce_invalid_reports(self):
        report = load_script("generate-report")
        cases = [{"metrics": None}, {"metrics": []}]
        for name in self.data["metrics"]:
            data = copy.deepcopy(self.data)
            data["metrics"][name] = "bad"
            cases.append(data)
        for data in cases:
            with self.subTest(data=data), tempfile.TemporaryDirectory() as temp:
                self.assertTrue(validation_failures(data))
                directory = Path(temp)
                filename = "honua-attribute-filter-run1.json"
                (directory / filename).write_text(json.dumps(data))
                report.generate_report(temp, str(directory / "report.md"), 1, ["honua"])
                result = json.loads((directory / "report.json").read_text())
                self.assertFalse(result["valid"])
                self.assertIn(filename, result["invalid_runs"])

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

    def test_report_requires_wholly_missing_optional_tracks(self):
        report = load_script("generate-report")
        cases = [
            (["honua"], "wms-getmap", False, "honua"),
            (["honua", "geoserver"], "wmts", False, "geoserver"),
            (["honua", "geoserver"], "geoservices-query", False, "honua"),
            (["geoserver"], "geoservices-query", True, "geoserver"),
        ]
        for servers, track, gsr, expected_server in cases:
            with self.subTest(track=track, gsr=gsr), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                (directory / "benchmark-metadata.json").write_text(json.dumps({
                    "servers": servers, "tests": {track: {}},
                    "server_tuning": {"geoserver": {"gsr_enabled": gsr}},
                }))
                report.generate_report(temp, str(directory / "report.md"), 3, servers)
                data = json.loads((directory / "report.json").read_text())
                self.assertFalse(data["valid"])
                self.assertEqual(
                    {f"{expected_server}-{track}-run{run}.json" for run in range(1, 4)},
                    set(data["invalid_runs"]),
                )

    def test_workflow_rejects_custom_release_campaigns(self):
        for config in ({"SERVERS": "geoserver"}, {"TESTS": "wms-getmap"}):
            with self.subTest(config=config), self.assertRaisesRegex(ValueError, "evidence_only"):
                resolve_workflow_image(config)
        self.assertEqual("docker.osgeo.org/geoserver:3.0.1", resolve_workflow_image({}))
        self.assertEqual("docker.osgeo.org/geoserver:3.0.1", resolve_workflow_image({
            "EVIDENCE_ONLY": "true", "SERVERS": "geoserver", "TESTS": "wms-getmap",
        }))

    def test_report_preserves_missing_track_when_another_track_succeeds(self):
        report = load_script("generate-report")
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / "benchmark-metadata.json").write_text(json.dumps({
                "servers": ["honua"], "tests": {"attribute-filter": {}, "wms-getmap": {}},
            }))
            (directory / "honua-attribute-filter-run1.json").write_text(json.dumps(self.data))
            report.generate_report(temp, str(directory / "report.md"), 1, ["honua"])
            data = json.loads((directory / "report.json").read_text())
            self.assertFalse(data["valid"])
            self.assertIn("honua-wms-getmap-run1.json", data["invalid_runs"])

    def test_rebaseline_requires_valid_new_evidence_and_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            result_file = directory / "honua-attribute-filter-run1.json"
            result_file.write_text(json.dumps(self.data))
            baseline = directory / "baseline.json"
            baseline.write_text(json.dumps({"valid": False, "metrics": {}}))
            command = [sys.executable, str(ROOT / "scripts/check-regression.py"),
                       "--results-dir", temp, "--tests", "attribute-filter", "--expected-runs", "1"]

            def run(*arguments):
                return subprocess.run([*command, *arguments], capture_output=True, text=True, check=False)

            self.assertNotEqual(0, run("--baseline", str(baseline)).returncode)
            opted_in = run("--baseline", str(baseline), "--allow-invalid-baseline")
            self.assertEqual(0, opted_in.returncode, opted_in.stdout + opted_in.stderr)
            self.assertFalse(json.loads(baseline.read_text())["valid"])
            saved = run("--save-baseline", str(baseline))
            self.assertEqual(0, saved.returncode, saved.stdout + saved.stderr)
            self.assertTrue(json.loads(baseline.read_text())["valid"])

            # Opt-in does not suppress regressions against a valid baseline.
            self.data["metrics"]["http_req_duration"]["med"] = 100
            result_file.write_text(json.dumps(self.data))
            self.assertNotEqual(0, run("--baseline", str(baseline), "--allow-invalid-baseline").returncode)

            baseline.write_text(json.dumps({"valid": False, "metrics": {}}))
            original = baseline.read_text()
            self.data["metrics"]["errors"]["value"] = 0.5
            result_file.write_text(json.dumps(self.data))
            self.assertNotEqual(0, run("--baseline", str(baseline), "--allow-invalid-baseline").returncode)
            self.assertNotEqual(0, run("--save-baseline", str(baseline)).returncode)
            self.assertEqual(original, baseline.read_text())

    def test_workflow_resolves_matching_gsr_image_and_rejects_stable(self):
        config = {"EVIDENCE_ONLY": "true", "SERVERS": "geoserver",
                  "TESTS": "geoservices-query", "GEOSERVER_GSR_ENABLED": "1"}
        self.assertEqual("docker.osgeo.org/geoserver:3.0.x", resolve_workflow_image(config))
        digest_image = "docker.osgeo.org/geoserver:3.0.x@sha256:" + "a" * 64
        self.assertEqual(digest_image, resolve_workflow_image({**config, "GEOSERVER_IMAGE": digest_image}))
        with self.assertRaisesRegex(ValueError, "matching :3.0.x"):
            resolve_workflow_image({**config, "GEOSERVER_IMAGE": "docker.osgeo.org/geoserver:3.0.1"})

    def test_workflow_rejects_unknown_or_unsupported_selections(self):
        for tracks in ("wmts", "attribute-filter unknown-track"):
            with self.subTest(tracks=tracks), self.assertRaises(ValueError):
                resolve_workflow_image({"EVIDENCE_ONLY": "true", "SERVERS": "honua", "TESTS": tracks})


if __name__ == "__main__":
    unittest.main()
