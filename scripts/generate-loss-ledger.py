#!/usr/bin/env python3
"""Generate a ranked Honua loss ledger from GeoBench report.json files."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASELINE_SERVER = "honua"
METRICS = ("rps", "p50", "p95", "p99", "error_rate_pct")
LATENCY_METRICS = {"p50", "p95", "p99"}
TAIL_METRICS = {"p95", "p99"}
DEFAULT_NEAR_TIE_THRESHOLD = 0.02

SERVER_LABELS = {
    "honua": "Honua Server",
    "geoserver": "GeoServer",
    "qgis": "QGIS Server",
}

TEST_LABELS = {
    "attribute-filter": "Attribute Filter",
    "spatial-bbox": "Spatial BBox",
    "concurrent": "Concurrent",
    "wms-getmap": "WMS GetMap",
    "wms-reprojection": "WMS Reprojection",
    "wfs-getfeature": "WFS GetFeature",
    "wfs-filtered": "WFS Filtered",
    "wms-getfeatureinfo": "WMS GetFeatureInfo",
    "wms-filtered": "WMS Filtered",
    "wmts": "WMTS",
    "wcs": "WCS",
    "geoservices-query": "GeoServices Query",
    "geoservices-query-diagnostics": "GeoServices Query Diagnostics",
    "geoservices-export": "GeoServices Export",
    "geoservices-identify": "GeoServices Identify",
}

GROUPS = {
    "attribute-filter": "Common Standards: Feature",
    "spatial-bbox": "Common Standards: Feature",
    "concurrent": "Common Standards: Feature",
    "wms-getmap": "Common Standards: Raster",
    "wms-reprojection": "Common Standards: Raster",
    "wfs-getfeature": "Secondary Standards",
    "wfs-filtered": "Secondary Standards",
    "wms-getfeatureinfo": "Secondary Standards",
    "wms-filtered": "Secondary Standards",
    "wmts": "Secondary Standards",
    "wcs": "Secondary Standards",
    "geoservices-query": "Supplemental Native Protocols",
    "geoservices-query-diagnostics": "Supplemental Native Protocols",
    "geoservices-export": "Supplemental Native Protocols",
    "geoservices-identify": "Supplemental Native Protocols",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rank Honua losses across one or more GeoBench report.json files."
    )
    parser.add_argument(
        "reports",
        nargs="+",
        type=Path,
        help="GeoBench report.json files to compare.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        help="Directory for loss-ledger.json and loss-ledger.md. Defaults to results/loss-ledger-<timestamp>.",
    )
    parser.add_argument(
        "--baseline",
        default=BASELINE_SERVER,
        help="Server id to treat as the baseline. Defaults to honua.",
    )
    parser.add_argument(
        "--competitor",
        action="append",
        dest="competitors",
        help="Competitor server id to include. May be repeated. Defaults to every non-baseline server in each report.",
    )
    parser.add_argument(
        "--near-tie-threshold",
        type=float,
        default=DEFAULT_NEAR_TIE_THRESHOLD,
        help="Relative delta at or below this value is marked near-tie. Defaults to 0.02.",
    )
    parser.add_argument(
        "--include-wins",
        action="store_true",
        help="Include rows where the baseline wins. By default only losses, near-ties, and support gaps are written.",
    )
    parser.add_argument(
        "--dedupe",
        choices=("all", "latest"),
        default="all",
        help=(
            "Row retention mode. 'all' keeps every report row; 'latest' keeps only the newest "
            "row for each baseline/competitor/test/scenario/metric tuple before filtering wins."
        ),
    )
    parser.add_argument(
        "--max-markdown-rows",
        type=int,
        default=100,
        help="Maximum detailed rows to render in Markdown. JSON always contains every retained row.",
    )
    return parser.parse_args()


def load_report(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if "results" not in data or not isinstance(data["results"], dict):
        raise ValueError(f"{path} is not a GeoBench report.json with a results object")
    return data


def label_server(server: str) -> str:
    return SERVER_LABELS.get(server, server)


def label_test(test: str) -> str:
    return TEST_LABELS.get(test, test)


def confidence_for_runs(runs: int) -> str:
    if runs >= 5:
        return "high"
    if runs >= 3:
        return "medium"
    return "low"


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def metric_direction(metric: str) -> str:
    return "higher" if metric == "rps" else "lower"


def competitor_advantage(metric: str, baseline_value: float, competitor_value: float) -> float:
    """Return positive relative delta when competitor is better."""
    if metric == "rps":
        if baseline_value == 0:
            return math.inf if competitor_value > 0 else 0.0
        return (competitor_value - baseline_value) / baseline_value

    if competitor_value == 0:
        return math.inf if baseline_value > 0 else 0.0
    return (baseline_value - competitor_value) / competitor_value


def better_server(metric: str, baseline_value: float, competitor_value: float) -> str:
    if baseline_value == competitor_value:
        return "tie"
    if metric == "rps":
        return "baseline" if baseline_value > competitor_value else "competitor"
    return "baseline" if baseline_value < competitor_value else "competitor"


def classify_bottleneck(test: str, scenario: str, metric: str, status: str) -> str:
    if status in {"unsupported", "competitor-unsupported"}:
        return "feature-gap"
    if test == "wms-reprojection":
        return "projection"
    if test in {"wms-getmap", "wms-filtered", "wms-getfeatureinfo", "geoservices-export", "geoservices-identify"}:
        return "renderer"
    if test == "wmts":
        return "cache-tier"
    if test == "concurrent":
        if "like" in scenario or "range" in scenario:
            return "sql"
        return "admission" if metric in TAIL_METRICS else "unknown"
    if test in {"attribute-filter", "spatial-bbox", "wfs-getfeature", "wfs-filtered", "geoservices-query", "geoservices-query-diagnostics"}:
        return "sql"
    if metric in LATENCY_METRICS:
        return "serialization"
    return "unknown"


def priority_score(row: dict[str, Any]) -> float:
    status = row["status"]
    if status == "unsupported":
        return 1_000_000.0
    if status == "competitor-unsupported":
        return 900_000.0
    if status == "near-tie":
        base = 10.0
    elif status == "loss":
        base = 100.0
    else:
        base = 0.0

    metric = row.get("metric")
    if metric == "p99":
        base *= 5
    elif metric == "p95":
        base *= 4
    elif metric == "error_rate_pct":
        base *= 4
    elif metric == "rps":
        base *= 3
    elif metric == "p50":
        base *= 1

    if row.get("confidence") == "high":
        base *= 1.5
    elif row.get("confidence") == "medium":
        base *= 1.0
    else:
        base *= 0.65

    advantage = row.get("competitor_advantage_ratio")
    if is_number(advantage):
        base *= 1 + max(0.0, min(float(advantage), 10.0))
    return round(base, 4)


def build_audit_index(audits: dict[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    index: dict[tuple[str, str, str], dict[str, Any]] = {}
    for server, entries in audits.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            suite = entry.get("suite")
            request = entry.get("request")
            if not suite or request is None:
                continue
            index[(server, str(suite), str(request))] = entry
    return index


def audit_status(audit_index: dict[tuple[str, str, str], dict[str, Any]], server: str, test: str, scenario: str) -> int | None:
    entry = audit_index.get((server, test, scenario))
    if not entry:
        return None
    status = entry.get("status")
    return int(status) if isinstance(status, int) else None


def support_status_row(
    report_path: Path,
    report: dict[str, Any],
    baseline: str,
    competitor: str,
    test: str,
    scenario: str,
    baseline_status: int | None,
    competitor_status: int | None,
    status: str,
) -> dict[str, Any]:
    runs = int(report.get("runs") or report.get("run_metadata", {}).get("runs") or 1)
    winner = competitor if status == "unsupported" else baseline
    row = {
        "status": status,
        "group": GROUPS.get(test, "Unknown"),
        "test": test,
        "test_label": label_test(test),
        "scenario": scenario,
        "metric": "support",
        "baseline_server": baseline,
        "baseline_label": label_server(baseline),
        "baseline_value": baseline_status,
        "competitor_server": competitor,
        "competitor_label": label_server(competitor),
        "competitor_value": competitor_status,
        "winner": winner,
        "metric_direction": "2xx status",
        "competitor_advantage_ratio": None,
        "competitor_advantage_pct": None,
        "bottleneck_class": "feature-gap" if status in {"unsupported", "competitor-unsupported"} else "none",
        "confidence": confidence_for_runs(runs),
        "runs": runs,
        "report": str(report_path),
        "report_id": report_path.parent.name,
        "timestamp": report.get("timestamp"),
        "dataset": report.get("dataset"),
        "notes": f"{baseline} audit status {baseline_status}; {competitor} audit status {competitor_status}",
    }
    row["priority_score"] = priority_score(row)
    return row


def parse_row_time(row: dict[str, Any]) -> datetime:
    timestamp = row.get("timestamp")
    if isinstance(timestamp, str) and timestamp:
        try:
            return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            pass

    report_id = str(row.get("report_id") or "")
    match = re.match(r"^(\d{8})-(\d{6})$", report_id)
    if match:
        try:
            parsed = datetime.strptime("".join(match.groups()), "%Y%m%d%H%M%S")
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    return datetime.min.replace(tzinfo=timezone.utc)


def dedupe_latest_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            row["baseline_server"],
            row["competitor_server"],
            row["test"],
            row["scenario"],
            row["metric"],
        )
        existing = latest.get(key)
        if existing is None or parse_row_time(row) >= parse_row_time(existing):
            latest[key] = row
    return list(latest.values())


def compare_report(
    report_path: Path,
    report: dict[str, Any],
    baseline: str,
    competitors: list[str] | None,
    near_tie_threshold: float,
    include_wins: bool,
) -> list[dict[str, Any]]:
    results = report["results"]
    baseline_results = results.get(baseline, {})
    if not baseline_results:
        return []

    runs = int(report.get("runs") or report.get("run_metadata", {}).get("runs") or 1)
    confidence = confidence_for_runs(runs)
    audit_index = build_audit_index(report.get("response_shape_audits", {}))
    competitor_ids = competitors or [server for server in sorted(results) if server != baseline]
    rows: list[dict[str, Any]] = []
    support_gaps_seen: set[tuple[str, str, str]] = set()

    for competitor in competitor_ids:
        competitor_results = results.get(competitor)
        if not competitor_results:
            continue

        tests = sorted(set(baseline_results) | set(competitor_results))
        for test in tests:
            baseline_test = baseline_results.get(test, {})
            competitor_test = competitor_results.get(test, {})
            scenarios = sorted(set(baseline_test) | set(competitor_test))
            for scenario in scenarios:
                baseline_status = audit_status(audit_index, baseline, test, scenario)
                competitor_status = audit_status(audit_index, competitor, test, scenario)
                support_gap_key = (competitor, test, scenario)
                if baseline_status is not None and support_gap_key not in support_gaps_seen:
                    if (
                        competitor_status is not None
                        and baseline_status >= 400
                        and 200 <= competitor_status < 300
                    ):
                        rows.append(
                            support_status_row(
                                report_path,
                                report,
                                baseline,
                                competitor,
                                test,
                                scenario,
                                baseline_status,
                                competitor_status,
                                "unsupported",
                            )
                        )
                        support_gaps_seen.add(support_gap_key)
                        continue

                    if (
                        competitor_status is not None
                        and 200 <= baseline_status < 300
                        and not (200 <= competitor_status < 300)
                    ):
                        rows.append(
                            support_status_row(
                                report_path,
                                report,
                                baseline,
                                competitor,
                                test,
                                scenario,
                                baseline_status,
                                competitor_status,
                                "competitor-unsupported",
                            )
                        )
                        support_gaps_seen.add(support_gap_key)
                        continue

                    if (
                        competitor_status is not None
                        and 200 <= baseline_status < 300
                        and 200 <= competitor_status < 300
                    ):
                        rows.append(
                            support_status_row(
                                report_path,
                                report,
                                baseline,
                                competitor,
                                test,
                                scenario,
                                baseline_status,
                                competitor_status,
                                "win",
                            )
                        )
                        support_gaps_seen.add(support_gap_key)

                baseline_scenario = baseline_test.get(scenario)
                competitor_scenario = competitor_test.get(scenario)
                if isinstance(baseline_scenario, dict) and not isinstance(competitor_scenario, dict):
                    if support_gap_key not in support_gaps_seen:
                        rows.append(
                            support_status_row(
                                report_path,
                                report,
                                baseline,
                                competitor,
                                test,
                                scenario,
                                baseline_status if baseline_status is not None else 200,
                                competitor_status,
                                "competitor-unsupported",
                            )
                        )
                        support_gaps_seen.add(support_gap_key)
                    continue

                if not isinstance(baseline_scenario, dict) and isinstance(competitor_scenario, dict):
                    if support_gap_key not in support_gaps_seen:
                        rows.append(
                            support_status_row(
                                report_path,
                                report,
                                baseline,
                                competitor,
                                test,
                                scenario,
                                baseline_status,
                                competitor_status if competitor_status is not None else 200,
                                "unsupported",
                            )
                        )
                        support_gaps_seen.add(support_gap_key)
                    continue

                if not isinstance(baseline_scenario, dict) or not isinstance(competitor_scenario, dict):
                    continue

                for metric in METRICS:
                    baseline_value = baseline_scenario.get(metric)
                    competitor_value = competitor_scenario.get(metric)
                    if not is_number(baseline_value) or not is_number(competitor_value):
                        continue

                    baseline_float = float(baseline_value)
                    competitor_float = float(competitor_value)
                    winner_kind = better_server(metric, baseline_float, competitor_float)
                    advantage = competitor_advantage(metric, baseline_float, competitor_float)
                    abs_advantage = abs(advantage) if is_number(advantage) else math.inf

                    if abs_advantage <= near_tie_threshold:
                        status = "near-tie"
                        winner = "tie"
                    elif winner_kind == "competitor":
                        status = "loss"
                        winner = competitor
                    else:
                        status = "win"
                        winner = baseline

                    row = {
                        "status": status,
                        "group": GROUPS.get(test, "Unknown"),
                        "test": test,
                        "test_label": label_test(test),
                        "scenario": scenario,
                        "metric": metric,
                        "baseline_server": baseline,
                        "baseline_label": label_server(baseline),
                        "baseline_value": baseline_value,
                        "competitor_server": competitor,
                        "competitor_label": label_server(competitor),
                        "competitor_value": competitor_value,
                        "winner": winner,
                        "metric_direction": metric_direction(metric),
                        "competitor_advantage_ratio": round(advantage, 6) if is_number(advantage) else None,
                        "competitor_advantage_pct": round(advantage * 100, 2) if is_number(advantage) else None,
                        "bottleneck_class": classify_bottleneck(test, scenario, metric, status),
                        "confidence": confidence,
                        "runs": runs,
                        "report": str(report_path),
                        "report_id": report_path.parent.name,
                        "timestamp": report.get("timestamp"),
                        "dataset": report.get("dataset"),
                        "notes": None,
                    }
                    row["priority_score"] = priority_score(row)
                    rows.append(row)

    return rows


def format_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.1f}" if abs(value) >= 10 else f"{value:.3g}"
    return str(value)


def markdown_table(rows: list[list[str]]) -> list[str]:
    if not rows:
        return []
    widths = [max(len(str(row[index])) for row in rows) for index in range(len(rows[0]))]
    lines = []
    header = rows[0]
    lines.append("| " + " | ".join(str(value).ljust(widths[index]) for index, value in enumerate(header)) + " |")
    lines.append("| " + " | ".join("-" * widths[index] for index in range(len(header))) + " |")
    for row in rows[1:]:
        lines.append("| " + " | ".join(str(value).ljust(widths[index]) for index, value in enumerate(row)) + " |")
    return lines


def write_json(output_dir: Path, metadata: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    payload = {
        "metadata": metadata,
        "summary": dict(Counter(row["status"] for row in rows)),
        "rows": rows,
    }
    with (output_dir / "loss-ledger.json").open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def write_markdown(output_dir: Path, metadata: dict[str, Any], rows: list[dict[str, Any]], max_rows: int) -> None:
    lines = [
        "# GeoBench Loss Ledger",
        "",
        f"Generated: {metadata['generated_at']}",
        f"Baseline: `{metadata['baseline']}`",
        f"Near-tie threshold: `{metadata['near_tie_threshold']}`",
        f"Row retention: `{metadata['dedupe']}`",
        "",
        "## Reports",
        "",
    ]
    for report in metadata["reports"]:
        lines.append(f"- `{report}`")

    counts = Counter(row["status"] for row in rows)
    lines.extend(["", "## Summary", ""])
    summary_rows = [["Status", "Count"]]
    for status in ("unsupported", "competitor-unsupported", "loss", "near-tie", "win"):
        if counts.get(status):
            summary_rows.append([status, str(counts[status])])
    lines.extend(markdown_table(summary_rows))

    top_rows = rows[:max_rows]
    lines.extend(["", "## Ranked Rows", ""])
    if not top_rows:
        lines.append("No losses, near-ties, or support gaps found.")
    else:
        table = [[
            "Rank",
            "Status",
            "Score",
            "Confidence",
            "Report",
            "Row",
            "Scenario",
            "Metric",
            "Honua",
            "Competitor",
            "Gap",
            "Class",
        ]]
        for index, row in enumerate(top_rows, start=1):
            gap = row.get("competitor_advantage_pct")
            gap_text = "-" if gap is None else f"{gap:+.2f}%"
            table.append([
                str(index),
                row["status"],
                format_value(row["priority_score"]),
                row["confidence"],
                row["report_id"],
                row["test"],
                row["scenario"],
                row["metric"],
                format_value(row["baseline_value"]),
                f"{row['competitor_label']} {format_value(row['competitor_value'])}",
                gap_text,
                row["bottleneck_class"],
            ])
        lines.extend(markdown_table(table))

    lines.extend([
        "",
        "## Notes",
        "",
        "- Positive gap means the competitor is better for that metric.",
        "- `unsupported` rows come from response-shape audits where Honua returned a non-2xx status and a competitor returned 2xx.",
        "- `competitor-unsupported` rows mean Honua produced a result but the competitor had no comparable result or returned a non-2xx status.",
        "- JSON output contains all retained rows, even when Markdown is truncated.",
        "",
    ])

    with (output_dir / "loss-ledger.md").open("w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def main() -> int:
    args = parse_args()
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    output_dir = args.output_dir
    if output_dir is None:
        output_dir = Path("results") / f"loss-ledger-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    report_paths: list[str] = []
    for report_path in args.reports:
        report_path = report_path.resolve()
        report_paths.append(str(report_path))
        report = load_report(report_path)
        rows.extend(
            compare_report(
                report_path,
                report,
                args.baseline,
                args.competitors,
                args.near_tie_threshold,
                args.include_wins,
            )
        )

    if args.dedupe == "latest":
        rows = dedupe_latest_rows(rows)

    if not args.include_wins:
        rows = [row for row in rows if row["status"] != "win"]

    rows.sort(
        key=lambda row: (
            -float(row["priority_score"]),
            row["status"],
            row["report_id"],
            row["test"],
            row["scenario"],
            row["metric"],
        )
    )

    metadata = {
        "generated_at": generated_at,
        "baseline": args.baseline,
        "competitors": args.competitors,
        "near_tie_threshold": args.near_tie_threshold,
        "include_wins": args.include_wins,
        "dedupe": args.dedupe,
        "reports": report_paths,
    }
    write_json(output_dir, metadata, rows)
    write_markdown(output_dir, metadata, rows, args.max_markdown_rows)

    print(f"Wrote {output_dir / 'loss-ledger.json'}")
    print(f"Wrote {output_dir / 'loss-ledger.md'}")
    print(f"Rows: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
