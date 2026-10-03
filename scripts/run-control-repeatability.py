#!/usr/bin/env python3
"""Prepare an explicitly approved, same-image A/A diagnostic before optimization timing."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import math
import os
import random
import signal
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from feature_contract import DRAIN_SECONDS, HONUA_PROFILES, fingerprint

ROOT = Path(__file__).resolve().parents[1]
ARMS = ("control-a", "control-b")
DEFAULT_SCENARIOS = "bbox-small,range,page-medium"


def runner_module():
    spec = importlib.util.spec_from_file_location("repeatability_campaign", ROOT / "scripts/run-feature-campaign.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pair_order(seed):
    first = random.Random(seed).randrange(2)
    return [list(ARMS[(first + rep) % 2:] + ARMS[:(first + rep) % 2]) for rep in range(3)]


def require_approval(execute, note):
    if execute and (not note or not note.strip()):
        raise ValueError("Execution requires fresh explicit operator approval recorded with --approval-note; idle host load is not approval")


def positive_finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def prepare(runner, directory, args):
    if directory.exists():
        raise ValueError("Use a new output directory; failed attempts and their plans cannot be replaced")
    directory.mkdir(parents=True)
    manifests = {}
    for arm in ARMS:
        command = [sys.executable, str(ROOT / "scripts/run-feature-campaign.py"),
                   "--prepare-only", "--mode", "diagnostic", "--servers", "honua",
                   "--scenarios", args.scenarios, "--seed", str(args.seed),
                   "--honua-profile", args.honua_profile, "--generator-cpus", str(args.generator_cpus),
                   "--control-host", args.control_host, "--output", str(directory / arm)]
        for key in ("honua", "postgis", "k6"):
            command.extend(["--" + key + "-image", getattr(args, key + "_image")])
        subprocess.run(command, check=True, cwd=ROOT)
        manifests[arm] = json.loads((directory / arm / "campaign.json").read_text())
    a, b = (manifests[arm] for arm in ARMS)
    if a["binding"] != b["binding"]:
        raise ValueError("A/A arms must have identical workload, images, dataset, host, configuration and harness")
    phases = 6 * len(a["scenarios"])
    plan = {"schema": 1, "kind": "same-image-repeatability", "publication_ready": False,
            "campaign_binding": a["binding"], "seed": args.seed, "order": pair_order(args.seed),
            "maximum_relative_spread": .05,
            "campaign_sha256": {arm: digest(directory / arm / "campaign.json") for arm in ARMS},
            "scope": {"dataset": "100K points", "scenarios": a["scenarios"],
                      "honua_image": a["images"]["honua"]["id"], "profile": a["profile"],
                      "server_database_budget": a["budget"], "generator_budget": a["generator_budget"],
                      "paired_repetitions": 3, "warmup_seconds": a["warmup"],
                      "measurement_seconds": a["measurement"], "drain_seconds_per_phase": DRAIN_SECONDS,
                      "active_traffic_seconds": phases * (a["warmup"] + a["measurement"]),
                      "traffic_and_maximum_drain_seconds": phases * (a["warmup"] + a["measurement"] + 2 * DRAIN_SECONDS)},
            "authorization_required": "Fresh explicit approval before execute; no automatic waiting for a quiet host"}
    plan["binding"] = fingerprint(plan)
    runner.write(directory / "repeatability-plan.json", plan)
    print(json.dumps(plan, indent=2))
    return plan


def validate_prepared(runner, directory, plan):
    body = {key: value for key, value in plan.items() if key != "binding"}
    if fingerprint(body) != plan["binding"] or plan["order"] != pair_order(plan["seed"]):
        raise ValueError("Prepared plan has changed")
    manifests = {}
    for arm in ARMS:
        path = directory / arm
        if digest(path / "campaign.json") != plan["campaign_sha256"][arm]:
            raise ValueError("Prepared campaign has changed")
        manifest = json.loads((path / "campaign.json").read_text())
        if manifest["binding"] != plan["campaign_binding"]:
            raise ValueError("Prepared arms no longer match")
        if manifest["harness"]["content"] != runner.source_fingerprint():
            raise ValueError("Harness fingerprint drift; prepare a new plan")
        if manifest["host_identity"] != runner.host_identity():
            raise ValueError("Host/Docker identity drift; prepare a new plan")
        if digest(ROOT / "data/small/init.sql") != manifest["dataset_sha256"]:
            raise ValueError("Dataset fingerprint drift; prepare a new plan")
        if json.loads((ROOT / "config/feature-corpus-v1.json").read_text()) != manifest["corpus"]:
            raise ValueError("Workload drift; prepare a new plan")
        image_args = SimpleNamespace(mode="diagnostic", servers=["honua"],
                                     **{key + "_image": image["reference"] for key, image in manifest["images"].items()})
        if runner.resolve_images(image_args) != manifest["images"]:
            raise ValueError("Image fingerprint drift; prepare a new plan")
        composition = runner.make_compose("fingerprint", "honua", manifest["images"], manifest["honua_profile"],
                                          manifest["generator_budget"]["cpus"], manifest["control_host"])
        if composition != manifest["effective_compose"]["honua"]:
            raise ValueError("Effective configuration drift; prepare a new plan")
        runner.verify_snapshot(path, manifest)
        if json.loads((path / "attempts.json").read_text()):
            raise ValueError("Prepared campaign already has attempts; retries require a new plan and approval")
        manifests[arm] = manifest
    return manifests


def repeatability_report(manifests, ledgers, reports):
    """Gate on all six measurements, never median-of-medians alone or averaged percentiles."""
    failures, rows = [], {}
    expected = {(rep, arm) for rep in range(1, 4) for arm in ARMS}
    actual = [(attempt["repetition"], arm) for arm in ARMS for attempt in ledgers[arm]]
    if set(actual) != expected or len(actual) != len(set(actual)):
        failures.append("missing or duplicate scheduled repetitions")
    for arm in ARMS:
        if not reports[arm]["valid"]:
            failures.extend(f"{arm}: {reason}" for reason in reports[arm]["failures"])
        for attempt in ledgers[arm]:
            if attempt.get("status") != "passed" or not attempt.get("cleaned"):
                failures.append(f"{arm}/{attempt['id']}: incomplete/failed attempt or owned cleanup")
            if set(attempt.get("rows", {})) != set(manifests[arm]["scenarios"]):
                failures.append(f"{arm}/{attempt['id']}: missing scenarios")
            for scenario, row in attempt.get("rows", {}).items():
                if not row.get("warmup") or row.get("failures") or row["warmup"].get("failures"):
                    failures.append(f"{arm}/{attempt['id']}/{scenario}: missing or failed phase evidence")
                if any(part.get("counts", {}).get("clock_anomalies", 0) for part in (row, row.get("warmup", {}))):
                    failures.append(f"{arm}/{attempt['id']}/{scenario}: clock anomalies")
    attempts = [attempt for arm in ARMS for attempt in ledgers[arm] if attempt.get("status") == "passed"]
    for key in ("database_fingerprint", "response_contract"):
        values = [attempt.get(key) for attempt in attempts]
        if not values or any(not value for value in values) or len({fingerprint(value) for value in values}) != 1:
            failures.append(f"missing or incompatible {key} across arms")
    for scenario in manifests[ARMS[0]]["scenarios"]:
        samples = [{"arm": arm, "repetition": attempt["repetition"], "throughput": attempt["rows"][scenario]["throughput"],
                    "latency_ms": attempt["rows"][scenario]["latency_ms"]}
                   for arm in ARMS for attempt in ledgers[arm]
                   if attempt.get("status") == "passed" and scenario in attempt.get("rows", {})]
        summary = {}
        for metric in ("throughput", "p50", "p95", "p99"):
            values = [sample[metric] if metric == "throughput" else (sample["latency_ms"] or {}).get(metric) for sample in samples]
            if len(values) != 6 or any(not positive_finite(value) for value in values):
                failures.append(f"{scenario}: incomplete or invalid {metric} samples")
                continue
            spread = max(values) / min(values) - 1
            summary[metric] = {"median_of_repetitions": statistics.median(values), "min": min(values),
                               "max": max(values), "relative_spread": spread}
            if metric in ("throughput", "p95") and spread > .05 + 1e-9:
                failures.append(f"{scenario}: {metric} spread exceeds 5%")
        pairs = []
        for rep in range(1, 4):
            paired = {sample["arm"]: sample for sample in samples if sample["repetition"] == rep}
            if len(paired) == 2 and all(positive_finite(sample["throughput"]) and
                    positive_finite((sample["latency_ms"] or {}).get("p95")) for sample in paired.values()):
                a, b = (paired[arm] for arm in ARMS)
                pairs.append({"repetition": rep, "b_over_a_throughput": b["throughput"] / a["throughput"],
                              "b_over_a_p95": b["latency_ms"]["p95"] / a["latency_ms"]["p95"]})
        rows[scenario] = {"repetitions": samples, "summary_of_repetitions": summary, "paired_ratios": pairs}
    return {"same_image_repeatable": not failures, "publication_ready": False, "maximum_relative_spread": .05,
            "failures": sorted(set(failures)), "scenarios": rows,
            "limit": "Local diagnostic stability only; not observer/isolated-generator calibration or evidence of an optimization gain"}


def execute(runner, directory, plan, approval_note):
    require_approval(True, approval_note)
    receipt_file = directory / "execution.json"
    if receipt_file.exists():
        raise ValueError("An execution already exists; failed or interrupted attempts cannot be replaced")
    manifests = validate_prepared(runner, directory, plan)
    ledgers = {arm: [{"id": f"pair{rep}-honua", "server": "honua", "repetition": rep,
                      "status": "not-run", "error": "scheduled but not started", "rows": {}}
                     for rep in range(1, 4)] for arm in ARMS}
    receipt = {"status": "running", "plan_binding": plan["binding"], "approval_note": approval_note.strip(),
               "approved_utc": datetime.now(timezone.utc).isoformat(), "order": plan["order"]}

    def save():
        for arm in ARMS:
            runner.write(directory / arm / "attempts.json", ledgers[arm])
        receipt["utc"] = datetime.now(timezone.utc).isoformat()
        receipt["attempts"] = ledgers
        runner.write(receipt_file, receipt)

    save()
    try:
        for rep, order in enumerate(plan["order"], 1):
            for arm in order:
                attempt = ledgers[arm][rep - 1]
                attempt.update(status="scheduled")
                attempt.pop("error", None)
                save()
                runner.execute_attempt(directory / arm, manifests[arm], attempt, save)
                if attempt["status"] != "passed" or not attempt.get("cleaned") or attempt.get("fairness_failures"):
                    raise ValueError(f"{arm}/{attempt['id']}: attempt failed; remaining scheduled attempts will not run")
                if any(part.get("counts", {}).get("clock_anomalies", 0)
                       for row in attempt.get("rows", {}).values() for part in (row, row.get("warmup", {}))):
                    raise ValueError(f"{arm}/{attempt['id']}: clock anomalies; remaining scheduled attempts will not run")
        receipt["status"] = "completed"
    except KeyboardInterrupt:
        receipt["status"] = "interrupted"
        raise
    except Exception as exc:
        receipt.update(status="failed", error=str(exc))
        raise
    finally:
        for ledger in ledgers.values():
            for attempt in ledger:
                if attempt["status"] in {"scheduled", "running"}:
                    attempt.update(status="interrupted", error="execution stopped; attempt retained")
        save()
        try:
            reports = {arm: runner.report(directory / arm, manifests[arm], ledgers[arm]) for arm in ARMS}
            result = repeatability_report(manifests, ledgers, reports)
            runner.write(directory / "repeatability-report.json", result)
            if receipt["status"] == "completed":
                receipt["status"] = "passed-repeatability" if result["same_image_repeatable"] else "failed-repeatability"
        except Exception as exc:
            receipt["report_error"] = str(exc)
            if receipt["status"] == "completed":
                receipt["status"] = "failed-report"
            raise
        finally:
            save()
    return 0 if result["same_image_repeatable"] else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--execute", action="store_true", help="Execute a prepared plan only after explicit operator approval")
    parser.add_argument("--approval-note", help="Record who approved this specific quiet-machine window and its scope")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scenarios", default=DEFAULT_SCENARIOS)
    parser.add_argument("--honua-profile", choices=HONUA_PROFILES, default="automatic-bounded")
    parser.add_argument("--generator-cpus", type=int, default=8)
    parser.add_argument("--control-host", choices=("localhost", "host.docker.internal"), default="localhost")
    for key in ("honua", "postgis", "k6"):
        parser.add_argument("--" + key + "-image", default=os.environ.get(key.upper() + "_IMAGE", ""))
    args = parser.parse_args(argv)
    require_approval(args.execute, args.approval_note)
    directory = args.output.resolve()
    if not directory.is_relative_to(ROOT / "results"):
        raise ValueError("Output must be under results/")
    runner = runner_module()
    if not args.execute:
        prepare(runner, directory, args)
        return 0
    plan = json.loads((directory / "repeatability-plan.json").read_text())
    with open(f"/tmp/geobench-feature-campaign-{os.getuid()}.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return execute(runner, directory, plan, args.approval_note)


if __name__ == "__main__":
    def interrupt(signum, frame):
        raise KeyboardInterrupt(f"signal {signum}")
    signal.signal(signal.SIGTERM, interrupt)
    sys.exit(main())
