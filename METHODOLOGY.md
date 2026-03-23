# GeoBench Methodology

This document describes how GeoBench ensures fair, reproducible comparisons between geospatial feature servers.

## Principles

1. **Vendor-neutral**: No server gets special treatment. All use the same dataset, database, network, and resource constraints.
2. **Reproducible**: Deterministic dataset (seed=42), pinned Docker image versions, published system cards. Anyone can replicate results.
3. **Transparent**: All configuration is public. Server-specific tuning is documented, not hidden.

## Environment

### Shared Infrastructure

All servers connect to a **single PostGIS instance** with identical data, indexes, and statistics. This eliminates database-side variance.

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

## Protocol

**Primary**: OGC API Features (all servers support this). Enables direct apples-to-apples comparison on the same API surface.

**Supplementary**: Per-server native protocols (GeoServices REST for Honua, WFS for GeoServer) may be added later as additional data points.

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
- **Single PostGIS instance**: Database-side contention is shared. A server that generates more efficient SQL benefits from less DB load — this is fair (query efficiency is a real characteristic).
- **CQL2 support varies**: QGIS Server has limited CQL2 support. Attribute filter tests may use simpler OGC API Features Part 1 property filters for QGIS, which is noted in results.
- **Response size cap**: `limit=100` per request. Servers with faster JSON serialization benefit — this is intentional (serialization is part of server performance).
- **No raster/imagery benchmarks** in v1.
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
