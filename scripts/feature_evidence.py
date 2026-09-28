"""Nonoverlapping measured samples and fail-closed paired campaign reports."""
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path


def distribution(values):
    values = sorted(values)
    if not values:
        return None
    # Nearest-rank quantiles of actual samples, never averages of quantiles.
    return {name: values[max(0, math.ceil(len(values) * quantile) - 1)]
            for name, quantile in (("p50", .50), ("p95", .95), ("p99", .99))}


def summarize(path, duration, phase="measurement"):
    counts = Counter()
    latencies = []
    requests = Counter()
    seen = set()
    for line in Path(path).read_text().splitlines():
        entry = json.loads(line)
        if entry.get("type") != "Point":
            continue
        metric, data = entry["metric"], entry["data"]
        value, tags = data["value"], data.get("tags", {})
        seen.add(metric)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError("Invalid sample")
        if metric == "dropped_iterations":
            counts["dropped"] += value
        if metric == "feature_started":
            counts["started"] += value
        if metric == "feature_completed":
            counts["completed"] += value
            counts[tags.get("phase", "unknown")] += value
        if metric == "feature_invalid":
            counts["invalid"] += value
        if metric == "feature_latency" and tags.get("phase") == phase and tags.get("valid") == "true":
            latencies.append(value)
            requests[tags["request"]] += 1
    counts["cancelled"] = counts["started"] - counts["completed"]
    failures = []
    required = {"feature_started", "feature_completed", "feature_latency", "feature_invalid"}
    if not required <= seen:
        failures.append("missing custom completion/semantic metrics")
    if counts["unknown"]:
        failures.append("unclassified completions")
    if not latencies:
        failures.append("no valid completions within the measurement window")
    if counts["invalid"] or counts["cancelled"] or counts["cancelled"] < 0:
        failures.append("invalid responses or cancelled requests")
    if counts[phase] != len(latencies):
        failures.append("completion/latency evidence mismatch")
    return {"counts": dict(counts), "requests": dict(requests), "throughput": len(latencies) / duration,
            "latency_ms": distribution(latencies), "failures": failures}


def calibration_failures(evidence, binding):
    if not isinstance(evidence, dict) or evidence.get("binding") != binding:
        return ["missing calibration bound to this configuration, images, workload, dataset and harness"]
    reasons = []
    if not evidence.get("isolated_generator_identity") or evidence.get("isolated_generator_identity") == evidence.get("local_generator_identity"):
        reasons.append("missing separate isolated load-generator identity")
    for key in ("observer_off", "observer_on", "isolated_generator"):
        rows = evidence.get(key, [])
        if len(rows) < 3 or any(not all(isinstance(r.get(k), (int, float)) and
                math.isfinite(r[k]) and r[k] > 0 for k in ("throughput", "p95")) for r in rows):
            reasons.append(f"missing/invalid calibration samples: {key}")
    if reasons:
        return reasons
    for metric in ("throughput", "p95"):
        baseline = statistics.median(row[metric] for row in evidence["isolated_generator"])
        for key in ("observer_off", "observer_on"):
            actual = statistics.median(row[metric] for row in evidence[key])
            if abs(actual / baseline - 1) > .05:
                reasons.append(f"local setup unsuitable: {key} {metric} varies by more than 5%")
        off = statistics.median(row[metric] for row in evidence["observer_off"])
        on = statistics.median(row[metric] for row in evidence["observer_on"])
        if abs(on / off - 1) > .05:
            reasons.append(f"observer overhead exceeds 5%: {metric}")
    return reasons


