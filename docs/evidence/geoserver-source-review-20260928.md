# GeoServer source review — 2026-09-28

This review identifies optimization candidates for Honua's source-backed feature
reads. It is diagnostic work on the shared development host, not a new product
comparison. The scope is the deterministic 100K-point dataset, 100-feature pages,
exact counts, and the OGC API Features corpus.

> September 29 follow-up: all three optimization PRs have merged. See the
> [AOT rebaseline record](aot-rebaseline-20260929.md) for the exact integration
> candidate, separate tuning profile, and measurement status. The findings below
> retain the identities and evidence available at the original review.

## Versions and runtime evidence

The reviewed upstream tags match the versioned JARs recorded by
`results/feature-aot-followup-smoke-20260928/pair1-geoserver/plugins.json`:

| Component | Release | Source commit |
|---|---|---|
| GeoServer, including OGC API Features and WFS core | 3.0.1 | `804fe178e4ff3fb4d0a2d0a0751930b31bf43a2a` |
| GeoTools JDBC and PostGIS | 35.1 | `820904c219b584f817dbf7341ba2c480fc1a3e06` |
| Honua source baseline reviewed | trunk snapshot | `e9ef3d292787834ac3f943044788da5ccd7e9427` |

The GeoServer image is
`sha256:a395701a5eea4884c855f136be84363d0ce05e06da1ea6c7e3b84e146279927b`.
The receipt records SHA-256 hashes of the installed JARs, including:

- `gs-ogcapi-features-3.0.1.jar`: `1d83a80015691f10b779fa373fd3bf2ec1db2fb09bd6e59efc98a5d45bebacbc`
- `gs-wfs-core-3.0.1.jar`: `333147436f230f278a18e0f44c4756be38c259f80e0e9fb2511eed2e73fd13dc`
- `gt-jdbc-35.1.jar`: `bf8a81d6d87cb89a62f324d1629bad49bf0db7977e6016685a4e874f3777c470`
- `gt-jdbc-postgis-35.1.jar`: `53f782b411ec5415cd799c94fb7e1a2f20e984414c2426fb10471b9db29e60a9`

This is a release-source review supported by runtime version/hash receipts and
executed SQL, not a byte-for-byte reproducible-build attestation. The reviewed
Honua source is newer than the published AOT image used in the HTTP diagnostics;
those identities must not be conflated.

## Findings and implications

### Native query execution is shared with WFS

The [OGC items handler][feature-service] creates a WFS GetFeature request, sets
sort, start index and limit, and calls `FeaturesGetFeature.run`. GeoTools
[JDBCFeatureSource][jdbc-source] splits database filters from application filters.
It pushes pagination into SQL when no application filter remains; otherwise it
removes SQL pagination and applies the remaining filter before paging. The
[PostGIS dialect][dialect] implements SQL `LIMIT` and `OFFSET`.

