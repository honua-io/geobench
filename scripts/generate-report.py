#!/usr/bin/env python3
"""Generate a markdown comparison report from k6 result files.

Supports both:
- legacy k6 point-stream JSON (`k6 run --out json=...`)
- k6 summary JSON (`k6 run --summary-export=...`)
"""

import argparse
import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


SERVERS = ("honua", "geoserver", "qgis")
CONCURRENT_LEVELS = ("1", "10", "50", "100")
CONCURRENT_WORKLOADS = (
    ("bbox", "bbox", "40%"),
    ("equality", "equality", "30%"),
    ("range", "range", "20%"),
    ("like", "like", "10%"),
)
CONCURRENT_WORKLOAD_PREFIX = "workload:"
CONCURRENT_WORKLOAD_LABELS = {
    "bbox": "bbox",
    "equality": "equality",
    "range": "range",
    "like": "like",
}
DEFAULT_CONCURRENT_MIX = {
    "bbox": 0.40,
    "equality": 0.30,
    "range": 0.20,
    "like": 0.10,
}
SPATIAL_CACHE_SENSITIVE_TESTS = {
    "spatial-bbox",
    "concurrent",
    "wfs-getfeature",
    "wms-getmap",
    "wms-reprojection",
    "wms-getfeatureinfo",
    "wms-filtered",
    "wcs",
    "geoservices-query",
    "geoservices-query-diagnostics",
    "geoservices-export",
    "geoservices-identify",
}
TEST_DEFINITIONS = {
    "attribute-filter": {
        "group": "Common Standards: Feature",
        "heading": "### Attribute Filter",
        "first_column": "Query Type",
        "scenarios": [
            {"id": "equality", "label": "equality", "tag_key": "query_type", "tag_value": "equality"},
            {"id": "range", "label": "range", "tag_key": "query_type", "tag_value": "range"},
            {"id": "like", "label": "like", "tag_key": "query_type", "tag_value": "like"},
        ],
    },
    "spatial-bbox": {
        "group": "Common Standards: Feature",
        "heading": "### Spatial BBox",
        "first_column": "BBox Size",
        "scenarios": [
            {"id": "small", "label": "small", "tag_key": "bbox_size", "tag_value": "small"},
            {"id": "medium", "label": "medium", "tag_key": "bbox_size", "tag_value": "medium"},
            {"id": "large", "label": "large", "tag_key": "bbox_size", "tag_value": "large"},
        ],
    },
    "concurrent": {
        "group": "Common Standards: Feature",
        "heading": "### Concurrent (Mixed Workload)",
        "first_column": "VUs",
        "scenarios": [
            {"id": "1", "label": "1", "tag_key": "concurrency", "tag_value": "1"},
            {"id": "10", "label": "10", "tag_key": "concurrency", "tag_value": "10"},
            {"id": "50", "label": "50", "tag_key": "concurrency", "tag_value": "50"},
            {"id": "100", "label": "100", "tag_key": "concurrency", "tag_value": "100"},
        ],
    },
    "wms-getmap": {
        "group": "Common Standards: Raster",
        "heading": "### WMS GetMap",
        "first_column": "BBox Size",
        "scenarios": [
            {"id": "small", "label": "small", "tag_key": "bbox_size", "tag_value": "small"},
            {"id": "medium", "label": "medium", "tag_key": "bbox_size", "tag_value": "medium"},
            {"id": "large", "label": "large", "tag_key": "bbox_size", "tag_value": "large"},
        ],
    },
    "wms-reprojection": {
        "group": "Common Standards: Raster",
        "heading": "### WMS GetMap Reprojection",
        "first_column": "BBox Size",
        "scenarios": [
            {"id": "small", "label": "small", "tag_key": "bbox_size", "tag_value": "small"},
            {"id": "medium", "label": "medium", "tag_key": "bbox_size", "tag_value": "medium"},
            {"id": "large", "label": "large", "tag_key": "bbox_size", "tag_value": "large"},
        ],
    },
    "wfs-getfeature": {
        "group": "Secondary Standards",
        "heading": "### WFS GetFeature",
        "first_column": "Scenario",
        "scenarios": [
            {"id": "base", "label": "base read", "tag_key": "query_type", "tag_value": "base"},
            {"id": "small", "label": "small bbox", "tag_key": "bbox_size", "tag_value": "small"},
            {"id": "medium", "label": "medium bbox", "tag_key": "bbox_size", "tag_value": "medium"},
            {"id": "large", "label": "large bbox", "tag_key": "bbox_size", "tag_value": "large"},
        ],
    },
    "wfs-filtered": {
        "group": "Secondary Standards",
        "heading": "### WFS Filtered Queries",
        "first_column": "Query Type",
        "scenarios": [
            {"id": "equality", "label": "equality", "tag_key": "query_type", "tag_value": "equality"},
            {"id": "range", "label": "range", "tag_key": "query_type", "tag_value": "range"},
            {"id": "like", "label": "like", "tag_key": "query_type", "tag_value": "like"},
        ],
    },
    "wms-getfeatureinfo": {
        "group": "Secondary Standards",
        "heading": "### WMS GetFeatureInfo",
        "first_column": "BBox Size",
        "scenarios": [
            {"id": "small", "label": "small", "tag_key": "bbox_size", "tag_value": "small"},
            {"id": "medium", "label": "medium", "tag_key": "bbox_size", "tag_value": "medium"},
            {"id": "large", "label": "large", "tag_key": "bbox_size", "tag_value": "large"},
        ],
    },
    "wms-filtered": {
        "group": "Secondary Standards",
        "heading": "### WMS GetMap filtered",
        "first_column": "Query Type",
        "scenarios": [
            {"id": "equality", "label": "equality", "tag_key": "query_type", "tag_value": "equality"},
            {"id": "range", "label": "range", "tag_key": "query_type", "tag_value": "range"},
            {"id": "like", "label": "like", "tag_key": "query_type", "tag_value": "like"},
        ],
    },
    "wmts": {
        "group": "Secondary Standards",
        "heading": "### WMTS tile fetch",
        "first_column": "Tile Matrix",
        "scenarios": [
            {"id": "z0", "label": "z0", "tag_key": "tile_level", "tag_value": "z0"},
            {"id": "z1", "label": "z1", "tag_key": "tile_level", "tag_value": "z1"},
            {"id": "z2", "label": "z2", "tag_key": "tile_level", "tag_value": "z2"},
        ],
    },
    "wcs": {
        "group": "Secondary Standards",
        "heading": "### WCS GetCoverage",
        "first_column": "BBox Size",
        "scenarios": [
            {"id": "small", "label": "small", "tag_key": "bbox_size", "tag_value": "small"},
            {"id": "medium", "label": "medium", "tag_key": "bbox_size", "tag_value": "medium"},
            {"id": "large", "label": "large", "tag_key": "bbox_size", "tag_value": "large"},
        ],
    },
    "geoservices-query": {
        "group": "Supplemental Native Protocols",
        "heading": "### GeoServices REST FeatureServer/query",
        "first_column": "BBox Size",
        "scenarios": [
            {"id": "small", "label": "small", "tag_key": "bbox_size", "tag_value": "small"},
            {"id": "medium", "label": "medium", "tag_key": "bbox_size", "tag_value": "medium"},
            {"id": "large", "label": "large", "tag_key": "bbox_size", "tag_value": "large"},
        ],
    },
    "geoservices-query-diagnostics": {
        "group": "Supplemental Native Protocols",
        "heading": "### GeoServices REST Query Diagnostics",
        "first_column": "Variant",
        "scenarios": [
            {"id": "medium-full-1vu", "label": "medium full 1vu", "tag_key": "variant", "tag_value": "medium-full-1vu"},
            {"id": "medium-full-10vu", "label": "medium full 10vu", "tag_key": "variant", "tag_value": "medium-full-10vu"},
            {"id": "medium-attrs-10vu", "label": "medium attrs-only 10vu", "tag_key": "variant", "tag_value": "medium-attrs-10vu"},
            {"id": "medium-geom-oid-10vu", "label": "medium geom+oid 10vu", "tag_key": "variant", "tag_value": "medium-geom-oid-10vu"},
            {"id": "large-full-1vu", "label": "large full 1vu", "tag_key": "variant", "tag_value": "large-full-1vu"},
            {"id": "large-full-10vu", "label": "large full 10vu", "tag_key": "variant", "tag_value": "large-full-10vu"},
            {"id": "large-attrs-10vu", "label": "large attrs-only 10vu", "tag_key": "variant", "tag_value": "large-attrs-10vu"},
            {"id": "large-geom-oid-10vu", "label": "large geom+oid 10vu", "tag_key": "variant", "tag_value": "large-geom-oid-10vu"},
        ],
    },
    "geoservices-export": {
        "group": "Supplemental Native Protocols",
        "heading": "### GeoServices REST MapServer/export",
        "first_column": "BBox Size",
        "scenarios": [
            {"id": "small", "label": "small", "tag_key": "bbox_size", "tag_value": "small"},
            {"id": "medium", "label": "medium", "tag_key": "bbox_size", "tag_value": "medium"},
            {"id": "large", "label": "large", "tag_key": "bbox_size", "tag_value": "large"},
        ],
    },
    "geoservices-identify": {
        "group": "Supplemental Native Protocols",
        "heading": "### GeoServices REST MapServer/identify",
        "first_column": "BBox Size",
        "scenarios": [
            {"id": "small", "label": "small", "tag_key": "bbox_size", "tag_value": "small"},
            {"id": "medium", "label": "medium", "tag_key": "bbox_size", "tag_value": "medium"},
            {"id": "large", "label": "large", "tag_key": "bbox_size", "tag_value": "large"},
        ],
    },
}
REPORT_GROUPS = [
    ("Common Standards: Feature", ["attribute-filter", "spatial-bbox", "concurrent"]),
    ("Common Standards: Raster", ["wms-getmap", "wms-reprojection"]),
    ("Secondary Standards", ["wfs-getfeature", "wfs-filtered", "wms-getfeatureinfo", "wms-filtered", "wmts", "wcs"]),
    ("Supplemental Native Protocols", ["geoservices-query", "geoservices-query-diagnostics", "geoservices-export", "geoservices-identify"]),
]
SERVER_LABELS = {
    "honua": "Honua Server",
    "geoserver": "GeoServer",
    "qgis": "QGIS Server",
}


