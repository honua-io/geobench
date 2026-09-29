# AOT feature rebaseline — September 29, 2026

This campaign measures the merged source-query optimizations against GeoServer
on the shared WSL development host. It is diagnostic evidence for optimization,
not a publishable performance comparison. The production amd64 Native AOT image has now passed its hosted-CI verification
and local identity checks. Both products passed the 20-scenario baseline smoke
campaign with no invalid responses. The paired tuned smoke campaign also passed.
All three baseline mixed-workload pairs are complete and favor GeoServer: median
paired Honua/GeoServer throughput is 0.576 and p95 latency is 2.054. The sustained
count-tuned campaign is also complete: its paired throughput ratio is 0.809 and
p95 ratio is 1.339. Neither profile has established parity on this mixed workload.
The [previous diagnostics](feature-followup-20260928.md) favored GeoServer by
roughly 2× on mixed-workload throughput; source-level improvements do not replace
a fresh measurement.

## Changes and source identity

These server changes reached trunk through the normal PR lander and are present
in the measured image. The count-tuning change was subsequently reverted by
PR 5318; its restoration is pending as described below.

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
mixed-workload measurements are complete below; individual spatial rows remain pending.

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

All three baseline mixed-workload pairs completed at 10 VUs, with 30 seconds
of warmup and 30 seconds of measurement. All six attempts passed their correctness
and fairness checks, with no invalid responses, cancellations or dropped
iterations. Each measurement phase had ten late completions, reported separately
from measured completions. Warmup has its own drain accounting.

| Repetition | Honua requests/s | GeoServer requests/s | Honua p95 ms | GeoServer p95 ms |
|---|---:|---:|---:|---:|
| 1 | 23.87 | 41.47 | 920.49 | 448.22 |
| 2 | 23.10 | 47.53 | 1065.23 | 388.61 |
| 3 | 21.03 | 35.10 | 1009.26 | 499.87 |
| Median of repetitions | 23.10 | 41.47 | 1009.26 | 448.22 |
| Range | 21.03–23.87 | 35.10–47.53 | 920.49–1065.23 | 388.61–499.87 |

The median paired Honua/GeoServer throughput ratio is **0.576**, range
**0.486–0.599**. The paired p95 ratio is **2.054**, range **2.019–2.741**.
These are ratios computed within each pair; the table's median p95 values
summarize repetitions and are not combined latency percentiles. Full p50/p95/p99
and completion counts are retained in `mixed-baseline/report.json`.

One auxiliary HTTP timing anomaly occurred in GeoServer repetition 2. The
diagnostic latency uses monotonic executor progress and includes receiving and
validating the response, as defined in the harness. The report is valid for
diagnostics and explicitly **not publishable**: the local wall clock is unsuitable,
this is diagnostic mode, and isolated-generator calibration is missing.

All pairs favor GeoServer on both metrics. In the first pair, Honua's sampled database pressure
reached six active source queries and five parallel workers; GeoServer reached
four active source queries and no observed parallel workers. These observations
support further count-planning investigation, without establishing a causal
speedup or a reason to force serial execution. Readouts for still-running campaigns
retain individual completed pairs and explicitly mark those campaigns incomplete.

The separate count-tuned campaign has now completed all three pairs with the same
runtime image and workload. All six attempts passed semantic and fairness checks,
with zero invalid responses, cancellations or dropped iterations. Each measured
phase recorded ten drain completions separately.

| Repetition | Honua requests/s | GeoServer requests/s | Honua p95 ms | GeoServer p95 ms |
|---|---:|---:|---:|---:|
| 1 | 25.73 | 31.80 | 756.54 | 564.87 |
| 2 | 32.10 | 38.63 | 645.72 | 490.17 |
| 3 | 29.97 | 47.60 | 682.32 | 374.25 |
| Median of repetitions | 29.97 | 38.63 | 682.32 | 490.17 |
| Range | 25.73–32.10 | 31.80–47.60 | 645.72–756.54 | 374.25–564.87 |

The count-tuned median paired Honua/GeoServer throughput ratio is **0.809**, range
**0.630–0.831**. The paired p95 ratio is **1.339**, range **1.317–1.823**. GeoServer
leads both metrics in every pair. Full p50/p95/p99 values and completion accounting
are retained in `mixed-count-jit-off/report.json`. GeoServer had four auxiliary
negative HTTP timings during measurement and two during warmup. As with the
baseline, the custom latency uses monotonic executor progress, and publication is
blocked by the clock anomalies, diagnostic mode and missing calibration.

The tuned campaign shows a smaller paired gap than the baseline, but the two
campaigns ran at different times on a shared host. This does not isolate the
setting's causal speedup. Individual-query results and the queued serial-read
profiles will determine the next optimization priority.

The completed mixed runs can also be split by request type using the raw
`feature_latency` samples. The analysis verifies each raw file's recorded hash and
completion counts, selects only semantically valid measurement completions, and
uses every selected sample once. These are latencies under mixed traffic, not
standalone per-request throughput tests.

| Request in count-tuned mixed traffic | Median paired Honua/GeoServer p95 | Paired range |
|---|---:|---:|
| Equality | 1.010 | 0.949–1.359 |
| Numeric range | 0.887 | 0.878–1.132 |
| Tested prefix | 0.652 | 0.620–0.848 |
| Medium bbox | 1.478 | 1.312–1.843 |

