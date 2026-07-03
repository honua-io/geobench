# GeoBench Results

Generated: 2026-07-03 05:30 UTC
Dataset: Small (100K points) | Runs: 3 (median reported)

## Benchmark Semantics

| Topic | Policy |
| --- | --- |
| `spatial-bbox` | viewport/windowing bbox; not an exact spatial predicate row; edge tolerance=0.0001 degrees |
| `attribute-filter` | equality, numeric range, and literal-prefix LIKE filters via CQL2 where supported |
| `concurrent` | mixed workload: 40% bbox, 30% equality, 20% range, 10% like; report includes workload-tagged tail latency when available |
| Spatial response caching | default=false; cache-assisted spatial/render rows must be run as a separate track |
| Response validation | k6 discards default bodies; measured feature requests set responseType=text so checks can validate payload semantics |
| Pool profile | connection/admission settings are reported as benchmark inputs, not hidden tuning |

## Common Standards: Feature

### Attribute Filter

| Query Type | Metric | Honua Server |
| --- | --- | --- |
| equality | req/s | 4605.4 |
|  | p50 ms | 1.7 |
|  | p95 ms | 3.7 |
|  | p99 ms | 5.3 |
|  | error % | — |
| range | req/s | 4449.4 |
|  | p50 ms | 1.7 |
|  | p95 ms | 3.6 |
|  | p99 ms | 5.2 |
|  | error % | — |
| like | req/s | 4389.9 |
|  | p50 ms | 1.7 |
|  | p95 ms | 3.7 |
|  | p99 ms | 5.5 |
|  | error % | — |

### Spatial BBox

| BBox Size | Metric | Honua Server |
| --- | --- | --- |
| small | req/s | 4523.0 |
|  | p50 ms | 1.7 |
|  | p95 ms | 3.7 |
|  | p99 ms | 5.5 |
|  | error % | — |
| medium | req/s | 4102.2 |
|  | p50 ms | 1.7 |
|  | p95 ms | 3.6 |
|  | p99 ms | 5.5 |
|  | error % | — |
| large | req/s | 4154.5 |
|  | p50 ms | 1.6 |
|  | p95 ms | 3.7 |
|  | p99 ms | 5.8 |
|  | error % | — |

### Concurrent (Mixed Workload)

| VUs | Metric | Honua Server |
| --- | --- | --- |
| 1 | req/s | 1411.2 |
|  | p50 ms | 0.4 |
|  | p95 ms | 0.5 |
|  | p99 ms | 1.8 |
|  | error % | — |
| 10 | req/s | 4048.3 |
|  | p50 ms | 1.7 |
|  | p95 ms | 3.9 |
|  | p99 ms | 6.4 |
|  | error % | — |
| 50 | req/s | 4819.5 |
|  | p50 ms | 8.7 |
|  | p95 ms | 17.7 |
|  | p99 ms | 27.0 |
|  | error % | — |
| 100 | req/s | 4808.4 |
|  | p50 ms | 17.9 |
|  | p95 ms | 32.8 |
|  | p99 ms | 47.6 |
|  | error % | — |

#### Concurrent Workload Breakdown

Canonical mixed workload: 40% bbox, 30% equality, 20% range, 10% like.
Rows are reported when k6 exports both `concurrency` and `workload` tags.