def parse_result_filename(filename):
    """Parse server, test, and run id from a result filename."""
    stem = Path(filename).stem

    for server in SERVERS:
        prefix = server + "-"
        if not stem.startswith(prefix):
            continue

        remainder = stem[len(prefix) :]
        for test in sorted(TEST_DEFINITIONS.keys(), key=len, reverse=True):
            if remainder == test:
                return server, test, "default"

            test_prefix = test + "-"
            if remainder.startswith(test_prefix):
                return server, test, remainder[len(test_prefix) :]

    return None


def round_metric(value):
    if value is None:
        return None
    return round(float(value), 1)


def duration_seconds(value, default=None):
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().lower()
    if not text:
        return default

    try:
        if text.endswith("ms"):
            return float(text[:-2]) / 1000.0
        if text.endswith("s"):
            return float(text[:-1])
        if text.endswith("m"):
            return float(text[:-1]) * 60.0
        if text.endswith("h"):
            return float(text[:-1]) * 3600.0
        return float(text)
    except ValueError:
        return default


def scenario_duration_for_test(run_metadata, test):
    tests = run_metadata.get("tests", {}) if isinstance(run_metadata, dict) else {}
    entry = tests.get(test, {}) if isinstance(tests.get(test), dict) else {}
    seconds = duration_seconds(entry.get("scenario_duration_seconds"))
    return seconds if seconds and seconds > 0 else None


