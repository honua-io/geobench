# GeoServer vs Honua Performance Investigation

## Purpose

Capture the current explanation for benchmark variation between GeoServer and Honua, with emphasis on:

- what is proven from code and benchmark artifacts
- what likely explains the current results
- what is still an open measurement problem

This note is intentionally protocol-by-protocol so we do not collapse all behavior into one headline claim.

## Current Benchmark Context

Latest fair common OGC feature comparison:
- [results/20260325-131101/report.md](../results/20260325-131101/report.md)

Key shape from that run:
- Honua wins `equality`, `like`, `large bbox`, and mixed load at `10` and `100` VUs
- GeoServer wins `range` throughput, `small bbox`, `medium bbox`, and mixed load at `50` VUs
- Honua payload bloat is mostly fixed in current OGC output

Important constraint:
- We do **not** yet have published Honua vs GeoServer WFS or WMS benchmark runs on the current patched builds.
- The protocol findings below therefore combine measured GeoBench behavior where available with direct code inspection of both servers.
- A fresh March 25 WFS rerun was attempted, but the current `honuaio/honua-server:latest` image now boots with no admin services at all. GeoBench's Honua adapter currently assumes a preexisting `default` service, so the fresh WFS measurement is blocked by adapter/bootstrap drift rather than by the benchmark test itself.

## Proven Cross-Cutting Differences

### 1. GeoServer OGC API Features is a thin wrapper over WFS/GetFeature

GeoServer's OGC API Features handler builds a WFS `GetFeatureRequest` and then delegates to the existing WFS implementation:
- [/tmp/geoserver/src/extension/ogcapi/ogcapi-features/src/main/java/org/geoserver/ogcapi/v1/features/FeatureService.java](/tmp/geoserver/src/extension/ogcapi/ogcapi-features/src/main/java/org/geoserver/ogcapi/v1/features/FeatureService.java)
- [/tmp/geoserver/src/extension/ogcapi/ogcapi-features/src/main/java/org/geoserver/ogcapi/v1/features/FeaturesGetFeature.java](/tmp/geoserver/src/extension/ogcapi/ogcapi-features/src/main/java/org/geoserver/ogcapi/v1/features/FeaturesGetFeature.java)

Why it matters:
- GeoServer is not maintaining a separate OGC query engine here.
- OGC API benefits from the same mature WFS/JDBC/PostGIS path GeoServer already uses.

### 2. GeoTools pushes sort/offset/limit into JDBC when possible

GeoTools' JDBC feature source explicitly advertises support for:
- sorting when the property is sortable
- offset when the dialect supports limit/offset
- limit when the dialect supports limit/offset

Relevant code:
- [/tmp/geotools/modules/library/jdbc/src/main/java/org/geotools/jdbc/JDBCQueryCapabilities.java](/tmp/geotools/modules/library/jdbc/src/main/java/org/geotools/jdbc/JDBCQueryCapabilities.java)
- [/tmp/geotools/modules/library/jdbc/src/main/java/org/geotools/jdbc/JDBCFeatureSource.java](/tmp/geotools/modules/library/jdbc/src/main/java/org/geotools/jdbc/JDBCFeatureSource.java)

Why it matters:
- GeoServer can keep `filter + sort + limit + offset` down in SQL on the happy path.
- If a filter cannot be fully pushed down, GeoTools disables native paging and does the safe fallback in memory. That makes its behavior conservative rather than silently wrong.

Additional evidence:
- `JDBCFeatureSource` only applies in-memory offset/max-feature skipping when post-filtering is required:
  - [/tmp/geotools/modules/library/jdbc/src/main/java/org/geotools/jdbc/JDBCFeatureSource.java](/tmp/geotools/modules/library/jdbc/src/main/java/org/geotools/jdbc/JDBCFeatureSource.java)

Why it matters:
- GeoServer gets native paging when it safely can.
- When it cannot, it falls back explicitly instead of paying hybrid costs on every request.

### 3. GeoServer writes GeoJSON by streaming feature collections to the output writer

GeoServer's GeoJSON response path iterates the feature collection and writes directly to the response writer:
- [/tmp/geoserver/src/wfs-core/src/main/java/org/geoserver/wfs/json/GeoJSONGetFeatureResponse.java](/tmp/geoserver/src/wfs-core/src/main/java/org/geoserver/wfs/json/GeoJSONGetFeatureResponse.java)
- [/tmp/geoserver/src/main/src/main/java/org/geoserver/json/GeoJSONFeatureWriter.java](/tmp/geoserver/src/main/src/main/java/org/geoserver/json/GeoJSONFeatureWriter.java)

