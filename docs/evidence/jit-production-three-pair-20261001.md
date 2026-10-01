# Three-pair production-settings JIT diagnostic — October 1, 2026 (UTC)

All three scheduled pairs passed the 12 existing scenarios: **72 measured rows**,
zero semantic failures/cancellations, and verified cleanup of all six owned stacks.
Independent recalculation from the raw measured samples matches every count, drain
count, per-row throughput, p50/p95/p99 and all 36 paired ratios. Preflight records
numeric count metadata and identity compression for both products.

This is Release JIT on the deterministic 100K-point corpus, shared WSL/Docker Desktop.
The report is valid for diagnostics and explicitly **not publishable**. It does not
establish isolated-generator calibration, production AOT performance, other protocols,
line/polygon or larger-dataset results. Native decoding and metadata reuse are outside
this measured image.

## Per-case paired results

The table reports medians of three paired ratios and their throughput ranges.
Latency ratios are medians of paired per-repetition quantiles, not pooled quantiles.
Higher throughput and lower latency ratios favor Honua. No cross-protocol score is calculated.

| Scenario | Throughput H/G median | Range | p50 H/G median | p95 H/G median | p99 H/G median |
| --- | ---: | ---: | ---: | ---: | ---: |
| equality | 1.214 | 1.174–1.267 | 0.854 | 0.731 | 0.702 |
| range | 1.076 | 0.996–1.077 | 0.940 | 0.931 | 0.914 |
| prefix | 1.846 | 1.837–1.922 | 0.528 | 0.583 | 0.583 |
| bbox-small | 1.063 | 1.052–1.133 | 0.949 | 0.908 | 0.807 |
| bbox-medium | 1.951 | 1.936–1.956 | 0.517 | 0.549 | 0.581 |
| bbox-large | 3.528 | 3.486–3.698 | 0.273 | 0.293 | 0.311 |
| page-shallow | 0.979 | 0.970–0.981 | 1.020 | 1.063 | 1.027 |
| page-medium | 0.969 | 0.967–0.978 | 1.029 | 1.056 | 1.044 |
| page-deep | 1.623 | 1.612–1.652 | 0.588 | 0.648 | 0.629 |
| empty | 1.320 | 1.300–1.336 | 1.185 | 0.287 | 0.338 |
| bbox-boundary | 1.279 | 1.274–1.279 | 1.069 | 0.372 | 0.421 |
| mixed:vus:10 | 1.517 | 1.224–1.583 | 0.693 | 0.568 | 0.533 |

Median throughput leads in 10 of 12 cases. Shallow/medium pages trail by
about 2%/3%, with p95 about 6% worse in each. Empty and boundary queries lead
capacity and tail latency but have roughly 19%/7% slower medians. Range throughput
is close to parity in one repetition; its earlier tail deficit is absent in these
three pairs. Mixed throughput varies from 1.224 to 1.583, so its median alone does
not convey the observed range. These are optimization targets and diagnostic
observations, not statistically established causal improvements over an older Honua build.

## Each paired repetition

| Scenario | Pair 1 TP / p95 | Pair 2 TP / p95 | Pair 3 TP / p95 |
| --- | ---: | ---: | ---: |
| equality | 1.214 / 0.745 | 1.174 / 0.731 | 1.267 / 0.723 |
| range | 1.077 / 0.931 | 1.076 / 0.900 | 0.996 / 0.992 |
| prefix | 1.837 / 0.589 | 1.922 / 0.537 | 1.846 / 0.583 |
| bbox-small | 1.063 / 0.908 | 1.052 / 0.909 | 1.133 / 0.849 |
| bbox-medium | 1.936 / 0.570 | 1.956 / 0.549 | 1.951 / 0.540 |
| bbox-large | 3.528 / 0.293 | 3.698 / 0.290 | 3.486 / 0.312 |
| page-shallow | 0.970 / 1.064 | 0.981 / 1.036 | 0.979 / 1.063 |
| page-medium | 0.978 / 1.038 | 0.967 / 1.056 | 0.969 / 1.070 |
| page-deep | 1.612 / 0.609 | 1.652 / 0.648 | 1.623 / 0.692 |
| empty | 1.336 / 0.270 | 1.300 / 0.295 | 1.320 / 0.287 |
| bbox-boundary | 1.274 / 0.369 | 1.279 / 0.372 | 1.279 / 0.380 |
| mixed:vus:10 | 1.224 / 0.842 | 1.583 / 0.543 | 1.517 / 0.568 |

