# Ticket: Honua Service/Layer Performance Profiles

Superseded as a standalone planning artifact by
[docs/honua-performance-refactor-ticket.md](./honua-performance-refactor-ticket.md).
Keep this note as design background for the profile portion of the refactor.

## Summary

Add explicit Honua performance profiles at the service and layer level so different use cases can
be optimized without forcing one global tradeoff between low-load latency and high-load throughput.

## Background

GeoBench shows two distinct behaviors in Honua:

- selective reads are very strong
- mixed concurrent load falls behind GeoServer

The current benchmark adapter also confirms that Honua has explicit `serviceName` and layer
publication concepts, which makes per-service and per-layer optimization a natural fit.

## Problem

Today Honua behaves like one global serving profile. That makes it hard to optimize for:

- interactive lookup latency
- map browsing and bbox-heavy workloads
- bulk export throughput
- future adaptive routing under overload

Some throughput-oriented changes may hurt low-load latency if they are applied globally.

## Goal

Support distinct Honua service/layer profiles such as:

- `latency`
- `balanced`
- `throughput`

These profiles should be selectable per service and overridable per layer.

## Scope

In scope:

- define which settings are global, per service, and per layer
- allow different layers to use different backing shapes such as tables, views, or materialized views
- allow different index strategies per use case
- expose enough metadata so benchmarks can report the active profile clearly

Out of scope for the first pass:

- automatic runtime adaptation
- benchmark result collapsing across different profiles

## Proposed Design

Global:

- connection pool safety limits
- process-wide resource limits
- cache infrastructure toggles

Per service:

- default page size / max record count
- concurrency and batching policy
- payload defaults
- cache policy

Per layer:

- backing source table / view
- published field set
- hot-filter indexes
- sort strategy
- bbox/query optimization target

Future:

- optional adaptive routing between stable profiles based on load and request shape

## Immediate Follow-up

Before profile work lands, keep the current structural win:

- add typed expression indexes for hot fields in Honua's `public.features`

That change is expected to help both low-load and high-load behavior because it removes avoidable
scan work rather than trading latency for throughput.

## Acceptance Criteria

- a Honua service can declare a named performance profile
- a Honua layer can override the service profile
- benchmark output can identify the active Honua profile
- at least two profiles are documented and reproducible
- no benchmark report mixes results from different profiles into one headline ranking

## Benchmarking Notes

Profiles should be reported separately:

- `default`
- `latency`
- `balanced`
- `throughput`

Payload size should remain an independent axis from profile selection.