Why it matters:
- GeoServer is not rebuilding a generic attribute bag and then serializing it again per feature in the OGC/WFS output path.
- That keeps the app-layer response path relatively lean.

### 4. Honua still pays a generic attribute-bag cost per feature

Honua's Postgres feature readers read `attributes` as a JSON string, deserialize it, convert values, and then attach `objectid`:
- [/home/makani/honua-server/src/Honua.Postgres/Features/FeatureStore/Services/FeatureDataAccess.Readers.cs](/home/makani/honua-server/src/Honua.Postgres/Features/FeatureStore/Services/FeatureDataAccess.Readers.cs)

Then OGC and WFS rebuild response properties from that attribute dictionary:
- [/home/makani/honua-server/src/Honua.Server/Features/OgcFeatures/OgcFeaturesQueryHandler.cs](/home/makani/honua-server/src/Honua.Server/Features/OgcFeatures/OgcFeaturesQueryHandler.cs)
- [/home/makani/honua-server/src/Honua.Server/Features/Wfs20/Services/Wfs20Handler.cs](/home/makani/honua-server/src/Honua.Server/Features/Wfs20/Services/Wfs20Handler.cs)

Why it matters:
- Even after the SQL/index fixes, Honua still has more app-layer per-row work than GeoServer on common feature outputs.
- This is one of the strongest explanations for the remaining cases where Honua lags despite the DB path being much healthier now.

Additional evidence:
- Honua's OGC handler still materializes arrays of `GeoJsonFeature` and serializes them after rebuilding properties:
  - [/home/makani/honua-server/src/Honua.Server/Features/OgcFeatures/OgcFeaturesQueryHandler.cs](/home/makani/honua-server/src/Honua.Server/Features/OgcFeatures/OgcFeaturesQueryHandler.cs)
- Honua's WFS JSON/GML handlers similarly build full feature collections after the plan/count phase:
  - [/home/makani/honua-server/src/Honua.Server/Features/Wfs20/Services/Wfs20Handler.cs](/home/makani/honua-server/src/Honua.Server/Features/Wfs20/Services/Wfs20Handler.cs)

### 6. Honua's shared limited-query store path is still heavier than it looks

Honua's store layer still carries count work on many limited queries:
- unlimited queries do a separate `COUNT(*)` plus `SELECT`
- limited "optimized" queries use `COUNT(*) OVER()` in the shared SQL builder

Relevant code:
- [/home/makani/honua-server/src/Honua.Postgres/Features/FeatureStore/PostgresFeatureStore.cs](/home/makani/honua-server/src/Honua.Postgres/Features/FeatureStore/PostgresFeatureStore.cs)
- [/home/makani/honua-server/src/Honua.Postgres/Features/FeatureStore/Services/FeatureQueryBuilder.Build.cs](/home/makani/honua-server/src/Honua.Postgres/Features/FeatureStore/Services/FeatureQueryBuilder.Build.cs)
- [/home/makani/honua-server/src/Honua.Postgres/Features/FeatureStore/Services/FeatureQueryBuilder.EncodedFormats.cs](/home/makani/honua-server/src/Honua.Postgres/Features/FeatureStore/Services/FeatureQueryBuilder.EncodedFormats.cs)

Why it matters:
- Honua can still pay exact-count or window-count cost on protocol paths that do not actually need totals.
- This likely affects not just WFS and default OGC behavior, but also raster paths that call the same `QueryAsync(...)` machinery with a limit.

### 5. GeoServer currently serves the typed benchmark table directly

GeoServer is published directly against `bench_points`:
- [adapters/geoserver/setup.sh](/home/makani/geobench/adapters/geoserver/setup.sh)

The benchmark dataset gives that table exactly aligned indexes:
- [data/small/generate.py](/home/makani/geobench/data/small/generate.py)

Honua still serves through `public.features` with JSON-backed attributes:
- [adapters/honua/setup.sh](/home/makani/geobench/adapters/honua/setup.sh)

Why it matters:
- GeoServer starts from a friendlier storage shape for this benchmark.
- Honua can compensate with expression indexes, and we already added some, but the underlying row shape is still more generic.

## Protocol Findings

## OGC API Features

### What is proven

- GeoServer OGC API requests reuse WFS/GetFeature and GeoTools JDBC pushdown.
- Honua OGC requests use a separate handler and a separate response assembly path.
- Honua's OGC path now supports omitting exact `numberMatched` on the hot path:
  - [/home/makani/honua-server/src/Honua.Server/Features/OgcFeatures/OgcFeaturesOptions.cs](/home/makani/honua-server/src/Honua.Server/Features/OgcFeatures/OgcFeaturesOptions.cs)
  - [/home/makani/honua-server/src/Honua.Server/Features/OgcFeatures/OgcFeaturesQueryHandler.cs](/home/makani/honua-server/src/Honua.Server/Features/OgcFeatures/OgcFeaturesQueryHandler.cs)