def compute_metrics(values, scenario_duration_seconds=None):
    """Compute benchmark metrics from a list of duration values (ms)."""
    if not values:
        return None

    values_sorted = sorted(values)
    n = len(values_sorted)
    rps_denominator = scenario_duration_seconds or 120.0

    return {
        "rps": round_metric(n / rps_denominator),
        "p50": round_metric(values_sorted[min(int(n * 0.50), n - 1)]),
        "p95": round_metric(values_sorted[min(int(n * 0.95), n - 1)]),
        "p99": round_metric(values_sorted[min(int(n * 0.99), n - 1)]),
    }


def metrics_from_summary(duration_metric, request_metric, scenario_duration_seconds=None):
    if not duration_metric or not request_metric:
        return None

    if scenario_duration_seconds:
        request_count = request_metric.get("count")
        rps = (float(request_count) / scenario_duration_seconds) if request_count is not None else None
    else:
        rps = request_metric.get("rate")

    return {
        "rps": round_metric(rps),
        "p50": round_metric(duration_metric.get("med")),
        "p95": round_metric(duration_metric.get("p(95)")),
        "p99": round_metric(duration_metric.get("p(99)")),
    }


def parse_metric_name(metric_name):
    if "{" not in metric_name or not metric_name.endswith("}"):
        return metric_name, {}

    base, raw_tags = metric_name.split("{", 1)
    tags = {}
    for part in raw_tags[:-1].split(","):
        if not part or ":" not in part:
            continue
        key, value = part.split(":", 1)
        tags[key] = value
    return base, tags


def metric_for_tags(metrics, metric_name, expected_tags):
    expected = {str(key): str(value) for key, value in expected_tags.items()}
    for key, value in metrics.items():
        base, tags = parse_metric_name(key)
        if base == metric_name and tags == expected:
            return value
    return None


def parse_k6_point_stream(filepath, run_metadata=None):
    """Parse a k6 point-stream JSON file into scenario metrics."""
    test = None
    parsed_name = parse_result_filename(Path(filepath).name)
    if parsed_name:
        _, test, _ = parsed_name

    definitions = TEST_DEFINITIONS.get(test, {}).get("scenarios", [])
    scenario_duration_seconds = scenario_duration_for_test(run_metadata or {}, test)
    points = defaultdict(list)

    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if entry.get("type") != "Point" or entry.get("metric") != "http_req_duration":
                continue

            data = entry.get("data", {})
            tags = data.get("tags", {})
            if tags.get("phase") == "warmup":
                continue

            scenario = None
            for definition in definitions:
                if tags.get(definition["tag_key"]) == definition["tag_value"]:
                    scenario = definition["id"]
                    break
            if scenario is None:
                scenario = (
                    tags.get("query_type")
                    or tags.get("bbox_size")
                    or tags.get("concurrency")
                    or "mixed"
                )
            points[scenario].append(data.get("value", 0))

            if test == "concurrent" and tags.get("concurrency") and tags.get("workload"):
                points[
                    f"{CONCURRENT_WORKLOAD_PREFIX}{tags['concurrency']}:{tags['workload']}"
                ].append(data.get("value", 0))

    parsed = {}
    for scenario, values in points.items():
        metrics = compute_metrics(values, scenario_duration_seconds)
        if metrics:
            parsed[scenario] = metrics
    return parsed


