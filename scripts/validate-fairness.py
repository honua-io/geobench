#!/usr/bin/env python3
"""Validate that benchmark requests are semantically equivalent across servers."""

from __future__ import annotations

import argparse
import json
import random
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


CATEGORIES = [
    "park",
    "building",
    "road",
    "bridge",
    "water",
    "forest",
    "farm",
    "commercial",
    "residential",
    "industrial",
]

HOTSPOTS = [
    {"lon": -73.98, "lat": 40.75},
    {"lon": 2.35, "lat": 48.86},
    {"lon": 139.69, "lat": 35.69},
    {"lon": -46.63, "lat": -23.55},
    {"lon": 151.21, "lat": -33.87},
]


@dataclass(frozen=True)
class ServerConfig:
    name: str
    base_url: str
    filter_mode: str
    offset_param: str
    collection: str = "bench_points"
    map_path: str | None = None
    collection_id: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--server",
        action="append",
        choices=["honua", "geoserver", "qgis"],
        help="Validate only specific servers; repeatable.",
    )
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--cases-per-operator", type=int, default=40)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--include-scan", action="store_true")
    return parser.parse_args()


def server_configs() -> dict[str, ServerConfig]:
    return {
        "honua": ServerConfig(
            name="honua",
            base_url="http://localhost:8081",
            filter_mode="cql2",
            offset_param="offset",
            collection_id="1",
        ),
        "geoserver": ServerConfig(
            name="geoserver",
            base_url="http://localhost:8082",
            filter_mode="cql2",
            offset_param="startIndex",
        ),
        "qgis": ServerConfig(
            name="qgis",
            base_url="http://localhost:8083",
            filter_mode="wfs-fes",
            offset_param="offset",
            map_path="/etc/qgisserver/geobench.qgs",
        ),
    }


def escape_xml(text: Any) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def escape_like_prefix(prefix: str) -> str:
    return prefix.replace("\\", "\\\\").replace("_", "\\_").replace("%", "\\%")


def quote_cql_literal(value: Any) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def normalize_filter_spec(spec: dict[str, Any] | None) -> dict[str, Any] | None:
    if not spec:
        return None
    if spec["type"] == "between":
        return {
            "type": spec["type"],
            "field": spec["field"],
            "low": round(float(spec["low"]), 1),
            "high": round(float(spec["high"]), 1),
        }
    return spec


def build_cql2_filter(spec: dict[str, Any]) -> str:
    if spec["type"] == "eq":
        return f"{spec['field']}={quote_cql_literal(spec['value'])}"
    if spec["type"] == "between":
        return (
            f"{spec['field']} >= {spec['low']:.1f} AND "
            f"{spec['field']} <= {spec['high']:.1f}"
        )
    if spec["type"] == "prefix":
        return f"{spec['field']} LIKE {quote_cql_literal(spec['prefix'] + '%')}"
    raise ValueError(f"unsupported filter spec: {spec}")


def build_qgis_filter_xml(spec: dict[str, Any]) -> str:
    if spec["type"] == "eq":
        return (
            '<Filter xmlns="http://www.opengis.net/ogc">'
            "<PropertyIsEqualTo>"
            f"<PropertyName>{escape_xml(spec['field'])}</PropertyName>"
            f"<Literal>{escape_xml(spec['value'])}</Literal>"
            "</PropertyIsEqualTo>"
            "</Filter>"
        )
    if spec["type"] == "between":
        return (
            '<Filter xmlns="http://www.opengis.net/ogc">'
            "<PropertyIsBetween>"
            f"<PropertyName>{escape_xml(spec['field'])}</PropertyName>"
            f"<LowerBoundary><Literal>{spec['low']:.1f}</Literal></LowerBoundary>"
            f"<UpperBoundary><Literal>{spec['high']:.1f}</Literal></UpperBoundary>"
            "</PropertyIsBetween>"
            "</Filter>"
        )
    if spec["type"] == "prefix":
        return (
            '<Filter xmlns="http://www.opengis.net/ogc">'
            '<PropertyIsLike wildCard="%" singleChar="_" escapeChar="\\">'
            f"<PropertyName>{escape_xml(spec['field'])}</PropertyName>"
            f"<Literal>{escape_xml(escape_like_prefix(spec['prefix']) + '%')}</Literal>"
            "</PropertyIsLike>"
            "</Filter>"
        )
    raise ValueError(f"unsupported filter spec: {spec}")