Raw receipts retain each measured p50/p95/p99 and all corresponding paired ratios.

## Contract and identities

- Frozen server source: `5349cce68e232fbf92ccbb88bcbe3a8f4817a2df`,
  [PR #5343](https://github.com/honua-io/honua-server/pull/5343).
- Honua image: `sha256:5a8d9c7e3ecbdb8ce6b36dc75adcc9a74dd820c4f623f2d023302b3955cabd48`.
- GeoServer image: `sha256:32b61aed98bca6cc0821fbcdab9dbc5b9b22b6fa1af6d51d396fb64e63dac491`,
  GeoServer 3.0.1 plus matching OGC API extension; prior 310-JAR identity verification retained.
- Harness: `869d19e75bdf456c508b561d966652921cfd9dc5`, complete patch subsequently merged
  through [GeoBench PR #34](https://github.com/honua-io/geobench/pull/34).
- Dataset SHA256: `2ca9025b025361a85e7e0866a80748d29dacd44d27987ce75631a7473189a525`.
- Report SHA256: `306a3738ca5dfe013c58ea8423c8ccb2be42b832173e77fcf9216ef5f406141f`.
- Three repetitions, seed 42, 30-second warmup/measurement and explicit drain.
  Order alternates H/G, G/H, H/G; stacks/databases are recreated for each attempt.
- Server/database each 4 CPUs / 4 GiB, configured source pools six; both generators
  8 CPUs / 4 GiB. Observed database sessions/workers remain separately recorded.
- Exact response caching and adaptive admission disabled; normal metadata caches retained.
  `HONUA_TEST_SCHEMA_HEADERS=false` is enforced before/after traffic. Serial-planner
  flags are omitted to exercise the candidate automatic bounded policy.
- Runtime maps CoreCLR and executes `dotnet Honua.Server.dll`. The earlier informational
  version stamp discrepancy and tested/published assembly hash proof are disclosed in
  the [qualification note](jit-optimization-batch-20260930.md); final AOT needs a fresh
  actual-source stamp. This campaign is not presented as an AOT result.
- The existing prefix expression does not establish escaped-underscore literal-prefix
  coverage. That limitation remains disclosed before any strict publication.

## Next code qualification

[Native decoding #5349](https://github.com/honua-io/honua-server/pull/5349) and
[authorized metadata reuse #5351](https://github.com/honua-io/honua-server/pull/5351)
have exact-head PR Gate success. A clean combined checkout at
`e110a28cb4b3b5a64fd3b0e4c279a2099fb35f06` is undergoing local JIT qualification.
The first launcher exited before the driver because of a duplicated Python entrypoint;
its exact terminal log and cleanup are retained. The next build failed on an SDK static-assets
shared file lock before tests; all its owned fixtures were cleaned. The subsequent
attempt serializes MSBuild without weakening analyzers or selections. None is counted
as a native-decoder/metadata semantic pass yet.

[Policy batching #5352](https://github.com/honua-io/honua-server/issues/5352) is the
next fixed-overhead opportunity, with fresh policy/principal evaluation, strict custom
store/source compatibility and independent missing-table behavior required. Direct UTF8
writing remains a later nonempty-page opportunity. No policy/credential TTL cache is proposed.

Final AOT, strict repetitions, calibration and publication remain after the remaining
optimization and verification work. Earlier failed/interrupted campaigns remain visible.

## Retained local artifacts

Under `results/jit-optimization-batch-20260929/`:

- `production-three-pair-raw-verification-20261001.json` contains all 72 measured
  row hashes/counts/distributions and 36 paired ratios, with the immutable report hash.
- `harness-control-checkout/results/integrated-production-comparison-v2-20261001/`
  contains raw samples, full reports, fingerprints, runtime/SQL/telemetry receipts.
- `durable-coordinator-v2-20261001/` records successful terminal state and full paired ranges.
- `native-metadata-hosted-gates-20261001.json` records both exact-head hosted gates.
- `native-metadata-integration-preparation-20261001.json` and versioned preparations
  bind current source and qualification recipes; compilation/tests remain separately recorded.
- `durable-native-metadata-pg17-20261001/` and `native-metadata-pg17-v2-20261001/`
  retain the failed launcher/build and cleanup. The current attempt uses a fresh v3 directory.
