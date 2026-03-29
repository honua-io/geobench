#!/usr/bin/env python3
"""Capture lightweight response-shape samples alongside GeoBench runs.

This is intentionally small and publication-safe. It records only headers,
sizes, hashes, and compact structural notes, never the raw body content.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_IMAGE_SIZE = 256


@dataclass(frozen=True)
class ServerConfig:
    name: str
    base_url: str


def env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def http_get(url: str) -> tuple[int, str, bytes]:
    request = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.headers.get("Content-Type", ""), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, (exc.headers.get("Content-Type", "") if exc.headers else ""), exc.read() if exc.fp else b""


def http_get_json(url: str) -> tuple[int, str, bytes, Any]:
    status, content_type, body = http_get(url)
    payload = None
    if body:
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            payload = None
    return status, content_type, body, payload


def top_level_keys(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        return sorted(payload.keys())
    return []


def feature_shape(payload: Any) -> dict[str, Any]:
    features = []
    if isinstance(payload, dict):
        raw_features = payload.get("features")
        if isinstance(raw_features, list):
            features = raw_features

    first_feature = features[0] if features else {}
    if not isinstance(first_feature, dict):
        first_feature = {}

    properties = first_feature.get("properties")
    if not isinstance(properties, dict):
        properties = {}
    geometry = first_feature.get("geometry")
    if not isinstance(geometry, dict):
        geometry = {}

    feature_id = first_feature.get("id")
    if feature_id is None:
        feature_id = properties.get("id")

    if feature_id is None:
        feature_id_kind = "missing"
    elif isinstance(feature_id, bool):
        feature_id_kind = "boolean"
    elif isinstance(feature_id, (int, float)):
        feature_id_kind = "number"
    else:
        feature_id_kind = "string"

    summary = "; ".join(
        [
            f"top_keys={','.join(top_level_keys(payload)) or '-'}",
            f"features={len(features)}",
            f"first_id={feature_id_kind}",
            f"first_geom={geometry.get('type') or '-'}",
            f"first_props={','.join(sorted(properties.keys())[:8]) or '-'}",
        ]
    )

    return {
        "top_level_keys": top_level_keys(payload),
        "feature_count": len(features),
        "first_feature_property_keys": sorted(properties.keys()),
        "first_feature_geometry_type": geometry.get("type"),
        "first_feature_id_kind": feature_id_kind,
        "summary": summary,
    }


def geoservices_feature_shape(payload: Any) -> dict[str, Any]:
    features = []
    if isinstance(payload, dict):
        raw_features = payload.get("features")
        if isinstance(raw_features, list):
            features = raw_features

    first_feature = features[0] if features else {}
    if not isinstance(first_feature, dict):
        first_feature = {}

    attributes = first_feature.get("attributes")
    if not isinstance(attributes, dict):
        attributes = {}

    geometry = first_feature.get("geometry")
    if not isinstance(geometry, dict):
        geometry = {}

    geometry_type = "-"
    if "x" in geometry and "y" in geometry:
        geometry_type = "Point"
    elif "paths" in geometry:
        geometry_type = "Polyline"
    elif "rings" in geometry:
        geometry_type = "Polygon"

    feature_id = (
        attributes.get("OBJECTID")
        or attributes.get("objectid")
        or attributes.get("id")
    )
    if feature_id is None:
        feature_id_kind = "missing"
    elif isinstance(feature_id, bool):
        feature_id_kind = "boolean"
    elif isinstance(feature_id, (int, float)):
        feature_id_kind = "number"
    else:
        feature_id_kind = "string"

    summary = "; ".join(
        [
            f"top_keys={','.join(top_level_keys(payload)) or '-'}",
            f"features={len(features)}",
            f"first_id={feature_id_kind}",
            f"first_geom={geometry_type}",
            f"first_attrs={','.join(sorted(attributes.keys())[:8]) or '-'}",
        ]
    )

    return {
        "top_level_keys": top_level_keys(payload),
        "feature_count": len(features),
        "first_feature_property_keys": sorted(attributes.keys()),
        "first_feature_geometry_type": geometry_type,
        "first_feature_id_kind": feature_id_kind,
        "summary": summary,
    }


def parse_png_dimensions(body: bytes) -> dict[str, int] | None:
    if len(body) < 24:
        return None
    if body[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    if body[12:16] != b"IHDR":
        return None
    return {
        "width": int.from_bytes(body[16:20], "big"),
        "height": int.from_bytes(body[20:24], "big"),
    }


def raster_shape(body: bytes) -> dict[str, Any]:
    dimensions = parse_png_dimensions(body)
    summary = f"bytes={len(body)}"
    if dimensions:
        summary += f"; dimensions={dimensions['width']}x{dimensions['height']}"
    return {"dimensions": dimensions, "summary": summary}


def server_config(server: str) -> ServerConfig:
    server = server.lower()
    if server == "honua":
        return ServerConfig(
            "honua",
            env("HONUA_URL", f"http://localhost:{env('HONUA_PORT', '8081')}"),
        )
    if server == "geoserver":
        return ServerConfig(
            "geoserver",
            env("GEOSERVER_URL", f"http://localhost:{env('GEOSERVER_PORT', '8082')}"),
        )
    if server == "qgis":
        return ServerConfig(
            "qgis",
            env("QGIS_URL", f"http://localhost:{env('QGIS_PORT', '8083')}"),
        )
    raise ValueError(f"Unsupported server: {server}")


def feature_requests(server: ServerConfig) -> list[dict[str, str]]:
    if server.name == "honua":
        base = f"{server.base_url}/ogc/features/collections/1/items"
        return [
            {"family": "feature", "protocol": "ogc-api", "suite": "attribute-filter", "request": "equality", "url": base + "?f=json&limit=100&filter=category%20%3D%20'park'&filter-lang=cql2-text"},
            {"family": "feature", "protocol": "ogc-api", "suite": "spatial-bbox", "request": "small", "url": base + "?f=json&limit=100&bbox=139.2325,35.2325,139.3325,35.3325"},
        ]
    if server.name == "geoserver":
        base = f"{server.base_url}/geoserver/ogc/features/v1/collections/geobench:bench_points/items"
        return [
            {"family": "feature", "protocol": "ogc-api", "suite": "attribute-filter", "request": "equality", "url": base + "?f=json&limit=100&filter=category%20%3D%20'park'&filter-lang=cql2-text"},
            {"family": "feature", "protocol": "ogc-api", "suite": "spatial-bbox", "request": "small", "url": base + "?f=json&limit=100&bbox=139.2325,35.2325,139.3325,35.3325"},
        ]
    if server.name == "qgis":
        base = f"{server.base_url}/wfs3/collections/bench_points/items"
        return [
            {"family": "feature", "protocol": "ogc-api", "suite": "attribute-filter", "request": "base-read", "url": base + "?limit=100"},
            {"family": "feature", "protocol": "ogc-api", "suite": "spatial-bbox", "request": "small", "url": base + "?limit=100&bbox=139.2325,35.2325,139.3325,35.3325"},
        ]
    return []


def wfs_requests(server: ServerConfig) -> list[dict[str, str]]:
    if server.name == "honua":
        base = f"{server.base_url}/wfs"
        return [
            {"family": "feature", "protocol": "wfs", "suite": "wfs-getfeature", "request": "base", "url": base + "?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=bench_points&COUNT=100&OUTPUTFORMAT=application/json"},
            {"family": "feature", "protocol": "wfs", "suite": "wfs-getfeature", "request": "small-bbox", "url": base + "?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=bench_points&COUNT=100&BBOX=139.2325,35.2325,139.3325,35.3325&OUTPUTFORMAT=application/json"},
        ]
    if server.name == "geoserver":
        base = f"{server.base_url}/geoserver/wfs"
        return [
            {"family": "feature", "protocol": "wfs", "suite": "wfs-getfeature", "request": "base", "url": base + "?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=geobench:bench_points&COUNT=100&OUTPUTFORMAT=application/json"},
            {"family": "feature", "protocol": "wfs", "suite": "wfs-getfeature", "request": "small-bbox", "url": base + "?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=geobench:bench_points&COUNT=100&BBOX=139.2325,35.2325,139.3325,35.3325,EPSG:4326&OUTPUTFORMAT=application/json"},
        ]
    if server.name == "qgis":
        map_path = urllib.parse.quote(env("QGIS_MAP_PATH", "/etc/qgisserver/geobench.qgs"))
        base = f"{server.base_url}/ows/"
        return [
            {"family": "feature", "protocol": "wfs", "suite": "wfs-getfeature", "request": "base", "url": base + "?MAP=" + map_path + "&SERVICE=WFS&VERSION=1.1.0&REQUEST=GetFeature&TYPENAME=bench_points&MAXFEATURES=100&OUTPUTFORMAT=application/vnd.geo+json"},
            {"family": "feature", "protocol": "wfs", "suite": "wfs-getfeature", "request": "small-bbox", "url": base + "?MAP=" + map_path + "&SERVICE=WFS&VERSION=1.1.0&REQUEST=GetFeature&TYPENAME=bench_points&MAXFEATURES=100&BBOX=139.2325,35.2325,139.3325,35.3325&OUTPUTFORMAT=application/vnd.geo+json"},
        ]
    return []


def raster_requests(server: ServerConfig, enabled_tests: list[str]) -> list[dict[str, str]]:
    requests: list[dict[str, str]] = []
    if server.name == "honua":
        if "wms-getmap" in enabled_tests:
            requests.append(
                {
                    "family": "raster",
                    "protocol": "wms",
                    "suite": "wms-getmap",
                    "request": "small",
                    "url": f"{server.base_url}/ogc/services/default/wms?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=bench_points&STYLES=&CRS=CRS:84&BBOX=139.2325,35.2325,139.3325,35.3325&WIDTH={DEFAULT_IMAGE_SIZE}&HEIGHT={DEFAULT_IMAGE_SIZE}&FORMAT=image/png&TRANSPARENT=true",
                }
            )
        if "geoservices-export" in enabled_tests:
            requests.append(
                {
                    "family": "raster",
                    "protocol": "geoservices-rest",
                    "suite": "geoservices-export",
                    "request": "small",
                    "url": f"{server.base_url}/rest/services/default/MapServer/export?bbox=139.2325,35.2325,139.3325,35.3325&bboxSR=4326&imageSR=4326&size={DEFAULT_IMAGE_SIZE},{DEFAULT_IMAGE_SIZE}&format=png&transparent=true&f=image",
                }
            )
        return requests
    if server.name == "geoserver":
        if "wms-getmap" in enabled_tests:
            requests.append(
                {
                    "family": "raster",
                    "protocol": "wms",
                    "suite": "wms-getmap",
                    "request": "small",
                    "url": f"{server.base_url}/geoserver/wms?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=geobench:bench_points&STYLES=&CRS=CRS:84&BBOX=139.2325,35.2325,139.3325,35.3325&WIDTH={DEFAULT_IMAGE_SIZE}&HEIGHT={DEFAULT_IMAGE_SIZE}&FORMAT=image/png&TRANSPARENT=true",
                }
            )
        return requests
    if server.name == "qgis":
        map_path = urllib.parse.quote(env("QGIS_MAP_PATH", "/etc/qgisserver/geobench.qgs"))
        if "wms-getmap" in enabled_tests:
            requests.append(
                {
                    "family": "raster",
                    "protocol": "wms",
                    "suite": "wms-getmap",
                    "request": "small",
                    "url": f"{server.base_url}/ows/?MAP={map_path}&SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=bench_points&STYLES=&CRS=CRS:84&BBOX=139.2325,35.2325,139.3325,35.3325&WIDTH={DEFAULT_IMAGE_SIZE}&HEIGHT={DEFAULT_IMAGE_SIZE}&FORMAT=image/png&TRANSPARENT=true",
                }
            )
        return requests
    return requests


def build_geoservices_query_url(base: str, params: dict[str, Any]) -> str:
    return base + "?" + urllib.parse.urlencode(params)


def geoservices_feature_requests(server: ServerConfig) -> list[dict[str, str]]:
    if server.name == "honua":
        base = (
            f"{server.base_url}/rest/services/"
            f"{env('HONUA_GSR_SERVICE_ID', env('HONUA_SERVICE_NAME', 'default'))}"
            f"/FeatureServer/{env('HONUA_GSR_LAYER_ID', env('HONUA_COLLECTION_ID', '1'))}/query"
        )
    elif server.name == "geoserver":
        base = (
            f"{server.base_url}/geoserver/gsr/services/"
            f"{env('GEOSERVER_GSR_SERVICE', 'geobench')}"
            f"/FeatureServer/{env('GEOSERVER_GSR_LAYER_ID', '0')}/query"
        )
    else:
        return []

    base_params = {
        "f": "json",
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
    }
    bbox = {
        "geometry": "139.5650,35.5650,139.8150,35.8150",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
    }

    return [
        {
            "family": "feature",
            "protocol": "geoservices-rest",
            "suite": "geoservices-query",
            "request": "small-bbox",
            "url": build_geoservices_query_url(base, {**base_params, **bbox}),
        },
    ]


def geoservices_diagnostic_requests(server: ServerConfig) -> list[dict[str, str]]:
    if server.name == "honua":
        base = (
            f"{server.base_url}/rest/services/"
            f"{env('HONUA_GSR_SERVICE_ID', env('HONUA_SERVICE_NAME', 'default'))}"
            f"/FeatureServer/{env('HONUA_GSR_LAYER_ID', env('HONUA_COLLECTION_ID', '1'))}/query"
        )
    elif server.name == "geoserver":
        base = (
            f"{server.base_url}/geoserver/gsr/services/"
            f"{env('GEOSERVER_GSR_SERVICE', 'geobench')}"
            f"/FeatureServer/{env('GEOSERVER_GSR_LAYER_ID', '0')}/query"
        )
    else:
        return []

    variants = [
        {
            "request": "medium-full",
            "params": {
                "f": "json",
                "where": "1=1",
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": "4326",
                "geometry": "139.4400,35.4400,139.9400,35.9400",
                "geometryType": "esriGeometryEnvelope",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
            },
        },
        {
            "request": "medium-attrs-only",
            "params": {
                "f": "json",
                "where": "1=1",
                "outFields": "*",
                "returnGeometry": "false",
                "outSR": "4326",
                "geometry": "139.4400,35.4400,139.9400,35.9400",
                "geometryType": "esriGeometryEnvelope",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
            },
        },
        {
            "request": "medium-geom-oid",
            "params": {
                "f": "json",
                "where": "1=1",
                "outFields": "objectid",
                "returnGeometry": "true",
                "outSR": "4326",
                "geometry": "139.4400,35.4400,139.9400,35.9400",
                "geometryType": "esriGeometryEnvelope",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
            },
        },
        {
            "request": "large-full",
            "params": {
                "f": "json",
                "where": "1=1",
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": "4326",
                "geometry": "139.1900,35.1900,140.1900,36.1900",
                "geometryType": "esriGeometryEnvelope",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
            },
        },
        {
            "request": "large-attrs-only",
            "params": {
                "f": "json",
                "where": "1=1",
                "outFields": "*",
                "returnGeometry": "false",
                "outSR": "4326",
                "geometry": "139.1900,35.1900,140.1900,36.1900",
                "geometryType": "esriGeometryEnvelope",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
            },
        },
        {
            "request": "large-geom-oid",
            "params": {
                "f": "json",
                "where": "1=1",
                "outFields": "objectid",
                "returnGeometry": "true",
                "outSR": "4326",
                "geometry": "139.1900,35.1900,140.1900,36.1900",
                "geometryType": "esriGeometryEnvelope",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
            },
        },
    ]

    return [
        {
            "family": "feature",
            "protocol": "geoservices-rest",
            "suite": "geoservices-query-diagnostics",
            "request": variant["request"],
            "url": build_geoservices_query_url(base, variant["params"]),
        }
        for variant in variants
    ]


def summarize_entry(entry: dict[str, Any], body: bytes, payload: Any | None) -> dict[str, Any]:
    summary = {
        "family": entry["family"],
        "protocol": entry["protocol"],
        "suite": entry["suite"],
        "request": entry["request"],
        "url": entry["url"],
        "status": entry["status"],
        "content_type": entry["content_type"],
        "bytes": len(body),
        "sha256": sha256_bytes(body),
    }

    if entry["family"] == "feature":
        if entry.get("protocol") == "geoservices-rest":
            summary.update(geoservices_feature_shape(payload))
        else:
            summary.update(feature_shape(payload))
    else:
        summary.update(raster_shape(body))

    return summary


def summarize_error(entry: dict[str, Any], error: str) -> dict[str, Any]:
    return {
        "family": entry["family"],
        "protocol": entry["protocol"],
        "suite": entry["suite"],
        "request": entry["request"],
        "url": entry["url"],
        "status": "error",
        "content_type": "",
        "bytes": 0,
        "sha256": "",
        "summary": f"error={error}",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture lightweight response-shape samples.")
    parser.add_argument("--server", required=True, choices=["honua", "geoserver", "qgis"])
    parser.add_argument("--tests", nargs="*", default=[], help="Selected benchmark tests")
    parser.add_argument("--output", required=True, help="Output JSON file")
    args = parser.parse_args()

    server = server_config(args.server)
    enabled_tests = [test for test in args.tests if test]

    requests: list[dict[str, str]] = []
    if any(test in enabled_tests for test in ("attribute-filter", "spatial-bbox", "concurrent")):
        requests.extend(feature_requests(server))
    if "geoservices-query" in enabled_tests:
        requests.extend(geoservices_feature_requests(server))
    if "geoservices-query-diagnostics" in enabled_tests:
        requests.extend(geoservices_diagnostic_requests(server))
    if "wfs-getfeature" in enabled_tests:
        requests.extend(wfs_requests(server))
    if any(test in enabled_tests for test in ("wms-getmap", "geoservices-export")):
        requests.extend(raster_requests(server, enabled_tests))

    entries = []
    for spec in requests:
        try:
            if spec["family"] == "feature":
                status, content_type, body, payload = http_get_json(spec["url"])
                entry = {
                    **spec,
                    "status": status,
                    "content_type": content_type,
                }
                entries.append(summarize_entry(entry, body, payload))
            else:
                status, content_type, body = http_get(spec["url"])
                entry = {
                    **spec,
                    "status": status,
                    "content_type": content_type,
                }
                entries.append(summarize_entry(entry, body, None))
        except Exception as exc:
            entries.append(summarize_error(spec, type(exc).__name__))

    output = {
        "server": server.name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tests": enabled_tests,
        "entries": entries,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2))
    print(f"Wrote {output_path} with {len(entries)} response-shape samples", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
