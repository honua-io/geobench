# Ticket: Honua Performance Refactor

## Summary

Create one coherent Honua performance program across OGC API Features, WFS, WMS, and GeoServices
REST so Honua is competitive or clearly better than GeoServer on the protocols that matter.

This is not a one-knob tuning task anymore. The benchmark evidence and source inspection now point
to a broader refactor:

- split counted and uncounted query paths cleanly
- reduce per-row attribute and geometry conversion overhead
- avoid full materialization where streaming is possible
- introduce service/layer-level performance profiles
- build a lighter raster path instead of trying to SQL-tune away renderer costs

This ticket is the umbrella for the earlier OGC load and service/layer profile tickets.

Related notes:

- [docs/geoserver-honua-performance-investigation.md](./geoserver-honua-performance-investigation.md)
- [docs/honua-ogc-load-optimization-ticket.md](./honua-ogc-load-optimization-ticket.md)
- [docs/honua-service-layer-profiles-ticket.md](./honua-service-layer-profiles-ticket.md)

## Goals

- make the benchmark comparison defensible and fair
- explain the remaining protocol-by-protocol performance variation
- close the gaps where Honua still lags GeoServer
- make performance behavior tunable per service and per layer instead of globally

## What Already Landed

These changes should be treated as part of this refactor baseline, not separate efforts:

- benchmark-aligned expression indexes for the Honua benchmark feature store
- OGC `numberMatched` policy and no-count paged OGC path
- OGC payload cleanup to remove the large default response bloat
- metadata/catalog caching improvements on the hot OGC path
- quieter benchmark logging and production-mode benchmark config
- benchmark harness fairness fixes:
  - no unconditional OGC `sortby`
  - cleaner payload-shape auditing
  - cleaner protocol-matrix split between common and native paths

These changes were useful, but they did not remove the whole gap.

## Best Current Explanation

### Cross-cutting

Honua still has more hot-path app work than GeoServer:

- the shared limited-query store path still carries count work in places that do not always need it
- the shared feature readers deserialize JSON attributes per row
- protocol handlers often rebuild response objects after the store already returned features
- some handlers still materialize full feature arrays before writing the response

GeoServer benefits from:

- a mature GeoTools JDBC pushdown path
- leaner streaming-oriented response writers
- a typed benchmark table with aligned indexes
- a more optimized raster renderer stack

### OGC API Features

Honua is now much more competitive, but the remaining lagging cases are still likely explained by:

- attribute-bag decode and property rebuilding
- geometry conversion overhead
- generic storage shape compared with GeoServer serving the typed benchmark table directly

### WFS

This is still likely one of Honua's weakest paths because:

- WFS currently exact-counts before building paged plans
- then it queries again to fetch data
- then it materializes and reformats the response

### WMS / Raster

This is likely the largest structural gap:

- GeoServer reduces the query before draw based on bbox/style/rules and uses `StreamingRenderer`
- Honua currently queries features, materializes them, converts WKB to Skia geometry, evaluates
  style filters in the render loop, and then encodes PNG

### GeoServices REST / FeatureServer

This is likely Honua's best protocol family because the native query path already has:

- streaming support
- `LIMIT + 1` semantics for `hasMoreResults`
- native binary/export-oriented formats

But it is still not the shared path that OGC, WFS, and WMS currently depend on.

## Refactor Scope

### 1. Split counted and uncounted query paths

Refactor the shared feature-store path so protocols can explicitly choose:

- exact count required
- count omitted
- count estimated

This should remove accidental `COUNT(*) OVER()` / exact-count behavior from hot paths that only
need page contents or `hasMoreResults`.

Priority:

- OGC items
- WFS paged results
- WMS / MapServer reads
- FeatureServer JSON paths that still use the counted shared path

### 2. Reduce per-row app-layer work

Refactor the common feature-read pipeline to reduce:

- JSON attribute deserialization per row
- property dictionary rebuilding
- redundant ID duplication
- repeated geometry conversion between storage, NTS, GeoJSON, and renderer formats

Possible directions:

