# GeoBench

Open, vendor-neutral benchmark suite for geospatial feature servers. Think [TechEmpower](https://www.techempower.com/benchmarks/) for GIS.

## Why

There's no standardized way to compare geospatial feature server performance. Published numbers are
often hard to reproduce or compare across products. GeoBench provides independently verifiable
benchmark definitions, system cards, and artifacts that anyone can rerun.

## Servers Tested

| Server | Runtime | Image |
|--------|---------|-------|
| [Honua Server](https://github.com/honua-io/honua-server) | .NET 10 | `honuaio/honua-server:latest` |
| [GeoServer](https://geoserver.org/) | Java / JVM | `docker.osgeo.org/geoserver:2.28.x` for the headline profile |
| [QGIS Server](https://qgis.org/en/site/about/features.html#qgis-server) | C++ / Qt | `qgis/qgis-server:3.38` |

GeoBench now supports separate tracks for **common feature APIs**, **common raster APIs**,
**secondary standards** such as WFS, and **supplemental native protocols** such as GeoServices
REST. See [METHODOLOGY.md](METHODOLOGY.md) for the matrix and reporting rules.

## Current Snapshot

Current headline two-server snapshot, generated April 28, 2026 HST (April 29 UTC in the report
timestamp), on the 100K-point dataset. This is a 5-run median, baseline/no spatial-response-cache
profile with 30s warmup and 30s measured windows per scenario. Both servers used the strict bounded
database profile: Honua active-query/pool settings were `6/6/3`, and GeoServer datastore pool
settings were `6/3`. Exact image tags and environment variables are shown in the reproduction
command below.

GeoServer was run as `docker.osgeo.org/geoserver:2.28.x` with
`GEOSERVER_COMMUNITY_EXTENSIONS=gsr` for the GeoServices rows. The local image used for this
snapshot resolved to
`docker.osgeo.org/geoserver@sha256:48fcd9488f35c29ef8b8dd2d0b6ae491d1bef73cea83f0ef27f6fa124ddcf245`
and was created on April 20, 2026.

Across the report, all 204 measured performance cells where both servers had data favored the Honua
row, and the six comparable error-rate cells were ties at `0.0%`. The table below keeps raw values
visible instead of repeating a winner label on every line. GeoServices `MapServer/export` has no
GeoServer row in this harness profile. QGIS Server remains runnable in the harness, but it is
omitted from this headline table because this snapshot focuses on the current Honua and GeoServer
profile.

| Track | Scenario | Honua | GeoServer |
|---|---|---:|---:|
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

Full artifacts are under `results/20260428-192053/`, with the two-server report at
`results/20260428-192053/report.md` and the action ledger at
`results/20260428-192053/loss-ledger-final/loss-ledger.md`. Response-shape audits are part of the
report; some feature/native rows have payload metadata or property-key drift and should be described
with those caveats in public claims. The result metadata records that Honua rows came from the
render-gate run in this directory, GeoServer non-refreshed rows came from the strict baseline
`results/20260428-130814/`, and GeoServer `geoservices-query`/`wms-filtered` rows were refreshed in
this directory to remove zero-sample and error-rate caveats.

External reproducibility note: the Honua image for this snapshot,
`honua-geobench:trunk-b650a321-rendergate2`, is a local benchmark build from Honua source around
`b650a321` with the raster render gate defaults set to 8 concurrent renders and a 5s acquire
timeout. Publish or pin the corresponding Honua Server source/image before treating this exact
snapshot as externally rerunnable.

Before publishing a new headline snapshot, run the fairness audit against the result directory:

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

The current rerun status is tracked in [docs/matrix-status.md](docs/matrix-status.md).

## Quick Start

**Requirements**: Docker, Docker Compose v2, Python 3, jq, curl

```bash
# 1. Generate the test dataset (100K points)
python3 data/small/generate.py

# 2. Start all services
docker compose up -d

# 3. Run the default feature benchmark suite
./scripts/run-benchmark.sh
```

Results are written to `results/<timestamp>/report.md`.
Each run also writes `*-response-shapes.json` audit files for the selected servers. The generated
report includes a compact payload comparability section plus a response-shape section with status,
`Content-Type`, byte count, a body hash, and structural notes.

To rank support gaps, regressions, and close rows across existing reports, generate a loss ledger:

```bash
scripts/generate-loss-ledger.py \
  --dedupe latest \
  results/20260425-213925/report.json \
  results/20260329-090404/report.json \
  -o results/loss-ledger-current
```

The ledger writes `loss-ledger.md` and `loss-ledger.json`, ranking support gaps, p95/p99 losses,
throughput losses, and near-ties by priority. Use `--dedupe latest` for the action ledger so fresh
targeted reruns supersede stale rows for the same server/test/scenario/metric tuple. Keep
non-reproducible optional-extension reports out of the current action ledger until the same
extension profile verifies on the current image.

For narrow investigation runs, enable diagnostics:

```bash
DIAGNOSTICS=1 \
TESTS="wms-reprojection" \
SERVERS="honua geoserver" \
WMS_REPROJECTION_SCENARIOS=medium \
WMS_REPROJECTION_WARMUP=10s \
WMS_REPROJECTION_DURATION=30s \
./scripts/run-benchmark.sh
```

Diagnostics mode enables PostGIS statement-duration logging and writes per-server artifacts under
`results/<timestamp>/diagnostics/`: output-shape samples, server logs, PostGIS logs, extracted SQL
statement logs, runtime monitor samples, and `diagnostics/comparison.json`. The comparison summary
includes SQL duration stats for the full log and for the benchmark-marker window, so setup/import
queries do not get confused with timed workload SQL.

The default harness now runs `5` median-reported runs. For quick local validation, set `RUNS=1`
and shorten the suite-specific warmup and duration values.

Protocol-specific runs can be selected explicitly:

```bash
# Common raster track
TESTS="wms-getmap" SERVERS="geoserver qgis" ./scripts/run-benchmark.sh

# Common raster reprojection track
TESTS="wms-reprojection" SERVERS="honua geoserver qgis" ./scripts/run-benchmark.sh

# WMS GetFeatureInfo, narrowed for quick support/tail checks
TESTS="wms-getfeatureinfo" \
WMS_GETFEATUREINFO_SCENARIOS=small \
WMS_GETFEATUREINFO_WARMUP=10s \
WMS_GETFEATUREINFO_DURATION=30s \
WMS_GETFEATUREINFO_VUS=2 \
SERVERS="honua geoserver" \
./scripts/run-benchmark.sh

# Secondary standards track
TESTS="wfs-getfeature" ./scripts/run-benchmark.sh

# Focused WFS GetFeature row check
TESTS="wfs-getfeature" \
WFS_GETFEATURE_SCENARIOS=large \
WFS_GETFEATURE_WARMUP=10s \
WFS_GETFEATURE_DURATION=30s \
WFS_GETFEATURE_VUS=10 \
SERVERS="honua geoserver" \
./scripts/run-benchmark.sh

# Focused feature-filter tail check
TESTS="attribute-filter" \
ATTRIBUTE_FILTER_SCENARIOS=range \
ATTRIBUTE_FILTER_WARMUP=10s \
ATTRIBUTE_FILTER_DURATION=30s \
ATTRIBUTE_FILTER_VUS=2 \
SERVERS="honua geoserver" \
./scripts/run-benchmark.sh

# Focused spatial viewport row check
TESTS="spatial-bbox" \
SPATIAL_BBOX_SCENARIOS=small \
SPATIAL_BBOX_WARMUP=10s \
SPATIAL_BBOX_DURATION=30s \
SPATIAL_BBOX_VUS=10 \
SERVERS="honua geoserver" \
./scripts/run-benchmark.sh

# Focused concurrent workload tail check
TESTS="concurrent" \
CONCURRENT_LEVELS=10 \
CONCURRENT_WORKLOADS=like \
CONCURRENT_WARMUP=10s \
CONCURRENT_DURATION=30s \
SERVERS="honua geoserver" \
./scripts/run-benchmark.sh

# Secondary standards filtered WFS track on the shared WFS 2.0 profile
TESTS="wfs-filtered" SERVERS="honua geoserver" ./scripts/run-benchmark.sh

# Focused WFS filtered row check
TESTS="wfs-filtered" \
WFS_FILTERED_SCENARIOS=range \
WFS_FILTERED_WARMUP=10s \
WFS_FILTERED_DURATION=30s \
WFS_FILTERED_VUS=10 \
SERVERS="honua geoserver" \
./scripts/run-benchmark.sh

# WMS filtered GetMap on the two-server profile
TESTS="wms-filtered" SERVERS="honua geoserver" ./scripts/run-benchmark.sh

# WMTS tile suite (GeoServer only, explicit warm-tile-cache track)
WMTS_CACHE_POLICY=warm TESTS="wmts" SERVERS="geoserver" ./scripts/run-benchmark.sh

# WCS GetCoverage (GeoServer only, requires coverage id and remains experimental)
GEOSERVER_WCS_COVERAGE="geobench:points" TESTS="wcs" SERVERS="geoserver" ./scripts/run-benchmark.sh

# GeoServices MapServer/identify suite
TESTS="geoservices-identify" SERVERS="honua" ./scripts/run-benchmark.sh

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

# GeoServices MapServer/export track for servers that expose it
TESTS="geoservices-export" SERVERS="honua" ./scripts/run-benchmark.sh

# Focused MapServer/export row check
TESTS="geoservices-export" \
GEOSERVICES_EXPORT_SCENARIOS=large \
GEOSERVICES_EXPORT_WARMUP=10s \
GEOSERVICES_EXPORT_DURATION=30s \
GEOSERVICES_EXPORT_VUS=10 \
SERVERS="honua" \
./scripts/run-benchmark.sh

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
| `attribute-filter` | Equality, range, literal-prefix LIKE queries via CQL2 | 10 | 120s each |
| `spatial-bbox` | Small/medium/large viewport bounding box queries | 10 | 120s each |
| `concurrent` | Mixed workload at 1/10/50/100 VUs | 1-100 | 120s each |
| `wms-getmap` | WMS raster rendering on the common standards track | 10 | 120s each |
| `wms-reprojection` | WMS `GetMap` with deterministic `EPSG:3857` reprojection from `4326` source data | 10 | 120s each |
| `wms-getfeatureinfo` | WMS `GetFeatureInfo` on deterministic `CRS:84` hotspots | 10 | 120s each |
| `wms-filtered` | WMS GetMap with OGC `FILTER` queries (equality/range/like) | 10 | 120s each |
| `wmts` | WMTS `GetTile` tile matrix requests | 10 | 120s each |
| `wcs` | WCS `GetCoverage` coverage reads (server-specific coverage required) | 10 | 120s each |
| `wfs-getfeature` | WFS base read plus bbox reads on the standards track | 10 | 120s each |
| `wfs-filtered` | WFS equality/range/prefix filtering on the shared FES 2.0 profile | 10 | 120s each |
| `geoservices-query` | GeoServices REST FeatureServer/query spatial bbox track | 10 | 120s each |
| `geoservices-query-diagnostics` | Native query diagnostics: 1 VU vs 10 VU and reduced-payload variants on medium/large bboxes | mixed | 15s warmup + 20s each |
| `geoservices-export` | GeoServices REST MapServer/export where the server exposes it | 10 | 120s each |
| `geoservices-identify` | GeoServices REST MapServer/identify on deterministic points | 10 | 120s each |

The runner captures a lightweight response-shape audit before each timed server run. It is
designed for blog-safe publishing and regression checking, not for performance comparison. The
generated report now also summarizes whether payload differences appear to be metadata-only or a
core shape divergence that would weaken cross-server comparability.
The `spatial-bbox` row is treated as viewport/windowing behavior, not a definitive spatial
predicate row. Its response validator allows a small coordinate tolerance at bbox edges
(`BBOX_TOLERANCE_DEG`, default `0.0001`) so float-precision envelope candidates do not invalidate
display-oriented bbox results. Exact spatial semantics should be tested through explicit spatial
predicate rows.
The `concurrent` report includes workload-tagged rows when present in k6 summary output. Use those
rows to diagnose tails before tuning the product against the aggregate mixed-workload p95/p99.
`wfs-filtered` currently targets Honua and GeoServer only; the local QGIS benchmark image remains
on a separate WFS 1.1 profile and is not part of this row yet.

## Cache Tiers

GeoBench treats cache behavior as a separate scientific dimension, not as a hidden implementation
detail.

- `baseline`: no dedicated external cache layer is introduced for the row. Warmed runtime state,
  database buffers, and OS cache still exist after warmup.
- `warm service`: an optional label for steady-state warmed service behavior after warmup.
- `warm tile cache`: tile requests intentionally served from a warmed tile cache. This is where the
  current `wmts` row belongs.
- `cache-assisted`: Redis, GeoWebCache blobstores, MinIO/object-store-backed caches, or CDN-like
  layers. Useful, but separate from the baseline matrix.

Current rule: do not compare `warm tile cache` numbers against `baseline` render numbers in the
same table. If a future Redis or MinIO experiment is added, it should be published as a separate
cache-assisted track unless every server is using an equivalent cache role. Ad hoc spatial feature
queries are not treated as cache-assisted rows, and the runner defaults non-WMTS rows to
`baseline`: exact response caching for arbitrary `bbox`,
geometry, nearest/distance, CQL2 spatial predicates, or OData `geo.*` filters has low expected
reuse, so spatial feature rows should measure indexed query execution under warm service state.
Static map/map export bboxes follow the same rule. Tiled or cache-hinted feature reads belong in a
separate tile/cache-assisted track.

GeoWebCache-style results belong in that separate tile/cache-assisted track: fixed gridsets, finite
tile matrix keys, style/format parameter filters, seed/truncate jobs, metatiling, and quota-managed
tile storage. Servers should cache only snapped tile-style keys for those rows and avoid presenting
high-cardinality ad hoc spatial response caching as a baseline benchmark advantage.

Deployment guidance should keep cache roles explicit. Metadata/catalog caches can be useful across
microservice and serverless deployments, but exact response and generic query-result caching should
default off and remain opt-in only for low-cardinality nonspatial reads with measured reuse. Tile
caches should use bounded external storage, quotas, invalidation, and seeded finite key spaces.

## Database Admission Guidance

GeoBench treats database admission as an explicit benchmark input. Do not hide tail-latency wins
behind larger connection pools, implicit adaptive controllers, or cache-assisted rows. The default
recommendation is bounded admission first:

- Cap active database work per service instance. Keep each server's active-query cap and database
  pool ceiling aligned unless a named experiment proves that a larger idle pool helps without
  increasing active database pressure.
- Start from the smallest cap that keeps throughput stable and p95/p99 acceptable. On the local
  small 4-vCPU profile, tested useful caps are in the 4-6 active-query range; simply increasing the
  pool can overfeed PostGIS and worsen tails.
- Scale caps deliberately with node size and database capacity. For multi-node deployments, reason
  from the total database budget first, then divide across nodes; do not let per-node defaults
  multiply into uncontrolled aggregate concurrency.
- Publish fixed-cap results separately from adaptive-admission results. Fixed caps remain the
  baseline until adaptive mode repeatedly beats them under the same image, workload, and machine
  state.
- Treat Redis coordination as research, not a default. It is only justified if multi-node tests
  show that local fixed or adaptive caps cannot protect a shared PostGIS budget.

The runner defaults remain intentionally bounded for both servers
(`HONUA_MAX_CONCURRENT_QUERIES=6`, `HONUA_MAX_CONNECTION_POOL_SIZE=6`,
`HONUA_MIN_CONNECTION_POOL_SIZE=3`, `GEOSERVER_MAX_CONNECTIONS=6`,
`GEOSERVER_MIN_CONNECTIONS=3`) so the benchmark does not trade away p99 latency through hidden
database oversubscription. If a result overrides those values, publish it as a named profile and
keep the exact values visible in the report metadata.

Adaptive admission is benchmark-visible but off by default in the headline profile. The runner
records server-specific adaptive settings in report metadata when a server exposes them. Enable
adaptive admission only as a named profile and keep fixed-pool results separate from adaptive
results. Adaptive reports should include admission telemetry such as current limit, queued waiters,
duration EWMA, queue-wait EWMA when available, and adjustment count.

The runner rejects cache-assisted labels for high-cardinality spatial/render tests unless
`ALLOW_SPATIAL_CACHE_ASSISTED=1` is set. Use that override only for a separate cache-assisted
experiment, not for the baseline standards matrix.

## Optional GeoServer GSR

GeoServer's GeoServices REST support is not part of the stock image. To benchmark
`FeatureServer/query`, run GeoServer with the `gsr` community extension on a matching
nightly build tag such as `docker.osgeo.org/geoserver:2.28.x`, then set
`GEOSERVER_GSR_ENABLED=1`. The GeoBench adapter verifies the GSR query endpoint before the timed
run starts. If verification fails, treat the GeoServer GSR row as unavailable for the current image
and exclude older GSR reports from the current action ledger instead of ranking stale optional
extension rows as current comparative gaps.

## Dataset

**Small** (default): 100,000 point features with 10 attribute fields.

- Deterministic generation (`seed=42`) for reproducibility
- 60% spatially clustered (NYC, Paris, Tokyo, Sao Paulo, Sydney), 40% global
- Attributes: category (10 enum), status (5 enum), priority (1-5), temperature (float), population (int), timestamps, country code, description
- PostGIS GiST spatial index + btree indexes on filterable columns

## Methodology

See [METHODOLOGY.md](METHODOLOGY.md) for the complete fairness and reproducibility framework, including:

- Identical resource constraints per server
- Declared warmup window before all measurements
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