| VUs | Workload | Mix | Metric | Honua Server |
| --- | --- | --- | --- | --- |
| 1 | bbox | 40% | req/s | 562.3 |
|  |  |  | p50 ms | 0.4 |
|  |  |  | p95 ms | 0.5 |
|  |  |  | p99 ms | 16.9 |
|  |  |  | error % | — |
| 1 | equality | 30% | req/s | 423.9 |
|  |  |  | p50 ms | 0.4 |
|  |  |  | p95 ms | 0.5 |
|  |  |  | p99 ms | 0.7 |
|  |  |  | error % | — |
| 1 | range | 20% | req/s | 280.2 |
|  |  |  | p50 ms | 0.4 |
|  |  |  | p95 ms | 0.5 |
|  |  |  | p99 ms | 3.4 |
|  |  |  | error % | — |
| 1 | like | 10% | req/s | 141.4 |
|  |  |  | p50 ms | 0.4 |
|  |  |  | p95 ms | 0.5 |
|  |  |  | p99 ms | 5.9 |
|  |  |  | error % | — |
| 10 | bbox | 40% | req/s | 1615.0 |
|  |  |  | p50 ms | 1.7 |
|  |  |  | p95 ms | 3.9 |
|  |  |  | p99 ms | 6.8 |
|  |  |  | error % | — |
| 10 | equality | 30% | req/s | 1218.5 |
|  |  |  | p50 ms | 1.7 |
|  |  |  | p95 ms | 3.9 |
|  |  |  | p99 ms | 5.9 |
|  |  |  | error % | — |
| 10 | range | 20% | req/s | 808.1 |
|  |  |  | p50 ms | 1.8 |
|  |  |  | p95 ms | 4.0 |
|  |  |  | p99 ms | 6.5 |
|  |  |  | error % | — |
| 10 | like | 10% | req/s | 406.6 |
|  |  |  | p50 ms | 1.8 |
|  |  |  | p95 ms | 4.0 |
|  |  |  | p99 ms | 6.8 |
|  |  |  | error % | — |
| 50 | bbox | 40% | req/s | 1928.7 |
|  |  |  | p50 ms | 8.7 |
|  |  |  | p95 ms | 17.7 |
|  |  |  | p99 ms | 27.5 |
|  |  |  | error % | — |
| 50 | equality | 30% | req/s | 1441.9 |
|  |  |  | p50 ms | 8.7 |
|  |  |  | p95 ms | 17.6 |
|  |  |  | p99 ms | 25.7 |
|  |  |  | error % | — |
| 50 | range | 20% | req/s | 966.4 |
|  |  |  | p50 ms | 8.8 |
|  |  |  | p95 ms | 17.7 |
|  |  |  | p99 ms | 27.3 |
|  |  |  | error % | — |
| 50 | like | 10% | req/s | 482.5 |
|  |  |  | p50 ms | 8.8 |
|  |  |  | p95 ms | 17.5 |
|  |  |  | p99 ms | 27.8 |
|  |  |  | error % | — |
| 100 | bbox | 40% | req/s | 1925.5 |
|  |  |  | p50 ms | 17.9 |
|  |  |  | p95 ms | 32.9 |
|  |  |  | p99 ms | 49.0 |
|  |  |  | error % | — |
| 100 | equality | 30% | req/s | 1442.3 |
|  |  |  | p50 ms | 17.9 |
|  |  |  | p95 ms | 32.8 |
|  |  |  | p99 ms | 46.3 |
|  |  |  | error % | — |
| 100 | range | 20% | req/s | 960.0 |
|  |  |  | p50 ms | 18.0 |
|  |  |  | p95 ms | 32.7 |
|  |  |  | p99 ms | 47.9 |
|  |  |  | error % | — |
| 100 | like | 10% | req/s | 480.5 |
|  |  |  | p50 ms | 17.9 |
|  |  |  | p95 ms | 32.9 |
|  |  |  | p99 ms | 48.2 |
|  |  |  | error % | — |

## Cache Tiers

Default non-WMTS tier: `baseline`

| Test | Cache tier | Notes |
| --- | --- | --- |
| attribute-filter | baseline | - |
| spatial-bbox | baseline | bbox_tolerance_deg=0.0001 |
| concurrent | baseline | - |

## Server Images

| Component | Image |
| --- | --- |
| Honua Server | `ghcr.io/honua-io/honua-server:nightly-aot` |
| postgis | `postgis/postgis:17-3.5` |
| k6 | `grafana/k6:0.54.0` |

## Server Tuning

| Server | Setting | Value |
| --- | --- | --- |
| Honua Server | `adaptive_admission_enabled` | `False` |
| Honua Server | `adaptive_admission_initial_target` | `6` |
| Honua Server | `adaptive_admission_max_target` | `6` |
| Honua Server | `adaptive_admission_min_target` | `3` |
| Honua Server | `adaptive_admission_target_duration_ms` | `100` |
| Honua Server | `adaptive_admission_update_interval_ms` | `1000` |
| Honua Server | `max_concurrent_queries` | `6` |
| Honua Server | `max_connection_pool_size` | `6` |
| Honua Server | `min_connection_pool_size` | `3` |
| Honua Server | `response_caching_enabled` | `False` |
