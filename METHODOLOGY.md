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
| Raster | WMS `GetMap` | Yes | Yes | Yes | Primary | First common raster track |
| Raster | WMS `GetMap` reprojection | Yes | Yes | Yes | Secondary | Same deterministic views as the base WMS row, requested in `EPSG:3857` |
| Raster | WMS `GetFeatureInfo` | Yes | Yes | Yes | Secondary | Useful, but more sensitive to styling and hit-testing nuances |

### Secondary Standards Track

These are standards-based, but version and implementation differences can make the comparisons
messier than the primary track. They should be published separately with explicit caveats.

| Family | Operation | Honua | GeoServer | QGIS | Publish Tier | Notes |
|--------|-----------|-------|-----------|------|--------------|-------|
| Feature | WFS `GetFeature` | Yes | Yes | Yes | Secondary | WFS version support differs across servers |
| Feature | WFS filtered queries | Yes | Yes | Yes | Secondary | Prefer a version/profile all tested servers genuinely support |
| Raster/Tiles | WMTS tile fetch | Claimed | Yes | Yes | Secondary | Requires an explicit cache policy before benchmarking |
| Raster | WCS coverage access | Unknown | Yes | Yes | Experimental | Not part of v1 until common coverage data exists |

### Supplemental Native Track

These are useful for product evaluation but are not vendor-neutral standards comparisons. They
must be reported in separate charts.

| Family | Operation | Honua | GeoServer | QGIS | Publish Tier | Notes |
|--------|-----------|-------|-----------|------|--------------|-------|
| Feature | GeoServices REST `FeatureServer/query` | Yes | With GSR extension | No | Supplemental | GeoBench v1 limits this track to spatial bbox queries |
| Feature | GeoServices REST query diagnostics | Yes | With GSR extension | No | Diagnostic | For optimization work only: concurrency and payload-shape isolates on medium/large bbox reads |
| Raster | GeoServices REST `MapServer/export` | Yes | No | No | Supplemental | Honua-only supplemental raster track |
| Raster/Identify | GeoServices REST `MapServer/identify` | Yes | With GSR extension | No | Supplemental | Useful if we later add identify tests |

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
- **GeoServices REST on GeoServer** is not part of the stock image. It requires the
  **GSR community extension** and a matching GeoServer nightly build, so it should be treated
  as a separate packaging tier.
- **GeoServer GSR support is partial**:
  - `FeatureServer/query` is suitable for supplemental native benchmarking, but without non-geospatial filters or record-count pagination
  - `MapServer/export` is not part of the current GeoServer GSR capability surface
- **WMTS and tile-based benchmarks** require an explicit cache policy. Cache-on and cache-off
  results answer different questions and should not be conflated.

### Reporting Rule

GeoBench reports protocols in separate families:

1. **Common standards, feature**
2. **Common standards, raster**
3. **Secondary standards**
4. **Supplemental native protocols**

No overall "fastest server" claim is valid across mixed protocol families.

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
- **CQL2 / filter support varies**: QGIS Server may require WFS Filter Encoding instead of native OGC API `filter=` semantics for fair equivalent filter tests.
- **Response size cap**: `limit=100` per request. Servers with faster JSON serialization benefit — this is intentional (serialization is part of server performance).
- **Raster benchmarks must control styling**: default symbology, labels, antialiasing, and transparency can materially change render cost and output bytes.
- **Raster results must be reported separately** from feature results until style parity is pinned and documented.
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
