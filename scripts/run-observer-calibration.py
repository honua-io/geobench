#!/usr/bin/env python3
"""Collect paired observer-off/on evidence; never substitutes for isolated calibration."""
import argparse
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
import random
import signal
import statistics
import sys
import uuid
from pathlib import Path

from feature_evidence import calibration_sample_failures, summarize
from feature_runtime import Observer


def load_runner():
    spec = importlib.util.spec_from_file_location("campaign", Path(__file__).with_name("run-feature-campaign.py"))
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


def observer_order(seed, repetition):
    first = random.Random(seed).randrange(2)
    groups = ["observer_off", "observer_on"]
    return groups[(first + repetition - 1) % 2:] + groups[:(first + repetition - 1) % 2]


def combine_observations(summaries):
    return {
        "samples": sum(s["samples"] for s in summaries),
        "max_database_pressure": {key: max(s["max_database_pressure"][key] for s in summaries)
                                  for key in ("source_sessions", "source_active", "parallel_workers")},
        "failures": [failure for s in summaries for failure in s["failures"]],
        "observations": summaries,
    }


def local_report(directory, manifest, attempts, scenarios):
    """Retain failures and raw evidence; show observer deltas only for complete pairs."""
    failures = []
    expected = {(r, s) for r in range(1, 4) for s in manifest["servers"]}
    actual = [(a["repetition"], a["server"]) for a in attempts]
    if set(actual) != expected or len(actual) != len(set(actual)):
        failures.append("missing or duplicate scheduled calibration attempts")
    rows = []
    for server in manifest["servers"]:
        for scenario in scenarios:
            groups = {key: [] for key in ("observer_off", "observer_on")}
            for attempt in attempts:
                if attempt["server"] != server:
                    continue
                if attempt["status"] != "passed":
                    failures.append(f"{attempt['id']}: {attempt['status']}: {attempt.get('error', '')}")
                for key, samples in groups.items():
                    sample = attempt.get("calibration_rows", {}).get(scenario, {}).get(key)
                    if sample:
                        samples.append(sample)
                        failures.extend(calibration_sample_failures(sample))
            if any(len(samples) != 3 for samples in groups.values()):
                failures.append(f"{server}/{scenario}: missing three observer pairs")
                continue
            if any(calibration_sample_failures(sample) for samples in groups.values() for sample in samples):
                continue
            summaries = {key: {metric: statistics.median(s[metric] for s in samples)
                               for metric in ("throughput", "p95")} for key, samples in groups.items()}
            deltas = {metric: summaries["observer_on"][metric] / summaries["observer_off"][metric] - 1
                      for metric in ("throughput", "p95")}
            rows.append({"server": server, "scenario": scenario, "samples": groups,
                         "medians": summaries, "relative_change": deltas,
                         "within_five_percent": all(abs(value) <= .05 + 1e-9 for value in deltas.values())})
    # Recheck every retained artifact, including runtime, oracle, warmup and telemetry.
    for attempt in attempts:
        if not attempt.get("artifact_sha256"):
            failures.append(f"{attempt['id']}: missing artifact integrity receipt")
        for relative, digest in attempt.get("artifact_sha256", {}).items():
            path = (directory / relative).resolve()
            if not path.is_relative_to(directory) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                failures.append(f"{attempt['id']}: missing or changed artifact {relative}")
    return {"binding": manifest["binding"], "valid": not failures,
            "within_five_percent": not failures and all(row["within_five_percent"] for row in rows),
            "publishable": False, "publication_failures": ["isolated generator calibration is still required"],
            "local_generator_identity": manifest["host_identity"], "mode": manifest["mode"],
            "warmup_seconds": manifest["warmup"], "measurement_seconds": manifest["measurement"],
            "scenarios": rows, "failures": sorted(set(failures)), "attempts": attempts}


