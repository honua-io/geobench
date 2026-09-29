# AOT feature rebaseline — September 29, 2026

The earlier first-page image's best completed tuned mixed campaign combines serial feature reads with
count-specific PostgreSQL JIT suppression on the production Native AOT first-page
image. Median paired Honua/GeoServer throughput is **0.946** (range
**0.846–1.110**) and p95 latency is **1.073** (range **0.858–1.168**). Honua wins
one pair and loses two on both metrics. This is near parity in this local tuned
mixed-workload diagnostic, not evidence of parity across all individual requests.
All semantic checks passed. Generator headroom and shared-host variability limit
interpretation. The newer serial-count AOT image has passed its production build
and image checks. All six scheduled smoke profiles passed on both products;
its untuned mixed baseline completed at throughput H/G **0.532** and p95 H/G
**2.471**. On the new image, count-JIT-off alone completed at throughput H/G
**0.598** and p95 H/G **1.768**. Serial counts alone completed at throughput H/G
**0.859** and p95 H/G **1.471**. Serial counts plus count-JIT suppression completed
at throughput H/G **0.887** and p95 H/G **1.236**; GeoServer leads all three pairs
for both count profiles. Combined read/count comparisons are running.

These are optimization diagnostics on the shared WSL development host, not
publishable comparisons. The original image's results below remain identified
separately; the latest image and results are in the final section. Neither a
cross-build improvement nor parity follows from measurements taken at different
times on this shared host.

## Changes and source identity

These server changes reached trunk through the normal PR lander and are present
in the measured image. The count-tuning change was subsequently reverted by
PR 5318 and restored with the first-page optimization in PR 5315. The tables in
the original campaign sections below describe that original image. The final section records the subsequent first-page image and its separate
HTTP results. The serial-count implementation has merged, its new AOT image has
passed verification, and its completed and pending measurements are recorded below.

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
mixed-workload and individual spatial measurements are complete below.

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
setting's causal speedup. A retrospective audit of the seven-repetition saved
SQL plans makes that distinction concrete: **zero of seven medium-bbox exact
count plans used JIT**, and both ordinary and JIT-disabled variants launched one
parallel worker. Their elapsed-time difference does not establish a benefit from
removing compilation. Large and world exact counts did contain JIT in all seven
plans. These are saved SQL diagnostics, not plans captured during the current
HTTP run; `saved-plan-audit.json` retains each plan hash, JIT presence and worker
observations. Serial
page/count pressure therefore remains a separate hypothesis requiring its own
measurements. Individual-query results and the queued serial-read profiles will
determine the next optimization priority.

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

The individual-query baseline has completed all three matched pairs at 10 VUs,
with 30-second warmups and 30-second measurement windows. All six attempts
passed semantic and fairness checks across all eleven requests. This is the
default Honua planner profile, not the count-tuned profile above, and it does
not include the unmerged first-page optimization.

The tested prefix and deep pagination favor Honua in the median paired
comparisons for both throughput and p95, but neither wins every pair. All other
rows favor GeoServer on both median paired metrics. Broad bboxes remain the
largest, most consistent gaps. These results do not establish near parity overall.

Ratios below compare Honua with GeoServer within each matched pair. Higher
is better for throughput; lower is better for p95. Each entry gives the median
paired ratio and its full three-pair range. No latency percentiles are averaged.

| Request | Throughput H/G, median [range] | p95 H/G, median [range] |
|---|---:|---:|
| Equality | 0.848 [0.730–1.113] | 1.190 [0.923–1.289] |
| Numeric range | 0.824 [0.597–0.996] | 1.111 [0.950–1.540] |
| Tested prefix | 1.123 [0.631–1.708] | 0.962 [0.671–2.067] |
| Small bbox | 0.660 [0.454–0.993] | 1.519 [0.969–2.224] |
| Medium bbox | 0.192 [0.165–0.203] | 5.198 [4.527–5.381] |
| Large bbox | 0.386 [0.359–0.449] | 2.600 [1.973–2.714] |
| Shallow page | 0.684 [0.651–0.792] | 1.425 [1.154–1.478] |
| Medium page | 0.718 [0.675–0.986] | 1.450 [0.934–1.592] |
| Deep page | 1.292 [0.974–1.618] | 0.743 [0.584–1.125] |
| Empty query | 0.653 [0.643–0.746] | 1.374 [1.170–1.574] |
| Bbox boundary | 0.507 [0.454–0.723] | 1.899 [1.275–2.217] |

| Request, pair 1 | Honua requests/s | GeoServer requests/s | Honua p95 ms | GeoServer p95 ms |
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

| Request, pair 2 | Honua requests/s | GeoServer requests/s | Honua p95 ms | GeoServer p95 ms |
|---|---:|---:|---:|---:|
| Equality | 52.03 | 61.37 | 347.75 | 292.22 |
| Numeric range | 49.40 | 59.97 | 338.19 | 304.53 |
| Tested prefix | 61.60 | 54.83 | 290.50 | 301.94 |
| Small bbox | 100.93 | 152.97 | 200.90 | 132.22 |
| Medium bbox | 6.83 | 33.73 | 2079.86 | 459.48 |
| Large bbox | 5.87 | 15.20 | 2345.62 | 902.05 |
| Shallow page | 49.87 | 72.93 | 357.30 | 250.65 |
| Medium page | 50.00 | 69.67 | 373.36 | 257.40 |
| Deep page | 31.37 | 32.20 | 542.62 | 482.40 |
| Empty query | 222.97 | 346.83 | 95.16 | 69.24 |
| Bbox boundary | 202.47 | 280.07 | 98.04 | 76.89 |

| Request, pair 3 | Honua requests/s | GeoServer requests/s | Honua p95 ms | GeoServer p95 ms |
|---|---:|---:|---:|---:|
| Equality | 38.30 | 52.50 | 455.92 | 353.57 |
| Numeric range | 34.93 | 58.47 | 497.94 | 323.41 |
| Tested prefix | 25.93 | 41.07 | 867.18 | 419.61 |
| Small bbox | 57.80 | 127.23 | 367.17 | 165.09 |
| Medium bbox | 5.80 | 35.23 | 2527.58 | 469.76 |
| Large bbox | 5.83 | 13.00 | 2301.45 | 1166.23 |
| Shallow page | 42.63 | 65.47 | 403.21 | 272.74 |
| Medium page | 37.87 | 56.07 | 508.27 | 319.23 |
| Deep page | 24.33 | 18.83 | 639.01 | 860.32 |
| Empty query | 155.97 | 238.67 | 144.76 | 91.95 |
| Bbox boundary | 126.27 | 278.20 | 165.39 | 74.60 |

The measurement windows contain 73,529 valid Honua completions and 106,361
valid GeoServer completions across the 33 sequential scenarios per product,
with zero invalid responses or cancellations. The 337 Honua and 335 GeoServer
late completions are reported separately. These totals are completion accounting,
not an overall throughput or winner score. All p50/p95/p99 values, warmup/drain
counts and per-repetition ranges remain in `features-baseline/report.json`.
The report records seven auxiliary clock anomalies for Honua and 18 for
GeoServer; diagnostic latency uses monotonic executor progress. Clock anomalies,
diagnostic mode and missing calibration keep the report explicitly not publishable.

