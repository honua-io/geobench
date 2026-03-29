#!/usr/bin/env python3
"""Run or summarize GeoServices query salt sweeps.

This exists because the large bbox native track is salt-sensitive. A single
deterministic stream is not stable enough to publish as truth on its own.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_ROOT = REPO_ROOT / "results"


@dataclass(frozen=True)
class SweepRun:
    label: str
    results_dir: Path
    metrics: dict[str, dict[str, float | None]]


def parse_salts(raw: str) -> list[str]:
    salts = [value.strip() for value in raw.split(",") if value.strip()]
    if not salts:
        raise ValueError("at least one salt is required")
    return salts


def parse_results(results_dir: Path, test: str, scenario: str) -> dict[str, dict[str, float | None]]:
    with open(results_dir / "report.json") as f:
        payload = json.load(f)

    results = payload.get("results", {})
    parsed: dict[str, dict[str, float | None]] = {}
    for server in ("honua", "geoserver", "qgis"):
        server_metrics = results.get(server, {}).get(test, {}).get(scenario)
        if server_metrics:
            parsed[server] = {
                "rps": server_metrics.get("rps"),
                "p50": server_metrics.get("p50"),
                "p95": server_metrics.get("p95"),
                "p99": server_metrics.get("p99"),
            }
    return parsed


def discover_new_results_dir(before: set[str], after_root: Path) -> Path:
    candidates = sorted(
        [
            path
            for path in after_root.iterdir()
            if path.is_dir() and path.name not in before
        ],
        key=lambda path: path.stat().st_mtime,
    )
    if not candidates:
        raise RuntimeError("could not discover a new results directory after benchmark run")
    return candidates[-1]


def run_single_salt(
    salt: str,
    scenario: str,
    duration: str,
    warmup: str,
    servers: str,
    geoserver_image: str,
    geoserver_extensions: str,
) -> Path:
    env = os.environ.copy()
    env.update(
        {
            "RUNS": "1",
            "SERVERS": servers,
            "TESTS": "geoservices-query",
            "GEOSERVICES_QUERY_SCENARIOS": scenario,
            "GEOSERVICES_QUERY_DURATION": duration,
            "GEOSERVICES_QUERY_WARMUP": warmup,
            f"GEOSERVICES_QUERY_SALT_{scenario.upper()}": salt,
        }
    )

    if "geoserver" in servers.split():
        env["GEOSERVER_GSR_ENABLED"] = "1"
        env["GEOSERVER_IMAGE"] = geoserver_image
        env["GEOSERVER_COMMUNITY_EXTENSIONS"] = geoserver_extensions

    before = {path.name for path in RESULTS_ROOT.iterdir() if path.is_dir()}
    cmd = ["./scripts/run-benchmark.sh"]

    print(f"[run] salt={salt} scenario={scenario} duration={duration} warmup={warmup}", flush=True)
    result = subprocess.run(cmd, cwd=REPO_ROOT, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"benchmark run failed for salt {salt} with exit code {result.returncode}")

    return discover_new_results_dir(before, RESULTS_ROOT)


def summarize_runs(runs: list[SweepRun], scenario: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append("# GeoServices Query Sweep")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"Scenario: `{scenario}`")
    lines.append("")
    lines.append("## Per Salt")
    lines.append("")
    lines.append("| Salt | Server | req/s | p50 ms | p95 ms | p99 ms | Results |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for run in runs:
        for server in ("honua", "geoserver"):
            metrics = run.metrics.get(server, {})
            lines.append(
                "| {salt} | {server} | {rps} | {p50} | {p95} | {p99} | [{name}]({path}) |".format(
                    salt=run.label,
                    server=server,
                    rps=metrics.get("rps", "—"),
                    p50=metrics.get("p50", "—"),
                    p95=metrics.get("p95", "—"),
                    p99=metrics.get("p99", "—"),
                    name=run.results_dir.name,
                    path=run.results_dir,
                )
            )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Server | median req/s | min req/s | max req/s | median p95 ms | min p95 ms | max p95 ms |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for server in ("honua", "geoserver"):
        rps_values = [run.metrics.get(server, {}).get("rps") for run in runs]
        p95_values = [run.metrics.get(server, {}).get("p95") for run in runs]
        rps_numbers = [value for value in rps_values if isinstance(value, (int, float))]
        p95_numbers = [value for value in p95_values if isinstance(value, (int, float))]
        lines.append(
            "| {server} | {median_rps} | {min_rps} | {max_rps} | {median_p95} | {min_p95} | {max_p95} |".format(
                server=server,
                median_rps=round(statistics.median(rps_numbers), 1) if rps_numbers else "—",
                min_rps=round(min(rps_numbers), 1) if rps_numbers else "—",
                max_rps=round(max(rps_numbers), 1) if rps_numbers else "—",
                median_p95=round(statistics.median(p95_numbers), 1) if p95_numbers else "—",
                min_p95=round(min(p95_numbers), 1) if p95_numbers else "—",
                max_p95=round(max(p95_numbers), 1) if p95_numbers else "—",
            )
        )

    markdown_path = output_dir / "report.md"
    json_path = output_dir / "report.json"

    with open(markdown_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    with open(json_path, "w") as f:
        json.dump(
            {
                "scenario": scenario,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "runs": [
                    {
                        "label": run.label,
                        "results_dir": str(run.results_dir),
                        "metrics": run.metrics,
                    }
                    for run in runs
                ],
            },
            f,
            indent=2,
        )

    return markdown_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run or summarize GeoServices query salt sweeps.")
    parser.add_argument("--scenario", default="large", help="GeoServices bbox scenario to sweep")
    parser.add_argument("--duration", default="120s", help="Per-scenario k6 duration")
    parser.add_argument("--warmup", default="60s", help="Warmup duration")
    parser.add_argument("--servers", default="honua geoserver", help="Servers to benchmark")
    parser.add_argument("--geoserver-image", default="docker.osgeo.org/geoserver:2.28.x")
    parser.add_argument("--geoserver-extensions", default="gsr")
    parser.add_argument("--salts", help="Comma-separated salt list to execute")
    parser.add_argument(
        "--results-dir",
        action="append",
        default=[],
        help="Existing results directory to summarize instead of executing a run",
    )
    args = parser.parse_args()

    runs: list[SweepRun] = []

    if args.results_dir:
        for raw_path in args.results_dir:
            results_dir = Path(raw_path).resolve()
            runs.append(
                SweepRun(
                    label=results_dir.name,
                    results_dir=results_dir,
                    metrics=parse_results(results_dir, "geoservices-query", args.scenario),
                )
            )
    else:
        if not args.salts:
            parser.error("--salts is required when --results-dir is not provided")
        for salt in parse_salts(args.salts):
            results_dir = run_single_salt(
                salt=salt,
                scenario=args.scenario,
                duration=args.duration,
                warmup=args.warmup,
                servers=args.servers,
                geoserver_image=args.geoserver_image,
                geoserver_extensions=args.geoserver_extensions,
            )
            runs.append(
                SweepRun(
                    label=salt,
                    results_dir=results_dir,
                    metrics=parse_results(results_dir, "geoservices-query", args.scenario),
                )
            )

    if not runs:
        raise RuntimeError("no sweep runs were collected")

    summary_dir = RESULTS_ROOT / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-geoservices-query-sweep"
    report_path = summarize_runs(runs, args.scenario, summary_dir)
    print(f"[summary] wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
