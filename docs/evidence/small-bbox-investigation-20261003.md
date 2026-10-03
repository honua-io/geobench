# Small-bbox investigation — October 3, 2026 (UTC)

This investigation uses the final merged-source production Native AOT image
from the [local diagnostic baseline](aot-release-readiness-20261001.md#final-production-native-aot-diagnostics-complete-october2).
It is diagnostic evidence only. The publication calibration failure and missing
separate-generator evidence remain unchanged.

## What the retained evidence establishes

The small bbox returns **35 points**, below the requested limit of 100. The
measured reader already elides the separate exact count for a short first page.
Adding that optimization again would not address this result.

The three paired Honua/GeoServer throughput ratios were 0.650, 0.778 and 1.064.
Honua lost two pairs and won one; the 22% paired median deficit is not a stable
gap across every repetition. Median completion latency across repetitions was
approximately 28 ms for Honua and 22 ms for GeoServer. These include response
validation in the load generator. The retained HTTP time-to-first-byte samples
also differ, so the generator's semantic checks alone do not explain the gap.

The separate SQL trace shows three live catalog queries before the Honua feature
SELECT: authoritative connection details, row-security policies and field-mask
policies. They remain present even with anonymous access and no matching
policies. These queries preserve credential and policy freshness; replacing
them with cached metadata or skipping wildcard policies is not an acceptable
optimization. The existing [fresh policy batching issue #5352](https://github.com/honua-io/honua-server/issues/5352)
is a candidate for reducing round trips while preserving those semantics. Its
checkpoint remains unqualified; this investigation does not claim a batching gain.

## SQL replay

A fresh, uniquely owned database restored the exact deterministic 100K-point
artifact into the pinned PostgreSQL 17/PostGIS 3.5 image, under 4 CPU/4 GiB.
Statistics were prepared, the original Honua query's complete ordered 35-ID
sequence matched the existing oracle, and every tested plan returned 35 rows.
After warmup, 120 EXPLAIN ANALYZE samples covered eight treatments with 15
repetitions each, shuffled with recorded seed 20261002. The shared build and
measurement locks were held. Only the exact owned container and its attached
anonymous volume were removed after the replay; receipts and all plans remain.

| Treatment | Median planning ms | Median execution ms |
| --- | ---: | ---: |
| Honua, default PostgreSQL parallel setting | 0.428 | 0.473 |
| Honua, serial setting | 0.423 | 0.449 |
| Honua, type guards removed, default | 0.372 | 0.378 |
| Honua, type guards removed, serial | 0.339 | 0.395 |
| GeoServer page SELECT, default | 0.422 | 0.201 |
| GeoServer page SELECT, serial | 0.363 | 0.214 |
| Honua, forced custom prepared plan | 0.516 | 0.446 |
| Honua, forced generic prepared plan | 0.038 | 0.481 |

These are SQL component timings, not HTTP speed ratios. GeoServer's separate
bounded-count query is not included in its page SELECT timing. Type-guard
removal is an experimental control, **not a safe production change**: guards
handle stale published hints and actual database types. Prepared-plan controls
also do not establish that a generic plan is safe or faster for other filters
or bbox selectivities. Complete attributes and geometry were not independently
revalidated for the experimental SQL controls; no production patch is proposed
from them.

Honua uses a bitmap spatial-index scan in this replay; changing the serial
setting preserves that plan. GeoServer uses a direct spatial-index scan, with
an explicit `&&` bbox predicate plus exact intersection. Both hit 39 shared
buffers and read zero blocks after warmup. The plan difference and remaining
JSON conversions explain some additional SQL work, but these sub-millisecond
component differences do not establish the dominant cause of the HTTP gap.

## Explicit bbox predicate follow-up

A second fresh database repeated the SQL diagnostic with the additional
`geom && envelope AND ST_Intersects(geom, envelope)` control, retaining the
original projection and exact predicate. It collected 150 shuffled samples,
15 per treatment, and every plan returned 35 rows. The added predicate changed
Honua's bitmap scan to a direct index scan, matching GeoServer's scan shape.
It did not demonstrate a clear execution-time benefit:

| Treatment | Median planning ms | Median execution ms [min–max] |
| --- | ---: | ---: |
| Original Honua, default | 0.678 | 0.848 [0.430–2.673] |
| Explicit bbox plus exact, default | 0.883 | 0.902 [0.570–2.123] |
| Original Honua, serial | 0.764 | 0.911 [0.384–2.492] |
| Explicit bbox plus exact, serial | 0.780 | 0.820 [0.408–3.182] |

The ranges overlap substantially. A more similar plan is not proof of a faster
HTTP request. Earlier [broader SQL diagnostics](feature-followup-20260928.md#spatial-count-optimization-diagnostics-on-the-shared-host)
also found that copying the redundant bbox predicate could worsen broad/world
queries. No predicate or planner default was changed in production.

An independent pass decoded both raw EXPLAIN streams, recomputed all 270 plans'
timings, medians and ranges, checked their 35-row results, and verified exact
owned database cleanup. Raw statements, replay order, JSON plans and hashes
remain in the two private result directories.

## HTTP profile check stopped because of observed contention

The same Native AOT image was scheduled for three paired small-bbox-only
profile repetitions, with fresh fixtures and alternating automatic/baseline,
baseline/automatic, automatic/baseline order. Both used the existing oracle,
30s warmup/30s measurement, 10 VUs, identical 4 CPU/4 GiB server/database and
8 CPU/4 GiB generator budgets, six source connections and production security.
The `baseline` profile explicitly disables the serial planner options; it does
not bypass security or change exact-count behavior.

Three treatments completed correctness and postrun fairness checks:

| Repetition | Profile | Valid measured req/s | p95 completion ms |
| --- | --- | ---: | ---: |
| 1 | automatic-bounded | 153.37 | 120.93 |
| 1 | baseline | 119.27 | 151.71 |
| 2 | baseline | 79.23 | 251.53 |

These partial rows **do not establish a profile winner or speedup**. Median
one-minute host load in the measurement samples rose from 20.69 to 25.61 to
28.88 on a 22-core Docker host, with individual samples exceeding 30. Median
observer collection duration rose
from 3.92s to 4.30s to 5.60s, exceeding its five-second cadence. The timed A/B
was stopped because that observed contention prevents attributing the variation
to the planner setting. Repetition 2 automatic remains interrupted; both
repetition 3 treatments are explicitly not-run. Both campaign reports fail
validity for incomplete scheduled repetitions. No full three-pair ratio is
computed, and the original final-image diagnostic baseline remains unchanged.

The initial HTTP launcher also retained a preparation failure: the parent held
the host measurement lock while its prepare-only subprocess attempted to take
the same lock. It rejected before stacks or timed traffic. The corrected attempt
releases the parent lock during prepare-only and reacquires it before workloads.
That failure, logs and exact controller cleanup are retained separately. All
owned fixtures and both HTTP controllers were cleaned by exact identity; no
foreign containers or fleet settings were changed.

## Finding and next optimization

There is **no demonstrated one-line fix** for the small-bbox deficit. The short
page count optimization is already present, the serial setting does not change
the small-bbox SQL scan, copying GeoServer's explicit predicate did not prove
a gain, and removing type guards is unsafe without preserving schema-drift
behavior. The unresolved fixed-overhead candidates are fresh catalog round
trips and remaining row/response conversion.

The strongest next implementation candidate is fresh row/field policy batching
in #5352, which removes a catalog round trip without caching evaluated policy.
It needs compatibility, policy/principal freshness, legacy-table fallback,
cancellation and transaction tests, followed by SQL round-trip proof and a
controlled HTTP check. This investigation neither qualifies that checkpoint
nor claims it will recover the full gap. No server code or shipping setting
was changed, and no new AOT build is required for these findings.

Source: `36581bd29870101d103ea16e3ba215a2a98811fe`.
Native image:
`ghcr.io/honua-io/honua-server@sha256:b2549f8d3d1e6eac54d697d45de31e0f8b921accb34f083eda44612e72ac1f66`.
Harness: `869d19e75bdf456c508b561d966652921cfd9dc5`.
Dataset SHA256:
`2ca9025b025361a85e7e0866a80748d29dacd44d27987ce75631a7473189a525`.
Local receipts, statements and raw plans:
`results/jit-optimization-batch-20260929/small-bbox-investigation-v1-20261002/`.
Additional SQL replay:
`results/jit-optimization-batch-20260929/small-bbox-investigation-v2-20261003/`.
Independent SQL verification: `sql-independent-verification.json` in the first
directory. HTTP interruption/cleanup: `http-v2-{receipt,cleanup}.json` there.
Incomplete HTTP campaign reports:
`harness-control-checkout/results/small-bbox-planner-{automatic-bounded,baseline}-v2-20261003/`.
