# Source-backed feature campaigns

`config/feature-corpus-v1.json` is the shared contract for the deterministic
100K-point dataset. It covers equality, numeric range, literal prefix (escaped
underscore), three bbox sizes, three page depths, legitimate empty results,
and an inclusive boundary anchored on dataset point 1. Mixed traffic repeats
a deterministic 40/30/20/10 bbox/equality/range/prefix sequence. Every request
asks for 100 features, all source fields, geometry, ascending source ID,
anonymous reads and identity compression. OGC uses CRS84; GSR uses EPSG:4326
with x/y ordering. Attribute dates are compared as instants with protocol-specific
JSON types; numeric types and all other attribute values must match exactly.
Point coordinate tolerance is 1e-7 degrees, tighter than dataset precision.

The source SQL pass creates full expected ID sequences, values and geometries.
No oracle SQL runs during timed traffic. The same pure JavaScript validator
runs before traffic and on **every** response, including empty responses.
Missing/malformed payloads, ignored filters, duplicates, wrong order, incomplete
pages and wrong geometries fail. The OGC profile requires exact `numberMatched`; returned counts must agree with
the oracle. Count-metadata presence is also compared across products.

## Prepare immutable images

Use digest references for Honua, PostGIS and k6. Tags are rejected. The comparison
profile requires Honua's `honua.runtime.compilation=native-aot` label and OCI
revision. A JIT image can only produce diagnostic evidence.

Bake the matching GeoServer OGC extension before measurement:

```bash
docker build -f adapters/geoserver/Dockerfile.features \
  --build-arg BASE_IMAGE=docker.osgeo.org/geoserver@sha256:<digest> \
  -t geobench-geoserver:features .
docker image inspect geobench-geoserver:features --format '{{.Id}}'
```

Use that immutable local `sha256:...` ID as `GEOSERVER_IMAGE`, or push the image
to your registry and use its `repository@sha256:...` digest. Keep/export that
image for reproduction on another host. Build output, final image identity,
installed JAR hashes, core/plugin versions and Java version form the runtime
receipt. Downloading plugins during a campaign is disabled. Rebuilding from a
mutable plugin URL may produce a different image; it is a new profile identity,
not a valid resume of the old campaign.

