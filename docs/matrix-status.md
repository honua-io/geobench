# GeoBench Matrix Status

Current authoritative matrix status for the rerun campaign on the current local harness.

## Authoritative Reports

| Family | Row | Servers | Status | Report | Notes |
| --- | --- | --- | --- | --- | --- |
| Common Standards: Feature | `attribute-filter` | Honua, GeoServer, QGIS | Complete | `results/20260328-204508/report.md` | Fresh 3-server rerun on the current deterministic harness |
| Common Standards: Feature | `spatial-bbox` | Honua, GeoServer, QGIS | Complete | `results/20260328-212511/report.md` | Fresh 3-server rerun on the current deterministic harness |
| Common Standards: Feature | `concurrent` | Honua, GeoServer, QGIS | Complete | `results/20260328-214959/report.md` | Fresh 3-server rerun on the current deterministic harness; QGIS had 1 failed request but remained below the test threshold |
| Common Standards: Raster | `wms-getmap` | Honua, GeoServer, QGIS | Complete | `results/20260329-090404/report.md` | Fresh 3-server rerun pinned to merged Honua trunk image `honua-geobench:trunk-20260329`; Honua leads on small, medium, and large |
| Common Standards: Raster | `wms-reprojection` | Honua, GeoServer, QGIS | Complete | `results/20260331-212245/report.md` | Fresh 3-server rerun on the current deterministic harness |
| Supplemental Native Protocols | `geoservices-query` | Honua, GeoServer GSR | Complete | `results/20260329-093029/report.md` | Fresh rerun pinned to merged Honua trunk image and GeoServer `2.28.x` + `gsr`; Honua wins small and large, GeoServer still leads on medium |
| Secondary Standards | `wfs-getfeature` | Honua, GeoServer | Complete | `results/20260329-094824/report.md` | Fresh rerun pinned to merged Honua trunk image `honua-geobench:trunk-20260329`; Honua leads on base, small, medium, and large |
| Secondary Standards | `wfs-filtered` | Honua, GeoServer | Complete | `results/20260331-214615/report.md` | Honua-GeoServer filtered query rerun (equality, range, like) |
| Secondary Standards | `wms-filtered` | Honua, GeoServer | Pending | — | Added suite and harness support |
| Secondary Standards | `wmts` | GeoServer | Pending | — | Added suite and harness support as an explicit warm-tile-cache row |
| Secondary Standards | `wcs` | GeoServer | Runnable | `warm_service` | Self-contained coverage is now provisioned by the GeoServer adapter; short smoke pass validated |
| Supplemental Native Protocols | `geoservices-query` large seed sweep | Honua, GeoServer GSR | Complete | `results/20260329-104204-geoservices-query-sweep/report.md` | Three-salt large-bbox sweep on the pinned merged-trunk image; GeoServer retains the better median and p95, and the row is strongly seed-sensitive |
| Supplemental Native Protocols | `geoservices-export` | Honua | Complete | `results/20260331-222523/report.md` | Fresh Honua-only rerun on the current deterministic harness |
| Supplemental Native Protocols | `geoservices-identify` | Honua, GeoServer GSR | Pending | — | Added suite and harness support |

## Pending Canonical Reruns

| Family | Row | Target Servers | Status | Notes |
| --- | --- | --- | --- | --- |
| Secondary Standards | `wms-filtered` | Honua, GeoServer | Pending | Harness implemented; awaiting canonical rerun on the updated warmup policy |
| Secondary Standards | `wmts` | GeoServer | Pending | Harness implemented as an explicit warm-tile-cache row; awaiting canonical rerun |
| Secondary Standards | `wcs` | GeoServer | Runnable | Self-contained benchmark coverage now uploads automatically; canonical 5-run validation still pending |
| Supplemental Native Protocols | `geoservices-identify` | Honua, GeoServer GSR | Pending | Harness implemented; awaiting canonical rerun |

## Not Part of the Canonical Matrix

| Row | Status | Notes |
| --- | --- | --- |
| `geoservices-query-diagnostics` | Diagnostic only | Useful for optimization work, not for the publishable matrix |
| `wms-getfeatureinfo` | Implemented, but blocked on Honua | Reran in `results/20260331-220126/report.md`; Honua returns HTTP 405 (`Method Not Allowed`) for `GetFeatureInfo`, so this row is not currently comparable |

## Discarded Runs

| Results Dir | Reason |
| --- | --- |
| `results/20260328-210952` | Partial `spatial-bbox` run aborted by a transient GeoServer startup miss before the 3-server row completed |

## 2026-04-02 update: GeoServer `wms-filtered` remains blocked

- Canonical rerun after fixing the `PropertyIsLike` `escape` attribute still failed on GeoServer under sustained load.
- Canonical artifact: `results/20260402-130945/report.md`
- Short repro artifact: `results/20260402-130553/report.md`
- Response-shape audit remained valid for `equality`, `range`, and `like`, so request construction is not the main blocker.
- During failure, the GeoServer JVM heap sat near full at roughly `1046560K / 1048576K`, and container logs reported `java.lang.OutOfMemoryError: Java heap space`.
- Matrix decision: keep `wms-filtered` blocked in the uncached baseline matrix under the current GeoServer 1 GiB heap profile.
- Any rerun with a larger or tuned GeoServer heap must be published as a separate tuned-memory track, not silently merged into the baseline matrix.