- Honua's paged no-count path uses `LIMIT + 1` semantics via `QueryPageAsync` and `QueryGeoJsonPageAsync`:
  - [/home/makani/honua-server/src/Honua.Postgres/Features/FeatureStore/PostgresFeatureStore.cs](/home/makani/honua-server/src/Honua.Postgres/Features/FeatureStore/PostgresFeatureStore.cs)

### What still likely explains lagging OGC cases

Where Honua still lags GeoServer on the common feature track, the remaining likely causes are:

- app-layer attribute JSON deserialization per row
- per-feature geometry conversion work in the response layer
- higher response assembly overhead in Honua than GeoServer's streaming writer path
- remaining storage-shape disadvantage from JSON-backed attributes vs typed columns

### What no longer looks like the main cause

- unconditional payload bloat from OGC links and duplicate ids
  - largely fixed
- mandatory exact count on OGC items
  - now configurable away for the hot path
- completely missing hot indexes
  - no longer true for the benchmark filters we already aligned

## WFS 2.0

### What is proven

Honua's WFS handler currently does an exact per-layer count before building paged query plans:
- [/home/makani/honua-server/src/Honua.Server/Features/Wfs20/Services/Wfs20Handler.cs](/home/makani/honua-server/src/Honua.Server/Features/Wfs20/Services/Wfs20Handler.cs)

Specifically:
- `BuildLayerQueryPlansAsync(...)` calls `_featureReader.CountAsync(...)` before issuing the actual query
- JSON and GML result builders then issue the actual query and materialize results

GeoServer's WFS path is more nuanced:
- `GetFeature` builds `CountExecutor` objects only when needed
- `CountExecutor` can reuse a provided count, call `getCount`, or fall back to `getFeatures(query).size()`

Relevant code:
- [/tmp/geoserver/src/wfs-core/src/main/java/org/geoserver/wfs/GetFeature.java](/tmp/geoserver/src/wfs-core/src/main/java/org/geoserver/wfs/GetFeature.java)
- [/tmp/geoserver/src/wfs-core/src/main/java/org/geoserver/wfs/CountExecutor.java](/tmp/geoserver/src/wfs-core/src/main/java/org/geoserver/wfs/CountExecutor.java)

### Likely implication for benchmarking

If Honua lags GeoServer on WFS, the first suspect should be:

- exact pre-count before every paged WFS result

The second suspect should be:

- the same attribute-deserialize and response-materialization overhead seen on OGC

The third suspect should be:

- Honua does not yet have the OGC-style no-count paged fast path in WFS, so WFS is structurally heavier than Honua's own optimized OGC path today

### Confidence

High confidence on the structural difference.
Low confidence on the exact size of the benchmark penalty until we run the current WFS suite.

## WMS / Raster

### What is proven in GeoServer

GeoServer's raster map output uses `StreamingRenderer` with several performance-relevant hints enabled:
- `optimizedDataLoadingEnabled`
- `renderingBuffer`
- `maxFiltersToSendToDatastore`
- renderer thread pool
- line width optimization
- advanced projection handling controls

Relevant code:
- [/tmp/geoserver/src/wms-core/src/main/java/org/geoserver/wms/map/RenderedImageMapOutputFormat.java](/tmp/geoserver/src/wms-core/src/main/java/org/geoserver/wms/map/RenderedImageMapOutputFormat.java)
- [/tmp/geoserver/src/wms-core/src/main/java/org/geoserver/wms/map/StyleQueryUtil.java](/tmp/geoserver/src/wms-core/src/main/java/org/geoserver/wms/map/StyleQueryUtil.java)
- [/tmp/geotools/modules/library/render/src/main/java/org/geotools/renderer/lite/StreamingRenderer.java](/tmp/geotools/modules/library/render/src/main/java/org/geotools/renderer/lite/StreamingRenderer.java)

This stack reduces work by:

- building a bbox/style-aware query
- pushing the spatial filter into the datastore
- using renderer hints like screenmap/generalization where supported
- rendering through a mature renderer rather than an endpoint-specific raster loop

