# GeoBench Matrix Status

Current authoritative matrix status for the rerun campaign on the current local harness.

## Authoritative Reports

| Family | Row | Servers | Status | Report | Notes |
| --- | --- | --- | --- | --- | --- |
| Common Standards: Feature | `attribute-filter` | Honua, GeoServer, QGIS | Complete | `results/20260328-204508/report.md` | Fresh 3-server rerun on the current deterministic harness |
| Common Standards: Feature | `spatial-bbox` | Honua, GeoServer, QGIS | Complete | `results/20260328-212511/report.md` | Fresh 3-server rerun on the current deterministic harness |
| Common Standards: Feature | `concurrent` | Honua, GeoServer, QGIS | Complete | `results/20260328-214959/report.md` | Fresh 3-server rerun on the current deterministic harness; QGIS had 1 failed request but remained below the test threshold |
| Common Standards: Raster | `wms-getmap` | Honua, GeoServer, QGIS | Complete | `results/20260329-090404/report.md` | Fresh 3-server rerun pinned to merged Honua trunk image `honua-geobench:trunk-20260329`; Honua leads on small, medium, and large |
| Supplemental Native Protocols | `geoservices-query` | Honua, GeoServer GSR | Complete | `results/20260329-093029/report.md` | Fresh rerun pinned to merged Honua trunk image and GeoServer `2.28.x` + `gsr`; Honua wins small and large, GeoServer still leads on medium |
| Secondary Standards | `wfs-getfeature` | Honua, GeoServer | Complete | `results/20260329-094824/report.md` | Fresh rerun pinned to merged Honua trunk image `honua-geobench:trunk-20260329`; Honua leads on base, small, medium, and large |
| Supplemental Native Protocols | `geoservices-query` large seed sweep | Honua, GeoServer GSR | Complete | `results/20260329-104204-geoservices-query-sweep/report.md` | Three-salt large-bbox sweep on the pinned merged-trunk image; GeoServer retains the better median and p95, and the row is strongly seed-sensitive |

## Pending Canonical Reruns

| Family | Row | Target Servers | Status | Notes |
| --- | --- | --- | --- | --- |
| — | — | — | None | Current reduced canonical matrix reruns are complete |

## Not Part of the Canonical Matrix

| Row | Status | Notes |
| --- | --- | --- |
| `geoservices-query-diagnostics` | Diagnostic only | Useful for optimization work, not for the publishable matrix |
| `geoservices-export` | Supplemental single-server | Honua-only native raster track |
| `wms-reprojection` | Initial validation complete | Implemented and smoke-benchmarked in `results/20260329-124605/report.md`; not yet part of the reduced canonical matrix |
| `wms-getfeatureinfo` | Not rerun yet | Secondary row, not part of the current completed set |
| WFS filtered queries | Not implemented as a canonical row yet | Still called out in methodology as secondary work |
| WMTS / WCS / `MapServer/identify` | Not rerun yet | Still missing from the current authoritative matrix |

## Discarded Runs

| Results Dir | Reason |
| --- | --- |
| `results/20260328-210952` | Partial `spatial-bbox` run aborted by a transient GeoServer startup miss before the 3-server row completed |
