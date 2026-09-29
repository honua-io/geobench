# Feature campaign validation — 2026-09-28

Scope: deterministic seed-42 **100K points**, source-backed PostGIS reads,
OGC API Features, production Honua Native AOT versus stable GeoServer. This
work produced harness validation evidence and concrete blockers, **no publishable
Honua–GeoServer performance comparison**.

The [follow-up campaign](feature-followup-20260928.md) verifies the merged source-pool
fix in a newer published AOT image, completes all 40 smoke rows, and records
three local observer pairs per product. Clock and calibration gates still prevent
publication.

Implementation is in three increments: oracle validation/reporting, immutable
paired orchestration, then diagnostics/calibration/regression coverage. See the
[operating guide](../feature-campaigns.md) for commands and the evidence contract.

## Runtime identities

- Honua Native AOT: `ghcr.io/honua-io/honua-server@sha256:a276c0a40d30536b1c8cb4567397fa6160aa057f44cc7eb8c65c874a8a830d57`, revision `bbd48b43bbf38b70d7e114286f829c2cab156cec`.
- Stable GeoServer 3.0.1 + matching OGC API extension, prepared immutable local image: `sha256:a395701a5eea4884c855f136be84363d0ce05e06da1ea6c7e3b84e146279927b`.
- Separate community GeoServer + GSR image: `sha256:84a8268aa55a1b5557ee603edefce9892473fb28a9a4666ae44a735bbea0be9f`.
- PostGIS 17/3.5: `sha256:01a6a70e41e6c4467c8f55f6063555ed72db2d6662cd0d571040d42eadaeb6f6`.
- k6 0.54.0: `sha256:1f40432b1cbe7234e977f96c362c9bc550a2d2b583d014dd8669fe40d3e9e755`.

Both prepared GeoServer images retain complete installed JAR hashes and version
checks. Extensions were installed before any timed traffic. The strict campaign
captured Native AOT labels, executable identity and absence of CoreCLR mappings.
All server/DB/generator containers had effective 4 CPU / 4 GiB limits.

## Findings

Both OGC implementations passed the full eleven-request oracle preflight:
complete ordered IDs, all source attribute values/types, exact count metadata,
geometry, empty results, escaped literal prefix, pagination and bbox boundary.
Separate SQL traces proved reads from `public.bench_points`. Their source
content, index and database-settings fingerprints matched.

The Honua pressure probe observed **ten source-query sessions** despite the
six-connection main pool/admission configuration. The tested image's
[bound source reader](https://github.com/honua-io/honua-server/blob/bbd48b43bbf38b70d7e114286f829c2cab156cec/src/Honua.Db/Postgres/Features/FeatureStore/Services/PostgresStorageMappedFeatureReader.cs#L1476)
opens the bound connection string directly; that path bypasses the default
connection provider's gate. Source pool configuration must be enforced and
verified before this profile can qualify as the bounded baseline. The harness
now probes this before timed comparisons rather than discovering it after a
long campaign. This finding applies to this image and provisioning profile.

The shared local host has no separate isolated load generator configured.
Consequently there is no observer-off/on/isolated calibration receipt with raw
samples, and the strict publication gate rejects the setup. A longer diagnostic
also exposed backward wall-clock adjustments. The corrected workload uses
monotonic executor progress for measurement boundaries and latency; auxiliary
negative HTTP timing samples remain visible and disqualify publication.

The separately packaged community GSR profile failed its independent response
contract. GeoServer returned incompatible feature counts for equality, range,
prefix, medium/large bbox and pagination, and extra attributes for small/boundary
bbox. Honua returned non-feature payloads for medium/large GSR bbox requests.
These are recorded response-contract coverage gaps, without protocol substitution
or a performance loss/winner classification.

## Campaign ledger

Artifacts remain locally under `results/`; generated campaign directories are
intentionally not committed.

| Directory | Evidence and outcome |
|---|---|
| `feature-smoke-20260928-a` | Preserved initial probe-address and SQL-tracing configuration failures. |
| `feature-smoke-20260928-b` | Preserved incorrect Honua count-policy configuration; corrected to `Exact`. |
| `feature-smoke-20260928-c` | Both products completed semantically valid short equality loads; Honua's observed source pool made the campaign invalid. |
| `feature-gsr-smoke-20260928` | Separate immutable community image, plugin identity checks and explicit GSR contract gaps. |
| `feature-reuse-diagnostic-20260928` | Preserved negative wall-clock timing failures and an explicitly interrupted attempt; owned resources were cleaned. |
| `feature-smoke-20260928-final` | Monotonic workload; Honua blocked at pressure preflight; GeoServer completed equality and all five fixed-arrival diagnostics. |
| `feature-comparison-20260928` | Full five-pair, 180s/120s schedule recorded at harness commit `c984bff`; first-pair prerequisites failed, remaining eight server runs explicitly not run. No strict measurement rows or publication approval. |
| `feature-reuse-diagnostic-20260928-final` | All three 30s/30s GeoServer diagnostic repetitions passed with the same three container IDs, private volume and network. Diagnostic valid; publication rejected, including six auxiliary clock anomalies in repetition 1. |

The final three-second arrival smoke windows illustrate correct accounting,
not steady-state capacity estimates:

| Offered req/s | Valid completions/s | p95 ms | Dropped iterations |
|---:|---:|---:|---:|
| 10 | 10.00 | 62.88 | 0 |
| 30 | 29.67 | 73.50 | 0 |
| 60 | 59.67 | 69.37 | 0 |
| 120 | 118.67 | 143.58 | 0 |
| 240 | 159.33 | 992.85 | 140 |

Late completions are separate; these are GeoServer-only diagnostic observations.
There is no paired ratio because Honua failed the fairness prerequisite.

## Verification and next campaign

The 33 automated tests pass, including semantic errors, missing scenarios,
warmup/drain exclusion, overlapping tags, invalid percentile aggregation,
configuration/snapshot drift, incompatible plugins, interrupted attempts,
owned cleanup, calibration evidence and the 5% boundary. Ruff, Python compilation,
all workload JavaScript syntax checks and Bash syntax checks pass. A real prepare/resume cycle retained its binding; changing the seed rejected resume without changing the existing manifest. ShellCheck
is configured in CI but its executable was unavailable locally.

Before a publishable campaign: enforce six connections on the actual Honua
source connection, rerun the pressure probe, supply isolated-generator and
observer calibration with raw hashes, and start a new five-pair campaign.
Cleanup verification found no campaign containers, volumes or networks remaining; the five unrelated containers present at the start remained running. Failed attempts remain immutable evidence. GSR requires separate contract fixes;
WFS, rendering, tiles, larger datasets, lines/polygons and memory-leak work remain
outside this initial point-feature comparison.
