# Honua OGC Load Optimization Ticket

Superseded as a standalone planning artifact by
[docs/honua-performance-refactor-ticket.md](./honua-performance-refactor-ticket.md).
Keep this note as protocol-specific background and evidence.

## Summary

Honua still loses the fair OGC API Features mixed-load benchmark to GeoServer under sustained concurrency.

The remaining bottleneck is not just missing Postgres indexes. Honua's OGC items path is structurally committed to exact total counts on the hot read path, which adds avoidable cost under load.

This ticket captures the current benchmark evidence and the concrete Honua-side change that is most likely to move the result.

## Current Benchmark Evidence

Latest production-mode Honua rerun:
- results: [results/20260323-195109/report.md](../results/20260323-195109/report.md)
- concurrent overall: `127.3 req/s`, `p95 1388.9 ms`, `p99 2889.5 ms`
- concurrent by stage:
  - `1 VU`: `10.0 req/s`, `p95 55.1 ms`
  - `10 VUs`: `29.1 req/s`, `p95 210.3 ms`
  - `50 VUs`: `33.2 req/s`, `p95 1164.6 ms`
  - `100 VUs`: `31.4 req/s`, `p95 2675.3 ms`

GeoServer fair reference:
- results: [results/20260323-141856/report.md](../results/20260323-141856/report.md)
- concurrent by stage:
  - `1 VU`: `15.9 req/s`, `p95 28.2 ms`
  - `10 VUs`: `56.0 req/s`, `p95 86.9 ms`
  - `50 VUs`: `59.7 req/s`, `p95 299.0 ms`
  - `100 VUs`: `68.0 req/s`, `p95 406.5 ms`

What improved already:
- benchmark-aligned expression indexes on `public.features`
- benchmark Honua service now runs in `Production` mode in [docker-compose.yml](../docker-compose.yml)

What that changed:
- better attribute-filter behavior
- better low/mid concurrency latency
- not enough to win the load test

## Direct Evidence From Honua

### 1. OGC handler requires exact totals

Decompiled `Honua.Server.Features.OgcFeatures.OgcFeaturesQueryHandler` shows:

- streaming OGC responses call `_featureReader.CountAsync(...)` before returning data
- non-streaming JSON/GeoJSON responses require `QueryAsync(...)` or `QueryGeoJsonAsync(...)` to return `TotalCount`
- the final OGC response always sets `numberMatched`

That means exact totals are part of the current OGC items contract in Honua's implementation.

### 2. Paginated OGC queries use window-count queries

Decompiled `Honua.Postgres.Features.FeatureStore.PostgresFeatureStoreRefactored` shows:

- paginated requests (`Limit` or `Offset`) use `QueryOptimizedAsync(...)` / `QueryOptimizedGeoJsonAsync(...)`
- those methods extract `__honua_total_count` from the returned row attributes

Decompiled `Honua.Postgres.Features.FeatureStore.Services.FeatureQueryBuilder` shows:

- `BuildOptimizedSelectWithWindowCountQuery(...)` emits:
  - `COUNT(*) OVER() as __honua_total_count`

So for the benchmark path, Honua is not just reading a page of rows. It is reading a page plus an exact total count in the same query.

### 3. Live Postgres logs matched the decompiled path

Observed benchmark-shaped SQL from the running Honua container:

```sql
SELECT objectid, ..., attributes, COUNT(*) OVER() as __honua_total_count
FROM "features"
WHERE layer_id = $1 AND ...
ORDER BY objectid ASC
LIMIT $n OFFSET $m
```

This confirms the benchmark is exercising the same path the decompiled code describes.

## Why This Matters

Under load, exact totals add work that GeoServer is either handling more efficiently or avoiding on the hot path.

For Honua's benchmark workload:
- every OGC page asks for only `100` features
- the client validates only the returned page contents
- exact `numberMatched` is not needed to validate correctness of the returned page

But Honua still pays for it on every request.

This matches the observed result shape:
- Honua is strong on selective reads
- Honua degrades much more sharply than GeoServer as mixed concurrent load rises

## Recommended Honua Changes

### P0: Add an OGC count policy for items responses

Add a server-level or service-level policy for OGC API Features items:

- `exact`
  - current behavior
- `omit_when_expensive`
  - do not compute `numberMatched` on the hot path
- `estimate`
  - return an approximate count where acceptable

Important note:
- OGC API Features allows `numberMatched` to be omitted when it is not practical to compute
- this is a standards-compatible optimization, not a benchmark-only shortcut

### P0: Stop using `COUNT(*) OVER()` for paginated hot reads when exact totals are disabled

For paginated OGC reads where exact totals are not required:

- fetch `LIMIT + 1` rows
- trim to `LIMIT`
- derive `hasMoreResults` from the extra row
- return `numberReturned`
- omit `numberMatched`

That removes the window count from the hottest query shape in this benchmark.

### P1: Keep exact counts for paths that genuinely need them

Exact totals should stay available for:
- WFS `resultType=hits`
- admin/export/reporting paths
- any explicitly configured service that values exact counts over throughput

### P1: Make the policy per service

This should be configurable per Honua service so different products can choose:
- low-latency interactive browsing
- balanced public API
- exact-count analytical/export behavior

This aligns with [honua-service-layer-profiles-ticket.md](./honua-service-layer-profiles-ticket.md).

## Nice-To-Have Follow-Ups

- investigate whether item-level `links` generation can be disabled on collection item pages
- benchmark `Tracing__Enabled=false` as a separate benchmark-profile toggle, not as a default claim
- add a count-policy dimension to future Honua benchmarking once the product supports it

## Definition Of Done

- Honua exposes an OGC items count policy that can omit exact `numberMatched`
- paginated OGC reads no longer force `COUNT(*) OVER()` when that policy is disabled
- GeoBench rerun shows a material mixed-load improvement on Honua without semantic failures
