# GeoBench

Open, vendor-neutral benchmark suite for geospatial feature servers. Think [TechEmpower](https://www.techempower.com/benchmarks/) for GIS.

## Why

There's no standardized way to compare geospatial feature server performance. Vendor benchmarks are self-serving. GeoBench provides reproducible, independently verifiable numbers that anyone can run.

## Servers Tested

| Server | Runtime | Image |
|--------|---------|-------|
| [Honua Server](https://github.com/honua-io/honua-server) | .NET 10 | `honuaio/honua-server:latest` |
| [GeoServer](https://geoserver.org/) | Java / JVM | `kartoza/geoserver:2.26.1` |
| [QGIS Server](https://qgis.org/en/site/about/features.html#qgis-server) | C++ / Qt | `qgis/qgis-server:3.38` |

GeoBench now supports separate tracks for **common feature APIs**, **common raster APIs**,
**secondary standards** such as WFS, and **supplemental native protocols** such as GeoServices
REST. See [METHODOLOGY.md](METHODOLOGY.md) for the matrix and reporting rules.

## Current Snapshot

Current authoritative reruns on the 100K-point dataset as of March 30, 2026 show Honua ahead of
GeoServer on throughput across the tracked comparative suites in the current full-suite snapshot.
Every comparative `req/s` row in the current authoritative report is won by Honua.

| Suite | Scenario | Honua | GeoServer | QGIS | Winner |
|---|---|---|---|---|---|
| Concurrent mixed workload | 1 VU | **43.8 req/s** | 9.1 req/s | 0.6 req/s | **Honua** |
| Concurrent mixed workload | 10 VUs | **191.9 req/s** | 34.9 req/s | 0.6 req/s | **Honua** |
| Concurrent mixed workload | 50 VUs | **203.8 req/s** | 45.2 req/s | 0.7 req/s | **Honua** |
| Concurrent mixed workload | 100 VUs | **191.3 req/s** | 41.0 req/s | 0.7 req/s | **Honua** |
| WMS reprojection | small bbox | **1020.4 req/s** | 23.6 req/s | 0.8 req/s | **Honua** |
| WMS reprojection | medium bbox | **27.8 req/s** | 9.1 req/s | 0.8 req/s | **Honua** |
| WMS reprojection | large bbox | **29.2 req/s** | 6.3 req/s | 0.8 req/s | **Honua** |
| GeoServices `FeatureServer/query` | small bbox | **489.5 req/s** | 107.3 req/s | — | **Honua** |
| GeoServices `FeatureServer/query` | medium bbox | **212.4 req/s** | 134.9 req/s | — | **Honua** |
| GeoServices `FeatureServer/query` | large bbox | **74.0 req/s** | 28.1 req/s | — | **Honua** |

The current authoritative rerun status is tracked in [docs/matrix-status.md](docs/matrix-status.md).

## Quick Start

**Requirements**: Docker, Docker Compose v2, Python 3, jq, curl

```bash
# 1. Generate the test dataset (100K points)
python3 data/small/generate.py

# 2. Start all services
docker compose up -d

# 3. Run the full benchmark suite
./scripts/run-benchmark.sh
```

Results are written to `results/<timestamp>/report.md`.
Each run also writes `*-response-shapes.json` audit files for the selected servers. The generated
report includes a compact response-shape section with status, `Content-Type`, byte count, a body
hash, and structural notes.

Protocol-specific runs can be selected explicitly:

```bash
# Common raster track
TESTS="wms-getmap" SERVERS="geoserver qgis" ./scripts/run-benchmark.sh

# Common raster reprojection track
TESTS="wms-reprojection" SERVERS="honua geoserver qgis" ./scripts/run-benchmark.sh

# Secondary standards track
TESTS="wfs-getfeature" ./scripts/run-benchmark.sh

# Supplemental native track
GEOSERVER_IMAGE=docker.osgeo.org/geoserver:2.28.x \
GEOSERVER_COMMUNITY_EXTENSIONS=gsr \
GEOSERVER_GSR_ENABLED=1 \
TESTS="geoservices-query" SERVERS="honua geoserver" ./scripts/run-benchmark.sh

# Long-burn subset of the main native track with the stock bbox salts
GEOSERVER_IMAGE=docker.osgeo.org/geoserver:2.28.x \
GEOSERVER_COMMUNITY_EXTENSIONS=gsr \
GEOSERVER_GSR_ENABLED=1 \
GEOSERVICES_QUERY_WARMUP=60s \
GEOSERVICES_QUERY_DURATION=120s \
GEOSERVICES_QUERY_SCENARIOS=medium,large \
TESTS="geoservices-query" SERVERS="honua geoserver" ./scripts/run-benchmark.sh

# Large-only seed sweep
GEOSERVER_IMAGE=docker.osgeo.org/geoserver:2.28.x \
GEOSERVER_COMMUNITY_EXTENSIONS=gsr \
GEOSERVER_GSR_ENABLED=1 \
GEOSERVICES_QUERY_WARMUP=60s \
GEOSERVICES_QUERY_DURATION=120s \
GEOSERVICES_QUERY_SCENARIOS=large \
GEOSERVICES_QUERY_SALT_LARGE=0xB02 \
TESTS="geoservices-query" SERVERS="honua geoserver" ./scripts/run-benchmark.sh

# Summarize multiple large-only runs into one sweep report
python3 scripts/run-geoservices-query-sweep.py \
  --scenario large \
  --results-dir results/20260328-183500 \
  --results-dir results/20260328-184250

# Supplemental native diagnostics for optimization work
GEOSERVER_IMAGE=docker.osgeo.org/geoserver:2.28.x \
GEOSERVER_COMMUNITY_EXTENSIONS=gsr \
GEOSERVER_GSR_ENABLED=1 \
TESTS="geoservices-query-diagnostics" SERVERS="honua geoserver" ./scripts/run-benchmark.sh

# Long-burn diagnostic subset
GEOSERVER_IMAGE=docker.osgeo.org/geoserver:2.28.x \
GEOSERVER_COMMUNITY_EXTENSIONS=gsr \
GEOSERVER_GSR_ENABLED=1 \
GEOSERVICES_DIAG_WARMUP=60s \
GEOSERVICES_DIAG_DURATION=120s \
GEOSERVICES_DIAG_VARIANTS="medium-full-10vu,medium-geom-oid-10vu,large-full-10vu,large-geom-oid-10vu" \
TESTS="geoservices-query-diagnostics" SERVERS="honua geoserver" ./scripts/run-benchmark.sh

# Honua-native raster export track
TESTS="geoservices-export" SERVERS="honua" ./scripts/run-benchmark.sh

# Add lightweight response-shape audits to any selected protocol suite
AUDIT_SHAPES=1 TESTS="attribute-filter spatial-bbox wms-getmap wfs-getfeature" \
  SERVERS="honua geoserver qgis" ./scripts/run-benchmark.sh
```

For a quick validation without running full benchmarks:

```bash
docker compose up -d
./scripts/wait-for-healthy.sh
bash tests/smoke-test.sh
```

## Test Categories

| Category | Description | VUs | Duration |
|----------|-------------|-----|----------|
| `attribute-filter` | Equality, range, LIKE queries via CQL2 | 10 | 120s each |
| `spatial-bbox` | Small/medium/large bounding box queries | 10 | 120s each |
| `concurrent` | Mixed workload at 1/10/50/100 VUs | 1-100 | 120s each |
| `wms-getmap` | WMS raster rendering on the common standards track | 10 | 120s each |
| `wms-reprojection` | WMS `GetMap` with deterministic `EPSG:3857` reprojection from `4326` source data | 10 | 120s each |
| `wfs-getfeature` | WFS base read plus bbox reads on the standards track | 10 | 120s each |
| `geoservices-query` | GeoServices REST FeatureServer/query spatial bbox track | 10 | 120s each |
| `geoservices-query-diagnostics` | Native query diagnostics: 1 VU vs 10 VU and reduced-payload variants on medium/large bboxes | mixed | 15s warmup + 20s each |
| `geoservices-export` | GeoServices REST MapServer/export on the Honua-native track | 10 | 120s each |

The runner captures a lightweight response-shape audit before each timed server run. It is
designed for blog-safe publishing and regression checking, not for performance comparison.

## Optional GeoServer GSR

GeoServer's GeoServices REST support is not part of the stock image. To benchmark
`FeatureServer/query`, run GeoServer with the `gsr` community extension on a matching
nightly build tag such as `docker.osgeo.org/geoserver:2.28.x`, then set
`GEOSERVER_GSR_ENABLED=1`. The GeoBench adapter verifies the GSR query endpoint before the timed
run starts.

## Dataset

**Small** (default): 100,000 point features with 10 attribute fields.

- Deterministic generation (`seed=42`) for reproducibility
- 60% spatially clustered (NYC, Paris, Tokyo, Sao Paulo, Sydney), 40% global
- Attributes: category (10 enum), status (5 enum), priority (1-5), temperature (float), population (int), timestamps, country code, description
- PostGIS GiST spatial index + btree indexes on filterable columns

## Methodology

See [METHODOLOGY.md](METHODOLOGY.md) for the complete fairness and reproducibility framework, including:

- Identical resource constraints per server
- 60-second warmup before all measurements
- 5 runs with median reporting
- Mandatory system cards
- Caching and connection pool policies
- Protocol matrix and reporting tiers

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                  Docker Network                       │
│                                                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │  Honua   │  │GeoServer │  │  QGIS    │           │
│  │  :8080   │  │  :8080   │  │  :80     │           │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘           │
│       │              │              │                 │
│       └──────────────┼──────────────┘                 │
│                      │                                │
│               ┌──────┴──────┐                         │
│               │   PostGIS   │                         │
│               │   :5432     │                         │
│               └─────────────┘                         │
│                                                       │
│  ┌──────────┐                                         │
│  │    k6    │─── OGC API / WMS / WFS / GSR ──► servers│
│  └──────────┘                                         │
└──────────────────────────────────────────────────────┘
```

## Project Structure

```
geobench/
├── data/small/          # Dataset generation
├── adapters/            # Per-server setup scripts
├── src/tests/           # k6 benchmark scripts
├── scripts/             # Orchestration & reporting
├── system-cards/        # Server configuration metadata
├── configs/             # Default & tuned configs per server
├── results/             # Benchmark output (gitignored)
└── tests/               # Smoke tests
```

## Contributing

Adding a new server requires:

1. A Docker image that exposes OGC API Features
2. An adapter script in `adapters/<server>/setup.sh`
3. A server entry in `src/tests/helpers.js`
4. A system card in `system-cards/<server>.json`

See existing adapters for examples. PRs welcome.

## License

Apache 2.0. See [LICENSE](LICENSE).
