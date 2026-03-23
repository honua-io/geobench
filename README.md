# GeoBench

Open, vendor-neutral benchmark suite for geospatial feature servers. Think [TechEmpower](https://www.techempower.com/benchmarks/) for GIS.

## Why

There's no standardized way to compare geospatial feature server performance. Vendor benchmarks are self-serving. GeoBench provides reproducible, independently verifiable numbers that anyone can run.

## Servers Tested

| Server | Runtime | Image |
|--------|---------|-------|
| [Honua Server](https://github.com/honua-io/honua-server) | .NET 10 | `honuaio/honua-server:latest` |
| [GeoServer](https://geoserver.org/) | Java / JVM | `kartoza/geoserver:2.26.1` |
| [QGIS Server](https://qgis.org/en/site/about/features.html#qgis-server) | C++ / Qt | `qgis/qgis-server:3.38` |

All servers are tested via **OGC API Features** against the same shared PostGIS database with identical resource constraints (4 CPU, 4 GB RAM).

## Quick Start

**Requirements**: Docker, Docker Compose v2, Python 3, jq, curl

```bash
# 1. Generate the test dataset (100K points)
python3 data/small/generate.py

# 2. Start all services
docker compose up -d

# 3. Run the full benchmark suite
./scripts/run-benchmark.sh
```

Results are written to `results/<timestamp>/report.md`.

For a quick validation without running full benchmarks:

```bash
docker compose up -d
./scripts/wait-for-healthy.sh
bash tests/smoke-test.sh
```

## Test Categories

| Category | Description | VUs | Duration |
|----------|-------------|-----|----------|
| `attribute-filter` | Equality, range, LIKE queries via CQL2 | 10 | 120s each |
| `spatial-bbox` | Small/medium/large bounding box queries | 10 | 120s each |
| `concurrent` | Mixed workload at 1/10/50/100 VUs | 1-100 | 120s each |

## Dataset

**Small** (default): 100,000 point features with 10 attribute fields.

- Deterministic generation (`seed=42`) for reproducibility
- 60% spatially clustered (NYC, Paris, Tokyo, Sao Paulo, Sydney), 40% global
- Attributes: category (10 enum), status (5 enum), priority (1-5), temperature (float), population (int), timestamps, country code, description
- PostGIS GiST spatial index + btree indexes on filterable columns

## Methodology

See [METHODOLOGY.md](METHODOLOGY.md) for the complete fairness and reproducibility framework, including:

- Identical resource constraints per server
- 60-second warmup before all measurements
- 5 runs with median reporting
- Mandatory system cards
- Caching and connection pool policies

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                  Docker Network                       │
│                                                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │  Honua   │  │GeoServer │  │  QGIS    │           │
│  │  :8080   │  │  :8080   │  │  :80     │           │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘           │
│       │              │              │                 │
│       └──────────────┼──────────────┘                 │
│                      │                                │
│               ┌──────┴──────┐                         │
│               │   PostGIS   │                         │
│               │   :5432     │                         │
│               └─────────────┘                         │
│                                                       │
│  ┌──────────┐                                         │
│  │    k6    │─── OGC API Features ──► servers         │
│  └──────────┘                                         │
└──────────────────────────────────────────────────────┘
```

## Project Structure

```
geobench/
├── data/small/          # Dataset generation
├── adapters/            # Per-server setup scripts
├── src/tests/           # k6 benchmark scripts
├── scripts/             # Orchestration & reporting
├── system-cards/        # Server configuration metadata
├── configs/             # Default & tuned configs per server
├── results/             # Benchmark output (gitignored)
└── tests/               # Smoke tests
```

## Contributing

Adding a new server requires:

1. A Docker image that exposes OGC API Features
2. An adapter script in `adapters/<server>/setup.sh`
3. A server entry in `src/tests/helpers.js`
4. A system card in `system-cards/<server>.json`

See existing adapters for examples. PRs welcome.

## License

Apache 2.0. See [LICENSE](LICENSE).
