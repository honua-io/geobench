# Research Redis-Coordinated Query Admission for Multi-Node Database Connection Tuning

## Context

Recent GeoBench tuning work shows that database query admission and pool sizing have a large impact
on tail latency. On the current small-node benchmark profile, larger per-node pools can overfeed
PostGIS and worsen p95/p99 latency. Adaptive admission helps in some profiles, but the multi-node
case needs explicit coordination because per-node pools multiply against the same shared database.

Example risk:

- 8 query slots per node x 6 app nodes = 48 active database queries
- each Honua node may adapt independently and increase/decrease at the same time
- synchronized local controllers can still overload PostGIS even if each node is behaving rationally
  in isolation

## Research Question

Can Redis provide a simple, robust cluster-level coordination layer for Honua query admission without
putting Redis on the latency-critical path for every feature request?

## Proposed Direction

Investigate a shared admission-budget design:

- Redis stores a global database query budget for a service/database profile.
- Each Honua node heartbeats into Redis with node id, capacity class, and timestamp.
- Each node leases a small batch of query tokens with short TTLs.
- The local in-process admission gate enforces leased tokens without a Redis round trip per query.
- Expired leases return capacity automatically if a node crashes.
- If Redis is unavailable, nodes fall back to a conservative local cap rather than unlimited
  concurrency.
- Adaptive admission remains local, but its min/max bounds are derived from the cluster budget and
  active node count.

## Benchmark Scope

Use GeoBench to compare:

- single-node fixed caps vs adaptive caps
- multi-node fixed per-node caps vs Redis-coordinated global budget
- Redis available vs Redis unavailable/failover behavior
- uniform workload vs mixed workload with bbox/equality/range/LIKE breakdown
- different node counts and node-size envelopes

## Acceptance Criteria

- Define a minimal Redis coordination protocol: keys, lease TTLs, heartbeat semantics, and failure
  behavior.
- Add a benchmark profile or experiment plan for multi-node Honua against shared PostGIS.
- Report whether Redis coordination improves p95/p99 and avoids PostGIS oversubscription compared
  with independent per-node admission.
- Keep the design simple enough that a fixed node-size-aware profile remains the fallback if Redis
  coordination is not clearly better.

## Notes

Current evidence suggests the first-order win is bounded admission: smaller caps can outperform
larger pools by avoiding queue collapse. Redis should only be introduced if multi-node tests show
that local fixed/adaptive caps are insufficient for shared-database coordination.

## Initial Local Evidence

Single-node Honua-only concurrent repeats on `honua-geobench:trunk-1b301c3a-adaptive2` show that
the current adaptive controller does not yet beat a simple fixed cap at the same upper bound.

| Profile | Runs | 100 VU req/s | 100 VU p95 | 100 VU p99 | Notes |
| --- | ---: | ---: | ---: | ---: | --- |
| fixed cap 4 | 3 | 143.4 | 293.9 ms | 613.8 ms | Median report from `results/20260426-172603`; one run had a high p99 outlier |
| adaptive 2-4 | 3 | 73.8 | 1388.3 ms | 2152.2 ms | Median report from `results/20260426-175616`; two 100 VU runs had high p99 tails |

Admission sampling for `adaptive 2-4` showed:

- limit range: 3-4
- adjustment count: 40
- max queued waiters: 96
- max duration EWMA: 391.9 ms

This points to a controller issue before any Redis work: queue pressure needs to be a first-class
signal. The sampled controller sometimes returned to the max limit while queued waiters were still
high, because duration EWMA alone had already fallen. A Redis coordinator would not fix that local
control behavior by itself; it should come after the local controller handles queue pressure and
fixed node-size-aware caps are validated.

## Follow-up Local Controller Experiment

A queue-aware Honua patch was tested in local Docker image
`honua-geobench:trunk-b9f5879a-queue1`. The patch adds admission queue-wait EWMA telemetry and
prevents moderate adaptive downshifts when queue pressure dominates database lease duration.

| Profile | Runs | Result path | 100 VU req/s | 100 VU p95 | 100 VU p99 | Notes |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| adaptive 2-4, queue-aware | 1 | `results/20260426-193520` | 67.0 | 1678.1 ms | 2495.8 ms | Held at limit 4; no headroom to drain the queue |
| adaptive 2-6, queue-aware | 1 | `results/20260426-194638` | 85.2 | 1064.0 ms | 1861.2 ms | Increased from 4 to 6 and held max under load |

Admission sampling for `adaptive 2-6, queue-aware` showed:

- limit range: 4-6
- adjustment count: 1
- max queued waiters: 83
- max duration EWMA: 326.0 ms
- max queue-wait EWMA: 1071.9 ms

This validates the new queue telemetry and confirms that a wider adaptive envelope changes the
controller behavior. It still does not beat the earlier fixed cap 4 single-node result, so Redis
coordination remains premature. The next experiment should be a clean same-image fixed cap 4 vs
adaptive 2-6 comparison after other local Testcontainers workloads are stopped; one attempted
same-image fixed run was aborted because unrelated active agent processes started GeoServer, Redis,
and PostGIS Testcontainers during the benchmark.
