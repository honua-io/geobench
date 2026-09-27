"""Fail-closed validity checks shared by reports, resume, and release gates."""

import argparse
import json
import math
from pathlib import Path

MEASURED_TAGS = {"query_type", "bbox_size", "concurrency", "tile_level", "page_depth", "variant"}


def measured_tags(tags):
    return tags.get("phase") != "warmup" and bool(MEASURED_TAGS.intersection(tags))


def rate_value(metric):
    if not isinstance(metric, dict):
        return None
    value = metric.get("value", metric.get("rate"))
    if isinstance(value, (int, float)) and math.isfinite(value) and 0 <= value <= 1:
        return float(value)
    return None


def validation_failures(data):
    """Require traffic, passing checks, and zero errors, including warmup.

    This deliberately matches the suite's strict zero-error thresholds. Historical
    files without per-scenario errors cannot prove that failures were warmup-only.
    """
    metrics = data.get("metrics", {}) if isinstance(data, dict) else {}
    if not isinstance(metrics, dict):
        return ["invalid metrics object"]
    malformed = [f"invalid metric object: {name}" for name, metric in metrics.items()
                 if not isinstance(metric, dict)]
    if malformed:
        return malformed
    failures = []
    count = metrics.get("http_reqs", {}).get("count", 0)
    if not isinstance(count, (int, float)) or not math.isfinite(count) or count <= 0:
        failures.append("no completed requests")
    checks = metrics.get("checks", {})
    if rate_value(checks) != 1 or checks.get("fails", 0) != 0:
        failures.append("missing or failed response checks")
    for name in ("errors", "http_req_failed"):
        value = rate_value(metrics.get(name))
        if value is None:
            failures.append(f"missing or invalid {name} rate")
        elif value > 0:
            failures.append(f"{name}={value:.3%}")
    for name, metric in metrics.items():
        if name == "http_req_duration" or name.startswith("http_req_duration{"):
            for field in ("min", "med", "p(95)", "p(99)", "max"):
                value = metric.get(field)
                if value is not None and (
                    not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0
                ):
                    failures.append(f"invalid timing {name}.{field}={value}")
    measured = False
    for name, metric in metrics.items():
        if not name.startswith("http_reqs{") or not name.endswith("}"):
            continue
        suffix = name[len("http_reqs"):]
        tags = dict(part.split(":", 1) for part in suffix[1:-1].split(",") if ":" in part)
        if not measured_tags(tags):
            continue
        count = metric.get("count", 0)
        duration = metrics.get(f"http_req_duration{suffix}", {})
        if (isinstance(count, (int, float)) and math.isfinite(count) and count > 0
                and all(isinstance(duration.get(field), (int, float))
                        and math.isfinite(duration[field]) and duration[field] >= 0
                        for field in ("med", "p(95)", "p(99)"))):
            measured = True
    if not measured:
        failures.append("no measured-phase request and duration metrics")
    return failures


def point_stream_failures(contents):
    """Validate all point samples, including warmup, without retaining them."""
    seen = set()
    requests = 0
    measured_requests = 0
    measured_durations = 0
    for line in contents.splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if not isinstance(entry, dict) or entry.get("type") not in {"Metric", "Point"}:
            return ["invalid point-stream record"]
        if entry["type"] == "Metric":
            continue
        name = entry.get("metric")
        data = entry.get("data")
        if not isinstance(name, str) or not isinstance(data, dict):
            return ["invalid point-stream metric"]
        if not isinstance(data.get("tags", {}), dict):
            return ["invalid point-stream tags"]
        measured = measured_tags(data.get("tags", {}))
        value = data.get("value")
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            return [f"invalid point value: {name}"]
        seen.add(name)
        if name == "http_reqs":
            if value < 0:
                return ["invalid request count"]
            requests += value
            if measured:
                measured_requests += value
        elif name == "checks" and value != 1:
            return ["failed response checks"]
        elif name in {"errors", "http_req_failed"} and value != 0:
            return [f"{name}: failed requests"]
        elif name == "http_req_duration" and value < 0:
            return ["invalid timing http_req_duration"]
        if name == "http_req_duration" and measured:
            measured_durations += 1
    failures = [f"missing point metric: {name}" for name in
                ("checks", "errors", "http_req_failed", "http_req_duration") if name not in seen]
    if requests <= 0:
        failures.append("no completed requests")
    if measured_requests <= 0 or measured_durations == 0:
        failures.append("no measured-phase request and duration points")
    return failures


def file_failures(path, allow_point_stream=False):
    try:
        contents = Path(path).read_text()
        try:
            data = json.loads(contents)
        except json.JSONDecodeError:
            if allow_point_stream:
                return point_stream_failures(contents)
            return ["invalid summary: expected a summary-export JSON object"]
        return validation_failures(data)
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        return [f"invalid summary: {exc}"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()
    failed = False
    for path in args.paths:
        reasons = file_failures(path)
        if reasons:
            failed = True
            print(f"INVALID {Path(path).name}: {'; '.join(reasons)}")
    raise SystemExit(1 if failed else 0)
