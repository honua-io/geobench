#!/usr/bin/env python3
"""Summarize GeoBench diagnostics artifacts into diagnostics/comparison.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SQL_DURATION_MARKER = "duration:"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize a GeoBench diagnostics directory.")
    parser.add_argument("--results-dir", required=True, type=Path)
    return parser.parse_args()


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return sum(1 for _ in handle)


def percentile(sorted_values: list[float], fraction: float) -> float | None:
    if not sorted_values:
        return None
    index = int(len(sorted_values) * fraction)
    if index < 1:
        index = 1
    return sorted_values[index - 1]


def summarize_values(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "avgMs": None,
            "minMs": None,
            "p50Ms": None,
            "p95Ms": None,
            "p99Ms": None,
            "maxMs": None,
        }

    sorted_values = sorted(values)
    return {
        "count": len(sorted_values),
        "avgMs": round(sum(sorted_values) / len(sorted_values), 3),
        "minMs": round(sorted_values[0], 3),
        "p50Ms": round(percentile(sorted_values, 0.50) or 0, 3),
        "p95Ms": round(percentile(sorted_values, 0.95) or 0, 3),
        "p99Ms": round(percentile(sorted_values, 0.99) or 0, 3),
        "maxMs": round(sorted_values[-1], 3),
    }


def parse_sql_duration(line: str) -> float | None:
    marker_index = line.find(SQL_DURATION_MARKER)
    if marker_index < 0:
        return None
    remainder = line[marker_index + len(SQL_DURATION_MARKER):].lstrip()
    value_text = remainder.split(" ", 1)[0]
    try:
        return float(value_text)
    except ValueError:
        return None


def sql_summary(path: Path) -> dict[str, Any]:
    all_durations: list[float] = []
    benchmark_durations: list[float] = []
    in_benchmark_window = False

    if path.exists():
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if "geobench_diagnostics_start" in line:
                    in_benchmark_window = True
                    continue
                if "geobench_diagnostics_end" in line:
                    in_benchmark_window = False
                    continue

                duration = parse_sql_duration(line)
                if duration is None:
                    continue
                all_durations.append(duration)
                if in_benchmark_window:
                    benchmark_durations.append(duration)

    return {
        "all": summarize_values(all_durations),
        "benchmarkWindow": summarize_values(benchmark_durations),
    }


def parse_percent(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.strip().rstrip("%"))
    except ValueError:
        return None


def monitor_summary(path: Path) -> dict[str, Any]:
    samples = []
    if path.exists():
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    samples.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    max_cpu_by_name: dict[str, float] = {}
    last_query_admission = None
    for sample in samples:
        for stat in sample.get("dockerStats", []):
            name = stat.get("Name") or stat.get("Container") or stat.get("ID")
            cpu = parse_percent(stat.get("CPUPerc"))
            if name and cpu is not None:
                max_cpu_by_name[name] = max(max_cpu_by_name.get(name, 0.0), cpu)
        admission = (
            sample.get("honuaConnectionPool", {})
            .get("queryAdmission")
        )
        if admission:
            last_query_admission = admission

    return {
        "samples": len(samples),
        "firstSampleAt": samples[0].get("sampledAt") if samples else None,
        "lastSampleAt": samples[-1].get("sampledAt") if samples else None,
        "maxCpuPercentByContainer": max_cpu_by_name,
        "lastHonuaQueryAdmission": last_query_admission,
    }


def output_shape_summary(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path)
    if isinstance(payload, dict):
        payload = payload.get("entries")
    if not isinstance(payload, list):
        return []
    entries = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        entries.append({
            "suite": entry.get("suite"),
            "request": entry.get("request"),
            "status": entry.get("status"),
            "contentType": entry.get("content_type"),
            "bytes": entry.get("bytes"),
            "sha256": entry.get("sha256"),
            "summary": entry.get("summary"),
        })
    return entries


def server_summary(results_dir: Path, server_dir: Path) -> dict[str, Any]:
    server = server_dir.name
    report = read_json(results_dir / "report.json") or {}
    report_results = (
        report.get("results", {})
        .get(server, {})
    )
    return {
        "server": server,
        "resultMetrics": report_results,
        "outputShapes": output_shape_summary(server_dir / "output-shape.json"),
        "artifacts": {
            "runtimeMonitor": str(server_dir / "runtime-monitor.ndjson") if (server_dir / "runtime-monitor.ndjson").exists() else None,
            "serverLog": str(server_dir / "server.log") if (server_dir / "server.log").exists() else None,
            "postgisLog": str(server_dir / "postgis.log") if (server_dir / "postgis.log").exists() else None,
            "sqlStatements": str(server_dir / "sql-statements.log") if (server_dir / "sql-statements.log").exists() else None,
            "outputShape": str(server_dir / "output-shape.json") if (server_dir / "output-shape.json").exists() else None,
        },
        "counts": {
            "monitorSamples": count_lines(server_dir / "runtime-monitor.ndjson"),
            "sqlStatements": count_lines(server_dir / "sql-statements.log"),
            "serverLogLines": count_lines(server_dir / "server.log"),
            "postgisLogLines": count_lines(server_dir / "postgis.log"),
        },
        "sql": sql_summary(server_dir / "sql-statements.log"),
        "monitor": monitor_summary(server_dir / "runtime-monitor.ndjson"),
    }


def main() -> int:
    args = parse_args()
    results_dir = args.results_dir
    diagnostics_dir = results_dir / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    server_dirs = sorted(path for path in diagnostics_dir.iterdir() if path.is_dir())
    payload = {
        "resultsDir": str(results_dir),
        "report": str(results_dir / "report.json") if (results_dir / "report.json").exists() else None,
        "servers": [server_summary(results_dir, server_dir) for server_dir in server_dirs],
    }
    output_path = diagnostics_dir / "comparison.json"
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