- typed hot-field projection for common benchmark fields
- protocol-specific lightweight row readers
- direct encoded-geometry or direct response writing where practical

### 3. Add explicit service/layer performance profiles

Support named performance profiles at the service level with optional layer override.

Candidate profiles:

- `latency`
- `balanced`
- `throughput`
- later: `map`
- later: `export`

Profiles should control:

- count policy
- default page size / transfer behavior
- payload defaults
- cache strategy
- backing source choice
- index and sort strategy

### 4. Refactor raster rendering separately from feature-query tuning

Do not treat raster as “just another SQL optimization problem.”

Raster work needs its own pass:

- query only what the current style and viewport need
- avoid rescanning the same feature set for each style layer where possible
- reduce WKB-to-Skia conversion overhead
- move style filtering and simplification out of the deepest hot loop where practical
- measure query time, geometry conversion time, draw time, and encode time separately

### 5. Finish protocol-matrix benchmarking and instrumentation

Needed to make the refactor credible:

- fix the Honua adapter/bootstrap drift so fresh isolated WFS runs work again
- complete current WFS and raster reruns on patched builds
- keep response-shape audit in the loop for every protocol
- add protocol-local timing instrumentation to confirm which stage actually moved

## Proposed Work Breakdown

### P0: Shared Query Semantics

- create explicit counted vs uncounted query APIs in the feature store
- remove inherited count work from raster and lightweight paged reads
- unify `hasMoreResults` behavior around `LIMIT + 1` where exact totals are not needed

Expected impact:

- high on WFS
- medium to high on OGC mixed load
- medium on WMS/MapServer if those handlers currently inherit counted queries

### P1: Feature Response Fast Paths

- add lighter row readers for common feature outputs
- reduce per-feature property rebuilding
- reduce geometry conversion churn
- keep payload shape benchmark-safe

Expected impact:

- medium on OGC
- medium to high on WFS
- medium on FeatureServer JSON

### P2: Raster Path Refactor

- add timing splits to MapServer/WMS
- reduce per-style repeated work
- reduce per-feature conversion overhead
- evaluate whether a style-aware query prepass is needed

Expected impact:

- high on WMS/GetMap
- high on MapServer/export

### P3: Service/Layer Profiles

- formalize profiles
- expose them in service/layer config
- make benchmark output label the active profile

Expected impact:

- medium product value
- high long-term maintainability
- lets Honua optimize by use case without forcing one global tradeoff

## Effort Estimate

### If the goal is only common feature-path refactor

For one strong engineer working full-time:

- `2-3 weeks` to refactor the counted/uncounted feature-store path and protocol handlers for OGC
  and WFS, rerun the fair benchmarks, and stabilize the harness

This is the shortest plausible path to a meaningful win on common feature protocols.

### If the goal is the full protocol refactor

For one strong engineer working full-time:

- `6-10 weeks`

Rough split:

- shared query semantics and protocol handler cleanup: `1.5-2.5 weeks`
- OGC/WFS feature fast paths and validation: `1-2 weeks`
- raster renderer/query refactor: `2-4 weeks`
- service/layer profile design and wiring: `1-2 weeks`
- reruns, payload audit, regression cleanup: `0.5-1 week`

### Risk Factors

- benchmark/bootstrap drift in the latest Honua image
- response-shape regressions while optimizing hot paths
- raster work may hide a larger renderer architecture gap than current code inspection suggests
- some wins may require changes in both Honua server code and benchmark-layer publication strategy

## Acceptance Criteria

- a single ticketed plan exists for Honua performance work across all benchmarked protocols
- counted vs uncounted query semantics are explicit in the store and protocol handlers
- current common OGC and WFS paths no longer do avoidable exact count work on hot reads
- Honua raster path has stage-level timing and at least one material hot-loop improvement
- service/layer performance profiles are defined, even if only two are implemented initially
- benchmark reports can identify which Honua profile/configuration was used
- response-shape diffs remain documented so no performance claim depends on returning less data

## Recommendation

Treat this as one umbrella refactor with two delivery milestones:

1. feature protocols first
2. raster protocols second

That keeps the work shippable while still preserving the larger architecture plan.
