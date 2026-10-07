import copy
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("publish_results", ROOT / "scripts/publish-results.py")
publisher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publisher)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.run_id = "20261007-control"
        self.raw = self.root / "results" / self.run_id
        self.raw.mkdir(parents=True)
        self.names = [
            "report.md", "report.json", "benchmark-metadata.json",
            "fairness-audit.txt", "system-cards/honua.json",
        ]
        self.write("report.md", "Reviewed benchmark report\n")
        self.write("report.json", {"results": {}, "run_metadata": {"runs": 5}})
        self.write("benchmark-metadata.json", {"servers": ["honua"], "runs": 5})
        self.write("fairness-audit.txt", "PASS: no fairness gotchas detected\n")
        self.write("system-cards/honua.json", {"server": "honua", "image": "example:1.0"})
        self.approval = self.root / "review.json"
        self.approve()

    def write(self, name, value):
        path = self.raw / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value) if isinstance(value, (dict, list)) else value)
        return path

    def approve(self, names=None):
        review = publisher.review_plan(self.root, self.run_id, names or self.names)
        review.update({
            "decision": "approved", "approved_by": "Fixture reviewer",
            "approved_at": "2000-01-01T00:00:00Z",
            "reference": "https://example.invalid/reviews/42",
            "harness_revision": "a" * 40,
            "raw_evidence_reference": "https://example.invalid/evidence/control.zip",
        })
        self.approval.write_text(json.dumps(review))
        return review

    def promote(self, **kwargs):
        return publisher.promote(self.root, self.run_id, self.approval, **kwargs)

    def test_plan_is_pending_and_dry_run_copies_nothing(self):
        plan = publisher.review_plan(self.root, self.run_id, self.names)
        self.assertEqual(plan["decision"], "pending")
        self.assertIsNone(plan["approved_by"])
        self.assertEqual(self.promote()["mode"], "dry-run")
        self.assertFalse((self.root / "published").exists())
        self.assertEqual((self.raw / "report.md").read_text(), "Reviewed benchmark report\n")

    def test_pending_decision_or_missing_approval_fields_never_publish(self):
        original = json.loads(self.approval.read_text())
        for key, value in [
            ("decision", "pending"), ("approved_by", ""), ("approved_at", "2000-01-01"),
            ("reference", "http://example.invalid/review"),
            ("harness_revision", "trunk"), ("run_id", "different"),
            ("approved_at", "2999-01-01T00:00:00Z"),
        ]:
            with self.subTest(key=key, value=value):
                review = copy.deepcopy(original)
                review[key] = value
                self.approval.write_text(json.dumps(review))
                with self.assertRaises(ValueError):
                    self.promote(apply=True)
                self.assertFalse((self.root / "published").exists())

    def test_approved_small_package_is_verified_raw_retained_and_no_wholesale_copy(self):
        self.write("samples/raw.jsonl", '{"raw": true}\n')
        self.write("harness/.git", "gitdir: /elsewhere")
        self.write(".env", "PASSWORD=private")
        result = self.promote(apply=True)
        package = Path(result["destination"])
        self.assertEqual(publisher.verify_package(package, self.run_id)["mode"], "verified")
        self.assertEqual({p.relative_to(package).as_posix() for p in package.rglob("*") if p.is_file()},
                         set(self.names) | {"approval.json", "publication.json"})
        self.assertTrue((self.raw / "samples/raw.jsonl").exists())
        self.assertTrue((self.raw / ".env").exists())
        self.assertTrue((self.raw / "harness/.git").exists())
        self.assertEqual(json.loads((package / "publication.json").read_text())["harness_revision"], "a" * 40)

    def test_approval_binds_reviewed_bytes(self):
        self.write("report.md", "Changed after approval")
        with self.assertRaisesRegex(ValueError, "changed after review"):
            self.promote(apply=True)
        self.assertFalse((self.root / "published").exists())

    def test_existing_approved_destination_is_never_overwritten(self):
        self.promote(apply=True)
        package = self.root / "published" / self.run_id
        original = (package / "publication.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.promote(apply=True)
        self.assertEqual((package / "publication.json").read_bytes(), original)

    def test_concurrent_promotion_lock_is_preserved(self):
        (self.root / "published").mkdir()
        lock = self.root / "published" / f".{self.run_id}.publishing"
        lock.write_text("another promoter")
        with self.assertRaises(FileExistsError):
            self.promote(apply=True)
        self.assertEqual(lock.read_text(), "another promoter")
        self.assertFalse((self.root / "published" / self.run_id).exists())

    def test_source_changes_during_staging_abort_and_remove_only_owned_stage(self):
        with self.assertRaisesRegex(ValueError, "changed during promotion"):
            self.promote(apply=True, before_commit=lambda: self.write("report.md", "Changed while staging"))
        self.assertEqual(list((self.root / "published").iterdir()), [])
        self.assertTrue(self.raw.exists())

    def test_approval_changes_during_staging_abort(self):
        def change():
            approval = json.loads(self.approval.read_text())
            approval["reference"] = "https://example.invalid/different"
            self.approval.write_text(json.dumps(approval))
        with self.assertRaisesRegex(ValueError, "changed during promotion"):
            self.promote(apply=True, before_commit=change)
        self.assertEqual(list((self.root / "published").iterdir()), [])

    def test_destination_created_during_staging_is_not_overwritten(self):
        destination = self.root / "published" / self.run_id
        with self.assertRaisesRegex(ValueError, "destination appeared"):
            self.promote(apply=True, before_commit=destination.mkdir)
        self.assertTrue(destination.is_dir())
        self.assertEqual(list(destination.iterdir()), [])
        self.assertTrue(self.raw.exists())

    def test_traversal_raw_files_checkouts_and_binaries_are_not_selectable(self):
        for name in ["../report.md", "/report.md", "system-cards/../report.json",
                     ".env", "raw.jsonl", "harness/campaign.json", "pgdata/data.db", "report.exe"]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                publisher.collect(self.root, self.run_id, self.names + [name])
        for run_id in ["../outside", "baselines", "releases", "CON", "LPT1", ".hidden", "run/child"]:
            with self.subTest(run_id=run_id), self.assertRaises(ValueError):
                publisher.run_name(run_id)
        self.write(".git", "gitdir: /a/checkout")
        with self.assertRaisesRegex(ValueError, "not a Git checkout"):
            self.promote()

    def test_selected_artifact_symlink_and_linked_result_parent_are_refused(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "report.md").write_text("outside")
        (self.raw / "report.md").unlink()
        try:
            (self.raw / "report.md").symlink_to(outside / "report.md")
        except OSError:
            self.skipTest("symlink creation unavailable")
        with self.assertRaisesRegex(ValueError, "linked path"):
            self.promote(apply=True)
        (self.raw / "report.md").unlink()
        self.write("report.md", "Reviewed benchmark report\n")
        self.raw.rename(self.root / "original")
        self.raw.symlink_to(self.root / "original", target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "linked path"):
            self.promote(apply=True)

    def test_selected_nested_checkout_or_hardlink_is_refused(self):
        self.write("system-cards/.git", "gitdir: /elsewhere")
        with self.assertRaisesRegex(ValueError, "working Git checkout"):
            self.promote()
        (self.raw / "system-cards/.git").unlink()
        other = self.root / "linked-report"
        os.link(self.raw / "report.md", other)
        with self.assertRaisesRegex(ValueError, "independent small regular file"):
            self.promote()

    def test_missing_metadata_card_failing_audit_and_failed_report_are_refused(self):
        for name in ["benchmark-metadata.json", "system-cards/honua.json"]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                publisher.collect(self.root, self.run_id, [n for n in self.names if n != name])
        self.write("fairness-audit.txt", "FAIL: unequal resource budget\n")
        with self.assertRaisesRegex(ValueError, "fairness audit"):
            publisher.collect(self.root, self.run_id, self.names)
        self.write("fairness-audit.txt", "PASS: no fairness gotchas detected\n")
        self.write("report.json", {"publishable": False})
        with self.assertRaisesRegex(ValueError, "failed publication gate"):
            publisher.collect(self.root, self.run_id, self.names)

    def test_feature_gate_cannot_be_bypassed_by_human_approval(self):
        self.write("campaign.json", {"mode": "comparison", "binding": "original"})
        names = ["report.md", "report.json", "campaign.json"]
        for mode, valid, publishable, failures in [
            ("diagnostic", True, True, []), ("comparison", False, True, []),
            ("comparison", True, False, []), ("comparison", True, True, ["invalid samples"]),
        ]:
            with self.subTest(mode=mode, valid=valid, publishable=publishable):
                self.write("campaign.json", {"mode": mode})
                self.write("report.json", {"valid": valid, "publishable": publishable,
                                          "publication_failures": failures})
                with self.assertRaisesRegex(ValueError, "publication gates"):
                    publisher.collect(self.root, self.run_id, names)
        self.write("report.json", {"valid": True, "publishable": True,
                                  "failures": [], "publication_failures": []})
        self.approve(names)
        package = Path(self.promote(apply=True)["destination"])
        self.assertEqual(publisher.verify_package(package, self.run_id)["artifacts"], 3)

    def test_credentials_and_nonfinite_or_duplicate_json_are_refused(self):
        for contents in [
            '{"password":"private"}', '{"env":{"POSTGRES_PASSWORD":"private"}}',
            '{"note":"postgresql://user:private@host/db"}', '{"note":"Password=private;"}',
            '{"note":"-----BEGIN PRIVATE KEY-----"}',
            '{"value":NaN}', '{"value":1e9999}', '{"value":1,"value":2}',
        ]:
            with self.subTest(contents=contents), self.assertRaises(ValueError):
                self.write("benchmark-metadata.json", contents)
                publisher.collect(self.root, self.run_id, self.names)

    def test_large_artifacts_and_package_are_refused(self):
        self.write("report.md", "x" * (publisher.MAX_FILE_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "small regular file"):
            publisher.collect(self.root, self.run_id, self.names)
        self.write("report.md", "Reviewed benchmark report\n")
        with patch.object(publisher, "MAX_PACKAGE_BYTES", 16), self.assertRaisesRegex(ValueError, "16 MiB"):
            publisher.collect(self.root, self.run_id, self.names)

    def test_verifier_detects_tampering_provenance_changes_and_unknown_entries(self):
        package = Path(self.promote(apply=True)["destination"])
        for target, contents in [
            ("report.md", "tampered"),
            ("extra.json", "{}"),
        ]:
            with self.subTest(target=target):
                path = package / target
                original = path.read_bytes() if path.exists() else None
                path.write_text(contents)
                with self.assertRaises(ValueError):
                    publisher.verify_package(package, self.run_id)
                path.unlink() if original is None else path.write_bytes(original)
        manifest_path = package / "publication.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["harness_revision"] = "b" * 40
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "manifest"):
            publisher.verify_package(package, self.run_id)

    def test_cli_dry_run_and_failure_have_useful_exit_statuses(self):
        with patch.object(publisher, "ROOT", self.root):
            with patch("sys.stdout"):
                self.assertEqual(publisher.main(["promote", self.run_id, "--approval",
                                                 str(self.approval), "--dry-run"]), 0)
            self.write("report.md", "changed")
            with patch("sys.stderr"):
                self.assertEqual(publisher.main(["promote", self.run_id, "--approval",
                                                 str(self.approval), "--apply"]), 1)


class PublicationIgnoreTests(unittest.TestCase):
    def test_release_automation_uploads_raw_evidence_without_git_publication(self):
        workflow = (ROOT / ".github/workflows/benchmark-on-release.yml").read_text()
        self.assertIn("--baseline \"results/baselines/honua-baseline.json\"", workflow)
        self.assertIn('--save-baseline "results/${RESULT_TIMESTAMP}/honua-baseline.json"', workflow)
        self.assertIn("actions/upload-artifact@", workflow)
        self.assertIn("path: results/${{ steps.ts.outputs.ts }}/", workflow)
        self.assertNotIn("GEOBENCH_RESULTS_PUSH_TOKEN", workflow)
        self.assertNotIn("results/releases/", workflow)
        for command in ("git add", "git commit", "git push", "publish-results.py promote"):
            with self.subTest(command=command):
                self.assertNotIn(command, workflow)

    def test_raw_outputs_ignored_published_trackable_and_legacy_contracts_retained(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            historical = ["results/baselines/honua-baseline.json", "results/releases/legacy/report.json"]
            for name in historical:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}")
            subprocess.run(["git", "-C", str(root), "add", *historical], check=True)
            (root / ".gitignore").write_bytes((ROOT / ".gitignore").read_bytes())
            checks = {
                "results/raw-summary.json": True,
                "results/20261007/raw.jsonl": True,
                "results/20261007/harness/.git": True,
                "published/20261007/report.md": False,
                "published/20261007/publication.json": False,
                "published/.20261007.staging-abc/report.md": True,
                "published/.20261007.publishing": True,
                "results/baselines/honua-baseline.json": False,
                "results/releases/legacy/report.json": False,
                "results/baselines/new-raw.json": True,
                "results/baselines/nested/report.json": True,
                "results/releases/v2026.1/new-raw.json": True,
                "results/.gitkeep": False,
                ".env": True,
            }
            for name, ignored in checks.items():
                with self.subTest(name=name):
                    result = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", name], check=False)
                    self.assertEqual(result.returncode == 0, ignored)
            subprocess.run(["git", "-C", str(root), "ls-files", "--error-unmatch", *historical],
                           check=True, capture_output=True)