def report(directory, manifest, attempts):
    failures = []
    expected = {(rep, server) for rep in range(1, manifest["repetitions"] + 1)
                for server in manifest["servers"]}
    keys = [(a["repetition"], a["server"]) for a in attempts]
    if len(keys) != len(set(keys)):
        failures.append("duplicate attempts for a scheduled repetition; retries cannot replace failures")
    actual = {(a["repetition"], a["server"]) for a in attempts if a.get("status") == "passed"}
    if expected != actual:
        failures.append("missing or failed scheduled repetitions")
    for attempt in attempts:
        hashes = attempt.get("artifact_sha256", {})
        if not hashes:
            failures.append(f"attempt {attempt['id']}: missing artifact integrity receipt")
        for relative, expected_hash in hashes.items():
            path = (Path(directory) / relative).resolve()
            if not path.is_relative_to(Path(directory).resolve()) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
                failures.append(f"attempt {attempt['id']}: missing or modified evidence {relative}")
        if attempt.get("status") != "passed":
            failures.append(f"attempt {attempt['id']}: {attempt.get('error', attempt.get('status'))}")
        failures.extend(attempt.get("fairness_failures", []))
        if set(attempt.get("rows", {})) != set(manifest["scenarios"]):
            failures.append(f"attempt {attempt['id']}: missing scenarios")
    by_scenario = defaultdict(dict)
    pairs = []
    for scenario in manifest["scenarios"]:
        for server in manifest["servers"]:
            rows = [{"repetition": a["repetition"], **a["rows"][scenario]} for a in attempts
                    if a.get("status") == "passed" and a["server"] == server and scenario in a.get("rows", {})]
            summary = {}
            if rows:
                for metric in ("throughput", "p50", "p95", "p99"):
                    values = [r[metric] if metric == "throughput" else r["latency_ms"][metric] for r in rows]
                    summary[metric] = {"median": statistics.median(values), "min": min(values), "max": max(values)}
            by_scenario[scenario][server] = {"repetitions": rows, "summary_of_repetitions": summary}
        for rep in range(1, manifest["repetitions"] + 1):
            rows = {a["server"]: a["rows"][scenario] for a in attempts if a.get("status") == "passed"
                    and a["repetition"] == rep and scenario in a.get("rows", {})}
            if set(rows) == {"honua", "geoserver"}:
                h, g = rows["honua"], rows["geoserver"]
                pairs.append({"scenario": scenario, "repetition": rep,
                              "honua_over_geoserver_throughput": h["throughput"] / g["throughput"],
                              "honua_over_geoserver_p95": h["latency_ms"]["p95"] / max(g["latency_ms"]["p95"], .001)})
    # Require matching DB content/index/settings fingerprints and count contracts across products.
    evidence = [a for a in attempts if a.get("status") == "passed"]
    for key in ("database_fingerprint", "response_contract"):
        values = {json.dumps(a.get(key), sort_keys=True) for a in evidence}
        if len(values) != 1 or not evidence or any(not a.get(key) for a in evidence):
            failures.append(f"missing or incompatible {key}")
    publication_failures = list(failures)
    if manifest["mode"] != "comparison":
        publication_failures.append("diagnostic mode is not publication evidence")
    publication_failures.extend(calibration_failures(manifest.get("calibration"), manifest["binding"]))
    result = {"valid": not failures, "publishable": not publication_failures, "failures": failures,
              "publication_failures": publication_failures, "dataset": "100K points only",
              "profile": manifest["profile"], "attempts": attempts, "scenarios": by_scenario, "paired_ratios": pairs}
    directory = Path(directory)
    (directory / "report.json").write_text(json.dumps(result, indent=2) + "\n")
    lines = [f"GeoBench {manifest['mode']}: 100K points, {manifest['profile']}", "",
             f"Valid: {result['valid']}. Publishable: {result['publishable']}.", ""]
    lines.extend(f"- {reason}" for reason in dict.fromkeys(publication_failures))
    lines += ["", "| Scenario | Server | Repetition | Valid req/s | p50 ms | p95 ms | p99 ms | Late | Dropped |", "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for scenario, servers in by_scenario.items():
        for server, data in servers.items():
            for row in data["repetitions"]:
                latency = row["latency_ms"]
                lines.append(f"| {scenario} | {server} | {row['repetition']} | {row['throughput']:.2f} | {latency['p50']:.2f} | {latency['p95']:.2f} | {latency['p99']:.2f} | {row['counts'].get('drain', 0)} | {row['counts'].get('dropped', 0)} |")
    lines += ["", "Per-repetition medians, ranges, paired ratios, failures and warmup/drain accounting are in report.json. No combined percentile or cross-protocol winner is computed."]
    (directory / "report.md").write_text("\n".join(lines) + "\n")
    return result