Additional evidence:
- GeoServer's map output format explicitly sets:
  - `optimizedDataLoadingEnabled`
  - `renderingBuffer`
  - `maxFiltersToSendToDatastore`
  - thread pool
  - line-width optimization
  - advanced projection handling flags
  - [/tmp/geoserver/src/wms-core/src/main/java/org/geoserver/wms/map/RenderedImageMapOutputFormat.java](/tmp/geoserver/src/wms-core/src/main/java/org/geoserver/wms/map/RenderedImageMapOutputFormat.java)
- GeoServer's style query utility expands the bbox by the computed style buffer, mixes style and request filters, simplifies the filter, and sets `FEATURE_2D` hints:
  - [/tmp/geoserver/src/wms-core/src/main/java/org/geoserver/wms/map/StyleQueryUtil.java](/tmp/geoserver/src/wms-core/src/main/java/org/geoserver/wms/map/StyleQueryUtil.java)

### What is proven in Honua

Honua's MapServer export and WMS handlers currently:

- build a `FeatureQuery`
- call `featureReader.QueryAsync(...)`
- fully materialize feature arrays in memory
- iterate each feature
- convert WKB to Skia geometry
- evaluate style filters in the render loop
- draw with Skia

Relevant code:
- [/home/makani/honua-server/src/Honua.Server/Features/MapServer/MapServerRequestHandlers.Export.cs](/home/makani/honua-server/src/Honua.Server/Features/MapServer/MapServerRequestHandlers.Export.cs)
- [/home/makani/honua-server/src/Honua.Server/Features/MapServer/MapServerRequestHandlers.Wms.cs](/home/makani/honua-server/src/Honua.Server/Features/MapServer/MapServerRequestHandlers.Wms.cs)
- [/home/makani/honua-server/src/Honua.Server/Features/MapServer/Rendering/SkiaMapRenderer.cs](/home/makani/honua-server/src/Honua.Server/Features/MapServer/Rendering/SkiaMapRenderer.cs)

### Likely implication for benchmarking

If Honua lags GeoServer on WMS / export raster workloads, the first suspects are:

- inherited count/window-count cost from the shared limited query path
- full feature materialization before render
- WKB to Skia conversion cost
- style filter evaluation inside the render loop
- lack of screenmap/generalization-style renderer optimizations
- a hard `MaxFeaturesPerLayer` cap that can distort heavy layers

Important nuance:
- Honua's styled render path is effectively `for each style layer -> for each feature`, with filter evaluation and geometry conversion happening inside that loop.
- That means render cost can scale with both feature count and style-layer count, which is a materially different cost shape than GeoServer's mature renderer pipeline.

This is a very different architecture from GeoServer's WMS path and is likely to be the biggest protocol-level gap outside common feature JSON.

### Confidence

High confidence on the architectural difference.
Medium confidence on exact benchmark impact until the Honua raster suite is rerun against GeoServer on the same current builds.

## GeoServices REST / FeatureServer

### What is proven

Honua's native FeatureServer path is architecturally leaner than its common OGC/WFS paths in a few important ways:

- it has a dedicated `FeatureServerQueryExecutor`
- it supports streaming responses
- it uses `LIMIT + 1` style probing for `hasMoreResults`
- it already has native binary-oriented output paths such as PBF and GeoArrow helpers

Relevant code:
- [/home/makani/honua-server/src/Honua.Server/Features/FeatureServer/Services/FeatureServerQueryExecutor.cs](/home/makani/honua-server/src/Honua.Server/Features/FeatureServer/Services/FeatureServerQueryExecutor.cs)

### Likely implication

Honua's native FeatureServer path is the most likely place for Honua to look decisively better than GeoServer, especially if GeoServer only exposes GeoServices REST through the community GSR extension.

This is not yet a measured claim in GeoBench because the GeoServer GSR extension is not installed in the benchmark image.

Important limitation:
- GeoServer GeoServices REST is not comparable in the current local benchmark image because the GSR community extension is not installed.
- Any native-protocol claim here should therefore be treated as Honua architectural expectation until a GeoServer GSR image is added and benchmarked.

## GeoServer-Side Optional Knobs We Are Not Even Using Yet

Our current GeoServer adapter sets:
- `Loose bbox = false`
- `Estimated extends = true`
- `encode functions = true`
- connection pool settings

It does **not** explicitly enable prepared statements in the datastore config:
- [adapters/geoserver/setup.sh](/home/makani/geobench/adapters/geoserver/setup.sh)

GeoServer's PostGIS docs expose more tuning knobs:
- prepared statements
- loose bbox
- estimated extents
- SQL function encoding
- on-the-fly geometry simplification

Source:
- https://docs.geoserver.org/stable/en/user/data/database/postgis.html

