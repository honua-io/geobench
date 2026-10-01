# Frozen release and Native AOT readiness — October 1, 2026 (UTC)

**The earlier production-recipe AOT candidate is built, acquired and oracle-qualified.**
A replacement incorporating current trunk and the CI repair is building; the
older qualification below applies only to source `da06c51`.
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

## Strict candidate preparation checkpoint

The comparison manifest was prepared without starting either server stack or
sending traffic. It pins the acquired Native AOT candidate, stable GeoServer,
PostGIS17 and k6; records all12 scenarios, five paired repetitions,180s warmup,
120s measurement, and seed42; and archives the harness inputs. The attempts
ledger is empty. The preparation controller exited successfully and was removed
by exact owned identity.

Calibration binding: `1852e75e73de22ea77a34c4e33e948e52543b7ac4dc56f42e5c7fc8fd165ef2e`.
Harness: `869d19e75bdf456c508b561d966652921cfd9dc5`.
Coordinator hostname: `gb-aot-final-20261001`; future calibration and resume must
use the recorded coordinator recipe and host identity. This is a **candidate**
manifest. If final merged source, image, host, workload or harness differs, prepare
a new campaign and calibration binding rather than reusing this one.

The four optimization PRs remain open and mergeable. CI repair
[#5345](https://github.com/honua-io/honua-server/pull/5345) remains review-blocked
at `7d5700410eda9dafe7adf84fc8695ae3394e7a24`. Its owner's local commit
`a97054564f3cb288015e79fcaba25e8f017ba17a` contains the two requested fixture XML
summaries, but those fixes are not at the remote PR head. The production AOT
recipe still defaults to `RUNTIME_PACKAGE_REVISION=20260905`; the review requests
refreshing that default as well as the JIT recipe. The qualified candidate used
an explicit20261001 refresh and contains the fixed OpenSSL packages. These
observations do not establish that the repair or release has landed. Another
agent's worktree and the fleet CI brake were left intact.

The final campaign remains held. The user should quiet the machine only after
merged-source/image proof and publication calibration are ready; explicit user
confirmation is still required before final timing starts. Preparation receipt:
`results/jit-optimization-batch-20260929/strict-candidate-preparation-20261001/receipt.json`.

## CI repair follow-up checkpoint

The stalled repair lease was adopted with a recorded takeover comment under the
server repository's three-hour rule for unresolved repair work. The existing
owner's commit was preserved and fast-forwarded from an owned checkout; its
original worktree remains unchanged. The two XML summaries and production AOT
package-refresh default are now published in
[#5345](https://github.com/honua-io/honua-server/pull/5345) at
`4573567358a2ec2951be5bbb6abc468475d394f0`. All three findings were replied to
with source/validation evidence and resolved. The exact-head Review Gate passed;
[PR Gate run36828755759](https://github.com/honua-io/honua-server/actions/runs/36828755759)
completed successfully, including both affected GeoServices shards. The fresh
[canonical Native AOT serving-image check](https://github.com/honua-io/honua-server/actions/runs/36828755888/job/110260373857)
also passed.

The non-comment C# source is byte-identical to the previous remote head. The only
AOT recipe change sets its default revision to20261001, matching the explicit
argument used by the already-executed cloud qualification build. The pre-change
Dockerfile blob exactly matches that build's retained recipe receipt. Existing
hosted266-case and qualification536-case results remain attributed to their
original sources; neither is relabelled as a full test run of this repair.
`git diff --check` and the pre-PR selection dry run passed. Normal fleet admission,
any required repair matrix, trunk verification and calibration remain pending.
No merge brake was overridden and no final timed campaign started.

## Current trunk and merge admission checkpoint

The unchanged-trunk Core/Cloud rerun at
`4fa28024a99db339161328ecd65d31307eaa1797` passed all373 tests, including the
previously failing client-compatibility count request:
[job110264085750](https://github.com/honua-io/honua-server/actions/runs/36758108272/job/110264085750).
The original372/373 attempt remains retained. A single successful retry does
not establish the underlying failure's cause or make the whole matrix green.
The repair's COVERS declaration remains limited to its original two families.

Current trunk, the exact four frozen PR heads and CI repair5345 merge cleanly
into candidate `f0ba192135bfbeae7881fbde3a6640aa56d9d533`, pushed on
`qualification/current-trunk-release-20261001`. This candidate includes the
current trunk revert absent from the older qualified candidate. Fresh locked
local source qualification is underway; the old536-case result is not evidence
for this replacement source. A separate production full-profile Native AOT
build is running in
[run36830715665](https://github.com/honua-io/honua-server/actions/runs/36830715665).
Its application source is fixed to `f0ba192`; its workflow-only branch is
`qualification/aot-export-current-trunk-20261001`. No shipping alias was moved.
The replacement still needs acquired-image and HTTP oracle validation.

All five PRs remain open. The four optimization PRs and CI repair5345 have
successful exact-head PR Gate and Review Gate, zero unresolved threads, and
are non-draft/mergeable against trunk. A
[normal-admission handoff](https://github.com/honua-io/honua-server/pull/5345#issuecomment-5927249301)
records the repair evidence. The fleet's last recorded lander pass remains
2026-09-30T18:36:07Z, and its trunk verdict still references an older failed run.
The current session cannot connect to the host's user systemd bus, so it cannot
verify or restore that service here. Stale files alone do not prove the daemon
is stopped. The server's normal serialized lander remains the merge authority;
no second caller, manual/admin merge or brake-state edit was used.

Receipt paths under `results/jit-optimization-batch-20260929/`:
`trunk-core-cloud-rerun-artifact-20261001/verification.json`,
`current-trunk-release-integration-preparation-20261001.json`,
`current-trunk-aot-cloud-launch-20261001.json`,
`release-current-trunk-preparation-20261001.json`, and
`release-current-trunk-pg17-v1-20261001/receipt.json`.
The replacement image/source needs a new campaign and calibration binding.
No final timed traffic has started; publication calibration and the user's
quiet-machine confirmation remain required.
