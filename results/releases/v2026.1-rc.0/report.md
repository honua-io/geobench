# GeoBench Results

Generated: 2026-09-27 06:13 UTC
Dataset: Small (100K points) | Runs: 3 (median reported)

**INVALID / INCOMPLETE EVIDENCE — failed runs are excluded from performance tables.**
Do not publish comparisons or promote a baseline from this campaign.

- `honua-attribute-filter-run1.json`: missing or failed response checks; errors=99.424%; http_req_failed=99.424%
- `honua-attribute-filter-run2.json`: missing or failed response checks; errors=99.674%; http_req_failed=99.674%
- `honua-attribute-filter-run3.json`: missing or failed response checks; errors=99.563%; http_req_failed=99.563%
- `honua-concurrent-run1.json`: missing or failed response checks; errors=99.503%; http_req_failed=99.503%
- `honua-concurrent-run2.json`: missing or failed response checks; errors=99.599%; http_req_failed=99.599%
- `honua-concurrent-run3.json`: missing or failed response checks; errors=99.498%; http_req_failed=99.498%
- `honua-spatial-bbox-run1.json`: missing or failed response checks; errors=99.661%; http_req_failed=99.661%
- `honua-spatial-bbox-run2.json`: missing or failed response checks; errors=99.535%; http_req_failed=99.535%
- `honua-spatial-bbox-run3.json`: missing or failed response checks; errors=99.656%; http_req_failed=99.656%

## Benchmark Semantics

| Topic | Policy |
| --- | --- |
| `spatial-bbox` | viewport/windowing bbox; not an exact spatial predicate row; edge tolerance=0.0001 degrees |
| `attribute-filter` | equality, numeric range, and literal-prefix LIKE filters via CQL2 where supported |
| `concurrent` | mixed workload: 40% bbox, 30% equality, 20% range, 10% like; report includes workload-tagged tail latency when available |
| Spatial response caching | default=false; cache-assisted spatial/render rows must be run as a separate track |
| Response validation | k6 discards default bodies; measured feature requests set responseType=text so checks can validate payload semantics |
| Pool profile | connection/admission settings are reported as benchmark inputs, not hidden tuning |

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
