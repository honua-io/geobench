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


def compute_metrics(values):
    """Compute benchmark metrics from a list of duration values (ms)."""
    if not values:
        return None

    values_sorted = sorted(values)
    n = len(values_sorted)

    return {
        "rps": round_metric(n / 120.0),
        "p50": round_metric(values_sorted[min(int(n * 0.50), n - 1)]),
        "p95": round_metric(values_sorted[min(int(n * 0.95), n - 1)]),
        "p99": round_metric(values_sorted[min(int(n * 0.99), n - 1)]),
    }


def metrics_from_summary(duration_metric, request_metric):
    if not duration_metric or not request_metric:
        return None

    return {
        "rps": round_metric(request_metric.get("rate")),
        "p50": round_metric(duration_metric.get("med")),
        "p95": round_metric(duration_metric.get("p(95)")),
        "p99": round_metric(duration_metric.get("p(99)")),
    }


def parse_k6_point_stream(filepath):
    """Parse a k6 point-stream JSON file into scenario metrics."""
    test = None
    parsed_name = parse_result_filename(Path(filepath).name)
    if parsed_name:
        _, test, _ = parsed_name

    definitions = TEST_DEFINITIONS.get(test, {}).get("scenarios", [])
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

    parsed = {}
    for scenario, values in points.items():
        metrics = compute_metrics(values)
        if metrics:
            parsed[scenario] = metrics
    return parsed


def parse_k6_summary(data, test):
    """Parse a k6 summary-export JSON object into scenario and overall metrics."""
    metrics = data.get("metrics", {})
    definitions = TEST_DEFINITIONS.get(test, {}).get("scenarios", [])

    by_scenario = {}
    for definition in definitions:
        scenario_id = definition["id"]
        tag_key = definition["tag_key"]
        tag_value = definition["tag_value"]
        duration_metric = metrics.get(f"http_req_duration{{{tag_key}:{tag_value}}}")
        request_metric = metrics.get(f"http_reqs{{{tag_key}:{tag_value}}}")
        parsed = metrics_from_summary(duration_metric, request_metric)
        if parsed:
            by_scenario[scenario_id] = parsed

    overall = metrics_from_summary(
        metrics.get("http_req_duration"),
        metrics.get("http_reqs"),
    )

    return by_scenario, overall


def parse_result_file(filepath, test):
    """Parse either summary JSON or point-stream JSON results."""
    try:
        with open(filepath) as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return parse_k6_point_stream(filepath), None

    if isinstance(data, dict) and "metrics" in data:
        return parse_k6_summary(data, test)

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


def collect_results(results_dir):
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
        scenario_metrics, overall_metrics = parse_result_file(filepath, test)

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
            "first_feature_id_kind",
        ]
        metadata_only = []
        for key in core_keys:
            values = {comparable_shape_value(entry, key) for entry in entries}
            if len(values) > 1:
                return "Not comparable", f"Core payload drift in {key}"

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


def generate_report(results_dir, output_path, runs):
    aggregated, aggregated_overall = collect_results(results_dir)
    shape_audits = collect_shape_audits(results_dir)
    discovered_servers = set(aggregated.keys()) | set(aggregated_overall.keys()) | set(shape_audits.keys())
    servers = [server for server in SERVERS if server in discovered_servers]
    servers.extend(sorted(discovered_servers - set(servers)))

    if not servers:
        print("No results found in " + results_dir, file=sys.stderr)
        sys.exit(1)

    lines = []
    lines.append("# GeoBench Results")
    lines.append("")
    lines.append(
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )
    lines.append(f"Dataset: Small (100K points) | Runs: {runs} (median reported)")
    lines.append("")

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
            else:
                add_overall_section(lines, aggregated_overall, servers, test, heading)

    run_metadata = load_run_metadata(results_dir)

    add_cache_tier_section(lines, run_metadata)
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
                "run_metadata": run_metadata,
                "cache_tiers": {
                    test: entry.get("cache_tier")
                    for test, entry in run_metadata.get("tests", {}).items()
                },
                "results": aggregated,
                "overall_results": aggregated_overall,
                "response_shape_audits": shape_audits,
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

    default_cache_tier = metadata.get("default_cache_tier", "warm_service")
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
        entry = {"cache_tier": cache_tier}
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
    lines.append(f"Default non-WMTS tier: `{run_metadata.get('default_cache_tier', 'warm_service')}`")
    lines.append("")
    lines.append("| Test | Cache tier | Notes |")
    lines.append("| --- | --- | --- |")
    for test in ordered_tests(tests):
        entry = tests.get(test, {})
        notes = []
        if test == "wmts" and entry.get("wmts_cache_policy"):
            notes.append(f"wmts_cache_policy={entry['wmts_cache_policy']}")
        lines.append(
            f"| {test} | {humanize_cache_tier(entry.get('cache_tier'))} | {'; '.join(notes) or '-'} |"
        )
    lines.append("")


def main():
    parser = argparse.ArgumentParser(description="Generate GeoBench report")
    parser.add_argument("--results-dir", required=True, help="Directory with k6 JSON results")
    parser.add_argument("--output", required=True, help="Output markdown file")
    parser.add_argument("--runs", type=int, default=5, help="Number of runs (for labeling)")
    args = parser.parse_args()
    generate_report(args.results_dir, args.output, args.runs)


if __name__ == "__main__":
    main()
