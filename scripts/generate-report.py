#!/usr/bin/env python3
"""Parse k6 NDJSON results and generate a markdown comparison report.

Usage: python3 generate-report.py --results-dir results/20260322-1200 --output report.md --runs 5
"""

import argparse
import json
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def parse_k6_json(filepath):
    """Parse a k6 NDJSON output file and extract http_req_duration data points."""
    points = []
    try:
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if entry.get("type") != "Point":
                    continue
                if entry.get("metric") != "http_req_duration":
                    continue

                data = entry.get("data", {})
                tags = data.get("tags", {})

                # Skip warmup phase
                if tags.get("phase") == "warmup":
                    continue

                points.append(
                    {
                        "value": data.get("value", 0),
                        "tags": tags,
                    }
                )
    except FileNotFoundError:
        pass

    return points


def compute_metrics(values):
    """Compute benchmark metrics from a list of duration values (ms)."""
    if not values:
        return {"rps": 0, "p50": 0, "p95": 0, "p99": 0, "count": 0}

    values_sorted = sorted(values)
    n = len(values_sorted)

    p50_idx = int(n * 0.50)
    p95_idx = int(n * 0.95)
    p99_idx = int(n * 0.99)

    # Approximate rps: count / total_time_seconds
    # Each measurement window is ~120s
    total_time_s = sum(values) / 1000.0
    rps = n / max(total_time_s / max(n, 1) * n / 120, 0.001) if values else 0
    # Simpler: count / measurement_duration (120s)
    rps = n / 120.0

    return {
        "rps": round(rps, 1),
        "p50": round(values_sorted[min(p50_idx, n - 1)], 1),
        "p95": round(values_sorted[min(p95_idx, n - 1)], 1),
        "p99": round(values_sorted[min(p99_idx, n - 1)], 1),
        "count": n,
    }


def collect_results(results_dir, runs):
    """Collect and aggregate results across all runs.

    Returns: {server: {test: {scenario: {metric: median_value}}}}
    """
    # Structure: results[server][test][scenario][run] = [values]
    raw = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list))))

    for filename in sorted(os.listdir(results_dir)):
        if not filename.endswith(".json") or filename in ("report.json",):
            continue

        # Parse filename: server-test-runN.json
        parts = filename.replace(".json", "").rsplit("-run", 1)
        if len(parts) != 2:
            continue

        server_test = parts[0]
        run_num = parts[1]

        # Split server from test name
        for server in ("honua", "geoserver", "qgis"):
            if server_test.startswith(server + "-"):
                test = server_test[len(server) + 1 :]
                break
        else:
            continue

        filepath = os.path.join(results_dir, filename)
        points = parse_k6_json(filepath)

        # Group by scenario tag
        by_scenario = defaultdict(list)
        for p in points:
            tags = p["tags"]
            # Determine scenario from tags
            scenario = (
                tags.get("query_type")
                or tags.get("bbox_size")
                or tags.get("concurrency")
                or "mixed"
            )
            by_scenario[scenario].append(p["value"])

        for scenario, values in by_scenario.items():
            raw[server][test][scenario][run_num] = values

    # Aggregate: median across runs
    aggregated = {}
    for server in raw:
        aggregated[server] = {}
        for test in raw[server]:
            aggregated[server][test] = {}
            for scenario in raw[server][test]:
                # Compute metrics per run, then take median of each metric
                run_metrics = []
                for run_num, values in raw[server][test][scenario].items():
                    run_metrics.append(compute_metrics(values))

                if run_metrics:
                    aggregated[server][test][scenario] = {
                        "rps": round(
                            statistics.median([m["rps"] for m in run_metrics]), 1
                        ),
                        "p50": round(
                            statistics.median([m["p50"] for m in run_metrics]), 1
                        ),
                        "p95": round(
                            statistics.median([m["p95"] for m in run_metrics]), 1
                        ),
                        "p99": round(
                            statistics.median([m["p99"] for m in run_metrics]), 1
                        ),
                    }

    return aggregated