def parse_k6_summary(data, test, run_metadata=None):
    """Parse a k6 summary-export JSON object into scenario and overall metrics."""
    metrics = data.get("metrics", {})
    definitions = TEST_DEFINITIONS.get(test, {}).get("scenarios", [])
    scenario_duration_seconds = scenario_duration_for_test(run_metadata or {}, test)

    by_scenario = {}
    for definition in definitions:
        scenario_id = definition["id"]
        tag_key = definition["tag_key"]
        tag_value = definition["tag_value"]
        duration_metric = metric_for_tags(metrics, "http_req_duration", {tag_key: tag_value})
        request_metric = metric_for_tags(metrics, "http_reqs", {tag_key: tag_value})
        parsed = metrics_from_summary(duration_metric, request_metric, scenario_duration_seconds)
        if parsed:
            by_scenario[scenario_id] = parsed

    if test == "concurrent":
        for concurrency in CONCURRENT_LEVELS:
            for workload_id, _label, _weight in CONCURRENT_WORKLOADS:
                tags = {"concurrency": concurrency, "workload": workload_id}
                duration_metric = metric_for_tags(metrics, "http_req_duration", tags)
                request_metric = metric_for_tags(metrics, "http_reqs", tags)
                parsed = metrics_from_summary(duration_metric, request_metric, scenario_duration_seconds)
                if parsed:
                    by_scenario[
                        f"{CONCURRENT_WORKLOAD_PREFIX}{concurrency}:{workload_id}"
                    ] = parsed

    overall = metrics_from_summary(
        metrics.get("http_req_duration"),
        metrics.get("http_reqs"),
    )

    return by_scenario, overall


def parse_result_file(filepath, test, run_metadata=None):
    """Parse either summary JSON or point-stream JSON results."""
    try:
        with open(filepath) as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return parse_k6_point_stream(filepath, run_metadata), None

    if isinstance(data, dict) and "metrics" in data:
        return parse_k6_summary(data, test, run_metadata)

    return {}, None


def aggregate_runs(raw):
    aggregated = {}

    for server in raw:
        aggregated[server] = {}
        for test in raw[server]:
            aggregated[server][test] = {}
            for scenario in raw[server][test]:
                run_metrics = list(raw[server][test][scenario].values())
                scenario_metrics = {}

                for key in ("rps", "p50", "p95", "p99"):
                    values = [m[key] for m in run_metrics if m.get(key) is not None]
                    if values:
                        scenario_metrics[key] = round_metric(statistics.median(values))

                if scenario_metrics:
                    aggregated[server][test][scenario] = scenario_metrics

    return aggregated


def collect_results(results_dir, run_metadata=None):
    """Collect and aggregate results across all runs."""
    scenario_runs = defaultdict(
        lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    )
    overall_runs = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))

    for filepath in sorted(Path(results_dir).glob("*.json")):
        if filepath.name in ("report.json",):
            continue

        parsed_name = parse_result_filename(filepath.name)
        if not parsed_name:
            continue

        server, test, run_id = parsed_name
        scenario_metrics, overall_metrics = parse_result_file(filepath, test, run_metadata)

        for scenario, metrics in scenario_metrics.items():
            scenario_runs[server][test][scenario][run_id] = metrics

        if overall_metrics:
            overall_runs[server][test]["overall"][run_id] = overall_metrics

    return aggregate_runs(scenario_runs), aggregate_runs(overall_runs)


def collect_shape_audits(results_dir):
    audits = {}

    for filepath in sorted(Path(results_dir).glob("*-response-shapes.json")):
        try:
            with open(filepath) as f:
                data = json.load(f)
        except Exception:
            continue

        server = data.get("server")
        entries = data.get("entries")
        if server and isinstance(entries, list):
            audits[server] = entries

    return audits


def format_value(value):
    return "—" if value is None else value


def format_table(headers, rows):
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(format_value(c)) for c in row) + " |")
    return "\n".join(lines)


def add_scenario_section(lines, aggregated, servers, test, heading, first_column):
    lines.append(heading)
    lines.append("")
    headers = [first_column, "Metric"] + [SERVER_LABELS.get(s, s) for s in servers]
    rows = []

    for definition in TEST_DEFINITIONS[test]["scenarios"]:
        scenario = definition["id"]
        for metric, metric_label in [
            ("rps", "req/s"),
            ("p50", "p50 ms"),
            ("p95", "p95 ms"),
            ("p99", "p99 ms"),
        ]:
            row = [definition["label"] if metric == "rps" else "", metric_label]
            for server in servers:
                row.append(
                    aggregated.get(server, {})
                    .get(test, {})
                    .get(scenario, {})
                    .get(metric)
                )
            rows.append(row)

    lines.append(format_table(headers, rows))
    lines.append("")


