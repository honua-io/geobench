# Small-bbox investigation — October 3, 2026 (UTC)

Follow-up: [fresh policy batching qualification](policy-batching-qualification-20261003.md)
now records an implemented JIT candidate and verified command reduction. Its
timed performance screen remains pending; the original AOT findings below are
unchanged.

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
behavior. The attribution follow-up below now measures substantial catalog
overhead, rather than leaving it as a source-review hypothesis.

The strongest next implementation candidate is fresh row/field policy batching
in #5352, which removes a catalog round trip without caching evaluated policy.
It needs compatibility, policy/principal freshness, legacy-table fallback,
cancellation and transaction tests, followed by SQL round-trip proof and a
controlled HTTP check. This investigation neither qualifies that checkpoint
nor claims it will recover the full gap. No server code or shipping setting
was changed, and no new AOT build is required for these findings.

## Request attribution follow-up

Two fresh owned fixtures ran the **unchanged production Native AOT image** with
its existing OpenTelemetry tracing enabled at full sampling. No rebuild or
custom instrumentation was needed. Each capture collected ten serial warmup
responses, 30 serial diagnostic responses and 40 responses from ten Python
client workers. These are small diagnostic bursts, not a steady k6 concurrency
test or new benchmark campaign. The frozen oracle validator checked all
**160 responses**, including complete ordered IDs, counts, attribute values and
types, and geometry. The ten warmup responses in each capture are excluded from
the attribution summaries.

Every selected trace contains exactly four sequential Npgsql command spans:
authoritative connection lookup, row-security policies, field-mask policies,
and the feature batch. The feature batch includes the serial planner setting
and the SELECT. No separate exact-count query appears. Span intervals are
matched by the supplied W3C trace ID, checked against the enclosing ASP.NET
request, and counted once; nested feature-handler/router spans are not added
to database time. Raw OTLP protobuf batches were decoded again and checked
against the saved spans. An independent timestamp/SQL pass recomputed request
and catalog medians and all input hashes were verified.

| Capture | Client workers | Nonwarm responses | Median server ms | Median catalog ms | Median per-request catalog share | Median feature batch ms | Median after-handler ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1, postcapture bookkeeping failed | 1 | 30 | 9.764 | 3.432 | 34.6% | 2.957 | 0.680 |
| 1, postcapture bookkeeping failed | 10 | 40 | 18.096 | 5.162 | 28.4% | 5.599 | 0.763 |
| 2, postrun checks passed | 1 | 30 | 12.577 | 4.334 | 34.8% | 3.797 | 0.813 |
| 2, postrun checks passed | 10 | 40 | 21.637 | 8.598 | 38.0% | 5.951 | 0.798 |

Catalog time is the sum of the three catalog spans **within each request**,
then summarized across requests. Component medians do not add. The two policy
reads alone take median 2.301/2.787 ms in the serial captures, corresponding to
median per-request shares of 22.9%/21.4%. The shares in the ten-worker bursts
are 20.1%/24.7%. Complete medians and ranges are retained in the
[attribution summary](small-bbox-attribution-20261003.json).

This establishes that fresh catalog work is a substantial part of Honua's
small-bbox request cost in these captures. Later response execution is a
smaller median component. GeoServer's local 3.0.1 source confirms its
`GeoJSONFeatureWriter.writeFeatures` writes JSON while iterating features;
Honua's source-backed `ExecuteFeatureQueryAsync` materializes feature objects
before `OgcFeaturesQueryHandler` creates the response. That architectural
difference remains real, but these traces give stronger reason to address
catalog round trips first than to rewrite the response writer.

Npgsql spans include driver handling, network waits, scheduling and row
materialization; they are **not pure PostgreSQL execution times**. The driver's
first-response event belongs to a batch that starts with `set_config`, so it
cannot prove a first-feature-row boundary or isolate conversion CPU. Time
between commands also includes uninstrumented connection leasing and other
work. Time after the handler includes response execution and surrounding
middleware, not serialization alone. The larger client wall times include
the coordinator/Docker network path outside the ASP.NET request span.

These instrumented shared-host samples do not reconstruct the original
Honua/GeoServer latency difference or provide a new speed ratio. They rank
Honua components. **Batching both fresh policy reads is now a measured target**:
it removes one of four command round trips, while both policies still have to
be read and evaluated. It cannot eliminate the entire 21–25% policy component,
and its actual gain is unmeasured. Credential freshness, policy freshness,
custom-provider compatibility and legacy-table behavior remain required by
#5352. SQL round-trip proof and a controlled HTTP A/B must precede a gain claim.

The first capture failed only after all responses and spans were saved: its
pressure check referenced `PRESSURE_SQL` on the wrong Python module. Its
postcapture runtime verification did not run, and its attempt ledger remains
incomplete; it is not promoted to a passed campaign. Its prepared repetition
metadata also changed without rebinding and is not comparison evidence.
The corrected second capture imports the constant from `feature_runtime`,
preserves the prepared benchmark schedule, and passes postrun runtime/database
checks without producing benchmark rows. It records a postcapture pressure
sample, not continuous measured-load telemetry. Both attempts and all raw
responses are retained. Both fixtures and controllers were removed by exact
identity and verified absent under the harness ownership label.

Before the first fixture, the shared-slot queue was blocked by an idle Roslyn
compiler retaining the completed test's inherited lock descriptor. No active
build remained; normal `dotnet build-server shutdown --vbcscompiler` released
that lock. No fleet settings or foreign containers were changed.

Local artifacts: `small-bbox-attribution-v{1,2}-20261003/` beneath the same
private optimization result root. Each contains `requests.json`, full response
payloads, raw OTLP batches, decoded spans, semantic verification, per-request
analysis, independent verification and exact cleanup receipts. Both Native AOT
captures use the source/image/harness/dataset pins below. Publication remains
blocked by the original calibration prerequisites; the final baseline is
unchanged.

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
