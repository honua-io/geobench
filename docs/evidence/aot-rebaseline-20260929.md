# AOT feature rebaseline — September 29, 2026

This campaign measures the merged source-query optimizations against GeoServer
on the shared WSL development host. It is diagnostic evidence for optimization,
not a publishable performance comparison. The production amd64 Native AOT image has now passed its hosted-CI verification
and local identity checks. Both products passed the 20-scenario baseline smoke
campaign with no invalid responses. The paired tuned smoke campaign also passed,
and sustained mixed-workload diagnostics have started. No sustained campaign has
yet completed all scheduled repetitions.
The [previous diagnostics](feature-followup-20260928.md) favored GeoServer by
roughly 2× on mixed-workload throughput; source-level improvements do not replace
a fresh measurement.

## Changes and source identity

The server changes have landed through the normal PR lander:

| Change | PR | Merge revision |
|---|---|---|
| Page source rows before encoding JSON and geometry | [5299](https://github.com/honua-io/honua-server/pull/5299) | `6b55178d3b6adf04364b71dbbcfe8d21a053fe22` |
| Resolve read security once per public operation | [5302](https://github.com/honua-io/honua-server/pull/5302) | `3db220fb4f70c0bfb7beb1d442bb13555bf23a79` |
| Opt-in PostgreSQL JIT suppression for eligible spatial counts | [5307](https://github.com/honua-io/honua-server/pull/5307) | `6e4962be59b608ea573e098aabe3b6ae573dda91` |

The selected CI image was built from the exact trunk snapshot
`6e4962be59b608ea573e098aabe3b6ae573dda91` in
[run 36517628422](https://github.com/honua-io/honua-server/actions/runs/36517628422).
Its amd64 job passed the serving-image boundary check, GeoParquet smoke, and
verified image publication. The immutable image reference is
`ghcr.io/honua-io/honua-server@sha256:7345b8a0d0467b38393415c2ed8c7db86d5f5a99fdca9c255606050cb4dcf313`.
Local inspection confirms amd64, Native AOT, and the expected source revision.
The workflow has since completed: the server AOT jobs for both architectures and
the AOT manifest publication passed. The separate Lambda arm64 image build failed,
so the overall workflow result is failure. The selected server image's successful
job and verification steps are the evidence for this campaign.

The earlier local image candidate was `619e6f123328994342b44a36c530641285e261e5` on
`test/geobench-aot-rebaseline-20260929`. It uses the unchanged production
`docker/Dockerfile.aot`, the full build profile, and Native AOT with speed
optimization. The count change was cherry-picked while its normal merge was
pending. After that merge, all 11 files touched by these optimizations matched
the merged source exactly.

The complete trees are different: the earlier local candidate omits the later
[ArcGIS prefix change, PR 5308](https://github.com/honua-io/honua-server/pull/5308),
including its global `UsePathBase` middleware. The selected CI image includes that change. Results must retain the selected
image's actual revision; it is a snapshot, not a claim to include later trunk work.

After the CI image had passed verification and been pulled by digest, the
redundant local build was explicitly cancelled through its exact owned buildx
client. The local build and its waiting campaign runners are terminal; no timed
traffic ran in that attempt. Its original exit-130 receipt and supersession
reason remain in `results/merged-aot-rebaseline-20260929/`. A separate campaign
uses the verified CI image under `results/trunk-aot-rebaseline-20260929/`.

The harness revision selected before the run is
`536d5823b796e2c2ca13bf35a9bcef4ffedcc902`. Its feature-campaign implementation
subsequently landed in [GeoBench PR 23](https://github.com/honua-io/geobench/pull/23)
with integration fixes, at `64669b6f86f4afce635fdd4c02945719f759fc3f`.
The running campaign keeps its original harness revision.

## Comparison contract

Both products read their own source-backed PostGIS copy of the deterministic
100K-point dataset, with 100-feature pages, stable ID ordering, all ten requested
attributes, geometry in CRS84, exact counts, anonymous reads, and identity
compression. Every response is checked against precomputed PostGIS expectations.
Server and database budgets are each 4 CPU / 4 GiB, with six source-query
connections. Exact response caching and adaptive admission are disabled; normal
metadata caches remain enabled.

The baseline and tuned profiles remain separate. The tuned profile only adds
`Database__DisableJitForSourceSpatialCounts=true`; it does not enable forced serial
feature reads. This setting controls PostgreSQL's query JIT and does not turn the
Honua Native AOT executable into a .NET JIT build. Executed SQL must confirm the
scoped setting before attributing a result to it.

The separate SQL preflight now confirms four executed spatial counts in each
profile. In the tuned Honua trace, each follows
`SELECT pg_catalog.set_config('jit', 'off', true)` and uses the scoped count's
distinct `SELECT ALL COUNT(*)` query identity. The baseline trace contains no
such settings. `count-profile-sql-proof.json` retains the observations and source
trace hashes. Tuned Honua passed its four selected smoke scenarios with no invalid
responses, and the matching GeoServer campaign also passed. Sustained performance
measurements are pending.

| Component | Immutable local image identity |
|---|---|
| GeoServer 3.0.1 with matching OGC API extension | `sha256:a395701a5eea4884c855f136be84363d0ce05e06da1ea6c7e3b84e146279927b` |
| PostGIS | `sha256:01a6a70e41e6c4467c8f55f6063555ed72db2d6662cd0d571040d42eadaeb6f6` |
| k6 | `sha256:1f40432b1cbe7234e977f96c362c9bc550a2d2b583d014dd8669fe40d3e9e755` |

The selected Honua image identity is recorded in the new campaign build receipt
and must pass runtime preflight. An image tag alone is insufficient evidence.

## Scheduled measurements and interpretation

Initial smoke campaigns check both products and the separate tuned profile.
Their two-second warmup and three-second measurement establish correctness and
runtime readiness only; they cannot support a capacity claim.

Sustained diagnostics use three paired repetitions, a 30-second warmup and a
30-second measurement per scenario, seed 42, fresh isolated stacks per pair,
and explicit drain phases. They cover mixed load at 10 VUs in both profiles,
all eleven individual baseline corpus requests, and medium/large bbox requests
with count JIT disabled. Other concurrency and arrival-rate settings receive
smoke coverage only at this stage.

The first baseline mixed-workload pair has completed at 10 VUs, with 30 seconds
of warmup and 30 seconds of measurement. Both attempts passed their correctness
and fairness checks. Two further paired repetitions and the count-tuned campaign
remain pending; this is an individual shared-host observation, not a completed
campaign conclusion.

| Repetition | Honua requests/s | GeoServer requests/s | Honua p95 ms | GeoServer p95 ms |
|---|---:|---:|---:|---:|
| 1 | 23.87 | 41.47 | 920.49 | 448.22 |

This pair favors GeoServer on both metrics. Honua's sampled database pressure
reached six active source queries and five parallel workers; GeoServer reached
four active source queries and no observed parallel workers. These observations
support further count-planning investigation, without establishing a causal
speedup or a reason to force serial execution. The campaign's partial readout
retains individual completed pairs and explicitly marks the campaign incomplete.

Report each scenario's throughput and p50/p95/p99 latency, all repetitions,
paired ratios and ranges. Do not combine percentiles or use a single winner
score. The first milestone can be near parity or mixed wins and losses, assessed
separately for throughput and tail latency. A first article should describe those
results and acknowledge GeoServer's strengths; a later article can document further
improvements when new measurements support them. Neither outcome is predetermined.
A 10% working margin is
not a statistical equivalence test, especially on this shared host. The longer
term objective remains improvement across measured scenarios.

The prefix corpus has a known coverage limitation: GeoServer loses the escaped
underscore in executed SQL, but the generated feature names do not distinguish
the two meanings. These results cannot establish general literal-prefix
correctness. Rendering, tiles, WFS, GSR, non-point geometries and larger datasets
remain outside this campaign.

Local evidence is retained under
`results/trunk-aot-rebaseline-20260929/`, with the superseded local attempt retained
in `results/merged-aot-rebaseline-20260929/`: build and campaign receipts, immutable
image metadata, source merge proof, raw observations, campaign manifests,
per-attempt reports and failure ledgers. These generated files are gitignored.
Shared-host observer calibration has not passed publication requirements, and
there is no isolated-generator calibration. Diagnostic validity must not be
reported as publication validity.

## Next optimization informed by the source review

A page-first strategy could avoid an exact-count query when a bounded first page
is short. The saved oracle contains 35 matches for the small bbox and one for the
boundary case. All mixed-workload requests exceed the 100-feature limit, so this
strategy would still need their exact counts and would not remove a mixed-workload
round trip. Empty queries already take one SQL statement in the count-first path.
This follow-up is implemented separately under
[issue 5313](https://github.com/honua-io/honua-server/issues/5313), preserving
security, distinct-query semantics, offsets, and existing full-page concurrency
semantics. All 1,682 Postgres tests passed on each of PostgreSQL 16, 17, and 18 at
commit `865cd6a36cebf6740cfc771b63cab69c4810967e`, and the full build and formatting
check passed. [PR 5315](https://github.com/honua-io/honua-server/pull/5315) is open
for normal review and merge. It is not part of the selected CI image and will
need its own AOT measurements.

Review subsequently identified a concurrent-write edge case: after a full first
page is fetched, deletes can make the later count smaller than that page, and a
zero count currently discards it. Six deterministic regression cases were added
at `adddea4f8d25f575086cafbf5085f09239d67428` in
[run 36523173989](https://github.com/honua-io/honua-server/actions/runs/36523173989).
PostgreSQL 17 and 18 each reproduced exactly two failures (later counts of zero
and one after fetching two rows), with 1,686 other tests passing. The equal and
increasing-count controls passed. Commit
`4a2a80544081875659b980977e0dda0983701a02` preserves the fetched page and floors
the later total at its size. In
[run 36523993300](https://github.com/honua-io/honua-server/actions/runs/36523993300),
PostgreSQL 16, 17 and 18 each passed all 1,688 tests, including all six concurrency
cases. Full solution build passed with zero warnings/errors, and formatting
verification passed at the same revision. The [review finding was resolved with evidence](https://github.com/honua-io/honua-server/pull/5315#discussion_r4129824810),
and the required Review Gate is green. The remaining PR Gate checks and other
workflow jobs are still running; the PR has not merged yet.
