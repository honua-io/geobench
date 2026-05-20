# GeoBench

GeoBench is an open, vendor-neutral benchmark suite for geospatial feature and
map servers. It provides reproducible workloads, system cards, response-shape
audits, and run artifacts so teams can compare server behavior under the same
dataset, database topology, and benchmark harness.

Current benchmark capabilities are summarized in [docs/features/README.md](docs/features/README.md).

Think [TechEmpower](https://www.techempower.com/benchmarks/) for GIS:
transparent workloads, disclosed configuration, and repeatable results.

## What GeoBench Measures

GeoBench separates results by protocol family and cache tier. It does not merge
unrelated protocols into a single "fastest server" claim.

| Track | Coverage |
|-------|----------|
| Common feature APIs | OGC API Features reads, attribute filters, bbox filters, and mixed concurrent workloads |
| Common raster APIs | WMS `GetMap`, WMS reprojection, and WMS `GetFeatureInfo` |
| Secondary standards | WFS `GetFeature`, filtered WFS, filtered WMS `GetMap`, WMTS, and experimental WCS |
| Supplemental native protocols | GeoServices REST `FeatureServer/query`, `MapServer/identify`, and `MapServer/export` |

See [METHODOLOGY.md](METHODOLOGY.md) for the full protocol matrix, fairness
rules, cache taxonomy, and reporting requirements.

## Servers In The Harness

| Server | Runtime | Default Image |
|--------|---------|---------------|
| [Honua Server](https://github.com/honua-io/honua-server) | .NET 10 | `honuaio/honua-server:latest` |
| [GeoServer](https://geoserver.org/) | Java / JVM | `docker.osgeo.org/geoserver:2.28.0` |
| [QGIS Server](https://qgis.org/en/site/about/features.html#qgis-server) | C++ / Qt | `qgis/qgis-server:3.38` |

Headline snapshots may pin a digest or use a specific nightly tag. Exact images
are recorded in each result directory's metadata.

## Current Headline Snapshot

The current headline snapshot was generated on April 28, 2026 HST
(April 29, 2026 UTC in the report timestamp) against the 100K-point dataset.
It uses a 5-run median, a baseline profile with no spatial response cache, and
30-second warmup plus 30-second measured windows per scenario.

Both servers used a strict bounded database profile. Honua active-query and
pool settings were `6/6/3`; GeoServer datastore pool settings were `6/3`.
GeoServer was run with the GSR community extension for the GeoServices rows.
QGIS Server remains runnable in the harness, but this headline table focuses on
the current Honua and GeoServer profile.

**At a glance:** Honua led every comparable performance cell in this snapshot.
Across the headline rows below, Honua delivered **2.6x to 470x higher
throughput** and **3.1x to 450x lower tail latency**, depending on the protocol
and scenario. The six comparable error-rate cells were ties at `0.0%`.

| Scenario | Throughput Advantage | Tail-Latency Advantage |
|----------|---------------------:|-----------------------:|
| GeoServices `MapServer/identify`, large bbox | **470x higher req/s** | **450x lower p95** |
| WMS filtered `GetMap`, range | **101x higher req/s** | **113x lower p95** |
| Attribute filter, LIKE | **73x higher req/s** | **185x lower p95** |
| Spatial bbox, large bbox | **55x higher req/s** | **63x lower p95** |
| WFS filtered, LIKE | **20x higher req/s** | **20x lower p95** |
| WMS reprojection, large bbox | **14x higher req/s** | **24x lower p95** |
| Concurrent mixed workload, 100 VUs | **12x higher req/s** | **8.9x lower p99** |
| WFS `GetFeature`, large bbox | **10x higher req/s** | **14x lower p95** |
| WMS `GetFeatureInfo`, medium bbox | **6.9x higher req/s** | **11x lower p95** |
| GeoServices `FeatureServer/query`, medium bbox | **4.1x higher req/s** | **5.2x lower p95** |
| WMS `GetMap`, medium bbox | **2.6x higher req/s** | **3.1x lower p95** |

Raw headline values:

| Track | Scenario | Honua | GeoServer |
|-------|----------|------:|----------:|
| Attribute filter | LIKE | 1632.8 req/s, p95 5.2 ms | 22.3 req/s, p95 959.3 ms |
| Spatial bbox | large bbox | 1069.3 req/s, p95 15.5 ms | 19.5 req/s, p95 977.1 ms |
| Concurrent mixed workload | 100 VUs | 1190.2 req/s, p99 201.4 ms | 96.2 req/s, p99 1793.2 ms |
| WMS `GetMap` | medium bbox | 80.1 req/s, p95 186.4 ms | 30.5 req/s, p95 582.5 ms |
| WMS reprojection | large bbox | 131.9 req/s, p95 99.3 ms | 9.3 req/s, p95 2356.7 ms |
| WFS `GetFeature` | large bbox | 581.5 req/s, p95 29.0 ms | 57.8 req/s, p95 418.5 ms |
| WFS filtered | LIKE | 1094.3 req/s, p95 13.2 ms | 54.6 req/s, p95 269.1 ms |
| WMS `GetFeatureInfo` | medium bbox | 2808.9 req/s, p95 4.9 ms | 407.1 req/s, p95 53.7 ms |
| WMS filtered `GetMap` | range | 171.4 req/s, p95 105.5 ms | 1.7 req/s, p95 11953.6 ms |
| GeoServices `FeatureServer/query` | medium bbox | 937.2 req/s, p95 13.8 ms | 228.9 req/s, p95 71.7 ms |
| GeoServices `MapServer/identify` | large bbox | 2868.9 req/s, p95 6.3 ms | 6.1 req/s, p95 2833.6 ms |
| GeoServices `MapServer/export` | large bbox | 152.2 req/s, p95 108.6 ms | Not available |

In this report, all 204 measured performance cells where both servers had data
favored the Honua row. `MapServer/export` has no GeoServer row in this harness
profile.

Full artifacts are under `results/20260428-192053/`, including the generated
report at `results/20260428-192053/report.md` and the action ledger at
`results/20260428-192053/loss-ledger-final/loss-ledger.md`.
Response-shape audits are included in the report. Some feature and native rows
show payload metadata or property-key drift, so public claims should include
those caveats.

Important reproducibility note: the Honua image used for this exact snapshot,
`honua-geobench:trunk-b650a321-rendergate2`, is a local benchmark build from
Honua source around `b650a321`. It uses raster render-gate defaults of 8
concurrent renders and a 5-second acquire timeout. Publish or pin the matching
Honua Server source/image before treating this exact snapshot as externally
rerunnable.

<details>
<summary>Exact snapshot images and reproduction commands</summary>

The GeoServer image resolved locally to:

```text
docker.osgeo.org/geoserver@sha256:48fcd9488f35c29ef8b8dd2d0b6ae491d1bef73cea83f0ef27f6fa124ddcf245
```

The local image was created on April 20, 2026 and was run with
`GEOSERVER_COMMUNITY_EXTENSIONS=gsr` for the GeoServices rows.

Before publishing a new headline snapshot, run the fairness audit against the
result directory:

```bash
python3 scripts/audit-fairness.py \
  --results-dir results/20260428-192053 \
  --servers honua,geoserver \
  --strict-equal-db-budget
```

To regenerate the headline report from an existing result directory:

```bash
python3 scripts/generate-report.py \
  --results-dir results/20260428-192053 \
  --output results/20260428-192053/report.md \
  --runs 5 \
  --servers honua,geoserver
```

To rerun the same two-server headline profile:

```bash
HONUA_IMAGE=honua-geobench:trunk-b650a321-rendergate2 \
HONUA_MAX_CONCURRENT_QUERIES=6 \
HONUA_MAX_CONNECTION_POOL_SIZE=6 \
HONUA_MIN_CONNECTION_POOL_SIZE=3 \
HONUA_ADAPTIVE_ADMISSION_ENABLED=false \
GEOSERVER_IMAGE=docker.osgeo.org/geoserver@sha256:48fcd9488f35c29ef8b8dd2d0b6ae491d1bef73cea83f0ef27f6fa124ddcf245 \
GEOSERVER_COMMUNITY_EXTENSIONS=gsr \
GEOSERVER_GSR_ENABLED=1 \
GEOSERVER_MAX_CONNECTIONS=6 \
GEOSERVER_MIN_CONNECTIONS=3 \
SERVERS="honua geoserver" \
TESTS="attribute-filter spatial-bbox concurrent wms-getmap wms-reprojection wfs-getfeature wfs-filtered wms-getfeatureinfo wms-filtered geoservices-query geoservices-export geoservices-identify" \
RUNS=5 \
AUDIT_SHAPES=1 \
ATTRIBUTE_FILTER_WARMUP=30s ATTRIBUTE_FILTER_DURATION=30s \
SPATIAL_BBOX_WARMUP=30s SPATIAL_BBOX_DURATION=30s \
CONCURRENT_WARMUP=30s CONCURRENT_DURATION=30s \
WMS_GETMAP_WARMUP=30s WMS_GETMAP_DURATION=30s \
WMS_REPROJECTION_WARMUP=30s WMS_REPROJECTION_DURATION=30s \
WFS_GETFEATURE_WARMUP=30s WFS_GETFEATURE_DURATION=30s \
WFS_FILTERED_WARMUP=30s WFS_FILTERED_DURATION=30s \
WMS_GETFEATUREINFO_WARMUP=30s WMS_GETFEATUREINFO_DURATION=30s \
WMS_FILTERED_WARMUP=30s WMS_FILTERED_DURATION=30s \
GEOSERVICES_QUERY_WARMUP=30s GEOSERVICES_QUERY_DURATION=30s \
GEOSERVICES_EXPORT_WARMUP=30s GEOSERVICES_EXPORT_DURATION=30s \
GEOSERVICES_IDENTIFY_WARMUP=30s GEOSERVICES_IDENTIFY_DURATION=30s \
./scripts/run-benchmark.sh
```

</details>

The current rerun status is tracked in
[docs/matrix-status.md](docs/matrix-status.md).

## Quick Start

Requirements:

- Docker with Docker Compose v2
- Python 3
- `jq`
- `curl`

Generate the deterministic dataset and run the default benchmark suite:

```bash
python3 data/small/generate.py
./scripts/run-benchmark.sh
```

The runner starts one server stack at a time, gives each server its own PostGIS
instance, runs the selected k6 workloads, writes results under
`results/<timestamp>/`, and then tears the stack down before moving to the next
server. The default suite runs `attribute-filter`, `spatial-bbox`, and
`concurrent` for Honua, GeoServer, and QGIS.

For a quick local validation run:

```bash
RUNS=1 \
SERVERS="honua geoserver" \
TESTS="attribute-filter" \
ATTRIBUTE_FILTER_WARMUP=5s \
ATTRIBUTE_FILTER_DURATION=10s \
./scripts/run-benchmark.sh
```

Each run writes raw k6 JSON, copied system cards, benchmark metadata,
response-shape audits, and a generated report.

## Running Specific Tracks

Select benchmark families with `TESTS` and server targets with `SERVERS`:

```bash
# Common raster track
TESTS="wms-getmap" SERVERS="honua geoserver qgis" ./scripts/run-benchmark.sh

# Common raster reprojection track
TESTS="wms-reprojection" SERVERS="honua geoserver qgis" ./scripts/run-benchmark.sh

# Secondary standards track
TESTS="wfs-getfeature wfs-filtered" SERVERS="honua geoserver" ./scripts/run-benchmark.sh

# Supplemental GeoServices REST track
GEOSERVER_IMAGE=docker.osgeo.org/geoserver:2.28.x \
GEOSERVER_COMMUNITY_EXTENSIONS=gsr \
GEOSERVER_GSR_ENABLED=1 \
TESTS="geoservices-query geoservices-identify" \
SERVERS="honua geoserver" \
./scripts/run-benchmark.sh

# GeoServices MapServer/export for servers that expose it
TESTS="geoservices-export" SERVERS="honua" ./scripts/run-benchmark.sh

# WMTS tile suite, published only as an explicit warm-tile-cache row
WMTS_CACHE_POLICY=warm TESTS="wmts" SERVERS="geoserver" ./scripts/run-benchmark.sh

# WCS GetCoverage, experimental and server-specific
GEOSERVER_WCS_COVERAGE="geobench:points" TESTS="wcs" SERVERS="geoserver" ./scripts/run-benchmark.sh
```

For targeted investigation, enable diagnostics:

```bash
DIAGNOSTICS=1 \
TESTS="wms-reprojection" \
SERVERS="honua geoserver" \
WMS_REPROJECTION_SCENARIOS=medium \
WMS_REPROJECTION_WARMUP=10s \
WMS_REPROJECTION_DURATION=30s \
./scripts/run-benchmark.sh
```

Diagnostics mode enables PostGIS statement-duration logging and writes
per-server artifacts under `results/<timestamp>/diagnostics/`, including output
shape samples, server logs, PostGIS logs, extracted SQL statement logs, runtime
monitor samples, and `diagnostics/comparison.json`.

## Test Categories

| Category | Description | Default VUs | Default Measurement Window |
|----------|-------------|------------:|---------------------------:|
| `attribute-filter` | Equality, range, and literal-prefix LIKE queries via CQL2 | 10 | 120s each |
| `spatial-bbox` | Small, medium, and large viewport bounding-box queries | 10 | 120s each |
| `concurrent` | Mixed workload at 1, 10, 50, and 100 VUs | 1-100 | 120s each |
| `wms-getmap` | WMS raster rendering on the common standards track | 10 | 120s each |
| `wms-reprojection` | WMS `GetMap` with deterministic `EPSG:3857` reprojection from `EPSG:4326` source data | 10 | 120s each |
| `wms-getfeatureinfo` | WMS `GetFeatureInfo` on deterministic `CRS:84` hotspots | 10 | 120s each |
| `wms-filtered` | WMS `GetMap` with OGC `FILTER` queries | 10 | 120s each |
| `wmts` | WMTS `GetTile` tile-matrix requests | 10 | 120s each |
| `wcs` | WCS `GetCoverage` coverage reads | 10 | 120s each |
| `wfs-getfeature` | WFS base reads and bbox reads on the standards track | 10 | 120s each |
| `wfs-filtered` | WFS equality, range, and prefix filtering on the shared FES 2.0 profile | 10 | 120s each |
| `geoservices-query` | GeoServices REST `FeatureServer/query` spatial bbox track | 10 | 120s each |
| `geoservices-query-diagnostics` | Native query diagnostics for concurrency and payload-shape isolates | mixed | 15s warmup + 20s each |
| `geoservices-export` | GeoServices REST `MapServer/export` where available | 10 | 120s each |
| `geoservices-identify` | GeoServices REST `MapServer/identify` on deterministic points | 10 | 120s each |

The runner captures a lightweight response-shape audit before each timed server
run. The audit records status, `Content-Type`, byte count, body hash, and
structural notes for JSON and image responses. It is intended for publishing and
regression checks, not as a performance metric.

## Dataset

The default dataset is 100,000 deterministic point features with 10 attribute
fields.

- Generated with `seed=42`
- 60% spatially clustered around NYC, Paris, Tokyo, Sao Paulo, and Sydney
- 40% globally distributed
- Attributes include category, status, priority, temperature, population,
  timestamps, country code, and description
- PostGIS GiST spatial index plus btree indexes on filterable columns

Generate the dataset with:

```bash
python3 data/small/generate.py
```

## Methodology Summary

GeoBench is built around isolation and disclosure:

- Each server runs against its own dedicated PostGIS instance initialized from
  the same deterministic dataset.
- The orchestrator starts one server at a time, runs the selected benchmarks,
  and tears the stack down before starting the next server.
- Server containers, PostGIS, and k6 each use 4 CPU cores and 4 GB memory.
- Published rows disclose warmup duration, measurement duration, Docker images,
  system cards, cache tier, and database admission or pool settings.
- The default reported value is the median across 5 independent runs.

Cache behavior is treated as a benchmark dimension. Baseline feature, WFS,
GeoServices query, and primary WMS rows do not use exact response caching.
WMTS belongs in a separate warm-tile-cache row, and Redis, GeoWebCache,
MinIO/object-store-backed caches, or CDN-like layers belong in explicitly named
cache-assisted tracks.

Database admission is also part of the benchmark profile. The default posture is
bounded fixed admission so tail-latency wins are not hidden behind larger
connection pools or adaptive controllers. Adaptive-admission results should be
published as separate named profiles with their settings and telemetry.

## Optional GeoServer GSR

GeoServer's GeoServices REST support is not part of the stock image. To
benchmark `FeatureServer/query` or `MapServer/identify`, run GeoServer with the
`gsr` community extension on a matching nightly build tag such as
`docker.osgeo.org/geoserver:2.28.x`, then set `GEOSERVER_GSR_ENABLED=1`.

If GSR endpoint verification fails, treat the GeoServer GSR row as unavailable
for the current image and exclude older optional-extension reports from current
comparisons.

## Project Layout

```text
geobench/
|-- adapters/          # Per-server setup scripts
|-- data/small/        # Deterministic dataset generator
|-- docs/              # Investigation notes, status, and issue drafts
|-- results/           # Local benchmark output
|-- scripts/           # Orchestration, reporting, diagnostics, and audits
|-- src/tests/         # k6 benchmark scripts
|-- system-cards/      # Server configuration metadata
|-- tests/             # Smoke and validation helpers
|-- docker-compose.yml
|-- METHODOLOGY.md
`-- README.md
```

## Contributing

Adding a new server requires:

1. A Docker image that exposes the target geospatial API surface.
2. An adapter script at `adapters/<server>/setup.sh`.
3. A server entry in `src/tests/helpers.js`.
4. A system card at `system-cards/<server>.json`.

See the existing adapters and system cards for examples. Pull requests are
welcome.

## License

Apache 2.0. See [LICENSE](LICENSE).
