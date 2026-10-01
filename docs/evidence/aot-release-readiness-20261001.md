# Frozen release and Native AOT readiness — October 1, 2026 (UTC)

**The production-recipe AOT candidate is built, acquired and oracle-qualified.**
The final timed comparison has not started and no AOT speed claim is made.
Normal merges and publication calibration remain pending; the user has not yet
quieted the machine for final timing. The latest performance evidence remains
the [three-pair JIT diagnostic](jit-production-three-pair-20261001.md), which
excludes the final native/metadata and pagination patches.

## Frozen release and verification

Source `da06c51de0bc8579601fc86bc5ddcafabaed7a70`, branch
`qualification/release-20261001-r2`, combines
[bounded planning/shared GeoJSON #5343](https://github.com/honua-io/honua-server/pull/5343),
[native decoding #5349](https://github.com/honua-io/honua-server/pull/5349),
[authorized metadata reuse #5351](https://github.com/honua-io/honua-server/pull/5351)
and [response-owned pages #5354](https://github.com/honua-io/honua-server/pull/5354).
Policy batching #5352, exact-count/page batching and further projection/output
rewriting are deferred. No cache or admission profile was changed to chase a win.

Fresh source-stamped Release JIT compilation, analyzers/warnings-as-errors and
changed-file formatting passed. All536 selected tests passed on PostgreSQL16:
core27, security58, provider265, OGC API66, GeoServices108 and WFS12, with
zero failures/skips and all11 owned fixtures cleaned. The identical hash-verified
assemblies passed all265 provider cases on PostgreSQL17 and18. Compilation
emitted48 uncoded SourceLink warnings with SCM queries disabled; no coded
warnings or errors.

The production AOT HTTP oracle smoke then passed all24 scenario rows:12 each
for Honua and stable GeoServer3.0.1 with its matching OGC extension. This covers
the existing100K-point corpus, exact numeric counts, complete IDs/attributes/
geometries, ordering, legitimate empty and boundary queries, and production test
headers disabled. Both stacks cleaned. Honua executed `/app/Honua.Server`, with
no CoreCLR mapped,4CPU and4GiB. The smoke used2s warmup/3s measurement and
is **valid diagnostic correctness evidence, not publishable performance**.
Report SHA256: `89b1f02fd13d457494fb1c41be07535edbc98767716cd4b526e28149b86119a2`.

#5349, #5351 and #5354 were marked ready after their current-head PR gates and
combined AOT oracle passed. Null-safety findings were checked against the current
assertion/conditional-access code, and the explicit stateful geometry loop was
retained with rationale. Review threads were resolved with evidence. #5343 was
already ready with green required gates. No manual/admin merge or brake bypass
was performed. All four exact-head PR Gate and Review Gate checks subsequently passed; each PR is non-draft and mergeable. All four remained open at that check. The normal lander/merge state remains a live prerequisite.

## Acquired production AOT image

`ghcr.io/honua-io/honua-server@sha256:d53ff0a7026a620aead109f136eda08624a016b1a54f79556be5d9cf9bf53e81`

[Production boundary run36819900206](https://github.com/honua-io/honua-server/actions/runs/36819900206)
compiled identical serving inputs at source `4c54532a512ec55246c3d4f1578ff89c5036bab1`.
[Qualification export run36820832934](https://github.com/honua-io/honua-server/actions/runs/36820832934)
succeeded, checking out exactly the release SHA and using the unchanged production
`docker/Dockerfile.aot`, full profile and pinned SDK/runtime bases. The export
reused the verified native build cache and refreshed runtime packages through
`RUNTIME_PACKAGE_REVISION=20261001`. OpenSSL/libssl3t64 are
`3.0.13-0ubuntu3.16`. The exact recipe blob and installed package receipt are retained.
This isolated qualification image did not move shipping/nightly/trunk aliases.

The registry manifest's raw SHA matches the pinned digest; its config digest is
`sha256:7cc26ece74c2608df2a82bf47671d5d5dfe8fad98cc554419267b3bebb6c7048`,
matching the hosted Docker image ID. Docker Desktop's containerd backend reports
the manifest digest as its image ID. Runtime configuration, layer diffIDs,
architecture, native/source labels and recipe blob match. Only nine missing versus
empty/false legacy daemon fields were normalized; no runtime difference was waived.

## Retained failures and cleanup

Earlier519-case passes apply to their recorded older sources. Their PostgreSQL16
volatile-policy regression retained four failures. The fixture had authenticated as
a superuser with a startup role option; its pinned16.4 image predates the documented
[role-reset correction](https://www.postgresql.org/support/security/CVE-2024-10978/).
The tests now authenticate as the constrained LOGIN role and check pooled identity.
The complete current suite passes without weakening runtime recovery or RLS rules.

The first current-source PostgreSQL18 attempt retained201 startup connection-refused
failures. Readiness had accepted the temporary Unix-socket initialization server.
A new coordinator waits explicitly for TCP, after which all265 cases passed using
the same assemblies. The AOT acquisition retained the initial image-ID assertion
failure and a later strict Config equality failure before the stronger manifest/
config/layer verification passed. The initial smoke dependency failure was retained;
a fresh both-product smoke passed. Failed attempts were not silently replaced.
All terminal controllers and owned fixtures were cleaned by exact identity, with
logs/receipts preserved. The earlier measured JIT coordinator remains for its
existing qualification prerequisites.

## Before final timing and publication

Verify normal merges and final merged serving-content identity. The normal lander
still retains a trunk CI brake; #5343 remained open at the last check. Acquire or
confirm the appropriate final image after that proof, then notify the user that
the setup is ready for their quiet-machine window. Do not start final timing before
that confirmation. The qualified image above is an unmerged combined candidate,
not a claim that the release has shipped.

Twelve scenarios with five pairs and180s warmup/120s measurement take roughly10hours,
plus preparation, drain and calibration. Quiet WSL does not establish the separate
isolated load-generator calibration required by publication gates. That evidence
remains missing; strict publication must fail closed. The existing prefix query
also does not establish escaped-underscore literal-prefix coverage. Results remain
specific to the100K-point feature corpus and selected profiles.

Receipts under `results/jit-optimization-batch-20260929/` include full current
qualification and provider retries, `aot-acquisition-v3-20261001/`, cloud launch/
export receipts, `durable-aot-smoke-v2-20261001/`, and
`harness-control-checkout/results/aot-release-smoke-v2-20261001/`.
