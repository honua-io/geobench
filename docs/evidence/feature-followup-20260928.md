# Feature comparison follow-up — 2026-09-28

Scope: seed-42 100K points, source-backed PostGIS reads, anonymous OGC API
Features, bounded four-CPU/four-GiB services and six source connections.
This follow-up resolves the source-pool blocker and adds runnable local observer
calibration. It does not produce a publishable product comparison.

## Updated runtime

The published Native AOT image
`ghcr.io/honua-io/honua-server@sha256:b72513a9a724d7331d8b2a0285b2a29b8f8de9b865f381a1c95192a31da73091`
records revision `75e88443eb008ac010f890d16e9efcbcf421dd50`. That revision includes
[`c1ede6f63`](https://github.com/honua-io/honua-server/commit/c1ede6f634cfa984c204db5a4cf5c5336086939a),
which routes bound-source reads through shared admission and configured pools.
The fix was already merged; this work verified its published runtime rather than
creating another server patch. Runtime receipts confirm `/app/Honua.Server`, no
CoreCLR mappings, and effective four-CPU/four-GiB budgets.

GeoServer remains the prepared stable 3.0.1 OGC extension image
`sha256:a395701a5eea4884c855f136be84363d0ce05e06da1ea6c7e3b84e146279927b`.
PostGIS and k6 retain the immutable identities in the [initial evidence](feature-campaign-20260928.md).

## Complete smoke campaign

`results/feature-aot-followup-smoke-20260928` passed all **40 rows**: each product
completed eleven corpus scenarios, four closed-loop mixed concurrency levels,
and five fixed arrival rates. Every response underwent oracle validation. The
campaign used two-second warmup and three-second measurement windows and only
supports harness validation, not capacity or product-performance claims.

Both products passed the source-query SQL pass, full-corpus preflight, database
fingerprints and runtime checks. Sampled source sessions/active queries stayed
at or below six for both products. Maximum sampled parallel workers were six
for Honua and one for GeoServer; these are separate from client connections and
remain visible in the telemetry under the equal database CPU budgets.

The report is diagnostic-valid and not publishable. Honua's measured samples had
no clock anomalies. GeoServer's 240 req/s mixed row included one auxiliary
`http_req_receiving` value of **−38.252283 ms**, which is retained and rejects
publication. Custom window/latency accounting uses monotonic executor progress.
Both smoke stacks and their private resources were removed.

## Local observer calibration

The new `scripts/run-observer-calibration.py` collects actual observer-off/on
samples from a prepared campaign, with separate ledgers, raw hashes, alternating
order, fresh owned stacks, normal preflights and explicit drain. It cannot approve
publication without an isolated-generator comparison. Interrupted attempts remain
visible and cleanup validates exact resource ownership. Calibration validation
also rejects reused raw files across treatments and clock anomalies.

`results/feature-observer-followup-20260928` records three paired repetitions for
each product at `mixed:vus:10`, using diagnostic 30-second warmup and 30-second
measurement windows. These durations and this selected workload do not qualify
as calibration for a strict campaign. See the [operating guide](../feature-campaigns.md)
for the command and the strict 180s/120s preparation option.

All six product/repetition attempts completed; all twelve measured treatment
samples had zero invalid responses and zero cancellations. Each sample's warmup,
late completions and measured traffic remain separate. The source-budget checks
passed. The calibration gate rejected the evidence: GeoServer samples contained
nine auxiliary clock anomalies, and each product exceeded 5% on one observer
comparison metric.

| Product | Observer off median req/s | Observer on median req/s | Throughput change | Observer off median p95 ms | Observer on median p95 ms | p95 change |
|---|---:|---:|---:|---:|---:|---:|
| Honua AOT | 35.67 | 33.23 | −6.82% | 580.85 | 607.04 | +4.51% |
| GeoServer | 71.27 | 74.20 | +4.12% | 257.22 | 241.10 | −6.27% |

These are medians of per-repetition statistics, not a combined latency
distribution or an average of percentiles. The per-repetition observer-on
throughput ratios, GeoServer/Honua, were 2.112, 2.233 and 2.195 (median **2.195**).
Observer-off paired ratios were 1.686, 1.998 and 2.101 (median **1.998**).
For this diagnostic mixed workload, GeoServer completed roughly twice as many
valid requests per second. The smoke attribute-filter rows favored Honua, but
three-second windows cannot establish sustained filter performance. There is
no overall or publishable winner claim.

The JSON ledger retains each treatment's counts, throughput, p95, raw path/hash
and phase duration. A final audit at harness `862c5c9` re-read all twelve raw
measurement windows, verified their full mixed-request coverage and all retained
artifact hashes, and wrote `observer-ea4d7cbd2a-verified-report.json`. It retains
the diagnostic medians while rejecting clock-invalid calibration. The original
collector report and raw evidence are unchanged.

## Strict gate and remaining prerequisites

`results/feature-comparison-followup-20260928` records the normal five-pair,
fifteen-scenario, 180s/120s schedule. Both products passed the complete oracle,
source-query and bounded-pressure preflights. Both stopped before timed comparison
traffic because no strict calibration receipt exists. The eight remaining server
attempts are explicitly `not-run`; there are no strict measurement rows or
publication approval.

The available environment is WSL with local Docker. No separate generator host
was supplied or configured. A publishable campaign still needs a setup without
clock anomalies, observer-on/off and isolated-generator calibration within 5%,
and all five paired comparison repetitions. The short observer diagnostics above
cannot replace those prerequisites. GSR remains a separate community profile;
this follow-up makes no new GSR, rendering, line/polygon or memory-leak claims.

All **37 harness tests** pass, including interrupted calibration recovery,
ownership refusal, observer phase separation, reused-treatment rejection and
clock rejection. Ruff, Python compilation, all k6 JavaScript syntax checks,
Bash syntax checks and CI's warning-level ShellCheck command pass. The final raw
calibration audit verified all required mixed requests and artifact hashes.

Cleanup-only was also exercised against the completed collector ledger. Final
inspection found no campaign-labelled containers, volumes or networks. All five
unrelated containers present at the start remained running. Failed attempts and
both original and verified reports remain retained under their campaign paths.