def format_table(headers, rows):
    """Format a markdown table."""
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def generate_report(results_dir, output_path, runs):
    aggregated = collect_results(results_dir, runs)
    servers = sorted(aggregated.keys())

    if not servers:
        print("No results found in " + results_dir, file=sys.stderr)
        sys.exit(1)

    server_labels = {
        "honua": "Honua Server",
        "geoserver": "GeoServer",
        "qgis": "QGIS Server",
    }

    lines = []
    lines.append("# GeoBench Results")
    lines.append("")
    lines.append(
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )
    lines.append(f"Dataset: Small (100K points) | Runs: {runs} (median reported)")
    lines.append("")

    # Attribute filter table
    test = "attribute-filter"
    if any(test in aggregated.get(s, {}) for s in servers):
        lines.append("## Attribute Filter")
        lines.append("")
        headers = ["Query Type", "Metric"] + [
            server_labels.get(s, s) for s in servers
        ]
        rows = []
        for scenario in ["equality", "range", "like"]:
            for metric, label in [
                ("rps", "req/s"),
                ("p50", "p50 ms"),
                ("p95", "p95 ms"),
                ("p99", "p99 ms"),
            ]:
                row = [scenario if metric == "rps" else "", label]
                for s in servers:
                    val = (
                        aggregated.get(s, {})
                        .get(test, {})
                        .get(scenario, {})
                        .get(metric, "—")
                    )
                    row.append(val)
                rows.append(row)
        lines.append(format_table(headers, rows))
        lines.append("")

    # Spatial bbox table
    test = "spatial-bbox"
    if any(test in aggregated.get(s, {}) for s in servers):
        lines.append("## Spatial BBox")
        lines.append("")
        headers = ["BBox Size", "Metric"] + [
            server_labels.get(s, s) for s in servers
        ]
        rows = []
        for scenario in ["small", "medium", "large"]:
            for metric, label in [
                ("rps", "req/s"),
                ("p50", "p50 ms"),
                ("p95", "p95 ms"),
                ("p99", "p99 ms"),
            ]:
                row = [scenario if metric == "rps" else "", label]
                for s in servers:
                    val = (
                        aggregated.get(s, {})
                        .get(test, {})
                        .get(scenario, {})
                        .get(metric, "—")
                    )
                    row.append(val)
                rows.append(row)
        lines.append(format_table(headers, rows))
        lines.append("")

    # Concurrent table
    test = "concurrent"
    if any(test in aggregated.get(s, {}) for s in servers):
        lines.append("## Concurrent (Mixed Workload)")
        lines.append("")
        headers = ["VUs", "Metric"] + [server_labels.get(s, s) for s in servers]
        rows = []
        for scenario in ["1", "10", "50", "100"]:
            for metric, label in [
                ("rps", "req/s"),
                ("p50", "p50 ms"),
                ("p95", "p95 ms"),
                ("p99", "p99 ms"),
            ]:
                row = [scenario if metric == "rps" else "", label]
                for s in servers:
                    val = (
                        aggregated.get(s, {})
                        .get(test, {})
                        .get(scenario, {})
                        .get(metric, "—")
                    )
                    row.append(val)
                rows.append(row)
        lines.append(format_table(headers, rows))
        lines.append("")

    report = "\n".join(lines)

    with open(output_path, "w") as f:
        f.write(report)
    print(f"Report written to {output_path}", file=sys.stderr)

    # Also write structured JSON
    json_path = output_path.replace(".md", ".json")
    with open(json_path, "w") as f:
        json.dump(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "dataset": "small",
                "runs": runs,
                "results": aggregated,
            },
            f,
            indent=2,
        )
    print(f"JSON written to {json_path}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Generate GeoBench report")
    parser.add_argument("--results-dir", required=True, help="Directory with k6 JSON results")
    parser.add_argument("--output", required=True, help="Output markdown file")
    parser.add_argument("--runs", type=int, default=5, help="Number of runs (for labeling)")
    args = parser.parse_args()
    generate_report(args.results_dir, args.output, args.runs)


if __name__ == "__main__":
    main()
