# GeoBench Feature Map

This map summarizes source-backed benchmark capabilities in this repository.

## Implemented Surfaces

- Vendor-neutral benchmark harness for Honua Server, GeoServer, and QGIS Server.
- Common feature API tracks: attribute filters, spatial bbox queries, concurrent workloads, and row-shape checks.
- Common raster API tracks: WMS `GetMap`, WMS reprojection, WMS `GetFeatureInfo`, WMTS tiles, and WCS `GetCoverage`.
- Secondary standards and native tracks: WFS filtered rows, GeoServices `FeatureServer/query`, `MapServer/identify`, and `MapServer/export`.
- Reproducible datasets, system cards, run ledgers, result reports, fairness audits, and response-shape audits.
- Scripts for benchmark execution, report generation, fairness review, matrix status, and diagnostic reruns.

## Source Evidence

- Benchmark orchestration: `scripts/run-benchmark.sh`
- Reporting and audit helpers: `scripts/generate-report.py`, `scripts/audit-fairness.py`
- Adapter and server-specific execution code: `adapters/`, `src/`
- Published run artifacts and ledgers: `results/`
- Matrix status and planning docs: `docs/matrix-status.md`, `docs/*ticket*.md`

## Release Notes

GeoBench is useful for release proof, but headline claims should stay tied to pinned images, published result directories, and the fairness audit output. The README snapshot already carries the current caveat that some rows have response-shape or metadata drift that must be disclosed in public claims.
