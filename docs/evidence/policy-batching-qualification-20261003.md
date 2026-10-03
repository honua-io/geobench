# Fresh policy batching qualification — October 3, 2026 (UTC)

[Server PR #5377](https://github.com/honua-io/honua-server/pull/5377) implements
[issue #5352](https://github.com/honua-io/honua-server/issues/5352). It combines
fresh row-policy and field-mask reads in one PostgreSQL batch and one lease
when the actual registered sources, providers, schema and request context are
compatible. It preserves independent paths for custom sources, background
work, previously enforced restrictions and caller transactions. Missing legacy
tables fall back independently; other errors and cancellation propagate.

This is an implementation checkpoint, **not a qualified speedup**. The PR stays
draft until the alternating JIT performance screen passes.
Production Native AOT qualification and publication remain separate steps.

## Immutable JIT controls and live correctness

The control source is `fee8354f26cec68379652a272ca489ecdd667b0e`; the candidate
is `c6e4e3ec9745188ad54dd39929bd9711b962f1a1`. Both full builds carry their
exact source stamps in the four critical runtime assemblies. Both images use
the same immutable .NET/ASP.NET 10.0.11 runtime base, with no assembly overlays.

| Treatment | Local immutable image ID |
| --- | --- |
| Control | `sha256:ba96eef74ada7209edb3c786c6e7ba9b5170db53c1698ed06d1d4e04523e9a2b` |
| Candidate | `sha256:c21146e9e5b74419935458f1db7a451f978386230ab4265a158c79b4ad0e1607` |

Each fresh owned fixture passed the complete existing twelve-scenario oracle
preflight, source-query proof and resource checks against the deterministic
100K-point dataset. Five cases then captured 80 responses each: small bbox,
bbox boundary, numeric range, shallow page and medium page. Per case, ten
responses are warmup, thirty are serial diagnostics and forty use ten client
workers. Independent validation checked **800 responses, zero invalid**,
including ordered IDs, counts, attribute values/types and geometry. Both stacks
and their exact owned controllers were removed after capture.

## Command proof and explicit limits

Raw OTLP batches were decoded again and matched to every saved request's
trace ID and span ancestry, without duplicate spans. Every control request has
two policy commands; every candidate request has one containing both policy
statements. Registry and feature/count work are preserved:

| Cases | Control core commands | Candidate core commands | Separate count |
| --- | ---: | ---: | --- |
| Small bbox, bbox boundary | 4 | 3 | Elided in both |
| Numeric range, shallow page, medium page | 5 | 4 | One in both |

These are core query commands, not unconditional totals. Three control requests
and four candidate requests also trigger four metadata refresh commands. One
candidate small-bbox request opens a connection and executes a session-settings
command. Those events remain visible in the [proof summary](policy-batching-proof-20261003.json),
including nonwarm requests; they are not discarded as outliers.

One control and three candidate requests have parent/child timestamps that
violate containment. Span ancestry and command contents still verify, but the
capture is **unsuitable for trace latency conclusions**. No component timing,
throughput ratio or GeoServer speed comparison is calculated from these bursts.

## Verification and remaining release gates

At the candidate source, the ten new real-PostGIS cases, sixteen shared resolver
cases, fifty server principal/entitlement/background cases, fourteen HTTP
security regressions and twenty-nine read-security/count regressions passed
without skips. The full PostgreSQL security project retry passed all thirty-eight
cases. Its earlier failed attempt remains recorded: twenty-eight cases passed
and ten failed during Testcontainers fixture startup in image-name regex matching,
before the policy test bodies ran. The unchanged-source retry does not erase it.
Release compilation uses warnings as errors. Formatting and the exact-head PR
Gate, including all selected affected shards, passed. All 351 full architecture
cases passed without skips. The six regression suites cover 498 passing cases;
the focused ten-case PostgreSQL run is included in the full thirty-eight-case
retry and is not counted twice.

The next screen uses three alternating control/candidate pairs with fresh
fixtures, 30-second warmup and 30-second measurement for each of the five cases.
Fewer policy commands can qualify if performance remains neutral: repeatable
throughput or p95 regressions greater than 5% require three fresh confirmation
pairs and reject the patch if confirmed. No timed screen has started because
the shared WSL host is under substantial competing load.

After this screen qualifies, at most one guarded native-attribute projection
optimization remains in scope, followed by all twelve cases against both
products. Only the normal exact-head gates and fleet lander may merge accepted
changes. The final production Native AOT image must be verified and smoke-tested
before requesting a fresh quiet window for final timing. Existing observer
calibration failure and absent isolated-generator evidence still block
publishable comparisons; this checkpoint makes no publication claim.
