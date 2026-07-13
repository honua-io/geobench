# GeoBench

[![CI](https://github.com/honua-io/geobench/actions/workflows/ci.yml/badge.svg)](https://github.com/honua-io/geobench/actions/workflows/ci.yml)
[![Security](https://github.com/honua-io/geobench/actions/workflows/security.yml/badge.svg)](https://github.com/honua-io/geobench/actions/workflows/security.yml)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/honua-io/geobench/badge)](https://scorecard.dev/viewer/?uri=github.com/honua-io/geobench)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

GeoBench is an open, vendor-neutral benchmark suite for geospatial feature and
map servers. It runs reproducible [k6](https://k6.io/) workloads against each
server under identical resource limits, with each server backed by its own
dedicated PostGIS instance loaded from the same deterministic dataset, and it
publishes system cards, response-shape audits, fairness audits, and full run
artifacts so results can be checked, not just believed.

Think [TechEmpower](https://www.techempower.com/benchmarks/) for GIS:
transparent workloads, disclosed configuration, and repeatable results.

**Read [METHODOLOGY.md](METHODOLOGY.md) first.** It defines the fairness rules,
protocol matrix, cache-tier taxonomy, database-admission profiles, and
reporting requirements that every published number must follow. A benchmark
capability summary also lives in
[docs/features/README.md](docs/features/README.md).

## Status

Pre-1.0 and actively evolving. Three servers are currently wired into the
harness (see below); adapters for additional servers are welcome. Read
workloads only — no write/edit benchmarks yet. Published comparison snapshots
are point-in-time and carry explicit caveats.

## What GeoBench Measures

GeoBench separates results by protocol family and cache tier. It never merges
unrelated protocols or cache tiers into a single "fastest server" claim.

| Track | Coverage |
|-------|----------|
| Common feature APIs | OGC API Features reads, attribute filters, bbox filters, deep pagination, and mixed concurrent workloads |
| Common raster APIs | WMS `GetMap`, WMS reprojection, and WMS `GetFeatureInfo` |
| Secondary standards | WFS `GetFeature`, filtered WFS, filtered WMS `GetMap`, WMTS (warm-tile-cache row only), and experimental WCS |
| Supplemental native protocols | GeoServices REST `FeatureServer/query`, `MapServer/identify`, and `MapServer/export` |

See [METHODOLOGY.md](METHODOLOGY.md) for the full protocol matrix and which
servers support which rows.

## Servers In The Harness

| Server | Runtime | Default Image |
|--------|---------|---------------|
| [GeoServer](https://geoserver.org/) | Java / JVM | `docker.osgeo.org/geoserver:2.28.0` |
| [Honua Server](https://github.com/honua-io/honua-server) | .NET 10 | `honuaio/honua-server:latest` |
| [QGIS Server](https://qgis.org/en/site/about/features.html#qgis-server) | C++ / Qt | `qgis/qgis-server:3.38` |

Published snapshots may pin a digest or a specific nightly tag; the exact
images used are recorded in each result directory's metadata.

## Quick Start

Requirements: Docker with Docker Compose v2, Python 3, `jq`, `curl`.

Generate the deterministic dataset, then run the default suite
(`attribute-filter`, `spatial-bbox`, `concurrent`; 5 runs each against Honua,
GeoServer, and QGIS):

```bash
python3 data/small/generate.py
./scripts/run-benchmark.sh
```

The runner starts one server stack at a time (PostGIS + server + k6), runs the
selected workloads, writes artifacts under `results/<timestamp>/`, and tears
the stack down before moving to the next server. For a fast local validation
run:

```bash
RUNS=1 \
SERVERS="honua geoserver" \
TESTS="attribute-filter" \
ATTRIBUTE_FILTER_WARMUP=5s \
ATTRIBUTE_FILTER_DURATION=10s \
./scripts/run-benchmark.sh
```

Each run writes raw k6 JSON, copied system cards, `benchmark-metadata.json`,
response-shape audits, and a generated report. Optionally copy `.env.example`
to `.env` to change image tags, host ports, credentials, and defaults —
configuration is entirely env-var driven.

## Running Specific Tracks

Select benchmark families with `TESTS` and server targets with `SERVERS`:

```bash
# OGC API Features deep-pagination track
TESTS="pagination" SERVERS="honua geoserver qgis" ./scripts/run-benchmark.sh

# Common raster track
TESTS="wms-getmap" SERVERS="honua geoserver qgis" ./scripts/run-benchmark.sh

# Common raster reprojection track
TESTS="wms-reprojection" SERVERS="honua geoserver qgis" ./scripts/run-benchmark.sh

# Secondary standards track
TESTS="wfs-getfeature wfs-filtered" SERVERS="honua geoserver" ./scripts/run-benchmark.sh

# Supplemental GeoServices REST track (GeoServer needs the GSR extension, below)
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

For targeted investigation, set `DIAGNOSTICS=1`. Diagnostics mode enables
PostGIS statement-duration logging and writes per-server artifacts under
`results/<timestamp>/diagnostics/`: output shape samples, server and PostGIS
logs, extracted SQL statement logs, runtime monitor samples, and
`diagnostics/comparison.json`.

## Test Categories

| Category | Description | Default VUs | Default Measurement Window |
|----------|-------------|------------:|---------------------------:|
| `attribute-filter` | Equality, range, and literal-prefix LIKE queries via CQL2 | 10 | 120s each |
| `spatial-bbox` | Small, medium, and large viewport bounding-box queries | 10 | 120s each |
| `pagination` | OGC API Features `offset`/`startIndex` paging at shallow, medium, and deep depths | 10 | 120s each |
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

Before each timed run the harness captures a lightweight response-shape audit
(status, `Content-Type`, byte count, body hash, structural notes). It exists
for publishing and regression checks, not as a performance metric.

## Methodology Summary

GeoBench is built around isolation and disclosure:

- Each server runs against its own dedicated PostGIS instance initialized from
  the same deterministic dataset; the orchestrator runs one server at a time
  and tears the stack down between servers.
- Server containers, PostGIS, and k6 each get 4 CPU cores and 4 GB memory.
- Published rows disclose warmup and measurement durations, Docker images,
  system cards, cache tier, and database admission/pool settings.
- The default reported value is the median across 5 independent runs.
- Cache behavior is a benchmark dimension: baseline feature, WFS, GeoServices
  query, and primary WMS rows use no exact response caching; WMTS is a separate
  warm-tile-cache row; Redis/GeoWebCache/object-store caches belong in
  explicitly named cache-assisted tracks.
- Database admission is part of the profile: the default posture is bounded
  fixed admission, so tail-latency wins are not hidden behind larger connection
  pools or adaptive controllers.

Full rules, including the cache-tier taxonomy and reporting requirements, are
in [METHODOLOGY.md](METHODOLOGY.md).

## Dataset

The default dataset is 100,000 deterministic point features with 10 attribute
fields, generated by `python3 data/small/generate.py`:

- Generated with `seed=42`
- 60% spatially clustered around NYC, Paris, Tokyo, Sao Paulo, and Sydney;
  40% globally distributed
- Attributes include category, status, priority, temperature, population,
  timestamps, country code, and description
- PostGIS GiST spatial index plus btree indexes on filterable columns

## Results, System Cards, and Regression Tracking

Every run directory contains raw k6 JSON per run, copied system cards from
`system-cards/`, `benchmark-metadata.json` with exact per-run settings, and
response-shape audits. Without system cards and run metadata, results are not
considered publishable. Useful tooling:

```bash
# Regenerate a report from an existing result directory
python3 scripts/generate-report.py \
  --results-dir results/<timestamp> --output results/<timestamp>/report.md \
  --runs 5 --servers honua,geoserver

# Fairness audit before publishing any comparison snapshot
python3 scripts/audit-fairness.py \
  --results-dir results/<timestamp> --servers honua,geoserver \
  --strict-equal-db-budget
```

The repo also runs an automated per-release benchmark
([.github/workflows/benchmark-on-release.yml](.github/workflows/benchmark-on-release.yml)):
each Honua Server release tag triggers the core feature tracks plus a
cold-start measurement, compares p50/p95/p99, req/s, and error rate against the
stored baseline (`results/baselines/honua-baseline.json`) with
`scripts/check-regression.py`, and commits the results under
[results/releases/](results/releases/). This is a single-server regression
gate, not a cross-server comparison.

## Published Comparison Snapshots

The most recent cross-server snapshot (Honua vs GeoServer, April 28, 2026,
100K-point dataset, 5-run median, 30s warmup + 30s measured windows, baseline
cache tier, strict bounded database profile: Honua active-query/pool `6/6/3`,
GeoServer datastore pool `6/3`, GeoServer running the GSR community extension
for GeoServices rows) is summarized below. In that snapshot all 204 comparable
performance cells favored Honua; the six comparable error-rate cells tied at
`0.0%`. QGIS Server remains runnable in the harness but was not part of this
two-server profile.

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

Read this snapshot with its caveats:

- Some feature and native rows show payload metadata or property-key drift in
  the response-shape audits; public claims should carry those caveats.
- The Honua image used for this exact snapshot
  (`honua-geobench:trunk-b650a321-rendergate2`) was a local benchmark build
  from Honua source around `b650a321` (raster render-gate defaults: 8
  concurrent renders, 5-second acquire timeout). Until a matching public
  Honua image or source pin is published, this exact snapshot is not
  externally rerunnable.
- Per-timestamp result directories are gitignored; the full artifacts for this
  run live with the maintainers, and the snapshot status is tracked in
  [docs/matrix-status.md](docs/matrix-status.md).

<details>
<summary>Exact snapshot images and reproduction commands</summary>

The GeoServer image resolved locally to:

```text
docker.osgeo.org/geoserver@sha256:48fcd9488f35c29ef8b8dd2d0b6ae491d1bef73cea83f0ef27f6fa124ddcf245
```

The local image was created on April 20, 2026 and was run with
`GEOSERVER_COMMUNITY_EXTENSIONS=gsr` for the GeoServices rows.

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

Before publishing a new headline snapshot, run the fairness audit against the
result directory (see command above).

</details>

## Optional GeoServer GSR

GeoServer's GeoServices REST support is not part of the stock image. To
benchmark `FeatureServer/query` or `MapServer/identify`, run GeoServer with the
`gsr` community extension on a matching nightly build tag such as
`docker.osgeo.org/geoserver:2.28.x`, then set `GEOSERVER_GSR_ENABLED=1`. If GSR
endpoint verification fails, treat the GeoServer GSR row as unavailable for the
current image.

## Project Layout

```text
geobench/
|-- adapters/          # Per-server setup scripts (honua, geoserver, qgis)
|-- data/small/        # Deterministic dataset generator
|-- docs/              # Investigation notes, matrix status, and issue drafts
|-- results/           # Benchmark output; committed: baselines/ and releases/
|-- scripts/           # Orchestration, reporting, diagnostics, and audits
|-- src/tests/         # k6 benchmark scripts and shared helpers
|-- system-cards/      # Server configuration metadata
|-- tests/             # Smoke test (1 VU, 5s per server, needs a running stack)
|-- docker-compose.yml
|-- METHODOLOGY.md
`-- README.md
```

## Adding a Server

GeoBench is designed to grow beyond the current three servers. A new server
needs:

1. A Docker image that exposes the target geospatial API surface.
2. A service (plus dedicated `postgis-<server>` instance) in
   `docker-compose.yml`, gated by a `<server>` Compose profile.
3. An adapter script at `adapters/<server>/setup.sh` that loads data and
   configures layers/styles.
4. A server entry in the `SERVERS` map in `src/tests/helpers.js`.
5. A system card at `system-cards/<server>.json`.

See the existing adapters and system cards for examples. Any product-specific
serving objects the adapter creates (published layers, materialized rows,
expression indexes) must be disclosed in the adapter and system card. Pull
requests are welcome.

## Related Projects

- [honua-server](https://github.com/honua-io/honua-server) — one of the
  servers benchmarked here; its releases drive the per-release regression gate
- [geospatial-grpc](https://github.com/honua-io/geospatial-grpc) — open,
  vendor-neutral gRPC protocol standard for geospatial services
- [geospatial-mcp](https://github.com/honua-io/geospatial-mcp) — open,
  vendor-neutral geospatial MCP standard

## Security

Report vulnerabilities to security@honua.io. See the
[organization security policy](https://github.com/honua-io/.github/blob/main/SECURITY.md).

## License

Apache 2.0. See [LICENSE](LICENSE).