Hash-verified telemetry also shows substantial variation. Across samples labelled
measurement-and-drain, median one-minute host load for Honua/GeoServer was
16.02/15.42 in pair 1, 21.46/14.21 in pair 2 and 26.11/30.59 in pair 3. Collector
passes reached 15.29 seconds, so a nominal five-second cadence does not guarantee
five-second coverage. Host load includes the benchmark itself as well as other
work; sparse, non-instantaneous samples cannot assign latency differences to
interference. Collector elapsed time is not CPU utilization or a measured
throughput penalty. `feature-telemetry-analysis.json` and its adjacent
`analyze-feature-telemetry.py` retain the per-scenario values and hashes.

The separate spatial count-tuned campaign completed all three pairs. All six
attempts passed semantic and fairness checks and cleaned up their owned stacks.
The same production AOT image, 10 VUs, 30-second warmup and 30-second measurement
were used; this profile disables PostgreSQL JIT only for eligible spatial counts.

| Bbox | Pair | Honua requests/s | GeoServer requests/s | Honua p95 ms | GeoServer p95 ms |
|---|---:|---:|---:|---:|---:|
| Medium | 1 | 12.20 | 20.57 | 1165.64 | 709.46 |
| Medium | 2 | 12.50 | 24.50 | 1169.85 | 663.48 |
| Medium | 3 | 13.13 | 37.53 | 1101.66 | 455.17 |
| Large | 1 | 12.00 | 8.80 | 1195.65 | 1863.79 |
| Large | 2 | 14.67 | 9.87 | 941.29 | 1481.29 |
| Large | 3 | 10.57 | 17.10 | 1373.04 | 837.54 |

| Bbox | Paired H/G throughput median [range] | Paired H/G p95 median [range] |
|---|---:|---:|
| Medium | 0.510 [0.350, 0.593] | 1.763 [1.643, 2.420] |
| Large | 1.364 [0.618, 1.486] | 0.642 [0.635, 1.639] |

There were 2,252 valid measured Honua completions and 3,551 GeoServer
completions, with 60 drain completions per product and zero invalid responses or
cancellations. These totals are completion accounting, not an aggregate winner score.
Full p50/p95/p99 values and per-product repetition medians/ranges remain in
`spatial-count-jit-off/report.json`. All recorded artifact hashes were checked
before generating these tables; `documentation-receipt.json` records that check.

Medium bbox favors GeoServer in every pair. Large bbox favors Honua in the first
two pairs and GeoServer in the third: its favorable median is not a consistent
win. The report remains diagnostic and not publishable; isolated-generator
calibration is missing. Comparing this separately timed campaign with the baseline
does not establish an option-only speedup on the shared host.

