# Remaining feature optimization opportunities — October 1, 2026 (UTC)

The [verified three-pair JIT diagnostic](jit-production-three-pair-20261001.md)
identifies shallow/medium pagination as the remaining throughput deficits: roughly
2%/3% behind GeoServer, with p95 about 6% worse. Empty/boundary throughput and tails
lead, but their median latency is about 19%/7% worse. This review prioritizes those
paths. It does not infer gains from source inspection or establish AOT performance.

An independent read-only review inspected the combined checkout
`e110a28cb4b3b5a64fd3b0e4c279a2099fb35f06`. Native decoding
([#5349](https://github.com/honua-io/honua-server/pull/5349)) and authorized metadata
reuse ([#5351](https://github.com/honua-io/honua-server/pull/5351)) are implemented
but still awaiting current-source compatibility and HTTP measurements. The retained
fifth qualification failed six PostgreSQL cases. After fixes, source
`68a6c0de2b152128c5ccdc037f686bcc2ac36c35` passed fresh Release JIT build,
format and all 519 selected tests with zero failures/skips and complete owned cleanup.
Supplemental caller-transaction stability source
`cf49cb77d31e7a56ed81870b8e10ab6e7a427a61` is undergoing the same qualification
in a separate seventh attempt. The previous-source pass is not a current-source claim. Production
schema-header correction is already delivered. The earlier range-tail deficit did
not recur in the current three pairs, so it is not the primary target.

## Priority and applicability

| Order | Pending change | Cases and current code evidence | Verification boundary |
| --- | --- | --- | --- |
| 1 | Batch fresh row-policy and field-mask reads on one catalog lease | Empty/boundary fixed overhead and all feature requests; tracked in [#5352](https://github.com/honua-io/honua-server/issues/5352). Initial reads remain separate despite operation-local security resolution. | Preserve fresh policies/principal, anonymous wildcard rules, scopes, custom store overrides, independent missing-table behavior and cancellation. No policy TTL cache. |
| 2 | Reuse the request's WKB reader | `src/Honua.Protocols.Ogc.Shared/Common/OgcFeaturesGeometryServices.cs:70` allocates one reader per feature; the service is scoped and sequential, already reusing its writer. Applies to nonempty pages and boundary's point. | Preserve parser state across different byte orders, geometry types, empty/malformed input, Z/M and axis order. Existing geometry regressions, allocation check and oracle smoke. |
| 3 | Remove redundant ID delegates and array copies | `OgcGeoJsonFeatureBuilder.cs:32,75` captures feature IDs in a delegate and copies the collection array; identifier resolution repeats the primary-ID lookup. Source reader materialization grows an empty builder and copies its contents. | Preserve configured public IDs, string/numeric IDs and fallback behavior. Reuse prepared schema data; reserve only bounded capacities; transfer only if capacity equals count. Verify sparse/empty/full pages and allocations. |
| 4 | Resolve the attribute projection once per SQL build | `PostgresStorageMappedFeatureReader.NativeAttributes.cs:25`, `.Paging.cs:32` and JSON fallback revisit field resolution; `PostgresStorageMappedFeatureReader.cs:685–706` scans schema/builds collections. Applies to page and tiny-response fixed overhead. | Carry a request-local field list; preserve masks, requested order, case collisions, DISTINCT, excluded attributes, identifier checks and stale-type fallback. Existing projection/mask/wide-field tests. |
| 5 | Remove the Point geometry text/DOM round trip | `OgcFeaturesGeometryServices.cs:313–338` applies limits, writes NTS geometry to JSON, parses it, extracts coordinates, then final output writes them again. | Point-only output after existing limits; preserve empty points, Z/M, precision/rounding, axis order and nonfinite behavior. Compare complete parsed responses and existing geometry cases before timing. |
| Later, outside current measured page path | Reuse/batch exact count and page source leases | `PostgresStorageMappedFeatureReader.cs:163–179` issues count/page separately; each opens a lease. Exact-count consumers may benefit. The current benchmark uses `OmitWhenExpensive`; mapped `IPagedFeatureReader.QueryPageAsync` executes one SELECT without COUNT. This does not target its shallow/medium deficit. | Preserve transaction ownership, planner-setting scope, security once, count/order behavior, errors/cancellation and lease cleanup. Keep short-first-page count elision; do not add unconditional counts to empty first pages. |
| 7 | Write buffered GeoJSON directly to UTF-8 with prepared schema | The source-backed reader implements generic reader interfaces (`PostgresStorageMappedFeatureReader.cs:32`), so measured reads reach `OgcFeaturesQueryHandler.cs:416–438`. Other store's native/raw GeoJSON interfaces do not accelerate this provider automatically. | Consume authorized materialized features without changing database work. Preserve exact counts, fields/types/dates, IDs, masks, links, CRS and geometry. Oracle and 100-feature allocation checks before HTTP timing. |

The next small batch should combine reader reuse, ID/allocation cleanup and projection
reuse, alongside the separately tracked security-policy batching. Geometry and direct
output rewrites need more parity testing. Count/page batching does not apply to the current measured page path and also changes
transaction/planner scope, so it is deferred to exact-count consumers. None of these pending changes
is counted in the existing 72-row result or described as a measured improvement.

No reviewer edits, builds or traffic were performed. Current optimization remains
Release JIT; final production AOT and strict publishable evidence follow qualification
and paired remeasurement of the completed optimizations.

## Focused pagination follow-up

A new read-only reviewer examined source
`cf49cb77d31e7a56ed81870b8e10ab6e7a427a61` and verified the current benchmark
path: `OmitWhenExpensive`, feature links disabled, mapped `IPagedFeatureReader`,
`QueryPageAsync` with one SELECT and a limit-plus-one probe, followed by WKB/DTO
conversion. The recommended immediate page batch is:

1. Remove the second properties dictionary only in the internal OGC builder's
   response-owned path. `GeoJsonFeatureBaseBuilder.cs:84` already creates the
   dictionary; `OgcExtensions.cs:72` copies it again. Preserve the public conversion
   helper's detached-copy semantics for arbitrary callers.
2. Reuse WKB decoding within the sequential response scope, preserving NTS output
   and testing mixed endian/SRID/Z/M/empty/malformed inputs and recovery after an
   invalid read. Local GeoTools35.1 `PostGISDialect.java:296,358–367` and
   `WKBAttributeIO.java:40–41,77–84` reuse their decoder/reader, a source precedent
   rather than evidence of a Honua speed gain.
3. Prepare public-ID field resolution once; avoid per-feature closures and schema
   scans. Use direct lookup only for known canonical case-insensitive dictionaries;
   retain configured-ID, fallback-id, internal-ID ordering and general dictionaries'
   case-collision behavior.
4. Add ownership-aware array transfer for the exact array created by the handler.
   A page-specific materializer can also avoid decoding the extra probe feature and
   copying the immutable array to remove it. Preserve public query/stream behavior,
   result ordering, page lengths and general callers' array isolation.
5. Reuse query-local projection decisions, preserving masks, hidden fields,
   declaration order, case handling and retry fallback. This ranks lower for the
   current small all-field schema.

The strongest immediate page candidates are dictionary-copy removal, WKB reuse,
and prepared IDs. Fresh policy batching remains the separate fixed-overhead target.
The first allocation batch is now implemented in independent trunk-based
[draft PR5354](https://github.com/honua-io/honua-server/pull/5354), closing
[issue5353](https://github.com/honua-io/honua-server/issues/5353): response-owned
properties transfer, scoped sequential WKB reader reuse, and explicit handler-owned
array transfer. Source `c3f597df357978b120a90fea23f61aaa05ca92ef` is queued for
fresh JIT compilation, changed-file format verification and expanded OGC GeoJSON,
query, geometry and identifier regressions. New tests cover canonical/encoded response
isolation, public/arbitrary detached copies, empty/full collections and fresh-versus-reused
parsing across endian/SRID/Z/M, including invalid-then-valid input. Tests and speed gains
are not yet claimed passing. Prepared IDs/projection/probe materialization and policy
batching remain follow-ups. No new serving changes are included in the measured72rows.

## Credential freshness review

A separate registry-cache shortcut was rejected: the metadata graph has no authoritative
credential epoch and omits current encrypted credentials/key version, registry activity
and complete host/SSL assertions. Registry updates do not invalidate graph snapshots
across replicas; their graph cache falls back to TTL. A graph revision is therefore not
a credential revision. Existing reader string memoization already avoids repeated
per-reader decryption. Keep the first authoritative lookup. Batching live registry and
policy reads, or reusing a freshly resolved connection within one authorized multi-layer
request, remains a future possibility. Neither is an implemented or measured gain.