For **separate community GSR evidence**, build with a compatible community
GeoServer base digest and `--build-arg COMMUNITY=gsr`, then run with
`--protocol gsr`. Both extension versions must match the core and pass the
independent full-corpus preflight. An unsupported GSR request is a coverage gap;
there is no fallback to OGC/WFS and no performance ratio for a missing row.
Community modules are [distributed separately from official releases](https://docs.geoserver.org/main/en/user/community/).

## Run

```bash
export HONUA_IMAGE='ghcr.io/honua-io/honua-server@sha256:<digest>'
export GEOSERVER_IMAGE='sha256:<prepared-image-id>'
export POSTGIS_IMAGE='postgis/postgis@sha256:<digest>'
export K6_IMAGE='grafana/k6@sha256:<digest>'
python3 scripts/run-feature-campaign.py --smoke --scenarios equality
python3 scripts/run-feature-campaign.py --mode diagnostic --arrival-rates
python3 scripts/run-feature-campaign.py --mode comparison --calibration calibration.json
```

`BENCHMARK_MODE=diagnostic scripts/run-benchmark.sh` also selects this runner.
The legacy broad protocol runner remains available without `BENCHMARK_MODE`.
Diagnostics may select one product with `--servers geoserver`.
Use `--scenarios equality,bbox-small,mixed:vus:10` to select rows. Closed-loop
mixed tests use 1/10/50/100 VUs; arrival diagnostics use 10/30/60/120/240 req/s.
Arrival tests allocate at most 100 VUs and disclose dropped iterations. They do
not claim all offered load was achieved. `--smoke` is always diagnostic and uses
one pair, two-second warmup and three-second measurement.

Diagnostic defaults are three repetitions, 30-second warmup and 30-second
measurement per scenario. Comparison defaults are five paired repetitions,
180-second warmup and 120-second measurement. `--seed` records the initial
server order, reversed on every subsequent pair. Each server/repetition gets
fresh private PostGIS storage, network and ephemeral loopback port. Both server
and DB have 4 CPUs / 4 GiB; source pools target six connections. The load generator
also has 4 CPUs / 4 GiB. Normal metadata caches remain enabled. Honua exact
response caching and adaptive admission are disabled. Honua uses exact
`numberMatched` to match GeoServer's count behavior. Imported storage is not
part of this source-backed profile.

Each scenario runs warmup and measurement in separate k6 processes, with a
35-second graceful drain after each. The HTTP timeout is 30 seconds. No process
starts until its predecessor exits. Only successful, semantically valid
completions before the measurement deadline count toward throughput and latency.
The custom latency includes receipt and validation of the response. Measurement
boundaries and latency use monotonic executor progress; progress is capped at
the deadline, so late requests contribute counts, never truncated latencies.
[k6 executor progress](https://github.com/grafana/k6/blob/v0.54.0/lib/executor/constant_vus.go)
uses monotonic elapsed time. Negative wall-clock timings in k6's auxiliary HTTP metrics are disclosed as clock
anomalies and block publication. Warmup,
late completions, invalid responses, cancellations and dropped iterations are
retained separately. See [k6 graceful stop](https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/graceful-stop/).

## Evidence and resumption

Each result directory contains the immutable campaign manifest, append-only
attempt ledger, snapshotted workloads/adapters, runtime and database receipts,
SQL source-query trace from the diagnostic pass, oracle, per-phase raw samples,
preflight receipts, five-second telemetry, and reports. SQL tracing is disabled
before warmup. No heap dumps, plans, downloads or package restores run during
measurement. Database pressure reports active queries, last-query source
sessions, background connections and parallel workers; sampling does not prove
an exact peak. Interpret these alongside server, DB, generator and host samples.

A campaign owns unique labels and records exact resource IDs. Cleanup checks
each label before deleting an ID. It never kills unrelated k6 processes or
runs project-wide/global Docker pruning. Interrupted attempts remain visible.
`--output results/<name> --resume` requires the same workload, images, dataset,
effective configuration, host identity and harness content. It continues unscheduled attempts;
it does not replace failed attempts. Artifact hashes detect altered/missing
evidence. A retry needs a new campaign directory. Diagnostics may opt into `--reuse-fixture`: passed fixtures are stopped between
server turns, then their exact owned resource identities, configuration and
source database fingerprints are verified before reuse. Comparison mode rejects
this option. All retained fixtures are removed when the campaign ends.

Publication fails closed on missing repetitions/scenarios, semantic failures,
runtime/configuration drift, unmatched database/response fingerprints, unfair
observed DB pressure or missing calibration. The report includes every repetition,
median and range of each repetition statistic, and paired throughput/p95 ratios.
It never computes an overall winner or an average of percentiles across scenarios.
A selected-scenario campaign only supports claims about those selected rows.

## Calibration

Collect the local observer half automatically from a prepared campaign:

```bash
python3 scripts/run-feature-campaign.py --mode diagnostic \
  --scenarios mixed:vus:10 --prepare-only --output results/observer-local
python3 scripts/run-observer-calibration.py --campaign results/observer-local
```

The image environment variables above are required for preparation. The collector
uses three paired repetitions per product, fresh owned fixtures, the complete
oracle and pressure preflights, and separate warmup/measurement/drain processes.
Observer-off traffic has no five-second observer; observer-on traffic uses the
normal observer. Their order alternates from the recorded seed. Raw samples,
runtime receipts, failed/interrupted attempts and cleanup receipts are retained
in a separate ledger under the prepared campaign. It does not populate or replace
comparison attempts. The JSON report shows each sample, medians and relative
throughput/p95 changes, with an explicit 5% check for each selected product/scenario.
`--scenarios` may restrict calibration to a subset of the prepared scenarios;
the report records that scope. Re-running creates a new ledger, never overwrites
an old attempt. Changed harness/host fingerprints require new preparation.

Diagnostic preparation uses 30s warmup/30s measurement and remains diagnostic.
Prepare with `--mode comparison` to collect the 180s/120s phases bound to a
strict campaign. Local observer evidence alone **cannot approve publication**:
an isolated-generator run is still required, and a failed 5% check requires
changing the setup and collecting new evidence. Do not copy one raw sample
between treatments or use a diagnostic receipt for a comparison binding.

The local machine is a shared development host. Publication requires an actual
separate load-generator host, plus observer-off/on measurements. Run `--prepare-only --output results/<campaign>` to create the immutable inputs
and calibration binding without starting stacks. Supply a JSON receipt bound to
the `binding` in `campaign.json`, then run the same arguments with `--resume`
and `--calibration <receipt>`:

```json
{
  "binding": "<configuration/workload/image/dataset/harness fingerprint>",
  "local_generator_identity": "<host identity>",
  "isolated_generator_identity": "<different host identity>",
  "observer_off": [{"throughput": 100, "p95": 20, "raw_points": "off-1.jsonl", "sha256": "<hash>", "measurement_seconds": 120}],
  "observer_on": [{"throughput": 100, "p95": 20, "raw_points": "on-1.jsonl", "sha256": "<hash>", "measurement_seconds": 120}],
  "isolated_generator": [{"throughput": 100, "p95": 20, "raw_points": "remote-1.jsonl", "sha256": "<hash>", "measurement_seconds": 120}]
}
```

Each array needs at least **three actual runs** (the single entries illustrate
the schema). Raw paths are relative to the receipt and are archived in the campaign.
Hashes and reported throughput/p95 must match the raw custom metrics; duplicate
artifacts cannot count as separate repetitions. All throughput and
p95 median differences, including observer-on/off, must be at most 5%. Missing
calibration or a larger difference marks the campaign unsuitable for publication;
local diagnostic results are still useful. The harness validates supplied
calibration receipts; it does not provision a remote generator host.

Run verification with `python3 -m unittest discover -s tests -p 'test_*.py'`,
`ruff check scripts`, and the JavaScript/ShellCheck checks in CI. No performance
claim from this dataset extends to lines, polygons, rendering, tiles or larger
datasets. Memory leaks require their own load/idle investigation.
