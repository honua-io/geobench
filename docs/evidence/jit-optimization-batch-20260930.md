# JIT optimization batch qualification — September 30, 2026

The combined automatic-planning and shared-GeoJSON-preparation candidate passed
local correctness qualification and all 12 existing HTTP oracle scenarios. The
three paired diagnostic repetitions are running; there is no new speed ratio or
claim of parity yet. These checks cover the deterministic 100K-point dataset.

Optimization uses Release JIT by user instruction. Final production AOT and
strict GeoBench publication remain deferred until the remaining optimizations and
all final correctness, fairness, calibration and performance gates pass.

## Candidate and harness identities

- Server [PR #5343](https://github.com/honua-io/honua-server/pull/5343),
  source `5349cce68e232fbf92ccbb88bcbe3a8f4817a2df`. It remains draft pending paired performance qualification.
- Local Release JIT image `sha256:5a8d9c7e3ecbdb8ce6b36dc75adcc9a74dd820c4f623f2d023302b3955cabd48`.
- Frozen harness `fc1a35e4809ab9fa948700630fc80ba17442e91e`.
  [GeoBench PR #33](https://github.com/honua-io/geobench/pull/33) merged as
  `1aff0b7079a26ee370569b2728e705365f2b3679`; its complete patch was verified
  present on fetched trunk. Running inputs remain frozen at the pre-merge hash.
- Historical seed-42 dataset artifact SHA-256
  `2ca9025b025361a85e7e0866a80748d29dacd44d27987ce75631a7473189a525`.
- GeoServer image `sha256:32b61aed98bca6cc0821fbcdab9dbc5b9b22b6fa1af6d51d396fb64e63dac491`. It was rebuilt
  outside measurement from the pinned 3.0.1 base with the matching OGC API
  extension. All 310 installed JAR hashes match the preceding image manifest;
  the new image identity is retained separately.

The build's assembly informational-version stamp still contains historical source
`e2bf1bf5e236566a056d1d078fa98f784e5df36b`. That stamp is not the candidate's
source identity. The clean source checkout, successful current-source compilation,
test-output assembly hashes, published hashes and image revision label establish
the candidate identity above. Packaging used `--no-build --no-restore`, and all
nine checked application/provider/protocol assemblies match all four tested
outputs. Runtime inspection confirms CoreCLR and `dotnet Honua.Server.dll`.

## Correctness and allocation evidence

[Hosted PR Gate](https://github.com/honua-io/honua-server/actions/runs/36649419060)
passed build/tests, analyzers, formatting and selected server shards at this exact
source head. Local tests completed with no failures or skips:

| Database | Selection | Passed |
|---|---|---:|
| PostgreSQL 17 | Mapped provider/planner | 227 |
| PostgreSQL 17 | OGC API feature/GeoJSON | 49 |
| PostgreSQL 17 | GeoServices query formatters/GeoJSON | 108 |
| PostgreSQL 17 | Changed WFS JSON/count/axis/temporal/paging paths | 12 |
| PostgreSQL 16 | Mapped provider/planner | 227 |
| PostgreSQL 18 | Mapped provider/planner | 227 |

All owned test database, Redis and network resources were cleaned. The WFS
selection is targeted coverage, not a claim that the whole endpoint or CITE suite
was rerun locally.

The current-head 100-feature declared-field builder fixture allocated 63,720
bytes with request preparation and 115,200 without it. Sparse rows on a 512-field
schema and one-field projections each allocated 28,488 bytes. These fixtures
measure allocation only; they do not establish HTTP throughput improvement.

HTTP smoke passed equality, range, prefix, small/medium/large bboxes,
shallow/medium/deep pages, legitimate empty results, the bbox boundary case and
mixed traffic at 10 VUs. The separate SQL diagnostic confirms reads of
`public.bench_points` and executed scoped planning with both serial options
omitted. The report is valid for diagnostics and explicitly not publishable.
The existing prefix case still does not establish general escaped-underscore
semantics; see the [source-review limitation](geoserver-source-review-20260928.md).

## Paired comparison and remaining work

The running comparison uses the same 12 rows, three paired repetitions, seed 42,
30-second warmup, 30-second measurement, explicit drain, fresh owned stacks and
separate 4-CPU/4-GiB server/database budgets. The generator has an equal eight-CPU
budget for both products; source pools remain six connections. Exact response
caching and adaptive admission are disabled. Normal metadata caches remain.

Per-repetition throughput and p50/p95/p99, median/range summaries, paired ratios,
semantic failures, warmup/drain traffic and observed resource pressure are retained
separately. No averaged percentile or cross-protocol winner score is used. This
shared WSL run cannot satisfy isolated-generator calibration for publication.

Typed native-column decoding and direct UTF8 output remain planned work. The
combined candidate must first complete its paired qualification; final AOT is
not requested during this optimization cycle. Existing WFS/rendering/tile tracks
follow the feature foundation, as described in the original plan.

## Local receipts

All current receipts and earlier failed/interrupted attempts are retained under
`results/jit-optimization-batch-20260929/`:

- `integrated-pg17-tests-recovered/receipt.json`, `integrated-pg16/receipt.json`
  and `integrated-pg18/receipt.json`, with raw TRX files and hashes.
- `allocation-contained-20260930.json` and `jit-image-integrated/receipt.json`.
- `restored-images-r2/receipt.json`, including the unchanged-JAR comparison.
- `smoke-integrated-receipt.json` and its recorded raw output directory.
- `integrated-contained-campaign-receipt.json` and its recorded raw output
  directory, currently running.
- `pr-33-landed.json`, recording content verification on trunk.

The interrupted compilation attempt is recorded as interrupted after a
successful build. Its assemblies were checked and reused, and every qualification
selection was rerun; no interrupted test completion is claimed as a pass.
