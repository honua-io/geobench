import contextlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

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
            {
                "id": cid,
                "state": "restarts=0",
                "load": [1, 1, 1],
                "gc_pause_seconds_total": value,
            }
            for cid, value in [("a", 2), ("a", 3), ("b", 10), ("b", 12)]
        ]
        self.assertEqual(3, self.summary(rows)["gc_pause_seconds_observed_delta"])

    def test_pause_deltas_do_not_cross_process_restarts_with_same_container(self):
        rows = [
            {
                "id": "a",
                "load": [1, 1, 1],
                "state": f"restarts={restart}",
                "gc_pause_seconds_total": value,
            }
            for restart, value in [(0, 2), (0, 3), (1, 10), (1, 12)]
        ]
        self.assertEqual(3, self.summary(rows)["gc_pause_seconds_observed_delta"])

    def test_sampler_discards_counter_when_process_restarts_during_metrics(self):
        before = "running exit=0 oom=false restarts=0 health=healthy started=old pid=10"
        after = "running exit=0 oom=false restarts=1 health=healthy started=new pid=11"
        completed = lambda output: subprocess.CompletedProcess([], 0, output, "")
        stop = Mock()
        stop.wait.side_effect = [False, True]
        response = Mock()
        response.read.return_value = b"dotnet_gc_pause_time_seconds_total 10\n"
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with tempfile.TemporaryDirectory() as temporary:
            prefix = Path(temporary) / "runtime"
            with (
                patch.object(
                    gc.subprocess,
                    "run",
                    side_effect=[
                        completed("cid"),
                        completed(""),
                        completed(before),
                        completed(after),
                    ],
                ),
                patch.object(gc, "sh", return_value=completed("")),
                patch.object(gc, "urlopen", return_value=response),
            ):
                gc.capture_server({"HONUA_PORT": "8000"}, prefix, stop)
            sample = json.loads(prefix.with_suffix(".samples.jsonl").read_text())
            self.assertNotIn("gc_pause_seconds_total", sample)
            self.assertEqual(
                "container lifetime changed during metrics collection",
                sample["gc_metrics_error"],
            )

    def run_until_keyring(self, revision):
        calls = []
        image = "sha256:" + "a" * 64

        def shell(*args, **kwargs):
            calls.append(args)
            output = ""
            if args[:3] == ("docker", "image", "inspect"):
                output = json.dumps(
                    [
                        {
                            "Config": {
                                "Labels": {
                                    "org.opencontainers.image.revision": revision,
                                    "honua.runtime.compilation": "native-aot",
                                }
                            }
                        }
                    ]
                )
            if args[:2] == ("docker", "cp"):
                return subprocess.CompletedProcess(args, 1, "", "")
            return subprocess.CompletedProcess(args, 0, output, "")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "scripts").mkdir()
            (root / "scripts/run-benchmark.sh").touch()
            (root / "data/small").mkdir(parents=True)
            (root / "data/small/init.sql").touch()
            with (
                contextlib.chdir(root),
                patch.object(gc, "sh", side_effect=shell),
                patch.object(gc.os, "getloadavg", return_value=(0, 0, 0)),
                patch.object(
                    gc, "make_keyring", side_effect=RuntimeError("stop at keyring")
                ),
                patch.object(
                    sys, "argv", [str(SCRIPT), "--image", image, "--source", "b" * 40]
                ),
            ):
                try:
                    gc.main()
                except RuntimeError as exc:
                    return str(exc), calls
        self.fail("expected diagnostic to stop")

    def test_source_mismatch_is_rejected(self):
        message, _ = self.run_until_keyring("c" * 40)
        self.assertEqual("image revision mismatch", message)

    def test_source_mismatch_is_rejected_with_python_optimization(self):
        result = subprocess.run(
            [
                sys.executable,
                "-O",
                str(Path(__file__).resolve()),
                "GcDiagnosticTests.test_source_mismatch_is_rejected",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_image_validation_never_mutates_a_shared_tag(self):
        message, calls = self.run_until_keyring("b" * 40)
        self.assertEqual("stop at keyring", message)
        self.assertFalse(
            any(call[:2] in [("docker", "tag"), ("docker", "rmi")] for call in calls),
            calls,
        )

    def test_compose_override_uses_the_validated_immutable_image(self):
        image = "sha256:" + "a" * 64
        rendered = gc.override(
            "Small", dict(gc.SIZES["Small"], gc_profile="defaults"), 5433, image
        )
        self.assertIn(f"    image: {image}\n", rendered)

    def test_pause_counter_without_process_lifetime_stays_unknown(self):
        rows = [
            {"id": "a", "load": [1, 1, 1], "gc_pause_seconds_total": value}
            for value in [2, 3]
        ]
        self.assertIsNone(self.summary(rows)["gc_pause_seconds_observed_delta"])

    def test_pause_counter_reset_does_not_report_a_delta(self):
        rows = [
            {
                "id": "a",
                "state": "restarts=0",
                "load": [1, 1, 1],
                "gc_pause_seconds_total": value,
            }
            for value in [2, 5, 1, 6]
        ]
        self.assertIsNone(self.summary(rows)["gc_pause_seconds_observed_delta"])

    def test_invalid_selection_fails_before_docker_or_artifact_creation(self):
        for flag, value in [
            ("--sizes", "Unknown"),
            ("--levels", "0"),
            ("--levels", "1,1"),
            ("--max-load", "nan"),
            ("--max-load", "inf"),
            ("--max-load", "0"),
            ("--max-load", "-1"),
            ("--max-load", "16.01"),
            ("--max-load", "96"),
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

    def test_busy_host_refuses_before_any_docker_command(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "scripts").mkdir()
            (root / "scripts/run-benchmark.sh").touch()
            with (
                contextlib.chdir(root),
                patch.object(gc, "sh") as shell,
                patch.object(gc.os, "getloadavg", return_value=(17, 0, 0)),
                patch.object(
                    sys,
                    "argv",
                    [str(SCRIPT), "--image", "sha256:" + "a" * 64,
                     "--source", "b" * 40, "--max-load", "16"],
                ),
            ):
                self.assertEqual(3, gc.main())
                shell.assert_not_called()
            result = json.loads(next(root.glob("artifacts/**/result.json")).read_text())
            self.assertEqual("NOT_QUIET", result["verdict"])
            self.assertEqual(17, result["load_at_start"]["load1"])


if __name__ == "__main__":
    unittest.main()