The serial-planner queue has now started its first smoke campaign. Its separate
mixed-workload measurements follow both profile smokes. The first-page optimization
still needs a new production AOT build and its own measurements.

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
plus the full solution build and formatting verification. Both required gates
are green at `f4265d5`: [PR Gate run 36529753831](https://github.com/honua-io/honua-server/actions/runs/36529753831)
and Review Gate. The separate [hosting rollback PR 5317](https://github.com/honua-io/honua-server/pull/5317)
has now merged. The repair candidate `768c934d5` retains externally supplied mount paths.
Its [PR Gate catalog shard](https://github.com/honua-io/honua-server/actions/runs/36532952643/job/109291815080)
passed all 266 tests, including all ten new mounted-host cases confirmed from
the named TRX results. Full solution build and formatting also passed.
The [tests-first baseline](https://github.com/honua-io/honua-server/actions/runs/36532387799/job/109290386798)
reproduced exactly nine expected mounted-URL assertion failures, with 257 passes
and no skips. The unconfigured attachment control and all existing cases passed.
All four review findings are resolved with evidence, and both required PR Gate
and Review Gate passed at the same candidate revision. The repair merged into
trunk as `8f2c9a68450778e7622eb1aa228d21225b140e34`. A per-path Git comparison
confirms that all five URL fixes and the mounted-host test file exactly match
the tested candidate, and the automatic alias middleware remains absent. The
trailing trunk matrix must clear the failure brake before normal optimization
landings resume. The [full candidate CI matrix](https://github.com/honua-io/honua-server/actions/runs/36532839829)
subsequently passed: 104 successful jobs and two skipped jobs, with no failures.
Its AOT verification completed on September 29 at 08:07 UTC. That reduced-profile
compile is not a production serving-image build, and the candidate result does
not replace the repaired-trunk matrix. `candidate-ci-final.json` and its hash
are retained with the hosting repair evidence. Future AOT images must be checked
for that content; the current benchmark image remains the immutable `6e4962b`
snapshot with the count-tuning option present.

A later review correction narrowed the expected cancellation exception in the
count-tuning regression test, advancing PR 5315 to
`547eae82565df1f255b79601c97e7a32b1ac817e`. Both required gates passed at this
head: [PR Gate run 36541206062](https://github.com/honua-io/honua-server/actions/runs/36541206062)
and Review Gate. The earlier PostgreSQL matrix evidence belongs to `f4265d5`,
not this new head.

The older trunk run `36533906528` has completed with the two known hosting
failures and their failed summary gates. It predates the merged hosting repair.
A separate operational problem was preventing current runs from reaching the
watcher: GitHub's branch-filtered workflow listing repeatedly returned September
4 runs, while an unfiltered listing with an exact local trunk filter returned
September 29 runs. [Flow PR 97](https://github.com/honua-io/honua-flow/pull/97)
merged at `91b7d0513d0c8d0b60dfcb0f04603829892c15e1` after offline discovery,
full landing/crash-recovery, dashboard and hosted checks passed. It preserves
existing merge gates and fails closed on unavailable evidence. Normal fleet sync has picked up the repair and its two runtime files match
the tested content. The normal watcher then recognized the stale failure and dispatched
[full trunk matrix 36544117214](https://github.com/honua-io/honua-server/actions/runs/36544117214)
at repaired revision `8f2c9a6`. That run must still pass before the server brake
can clear; successful dispatch is not a green matrix. The read-only reproduction and
verification receipt are retained in `results/trunk-ci-discovery-20260929/`.

The repaired-trunk matrix reported one failure in
[Core and Cloud Contracts](https://github.com/honua-io/honua-server/actions/runs/36544117214/job/109326553516):
372 tests passed and the migrated client-compatibility seed test failed when its
first count request returned 500. The correlated exception is an unresolved
`IMetadataV2GraphProvider` while activating `ResourceValidator`. This matches
the dependency-resolution failure documented in
[issue 4640](https://github.com/honua-io/honua-server/issues/4640) and the repository's
known-flake instructions. Those instructions call for a failed-shard rerun;
they do not establish that this attempt passed or prove the underlying cause.
The raw job log is retained as `repaired-trunk-core-cloud.log`, SHA-256
`972b11e42e6cdc560159563475b3640925dd42363d61cbea0d892053c026f81d`.
The first matrix attempt finished with 100 successful jobs, two skipped jobs,
and four failures: this shard, Catalog and ImageServer Support, and the two
summary gates. The catalog shard exhausted its 18-minute test budget while still
producing output four seconds earlier; no test assertion failure was reported
before termination. Both previously failing hosting shards passed. The normal
watcher issued its failed-job retry, now queued as attempt 2 of the same run.
The original failed attempt and raw catalog log remain retained; a queued retry
does not clear the server failure brake.

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
The serial-read smoke has now passed on both products for equality, small/medium/large
bboxes and deep pagination, with zero invalid responses or cancellations. Its SQL
proof records four scoped feature queries and zero scoped counts; all recorded
artifact hashes were verified in `smoke-serial-reads/verification-receipt.json`.
The combined count/read smoke also passed on both products with zero invalid
responses or cancellations. Its SQL proof records four scoped counts and four
scoped feature queries. Both campaigns cleaned their owned resources, and all
244 recorded artifact hashes were independently checked. The combined report's
SHA-256 is `53c1f52bb21c12e1f04fee716fd37234e1bc7a331a71161747bbf00541f91a96`.
PR 25 merged as `25697e8405fd01884c49cc64000b13bfeb4e86ea`; all eight changed
paths match the tested revision. The running diagnostics retain harness
`879b9610b0587b45916ab25b67a09403b27f731b` and the same immutable AOT image.
Smoke results establish correctness and profile activation, not capacity.

The original queue supervisor disappeared while its first sustained campaign
remained alive. Its interruption is recorded in the original queue receipt,
with the prior receipt preserved separately. A detached recovery supervisor
reacquired the shared build slot and observes that exact surviving process,
checking its process start identity and campaign fingerprint. It does not
restart or resume the live campaign. Only after all six attempts, artifact
hashes, cleanup and report validity pass can it start the previously scheduled
combined-profile campaign. `recovery-receipt.json`, `recovery-driver.py` and
`recovery-driver-provenance.json` retain this operational evidence under
`results/serial-planner-diagnostics-20260929/` in the serial-profile worktree.
That first supervisor interruption's cause is unknown.

At approximately 09:19 UTC, the locked serial-profile worktree itself disappeared,
terminating the surviving campaign and recovery supervisor. Five attempts had
passed and the sixth GeoServer stack was provisioning, but the campaign never
completed. The Git worktree registration and explicit lock remained. The mounted
results directory was empty, and the original raw serial-profile smoke and
sustained artifacts are no longer available. The earlier smoke checks above
describe verification performed before the loss; they cannot substitute for
retained raw evidence in a new campaign. No partial sustained result is promoted
to a campaign conclusion. The completed baseline and count-tuned campaigns in
the main evidence directory were unaffected.

The cleanup script ignored worktree locks and recursively deleted a directory
after any refusal from `git worktree remove`. Offline real-Git tests reproduced
this deletion for locked trees, late-acquired locks and arbitrary removal
failures. [Flow PR 99](https://github.com/honua-io/honua-flow/pull/99) removes that
fallback, checks protection before archival and deletion, and reports refusals
without claiming removal. Nine regression cases and the required dashboard
checks pass. The fix merged as `7dca2100d81328bdd6c9e8ea362afc788544be82` after
[hosted CI](https://github.com/honua-io/honua-flow/actions/runs/36550185095) also ran
and passed the nine regressions at `114597ad272a70a20b5b81fe7e1f69dc7be59160`. All
three merged paths match that tested revision. Normal fleet sync has picked up
the repair, and the live sweeper's complete file matches the tested content.
The loss receipt, surviving container logs, exact resource identities,
original lock and cleanup-test receipts are retained outside the deleted worktree
in `results/serial-planner-loss-20260929/`. Only the interrupted attempt's three
containers and its owned volume/network were removed after evidence capture.

A separately identified count-only diagnostic now uses a fresh harness worktree
and stores evidence directly in `results/source-count-pressure-20260929-r2/`
outside it. It starts only after the interrupted campaign's resources are cleaned
and both the shared build slot and measurement lock are acquired. Its two
PostgreSQL variants both disable JIT; they differ only in the transaction-local
parallel-worker setting. Three paired repetitions use one and six clients, a
small-bbox control and medium bbox, five-second warmups and ten-second measurement
windows with fully drained phases and every scalar count validated. This tests
a specific count-planning hypothesis, not HTTP throughput or a product winner.
The motivating saved plans launched one worker in all 14 medium-bbox cases,
but that worker scanned zero rows in 11 of them; all 14 saved artifact hashes
were checked. Neither the serial-read flag nor the combined profile forces
serial count execution, so the interrupted HTTP experiment did not test that
hypothesis directly. The completed count diagnostic is recorded below.

## Count-only parallel-worker results

All 24 scheduled trials passed. Every returned scalar count matched the oracle,
and transaction-local settings reverted after every trial. Independent verification
checked all 67 recorded artifact hashes and recomputed each trial's completions,
drain accounting and p50/p95/p99 from its raw samples. The measurement windows
contained 74,340 valid completions; 83 late completions were retained separately.
The owned fixture was cleaned. These remain SQL-only shared-host diagnostics:
Honua authentication, feature decoding and HTTP response work are absent.

Both variants disable PostgreSQL JIT. “Default workers” allows two workers per
gather; “serial” allows zero, scoped to the count transaction. Counts/s below
are measured valid completions within the ten-second window.

| Bbox | Clients | Repetition | Default counts/s | Serial counts/s | Default p95 ms | Serial p95 ms |
|---|---:|---:|---:|---:|---:|---:|
| bbox-small | 1 | 1 | 592.10 | 654.10 | 2.66 | 2.50 |
| bbox-small | 1 | 2 | 487.90 | 417.10 | 3.65 | 6.22 |
| bbox-small | 1 | 3 | 474.20 | 524.40 | 4.65 | 3.44 |
| bbox-small | 6 | 1 | 657.70 | 650.40 | 21.58 | 21.71 |
| bbox-small | 6 | 2 | 528.10 | 531.30 | 34.33 | 31.56 |
| bbox-small | 6 | 3 | 636.20 | 628.70 | 23.88 | 25.15 |
| bbox-medium | 1 | 1 | 18.90 | 34.70 | 101.23 | 58.18 |
| bbox-medium | 1 | 2 | 19.30 | 45.30 | 92.42 | 41.65 |
| bbox-medium | 1 | 3 | 28.20 | 54.90 | 53.79 | 29.20 |
| bbox-medium | 6 | 1 | 36.10 | 111.60 | 298.63 | 100.78 |
| bbox-medium | 6 | 2 | 32.10 | 113.40 | 319.79 | 100.53 |
| bbox-medium | 6 | 3 | 40.60 | 116.70 | 286.54 | 98.64 |

Paired ratios are **serial/default**, not Honua/GeoServer ratios.

| Bbox | Clients | Median throughput ratio (range) | Median p95 ratio (range) |
|---|---:|---:|---:|
| bbox-small | 1 | 1.105 (0.855–1.106) | 0.938 (0.740–1.701) |
| bbox-small | 6 | 0.989 (0.988–1.006) | 1.006 (0.919–1.053) |
| bbox-medium | 1 | 1.947 (1.836–2.347) | 0.543 (0.451–0.575) |
| bbox-medium | 6 | 3.091 (2.874–3.533) | 0.337 (0.314–0.344) |

Every medium-bbox pair favors serial counts on throughput and p95. Small bbox
is mixed with one client and near parity with six; this does not justify a
blanket default change. [Server issue 5322](https://github.com/honua-io/honua-server/issues/5322)
scopes an opt-in count-planning change with eligibility, transaction restoration,
prepared-plan isolation, correctness tests and a production AOT HTTP rebaseline.
The SQL result supplies a reason to implement and measure that candidate; it
does not establish a Honua-versus-GeoServer speedup.

Summary SHA-256: `11f0b4e12ff4ce6d9c5dd3434911645ba01c43cea272726dc64f9c4cec0c75cd`.
`verification.json` retains the independent sample-accounting checks.

## First-page AOT rebaseline and serial-count follow-up

[PR 5315](https://github.com/honua-io/honua-server/pull/5315) merged into trunk
at `f34496e1893e17f974b4e5e330043078f8355b42`. It reuses exact totals from short
first pages and restores the independent count-specific PostgreSQL JIT option.
The production amd64 Native AOT build in
[run 36555577096](https://github.com/honua-io/honua-server/actions/runs/36555577096)
passed from subsequent trunk revision
`beac25991794543f96c79fac8fb9ed0745b136dd`. The exact amd64 job passed its
boundary check, GeoParquet smoke and image publication. Its immutable reference is
`ghcr.io/honua-io/honua-server@sha256:cbb62cbc230af7d07afd53ac5ab658300b9c249cc7e2bd656a0c478cbb764d39`.
The build log confirms the full production profile and speed-optimized Native
AOT publish; local runtime inspection records `/app/Honua.Server` with no CoreCLR
mapping. The complete workflow subsequently finished successfully.
This image includes PR 5315 but does not include the serial-count candidate below.

[Server PR 5323](https://github.com/honua-io/honua-server/pull/5323) implements the default-off
`Database:PreferSerialSourceSpatialCounts` option. Eligible source-backed point
envelope counts receive transaction-local zero parallel workers, independently
or together with JIT suppression. Four distinct prepared-statement identities
keep ordinary, JIT-only, serial-only and combined plans separate. The exact
count predicate, parameters, security restrictions and feature-read planning
are preserved; borrowed explicit and ambient transactions remain excluded.

The serial-only negative control failed in the ten expected cases before the
implementation. A combined-policy negative control then demonstrated that
enabling both flags still left JIT on; the final implementation fixes that
interaction. At implementation revision `c57159360d48a587bef413fb538a953727a85243`,
all 72 targeted regression cases passed, including pooling
restoration after errors/cancellation, actual generic parallel/serial plans,
boundary and empty counts, and existing first-page/JIT coverage. Formatting
verification passed. The complete unchanged provider suite passed all 1,724
cases on each of PostgreSQL 16, 17 and 18: 5,172 successful executions, with
all 72 targeted regression cases present in every leg. Independent checks
verified all six retained log/TRX hashes and individual test outcomes. Earlier
candidate failures remain in `results/source-serial-count-5322/`, alongside
the red/green TRX files, matrix receipts and logs. All three owned fixtures were
cleaned. That revision's full hosted PR Gate subsequently passed.

The current head, `02c3968117b62b1ab8cb920773da031330ad7fe7`, adds an assertion to
the cancellation test's cleanup handler in response to review. Production source
and documentation are byte-identical to the implementation revision. Both focused
cancellation cases passed after this test-only change. Its Review Gate and format
check passed, followed by the complete PR Gate and all six affected integration
groups at that exact head. The 5,172 provider executions above belong to the implementation
revision, not a repeat of the full matrix at the test-only follow-up head. The PR
merged through the normal lander at 12:03:45 UTC as
`2db24e648350927c3dada3eb00638bcec1e5cc3e`. Source and documentation on trunk
match the reviewed head exactly. The change is absent from the first-page AOT
image measured above.

[GeoBench PR 26](https://github.com/honua-io/geobench/pull/26) adds separate
serial-count and combined count profiles, plus combinations with the existing
serial page-read option. All eight settings combinations have distinct
fingerprints. At current harness head `d4a2009dfb11ed6db15ea6097a06b3f740b838ea`,
[CI 36566493767](https://github.com/honua-io/geobench/actions/runs/36566493767)
passed all 59 tests, Ruff, Python compilation, JavaScript syntax and ShellCheck.
Executed-SQL checks require both count settings before the same eligible count
and independent evidence for the feature-read setting. Missing flags, substituted
query targets and swapped backend evidence fail. All six scheduled production
AOT smoke pairs subsequently passed, and the PR merged normally as
`944b88996effc601ec08324a92b94b31072ecf19`. The active campaign keeps its tested
`d4a2009` fingerprint; integration CI on the merged harness is checked separately.

These implementation checks establish behavior, not a performance gain. The
serial-count candidate requires its own merged production AOT image and full
feature/mixed comparison. No broader protocol claim follows from the SQL-only
diagnostic.

Both first-page smoke profiles passed all twelve selected scenarios on both
products with zero invalid responses. Their two-second warmup and three-second
measurement establish correctness only. All three baseline mixed pairs also
completed, with 30-second warmup, 30-second measurement, ten VUs and seed 42.
Each attempt passed semantic and fairness checks and cleaned its owned resources.
An independent raw-sample recount verified artifact hashes, warmup separation,
measurement/drain completion accounting, request counts, throughput and
nearest-rank p50/p95/p99 for both smokes and the completed baseline campaign.

| Repetition | Honua requests/s | GeoServer requests/s | Honua p95 ms | GeoServer p95 ms |
|---|---:|---:|---:|---:|
| 1 | 73.70 | 181.07 | 292.24 | 86.23 |
| 2 | 98.73 | 177.97 | 204.82 | 91.47 |
| 3 | 96.83 | 182.30 | 208.88 | 85.42 |

The median paired Honua/GeoServer throughput ratio is **0.531**, range
**0.407–0.555**; paired p95 is **2.445**, range **2.239–3.389**. GeoServer leads
both metrics in all three pairs. Measurement had zero invalid responses and
cancellations; 10–11 late completions per attempt were excluded and retained
separately. Auxiliary clock anomalies, shared-host contention, diagnostic mode
and missing isolated-generator calibration prevent publication.

Within this mixed traffic, median paired p95 ratios are 1.890 for equality,
1.520 for numeric range, 1.074 for the tested prefix and 2.890 for medium bbox.
Medium bbox accounts for a median 61.7% of Honua's summed response latency while
representing 40% of the request sequence. This is response latency including
waiting and validation, not CPU attribution or standalone per-query throughput.
It keeps spatial count/page planning as the next optimization target.

Artifacts are retained outside the harness worktree under
`results/first-page-aot-rebaseline-20260929/`, including
`mixed-baseline/report.json`, `mixed-baseline-raw-verification.json` and
`mixed-baseline-request-breakdown.json`. The baseline report SHA-256 is
`12950ef80ef8fb334ddffea568ecfca777d78734d02a5fba7a939480bc1f6785`.
The count-JIT-off mixed campaign also completed all three pairs with the same
production image. Independent raw-sample verification passed, with zero invalid
responses or cancellations and 10–11 measurement drain completions per attempt.

| Repetition, count JIT off | Honua requests/s | GeoServer requests/s | Honua p95 ms | GeoServer p95 ms |
|---|---:|---:|---:|---:|

| 1 | 111.63 | 179.90 | 170.68 | 86.99 |
| 2 | 103.27 | 171.33 | 180.75 | 92.54 |
| 3 | 113.93 | 175.57 | 171.27 | 90.06 |

The tuned median paired throughput ratio is **0.621**, range **0.603–0.649**;
paired p95 is **1.953**, range **1.902–1.962**. GeoServer leads both metrics in
every pair. Medium-bbox p95 within mixed traffic is **1.888** times GeoServer's
(median paired ratio), accounting for a median **62.2%** of Honua's summed
response latency. Equality, range and the tested prefix have median paired p95
ratios of 1.441, 1.303 and 1.065 respectively. None establishes parity across
all measured requests. These request-type ratios describe latency within mixed
traffic, not independent throughput comparisons.

The smaller gap than the separate baseline run does not isolate the setting's
causal benefit. The earlier 0.809 throughput ratio belongs to the old image and
must not be presented as a result from this image. Both completed profiles remain
shared-host diagnostics, with auxiliary clock anomalies and no isolated-generator
calibration. Original and failed attempts remain retained.

The new tuned report and raw verification are
`mixed-count-jit-off/report.json` and `mixed-count-jit-off-raw-verification.json`;
request-level samples are summarized in
`mixed-count-jit-off-request-breakdown.json`. Report SHA-256:
`0cb9a97c0da7cdeb3f2ba4b70911c913961f39295ba9fe71c036cedbaaa11403`.

## Attribute projection diagnostic

After all four first-page HTTP campaigns finished, an isolated PostGIS pass
compared the existing JSONB/text attribute projection with native columns over
identical ordered pages. All eleven corpus requests returned equivalent IDs,
attribute values and point geometries against the oracle. Five randomized paired
repetitions per request produced 110 retained EXPLAIN ANALYZE plans. Both variants
used PostgreSQL JIT off, one client and the normal two-worker allowance. This is
SQL-only evidence: it excludes Npgsql decoding, Honua serialization and HTTP, and
includes EXPLAIN instrumentation overhead.

| Request | JSONB median execution ms | Native columns median execution ms | Median paired native/JSONB ratio |
|---|---:|---:|---:|
| equality | 0.856 | 0.197 | 0.247 |
| range | 0.770 | 0.127 | 0.158 |
| prefix | 0.795 | 0.138 | 0.184 |
| bbox-small | 0.357 | 0.155 | 0.385 |
| bbox-medium | 44.347 | 46.631 | 1.072 |
| bbox-large | 33.654 | 39.221 | 1.064 |
| page-shallow | 0.950 | 0.147 | 0.143 |
| page-medium | 0.822 | 0.316 | 0.327 |
| page-deep | 10.936 | 8.105 | 0.852 |
| empty | 0.038 | 0.037 | 0.974 |
| bbox-boundary | 0.092 | 0.088 | 0.826 |

Removing JSONB construction saves less than a millisecond in the simple-page
cases. Medium and large bbox plans still launch a parallel worker under a
Gather Merge, with startup dominating the short page scan. In the first medium
bbox JSONB plan, Gather Merge starts at 40.858 ms while its underlying index scan
finishes at 0.422 ms per loop. Native projection retains the same plan shape.
A native-column decoder remains a possible optimization, but this evidence keeps
spatial page/count planner overhead ahead of it. These SQL ratios are not
Honua/GeoServer ratios or predictions of HTTP gains.

All immutable SQL artifacts and row/plan counts were independently verified;
the exact owned fixture and its anonymous volumes were removed. The diagnostic
receipt also hashed the supervisor's control file while it was still running;
`queue-receipt.json` subsequently advanced to `passed`. That control-file hash
is stale. `verification.json` explicitly records this transition; all SQL, oracle,
result and plan hashes match. The first attempt that failed to obtain the shared
lock remains retained separately and produced no fixture or traffic.

Evidence lives in `results/source-projection-20260929-r2/`. The existing
`serial-reads` and `count-jit-off-serial-reads` profiles are now being tested against
the same first-page AOT digest in a separate queue under
`results/serial-read-first-page-aot-20260929/`, with their own paired GeoServer
runs and executed-SQL checks. Both mixed campaigns in that queue have completed, as recorded below. These profiles use the earlier
AOT image and do not include the serial-count change.

The serial-count production web AOT
[amd64 job 109397973600](https://github.com/honua-io/honua-server/actions/runs/36565949830/job/109397973600)
passed its build, serving-boundary verification, GeoParquet smoke and publication
steps from exact merged revision `2db24e648350927c3dada3eb00638bcec1e5cc3e`.
The pulled immutable image is
`ghcr.io/honua-io/honua-server@sha256:50aacf73ba6139a382e253319b008bcee136558286bd795bd5439839adda5d1c`.
Its architecture, source labels, web profile, Native AOT mode and entrypoint match
the recorded build. This claim applies to the web amd64 job: a separate Lambda
amd64 job in the workflow failed because Public ECR returned HTTP 429 for its
adapter image. No Lambda artifact or JIT image is substituted.

The supervisor started the diagnostic queue after the prior serial-read queue
completed. The queue verifies exact-head harness CI, source ancestry, immutable
images and dataset identity before any traffic.
Six profiles receive all-corpus smoke and three paired mixed repetitions:
baseline, count-JIT-off, serial-counts, count-JIT-off-serial-counts,
serial-reads-counts and count-JIT-off-serial-reads-counts. The baseline and both
joint page/count candidates then receive all eleven individual request
comparisons. The count-only mixed rows isolate that policy without repeating the
entire corpus for every settings combination. Completed smoke checks are recorded
below; no sustained serial-count HTTP comparison exists yet. Acquisition evidence is retained in
`results/serial-count-aot-rebaseline-20260929/build-receipt.json`; the build-log
SHA-256 is `03c0833c75bde055eae6b4c68f606e6aade8727642f04698b974c33342c49dda`.

## Completed serial-read-only mixed comparison

The existing serial feature-read option passed its full twelve-scenario smoke on
both products, as did the separate count-JIT-off/serial-read smoke. Revalidated
source SQL shows four scoped feature queries in each Honua smoke. The combined
profile also executes scoped JIT suppression before two spatial counts. Runtime
checks confirm Native AOT and the same `beac25991` source/image identity used by
the first-page campaigns. This is executed behavior, not just an environment flag.

The serial-read-only mixed campaign completed all three paired repetitions with
ten VUs, 30-second warmup and 30-second measurement. All attempts passed their
semantic/fairness checks and cleaned owned resources. An independent raw-sample
recount verified artifact hashes, complete pair coverage, warmup separation,
request counts, measurement/drain accounting and nearest-rank percentiles.

| Repetition | Honua requests/s | GeoServer requests/s | Honua p95 ms | GeoServer p95 ms |
|---|---:|---:|---:|---:|
| 1 | 115.37 | 167.13 | 166.25 | 92.68 |
| 2 | 137.30 | 171.93 | 132.64 | 91.39 |
| 3 | 131.47 | 174.63 | 143.57 | 90.74 |

Median paired throughput H/G is **0.753**, range **0.690–0.799**; p95 H/G is
**1.582**, range **1.451–1.794**. GeoServer leads both metrics in every pair. The
measurement windows contain zero invalid responses and cancellations; 10–11
late completions per attempt are retained separately. These remain shared-host
diagnostics, not publication evidence or proof of a causal improvement over the
separate baseline campaign.

Within mixed traffic, medium-bbox median paired p95 H/G is **1.755** (range
**1.634–1.908**). Equality is 1.532, numeric range 1.346 and the tested prefix
0.915. Prefix is mixed across repetitions (0.830–1.037); the other three request
types favor GeoServer on p95 in all pairs. This does not establish parity overall.
The separate count-JIT-off/serial-read campaign has now completed below.

Evidence is retained in `results/serial-read-first-page-aot-20260929/`, including
`smoke-sql-verification.json`, `mixed-serial-reads/report.json`,
`mixed-serial-reads-raw-verification.json` and
`mixed-serial-reads-request-breakdown.json`. The completed report SHA-256 is
`8b6fc3ee1cb9aa0bfae5a41b770bd89c84681013883f4d2ca2172d5c70d3acbf`.

## Telemetry scope and generator headroom

A retained phase breakdown separates pressure-probe and warmup telemetry from
`measurement-and-drain` samples. That label includes drain, so these are sampled
phase observations, not exact measurement-window utilization or true concurrency
peaks. Each value below is the range of per-repetition sample medians across the
completed serial-read-only mixed campaign; 100% denotes one logical core.

| Component | Honua runs, CPU percent | GeoServer runs, CPU percent |
|---|---:|---:|
| Server | 165.80–173.66 | 254.80–314.38 |
| Database | 399.84–405.08 | 387.52–392.25 |
| k6 generator | 225.58–240.00 | 380.68–389.63 |

Honua still has four to five sampled parallel workers in these phases despite
serial feature reads; its count policy remains the default in this profile.
GeoServer has no sampled parallel workers. The database pressure supports the
pending serial-count experiment. These samples do not attribute worker CPU to a
specific SQL statement.

The GeoServer generator is close to its four-core budget. This can limit the
local test's ability to distinguish server capacities when a faster Honua
candidate approaches parity; an apparent tie would need generator-headroom
validation. The current source validator also repeats expected-date parsing and,
when the property ID is absent, feature-ID parsing. Those are candidates for a
separately tested validator optimization, not changes made to these running
campaigns. Full attribute, ID, ordering, count and geometry validation must remain.

The standalone `phase-pressure.py` analysis verifies each retained telemetry hash
and writes `<campaign>-phase-pressure.json` beside the campaigns. The validator
source findings are retained in `validator-cost-review.json` under
`results/serial-read-first-page-aot-20260929/`. A subsequent synthetic validator
experiment is recorded below. It does not establish causal attribution of the
HTTP generator's CPU or satisfy publication calibration.

## Completed serial-read and count-JIT-off mixed comparison

This profile enables serial planning for eligible feature pages and PostgreSQL
JIT suppression for eligible spatial counts. It does not enable the new serial
count policy. All three pairs completed at ten VUs with 30-second warmup and
measurement phases. Independent raw verification passed, with zero invalid
responses and cancellations and 10–11 measured-phase drain completions per
attempt retained separately. All owned resources were cleaned.

| Repetition | Honua requests/s | GeoServer requests/s | Honua p95 ms | GeoServer p95 ms |
|---|---:|---:|---:|---:|
| 1 | 159.00 | 168.07 | 99.39 | 92.65 |
| 2 | 153.13 | 137.90 | 103.67 | 120.85 |
| 3 | 149.37 | 176.63 | 104.16 | 89.22 |

Median paired throughput H/G is **0.946**, range **0.846–1.110**; p95 H/G is
**1.073**, range **0.858–1.168**. Honua leads both metrics in pair 2 and trails
in pairs 1 and 3. This supports a near-parity observation for this tuned mixed
workload on this host; it does not establish a shipping-default result, consistent
wins, a causal gain over earlier campaigns, or parity across all feature cases.

Within mixed traffic, median paired p95 ratios are 1.181 for equality, 1.190 for
range, 0.904 for the tested prefix and 1.051 for medium bbox. All four vary across
parity between repetitions. Full individual-request throughput comparisons on the
next image remain necessary.

During measurement-and-drain, Honua's database still approaches the four-core
budget and has three to four sampled parallel workers. Its generator's sample
median is about 2.65–2.74 cores across repetitions; GeoServer's is about 3.23–3.84.
The generator-headroom limitation therefore still applies. The new serial-count
candidate remains the next server optimization to measure, not an established
speedup.

Artifacts under `results/serial-read-first-page-aot-20260929/` include
`mixed-count-jit-off-serial-reads/report.json`, the corresponding
`-raw-verification.json`, `-request-breakdown.json` and `-phase-pressure.json`.
The completed report SHA-256 is
`c2850fe38895a4e4e24fdca254a37e5a2ea5d13b5532b575dea15fadffd6b7ac`.

## Synthetic validator overhead experiment

The pinned campaign validator repeats parsing of oracle dates, construction of
the allowed-field list and, for features without a property ID, feature-ID
parsing. An isolated prototype prepares the invariant oracle data once and
reuses parsed feature IDs. This prototype has not changed the campaign harness.
The current and prepared validators returned identical results for 3,372 cases
across both protocols and all eleven oracle requests, including valid, empty and
adversarial payloads.

Twelve short synthetic k6 trials compared JSON parsing plus full response
validation, with no HTTP or database traffic. Both variants used the same
100-feature equality fixture, pinned k6 image, four VUs and four CPU / four GiB
budget. Three pairs per ID representation used seed 42 for variant order, with
two seconds of warmup, a separate one-second drain allowance, then four seconds
of measurement. Throughput counts completed validations within those four
seconds, excluding late completions.

| Synthetic payload representation | Prepared/current validation throughput, median [range] |
|---|---:|
| Numeric feature ID with property ID | 1.004 [0.972–1.252] |
| Prefixed feature ID without property ID | 1.126 [1.044–1.217] |

All 14,461 measured completions were valid; 48 late completions were retained
separately. Independent verification checked source and result hashes, paired
ratios, completion accounting and removal of every owned container. These short
shared-host trials show no consistent gain for the first representation and a
possible improvement for the second. They do not prove adequate generator
headroom, server speed, or an HTTP throughput improvement. The queued serial-count
campaign retains its original validator and harness fingerprint. Any validator
change needs separate validation and a fresh comparison of both products.

Artifacts are retained in `results/validator-overhead-20260929/`, including
`parity-result.json`, `experiment-receipt.json`, per-trial summaries and logs,
`verification.json`, and the experimental source. Receipt SHA-256:
`fc7d79672c8023ecf6bcc30cf202bb0dd85677c0ae4bf37b0b431f9c86a8a196`.

## New serial-count image: completed smoke evidence and capture limitation

The new `50aacf73` Native AOT image has completed the following full-corpus smoke
pairs. All 144 product/scenario rows passed, with zero invalid responses or
cancellations in warmup and measurement. Owned cleanup passed. These three-second measurement windows are
correctness checks and do not establish comparative speed.

| Honua profile | Honua scenarios | GeoServer scenarios | Scoped feature reads | Scoped counts |
|---|---:|---:|---:|---:|
| baseline | 12 / 12 | 12 / 12 | 0 | 0 |
| count-jit-off | 12 / 12 | 12 / 12 | 0 | 2 |
| serial-counts | 12 / 12 | 12 / 12 | 0 | 2 |
| count-jit-off-serial-counts | 12 / 12 | 12 / 12 | 0 | 2 |
| serial-reads-counts | 12 / 12 | 12 / 12 | 4 | 2 |
| count-jit-off-serial-reads-counts | 12 / 12 | 12 / 12 | 4 | 2 |

The retained runtime identity, resource limits, identical database fingerprints
and executed source SQL were rechecked. This uncovered an evidence limitation:
the pinned harness `d4a2009` omits `Database__...` planner keys from the environment
allowlist in `runtime.json`. The manifest retains configured intent and the SQL
trace proves executed tuning, but neither supplies the missing inspected
container environment. The campaigns remain diagnostic and unchanged.

[GeoBench PR 27](https://github.com/honua-io/geobench/pull/27) captures exact planner
keys from the shared profiles and checks them before traffic and at final drift
validation. Unrelated database values remain excluded to avoid exposing secrets.
Missing, changed, duplicated and unrequested flags fail validation. The original
capture failure was reproduced in hosted CI; the implementation's Python checks,
59 tests, JavaScript syntax, ShellCheck and CodeQL passed at `767ed9b`. The PR
merged normally as `b534ef0f93cba07a0f709feeac720ffc21fb9e06`. Future campaigns
need a new harness fingerprint; this fix
cannot retroactively complete the old environment receipts.

Per-campaign `*-profile-verification.json` artifacts under
`results/serial-count-aot-rebaseline-20260929/` explicitly report
`passed-with-runtime-setting-coverage-gap`. The initial verifier failure and the
first baseline verifier output remain retained separately. The helper reuses the
pinned SQL recognizer; it is not an independent parser or raw latency recount.


The consolidated smoke receipt is
`results/serial-count-aot-rebaseline-20260929/all-smokes-verification.json`.
[Profile PR 26](https://github.com/honua-io/geobench/pull/26) merged after these
checks. Three paired repetitions of each mixed profile and all eleven individual
requests for baseline and both joint read/count candidates remain in the running
queue. Server issue 5322 remains open for that performance acceptance.

Post-merge [CI 36575492131](https://github.com/honua-io/geobench/actions/runs/36575492131)
passed all 62 tests, Ruff, Python compilation, JavaScript syntax and ShellCheck
on `944b88996effc601ec08324a92b94b31072ecf19`, covering the combined profile support
and runtime-setting capture. This does not change the running campaign's older
harness identity or its disclosed evidence gap.


## New serial-count image: completed untuned mixed baseline

All three paired baseline repetitions completed on the production `50aacf73`
Native AOT image. The planner options are disabled in this profile. The campaign
retains ten VUs, 30-second warmup and 30-second measurement windows, with separate
drain accounting. Independent raw verification passed for every warmup and
measurement phase; there were zero invalid responses or cancellations and exactly
ten late completions per measurement attempt, excluded from measured throughput
and latency. Runtime/source SQL verification retains the disclosed environment
capture gap above.

| Repetition | Honua requests/s | GeoServer requests/s | Honua p95 ms | GeoServer p95 ms |
|---|---:|---:|---:|---:|
| 1 | 84.63 | 195.47 | 229.91 | 79.11 |
| 2 | 101.67 | 190.97 | 201.49 | 81.55 |
| 3 | 102.97 | 178.03 | 200.92 | 89.06 |

Median paired throughput H/G is **0.532**, range **0.433–0.578**; p95 H/G is
**2.471**, range **2.256–2.906**. GeoServer leads both metrics in all three pairs.
The earlier near-parity result used the previous image with serial feature reads
and count-JIT suppression. New-image tuned results remain pending. The separate
campaign times on a shared host do not establish a causal cross-build change.

Within this baseline mixed workload, medium-bbox median paired p95 H/G is 2.683
and its median share of Honua's summed response latency is about 61%, despite
making up 40% of scheduled mixed requests. Equality is 1.811, range 1.579 and the
tested prefix 1.095 on paired p95. These are request latencies within mixed
traffic, not standalone throughput or CPU attribution.

Measurement-and-drain telemetry shows Honua database sample medians of
397.90–399.59% CPU and four to six sampled parallel workers, with server medians
114.19–128.03%. GeoServer's generator medians are 379.47–389.94%, close to its
four-core limit. These phase samples include drain and do not prove exact-window
utilization or true concurrency peaks. The queued serial-count/read policies
remain the next performance experiment; generator headroom still limits the
interpretation of any apparent tie or win.

Artifacts under `results/serial-count-aot-rebaseline-20260929/` include
`mixed-baseline/report.json`, `mixed-baseline-raw-verification.json`,
`mixed-baseline-profile-verification.json`, `mixed-baseline-request-breakdown.json`
and `mixed-baseline-phase-pressure.json`. Completed report SHA-256:
`6bbfa5e818c122ca8d8ef8b3034d16a9157d0bb71fa3d18e1cc945032dba46c6`.

Completed-campaign analysis uses low process priority, idle IO priority and
cooperative yields between raw-sample chunks. The analysis queue retains start
and finish times and child CPU usage; the first recount used 3.90 CPU seconds
across 46.72 wall seconds. It sends no HTTP or oracle queries. These controls do
not replace observer/load-generator calibration, and publication remains disabled.


## New serial-count image: completed count-JIT-off mixed comparison

This profile suppresses PostgreSQL JIT for eligible spatial counts; serial page
and count planning remain disabled. All three paired repetitions completed and
passed independent raw verification, with zero invalid responses or cancellations
and ten late completions per measured attempt retained separately. Warmup and
measurement each lasted 30 seconds at ten VUs. The same runtime environment
capture limitation applies.

| Repetition | Honua requests/s | GeoServer requests/s | Honua p95 ms | GeoServer p95 ms |
|---|---:|---:|---:|---:|
| 1 | 113.67 | 190.17 | 169.74 | 80.88 |
| 2 | 94.90 | 142.07 | 195.01 | 119.15 |
| 3 | 85.60 | 147.63 | 203.18 | 114.89 |

Median paired throughput H/G is **0.598**, range **0.580–0.668**; p95 H/G is
**1.768**, range **1.637–2.099**. GeoServer leads both metrics in every pair.
These paired observations remain shared-host diagnostics; their difference from
the separately timed baseline is not proof of a causal tuning gain.

Within mixed traffic, medium-bbox median paired p95 H/G is 1.753 and its median
share of Honua's summed response latency is about 62%. Equality is 1.319, range
1.403 and the tested prefix 0.972. Prefix varies across parity (0.837–1.118);
these are not standalone per-request throughput measurements.

Honua database CPU sample medians during measurement-and-drain are
395.23–405.33%, with three to four sampled parallel workers. GeoServer generator
medians are 363.73–393.01%, so the existing generator-headroom caveat remains.
These samples include drain and do not identify which individual SQL statements
consumed the worker CPU. The separate serial-count-only campaign is now running;
its new server policy has not yet completed all three performance pairs.

Artifacts under `results/serial-count-aot-rebaseline-20260929/` include
`mixed-count-jit-off/report.json` and the corresponding `-raw-verification.json`,
`-profile-verification.json`, `-request-breakdown.json` and `-phase-pressure.json`.
Completed report SHA-256:
`17f2db6bd6569ca2af69d311712ea63134501a2512be0c6b9d9edceaabca9d1e`.


## New serial-count image: completed serial-count-only mixed comparison

This profile enables serial planning for eligible source spatial counts while
leaving count-JIT suppression and serial feature reads disabled. All three paired
repetitions passed independent raw verification, with zero invalid responses or
cancellations and ten late completions per measurement attempt excluded from
measured throughput and latency. Each attempt used ten VUs, 30 seconds of warmup
and 30 seconds of measurement. Runtime identity, database fingerprints, source
SQL and owned cleanup checks passed; the previously disclosed missing planner
environment capture remains an evidence gap.

| Repetition | Honua requests/s | GeoServer requests/s | Honua p95 ms | GeoServer p95 ms |
|---|---:|---:|---:|---:|
| 1 | 135.63 | 153.73 | 144.29 | 98.08 |
| 2 | 141.07 | 177.07 | 138.29 | 89.12 |
| 3 | 153.67 | 178.97 | 112.46 | 81.91 |

Median paired throughput H/G is **0.859**, range **0.797–0.882**; p95 H/G is
**1.471**, range **1.373–1.552**. GeoServer leads both metrics in every pair.
These ratios are closer to parity than the separately timed baseline, but this
shared-host experiment does not establish the size of a causal tuning gain.
The earlier image's combined tuning result remains a separate comparison.

Within mixed traffic, median paired p95 H/G is 1.595 for medium bbox,
1.099 for equality, 1.137 for numeric range and 0.827 for the tested prefix.
Prefix p95 favors Honua in each pair (range 0.762–0.900); the other three request
types favor GeoServer in each pair. Medium bbox accounts for a median 57.5% of
Honua's summed response latency while making up 40% of scheduled requests.
These are latencies within mixed traffic, not standalone request throughput or
CPU attribution.

Honua database CPU sample medians during measurement-and-drain are
399.17–403.79%, with up to four sampled parallel workers. Preflight SQL confirms
the count-only policy and no scoped feature-read policy; the telemetry does not
attribute workers to particular statements. Honua server CPU sample medians are
172.51–181.12%, and GeoServer generator medians are 343.86–358.91%, with sampled
generator peaks reaching its four-core budget. These phase samples include drain
and do not prove exact-window utilization or true peaks. The queued combined
read/count policies remain necessary to evaluate the remaining spatial gap.

Artifacts under `results/serial-count-aot-rebaseline-20260929/` include
`mixed-serial-counts/report.json` and its `-raw-verification.json`,
`-profile-verification.json`, `-request-breakdown.json` and `-phase-pressure.json`.
Completed report SHA-256:
`00972fbb71efd3c35c0c57b623239590ca3b77436f1d9476707097a594c14e2c`.
The independent recount used 4.87 CPU seconds over 52.33 wall seconds with the
previously described cooperative analysis controls. Publication remains disabled.


## New serial-count image: completed count-JIT-off plus serial-count comparison

This profile combines serial spatial counts with count-specific PostgreSQL JIT
suppression; feature-read planning remains unchanged. All three paired mixed
repetitions passed independent raw verification, with zero invalid responses or
cancellations. Each attempt used ten VUs, 30 seconds of warmup and 30 seconds of
measurement. Five measurement attempts have ten late completions each; GeoServer
repetition three has eleven. All late completions are retained outside measured
throughput and latency. Runtime/source checks retain the disclosed planner
environment capture gap.

| Repetition | Honua requests/s | GeoServer requests/s | Honua p95 ms | GeoServer p95 ms |
|---|---:|---:|---:|---:|
| 1 | 148.33 | 191.63 | 103.87 | 81.01 |
| 2 | 165.73 | 174.97 | 101.45 | 87.07 |
| 3 | 169.10 | 190.60 | 98.36 | 79.57 |

Median paired throughput H/G is **0.887**, range **0.774–0.947**; p95 H/G is
**1.236**, range **1.165–1.282**. GeoServer leads both metrics in all three pairs.
This result does not establish parity or quantify a causal improvement over the
separately timed profiles. Serial feature reads together with serial counts, with
and without count-JIT suppression, have not completed for this image.

Within mixed traffic, median paired p95 H/G is 1.202 for medium bbox, 1.136 for
equality, 1.126 for range and 0.853 for the tested prefix. Prefix spans parity
(0.821–1.030); the other three request types favor GeoServer in every pair.
Medium bbox accounts for a median 56.7% of Honua's summed response latency.
These are mixed-traffic latency observations, not standalone throughput or CPU
attribution.

Honua database CPU sample medians during measurement-and-drain are
397.40–403.33%, with up to three or four sampled parallel workers per attempt.
Honua server medians are 172.42–200.28%, and GeoServer generator medians are
376.56–397.07%. The generator is still close to its four-core limit. These phase
samples include drain and do not attribute worker use to individual queries or
establish exact-window utilization.

Artifacts under `results/serial-count-aot-rebaseline-20260929/` include
`mixed-count-jit-off-serial-counts/report.json` and its `-raw-verification.json`,
`-profile-verification.json`, `-request-breakdown.json` and `-phase-pressure.json`.
Report SHA-256:
`4277ed0445317abf35184d4be53f44b6dd832d14895c401f58b5e045a7cb801d`.
Independent recount CPU/wall time was 5.65/56.46 seconds. These remain shared-host
diagnostics with publication disabled.


## Generator headroom follow-up

[GeoBench PR 31](https://github.com/honua-io/geobench/pull/31) merged as
`23fb387efd077beeaff74612d4007f862b9e0867`. New campaigns can select
`--generator-cpus 8` while retaining four CPUs and 4 GiB for each server/database,
six source connections and 4 GiB generator memory. Both products receive the same
generator CPU budget. Manifests, profile names, reports, effective runtime checks
and resume/calibration bindings record the distinction. Observer CPU warnings use
the inspected quota for each container.

Exact-head [CI 36581545372](https://github.com/honua-io/geobench/actions/runs/36581545372)
passed 69 tests, Ruff, compilation, JavaScript syntax and ShellCheck; CodeQL also
passed. The tests-only predecessor recorded the missing APIs/CLI and CPU receipt
failures before implementation. Receipts and logs are retained under
`results/generator-cpu-budget-20260929/`.

No new-budget HTTP smoke or headroom comparison has run yet: the existing queue
retains harness `d4a2009`, its original schedule and four-core generator. Future
generator-budget comparisons require separate campaigns and cannot be pooled with
these results. Extra local CPU does not replace isolated-generator or observer
calibration for publication.
