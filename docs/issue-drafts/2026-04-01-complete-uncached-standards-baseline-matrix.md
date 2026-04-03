# Complete Uncached Standards Baseline Matrix And Formalize Cache Tiers

## Summary

As of April 1, 2026, the GeoBench baseline standards matrix is not fully complete or fully
publishable. The primary/common baseline rows are mostly in place, but several secondary-standard
rows remain incomplete, blocked, or methodologically weak.

This issue tracks the remaining work needed to finish the uncached standards baseline and keep it
separate from warm-tile-cache and other cache-assisted tracks.

## Why

- We now have an explicit cache-tier taxonomy in the methodology:
  - `baseline`
  - `warm service state`
  - `warm tile cache`
  - `cache-assisted product track`
- The matrix still contains unfinished rows that should not be treated as authoritative until the
  baseline standards matrix is cleaned up.
- The current response-shape and comparability audits surfaced real anomalies that should be fixed
  before publication.

## Current Status

### Complete and publishable baseline/common rows

- `attribute-filter`
- `spatial-bbox`
- `concurrent`
- `wms-getmap`
- `wms-reprojection`
- `wfs-getfeature`
- `wfs-filtered` on the shared Honua/GeoServer WFS 2.0 + FES 2.0 profile

### Not yet complete or publishable

- `wms-filtered`
  - Runnable, but short validation flagged suspicious scenario collapse on Honua.
  - Audit report: `results/20260331-233312/report.md`
- `wms-getfeatureinfo`
  - Implemented, but not comparable because Honua currently returns HTTP 405.
  - Blocking report: `results/20260331-220126/report.md`
- `wmts`
  - Runnable after fixing the GeoServer WMTS gridset mismatch.
  - Must remain a `warm tile cache` row, not a baseline render row.
  - Validation report: `results/20260331-233223/report.md`
- `wcs`
  - Still experimental because the harness is not self-contained.
  - Requires a published benchmark coverage instead of a manually supplied coverage id.
- `geoservices-identify`
  - Runnable, but short validation returned an empty sample in the audit.
  - Needs guaranteed-hit sample points before publication.
  - Validation report: `results/20260331-233500/report.md`

## Findings From Short Validation Runs

### `wms-filtered`

- Honua returned the same raster hash for all three sampled filter variants in the audit.
- This does not prove the row is wrong, but it is suspicious enough that the row should not be
  called authoritative until the behavior is explained or fixed.

### `wmts`

- The harness originally used `EPSG:3857` for GeoServer WMTS requests.
- GeoServer advertised and accepted `EPSG:900913` for the benchmark layer.
- The row now runs end to end, but it should be labeled and reported only as a warm-tile-cache row.

### `geoservices-identify`

- The audit sample returned an empty `results` payload.
- The benchmark script itself runs, but the audit indicates the sample geometry is not a
  guaranteed-hit point.

## Scope

### Baseline standards work

- Finish the uncached standards baseline rows that are supposed to be publishable.
- Keep blocked or experimental rows clearly labeled.
- Do not mix warm-tile-cache or cache-assisted rows into the baseline standards matrix.

### Cache-tier work

- Make cache tier a first-class result/report field.
- Ensure every published row declares its cache tier.
- Keep `wmts` in `warm tile cache`.
- Keep `wms-getmap`, feature, and query rows in `baseline` / `warm service state` unless a
  separate cache-assisted track is explicitly introduced.

## Tasks

- Add `cache_tier` as a first-class field in run metadata and generated reports.
- Investigate and fix or explain Honua `wms-filtered` scenario collapse.
- Make `geoservices-identify` use guaranteed-hit sample points for audit and validation.
- Make `wcs` self-contained by publishing a known benchmark coverage in the GeoServer adapter.
- Re-run canonical 5-run benchmarks for:
  - `wms-filtered`
  - `wmts`
  - `geoservices-identify`
  - `wcs` only if the self-contained coverage work is complete
- Update `docs/matrix-status.md` after canonical reruns.

## Acceptance Criteria

- Every published row declares its cache tier.
- No report table mixes `baseline`, `warm service`, `warm tile cache`, or `cache-assisted` rows.
- `wms-filtered` has an explained and validated response-shape story across Honua and GeoServer.
- `wmts` is reported explicitly as a warm-tile-cache row and no longer presented as a baseline row.
- `geoservices-identify` audit samples are non-empty for canonical validation requests.
- `wcs` either:
  - becomes self-contained and rerunnable, or
  - remains explicitly labeled experimental and excluded from the authoritative baseline matrix.

## Notes

- Local Docker remains useful for reproducible comparative work, but not for claiming exact cloud
  behavior.
- Redis, GeoWebCache blobstores, MinIO, or CDN-like layers should be added only as separate
  cache-assisted tracks, not folded into the baseline standards matrix.
