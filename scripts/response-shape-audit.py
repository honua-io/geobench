#!/usr/bin/env python3
"""Capture lightweight response-shape samples alongside GeoBench runs.

This is intentionally small and publication-safe. It records only headers,
sizes, hashes, and compact structural notes, never the raw body content.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
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


def lonlat_to_web_mercator(lon: float, lat: float) -> tuple[float, float]:
    origin_shift = 20037508.342789244
    clamped_lat = max(min(lat, 85.05112878), -85.05112878)
    x = lon * origin_shift / 180.0
    y = math.log(math.tan((90.0 + clamped_lat) * math.pi / 360.0)) / (math.pi / 180.0)
    y = y * origin_shift / 180.0
    return x, y


def reproject_bbox_4326_to_3857(bbox: str) -> str:
    min_lon, min_lat, max_lon, max_lat = map(float, bbox.split(","))
    min_x, min_y = lonlat_to_web_mercator(min_lon, min_lat)
    max_x, max_y = lonlat_to_web_mercator(max_lon, max_lat)
    return f"{min_x:.3f},{min_y:.3f},{max_x:.3f},{max_y:.3f}"


def first_point_from_geometry(geometry: Any) -> tuple[float, float] | None:
    if not isinstance(geometry, dict):
        return None
    if geometry.get("type") != "Point":
        return None
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        return None
    try:
        return float(coordinates[0]), float(coordinates[1])
    except (TypeError, ValueError):
        return None


def collection_items_url(server: ServerConfig, collection: str) -> str | None:
    collection_id = urllib.parse.quote(collection, safe=":")
    if server.name == "honua":
        return f"{server.base_url}/ogc/features/collections/{collection_id}/items?limit=1"
    if server.name == "geoserver":
        return f"{server.base_url}/geoserver/ogc/features/v1/collections/{collection_id}/items?limit=1"
    return None


def discover_collection_point(server: ServerConfig, collection: str) -> tuple[float, float] | None:
    url = collection_items_url(server, collection)
    if not url:
        return None
    status, _content_type, _body, payload = http_get_json(url)
    if status != 200 or not isinstance(payload, dict):
        return None
    features = payload.get("features")
    if not isinstance(features, list):
        return None
    for feature in features:
        if not isinstance(feature, dict):
            continue
        point = first_point_from_geometry(feature.get("geometry"))
        if point is not None:
            return point
    return None


def bbox_around_point(lon: float, lat: float, delta: float = 0.02) -> str:
    return f"{lon - delta:.6f},{lat - delta:.6f},{lon + delta:.6f},{lat + delta:.6f}"


def top_level_keys(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        return sorted(payload.keys())
    return []


def value_kind(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def metadata_flags(payload: Any, keys: list[str]) -> dict[str, bool]:
    if not isinstance(payload, dict):
        return {}
    return {key: key in payload for key in keys}


def first_value_type_map(values: dict[str, Any]) -> dict[str, str]:
    return {key: value_kind(values[key]) for key in sorted(values.keys())}


def normalized_feature_id(feature: dict[str, Any]) -> str | None:
    feature_id = feature.get("id")
    if feature_id is None:
        properties = feature.get("properties")
        if isinstance(properties, dict):
            feature_id = properties.get("id")
    if feature_id is None:
        return None
    return str(feature_id)


def normalized_geoservices_id(feature: dict[str, Any]) -> str | None:
    attributes = feature.get("attributes")
    if not isinstance(attributes, dict):
        attributes = {}
    feature_id = (
        attributes.get("OBJECTID")
        or attributes.get("objectid")
        or attributes.get("id")
    )
    if feature_id is None:
        return None
    return str(feature_id)


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

    flags = metadata_flags(
        payload,
        ["links", "numberMatched", "numberReturned", "timeStamp", "bbox", "crs", "type"],
    )
    feature_ids = [identifier for identifier in (normalized_feature_id(feature) for feature in features[:5]) if identifier]

    return {
        "top_level_keys": top_level_keys(payload),
        "feature_count": len(features),
        "first_feature_property_keys": sorted(properties.keys()),
        "first_feature_property_types": first_value_type_map(properties),
        "first_feature_geometry_type": geometry.get("type"),
        "first_feature_id_kind": feature_id_kind,
        "feature_id_sample": feature_ids,
        "metadata_flags": flags,
        "summary": summary,
    }


def geoservices_feature_shape(payload: Any) -> dict[str, Any]:
    features = []
    if isinstance(payload, dict):
        raw_features = payload.get("features")
        if not raw_features:
            raw_features = payload.get("results")
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

    flags = metadata_flags(
        payload,
        ["fields", "objectIdFieldName", "geometryType", "spatialReference", "exceededTransferLimit", "results", "features", "layers"],
    )
    feature_ids = [identifier for identifier in (normalized_geoservices_id(feature) for feature in features[:5]) if identifier]

    return {
        "top_level_keys": top_level_keys(payload),
        "feature_count": len(features),
        "first_feature_property_keys": sorted(attributes.keys()),
        "first_feature_property_types": first_value_type_map(attributes),
        "first_feature_geometry_type": geometry_type,
        "first_feature_id_kind": feature_id_kind,
        "feature_id_sample": feature_ids,
        "metadata_flags": flags,
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


def wfs_filtered_requests(server: ServerConfig) -> list[dict[str, str]]:
    filter_param = (
        "%3Cfes%3AFilter%20xmlns%3Afes%3D%22http%3A%2F%2Fwww.opengis.net%2Ffes%2F2.0%22%3E"
        "%3Cfes%3APropertyIsEqualTo%3E"
        "%3Cfes%3AValueReference%3Ecategory%3C%2Ffes%3AValueReference%3E"
        "%3Cfes%3ALiteral%3Epark%3C%2Ffes%3ALiteral%3E"
        "%3C%2Ffes%3APropertyIsEqualTo%3E"
        "%3C%2Ffes%3AFilter%3E"
    )
    if server.name == "honua":
        base = f"{server.base_url}/wfs"
        return [
            {
                "family": "feature",
                "protocol": "wfs",
                "suite": "wfs-filtered",
                "request": "equality",
                "url": base + "?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=bench_points&COUNT=100&OUTPUTFORMAT=application/json&FILTER=" + filter_param,
            },
        ]
    if server.name == "geoserver":
        base = f"{server.base_url}/geoserver/wfs"
        return [
            {
                "family": "feature",
                "protocol": "wfs",
                "suite": "wfs-filtered",
                "request": "equality",
                "url": base + "?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=geobench:bench_points&COUNT=100&OUTPUTFORMAT=application/json&FILTER=" + filter_param,
            },
        ]
    return []


def wms_getfeatureinfo_requests(server: ServerConfig) -> list[dict[str, str]]:
    sample_bbox_4326 = "139.2325,35.2325,139.3325,35.3325"
    if server.name == "honua":
        return [
            {
                "family": "feature",
                "protocol": "wms",
                "suite": "wms-getfeatureinfo",
                "request": "small",
                "url": (
                    f"{server.base_url}/ogc/services/default/wms?"
                    f"SERVICE=WMS&VERSION=1.3.0&REQUEST=GetFeatureInfo&LAYERS=bench_points&STYLES=&"
                    f"QUERY_LAYERS=bench_points&CRS=CRS:84&BBOX={sample_bbox_4326}&WIDTH={DEFAULT_IMAGE_SIZE}&HEIGHT={DEFAULT_IMAGE_SIZE}"
                    f"&INFO_FORMAT=application/json&I=128&J=128&FEATURE_COUNT=10"
                ),
            }
        ]
    if server.name == "geoserver":
        return [
            {
                "family": "feature",
                "protocol": "wms",
                "suite": "wms-getfeatureinfo",
                "request": "small",
                "url": (
                    f"{server.base_url}/geoserver/wms?"
                    f"SERVICE=WMS&VERSION=1.3.0&REQUEST=GetFeatureInfo&LAYERS=geobench:bench_points&STYLES=&"
                    f"QUERY_LAYERS=geobench:bench_points&CRS=CRS:84&BBOX={sample_bbox_4326}&WIDTH={DEFAULT_IMAGE_SIZE}&HEIGHT={DEFAULT_IMAGE_SIZE}"
                    f"&INFO_FORMAT=application/json&I=128&J=128&FEATURE_COUNT=10"
                ),
            }
        ]
    if server.name == "qgis":
        map_path = urllib.parse.quote(env("QGIS_MAP_PATH", "/etc/qgisserver/geobench.qgs"))
        return [
            {
                "family": "feature",
                "protocol": "wms",
                "suite": "wms-getfeatureinfo",
                "request": "small",
                "url": (
                    f"{server.base_url}/ows/?MAP={map_path}&"
                    f"SERVICE=WMS&VERSION=1.3.0&REQUEST=GetFeatureInfo&LAYERS=bench_points&STYLES=&"
                    f"QUERY_LAYERS=bench_points&CRS=CRS:84&BBOX={sample_bbox_4326}&WIDTH={DEFAULT_IMAGE_SIZE}&HEIGHT={DEFAULT_IMAGE_SIZE}"
                    f"&INFO_FORMAT=application/json&I=128&J=128&FEATURE_COUNT=10"
                ),
            }
        ]
    return []




def wms_filtered_requests(server: ServerConfig) -> list[dict[str, str]]:
    fixtures = [
        {
            "request": "equality",
            "bbox_4326": "146.5040,-38.5760,151.5040,-33.5760",
            "xml": (
                "<Filter xmlns=\"http://www.opengis.net/ogc\">"
                "<PropertyIsEqualTo>"
                "<PropertyName>category</PropertyName>"
                "<Literal>park</Literal>"
                "</PropertyIsEqualTo>"
                "</Filter>"
            ),
        },
        {
            "request": "range",
            "bbox_4326": "-47.8625,-24.7825,-42.8625,-19.7825",
            "xml": (
                "<Filter xmlns=\"http://www.opengis.net/ogc\">"
                "<PropertyIsBetween>"
                "<PropertyName>temperature</PropertyName>"
                "<LowerBoundary><Literal>24.968923912383616</Literal></LowerBoundary>"
                "<UpperBoundary><Literal>34.968923912383616</Literal></UpperBoundary>"
                "</PropertyIsBetween>"
                "</Filter>"
            ),
        },
        {
            "request": "like",
            "bbox_4326": "139.6637,35.6637,144.6637,40.6637",
            "xml": (
                "<Filter xmlns=\"http://www.opengis.net/ogc\">"
                "<PropertyIsLike wildCard=\"%\" singleChar=\"_\" escapeChar=\"\\\\\">"
                "<PropertyName>feature_name</PropertyName>"
                "<Literal>feature_548%</Literal>"
                "</PropertyIsLike>"
                "</Filter>"
            ),
        },
    ]

    if server.name == "honua":
        base = f"{server.base_url}/ogc/services/default/wms"
        layer = "bench_points"
    elif server.name == "geoserver":
        base = f"{server.base_url}/geoserver/wms"
        layer = "geobench:bench_points"
    else:
        return []

    return [
        {
            "family": "raster",
            "protocol": "wms",
            "suite": "wms-filtered",
            "request": fixture["request"],
            "url": (
                f"{base}?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS={layer}&STYLES=&CRS=CRS:84"
                f"&BBOX={fixture['bbox_4326']}&WIDTH={DEFAULT_IMAGE_SIZE}&HEIGHT={DEFAULT_IMAGE_SIZE}"
                "&FORMAT=image/png&TRANSPARENT=true"
                f"&FILTER={urllib.parse.quote(fixture['xml'])}"
            ),
        }
        for fixture in fixtures
    ]
def wmts_requests(server: ServerConfig) -> list[dict[str, str]]:
    if server.name != "geoserver":
        return []

    base = f"{server.base_url}/geoserver/gwc/service/wmts"
    return [
        {
            "family": "raster",
            "protocol": "wmts",
            "suite": "wmts",
            "request": "z0",
            "url": (
                f"{base}?SERVICE=WMTS&VERSION=1.0.0&REQUEST=GetTile&LAYER=geobench:bench_points"
                f"&STYLE=&TILEMATRIXSET=EPSG:900913&TILEMATRIX=EPSG:900913:0&TILECOL=0&TILEROW=0&FORMAT=image/png"
            ),
        },
    ]


def wcs_requests(server: ServerConfig) -> list[dict[str, str]]:
    if server.name != "geoserver":
        return []

    coverage = env("GEOSERVER_WCS_COVERAGE", env("WCS_COVERAGE", "geobench:bench_raster"))

    sample_bbox_4326 = "139.2325,35.2325,139.3325,35.3325"
    base = f"{server.base_url}/geoserver/wcs"
    return [
        {
            "family": "raster",
            "protocol": "wcs",
            "suite": "wcs",
            "request": "small",
            "url": (
                f"{base}?SERVICE=WCS&VERSION=1.0.0&REQUEST=GetCoverage&COVERAGE={urllib.parse.quote(coverage)}"
                f"&CRS=EPSG:4326&BBOX={sample_bbox_4326}&WIDTH=256&HEIGHT=256&FORMAT=GeoTIFF"
            ),
        },
    ]




def geoservices_identify_requests(server: ServerConfig) -> list[dict[str, str]]:
    if server.name == "honua":
        service = env("HONUA_GSR_SERVICE_ID", env("HONUA_SERVICE_NAME", "default"))
        layer = env("HONUA_GSR_LAYER_ID", env("HONUA_COLLECTION_ID", "1"))
        collection = env("HONUA_COLLECTION_ID", "1")
        base = f"{server.base_url}/rest/services/{service}/MapServer/identify"
    elif server.name == "geoserver":
        if env("GEOSERVER_GSR_ENABLED", "0") != "1":
            return []
        service = env("GEOSERVER_GSR_SERVICE", "geobench")
        layer = env("GEOSERVER_GSR_LAYER_ID", "0")
        collection = "geobench:bench_points"
        base = f"{server.base_url}/geoserver/gsr/services/{service}/MapServer/identify"
    else:
        return []

    lon, lat = discover_collection_point(server, collection) or (139.2825, 35.2825)
    geometry = f"{lon:.6f},{lat:.6f}"
    sample_bbox_4326 = bbox_around_point(lon, lat)
    return [
        {
            "family": "feature",
            "protocol": "geoservices-rest",
            "suite": "geoservices-identify",
            "request": "small",
            "url": (
                f"{base}?f=json&geometry={urllib.parse.quote(geometry)}&geometryType=esriGeometryPoint&sr=4326"
                f"&mapExtent={urllib.parse.quote(sample_bbox_4326)}&imageDisplay={DEFAULT_IMAGE_SIZE}"
                f"%2C{DEFAULT_IMAGE_SIZE}%2C96&tolerance=2&returnGeometry=true&layers=all%3A{urllib.parse.quote(layer)}"
            ),
        },
    ]
def raster_requests(server: ServerConfig, enabled_tests: list[str]) -> list[dict[str, str]]:
    requests: list[dict[str, str]] = []
    sample_bbox_4326 = "139.2325,35.2325,139.3325,35.3325"
    sample_bbox_3857 = reproject_bbox_4326_to_3857(sample_bbox_4326)
    if server.name == "honua":
        if "wms-getmap" in enabled_tests:
            requests.append(
                {
                    "family": "raster",
                    "protocol": "wms",
                    "suite": "wms-getmap",
                    "request": "small",
                    "url": f"{server.base_url}/ogc/services/default/wms?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=bench_points&STYLES=&CRS=CRS:84&BBOX={sample_bbox_4326}&WIDTH={DEFAULT_IMAGE_SIZE}&HEIGHT={DEFAULT_IMAGE_SIZE}&FORMAT=image/png&TRANSPARENT=true",
                }
            )
        if "wms-reprojection" in enabled_tests:
            requests.append(
                {
                    "family": "raster",
                    "protocol": "wms",
                    "suite": "wms-reprojection",
                    "request": "small-3857",
                    "url": f"{server.base_url}/ogc/services/default/wms?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=bench_points&STYLES=&CRS=EPSG:3857&BBOX={sample_bbox_3857}&WIDTH={DEFAULT_IMAGE_SIZE}&HEIGHT={DEFAULT_IMAGE_SIZE}&FORMAT=image/png&TRANSPARENT=true",
                }
            )
        if "geoservices-export" in enabled_tests:
            requests.append(
                {
                    "family": "raster",
                    "protocol": "geoservices-rest",
                    "suite": "geoservices-export",
                    "request": "small",
                    "url": f"{server.base_url}/rest/services/default/MapServer/export?bbox={sample_bbox_4326}&bboxSR=4326&imageSR=4326&size={DEFAULT_IMAGE_SIZE},{DEFAULT_IMAGE_SIZE}&format=png&transparent=true&f=image",
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
                    "url": f"{server.base_url}/geoserver/wms?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=geobench:bench_points&STYLES=&CRS=CRS:84&BBOX={sample_bbox_4326}&WIDTH={DEFAULT_IMAGE_SIZE}&HEIGHT={DEFAULT_IMAGE_SIZE}&FORMAT=image/png&TRANSPARENT=true",
                }
            )
        if "wms-reprojection" in enabled_tests:
            requests.append(
                {
                    "family": "raster",
                    "protocol": "wms",
                    "suite": "wms-reprojection",
                    "request": "small-3857",
                    "url": f"{server.base_url}/geoserver/wms?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=geobench:bench_points&STYLES=&CRS=EPSG:3857&BBOX={sample_bbox_3857}&WIDTH={DEFAULT_IMAGE_SIZE}&HEIGHT={DEFAULT_IMAGE_SIZE}&FORMAT=image/png&TRANSPARENT=true",
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
                    "url": f"{server.base_url}/ows/?MAP={map_path}&SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=bench_points&STYLES=&CRS=CRS:84&BBOX={sample_bbox_4326}&WIDTH={DEFAULT_IMAGE_SIZE}&HEIGHT={DEFAULT_IMAGE_SIZE}&FORMAT=image/png&TRANSPARENT=true",
                }
            )
        if "wms-reprojection" in enabled_tests:
            requests.append(
                {
                    "family": "raster",
                    "protocol": "wms",
                    "suite": "wms-reprojection",
                    "request": "small-3857",
                    "url": f"{server.base_url}/ows/?MAP={map_path}&SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=bench_points&STYLES=&CRS=EPSG:3857&BBOX={sample_bbox_3857}&WIDTH={DEFAULT_IMAGE_SIZE}&HEIGHT={DEFAULT_IMAGE_SIZE}&FORMAT=image/png&TRANSPARENT=true",
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
    if "wfs-filtered" in enabled_tests:
        requests.extend(wfs_filtered_requests(server))
    if any(test in enabled_tests for test in ("wms-getmap", "wms-reprojection", "geoservices-export")):
        requests.extend(raster_requests(server, enabled_tests))
    if "wms-getfeatureinfo" in enabled_tests:
        requests.extend(wms_getfeatureinfo_requests(server))
    if "wms-filtered" in enabled_tests:
        requests.extend(wms_filtered_requests(server))
    if "wmts" in enabled_tests:
        requests.extend(wmts_requests(server))
    if "wcs" in enabled_tests:
        requests.extend(wcs_requests(server))
    if "geoservices-identify" in enabled_tests:
        requests.extend(geoservices_identify_requests(server))

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
