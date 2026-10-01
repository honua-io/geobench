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
but still awaiting full local qualification and HTTP measurements. Qualification passed 27 core and 58 security tests, then failed six of
247 PostgreSQL cases: five SQL assertion conflicts and one prepared result-type drift
regression after a physical column type change. Repair that candidate before adding
further serving changes or claiming its speed gains. Production
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
| 6 | Reuse/batch exact count and page source leases | `PostgresStorageMappedFeatureReader.cs:163–179` issues count/page separately; each opens a lease. Nonzero-offset buffered pages, particularly medium pagination, are the narrowest initial scope. | Preserve transaction ownership, planner-setting scope, security once, count/order behavior, errors/cancellation and lease cleanup. Keep short-first-page count elision; do not add unconditional counts to empty first pages. |
| 7 | Write buffered GeoJSON directly to UTF-8 with prepared schema | The source-backed reader implements generic reader interfaces (`PostgresStorageMappedFeatureReader.cs:32`), so measured reads reach `OgcFeaturesQueryHandler.cs:416–438`. Other store's native/raw GeoJSON interfaces do not accelerate this provider automatically. | Consume authorized materialized features without changing database work. Preserve exact counts, fields/types/dates, IDs, masks, links, CRS and geometry. Oracle and 100-feature allocation checks before HTTP timing. |

The next small batch should combine reader reuse, ID/allocation cleanup and projection
reuse, alongside the separately tracked security-policy batching. Geometry and direct
output rewrites need more parity testing. Count/page batching also changes transaction
and planner scope, so it follows the smaller changes. None of these pending changes
is counted in the existing 72-row result or described as a measured improvement.

No reviewer edits, builds or traffic were performed. Current optimization remains
Release JIT; final production AOT and strict publishable evidence follow qualification
and paired remeasurement of the completed optimizations.
