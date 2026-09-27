"""Fail-closed validity checks shared by reports, resume, and release gates."""

import argparse
import json
import math
from pathlib import Path


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
    return failures


def file_failures(path):
    try:
        return validation_failures(json.loads(Path(path).read_text()))
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
