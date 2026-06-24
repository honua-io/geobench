#!/usr/bin/env python3
"""Compare a benchmark result directory against a stored baseline and flag regressions.

A regression is flagged when a metric exceeds its baseline value by more than
the allowed threshold percentage.  The script exits non-zero when any tracked
metric regresses beyond the threshold so CI can fail the job.

Usage:
  python3 scripts/check-regression.py \\
      --results-dir  results/<timestamp> \\
      --baseline     results/baselines/honua-baseline.json \\
      [--server      honua] \\
      [--tests       attribute-filter spatial-bbox concurrent] \\
      [--threshold   0.20]   # 20 % regression budget; default 0.20

Baseline format (produced by --save-baseline):
  {
    "server": "honua",
    "release_tag": "v1.2.3",
    "measured_at": "...",
    "metrics": {
      "attribute-filter": {
        "http_req_duration.med": 1.75,
        "http_req_duration.p(95)": 4.69,
        "http_req_duration.p(99)": 9.10,
        "http_reqs.rate": 1778.8,
        "errors.rate": 0.0
      },
      ...
    },
    "cold_start": {
      "cold_start_healthy.median_ms": 820,
      "cold_start_first_request.median_ms": 825
    }
  }
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path


# Metrics extracted per test (result file).  Keys match k6 summary JSON fields.
TRACKED_METRICS: list[tuple[str, str, str]] = [
    # (result_path, baseline_key, direction)
    # direction: "lower_is_better" or "higher_is_better"
    ("http_req_duration.med", "http_req_duration.med", "lower_is_better"),
    ("http_req_duration.p(95)", "http_req_duration.p(95)", "lower_is_better"),
    ("http_req_duration.p(99)", "http_req_duration.p(99)", "lower_is_better"),
    ("http_reqs.rate", "http_reqs.rate", "higher_is_better"),
    ("errors.value", "errors.rate", "lower_is_better"),
    ("http_req_failed.value", "http_req_failed.rate", "lower_is_better"),
]

COLD_START_TRACKED: list[tuple[str, str]] = [
    ("cold_start_healthy.median_ms", "lower_is_better"),
    ("cold_start_first_request.median_ms", "lower_is_better"),
]

# Error metrics that are OK to be 0 even when baseline is 0.
ERROR_METRICS = {"errors.rate", "errors.value", "http_req_failed.rate", "http_req_failed.value"}


def extract_metric(metrics: dict, dotted_key: str) -> float | None:
    """Extract a nested value from k6 summary metrics using a dotted key.

    E.g. "http_req_duration.p(95)" → metrics["http_req_duration"]["p(95)"]
    """
    parts = dotted_key.split(".", 1)
    top = metrics.get(parts[0])
    if top is None:
        return None
    if len(parts) == 1:
        # Scalar metric
        if isinstance(top, (int, float)):
            return float(top)
        if isinstance(top, dict):
            # Explicit membership checks: an `or`-chain would drop a legitimate
            # 0.0 and fall through to the next field.
            if "value" in top:
                v = top["value"]
            elif "rate" in top:
                v = top["rate"]
            elif "count" in top:
                v = top["count"]
            else:
                v = None
            return float(v) if v is not None else None
        return None
    sub_key = parts[1]
    if isinstance(top, dict):
        v = top.get(sub_key)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def aggregate_runs(result_files: list[Path], metric_key: str) -> float | None:
    """Read multiple run JSON files and return the median of the extracted metric."""
    values = []
    for f in result_files:
        try:
            with f.open() as fh:
                data = json.load(fh)
        except Exception:
            continue
        metrics = data.get("metrics", {})
        v = extract_metric(metrics, metric_key)
        if v is not None:
            values.append(v)
    if not values:
        return None
    return statistics.median(values)


def load_baseline(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def save_baseline(
    results_dir: Path,
    server: str,
    tests: list[str],
    release_tag: str,
    cold_start_path: Path | None,
    output: Path,
) -> None:
    metrics: dict[str, dict[str, float]] = {}
    for test in tests:
        run_files = sorted(results_dir.glob(f"{server}-{test}-run*.json"))
        if not run_files:
            print(f"  WARNING: no result files found for {server}/{test}, skipping", file=sys.stderr)
            continue
        test_metrics: dict[str, float] = {}
        for result_key, baseline_key, _ in TRACKED_METRICS:
            v = aggregate_runs(run_files, result_key)
            if v is not None:
                test_metrics[baseline_key] = round(v, 6)
        if test_metrics:
            metrics[test] = test_metrics

    cold_start: dict[str, float] = {}
    if cold_start_path and cold_start_path.exists():
        with cold_start_path.open() as f:
            cs = json.load(f)
        for cs_key, _ in COLD_START_TRACKED:
            section_key, sub_key = cs_key.split(".", 1)
            section = cs.get(section_key, {})
            v = section.get(sub_key)
            if v is not None:
                cold_start[cs_key] = round(float(v), 1)

    baseline = {
        "server": server,
        "release_tag": release_tag,
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "cold_start": cold_start,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w") as f:
        json.dump(baseline, f, indent=2)
    print(f"Baseline saved to {output}")


def validate_results_complete(
    results_dir: Path,
    server: str,
    tests: list[str],
    expected_runs: int,
    cold_start_path: Path | None,
) -> list[str]:
    """Return validation failures for missing result files or tracked metrics."""
    failures: list[str] = []

    for test in tests:
        run_files = sorted(results_dir.glob(f"{server}-{test}-run*.json"))
        if not run_files:
            failures.append(f"MISSING {server}/{test}: no result files found")
            continue
        if expected_runs > 0 and len(run_files) < expected_runs:
            failures.append(
                f"MISSING {server}/{test}: expected {expected_runs} result files, found {len(run_files)}"
            )

        for result_key, baseline_key, _ in TRACKED_METRICS:
            if aggregate_runs(run_files, result_key) is None:
                failures.append(f"MISSING {server}/{test} {baseline_key}: metric not present in result files")

    if cold_start_path:
        if not cold_start_path.exists():
            failures.append(f"MISSING cold-start results: {cold_start_path}")
        else:
            try:
                with cold_start_path.open() as f:
                    cs = json.load(f)
            except Exception as exc:
                failures.append(f"INVALID cold-start results {cold_start_path}: {exc}")
            else:
                for cs_key, _ in COLD_START_TRACKED:
                    section_key, sub_key = cs_key.split(".", 1)
                    section = cs.get(section_key, {})
                    if not isinstance(section, dict) or section.get(sub_key) is None:
                        failures.append(f"MISSING cold_start {cs_key}: metric not present")

    return failures


def check_regression(
    results_dir: Path,
    baseline: dict,
    server: str,
    tests: list[str],
    threshold: float,
    cold_start_path: Path | None,
) -> list[str]:
    """Return a list of regression descriptions; empty list means all-clear."""
    regressions: list[str] = []

    for test in tests:
        run_files = sorted(results_dir.glob(f"{server}-{test}-run*.json"))
        if not run_files:
            print(f"  WARNING: no result files for {server}/{test}, skipping regression check")
            continue

        baseline_test = baseline.get("metrics", {}).get(test)
        if not baseline_test:
            print(f"  NOTICE: no baseline entry for {server}/{test}, skipping comparison")
            continue

        for result_key, baseline_key, direction in TRACKED_METRICS:
            current = aggregate_runs(run_files, result_key)
            if current is None:
                continue
            base_val = baseline_test.get(baseline_key)
            if base_val is None:
                continue

            # For error metrics, if both are essentially zero skip the ratio.
            if baseline_key in ERROR_METRICS and base_val < 1e-9 and current < 1e-9:
                continue

            if direction == "lower_is_better":
                # Regression: current is too much higher than baseline.
                if base_val > 1e-9:
                    ratio = (current - base_val) / base_val
                else:
                    # baseline is zero; any current value > 0 is a regression.
                    ratio = current
                if ratio > threshold:
                    pct = round(ratio * 100, 1)
                    regressions.append(
                        f"REGRESSION {server}/{test} {baseline_key}: "
                        f"current={round(current, 3)} base={round(base_val, 3)} (+{pct}%)"
                    )
                else:
                    chg = round(ratio * 100, 1) if base_val > 1e-9 else 0
                    sign = "+" if chg >= 0 else ""
                    print(f"  OK  {server}/{test} {baseline_key}: {round(current, 3)} ({sign}{chg}%)")
            else:  # higher_is_better
                if base_val > 1e-9:
                    ratio = (base_val - current) / base_val
                else:
                    ratio = 0.0
                if ratio > threshold:
                    pct = round(ratio * 100, 1)
                    regressions.append(
                        f"REGRESSION {server}/{test} {baseline_key}: "
                        f"current={round(current, 3)} base={round(base_val, 3)} (-{pct}%)"
                    )
                else:
                    chg = round((current / base_val - 1.0) * 100, 1) if base_val > 1e-9 else 0
                    sign = "+" if chg >= 0 else ""
                    print(f"  OK  {server}/{test} {baseline_key}: {round(current, 3)} ({sign}{chg}%)")

    # Cold-start regression check.
    cs_baseline = baseline.get("cold_start", {})
    if cold_start_path and cold_start_path.exists() and cs_baseline:
        with cold_start_path.open() as f:
            cs = json.load(f)
        for cs_key, direction in COLD_START_TRACKED:
            section_key, sub_key = cs_key.split(".", 1)
            section = cs.get(section_key, {})
            current = section.get(sub_key)
            if current is None:
                continue
            base_val = cs_baseline.get(cs_key)
            if base_val is None:
                continue
            if direction == "lower_is_better" and base_val > 1e-9:
                ratio = (current - base_val) / base_val
                if ratio > threshold:
                    pct = round(ratio * 100, 1)
                    regressions.append(
                        f"REGRESSION cold_start {cs_key}: "
                        f"current={round(current, 1)}ms base={round(base_val, 1)}ms (+{pct}%)"
                    )
                else:
                    chg = round(ratio * 100, 1)
                    sign = "+" if chg >= 0 else ""
                    print(f"  OK  cold_start {cs_key}: {round(current, 1)}ms ({sign}{chg}%)")

    return regressions


def main() -> int:
    parser = argparse.ArgumentParser(description="Check benchmark regression against a stored baseline.")
    parser.add_argument("--results-dir", required=True, type=Path, help="Directory containing k6 result JSON files.")
    parser.add_argument("--baseline", type=Path, default=None, help="Path to baseline JSON file.")
    parser.add_argument("--server", default="honua", help="Server name (default: honua).")
    parser.add_argument(
        "--tests",
        nargs="*",
        default=["attribute-filter", "spatial-bbox", "concurrent"],
        help="Test names to check.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.20,
        help="Regression threshold as a fraction, e.g. 0.20 = 20%% (default 0.20).",
    )
    parser.add_argument(
        "--cold-start",
        type=Path,
        default=None,
        help="Path to cold-start JSON produced by measure-cold-start.sh.",
    )
    parser.add_argument(
        "--expected-runs",
        type=int,
        default=0,
        help="Require at least this many result JSON files per selected test.",
    )
    parser.add_argument(
        "--save-baseline",
        type=Path,
        default=None,
        help="Instead of checking, save the current results as a new baseline to this path.",
    )
    parser.add_argument(
        "--release-tag",
        default="",
        help="Release tag written into the baseline when using --save-baseline.",
    )
    args = parser.parse_args()

    results_dir = args.results_dir
    if not results_dir.exists():
        print(f"ERROR: results directory not found: {results_dir}", file=sys.stderr)
        return 1

    completeness_failures = validate_results_complete(
        results_dir=results_dir,
        server=args.server,
        tests=args.tests,
        expected_runs=args.expected_runs,
        cold_start_path=args.cold_start,
    )
    if completeness_failures:
        print(f"FAILED — {len(completeness_failures)} completeness issue(s) detected:")
        for failure in completeness_failures:
            print(f"  {failure}")
        return 1

    if args.save_baseline:
        save_baseline(
            results_dir=results_dir,
            server=args.server,
            tests=args.tests,
            release_tag=args.release_tag,
            cold_start_path=args.cold_start,
            output=args.save_baseline,
        )
        return 0

    if not args.baseline:
        print("ERROR: --baseline is required unless --save-baseline is given", file=sys.stderr)
        return 1

    if not args.baseline.exists():
        print(
            f"NOTICE: baseline file not found at {args.baseline}; "
            "skipping regression check (first run — establish baseline with --save-baseline)."
        )
        return 0

    print(f"Loading baseline from {args.baseline}")
    baseline = load_baseline(args.baseline)

    print(f"Checking {args.server} results in {results_dir} (threshold={args.threshold*100:.0f}%)...")
    print()

    regressions = check_regression(
        results_dir=results_dir,
        baseline=baseline,
        server=args.server,
        tests=args.tests,
        threshold=args.threshold,
        cold_start_path=args.cold_start,
    )

    print()
    if regressions:
        print(f"FAILED — {len(regressions)} regression(s) detected:")
        for r in regressions:
            print(f"  {r}")
        return 1

    print("PASSED — no regressions beyond threshold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
