# Build a Loss-Ledger and Diagnostics Pipeline for Winning Every Benchmark Row

## Context

Honua now wins many GeoBench rows, but not all of them. The remaining work should be driven by
repeatable evidence instead of one-off tuning. Each losing row needs the same diagnostic package:
what was requested, what each server returned, what SQL ran, what the runtime was doing, and what
GeoServer/GeoTools does differently when it wins.

## Goal

Create a systematic pipeline that ranks every Honua loss, generates a diagnostics dossier for the
highest-value losses, and turns each dossier into a bounded Honua optimization ticket.

## Non-Goals

- Do not change benchmark fairness rules to create wins.
- Do not fold Redis, generic response caching, or larger memory/pool tracks into baseline results.
- Do not copy GeoServer architecture wholesale; inspect it only to explain winning rows.
- Do not optimize before the row has a reproducible loss dossier.

## Phase 1: Loss Ledger

Implemented first slice: `scripts/generate-loss-ledger.py` reads one or more `report.json` files
and produces:

- `loss-ledger.json`
- `loss-ledger.md`

Proposed command:

```bash
python3 scripts/generate-loss-ledger.py \
  results/20260425-213925/report.json \
  results/20260329-090404/report.json \
  results/20260331-212245/report.json
```

Each ledger row should include:

- benchmark family and row
- scenario, workload tag, and metric
- Honua value
- competitor value
- winner
- gap ratio or percent delta
- run count and confidence level
- status: `loss`, `near-tie`, `unsupported`, `pending`, `blocked`, or `stale`
- suggested bottleneck class: `sql`, `renderer`, `projection`, `serialization`,
  `admission`, `feature-gap`, `cache-tier`, or `unknown`
- link to the source report

Initial ranking policy:

1. unsupported comparable rows first, such as `wms-getfeatureinfo` returning `405`
2. high-confidence p95/p99 losses
3. high-confidence throughput losses
4. pending canonical reruns
5. stale or single-run evidence

## Phase 2: Diagnostics Dossier Mode

Implemented first slice: `DIAGNOSTICS=1 ./scripts/run-benchmark.sh` runs a narrow row/scenario and
writes a dossier under:

```text
results/<run>/diagnostics/<server>/<test>/<scenario>/
```

Minimum artifacts:

```text
request.txt
response.headers
response.sample
output-shape.json
runtime-monitor.ndjson
sql-statements.log
explain/
  001.sql
  001.explain.json
server.log
```

Top-level comparison artifact:

```text
results/<run>/diagnostics/comparison.json
```

Current implementation writes `output-shape.json`, `runtime-monitor.ndjson`,
`sql-statements.log`, `server.log`, `postgis.log`, and `comparison.json`. Separate
`request.txt`, `response.headers`, `response.sample`, and `explain/` artifacts remain follow-ups;
the first slice keeps request URL, status, content type, byte count, hash, and shape summary inside
`output-shape.json`.

`comparison.json` should summarize:

- response status and content type
- byte size
- feature count or image dimensions
- response-shape verdict
- representative SQL count
- slowest SQL statement
- DB acquisition/admission signals when available
- container CPU/memory maxima
- likely bottleneck class

Proposed command shape:

```bash
DIAGNOSTICS=1 \
DIAGNOSTIC_TEST=wms-reprojection \
DIAGNOSTIC_SCENARIO=medium \
SERVERS="honua geoserver" \
RUNS=1 \
./scripts/run-benchmark.sh
```

## Phase 3: SQL Capture and Explain

Started with Postgres-side capture so GeoServer can be analyzed without invasive instrumentation.

For diagnostic runs, configure the isolated PostGIS container with:

- `log_min_duration_statement=0`
- statement duration logging
- optional `auto_explain` with `ANALYZE` and `BUFFERS` for short, single-scenario runs