def has_concurrent_workload_data(aggregated, servers):
    for server in servers:
        scenarios = aggregated.get(server, {}).get("concurrent", {})
        if any(key.startswith(CONCURRENT_WORKLOAD_PREFIX) for key in scenarios):
            return True
    return False


def format_mix_weight(value):
    if value is None:
        return "-"
    return f"{float(value) * 100:.0f}%"


def concurrent_metadata(run_metadata):
    tests = run_metadata.get("tests", {}) if isinstance(run_metadata, dict) else {}
    entry = tests.get("concurrent", {}) if isinstance(tests.get("concurrent"), dict) else {}
    levels = entry.get("concurrent_levels") or list(CONCURRENT_LEVELS)
    workloads = entry.get("concurrent_workloads") or [workload[0] for workload in CONCURRENT_WORKLOADS]
    mix = entry.get("concurrent_mix")
    if not isinstance(mix, dict):
        mix = DEFAULT_CONCURRENT_MIX
    profile = entry.get("concurrent_workload_profile") or "canonical_mixed"
    return levels, workloads, mix, profile


def add_concurrent_workload_section(lines, aggregated, servers, run_metadata):
    if not has_concurrent_workload_data(aggregated, servers):
        return

    levels, workloads, mix, profile = concurrent_metadata(run_metadata)

    lines.append("#### Concurrent Workload Breakdown")
    lines.append("")
    if profile == "focused":
        selected = ", ".join(workloads)
        lines.append(f"Focused concurrent diagnostic workload: {selected}.")
    else:
        mix_text = ", ".join(
            f"{format_mix_weight(mix.get(workload_id))} {CONCURRENT_WORKLOAD_LABELS.get(workload_id, workload_id)}"
            for workload_id in workloads
        )
        lines.append(f"Canonical mixed workload: {mix_text}.")
    lines.append("Rows are reported when k6 exports both `concurrency` and `workload` tags.")
    lines.append("")

    headers = ["VUs", "Workload", "Mix", "Metric"] + [
        SERVER_LABELS.get(s, s) for s in servers
    ]
    rows = []
    for concurrency in levels:
        for workload_id in workloads:
            workload_label = CONCURRENT_WORKLOAD_LABELS.get(workload_id, workload_id)
            workload_weight = format_mix_weight(mix.get(workload_id))
            scenario = f"{CONCURRENT_WORKLOAD_PREFIX}{concurrency}:{workload_id}"
            if not any(
                aggregated.get(server, {}).get("concurrent", {}).get(scenario)
                for server in servers
            ):
                continue

            for metric, metric_label in [
                ("rps", "req/s"),
                ("p50", "p50 ms"),
                ("p95", "p95 ms"),
                ("p99", "p99 ms"),
            ]:
                row = [
                    concurrency if metric == "rps" else "",
                    workload_label if metric == "rps" else "",
                    workload_weight if metric == "rps" else "",
                    metric_label,
                ]
                for server in servers:
                    row.append(
                        aggregated.get(server, {})
                        .get("concurrent", {})
                        .get(scenario, {})
                        .get(metric)
                    )
                rows.append(row)

    if rows:
        lines.append(format_table(headers, rows))
        lines.append("")


def add_overall_section(lines, aggregated_overall, servers, test, heading):
    lines.append(heading)
    lines.append("")
    lines.append("Per-scenario breakdown is unavailable in these summary exports.")
    lines.append("")

    headers = ["Metric"] + [SERVER_LABELS.get(s, s) for s in servers]
    rows = []
    for metric, label in [
        ("rps", "req/s"),
        ("p50", "p50 ms"),
        ("p95", "p95 ms"),
        ("p99", "p99 ms"),
    ]:
        row = [label]
        for server in servers:
            row.append(
                aggregated_overall.get(server, {})
                .get(test, {})
                .get("overall", {})
                .get(metric)
            )
        rows.append(row)

    lines.append(format_table(headers, rows))
    lines.append("")


def add_shape_audit_section(lines, shape_audits, servers):
    if not shape_audits:
        return

    feature_rows = []
    raster_rows = []

    for server in servers:
        for entry in shape_audits.get(server, []):
            row = [
                SERVER_LABELS.get(server, server),
                f"{entry.get('protocol')} / {entry.get('suite')} / {entry.get('request')}",
                entry.get("status"),
                entry.get("content_type"),
                entry.get("bytes"),
                str(entry.get("sha256", ""))[:16] + "…",
                entry.get("summary"),
            ]
            if entry.get("family") == "raster":
                raster_rows.append(row)
            else:
                feature_rows.append(row)

    if not feature_rows and not raster_rows:
        return

    lines.append("## Response Shape Audit")
    lines.append("")

    if feature_rows:
        lines.append("### Feature Shapes")
        lines.append("")
        lines.append(
            format_table(
                ["Server", "Request", "Status", "Content-Type", "Bytes", "SHA256", "Shape"],
                feature_rows,
            )
        )
        lines.append("")

    if raster_rows:
        lines.append("### Raster Shapes")
        lines.append("")
        lines.append(
            format_table(
                ["Server", "Request", "Status", "Content-Type", "Bytes", "SHA256", "Shape"],
                raster_rows,
            )
        )
        lines.append("")