def build_items_url(
    server: ServerConfig,
    *,
    limit: int,
    filter_spec: dict[str, Any] | None = None,
    bbox: str | None = None,
    offset: int | None = None,
    sort_by: str = "id",
) -> str:
    filter_spec = normalize_filter_spec(filter_spec)

    if filter_spec and server.filter_mode == "wfs-fes":
        query = {
            "MAP": server.map_path or "",
            "SERVICE": "WFS",
            "VERSION": "1.1.0",
            "REQUEST": "GetFeature",
            "TYPENAME": server.collection,
            "MAXFEATURES": limit,
            "SORTBY": sort_by,
            "OUTPUTFORMAT": "application/vnd.geo+json",
            "FILTER": build_qgis_filter_xml(filter_spec),
        }
        return f"{server.base_url}/ows/?{urllib.parse.urlencode(query)}"

    if server.name == "honua":
        path = f"/ogc/features/collections/{server.collection_id}/items"
    elif server.name == "geoserver":
        path = f"/geoserver/ogc/features/v1/collections/geobench:{server.collection}/items"
    elif server.name == "qgis":
        path = f"/wfs3/collections/{server.collection}/items"
    else:
        raise ValueError(f"unknown server {server.name}")

    query: dict[str, Any] = {"f": "json", "limit": limit, "sortby": sort_by}
    if bbox:
        query["bbox"] = bbox
    if filter_spec:
        query["filter"] = build_cql2_filter(filter_spec)
        query["filter-lang"] = "cql2-text"
    if offset is not None:
        query[server.offset_param] = offset
    return f"{server.base_url}{path}?{urllib.parse.urlencode(query)}"


def fetch_json(url: str) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
        return response.status, payload


def validate_payload(
    payload: dict[str, Any],
    *,
    filter_spec: dict[str, Any] | None = None,
    bbox: str | None = None,
    offset: int | None = None,
) -> tuple[bool, dict[str, Any]]:
    features = payload.get("features") or []

    if bbox:
        min_lon, min_lat, max_lon, max_lat = map(float, bbox.split(","))
        for feature in features:
            coords = ((feature.get("geometry") or {}).get("coordinates") or [])
            if len(coords) < 2:
                return False, {"reason": "missing coordinates", "feature": feature}
            if not (
                min_lon <= coords[0] <= max_lon and min_lat <= coords[1] <= max_lat
            ):
                return False, {
                    "reason": "feature outside bbox",
                    "feature_id": (feature.get("properties") or {}).get("id"),
                    "coords": coords,
                    "bbox": bbox,
                }
        return True, {"rows": len(features)}

    if filter_spec:
        field = filter_spec["field"]
        for feature in features:
            props = feature.get("properties") or {}
            value = props.get(field)
            valid = False
            if filter_spec["type"] == "eq":
                valid = str(value) == str(filter_spec["value"])
            elif filter_spec["type"] == "between":
                try:
                    numeric = float(value)
                except (TypeError, ValueError):
                    numeric = None
                valid = numeric is not None and filter_spec["low"] <= numeric <= filter_spec["high"]
            elif filter_spec["type"] == "prefix":
                valid = str(value).startswith(filter_spec["prefix"])

            if not valid:
                return False, {
                    "reason": "filter mismatch",
                    "filter_spec": filter_spec,
                    "feature_id": props.get("id"),
                    "value": value,
                    "properties": props,
                }

        return True, {"rows": len(features)}

    if offset is not None:
        if not features:
            return False, {"reason": "empty page"}
        for index, feature in enumerate(features):
            props = feature.get("properties") or {}
            raw_id = props.get("id", feature.get("id"))
            if raw_id is None:
                return False, {"reason": "missing feature id", "feature": feature}
            if isinstance(raw_id, str) and "." in raw_id:
                raw_id = raw_id.rsplit(".", 1)[-1]
            try:
                numeric_id = int(raw_id)
            except (TypeError, ValueError):
                return False, {"reason": "non-numeric feature id", "raw_id": raw_id}
            expected_id = offset + index + 1
            if numeric_id != expected_id:
                return False, {
                    "reason": "unexpected page order",
                    "feature_id": numeric_id,
                    "expected_id": expected_id,
                    "offset": offset,
                }
        return True, {"rows": len(features)}

    return True, {"rows": len(features)}


def build_cases(count: int, seed: int) -> list[tuple[str, dict[str, Any]]]:
    random.seed(seed)
    cases: list[tuple[str, dict[str, Any]]] = []

    for _ in range(count):
        category = random.choice(CATEGORIES)
        cases.append(
            (
                "equality",
                {"type": "eq", "field": "category", "value": category},
            )
        )

    for _ in range(count):
        low = -20 + random.random() * 60
        cases.append(
            (
                "range",
                {
                    "type": "between",
                    "field": "temperature",
                    "low": low,
                    "high": low + 10,
                },
            )
        )

    for _ in range(count):
        prefix = "feature_" + str(random.randrange(1000))
        cases.append(
            (
                "like",
                {"type": "prefix", "field": "feature_name", "prefix": prefix},
            )
        )

    return cases


def build_scan_offsets(count: int, seed: int) -> list[int]:
    random.seed(seed + 1000)
    return [random.randrange(1000) for _ in range(count)]


