# AGENTS.md

## Overview

GeoBench is an open, vendor-neutral benchmark suite for geospatial feature and
map servers ("TechEmpower for GIS"). It runs reproducible k6 workloads against
GIS servers (Honua Server, GeoServer, QGIS Server), each backed by its own
dedicated PostGIS instance, and produces run artifacts, response-shape audits,
system cards, and generated reports.

This repo is an orchestration/benchmark harness, not an application server. It
spins Docker stacks up and down, drives load with k6, and post-processes results
with Python. See `README.md` and `METHODOLOGY.md` for the full protocol matrix,
fairness rules, and reporting requirements.

## Tech Stack

- Orchestration: Bash (`scripts/run-benchmark.sh`, `set -euo pipefail`)
- Load generation: k6 workloads written in JavaScript (`src/tests/*.js`),
  run via the `grafana/k6:0.54.0` container
- Post-processing / reporting / audits: Python 3 (standard library; no
  `requirements.txt` / `pyproject.toml` present)
- Servers under test (Docker): Honua Server (.NET 10), GeoServer (Java/JVM),
  QGIS Server (C++/Qt)
- Database: PostGIS (`postgis/postgis:17-3.5`), one instance per server
- Containerization: Docker + Docker Compose v2 (`docker-compose.yml`, uses
  Compose profiles `honua`, `geoserver`, `qgis`)

## Setup

Requirements (from `README.md`): Docker with Docker Compose v2, Python 3, `jq`,
`curl`.

1. Optionally copy `.env.example` to `.env` and adjust image tags, host ports,
   credentials, and benchmark defaults. The harness reads these env vars.
2. Generate the deterministic dataset (writes `data/small/init.sql`, which is
   gitignored):

   ```bash
   python3 data/small/generate.py
   ```

Do not commit `results/<timestamp>/`, `data/small/init.sql`, `pgdata/`, or
`.env` — all are gitignored.

## Commands

Run the default benchmark suite (Honua, GeoServer, QGIS; tests
`attribute-filter spatial-bbox concurrent`; 5 runs):

```bash
./scripts/run-benchmark.sh
```

Quick local validation run:

```bash
RUNS=1 SERVERS="honua geoserver" TESTS="attribute-filter" \
  ATTRIBUTE_FILTER_WARMUP=5s ATTRIBUTE_FILTER_DURATION=10s \
  ./scripts/run-benchmark.sh
```

Select tracks/servers via env vars (`TESTS`, `SERVERS`); see README "Running
Specific Tracks" for per-track examples (WMS, WFS, WMTS, WCS, GeoServices REST).

Smoke test (1 VU, 5s per server; requires a running stack):

```bash
./tests/smoke-test.sh
```

Generate a report from an existing result directory:

```bash
python3 scripts/generate-report.py \
  --results-dir results/<timestamp> --output results/<timestamp>/report.md \
  --runs 5 --servers honua,geoserver
```

Fairness audit before publishing a snapshot:

```bash
python3 scripts/audit-fairness.py \
  --results-dir results/<timestamp> --servers honua,geoserver \
  --strict-equal-db-budget
```

No formal lint/build/test runner or CI workflow is configured (no
`.github/workflows`, no `package.json`, no `Makefile`).

## Architecture

- `scripts/run-benchmark.sh` is the orchestrator. For each server it brings up
  that server's Compose profile (PostGIS + server + k6), runs each selected test
  category for `RUNS` iterations, captures raw k6 JSON, response-shape audits,
  system cards, and metadata, then tears the stack down (`docker compose ...
  down -v`) before moving to the next server. No shared DB/state across servers.
- Each test category maps to a k6 script in `src/tests/` (e.g.
  `attribute-filter.js`, `wms-getmap.js`, `geoservices-query.js`). Shared logic
  lives in `helpers.js`, `wms-helpers.js`, `wfs-helpers.js`,
  `geoservices-helpers.js`, `raster-helpers.js`, `deterministic.js`.
- Server selection is via the `SERVER` env var inside k6, resolved against the
  `SERVERS` map in `src/tests/helpers.js` (`honua`, `geoserver`, `qgis`, each
  with a `baseUrl` overridable by `*_URL` env vars).
- Per-server provisioning is done by `adapters/<server>/setup.sh` (loads data,
  configures layers/styles). GeoServer uses an SLD style; QGIS uses a `.qgs`
  project file.
