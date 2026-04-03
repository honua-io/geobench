# Session Handoff: 2026-03-26

## State

- Workspace: `/home/makani/geobench`
- No GeoBench benchmark containers are currently running.
- Honua PR:
  - PR: `https://github.com/honua-io/honua-server/pull/616`
  - Branch: `fix/614-honua-performance-refactor`
  - Current pushed head: `1f24c2a`
- `gh pr checks 616 --repo honua-io/honua-server` last showed all checks green, but the output appeared to reflect the previous completed run and may lag the latest push.

## Important Local GeoBench Changes

- Added deterministic request generation in:
  - `src/tests/deterministic.js`
  - `src/tests/helpers.js`
  - `src/tests/attribute-filter.js`
  - `src/tests/spatial-bbox.js`
  - `src/tests/concurrent.js`
  - `src/tests/wfs-helpers.js`
  - `src/tests/wfs-getfeature.js`
  - `src/tests/raster-helpers.js`
  - `src/tests/wms-getmap.js`
  - `src/tests/geoservices-export.js`
- Split warmup execs away from benchmark execs to prevent k6 submetric collapse in:
  - `src/tests/attribute-filter.js`
  - `src/tests/spatial-bbox.js`
  - `src/tests/concurrent.js`
  - `src/tests/wfs-getfeature.js`
  - `src/tests/wms-getmap.js`
  - `src/tests/geoservices-export.js`
- Explicit raster default styles are provisioned in:
  - `adapters/honua/setup.sh`
  - `adapters/geoserver/setup.sh`
  - `adapters/geoserver/geobench_simple_point.sld`
  - `adapters/qgis/geobench.qgs`

## Trustworthy Latest Results

### WMS 3-way deterministic-style comparison

Directory:
- `/home/makani/geobench/results/20260326-130232`

Report:
- `/home/makani/geobench/results/20260326-130232/report.md`

Headline:
- `small`: Honua `707.9 req/s`, GeoServer `137.9`, QGIS `0.8`
- `medium`: Honua `9.8 req/s`, GeoServer `20.7`, QGIS `0.8`
- `large`: Honua `19.8 req/s`, GeoServer `6.2`, QGIS `0.8`

Interpretation:
- On the deterministic WMS harness, Honua wins `small` and `large`.
- GeoServer still wins `medium`.
- Raster payloads for the same small map sample are still different:
  - Honua `816` bytes
  - GeoServer `2674`
  - QGIS `720`

### Honua-only WMS after latest renderer tuning

Directory:
- `/home/makani/geobench/results/20260326-133212`

Report:
- `/home/makani/geobench/results/20260326-133212/report.md`

Headline:
- `small`: `1104.3 req/s`, p95 `4.1 ms`
- `medium`: `13.7 req/s`, p95 `302.3 ms`
- `large`: `18.7 req/s`, p95 `211.0 ms`

Interpretation:
- Latest Honua renderer heuristics improved `medium` versus the deterministic 3-way run baseline, but not enough to beat GeoServer’s `20.7 req/s` on `medium`.

## Partial / Non-publishable Runs

### `/home/makani/geobench/results/20260326-134044`

- Started before the warmup-exec split.
- Do not use for comparison.
- Problem:
  - `attribute-filter` equality completed, but `range/like` submetrics and later suites are not trustworthy for publication because warmup/shared exec naming was still contaminating k6 submetrics.

### `/home/makani/geobench/results/20260326-135253`

- Started after the warmup-exec split, but intentionally aborted.
- Directory only contains:
  - `honua-attribute-filter-run1.json`
  - `honua-response-shapes.json`
- Useful data inside it:
  - Honua deterministic equality-only slice completed before abort:
    - `http_reqs{query_type:equality}` count `180430`
    - rate `1071.3592037172639`
    - p95 `5.6324650999999974 ms`
- `range` and `like` are zero because the run was stopped before those phases started.

## Honua-Server Raster Work Pushed

Pushed on PR branch:
- `1f24c2a Optimize raster point rendering heuristics`

This includes:
- batched circle-style point rendering
- hybrid fallback to per-point circles when batching is a bad fit
- shared raster/export heuristic updates

## Recommended Next Steps

1. Rerun deterministic `attribute-filter` only:
   - `HONUA_PORT=18082 HONUA_IMAGE=honua-geobench:pr616-raster8 TESTS='attribute-filter' SERVERS='honua geoserver' ./scripts/run-benchmark.sh`
2. If that is clean, rerun deterministic `spatial-bbox` and `concurrent`:
   - `HONUA_PORT=18082 HONUA_IMAGE=honua-geobench:pr616-raster8 TESTS='spatial-bbox concurrent' SERVERS='honua geoserver' ./scripts/run-benchmark.sh`
3. Rerun deterministic WFS after the same fairness fixes:
   - `HONUA_PORT=18082 HONUA_IMAGE=honua-geobench:pr616-raster8 TESTS='wfs-getfeature' SERVERS='honua geoserver' ./scripts/run-benchmark.sh`
4. If medium WMS is still behind after feature reruns:
   - continue tuning point batching heuristics in:
     - `/tmp/honua-server-perf-pr/src/Honua.Server/Features/MapServer/Rendering/SkiaMapRenderer.cs`
     - `/tmp/honua-server-perf-pr/src/Honua.Server/Features/MapServer/MapServerRequestHandlers.Export.cs`

## Notes

- The earlier fairness bug was real: several suites were still using `Math.random()`, which meant different servers could see different request streams. That is now fixed locally in GeoBench.
- The warmup/submetric collision was also real: shared exec names between warmup and measured scenarios caused broken submetrics. That is now fixed locally in GeoBench.
