"""Versioned feature contract and PostGIS oracle. No oracle calls during load."""
import hashlib
import json
import re
from urllib.parse import urlencode

MODES = {
    "diagnostic": {"repetitions": 3, "warmup": 30, "measurement": 30},
    "comparison": {"repetitions": 5, "warmup": 180, "measurement": 120},
}
ARRIVAL_RATES = (10, 30, 60, 120, 240)
CONCURRENCY = (1, 10, 50, 100)
DRAIN_SECONDS = 35
BUDGET = {"cpus": 4, "memory_bytes": 4 * 1024**3, "source_connections": 6}
HONUA_PROFILES = {
    "baseline": {},
    "count-jit-off": {"Database__DisableJitForSourceSpatialCounts": "true"},
    "serial-reads": {"Database__PreferSerialBoundedSpatialReads": "true"},
    "count-jit-off-serial-reads": {
        "Database__DisableJitForSourceSpatialCounts": "true",
        "Database__PreferSerialBoundedSpatialReads": "true",
    },
}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def immutable_image(image):
    return bool(re.fullmatch(r"(?:[^\s]+@)?sha256:[0-9a-f]{64}", image))


def oracle(corpus, sql):
    """sql executes against the isolated source database and returns JSON."""
    requests = []
    for original in corpus["requests"]:
        request = dict(original)
        if "boundary_id" in request:
            x, y = sql(f"SELECT json_build_array(ST_X(geom),ST_Y(geom)) FROM public.bench_points WHERE id={int(request['boundary_id'])}")
            request["bbox"] = [x, y, x + 0.000001, y + 0.000001]
        where = request.get("filter", "TRUE")
        if "bbox" in request:
            coords = ",".join(str(float(v)) for v in request["bbox"])
            where += f" AND ST_Intersects(geom,ST_MakeEnvelope({coords},4326))"
        fields = ",".join(corpus["fields"])
        # Corpus is repository-owned SQL, never user-supplied request text.
        query = f"""WITH selected AS (
          SELECT id,{fields},ST_AsGeoJSON(geom,9)::jsonb AS geometry
          FROM public.bench_points WHERE {where} ORDER BY id
          LIMIT {int(corpus['limit'])} OFFSET {int(request.get('offset', 0))}
        ) SELECT json_build_object('features',COALESCE(jsonb_agg(to_jsonb(selected) ORDER BY id),'[]'::jsonb),
          'matched',(SELECT count(*) FROM public.bench_points WHERE {where})) FROM selected"""
        request["expected"] = sql(query)
        requests.append(request)
    return {**corpus, "requests": requests}


def request_url(server, protocol, request, base, limit=100):
    if protocol == "ogc":
        path = ("/ogc/features/collections/1/items" if server == "honua" else
                "/geoserver/ogc/features/v1/collections/geobench:bench_points/items")
        params = {"f": "json", "limit": limit, "sortby": "id",
                  "offset" if server == "honua" else "startIndex": request.get("offset", 0)}
        if request.get("filter"):
            params.update({"filter": request["filter"], "filter-lang": "cql2-text"})
        if "bbox" in request:
            params["bbox"] = ",".join(map(str, request["bbox"]))
    elif protocol == "gsr":
        path = ("/rest/services/default/FeatureServer/1/query" if server == "honua" else
                "/geoserver/gsr/services/geobench/FeatureServer/0/query")
        params = {"f": "json", "where": request.get("filter", "1=1"), "outFields": "*",
                  "returnGeometry": "true", "outSR": 4326, "orderByFields": "id ASC",
                  "resultRecordCount": limit, "resultOffset": request.get("offset", 0)}
        if "bbox" in request:
            params.update({"geometry": ",".join(map(str, request["bbox"])), "inSR": 4326,
                           "geometryType": "esriGeometryEnvelope", "spatialRel": "esriSpatialRelIntersects"})
    else:
        raise ValueError(f"Unknown protocol: {protocol}")
    return base + path + "?" + urlencode(params)


def validate_plugin_jars(jars, gsr=False):
    """Require extension and core JARs from the same release/build version."""
    versions = {}
    for line in jars:
        match = re.search(r"/(gs-(?:main|ogcapi-features|gsr))-(.+)\.jar$", line)
        if match:
            if match[1] in versions:
                raise ValueError(f"Duplicate GeoServer core/plugin JAR: {match[1]}")
            versions[match[1]] = match[2]
    required = {"gs-main", "gs-ogcapi-features"} | ({"gs-gsr"} if gsr else set())
    if not required <= versions.keys() or len({versions[k] for k in required}) != 1:
        raise ValueError(f"Missing or incompatible GeoServer plugins: {versions}")
    if not gsr and any(term in versions["gs-main"].lower() for term in ("snapshot", "rc", "-m")):
        raise ValueError("Primary OGC profile requires a stable GeoServer release")
    return versions