def random_bbox(size_deg: float) -> str:
    center = random.choice(HOTSPOTS)
    half = size_deg / 2.0
    jitter = (random.random() - 0.5) * size_deg
    min_lon = max(-180.0, center["lon"] - half + jitter)
    min_lat = max(-90.0, center["lat"] - half + jitter)
    max_lon = min(180.0, min_lon + size_deg)
    max_lat = min(90.0, min_lat + size_deg)
    return f"{min_lon:.4f},{min_lat:.4f},{max_lon:.4f},{max_lat:.4f}"


def build_bboxes(count: int, seed: int) -> list[str]:
    random.seed(seed + 2000)
    sizes = [0.1, 5.0, 30.0]
    return [random_bbox(random.choice(sizes)) for _ in range(count)]


def main() -> int:
    args = parse_args()
    configs = server_configs()
    names = args.server or ["honua", "geoserver", "qgis"]
    cases = build_cases(args.cases_per_operator, args.seed)
    scan_offsets = build_scan_offsets(args.cases_per_operator, args.seed)
    bboxes = build_bboxes(args.cases_per_operator, args.seed)
    exit_code = 0

    for name in names:
        config = configs[name]
        print(f"SERVER {name}")
        summary: dict[str, dict[str, Any]] = {}

        for operator, spec in cases:
            info = summary.setdefault(
                operator,
                {"ok": 0, "fail": 0, "sample_failures": []},
            )
            normalized_spec = normalize_filter_spec(spec)
            url = build_items_url(config, limit=args.limit, filter_spec=normalized_spec)

            try:
                status, payload = fetch_json(url)
                if status != 200:
                    info["fail"] += 1
                    if len(info["sample_failures"]) < 3:
                        info["sample_failures"].append(
                            {"reason": "http status", "status": status, "url": url}
                        )
                    continue
                ok, detail = validate_payload(payload, filter_spec=normalized_spec)
                if ok:
                    info["ok"] += 1
                else:
                    info["fail"] += 1
                    if len(info["sample_failures"]) < 3:
                        info["sample_failures"].append(
                            {"url": url, "detail": detail, "rows": len(payload.get("features") or [])}
                        )
            except Exception as exc:  # pragma: no cover - diagnostic output
                info["fail"] += 1
                if len(info["sample_failures"]) < 3:
                    info["sample_failures"].append(
                        {"reason": "exception", "error": repr(exc), "url": url}
                    )

        bbox_info = summary.setdefault(
            "bbox",
            {"ok": 0, "fail": 0, "sample_failures": []},
        )
        for bbox in bboxes:
            url = build_items_url(config, limit=args.limit, bbox=bbox)
            try:
                status, payload = fetch_json(url)
                if status != 200:
                    bbox_info["fail"] += 1
                    if len(bbox_info["sample_failures"]) < 3:
                        bbox_info["sample_failures"].append(
                            {"reason": "http status", "status": status, "url": url}
                        )
                    continue
                ok, detail = validate_payload(payload, bbox=bbox)
                if ok:
                    bbox_info["ok"] += 1
                else:
                    bbox_info["fail"] += 1
                    if len(bbox_info["sample_failures"]) < 3:
                        bbox_info["sample_failures"].append({"url": url, "detail": detail})
            except Exception as exc:  # pragma: no cover - diagnostic output
                bbox_info["fail"] += 1
                if len(bbox_info["sample_failures"]) < 3:
                    bbox_info["sample_failures"].append(
                        {"reason": "exception", "error": repr(exc), "url": url}
                    )

        if args.include_scan:
            scan_info = summary.setdefault(
                "scan",
                {"ok": 0, "fail": 0, "sample_failures": []},
            )
            for offset in scan_offsets:
                url = build_items_url(config, limit=args.limit, offset=offset)
                try:
                    status, payload = fetch_json(url)
                    if status != 200:
                        scan_info["fail"] += 1
                        if len(scan_info["sample_failures"]) < 3:
                            scan_info["sample_failures"].append(
                                {"reason": "http status", "status": status, "url": url}
                            )
                        continue
                    ok, detail = validate_payload(payload, offset=offset)
                    if ok:
                        scan_info["ok"] += 1
                    else:
                        scan_info["fail"] += 1
                        if len(scan_info["sample_failures"]) < 3:
                            scan_info["sample_failures"].append({"url": url, "detail": detail})
                except Exception as exc:  # pragma: no cover - diagnostic output
                    scan_info["fail"] += 1
                    if len(scan_info["sample_failures"]) < 3:
                        scan_info["sample_failures"].append(
                            {"reason": "exception", "error": repr(exc), "url": url}
                        )

        print(json.dumps(summary, indent=2))
        if any(info["fail"] for info in summary.values()):
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