Implication:
- current GeoServer results are not coming from every optional PostGIS optimization being turned on
- if anything, the current GeoServer numbers are not a "max tuned" ceiling

## What The Open Source GeoServer Stack Suggests Strategically

GeoServer already uses two ideas that map directly to Honua product strategy:

### 1. Per-layer SQL specialization is normal

GeoServer SQL Views explicitly support pushing GeoServer-generated `WHERE` clauses into a tuned SQL view via `:where_clause:`:
- https://docs.geoserver.org/main/en/user/data/database/sqlview.html

That is strong precedent for Honua service/layer profiles backed by different tables, views, or materialized views.

### 2. Renderer-side query reduction matters as much as raw SQL

GeoServer WMS is not just "fast PostGIS".
It is:

- a style-aware query builder
- a renderer with generalization and screenmap support
- a rendering stack that can avoid drawing work before it happens

That means Honua cannot catch GeoServer raster performance just by tuning SQL indexes.

## Best Current Explanation By Protocol

### OGC API Features

Honua loses when:
- the storage-shape disadvantage of JSON-backed attributes matters
- the app-layer property/geometry conversion cost matters more than the raw SQL time

GeoServer wins by:
- reusing WFS/GetFeature
- leaning on GeoTools JDBC pushdown
- streaming GeoJSON output more directly

### WFS

Honua will likely lose when:
- exact `CountAsync` is required before paged results
- output materialization cost dominates
- service/layer bootstrap overhead or adapter drift prevents using the same clean current image in isolated reruns

GeoServer likely wins by:
- more opportunistic count handling
- the same mature JDBC/WFS pipeline it uses everywhere else

### WMS / Export Raster

Honua will likely lose when:
- rendering requires large in-memory feature batches
- per-feature geometry conversion and style evaluation dominate

GeoServer wins by:
- using `StreamingRenderer`
- shrinking the query to what the style and viewport need
- applying renderer-level optimizations that Honua does not yet have

### GeoServices REST / FeatureServer

Honua is most likely to look best here because:
- this is a native protocol path
- it already has streaming and lower-overhead response machinery

## Highest-Confidence Causes Matrix

| Protocol | Why GeoServer tends to win | Why Honua can still win | Confidence |
| --- | --- | --- | --- |
| OGC API Features | Reuses WFS/GetFeature, JDBC pushdown, leaner GeoJSON writer, typed benchmark table | Honua now has no-count OGC paging, good selective-query plans, and payload bloat is mostly fixed | High |
| WFS | More opportunistic `numberMatched` handling, mature GetFeature path, same JDBC pushdown stack | Honua can narrow the gap if WFS gets the same no-count fast path and less response materialization | High |
| WMS / GetMap | `StreamingRenderer`, style-aware query reduction, renderer hints, thread pool, optimized raster pipeline | Honua may do well on simple/default-style layers, but current architecture is heavier | High |
| GeoServices REST / FeatureServer | Not yet comparable locally because GeoServer GSR is absent | Honua has the leanest native path today: streaming, `LIMIT + 1`, and binary formats | Medium |

## Open Questions

These are still unresolved:

- exact cause of Honua's remaining OGC lag on `small` and `medium` bbox despite better DB plans
- exact WFS benchmark gap on the current patched Honua build once the adapter is updated for the new no-default-service image behavior
- exact raster gap on current Honua WMS/export vs GeoServer WMS
- how much of Honua raster lag is query fetch vs render loop vs PNG encoding

## Next Measurements That Would Close The Remaining Gaps

1. Run the current WFS suite for Honua and GeoServer.
   - First fix the Honua adapter to create a benchmark service instead of assuming `default` exists.
2. Run the current raster suite for Honua WMS or export and GeoServer WMS on the same layer/style.
3. Capture protocol-local traces:
   - Honua OGC/WFS: DB time vs response serialization time
   - Honua MapServer: query time vs WKB conversion vs draw time vs PNG encode time
4. Add a benchmark profile that exposes only typed columns for the hot benchmark fields, then rerun OGC/WFS.

## Bottom Line

The remaining GeoServer advantage is not one thing.

Today it is the combination of:

- a typed benchmark table with aligned indexes
- a mature JDBC pushdown stack
- response writers that stream efficiently
- smarter count behavior in WFS
- a heavily optimized raster renderer stack

Honua has already closed a meaningful part of the gap on the common OGC feature path.
The next gains are less about "one missing Postgres index" and more about:

- avoiding generic per-row attribute decode on hot paths
- reducing exact-count obligations by protocol
- building a renderer/query stack for raster that avoids materializing and drawing unnecessary work
