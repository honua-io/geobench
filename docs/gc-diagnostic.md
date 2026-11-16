# Container GC diagnostic

Run `scripts/gc-cohort-diagnostic.py` from the repository root on an existing
Docker host. It runs the source-backed 100K-point concurrent workload at Small
(1 CPU, 2 GiB) and Medium (2 CPU, 4 GiB) container limits with bounded database
admission. This is a container diagnostic; it does not qualify cloud hardware.

Provide an existing local immutable image ID or platform digest and its full
`org.opencontainers.image.revision` label. The script verifies the label and
records shipped runtime configuration and GC environment. Run profiles sequentially
in a dedicated checkout, with the same image and workload settings:

```bash
python3 scripts/gc-cohort-diagnostic.py --image sha256:<digest> --source <revision> --profile defaults
python3 scripts/gc-cohort-diagnostic.py --image sha256:<digest> --source <revision> --profile fixed
python3 scripts/gc-cohort-diagnostic.py --image sha256:<digest> --source <revision> --profile heap60
```

`defaults` preserves shipped GC settings, `fixed` sets
`DOTNET_GCDynamicAdaptationMode=0`, and `heap60` sets
`DOTNET_GCHeapHardLimitPercent=3C` (hexadecimal 60%). These are configuration
profiles; they do not prove that DATAS or Server GC is active. Single-CPU
containers may use a different GC mode. Establish actual mode separately before
selecting defaults from these measurements.

Defaults are three repetitions at 1, 10, 50 and 100 VUs, with 30 seconds of warmup
and 60 seconds of measurement per level. Results go to
`artifacts/gc-diagnostic/<timestamp>-<profile>/`. Keep raw request outputs and
response audits alongside the summary. The sampler records process RSS, cgroup
peak memory, container OOM/restart state, host load and authenticated runtime GC
metrics where available. GC pause deltas cover sampled startup, warmup and
measurement; they are not a distribution of individual pauses. Missing counters
remain unknown. Cgroup peak includes memory beyond managed heap and process RSS.

`COLLECTED` means request and memory evidence was collected. It does not mean a
profile passed its performance bar. Inspect each level's `meets_bar`, request
errors, OOM/restart state and counter availability. Every repetition must have
zero request errors and p95 below 500 ms to meet the level's bar. A failed or
partial run must remain in the comparison.

The script refuses startup above a 1-minute host load of 16 by default and
records load throughout. Raising `--max-load` permits harness debugging only;
busy-host timings cannot justify GC defaults or architecture comparisons. A
short `--runs 1 --levels 1 --duration 2 --warmup 1` run checks instrumentation.
Use compatible image/source revisions and controlled quiet-host runs for actual
comparisons. The script creates and removes its own Docker stack and throwaway
key-ring certificate; do not run multiple copies in one checkout.