Honua already pushes these operations into SQL. The relevant defect was the
placement of expensive output expressions: the observed deep-page plan encoded
50,100 rows to return 100. [PR #5299][paging-pr] moves encoding after the raw page
and preserves explicit ordering and column permissions. Its single SQL diagnostic
fell from about 706 ms to 56 ms; 145 mapped-reader tests passed. There is no new
candidate AOT HTTP result. PostgreSQL still has to scan/skip offset rows; this
change reduces encoding work, not the inherent cost of offset pagination.

### GeoServer does exact counts, with a bounded probe and a reuse opportunity

[GetFeature][get-feature] obtains the page size, reuses it as the total when it
proves the first page is complete, and otherwise creates an unbounded count query.
The total is lazily evaluated and cached within the response. [CountExecutor][count]
uses a supplied count or `source.getFeatures(query).size()`; the JDBC collection
can satisfy that through an SQL aggregate. [JDBCDataStore][jdbc-store] wraps
limited aggregate queries in `gt_limited_`.

The captured `source-query.log` contains this sequence for equality:

1. Count matching rows up to `LIMIT 100`.
2. Count all matching rows without the limit.
3. Select the ordered page of native columns and encoded geometry.

For the small bbox it contains the bounded count and feature SELECT, consistent
with reusing a complete first-page count. The [GeoJSON response][json-response]
resolves the total before invoking the writer; the OGC writer emits
`numberMatched` when that total is available. Lazy calculation therefore does not
mean the exact count disappears from response latency.

Honua's [mapped reader][honua-reader] currently performs the full count before
fetching features in `QueryAsync`. A page-first exact-count strategy could save
the separate count when offset is zero and fewer than the requested rows return.
It must still count full pages and nonzero offsets, preserve security, and define
the existing concurrent-update behavior. Do not copy GeoServer's extra bounded
count round trip without measuring whether the fetched page itself can prove the
same result. This remains a candidate, not an implemented improvement.

### Typed attributes avoid a database JSON round trip

The trace selects native fields and `encode(ST_AsEWKB(geom), 'base64')`.
[JDBCFeatureReader][jdbc-reader] reads ordinary values from the result set and
uses the geometry decoder for geometry columns. [GeoJSONFeatureWriter][json-writer]
iterates features and writes properties to the response writer. It still creates
feature/geometry objects and converts values; this is not a zero-allocation path.

Honua's source-backed reader uses `jsonb_build_object(...)::text`, reads that
string, parses it with `FeatureAttributeJsonReader`, and creates the canonical
attribute dictionary. The [OGC handler][honua-ogc] takes its buffered path at the
100-feature corpus limit (streaming requires a limit above 200 and other guards),
then constructs response features. Both products now read the same typed source
table: the older explanation that Honua reads imported `public.features` is
inapplicable to this campaign.

A typed source-row decoder could remove the database JSON encoding and parsing
while preserving Honua's shared feature model. Profile allocations and CPU before
choosing this larger change. Tests must cover nulls, decimals and large integers,
timestamps, booleans, JSON fields, projected/masked columns, aliases, and geometry
dimensions. Streaming alone would not remove PostgreSQL count/planning costs.

### Spatial SQL differs, but copying it is not a general win

[FilterToSqlHelper][spatial-helper] emits an explicit bbox operator followed by
exact intersection for this geometry/BBOX path when loose bbox is disabled.
The saved effective store sets `Loose bbox=false`, and executed SQL confirms
`geom && envelope AND ST_Intersects(geom, envelope)`.

Our [seven-repetition spatial SQL diagnostic][followup] tested that form directly.
It improved the large bbox but worsened the world bbox. Keeping the original
exact predicate and disabling PostgreSQL JIT locally was the more promising
experiment: large-count median 179 to 43 ms and world-count median 635 to 127 ms,
with wide shared-host ranges. These are SQL-only observations, not product speedup
ratios. PostgreSQL JIT is independent of Honua's Native AOT compilation.

No explicit JIT setting was found in the reviewed GeoTools JDBC/PostGIS production
source directories. That does not prove every runtime connection setting or query
plan. The reviewed trunk snapshot only scoped its serial-spatial helper to feature
reads. The count candidate described below adds separate opt-in JIT suppression;
it does not force serial counts or change the exact spatial predicate.

### Cursor fetching can change parallel execution

The pinned GeoTools factory defaults fetch size to 1,000, and its feature reader
uses a forward-only, read-only statement. Before opening that reader,
[JDBCFeatureSource](https://github.com/geotools/geotools/blob/820904c219b584f817dbf7341ba2c480fc1a3e06/modules/library/jdbc/src/main/java/org/geotools/jdbc/JDBCFeatureSource.java#L603)
sets autocommit from the dialect's query policy. The base
[SQLDialect](https://github.com/geotools/geotools/blob/820904c219b584f817dbf7341ba2c480fc1a3e06/modules/library/jdbc/src/main/java/org/geotools/jdbc/SQLDialect.java#L1112)
returns false; the reviewed PostGIS dialect does not override that method.
[pgJDBC documents](https://jdbc.postgresql.org/documentation/query/#getting-results-based-on-a-cursor)
that positive fetch size, autocommit off and a forward-only single-statement query
enable cursor fetching.

This matters beyond buffer sizing: [PostgreSQL 17 documents](https://www.postgresql.org/docs/17/when-can-parallel-query-be-used.html)
that an extended-protocol Execute with a nonzero fetch count cannot execute its
plan in parallel. An ordinary EXPLAIN ANALYZE of the same SQL can therefore differ
from the JDBC execution path. This is an explanation to investigate, not a reason
to copy GeoServer's connection policy or change global database settings.

Six retained GeoServer preflight traces from the completed September 29 first-page
mixed campaigns contain 208 source feature executions using named `C_` portals.
All 398 source count executions use the non-cursor path. The source and traces
support the inference that cursor fetching contributes to serial feature execution.
The wire-level Execute row count was not captured, so this is not a direct protocol
attestation or causal speedup measurement. Counts obtain their connection through
a separate path that restores autocommit; the cursor explanation must not be
extended to counts. Source files, hashes and per-trace observations are retained
in `results/geoserver-fetch-planner-20260929/review-receipt.json`.

[PostgisNGDataStoreFactory][postgis-factory] also defaults the prepared-statement
dialect option to false. Neither a fetch-size nor prepared-statement override
appears in the saved store. This remains a source-default interpretation supported
by the literal SQL and cursor traces, not an independent live getter measurement.
Prepared versus custom/generic plans remains a separate diagnostic dimension.

Honua's scoped serial-read option directly tests the worker-startup hypothesis
without adopting JDBC cursor transport. Separate count-only and combined profiles
are still required; no application performance gain follows from this review alone.

## Additional correctness follow-up discovered in the trace

The saved prefix request contains `feature_name LIKE 'feature\_1%'`, but
GeoServer's executed SQL contains `LIKE 'feature_1%'`. On the generated names
these produce the same IDs, so the current oracle corpus cannot prove preservation
of the literal underscore. The JDBC LIKE encoder calls
[`LikeFilterImpl.convertToSQL92`][like-conversion], whose escape branch emits the
next character without the original escape. That provides a source-level
explanation consistent with the trace, although the CQL2 parser's intermediate
filter and alternative request spellings still need an isolated test.
Before treating escaped-prefix support as proven, add an adversarial semantic
case whose result differs when the escape is lost, then trace both parsers. Keep
any unsupported contract visible as a coverage gap. Existing timings do not
establish general literal-prefix correctness.

## Implementation priority

1. Review the verified [read-security candidate][security-pr], which resolves
   policy once per operation while preserving fresh resolution on the next public
   read. Measure its removal of repeated absent-policy lookups in the application.
2. Retain the pagination candidate and validate it in a future AOT build when
   shared-host capacity allows.
3. Measure the verified count-JIT candidate in the application, separately from
   forced serial execution and from benchmark baseline defaults.
4. Measure page-first exact-count reuse and typed source-row decoding separately,
   with correctness and allocation evidence before combining them.

The last sustained local mixed diagnostic favored GeoServer by roughly 2× in
throughput. This source review explains work worth removing; it supplies no new
Honua-versus-GeoServer speed ratio. Rendering, WFS, tiles, GSR and non-point
workloads remain outside this review.

The focused security candidate reproduced seven failures and four passes before
the fix, then passed all 149 targeted mapped-reader/security tests without
skips. This verifies policy consistency and fewer resolver calls, not an HTTP
throughput improvement. See [draft PR #5302][security-pr].

The count-JIT candidate adds `Database__DisableJitForSourceSpatialCounts`, default
`false`, for source-backed point counts with simple intersects/envelope bboxes.
It preserves the original predicate and security parameters, uses a separate
prepared-query identity, and restores the original session settings after
success, SQL errors, and cancellation. Ambient and borrowed transactions retain
ordinary planning. All 156 targeted reader/registration tests passed, including
17 new integration cases; pool reset was disabled to expose setting leaks on the
same physical connection. The baseline reproduced four expected failures and
eight passes. A subsequent test compile failed on local-variable shadowing, was
corrected, and remains in the local attempt log. See
[draft PR #5307](https://github.com/honua-io/honua-server/pull/5307) and the local
receipt `results/source-spatial-count-jit-20260928/verification.json`. No candidate
AOT HTTP measurement has been run.

[security-pr]: https://github.com/honua-io/honua-server/pull/5302

[feature-service]: https://github.com/geoserver/geoserver/blob/804fe178e4ff3fb4d0a2d0a0751930b31bf43a2a/src/extension/ogcapi/ogcapi-features/src/main/java/org/geoserver/ogcapi/v1/features/FeatureService.java#L396
[get-feature]: https://github.com/geoserver/geoserver/blob/804fe178e4ff3fb4d0a2d0a0751930b31bf43a2a/src/wfs-core/src/main/java/org/geoserver/wfs/GetFeature.java#L518
[count]: https://github.com/geoserver/geoserver/blob/804fe178e4ff3fb4d0a2d0a0751930b31bf43a2a/src/wfs-core/src/main/java/org/geoserver/wfs/CountExecutor.java#L38
[json-response]: https://github.com/geoserver/geoserver/blob/804fe178e4ff3fb4d0a2d0a0751930b31bf43a2a/src/wfs-core/src/main/java/org/geoserver/wfs/json/GeoJSONGetFeatureResponse.java#L85
[json-writer]: https://github.com/geoserver/geoserver/blob/804fe178e4ff3fb4d0a2d0a0751930b31bf43a2a/src/main/src/main/java/org/geoserver/json/GeoJSONFeatureWriter.java#L387
[jdbc-source]: https://github.com/geotools/geotools/blob/820904c219b584f817dbf7341ba2c480fc1a3e06/modules/library/jdbc/src/main/java/org/geotools/jdbc/JDBCFeatureSource.java#L580
[jdbc-store]: https://github.com/geotools/geotools/blob/820904c219b584f817dbf7341ba2c480fc1a3e06/modules/library/jdbc/src/main/java/org/geotools/jdbc/JDBCDataStore.java#L4025
[jdbc-reader]: https://github.com/geotools/geotools/blob/820904c219b584f817dbf7341ba2c480fc1a3e06/modules/library/jdbc/src/main/java/org/geotools/jdbc/JDBCFeatureReader.java#L130
[jdbc-factory]: https://github.com/geotools/geotools/blob/820904c219b584f817dbf7341ba2c480fc1a3e06/modules/library/jdbc/src/main/java/org/geotools/jdbc/JDBCDataStoreFactory.java#L96
[dialect]: https://github.com/geotools/geotools/blob/820904c219b584f817dbf7341ba2c480fc1a3e06/modules/plugin/jdbc/jdbc-postgis/src/main/java/org/geotools/data/postgis/PostGISDialect.java#L1353
[spatial-helper]: https://github.com/geotools/geotools/blob/820904c219b584f817dbf7341ba2c480fc1a3e06/modules/plugin/jdbc/jdbc-postgis/src/main/java/org/geotools/data/postgis/FilterToSqlHelper.java#L333
[postgis-factory]: https://github.com/geotools/geotools/blob/820904c219b584f817dbf7341ba2c480fc1a3e06/modules/plugin/jdbc/jdbc-postgis/src/main/java/org/geotools/data/postgis/PostgisNGDataStoreFactory.java#L86
[like-conversion]: https://github.com/geotools/geotools/blob/820904c219b584f817dbf7341ba2c480fc1a3e06/modules/library/main/src/main/java/org/geotools/filter/LikeFilterImpl.java#L108
[honua-reader]: https://github.com/honua-io/honua-server/blob/e9ef3d292787834ac3f943044788da5ccd7e9427/src/Honua.Db/Postgres/Features/FeatureStore/Services/PostgresStorageMappedFeatureReader.cs#L119
[honua-ogc]: https://github.com/honua-io/honua-server/blob/e9ef3d292787834ac3f943044788da5ccd7e9427/src/Honua.Protocols.OgcApi/Features/OgcFeaturesQueryHandler.cs#L193
[paging-pr]: https://github.com/honua-io/honua-server/pull/5299
[followup]: feature-followup-20260928.md#spatial-count-optimization-diagnostics-on-the-shared-host