def comparable_shape_value(entry, key):
    value = entry.get(key)
    if isinstance(value, list):
        return tuple(value)
    if isinstance(value, dict):
        return tuple(sorted(value.items()))
    return value


def compare_shape_group(entries):
    if len(entries) < 2:
      return "Single-server row", "No cross-server comparability claim"

    statuses = {entry.get("status") for entry in entries}
    if statuses != {200}:
        return "Blocked", "One or more servers did not return HTTP 200"

    family = entries[0].get("family")
    if family == "feature":
        core_keys = [
            "feature_count",
            "first_feature_geometry_type",
            "first_feature_property_keys",
            "first_feature_property_types",
        ]
        metadata_only = []
        for key in core_keys:
            values = {comparable_shape_value(entry, key) for entry in entries}
            if len(values) > 1:
                return "Not comparable", f"Core payload drift in {key}"

        id_kind_values = {comparable_shape_value(entry, "first_feature_id_kind") for entry in entries}
        if len(id_kind_values) > 1:
            metadata_only.append("feature id representation differs")

        meta_values = {comparable_shape_value(entry, "metadata_flags") for entry in entries}
        top_key_values = {comparable_shape_value(entry, "top_level_keys") for entry in entries}
        if len(meta_values) > 1 or len(top_key_values) > 1:
            metadata_only.append("top-level metadata differs")

        if metadata_only:
            return "Comparable with metadata drift", "; ".join(metadata_only)

        return "Comparable", "Core payload shape matches"

    dimension_values = {comparable_shape_value(entry, "dimensions") for entry in entries}
    if len(dimension_values) > 1:
        return "Not comparable", "Raster dimensions differ"

    return "Comparable", "Raster dimensions match; byte/hash differences are informational"


def add_payload_comparability_section(lines, shape_audits, servers):
    groups = defaultdict(list)
    for server in servers:
        for entry in shape_audits.get(server, []):
            groups[(entry.get("family"), entry.get("suite"), entry.get("request"))].append(
                {
                    "server": server,
                    "entry": entry,
                }
            )

    if not groups:
        return

    lines.append("## Payload Comparability")
    lines.append("")
    rows = []
    for (_, suite, request), grouped in sorted(groups.items(), key=lambda item: (item[0][1], item[0][2])):
        ordered = sorted(grouped, key=lambda item: SERVERS.index(item["server"]) if item["server"] in SERVERS else 999)
        verdict, note = compare_shape_group([item["entry"] for item in ordered])
        rows.append(
            [
                f"{suite} / {request}",
                ", ".join(SERVER_LABELS.get(item["server"], item["server"]) for item in ordered),
                verdict,
                note,
            ]
        )

    lines.append(format_table(["Request", "Servers", "Verdict", "Notes"], rows))
    lines.append("")


def add_audit_findings_section(lines, shape_audits, servers):
    findings = []
    grouped = defaultdict(list)

    for server in servers:
        for entry in shape_audits.get(server, []):
            grouped[(server, entry.get("family"), entry.get("suite"))].append(entry)

    for (server, family, suite), entries in sorted(grouped.items(), key=lambda item: item[0]):
        request_names = {entry.get("request") for entry in entries if entry.get("request")}
        hashes = {entry.get("sha256") for entry in entries if entry.get("sha256")}

        if family == "raster" and len(request_names) > 1 and len(hashes) == 1:
            findings.append(
                [
                    SERVER_LABELS.get(server, server),
                    suite,
                    "Scenario collapse",
                    "All sampled variants returned the same raster hash",
                ]
            )

        if family == "feature":
            empty_requests = sorted(
                entry.get("request")
                for entry in entries
                if entry.get("feature_count") == 0 and entry.get("request")
            )
            if empty_requests:
                findings.append(
                    [
                        SERVER_LABELS.get(server, server),
                        suite,
                        "Empty sample",
                        "No features/results in sampled request(s): " + ", ".join(empty_requests),
                    ]
                )

    if not findings:
        return

    lines.append("## Audit Findings")
    lines.append("")
    lines.append(format_table(["Server", "Suite", "Finding", "Notes"], findings))
    lines.append("")