Current implementation enables `log_min_duration_statement=0` when `DIAGNOSTICS=1` and extracts
matching Postgres log lines to `sql-statements.log`. It also writes
`geobench_diagnostics_start` and `geobench_diagnostics_end` SQL markers around the timed diagnostic
window. `auto_explain` and representative
`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` capture remain follow-ups.

The diagnostics collector should:

- isolate the request window
- copy Postgres logs into the dossier
- normalize repeated statements
- redact credentials and connection strings
- run `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` for representative statements when safe
- preserve bind values or reconstructed literals when the server logs make them available

Honua should eventually expose generated SQL in an explicit diagnostic mode. That is useful but not
required for the first GeoBench implementation because Postgres logging covers both Honua and
GeoServer.

## Phase 4: Runtime Monitoring

Implemented first slice: `scripts/diagnostics-monitor.py` captures lightweight time-series samples
during diagnostic runs:

- Docker CPU and memory for server, PostGIS, and k6 containers
- Postgres `pg_stat_activity`
- Postgres wait events
- connection counts
- Honua `/monitoring/metrics/connection-pool`
- Honua query-admission fields:
  - current limit
  - queued waiters
  - duration EWMA
  - queue-wait EWMA when available
  - adjustment count
- GeoServer logs for request errors, JVM pressure, and rendering warnings

Write samples as newline-delimited JSON:

```text
runtime-monitor.ndjson
```

## Phase 5: GeoServer Source Intelligence

For every high-priority GeoServer win, inspect only the relevant source path and record findings in
the dossier. The output should identify concepts to adapt, not code to copy.

Rows likely to need source inspection first:

- `wms-reprojection` medium/large:
  - GeoServer WMS path
  - GeoTools `StreamingRenderer`
  - CRS transform and viewport clipping
  - style-aware query reduction
- `geoservices-query` medium/large:
  - GeoServer GSR extension query translation
  - bbox handling
  - property selection
  - feature-limit behavior
- `wmts`:
  - GeoWebCache key model
  - finite tile matrix keys
  - metatiling
  - seed/truncate lifecycle

Each source note should include:

- repository and commit/tag inspected
- files/classes inspected
- observed strategy
- Honua-native implication
- risk if adopted

## Phase 6: Optimization Loop

Every optimization ticket should follow this loop:

1. pick the top loss-ledger row
2. generate a dossier
3. classify the bottleneck
4. inspect GeoServer source only if competitor behavior is materially different
5. patch Honua or GeoBench narrowly
6. run a 1-run smoke
7. run 3-5 repeats if the smoke improves
8. update the ledger
9. promote the row only if response-shape comparability and p95/p99 guardrails hold

## Initial Priority Queue

1. `wms-getfeatureinfo`: Honua returns `405`; unblock comparability before performance tuning.
2. `wms-reprojection` medium/large: GeoServer has a large win and likely renderer/projection
   architecture lessons.
3. `geoservices-query` medium/large: seed-sensitive GeoServer advantage needs SQL and output
   comparison.
4. `concurrent` LIKE/range tails: use workload-tagged rows plus admission telemetry.
5. `wmts`, `wcs`, `geoservices-identify`: finish canonical coverage before optimizing.

## Acceptance Criteria

- A loss-ledger script ranks Honua losses across supplied `report.json` files.
- Diagnostics mode writes output, SQL, explain, logs, and monitor artifacts for at least one
  Honua-vs-GeoServer row.
- The first dossiers are produced for `wms-reprojection/medium` and
  `geoservices-query/medium` or the current top two ledger rows.
- Each dossier contains enough evidence to assign the bottleneck class without guessing.
- GeoServer source inspection notes are attached for rows where GeoServer is the clear winner.
- Benchmark reports and optimization notes distinguish baseline, tuned-memory, cache-assisted,
  adaptive-admission, and Redis-coordinated tracks.

## Definition of Done

The pipeline is considered usable when a new engineer can run one command to generate the current
Honua loss ledger, run one command to collect a dossier for the top loss, and open an optimization
ticket with request/output/SQL/runtime/source evidence attached.
