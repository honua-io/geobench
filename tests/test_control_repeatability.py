import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("repeatability", ROOT / "scripts/run-control-repeatability.py")
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


def fixture():
    manifests = {arm: {"scenarios": ["bbox-small"]} for arm in control.ARMS}
    row = {"throughput": 100, "latency_ms": {"p50": 10, "p95": 20, "p99": 30},
           "counts": {}, "failures": [], "warmup": {"counts": {}, "failures": []}}
    ledgers = {arm: [{"id": f"pair{rep}-honua", "repetition": rep, "status": "passed", "cleaned": True,
                      "rows": {"bbox-small": copy.deepcopy(row)}, "database_fingerprint": "same-db",
                      "response_contract": {"fields": ["id"], "exact_count": True}}
                     for rep in range(1, 4)] for arm in control.ARMS}
    reports = {arm: {"valid": True, "failures": []} for arm in control.ARMS}
    return manifests, ledgers, reports


class RepeatabilityTests(unittest.TestCase):
    def test_execution_requires_explicit_approval_before_loading_runner_or_starting_traffic(self):
        for note in (None, "", "   "):
            with self.subTest(note=note), patch.object(control, "runner_module") as runner:
                args = ["--execute", "--output", str(ROOT / "results/approval-test")]
                if note is not None:
                    args += ["--approval-note", note]
                with self.assertRaisesRegex(ValueError, "explicit operator approval"):
                    control.main(args)
                runner.assert_not_called()

    def test_prepare_mode_never_executes_attempts(self):
        runner = Mock()
        with patch.object(control, "runner_module", return_value=runner), patch.object(control, "prepare") as prepare:
            self.assertEqual(0, control.main(["--output", str(ROOT / "results/prepare-test")]))
        prepare.assert_called_once()
        runner.execute_attempt.assert_not_called()

    def test_real_preparation_calls_only_prepare_commands_and_records_load_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "campaign"
            runner = Mock()
            runner.write.side_effect = lambda path, value: path.write_text(json.dumps(value))
            manifest = {"binding": "identical", "scenarios": ["bbox-small", "range", "page-medium"],
                        "images": {"honua": {"id": "same-image"}}, "profile": "diagnostic",
                        "budget": {"cpus": 4}, "generator_budget": {"cpus": 8}, "warmup": 30, "measurement": 30}

            def prepare_command(command, **kwargs):
                target = Path(command[command.index("--output") + 1])
                target.mkdir()
                (target / "campaign.json").write_text(json.dumps(manifest))

            args = SimpleNamespace(scenarios=control.DEFAULT_SCENARIOS, seed=42, honua_profile="automatic-bounded",
                                   generator_cpus=8, control_host="localhost", honua_image="pinned-server",
                                   postgis_image="pinned-database", k6_image="pinned-generator")
            with patch.object(control.subprocess, "run", side_effect=prepare_command) as run, patch("builtins.print"):
                plan = control.prepare(runner, directory, args)
            self.assertEqual(2, run.call_count)
            for call in run.call_args_list:
                self.assertIn("--prepare-only", call.args[0])
            runner.execute_attempt.assert_not_called()
            self.assertEqual(1080, plan["scope"]["active_traffic_seconds"])
            self.assertEqual(2340, plan["scope"]["traffic_and_maximum_drain_seconds"])
            with self.assertRaisesRegex(ValueError, "new output directory"):
                control.prepare(runner, directory, args)

    def test_pair_order_is_recorded_seeded_and_alternating(self):
        order = control.pair_order(42)
        self.assertEqual(order, control.pair_order(42))
        self.assertEqual(order[0], order[2])
        self.assertEqual(order[0][::-1], order[1])
        self.assertEqual(set(control.ARMS), set(order[0]))

    def test_complete_stable_control_passes_without_a_publication_claim(self):
        result = control.repeatability_report(*fixture())
        self.assertTrue(result["same_image_repeatable"])
        self.assertFalse(result["publication_ready"])
        row = result["scenarios"]["bbox-small"]
        self.assertEqual(6, len(row["repetitions"]))
        self.assertEqual(3, len(row["paired_ratios"]))
        self.assertEqual(20, row["summary_of_repetitions"]["p95"]["median_of_repetitions"])

    def test_outlier_cannot_be_hidden_by_equal_arm_medians(self):
        manifests, ledgers, reports = fixture()
        ledgers["control-a"][0]["rows"]["bbox-small"]["throughput"] = 50
        # Both arm medians are still 100. The six-sample range must fail.
        result = control.repeatability_report(manifests, ledgers, reports)
        self.assertFalse(result["same_image_repeatable"])
        self.assertIn("bbox-small: throughput spread exceeds 5%", result["failures"])

    def test_p95_spread_is_checked_separately_from_throughput(self):
        manifests, ledgers, reports = fixture()
        ledgers["control-b"][1]["rows"]["bbox-small"]["latency_ms"]["p95"] = 25
        result = control.repeatability_report(manifests, ledgers, reports)
        self.assertIn("bbox-small: p95 spread exceeds 5%", result["failures"])

    def test_missing_duplicate_failed_and_unclean_attempts_fail_closed(self):
        for change in (lambda ledger: ledger.pop(), lambda ledger: ledger.append(ledger[0]),
                       lambda ledger: ledger[0].update(status="interrupted"),
                       lambda ledger: ledger[0].update(cleaned=False),
                       lambda ledger: ledger[0].update(rows={})):
            manifests, ledgers, reports = fixture()
            change(ledgers["control-a"])
            self.assertFalse(control.repeatability_report(manifests, ledgers, reports)["same_image_repeatable"])

    def test_clock_anomalies_in_either_phase_fail_even_if_diagnostic_report_is_valid(self):
        for phase in ("measurement", "warmup"):
            manifests, ledgers, reports = fixture()
            row = ledgers["control-a"][0]["rows"]["bbox-small"]
            part = row if phase == "measurement" else row["warmup"]
            part["counts"]["clock_anomalies"] = 1
            self.assertFalse(control.repeatability_report(manifests, ledgers, reports)["same_image_repeatable"])

    def test_invalid_or_missing_phase_statistics_fail_closed(self):
        for value in (0, -1, None, float("nan"), float("inf")):
            manifests, ledgers, reports = fixture()
            ledgers["control-a"][0]["rows"]["bbox-small"]["latency_ms"]["p95"] = value
            self.assertFalse(control.repeatability_report(manifests, ledgers, reports)["same_image_repeatable"])
        manifests, ledgers, reports = fixture()
        del ledgers["control-a"][0]["rows"]["bbox-small"]["warmup"]
        self.assertFalse(control.repeatability_report(manifests, ledgers, reports)["same_image_repeatable"])

    def test_cross_arm_database_and_response_contract_drift_fails(self):
        for key in ("database_fingerprint", "response_contract"):
            manifests, ledgers, reports = fixture()
            ledgers["control-b"][0][key] = "different"
            self.assertFalse(control.repeatability_report(manifests, ledgers, reports)["same_image_repeatable"])

    def test_artifact_integrity_failure_is_not_overridden_by_stable_numbers(self):
        manifests, ledgers, reports = fixture()
        reports["control-a"] = {"valid": False, "failures": ["raw artifact changed"]}
        result = control.repeatability_report(manifests, ledgers, reports)
        self.assertIn("control-a: raw artifact changed", result["failures"])

    def test_changed_plan_is_rejected_before_any_runtime_call(self):
        runner = Mock()
        plan = {"seed": 42, "order": control.pair_order(42)}
        plan["binding"] = control.fingerprint(plan)
        plan["seed"] = 12
        with self.assertRaisesRegex(ValueError, "plan has changed"):
            control.validate_prepared(runner, ROOT / "results/test", plan)
        runner.host_identity.assert_not_called()

    def test_prepared_fingerprints_reject_each_drift_before_traffic(self):
        for drift in ("harness", "commit", "host", "dataset", "workload", "image", "configuration", "attempts"):
            with self.subTest(drift=drift), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / "data/small").mkdir(parents=True)
                (root / "data/small/init.sql").write_text("deterministic dataset")
                (root / "config").mkdir()
                (root / "config/feature-corpus-v1.json").write_text("{}")
                directory = root / "results/control"
                manifest = {"binding": "identical", "harness": {"content": "harness", "commit": "prepared-commit"},
                            "host_identity": {"host": "same"}, "corpus": {},
                            "dataset_sha256": control.digest(root / "data/small/init.sql"),
                            "images": {"honua": {"reference": "sha256:pinned"}},
                            "honua_profile": "baseline", "generator_budget": {"cpus": 8},
                            "control_host": "localhost", "effective_compose": {"honua": {"pool": 6}}}
                for arm in control.ARMS:
                    (directory / arm).mkdir(parents=True)
                    (directory / arm / "campaign.json").write_text(json.dumps(manifest))
                    (directory / arm / "attempts.json").write_text("[]")
                plan = {"seed": 42, "order": control.pair_order(42), "campaign_binding": "identical",
                        "campaign_sha256": {arm: control.digest(directory / arm / "campaign.json") for arm in control.ARMS}}
                plan["binding"] = control.fingerprint(plan)
                runner = Mock()
                runner.source_fingerprint.return_value = "harness"
                runner.command.return_value = "prepared-commit"
                runner.host_identity.return_value = {"host": "same"}
                runner.resolve_images.return_value = manifest["images"]
                runner.make_compose.return_value = {"pool": 6}
                if drift == "harness":
                    runner.source_fingerprint.return_value = "changed"
                elif drift == "commit":
                    runner.command.return_value = "changed"
                elif drift == "host":
                    runner.host_identity.return_value = {"host": "different"}
                elif drift == "dataset":
                    (root / "data/small/init.sql").write_text("different data")
                elif drift == "workload":
                    (root / "config/feature-corpus-v1.json").write_text('{"request": "different"}')
                elif drift == "image":
                    runner.resolve_images.return_value = {"honua": {"reference": "different"}}
                elif drift == "configuration":
                    runner.make_compose.return_value = {"pool": 7}
                else:
                    (directory / control.ARMS[0] / "attempts.json").write_text('[{"status":"interrupted"}]')
                with patch.object(control, "ROOT", root), self.assertRaises(ValueError):
                    control.validate_prepared(runner, directory, plan)
                runner.execute_attempt.assert_not_called()

    def test_interruption_and_failure_write_terminal_receipt_and_retain_not_run_attempts(self):
        for error, status in ((KeyboardInterrupt(), "interrupted"), (ValueError("provision failed"), "failed")):
            with tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                for arm in control.ARMS:
                    (directory / arm).mkdir()
                runner = SimpleNamespace(
                    write=lambda path, value: path.write_text(json.dumps(value)),
                    execute_attempt=Mock(side_effect=error),
                    report=lambda path, manifest, attempts: {"valid": False, "failures": ["incomplete"]})
                manifests = {arm: {"scenarios": ["bbox-small"]} for arm in control.ARMS}
                plan = {"binding": "prepared", "order": control.pair_order(42)}
                with patch.object(control, "validate_prepared", return_value=manifests):
                    with self.assertRaises(type(error)):
                        control.execute(runner, directory, plan, "Approved by operator for this window")
                receipt = json.loads((directory / "execution.json").read_text())
                self.assertEqual(status, receipt["status"])
                statuses = [attempt["status"] for ledger in receipt["attempts"].values() for attempt in ledger]
                self.assertEqual(5, statuses.count("not-run"))
                self.assertEqual(1, statuses.count("interrupted"))
                self.assertFalse(json.loads((directory / "repeatability-report.json").read_text())["same_image_repeatable"])
                with self.assertRaisesRegex(ValueError, "execution already exists"):
                    control.execute(runner, directory, plan, "Another approval")


if __name__ == "__main__":
    unittest.main()