def add_benchmark_semantics_section(lines, run_metadata):
    tests = run_metadata.get("tests", {}) if isinstance(run_metadata, dict) else {}
    observed_tests = set(tests)
    if not observed_tests:
        return

    measurement_policy = (
        run_metadata.get("measurement_policy", {})
        if isinstance(run_metadata.get("measurement_policy"), dict)
        else {}
    )
    rows = []

    if "spatial-bbox" in observed_tests:
        tolerance = run_metadata.get("bbox_tolerance_deg")
        note = "viewport/windowing bbox; not an exact spatial predicate row"
        if tolerance is not None:
            note += f"; edge tolerance={tolerance} degrees"
        rows.append(["`spatial-bbox`", note])

    if "attribute-filter" in observed_tests:
        rows.append(
            [
                "`attribute-filter`",
                "equality, numeric range, and literal-prefix LIKE filters via CQL2 where supported",
            ]
        )

    if "concurrent" in observed_tests:
        levels, workloads, mix, profile = concurrent_metadata(run_metadata)
        if profile == "focused":
            concurrent_note = (
                "focused concurrent diagnostic; selected levels="
                + ",".join(levels)
                + "; selected workloads="
                + ",".join(workloads)
            )
        else:
            mix_text = ", ".join(
                f"{format_mix_weight(mix.get(workload_id))} {CONCURRENT_WORKLOAD_LABELS.get(workload_id, workload_id)}"
                for workload_id in workloads
            )
            concurrent_note = (
                f"mixed workload: {mix_text}; report includes workload-tagged tail latency when available"
            )
        rows.append(
            [
                "`concurrent`",
                concurrent_note,
            ]
        )

    if observed_tests & SPATIAL_CACHE_SENSITIVE_TESTS:
        spatial_cache_default = measurement_policy.get(
            "spatial_response_caching_default",
            False,
        )
        rows.append(
            [
                "Spatial response caching",
                f"default={str(spatial_cache_default).lower()}; cache-assisted spatial/render rows must be run as a separate track",
            ]
        )

    response_body_policy = measurement_policy.get(
        "response_body_policy",
        "k6 discards default bodies, while measured feature requests use responseType=text so validators can inspect payloads",
    )
    rows.append(["Response validation", response_body_policy])

    if run_metadata.get("server_tuning"):
        rows.append(
            [
                "Pool profile",
                "connection/admission settings are reported as benchmark inputs, not hidden tuning",
            ]
        )

    if not rows:
        return

    lines.append("## Benchmark Semantics")
    lines.append("")
    lines.append(format_table(["Topic", "Policy"], rows))
    lines.append("")


def generate_report(results_dir, output_path, runs, selected_servers=None):
    run_metadata = load_run_metadata(results_dir)
    aggregated, aggregated_overall = collect_results(results_dir, run_metadata)
    shape_audits = collect_shape_audits(results_dir)
    discovered_servers = set(aggregated.keys()) | set(aggregated_overall.keys()) | set(shape_audits.keys())
    if selected_servers:
        servers = [server for server in selected_servers if server in discovered_servers]
    else:
        servers = [server for server in SERVERS if server in discovered_servers]
        servers.extend(sorted(discovered_servers - set(servers)))

    if not servers:
        print("No results found in " + results_dir, file=sys.stderr)
        sys.exit(1)

    report_metadata = dict(run_metadata)
    report_metadata["servers"] = servers

    lines = []
    lines.append("# GeoBench Results")
    lines.append("")
    lines.append(
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )
    lines.append(f"Dataset: Small (100K points) | Runs: {runs} (median reported)")
    lines.append("")
    add_benchmark_semantics_section(lines, report_metadata)

    for group_name, tests in REPORT_GROUPS:
        rendered_group = False
        for test in tests:
            has_scenario_data = any(
                aggregated.get(server, {}).get(test) for server in servers
            )
            has_overall_data = any(
                aggregated_overall.get(server, {}).get(test) for server in servers
            )

            if not has_scenario_data and not has_overall_data:
                continue

            if not rendered_group:
                lines.append(f"## {group_name}")
                lines.append("")
                rendered_group = True

            heading = TEST_DEFINITIONS[test]["heading"]
            first_column = TEST_DEFINITIONS[test]["first_column"]
            if has_scenario_data:
                add_scenario_section(lines, aggregated, servers, test, heading, first_column)
                if test == "concurrent":
                    add_concurrent_workload_section(lines, aggregated, servers, report_metadata)
            else:
                add_overall_section(lines, aggregated_overall, servers, test, heading)

    add_cache_tier_section(lines, report_metadata)
    add_server_images_section(lines, report_metadata, servers)
    add_server_tuning_section(lines, report_metadata, servers)
    add_payload_comparability_section(lines, shape_audits, servers)
    add_audit_findings_section(lines, shape_audits, servers)
    add_shape_audit_section(lines, shape_audits, servers)

    report = "\n".join(lines)

    with open(output_path, "w") as f:
        f.write(report)
    print(f"Report written to {output_path}", file=sys.stderr)

    json_path = output_path.replace(".md", ".json")
    with open(json_path, "w") as f:
        json.dump(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "dataset": "small",
                "runs": runs,
                "run_metadata": report_metadata,
                "cache_tiers": {
                    test: entry.get("cache_tier")
                    for test, entry in report_metadata.get("tests", {}).items()
                },
                "results": {server: aggregated.get(server, {}) for server in servers},
                "overall_results": {server: aggregated_overall.get(server, {}) for server in servers},
                "response_shape_audits": {server: shape_audits.get(server, []) for server in servers},
            },
            f,
            indent=2,
        )
    print(f"JSON written to {json_path}", file=sys.stderr)