- Python scripts in `scripts/` handle reporting (`generate-report.py`),
  fairness (`audit-fairness.py`, `validate-fairness.py`), loss ledgers
  (`generate-loss-ledger.py`), diagnostics (`diagnostics-monitor.py`,
  `generate-diagnostics-summary.py`), and response-shape audits
  (`response-shape-audit.py`).
- `docker-compose.yml` defines `postgis-<server>`, the three servers, and the
  `k6` runner, gated by Compose profiles. Containers are constrained to 4 CPU /
  4 GB each per the methodology.

## Directory Layout

```text
geobench/
|-- adapters/        # Per-server provisioning: <server>/setup.sh, styles, QGIS project
|-- data/small/      # generate.py -> deterministic 100k-point dataset (init.sql, gitignored)
|-- docs/            # Investigation notes, matrix status, feature docs, issue drafts
|-- results/         # Local benchmark output, results/<timestamp>/ (gitignored)
|-- scripts/         # run-benchmark.sh orchestrator + Python reporting/audit/diagnostics
|-- src/tests/       # k6 benchmark scripts (*.js) and shared helpers
|-- system-cards/    # Server config metadata: honua.json, geoserver.json, qgis-server.json
|-- tests/           # smoke-test.sh
|-- docker-compose.yml
|-- .env.example     # Image tags, ports, credentials, benchmark defaults
|-- METHODOLOGY.md
`-- README.md
```

## Conventions & Gotchas

- Configuration is entirely env-var driven. Key vars: `SERVERS`, `TESTS`,
  `RUNS`, `AUDIT_SHAPES`, `DIAGNOSTICS`, per-test `*_WARMUP` / `*_DURATION` /
  `*_SCENARIOS`, image tags (`HONUA_IMAGE`, `GEOSERVER_IMAGE`, `QGIS_IMAGE`,
  `POSTGIS_IMAGE`, `K6_IMAGE`), and ports. See `.env.example` and the top of
  `scripts/run-benchmark.sh`.
- Always run `python3 data/small/generate.py` before the first benchmark;
  `data/small/init.sql` is generated and gitignored.
- The harness assumes invocation from the repo root; `run-benchmark.sh` derives
  `PROJECT_DIR` from its own path, but Compose profile commands run relative to
  cwd.
- Pin Docker image tags/digests for reproducibility; published headline rows
  record exact images in their result directory metadata.
- Adding a new server requires four things: a Docker image exposing the API,
  `adapters/<server>/setup.sh`, an entry in the `SERVERS` map in
  `src/tests/helpers.js`, and `system-cards/<server>.json`.
- GeoServer's GeoServices REST (GSR) is not in the stock image; it needs the
  `gsr` community extension and `GEOSERVER_GSR_ENABLED=1`.
- Cache tier and DB admission are benchmark dimensions, not toggles to maximize.
  Baseline rows use no exact response cache and bounded fixed DB admission; keep
  cache-assisted and adaptive-admission results in separately named profiles.
- No automated tests, linters, or CI exist. Validate changes manually via
  `tests/smoke-test.sh` and short `RUNS=1` benchmark runs.
- License: Apache 2.0.

## Shared dev-environment rules (multi-agent WSL)

This machine runs many agents concurrently (**Codex + Claude**, often via agentflow with multiple tabs/agents). To prevent host lockups and lost work, every agent MUST follow these:

1. **Heavy builds/tests are throttled by a shared lock.** `dotnet` and `npm` are PATH-shimmed, so their build/test/publish/pack and ci/install/test/run-build/run-test subcommands automatically run under a global semaphore (default 1 concurrent, `HONUA_BUILD_SLOTS`). For other heavy tools, call the wrapper explicitly: `with-build-lock pytest ...`, `with-build-lock cargo build`, `with-build-lock make build`. The lock is shared across ALL of this user's processes (every Codex/Claude tab, agentflow children). Do not bypass it for compiles or test suites. Long-running servers (`dotnet run`, `npm run dev`) are intentionally NOT locked — never wrap those.

2. **Commit and push when you finish a task** so your worktree can be reclaimed. An hourly job (`honua-clean`) removes a worktree ONLY when it is clean AND fully pushed (merged, remote-gone, or idle >=2d). Dirty or unpushed worktrees are NEVER touched — but uncommitted/unpushed work blocks reclamation and is at risk if the instance is reset. Build artifacts (bin/obj and untracked node_modules) are reclaimed automatically and safely.