Ratios below one favor Honua. The prefix case favors Honua in all three pairs;
equality and range are mixed. This is evidence for the particular corpus query,
not a general literal-prefix claim: the escaped-underscore coverage limitation
still applies. Medium bbox remains slower in every pair and contributes a median
60.8% of Honua's summed valid response latency despite making up 40% of the mixed
request sequence. That share includes waiting, transfer and validation; it is not
CPU utilization. The spatial page/count path is therefore the first diagnostic
priority. `mixed-request-breakdown.json` retains all per-repetition counts,
percentiles, latency shares, paired ratios and raw hashes; the adjacent
`geobench-mixed-request-breakdown.py` reproduces the breakdown.

The individual-query baseline has completed its first matched pair. The table
below retains all eleven rows, including losses; two more pairs are scheduled.
These use the default Honua planner profile, not the count-tuned profile above,
and do not establish a completed campaign result.

| Request, pair 1 only | Honua requests/s | GeoServer requests/s | Honua p95 ms | GeoServer p95 ms |
|---|---:|---:|---:|---:|
| Equality | 66.07 | 59.37 | 284.23 | 307.84 |
| Numeric range | 64.43 | 64.70 | 278.26 | 293.03 |
| Tested prefix | 74.47 | 43.60 | 256.67 | 382.32 |
| Small bbox | 160.20 | 161.30 | 115.95 | 119.71 |
| Medium bbox | 7.67 | 40.03 | 2012.53 | 387.14 |
| Large bbox | 5.97 | 16.60 | 2260.68 | 832.91 |
| Shallow page | 53.00 | 66.93 | 312.63 | 270.82 |
| Medium page | 55.37 | 56.17 | 307.75 | 329.44 |
| Deep page | 35.77 | 22.10 | 420.61 | 720.06 |
| Empty query | 336.63 | 451.20 | 63.50 | 54.30 |
| Bbox boundary | 202.40 | 398.87 | 102.43 | 53.93 |

Both attempts passed all eleven semantic and fairness checks. Honua leads both
metrics for equality, the tested prefix and deep pagination in this pair. Range,
small bbox and medium-page throughput are close; broad bboxes, shallow pagination,
empty queries and the boundary case remain optimization targets. The unmerged
first-page reuse change is not in this image. Remaining repetitions, the spatial
count-tuned campaign and the separately queued serial profiles must complete
before a profile-level conclusion.

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
and both required PR Gate and Review Gate are green. The PR has not merged:
trunk's failure brake is active after
[run 36520583030](https://github.com/honua-io/honua-server/actions/runs/36520583030).
[Repair PR 5318](https://github.com/honua-io/honua-server/pull/5318) merged at
`37972ef26` on September 29 at 05:55 UTC, reverting the scoped count-JIT change
because its tests exposed the pooled-session
smallint fixture assumption. The isolated 12-line fixture correction is already
in this verified candidate at commit `64eaf870caba390f8cd46d262f13147b2245b067`.
The first-page PR's merge conflict is now resolved at
`f4265d5d670486ebba81208584bd9fb72de5fdee`, which merges actual trunk and restores
the tuning dependency alongside the tested fixture correction. All ten
optimization paths remain byte-identical to the previously verified `4a2a805`
candidate. Fresh [CI run 36529383205](https://github.com/honua-io/honua-server/actions/runs/36529383205)
passed all 1,688 tests on PostgreSQL 16, 17 and 18 at this reconciled revision,
plus the full solution build and formatting verification. Required PR gates and
the separate [hosting rollback PR 5317](https://github.com/honua-io/honua-server/pull/5317)
remain pending. That repair now has ten new regression cases and a candidate
retaining externally supplied mount paths; its baseline and candidate validation
are still in progress. No whole-workflow pass is claimed. Future AOT images must be checked
for that content; the current benchmark image remains the immutable `6e4962b`
snapshot with the count-tuning option present.

An isolated Git-index rehearsal confirmed the modify/delete conflict in the
count-tuning tests. Retaining the updated regression file and restoring the
original tuning patch produced a recovery tree whose ten optimization paths
match the verified candidate exactly. `rollback-recovery-rehearsal.json` records
the tree identities and both patch-application attempts. This changed neither
branch and is not new CI evidence. The later actual reconciliation is recorded
separately in `landed-rollback-reconciliation.json` and was pushed as a normal
fast-forward to PR 5315 without changing the other repair agent's checkout.

[GeoBench PR 25](https://github.com/honua-io/geobench/pull/25) adds separately
fingerprinted serial spatial-read and combined count/read planner profiles. It
requires the selected transaction-local settings to execute before their matching
source queries on the same backend, and revalidates the raw SQL at report time.
All 56 harness tests, Ruff, Python compilation, JavaScript syntax and ShellCheck
passed at `879b9610b0587b45916ab25b67a09403b27f731b` in
[run 36528776047](https://github.com/honua-io/geobench/actions/runs/36528776047).
End-to-end checks remain pending. A sequential driver queues both profile
smokes and three-pair mixed diagnostics after the existing campaigns, using the
same immutable AOT image. These are additional diagnostics, not measured wins.