def ordered_tests(test_entries):
    ordered = [test for test in TEST_DEFINITIONS if test in test_entries]
    ordered.extend(sorted(test for test in test_entries if test not in TEST_DEFINITIONS))
    return ordered


def humanize_cache_tier(cache_tier):
    return str(cache_tier or "unknown").replace("_", " ")


def load_run_metadata(results_dir):
    results_path = Path(results_dir)
    metadata_path = results_path / "benchmark-metadata.json"
    metadata = {}
    if metadata_path.exists():
        try:
            with open(metadata_path) as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                metadata = loaded
        except (OSError, json.JSONDecodeError):
            metadata = {}

    default_cache_tier = metadata.get("default_cache_tier", "baseline")
    raw_tests = metadata.get("tests") if isinstance(metadata.get("tests"), dict) else {}

    observed_tests = []
    for path in sorted(results_path.glob("*-run*.json")):
        parsed = parse_result_filename(path.name)
        if not parsed:
            continue
        _server, test, _run = parsed
        if test not in observed_tests:
            observed_tests.append(test)

    if not observed_tests:
        observed_tests = ordered_tests(raw_tests)

    normalized_tests = {}
    for test in observed_tests:
        raw_entry = raw_tests.get(test) if isinstance(raw_tests.get(test), dict) else {}
        cache_tier = raw_entry.get("cache_tier") or ("warm_tile_cache" if test == "wmts" else default_cache_tier)
        entry = dict(raw_entry)
        entry["cache_tier"] = cache_tier
        wmts_cache_policy = raw_entry.get("wmts_cache_policy") or metadata.get("wmts_cache_policy")
        if test == "wmts" and wmts_cache_policy:
            entry["wmts_cache_policy"] = wmts_cache_policy
        normalized_tests[test] = entry

    metadata["default_cache_tier"] = default_cache_tier
    metadata["tests"] = normalized_tests
    return metadata


def add_cache_tier_section(lines, run_metadata):
    tests = run_metadata.get("tests", {}) if isinstance(run_metadata, dict) else {}
    if not tests:
        return

    lines.append("## Cache Tiers")
    lines.append("")
    lines.append(f"Default non-WMTS tier: `{run_metadata.get('default_cache_tier', 'baseline')}`")
    lines.append("")
    lines.append("| Test | Cache tier | Notes |")
    lines.append("| --- | --- | --- |")
    for test in ordered_tests(tests):
        entry = tests.get(test, {})
        notes = []
        if test == "wmts" and entry.get("wmts_cache_policy"):
            notes.append(f"wmts_cache_policy={entry['wmts_cache_policy']}")
        if test == "spatial-bbox" and run_metadata.get("bbox_tolerance_deg") is not None:
            notes.append(f"bbox_tolerance_deg={run_metadata['bbox_tolerance_deg']}")
        lines.append(
            f"| {test} | {humanize_cache_tier(entry.get('cache_tier'))} | {'; '.join(notes) or '-'} |"
        )
    lines.append("")


def add_server_tuning_section(lines, run_metadata, servers=None):
    tuning = run_metadata.get("server_tuning", {}) if isinstance(run_metadata, dict) else {}
    if not tuning:
        return

    lines.append("## Server Tuning")
    lines.append("")
    lines.append("| Server | Setting | Value |")
    lines.append("| --- | --- | --- |")
    for server in (servers or SERVERS):
        settings = tuning.get(server)
        if not isinstance(settings, dict):
            continue
        for key in sorted(settings):
            lines.append(f"| {SERVER_LABELS.get(server, server)} | `{key}` | `{settings[key]}` |")
    lines.append("")


def add_server_images_section(lines, run_metadata, servers=None):
    images = run_metadata.get("server_images", {}) if isinstance(run_metadata, dict) else {}
    if not images:
        return

    lines.append("## Server Images")
    lines.append("")
    lines.append("| Component | Image |")
    lines.append("| --- | --- |")
    for server in (servers or SERVERS):
        image = images.get(server)
        if image:
            lines.append(f"| {SERVER_LABELS.get(server, server)} | `{image}` |")
    for component in ("postgis", "k6"):
        image = images.get(component)
        if image:
            lines.append(f"| {component} | `{image}` |")
    lines.append("")


def main():
    parser = argparse.ArgumentParser(description="Generate GeoBench report")
    parser.add_argument("--results-dir", required=True, help="Directory with k6 JSON results")
    parser.add_argument("--output", required=True, help="Output markdown file")
    parser.add_argument("--runs", type=int, default=5, help="Number of runs (for labeling)")
    parser.add_argument("--servers", help="Comma- or space-separated server ids to include")
    args = parser.parse_args()
    selected_servers = None
    if args.servers:
        selected_servers = [
            part.strip()
            for chunk in args.servers.split()
            for part in chunk.split(",")
            if part.strip()
        ]
    generate_report(args.results_dir, args.output, args.runs, selected_servers)


if __name__ == "__main__":
    main()
