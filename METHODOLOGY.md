# GeoBench Methodology

This document describes how GeoBench ensures fair, reproducible comparisons between geospatial feature servers.

## Principles

1. **Vendor-neutral**: No server gets special treatment. All use the same dataset, database, network, and resource constraints.
2. **Reproducible**: Deterministic dataset (seed=42), pinned Docker image versions, published system cards. Anyone can replicate results.
3. **Transparent**: All configuration is public. Server-specific tuning is documented, not hidden.

## Environment

### Complete Isolation

Each server runs against its **own dedicated PostGIS instance** with identical data, indexes, and statistics. The orchestrator starts one server at a time (PostGIS + server + k6), runs all benchmarks, then tears the stack down completely before starting the next server. No shared database, no shared buffers, no connection slot contention.

- **PostGIS image**: `postgis/postgis:17-3.5`
- **Dataset**: 100K point features, 10 attribute fields, GiST spatial index + btree attribute indexes
- **Statistics**: `ANALYZE` run after data load

### Resource Constraints

Every server container runs with identical Docker resource limits:

| Resource | Server Containers | PostGIS | k6 (load generator) |
|----------|------------------|---------|---------------------|
| CPU | 4 cores | 2 cores | 4 cores |
| Memory | 4 GB | 2 GB | 2 GB |

Limits are enforced via Docker Compose `deploy.resources.limits` (requires Compose v2).

### Network

All containers share a single Docker bridge network. k6 runs inside the same network to eliminate host networking variance. External port mappings exist only for debugging.

## Configuration Tiers

Results are reported at two levels:

- **Default**: Server's shipping defaults. No tuning. Tests the out-of-box experience.
- **Tuned**: Server maintainer's recommended production configuration for the given hardware. All changes documented in system cards.

Both tiers are reported. Neither is hidden.

## Warmup Protocol

**Every** test category begins with a 60-second warmup phase under sustained load before measurement starts. This applies to all servers equally, normalizing:

- JVM JIT compilation (GeoServer)
- Connection pool ramp-up
- OS page cache warming
- PostGIS query plan caching

The warmup phase uses the same query patterns as the measurement phase. Warmup data points are excluded from reported metrics.

## Caching Policy

- **GeoWebCache** (GeoServer): Explicitly disabled for benchmark layers. GWC does not affect WFS/OGC API Features queries, only tile requests.
- **Server-side query caching**: Not disabled (would be artificial). If a server caches query results, that's a legitimate performance characteristic. Documented in system cards.
- **PostGIS shared buffers**: Default configuration. Same for all servers since they share the instance.

### Cache Tier Taxonomy

GeoBench treats caching as a measurement dimension, not a single yes/no setting. Different cache
roles answer different questions and must be published separately.

- **Baseline**
  No dedicated external cache product is added for the row. In-process caches, database buffers,
  OS page cache, and warmed execution plans are still part of steady-state behavior after warmup.
- **Warm Service State**
  The same baseline stack interpreted explicitly as warmed steady-state service behavior after the
  standard warmup period.
- **Warm Tile Cache**
  Tile requests are intentionally served from a warmed tile cache. This is valid for tile
  protocols such as WMTS and should be interpreted as a delivery/cache row, not a render row.
- **Cache-Assisted Product Track**
  A product's natural cache layer is introduced on purpose, such as GeoWebCache blobstores,
  Redis-backed response caches, MinIO/object-store-backed caches, or CDN-like layers. These rows
  are useful, but they are not vendor-neutral unless each server is tested with an equivalent
  cache role.

### Cache Tier Rules

- Every published row must declare its cache tier.
- Cache tiers must not be mixed within the same comparison table.
- `WMTS` belongs in a `Warm Tile Cache` row in the current harness.
- `OGC API Features`, `WFS`, `GeoServices query`, and primary `WMS GetMap` rows belong in the
  `Baseline` / `Warm Service State` interpretation unless a dedicated cache layer is explicitly
  added and disclosed.
- A local Redis or MinIO sidecar is valid only as a separate `Cache-Assisted Product Track`,
  because local Docker cache behavior is not the same thing as managed cloud cache behavior.

## Measurement

### Tool

