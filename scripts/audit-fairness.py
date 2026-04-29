#!/usr/bin/env python3
"""Audit a GeoBench result directory for publishability gotchas."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


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

SERVER_CARD_FILES = {
    "honua": "honua.json",
    "geoserver": "geoserver.json",
    "qgis": "qgis-server.json",
}


def supports_test(server: str, test: str) -> bool:
    if test in {"attribute-filter", "spatial-bbox", "concurrent", "wfs-getfeature"}:
        return True
    if test in {"wfs-filtered", "wms-filtered"}:
        return server in {"honua", "geoserver"}
    if test in {"wms-getmap", "wms-reprojection", "wms-getfeatureinfo"}:
        return server in {"honua", "geoserver", "qgis"}
    if test in {"wmts", "wcs"}:
        return server == "geoserver"
    if test in {"geoservices-query", "geoservices-query-diagnostics", "geoservices-identify"}:
        return server in {"honua", "geoserver"}
    if test == "geoservices-export":
        return server == "honua"
    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--servers", default="", help="Comma-separated server filter")
    parser.add_argument("--min-runs", type=int, default=5)
    parser.add_argument("--strict-equal-db-budget", action="store_true")
    parser.add_argument("--strict-payload-comparable", action="store_true")
    parser.add_argument("--allow-adaptive", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open() as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def comparable_value(entry: dict[str, Any], key: str) -> Any:
    value = entry.get(key)
    if isinstance(value, list):
        return tuple(value)
    if isinstance(value, dict):
        return tuple(sorted(value.items()))
    return value


def compare_shape_group(entries: list[dict[str, Any]]) -> tuple[str, str]:
    if len(entries) < 2:
        return "Single-server row", "No cross-server comparability claim"

    statuses = {entry.get("status") for entry in entries}
    if statuses != {200}:
        return "Blocked", "One or more servers did not return HTTP 200"

    family = entries[0].get("family")
    if family == "feature":
        for key in (
            "feature_count",
            "first_feature_geometry_type",
            "first_feature_property_keys",
            "first_feature_property_types",
        ):
            values = {comparable_value(entry, key) for entry in entries}
            if len(values) > 1:
                return "Not comparable", f"Core payload drift in {key}"
        return "Comparable", "Core payload shape matches or differs only in metadata"

    dimensions = {comparable_value(entry, "dimensions") for entry in entries}
    if len(dimensions) > 1:
        return "Not comparable", "Raster dimensions differ"
    return "Comparable", "Raster dimensions match"


def add(findings: list[tuple[str, str]], severity: str, message: str) -> None:
    findings.append((severity, message))


def parse_metric_name(metric_name: str) -> tuple[str, dict[str, str]]:
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


def scenario_tags(tags: dict[str, str]) -> tuple[tuple[str, str], ...] | None:
    keys = ("bbox_size", "query_type", "concurrency", "workload")
    selected = tuple((key, tags[key]) for key in keys if key in tags)
    return selected or None


def selected_servers(metadata: dict[str, Any], raw_filter: str) -> list[str]:
    if raw_filter.strip():
        return [part.strip() for part in raw_filter.split(",") if part.strip()]
    servers = metadata.get("servers")
    if isinstance(servers, list):
        return [str(server) for server in servers]
    return []


def audit_metadata(
    findings: list[tuple[str, str]],
    metadata: dict[str, Any],
    servers: list[str],
    args: argparse.Namespace,
) -> None:
    if not metadata:
        add(findings, "FAIL", "missing benchmark-metadata.json")
        return

    runs = metadata.get("runs")
    if not isinstance(runs, int) or runs < args.min_runs:
        add(findings, "WARN", f"runs={runs!r}; publishable median profile expects at least {args.min_runs}")

    tests = metadata.get("tests") if isinstance(metadata.get("tests"), dict) else {}
    default_cache_tier = str(metadata.get("default_cache_tier", "baseline"))
    if default_cache_tier not in {"baseline", "warm_service"}:
        selected_spatial = sorted(set(tests) & SPATIAL_CACHE_SENSITIVE_TESTS)
        if selected_spatial:
            add(
                findings,
                "FAIL",
                f"default_cache_tier={default_cache_tier!r} with spatial/render tests {selected_spatial}",
            )

    durations = {
        (entry.get("warmup_duration_seconds"), entry.get("scenario_duration_seconds"))
        for entry in tests.values()
        if isinstance(entry, dict) and "scenario_duration_seconds" in entry
    }
    if len(durations) > 1:
        add(findings, "WARN", f"mixed warmup/measurement windows in one result: {sorted(durations)}")

    tuning = metadata.get("server_tuning") if isinstance(metadata.get("server_tuning"), dict) else {}
    honua = tuning.get("honua") if isinstance(tuning.get("honua"), dict) else {}
    geoserver = tuning.get("geoserver") if isinstance(tuning.get("geoserver"), dict) else {}

    if "honua" in servers and honua:
        if honua.get("response_caching_enabled") is True and default_cache_tier == "baseline":
            add(findings, "FAIL", "Honua response caching enabled in a baseline result")
        if honua.get("adaptive_admission_enabled") is True and not args.allow_adaptive:
            add(findings, "WARN", "Honua adaptive admission enabled; publish as a named adaptive profile")
        if honua.get("max_concurrent_queries") != honua.get("max_connection_pool_size"):
            add(
                findings,
                "WARN",
                "Honua active-query cap and pool ceiling differ: "
                f"{honua.get('max_concurrent_queries')} vs {honua.get('max_connection_pool_size')}",
            )

    if {"honua", "geoserver"}.issubset(set(servers)) and honua and geoserver:
        honua_budget = honua.get("max_concurrent_queries")
        geoserver_budget = geoserver.get("max_connections")
        if honua_budget != geoserver_budget:
            severity = "FAIL" if args.strict_equal_db_budget else "WARN"
            add(
                findings,
                severity,
                "DB active budget differs between Honua and GeoServer: "
                f"Honua max_concurrent_queries={honua_budget}, "
                f"GeoServer max_connections={geoserver_budget}",
            )


def audit_system_cards(findings: list[tuple[str, str]], results_dir: Path, servers: list[str]) -> None:
    cards_dir = results_dir / "system-cards"
    for server in servers:
        card_name = SERVER_CARD_FILES.get(server)
        if card_name and not (cards_dir / card_name).exists():
            add(findings, "WARN", f"missing copied system card: system-cards/{card_name}")


def audit_run_counts(
    findings: list[tuple[str, str]],
    results_dir: Path,
    servers: list[str],
    metadata: dict[str, Any],
    min_runs: int,
) -> None:
    tests = metadata.get("tests") if isinstance(metadata.get("tests"), dict) else {}
    for server in servers:
        for test in tests:
            if not supports_test(server, test):
                continue
            count = len(list(results_dir.glob(f"{server}-{test}-run*.json")))
            if count < min_runs:
                add(findings, "WARN", f"incomplete run count for {server}/{test}: {count}/{min_runs}")


def audit_nonzero_scenario_samples(
    findings: list[tuple[str, str]],
    results_dir: Path,
    servers: list[str],
    min_runs: int,
) -> None:
    sample_runs: dict[tuple[str, str, tuple[tuple[str, str], ...]], set[str]] = defaultdict(set)
    zero_runs: dict[tuple[str, str, tuple[tuple[str, str], ...]], list[str]] = defaultdict(list)

    for server in servers:
        for path in sorted(results_dir.glob(f"{server}-*-run*.json")):
            rest = path.name[len(server) + 1:]
            if "-run" not in rest:
                continue
            test = rest.rsplit("-run", 1)[0]
            data = load_json(path)
            metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else {}
            for metric_name, metric in metrics.items():
                base, tags = parse_metric_name(str(metric_name))
                if base != "http_reqs" or not isinstance(metric, dict):
                    continue
                tag_key = scenario_tags(tags)
                if tag_key is None:
                    continue
                key = (server, test, tag_key)
                count = metric.get("count")
                try:
                    numeric_count = float(count)
                except (TypeError, ValueError):
                    continue
                if numeric_count > 0:
                    sample_runs[key].add(path.name)
                else:
                    zero_runs[key].append(path.name)

    for key in sorted(set(sample_runs) | set(zero_runs), key=str):
        server, test, tags = key
        nonzero = len(sample_runs.get(key, set()))
        if nonzero < min_runs:
            tag_text = ",".join(f"{name}={value}" for name, value in tags)
            zero_text = ", ".join(zero_runs.get(key, [])[:3])
            suffix = f"; zero-count runs include {zero_text}" if zero_text else ""
            add(
                findings,
                "WARN",
                f"nonzero scenario samples below target for {server}/{test} [{tag_text}]: "
                f"{nonzero}/{min_runs}{suffix}",
            )


def audit_run_errors(
    findings: list[tuple[str, str]],
    results_dir: Path,
    servers: list[str],
) -> None:
    for server in servers:
        for path in sorted(results_dir.glob(f"{server}-*-run*.json")):
            rest = path.name[len(server) + 1:]
            if "-run" not in rest:
                continue
            test = rest.rsplit("-run", 1)[0]
            data = load_json(path)
            metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else {}
            seen: set[tuple[str, tuple[tuple[str, str], ...] | None]] = set()
            for metric_name, metric in metrics.items():
                base, tags = parse_metric_name(str(metric_name))
                if base not in {"errors", "http_req_failed"} or not isinstance(metric, dict):
                    continue
                tag_key = scenario_tags(tags)
                duplicate_key = (path.name, tag_key)
                if duplicate_key in seen:
                    continue
                value = metric.get("value")
                try:
                    error_rate = float(value)
                except (TypeError, ValueError):
                    continue
                if error_rate <= 0:
                    continue
                seen.add(duplicate_key)
                tag_text = (
                    "overall"
                    if tag_key is None
                    else ",".join(f"{name}={value}" for name, value in tag_key)
                )
                add(
                    findings,
                    "WARN",
                    f"nonzero error rate in {path.name} {test} [{tag_text}]: {error_rate * 100:.3f}%",
                )


def audit_payload_shapes(
    findings: list[tuple[str, str]],
    results_dir: Path,
    servers: list[str],
    metadata: dict[str, Any],
    args: argparse.Namespace,
) -> None:
    groups: dict[tuple[Any, Any, Any], list[dict[str, Any]]] = defaultdict(list)
    audit_shapes = metadata.get("audit_shapes", 0)
    for server in servers:
        path = results_dir / f"{server}-response-shapes.json"
        if audit_shapes and not path.exists():
            add(findings, "WARN", f"missing response-shape audit for {server}")
            continue
        data = load_json(path)
        entries = data.get("entries") if isinstance(data.get("entries"), list) else []
        for entry in entries:
            if isinstance(entry, dict):
                groups[(entry.get("family"), entry.get("suite"), entry.get("request"))].append(entry)

    for (_family, suite, request), entries in sorted(groups.items(), key=lambda item: str(item[0])):
        verdict, note = compare_shape_group(entries)
        if verdict == "Not comparable":
            severity = "FAIL" if args.strict_payload_comparable else "WARN"
            add(findings, severity, f"payload not comparable for {suite}/{request}: {note}")


def main() -> int:
    args = parse_args()
    results_dir = Path(args.results_dir)
    metadata = load_json(results_dir / "benchmark-metadata.json")
    servers = selected_servers(metadata, args.servers)
    findings: list[tuple[str, str]] = []

    if not servers:
        add(findings, "FAIL", "no servers selected or recorded in metadata")
    else:
        audit_metadata(findings, metadata, servers, args)
        audit_system_cards(findings, results_dir, servers)
        audit_run_counts(findings, results_dir, servers, metadata, args.min_runs)
        audit_nonzero_scenario_samples(findings, results_dir, servers, args.min_runs)
        audit_run_errors(findings, results_dir, servers)
        audit_payload_shapes(findings, results_dir, servers, metadata, args)

    if findings:
        for severity, message in findings:
            print(f"{severity}: {message}")
    else:
        print("PASS: no fairness gotchas detected")

    return 1 if any(severity == "FAIL" for severity, _ in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
