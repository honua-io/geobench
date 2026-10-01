# Production-settings JIT rebaseline — October 1, 2026 (UTC)

Both products passed all 12 existing oracle scenarios in a fresh semantic smoke
run. The three paired diagnostic repetitions are running; no new repeated speed
ratio or publication claim is available. This remains the deterministic
100K-point workload on shared WSL/Docker Desktop, using Release JIT.

## What changed

The earlier harness enabled `HONUA_TEST_SCHEMA_HEADERS=true`. Workloads send no
schema override, and every attempt already owns an isolated database. Enabling
that test hook made Honua reset pooled connections, adding work that is absent
from its normal production configuration. The separately collected SQL trace
contained 162 `DISCARD ALL` statements in the earlier smoke and zero in the
production-settings smoke. These are SQL diagnostics, not throughput gains.

[GeoBench PR #34](https://github.com/honua-io/geobench/pull/34) disables the hook
and fails closed if runtime evidence is missing, conflicting or enabled. It also
records the Docker Desktop control address and narrowly adds that address to
Honua's allowed-host list. Host validation stays enabled; measured k6 requests
use the existing private service addresses. Changed inputs require a new campaign.
The complete six-file patch was verified on trunk merge
`832ff62dce921b06411073cf3cf4d945cc830c27`.

The host-side coordinator previously stopped during a long campaign. The new
coordinator is a detached, exactly labelled Docker container with a pinned local
image, one CPU and 1 GiB. Preflight proved visibility of the actual shared build
and measurement locks across WSL/Desktop and reachability of private published
ports. Source and qualification inputs are mounted read-only; result and state writes
stay in owned directories. Docker socket access provides orchestration; the
existing build locks are mounted read-only and the measurement lock read/write. Its image and
packages were prepared outside measurement. This coordinator does not establish
isolated-generator calibration or publication suitability.

## Qualification and identities

- Server source remains `5349cce68e232fbf92ccbb88bcbe3a8f4817a2df`,
  [PR #5343](https://github.com/honua-io/honua-server/pull/5343), still draft
  pending the combined performance qualification.
- Honua JIT image remains
  `sha256:5a8d9c7e3ecbdb8ce6b36dc75adcc9a74dd820c4f623f2d023302b3955cabd48`;
  the inspected runtime maps CoreCLR. Earlier test/package qualification is
  recorded in the [batch note](jit-optimization-batch-20260930.md).
- Frozen harness: `869d19e75bdf456c508b561d966652921cfd9dc5`.
- Coordinator image:
  `sha256:dc122da1f278221345489e361a4b0d4f0f632c6dc5d4ec143a7fe1c29092bd0a`.
  Its Docker CLI base is pinned to
  `docker.io/library/docker@sha256:b1805116a6a86cc591b5d5f60a910a0715cdcc9d18d866ad68b1457ead25c35c`.
- Existing GeoServer, PostGIS, k6 and dataset identities are unchanged from the
  preceding qualified batch; their references and effective settings are
  captured in the new manifest.
- All 86 Python tests, Ruff, Python compilation, JavaScript syntax checks,
  ShellCheck and hosted CI/CodeQL passed at the frozen harness head.
- HTTP smoke passed equality, range, prefix, small/medium/large bboxes,
  shallow/medium/deep pages, empty, boundary and mixed 10-VU traffic for both
  products: 24 measured rows. The report is valid for diagnostics and explicitly
  not publishable. Both attempts passed semantic and fairness checks; exact owned
  cleanup completed.

The first container-coordinator smoke failed Honua provisioning because the
control hostname was not allowed. GeoServer completed its 12 rows in that
attempt; the overall smoke is failed. Its logs, report and owned cleanup remain
visible. The corrected run uses a new directory. Neither that failure nor the
older interrupted campaign was replaced with a passing attempt.

## Performance and remaining work

The running comparison schedules three paired repetitions, seed 42, all 12
existing rows, 30-second warmup and 30-second measurement with explicit drain.
Server/database budgets remain 4 CPUs / 4 GiB each, source pools remain six,
and the generator has the same eight-CPU budget for both products. Exact
response caching and adaptive admission remain disabled; normal metadata caches
remain. Repetitions recreate isolated stacks and reverse server order.

The earlier [single-pair ratios](jit-optimization-batch-20260930.md) belong to the
test-schema-enabled configuration. They cannot be treated as results of this
production-settings campaign. The first corrected pair passed all 24 rows and completed owned cleanup.
Honua led throughput in 10 of 12 rows. These are provisional ratios recalculated
from retained attempt summaries; the remaining repetitions and independent raw
sample verification are still required. They do not establish repeatable gains
or attribute changes to the test-hook correction.

| Existing scenario | Honua / GeoServer throughput | p50 | p95 | p99 |
| --- | ---: | ---: | ---: | ---: |
| page-shallow | 0.970 | 1.020 | 1.064 | 1.105 |
| page-medium | 0.978 | 1.024 | 1.038 | 1.044 |
| empty | 1.336 | 1.185 | 0.270 | 0.309 |
| bbox-boundary | 1.274 | 1.075 | 0.369 | 0.414 |
| range | 1.077 | 0.931 | 0.931 | 0.914 |

Higher throughput ratios favor Honua; lower latency ratios favor Honua. Shallow
and medium pages trail slightly across these metrics. Empty and boundary reads
lead throughput and tail latency but trail median latency. The earlier range
tail deficit does not appear in this pair; repeatability remains unproven.

The independent code review prioritizes batching RLS and field-mask reads on one
catalog lease, followed by reuse of the already authorized request metadata
snapshot. These target fixed overhead in empty, boundary and cheap page reads.
Anonymous wildcard policies, publication/service scopes, cancellation and
fail-closed behavior must remain unchanged. Native decoding targets nonempty
page allocation; range planner changes require separate bottleneck evidence.

Native primitive attribute decoding is now
[draft PR #5349](https://github.com/honua-io/honua-server/pull/5349), current source
`7f9a4aa8f` (branch head at this checkpoint). The prior head passed format and
affected server shards but failed build on two CA1859 warnings in the new
test helper. The concrete collection signatures were corrected and pushed;
exact-head build/test qualification is pending. No allocation or HTTP improvement is claimed. It is
not included in the frozen comparison image. Authorized metadata reuse is now [draft PR #5351](https://github.com/honua-io/honua-server/pull/5351),
source `259c4cad6c462dc1c35b0290f0cd23fe1e2e2af5`. Both OGC item handlers use the
validation snapshot. Security sources reuse it only for the identical canonical
resource in the same request and use immutable service-name scopes built from
first-wins publication/service IDs. Tests were added for graph revisions, failed
authorization, duplicate IDs/names, principal changes, anonymous wildcard roles,
fresh policies and request/resource isolation. Its exact-head format gate passed;
compilation and semantic gates remain pending. No speed gain is claimed.

An isolated integration checkout at `e110a28cb4b3b5a64fd3b0e4c279a2099fb35f06`
combines both drafts with the already qualified bounded-planning/shared-GeoJSON
batch. It is clean and pushed to `qualification/native-metadata-20261001`. Its
qualification driver was syntax checked and its selection recipe inspected; no
build/test was executed during current timed traffic. The driver requires actual
terminal-success of the prior Docker coordinator, the passed comparison receipt,
and both shared locks before heavy work. All previous WFS selection cases remain
in the new recipe. Fresh compilation will stamp the actual integration source.

Policy-read batching and direct UTF8 output remain follow-up candidates; security
policy/credential caches based only on TTL are not proposed.

Final production AOT and strict feature publication remain deferred until all
optimization and required correctness, fairness, calibration and performance
work is complete. Existing WFS/rendering/tile tracks follow the feature foundation.

## Retained local evidence

Under `results/jit-optimization-batch-20260929/`:

- `production-settings-checks-v4-20261001/receipt.json` records the tested source
  file hashes and all checks.
- `production-settings-smoke-receipt-20261001.json` records the new smoke and
  its report hash; `pr-34-landed.json` verifies the whole merged patch.
- `durable-coordinator-20261001/` retains failed preflights, the failed first
  smoke coordinator, terminal logs and verified owned cleanup.
- `durable-coordinator-v2-20261001/launch-receipt.json` records the exact active
  coordinator identity, image, resource limits and mounts. Its state receipt
  identifies the current campaign directory and updates every five seconds.
- `harness-control-checkout/results/integrated-production-smoke-v2-20261001/`
  contains the complete corrected smoke; the comparison is separately retained
  at `integrated-production-comparison-v2-20261001/`.

- `production-first-pair-provisional-20261001.json` records the preliminary
  ratios and SHA256 of the separate passed-attempt snapshot; this checkpoint
  does not replace the running campaign or its earlier failed attempts.

- `native-metadata-integration-preparation-20261001.json` binds both candidate
  heads, applied commits, changed input hashes and the checked qualification
  recipe. Its explicit status is prepared, not built or tested.