def collect_observer_samples(runner, manifest, scenarios, path, ids, db, config, attempt, save):
    observations = []
    attempt["calibration_rows"] = {}
    attempt["observer_order"] = observer_order(manifest["seed"], attempt["repetition"])
    save()
    for scenario in scenarios:
        parts = scenario.split(":")
        config.update({"scenario": parts[0], "vus": int(parts[2]) if len(parts) == 3 and parts[1] == "vus" else 10,
                       "rate": int(parts[2]) if len(parts) == 3 and parts[1] == "rate" else None})
        attempt["calibration_rows"][scenario] = {}
        for treatment in attempt["observer_order"]:
            print(f"{attempt['id']} {scenario} {treatment}: warmup, measurement, drain", flush=True)
            observer = Observer(path, list(ids.values()), db) if treatment == "observer_on" else None
            with observer if observer else contextlib.nullcontext():
                if observer:
                    observer.activity = scenario + ":calibration-warmup-and-drain"
                name = scenario + "-" + treatment
                config.update({"phase": "warmup", "duration": manifest["warmup"]})
                warm_path, _ = runner.run_k6(ids, path, config, name + "-warmup")
                warm = summarize(warm_path, manifest["warmup"], "warmup")
                if warm["failures"]:
                    raise ValueError(f"Calibration warmup failed: {warm['failures']}")
                if observer:
                    observer.activity = scenario + ":calibration-measurement-and-drain"
                config.update({"phase": "measurement", "duration": manifest["measurement"]})
                raw, _ = runner.run_k6(ids, path, config, name + "-measurement")
                result = summarize(raw, manifest["measurement"])
                if result["failures"]:
                    raise ValueError(f"Calibration measurement failed: {result['failures']}")
            if observer:
                observations.append(observer.summary())
            sample = {"throughput": result["throughput"], "p95": result["latency_ms"]["p95"],
                      "raw_points": str(raw), "sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
                      "measurement_seconds": manifest["measurement"], "repetition": attempt["repetition"],
                      "counts": result["counts"], "warmup": warm}
            attempt["calibration_rows"][scenario][treatment] = sample
            save()
    return combine_observations(observations)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True, help="Prepared campaign directory")
    parser.add_argument("--scenarios", help="Comma-separated subset; defaults to every prepared scenario")
    args = parser.parse_args()
    runner = load_runner()
    directory = args.campaign.resolve()
    manifest = json.loads((directory / "campaign.json").read_text())
    if not directory.is_relative_to(runner.ROOT / "results"):
        parser.error("Campaign must be under results/")
    runner.verify_snapshot(directory, manifest)
    if runner.source_fingerprint() != manifest["harness"]["content"] or runner.host_identity() != manifest["host_identity"]:
        parser.error("Prepared harness or host identity changed; prepare a new campaign")
    if manifest.get("reuse_fixture") or manifest.get("smoke"):
        parser.error("Calibration requires fresh fixtures and normal phase durations")
    scenarios = args.scenarios.split(",") if args.scenarios else manifest["scenarios"]
    if not scenarios or len(scenarios) != len(set(scenarios)) or not set(scenarios) <= set(manifest["scenarios"]):
        parser.error("Calibration scenarios must be unique prepared scenarios")
    run_id = "observer-" + uuid.uuid4().hex[:10]
    attempts = []
    ledger = directory / (run_id + "-attempts.json")

    def save():
        runner.write(ledger, attempts)

    def workload(path, ids, db, config, attempt, save):
        return collect_observer_samples(runner, manifest, scenarios, path, ids, db, config, attempt, save)

    try:
        for repetition in range(1, 4):
            order = manifest["order"][(repetition - 1) % len(manifest["order"])]
            for server in order:
                attempt = {"id": f"{run_id}-pair{repetition}-{server}", "server": server,
                           "repetition": repetition, "status": "scheduled"}
                attempts.append(attempt)
                save()
                runner.execute_attempt(directory, manifest, attempt, save, calibration_workload=workload)
    finally:
        result = local_report(directory, manifest, attempts, scenarios)
        output = directory / (run_id + "-report.json")
        runner.write(output, result)
        print(f"Local observer evidence: {output}; valid={result['valid']}; isolated calibration still required", flush=True)
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    def interrupt(signum, frame):
        raise KeyboardInterrupt(f"signal {signum}")
    signal.signal(signal.SIGTERM, interrupt)
    with open(f"/tmp/geobench-feature-campaign-{os.getuid()}.lock", "a") as host_lock:
        try:
            fcntl.flock(host_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            sys.exit("Another feature campaign owns this host's measurement lock")
        sys.exit(main())