[k6](https://k6.io/) — scriptable load generator with native JSON metrics output.

### Duration & Runs

- **Measurement window**: 120 seconds per test scenario
- **Runs**: 5 independent runs per server/test combination
- **Reported value**: Median across runs (eliminates outliers)

### Metrics

| Metric | Definition |
|--------|-----------|
| req/s | Completed HTTP 200 responses per second |
| p50 | 50th percentile of `http_req_duration` (ms) |
| p95 | 95th percentile of `http_req_duration` (ms) |
| p99 | 99th percentile of `http_req_duration` (ms) |
| error rate | Percentage of non-200 responses |

All latency measurements are client-side (k6), including Docker bridge network time (sub-millisecond, identical for all servers).

### Concurrency Levels

The `concurrent` test ramps through: 1, 10, 50, 100 virtual users (VUs). Each level runs for 120 seconds after warmup.

### Error Threshold

- Standard tests: Results discarded if error rate > 1%
- High-concurrency tests (50+ VUs): Results discarded if error rate > 5%

### Response Shape Audit

Every server run also captures a lightweight response-shape audit before the timed load starts.
This audit is not part of the benchmark result. It records:

- HTTP status
- `Content-Type`
- response byte count
- body hash
- compact shape notes for JSON and image responses

The audit exists to make protocol comparisons publishable and to catch accidental response
shape drift without exposing raw payloads.

The generated report also includes a payload comparability summary. It distinguishes metadata-only
differences from core payload drift such as feature count changes, geometry-type changes, or
property-schema changes. This still does not replace full semantic validation or production
telemetry; it is a harness-local guardrail.

## Protocol Matrix

GeoBench separates protocol families into **primary common**, **secondary standards**, and
**supplemental native** tracks. Results from different tracks are never merged into a single
"winner" chart.

### Primary Common Track

These are the first charts to publish because they exercise equivalent capabilities across all
servers on broadly comparable surfaces.

| Family | Operation | Honua | GeoServer | QGIS | Publish Tier | Notes |
|--------|-----------|-------|-----------|------|--------------|-------|
| Feature | OGC API Features `items` read | Yes | Yes | Yes | Primary | Main apples-to-apples feature read surface |
| Feature | OGC API-equivalent attribute filtering | Yes | Yes | Yes | Primary | QGIS may require WFS Filter Encoding internally for fair equivalent filters |
| Feature | OGC API-equivalent bbox filtering | Yes | Yes | Yes | Primary | Same response limit and validation policy |
| Feature | Mixed feature workload | Yes | Yes | Yes | Primary | Must be composed only of request types that validate equivalently |
| Raster | WMS `GetMap` | Yes | Yes | Yes | Primary | First common raster track; baseline non-tile-cached render row |
| Raster | WMS `GetMap` reprojection | Yes | Yes | Yes | Secondary | Same deterministic views as the base WMS row, requested in `EPSG:3857` |
| Raster | WMS `GetFeatureInfo` | Yes | Yes | Yes | Secondary | Useful, but more sensitive to styling and hit-testing nuances |

### Secondary Standards Track

These are standards-based, but version and implementation differences can make the comparisons
messier than the primary track. They should be published separately with explicit caveats.

| Family | Operation | Honua | GeoServer | QGIS | Publish Tier | Notes |
|--------|-----------|-------|-----------|------|--------------|-------|
| Feature | WFS `GetFeature` | Yes | Yes | Yes | Secondary | WFS version support differs across servers |
| Feature | WFS filtered queries | Yes | Yes | Pending | Secondary | Current harness uses the shared Honua/GeoServer WFS 2.0 + FES 2.0 profile; QGIS needs a separate 1.1-equivalent row |
| Feature | WMS GetMap with OGC `FILTER` | Yes | Yes | No | Secondary | Deterministic equality/range/like filter patterns on raster rendering |
| Raster/Tiles | WMTS tile fetch | No | Yes | No | Secondary | Published only as an explicit warm-tile-cache row; cache-fill or uncached behavior belongs in a separate diagnostic track |
| Raster | WCS coverage access | No | Yes | No | Experimental | Requires explicit coverage configuration and shared sample coverage data |

### Supplemental Native Track

These are useful for product evaluation but are not vendor-neutral standards comparisons. They
must be reported in separate charts.

| Family | Operation | Honua | GeoServer | QGIS | Publish Tier | Notes |
|--------|-----------|-------|-----------|------|--------------|-------|
| Feature | GeoServices REST `FeatureServer/query` | Yes | With GSR extension | No | Supplemental | GeoBench v1 limits this track to spatial bbox queries |
| Feature | GeoServices REST query diagnostics | Yes | With GSR extension | No | Diagnostic | For optimization work only: concurrency and payload-shape isolates on medium/large bbox reads |
| Raster | GeoServices REST `MapServer/export` | Yes | No | No | Supplemental | Honua-only supplemental raster track |
| Raster/Identify | GeoServices REST `MapServer/identify` | Yes | With GSR extension | No | Supplemental | Added as a supplemental native benchmark row |

### Out of Cross-Server Scope

These are valid product capabilities, but they are not common enough across the tested servers
to belong in GeoBench's cross-server matrix.

| Capability | Honua | GeoServer | QGIS | Status |
|-----------|-------|-----------|------|--------|
| OData | Yes | No | No | Out of scope |
| gRPC runtime | Yes | No | No | Out of scope |
| MCP / agent tools | Yes | No | No | Out of scope |

### Version / Packaging Notes

- **WFS support is not uniform**:
  - Honua local benchmark image currently exposes **WFS 2.0.0**
  - GeoServer supports **WFS 1.0.0 / 1.1.0 / 2.0.0**
  - QGIS Server local benchmark image exposes **WFS 1.1.0**
- **WFS filtered queries currently use the shared WFS 2.0 + FES 2.0 profile**
  exposed by Honua and GeoServer. QGIS filtered WFS coverage needs a separate
  equivalent 1.1 profile and is not part of the current row.
- **GeoServices REST on GeoServer** is not part of the stock image. It requires the
  **GSR community extension** and a matching GeoServer nightly build, so it should be treated
  as a separate packaging tier.
- **GeoServer GSR support is partial**:
  - `FeatureServer/query` is suitable for supplemental native benchmarking, but without non-geospatial filters or record-count pagination
  - `MapServer/export` is not part of the current GeoServer GSR capability surface
- **WMTS and tile-based benchmarks** require an explicit cache policy. Cache-on and cache-off
  results answer different questions and should not be conflated.
- **Cache role equivalence matters more than cache brand**: Redis vs GeoWebCache vs MinIO is not
  the right comparison axis. The right question is whether each server is using an equivalent
  cache function: tile cache, query/result cache, metadata cache, or object/blob cache.
- **Local cache backends are not cloud telemetry**: a local Redis sidecar, filesystem cache, or
  GeoWebCache blobstore is useful for a harness-local cache-assisted track, but it does not model
  CDN behavior, object-store latency, or managed cloud cache failure modes.

### Reporting Rule

GeoBench reports protocols in separate families:

1. **Common standards, feature**
2. **Common standards, raster**
3. **Secondary standards**
4. **Supplemental native protocols**

No overall "fastest server" claim is valid across mixed protocol families.
No overall claim is valid across mixed cache tiers either. A `Warm Tile Cache` row and a
`Baseline` render row answer different questions and must remain in separate charts.

Response-shape audits are reported separately from performance tables and should be treated as
supporting evidence, not benchmark results.

## System Cards

Every result set includes a machine-readable `system-card.json` per server documenting:

- Server name, version, Docker image
- Runtime (JVM, .NET, C++)
- Resource limits (CPU, memory)
- Configuration tier
- Connection pool settings
- OGC API Features conformance classes
- CQL2 support level
- Any server-specific notes

Without a system card, results are not considered publishable.

## Known Limitations

- **Docker resource limits are soft** (cgroups v2). Bare-metal results may differ.
- **Dedicated PostGIS instances**: Each server gets its own PostGIS with identical data. Database shared buffers warm independently per server. Host-level CPU/memory is the only shared resource.
- **Local Docker is not the cloud**: these numbers are useful for reproducible local comparison, not
  for claiming exact production behavior under managed load balancers, remote caches, or cloud
  storage layers.
- **CQL2 / filter support varies**: QGIS Server may require WFS Filter Encoding instead of native OGC API `filter=` semantics for fair equivalent filter tests.
- **WFS filtered coverage is intentionally partial**: the current harness benchmarks the common Honua/GeoServer WFS 2.0 FES profile only.
- **Response size cap**: `limit=100` per request. Servers with faster JSON serialization benefit — this is intentional (serialization is part of server performance).
- **Raster benchmarks must control styling**: default symbology, labels, antialiasing, and transparency can materially change render cost and output bytes.
- **Raster results must be reported separately** from feature results until style parity is pinned and documented.
- **Payload audits are heuristic**: they surface shape drift and metadata differences, but they are
  not a substitute for deep payload equivalence proofs or cloud-side tracing.
- **No write/edit operation benchmarks** in v1.

## Reproducibility

```bash
# Generate dataset
python3 data/small/generate.py

# Start stack and run benchmarks
docker compose up -d
./scripts/run-benchmark.sh
```

Results directory contains all JSON metrics, system cards, and the generated report.
