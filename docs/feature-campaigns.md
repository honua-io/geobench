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

Fresh GeoServer fixtures expose the primary-key attribute and explicitly enable
OGC sorting in their WFS service metadata. The campaign verifies both persisted
settings and advertised sorting conformance, records the effective service
fingerprint, and checks it again after traffic. Reused fixtures must already
match; they are not silently reconfigured. A separate descending-ID oracle probe
runs during preflight for both products, so natural ascending database order
cannot conceal an ignored `sortby` parameter. This probe does not enter the
measured workload. Earlier campaigns without this check may contain repeated
GeoServer ignored-sort warnings and need a corrected rebaseline.

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

Runtime receipts also retain the exact Honua planner keys defined by the shared
profile configuration, without exposing unrelated database environment values.
The runner checks the inspected keys against the selected profile before traffic
and at the final drift check. Missing, changed, duplicated or unrequested planner
options fail the attempt. Executed-SQL proof remains a separate requirement.

For **separate community GSR evidence**, build with a compatible community
GeoServer base digest and `--build-arg COMMUNITY=gsr`, then run with
`--protocol gsr`. Both extension versions must match the core and pass the
independent full-corpus preflight. An unsupported GSR request is a coverage gap;
there is no fallback to OGC/WFS and no performance ratio for a missing row.
Community modules are [distributed separately from official releases](https://docs.geoserver.org/main/en/user/community/).

## Run

### Check local repeatability before optimization timing

`scripts/run-control-repeatability.py` prepares two identical Honua diagnostic
campaigns using the same immutable image, dataset, configuration and harness.
Preparation starts no stacks and sends no requests. The default selects
`bbox-small,range,page-medium`, three A/A pairs in seeded alternating order,
30-second warmup and 30-second measurement. Each of the six attempts provisions
fresh owned storage. The plan records CPU/memory budgets, image identity, active
traffic time and the maximum drain allowance; provisioning adds time separately.

```bash
python3 scripts/run-control-repeatability.py --output results/control-aa-v1 \
  --honua-image 'sha256:<prepared-image-id>' \
  --postgis-image 'postgis/postgis@sha256:<digest>' \
  --k6-image 'grafana/k6@sha256:<digest>'
```

Review `repeatability-plan.json`, obtain explicit approval for that specific
quiet-machine window, then execute the prepared plan:

```bash
python3 scripts/run-control-repeatability.py --output results/control-aa-v1 \
  --execute --approval-note 'Operator approved this prepared A/A window'
```

An idle-host reading never grants approval. Execution without an approval note
fails before loading the runner. Images, effective configuration, host, dataset,
workload and harness are checked again before traffic. The runner shares the
feature-campaign measurement lock and refuses concurrent campaigns. There is no
automatic retry or resume: interrupted/failed attempts remain visible, remaining
attempts are explicitly not run, and another execution needs a new plan and
approval. Each stack uses the existing exact-ownership cleanup.

`repeatability-report.json` passes only when all six attempts and scenarios have
valid retained evidence and owned cleanup, matching database/response contracts,
and no warmup or measurement clock anomalies. For every selected scenario,
`max/min - 1` must be at most 5% across **all six** throughput and p95 values;
equal arm medians cannot conceal an unstable repetition. The report retains
each repetition, paired ratios, and the median/range of per-repetition
p50/p95/p99 values. It does not average percentiles into a combined distribution.
Passing this local diagnostic does not qualify observer overhead, an isolated
generator, a server optimization or publication.

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
defaults to 4 CPUs / 4 GiB. Normal metadata caches remain enabled. Honua exact
response caching and adaptive admission are disabled. Honua uses exact
`numberMatched` to match GeoServer's count behavior. Imported storage is not
part of this source-backed profile.

Honua's test-schema headers are disabled (`HONUA_TEST_SCHEMA_HEADERS=false`).
Each attempt already owns an isolated database, and workloads do not send
per-request schema overrides. This retains the shipping connection reset policy;
turning test-schema isolation on adds resets of pooled catalog connections.
Runtime receipts record the flag and reject missing, conflicting or enabled
values before and after traffic. Older campaigns retain their original
configuration and results; this change requires a new fingerprint-bound campaign
and cannot be resumed into an earlier test-schema-enabled run.

A persistent coordinator container on Docker Desktop can use
`--control-host host.docker.internal` to reach the private published ports for
provisioning and configuration checks. The default is `localhost`. The manifest
records this address and binds it to resume/calibration; measured k6 requests
continue to use each product's private Compose-network address. This option does
not enable host networking or change the server/database/generator budgets.
The container-coordinator option explicitly adds `host.docker.internal` to
Honua's allowed-host list for provisioning; host validation remains enabled, and
the effective list is captured in runtime receipts.

Use `--generator-cpus 8` in a new diagnostic campaign to investigate generator
headroom. The option accepts positive integers and applies the same k6 CPU budget
to both products; server/database CPU, memory and source-connection limits remain
unchanged, and k6 memory remains 4 GiB. The manifest and reports record the separate
generator budget, and nondefault profile names include `generator-8cpu`. Effective
limits are checked before and after traffic. Changed budgets invalidate the resume
and calibration binding. Observer CPU warnings use inspected per-container quotas,
so 400% CPU is saturation for a four-core server but not an eight-core generator.

An enlarged local generator is a separate diagnostic configuration. It does not
prove unlimited generator capacity or replace isolated-generator and observer
calibration for publication. Compare the same server image/workload under each
generator budget and retain every repetition. Do not change a running campaign's
budget or combine rows across generator configurations.

The default `--honua-profile baseline` explicitly disables Honua's serial-read
and serial-count options, providing a database-planner control even when server
defaults change. Each explicitly tuned profile pins the other serial option off
unless that option is named in the profile. These controls preserve the earlier
untuned/tuned behavior; they are not evidence of a newer server's shipping defaults.

Use `--honua-profile automatic-bounded` for a server implementing automatic
bounded planning ([server issue #5338](https://github.com/honua-io/honua-server/issues/5338)). It leaves all planner flags absent and
requires the SQL diagnostic to prove transaction-local serial feature reads and
associated exact counts on the existing point/bbox requests. An older image that
keeps database planning, an injected explicit option, missing read/count tuning,
or unexpected count-JIT suppression fails validation. This is a separate,
fingerprinted profile using the same workload and resource budgets. Keep its
results distinct from explicitly tuned profiles. Its name does not establish a
performance gain or a publication claim.

Use `--honua-profile count-jit-off` in a separate campaign to enable
`Database__DisableJitForSourceSpatialCounts=true` on a supporting Honua image
(server PR #5307). This suppresses PostgreSQL JIT only for eligible count queries;
it is independent of Honua Native AOT and does not change database-wide JIT or
parallel-worker settings. The profile name and effective environment are included
in the campaign fingerprint, preventing resume across different tuning settings.
GeoServer's configuration is identical across these campaigns. Keep the baseline and
tuned rows separate; if database JIT is already off, this option adds no JIT-removal
benefit. A supporting image and executed SQL evidence are needed to establish
that the option was actually applied.

Use `--honua-profile serial-reads` to test the existing
`Database__PreferSerialBoundedSpatialReads=true` option separately. It requests
zero parallel workers only for eligible source-backed point bbox feature reads:
first pages of 1–100 features with default ID ordering and no ambient transaction.
It does not tune counts, later pages, or custom sorting. The
`--honua-profile count-jit-off-serial-reads` profile enables both options, using
separate transaction-local settings for count and feature queries. Neither option
changes database-wide settings or Honua's Native AOT compilation mode.

Use `--honua-profile serial-counts` to enable only
`Database__PreferSerialSourceSpatialCounts=true`. The separate
`--honua-profile count-jit-off-serial-counts` profile combines that count-worker
policy with PostgreSQL JIT suppression; neither enables serial feature reads.
These profiles require a server image implementing the count option. An image
that silently ignores it fails executed-SQL preflight.

Use `--honua-profile serial-reads-counts` to combine the independent serial page
and count options, or `--honua-profile count-jit-off-serial-reads-counts` to add
count-specific PostgreSQL JIT suppression. These profiles require separate
executed evidence for feature and count batches. Worker settings before a page
query cannot substitute for count evidence, and the three-option profile must
show both count settings before the same count. The individual profiles remain
available to isolate each policy's effect; combined profiles imply no speed gain.

Serial count proof requires a transaction-local worker setting immediately
followed by the spatial count on the same backend. The combined profile requires
both settings in the same setting statement before that count. Separate JIT-only
and serial-only counts cannot establish the combined profile. Fixed count SQL
identities distinguish serial-only and combined preparation policies. Raw SQL is
revalidated when generating the report, and each profile has its own campaign
fingerprint. These options do not imply a performance improvement; measure the
production Native AOT build before drawing that conclusion.

All nine profiles have distinct configuration fingerprints. Before timed traffic,
the SQL diagnostic must show the profile's settings actually executing on the
same database backend immediately before their eligible source queries. Report
generation independently checks this raw trace. An ignored or unsupported option,
unexpected tuning in the baseline, or missing half of the combined profile fails
validation. These profiles test planner choices; their names imply no speed benefit.

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

`source-query.json` summarizes executed geometry-encoding SELECTs and source
counts from the SQL trace. For these pinned profiles, every observed feature
projection must read only the qualified `public.bench_points` relation, including
inside pagination subqueries. Counts alone, parse/bind messages, SQL literals,
unqualified names, other schemas and additional feature-data joins cannot prove
source-backed feature reads. The recognizer targets the SQL shapes of the pinned
profiles; an unrecognized shape needs a separate diagnostic review. Reporting
revalidates the raw trace against its receipt. Older artifacts without this
receipt do not satisfy the new evidence gate.

The manifest fingerprints both the controller and Docker engine (engine ID,
kernel, CPU/memory capacity, version and cgroup settings). Engine identity and
capacity are checked again before and after traffic. Five-second `host` samples
read the engine kernel's `/proc` view through the owned database container;
`controller` samples describe the machine running Python. These can differ with
remote Docker or Docker Desktop. Container CPU/memory limits remain separate
from kernel totals. No privileged container or host mount is needed. On Docker
Desktop these samples describe its Linux kernel, not the physical Windows/macOS
host. This additional observation work must be included in calibration; older
campaigns' controller-only `host` samples cannot prove engine-host pressure.

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
After an interrupted collector, the next run marks the prior attempt interrupted
and cleans only its labelled resource IDs before provisioning. To clean without
new traffic, including after a harness change, use
`python3 scripts/run-observer-calibration.py --campaign results/observer-local --cleanup-only`.

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
