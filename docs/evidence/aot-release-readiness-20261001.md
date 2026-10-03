# Frozen release, Native AOT readiness and local diagnostics — October 2, 2026 (UTC)

**The final merged-source production Native AOT image is built, verified and oracle-qualified.**
Source `36581bd29870101d103ea16e3ba215a2a98811fe` includes all six performance
PRs and both CI repairs. Fresh managed verification passed558/558 tests with
zero failures/skips. The hosted production full-profile Native AOT export
succeeded. Its registry manifest, source/build inputs, runtime configuration
and layers were verified, then all24 both-product oracle smoke rows passed.
Honua executed `/app/Honua.Server` with no CoreCLR mapped, under4CPU/4GiB.
All owned smoke/preparation resources and controllers are cleaned up.

A new immutable five-pair comparison manifest is prepared for this exact image
and source, with180s warmup/120s measurement and seed42. Its attempt ledger is
empty. The user confirmed the machine is quiet on October2. All six local
observer-calibration pairs passed correctness, pressure and integrity checks,
but GeoServer's median observer-off/on variation exceeded the5% publication
limit. Matching isolated-generator calibration also remains missing. Strict
comparison/publication therefore stays closed. A separate three-pair local
AOT diagnostic campaign completed across all twelve point scenarios: all72
measured rows passed and were independently verified. Its paired median
throughput ratios were1.55 for mixed traffic and3.52 for large bbox reads;
small bbox and boundary reads lagged at0.78 and0.88. These are local diagnostic
figures with wide repetition ranges, not publishable comparison claims.
The [small-bbox follow-up](small-bbox-investigation-20261003.md) checks the
count shortcut, SQL plans and planner profiles without changing this baseline.
Two subsequent instrumented Native AOT captures validated all160 responses;
catalog command spans account for about35% of serial server request time.
Fresh policy batching is now a measured overhead target, with no batching
speedup demonstrated. The first capture's postcapture bookkeeping failure is
retained; the corrected capture passed its postrun checks. These attribution
bursts create no benchmark rows or new competitor ratios.
Final-source trailing CI passed, with all106 jobs accounted for and no failed
jobs. No strict measured comparison exists. The quiet window is complete and
the machine no longer needs to remain quiet for this diagnostic campaign.
Chronological checkpoints below retain their original sources and timestamps.

## Earlier frozen candidate and verification

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

## Replacement qualification outcome

[Cloud run36830715665](https://github.com/honua-io/honua-server/actions/runs/36830715665)
completed successfully at2026-10-01T08:24:42Z: production full-profile Native AOT
build, native serving boundary, executable startup smoke and candidate export all
passed for application source `f0ba192135bfbeae7881fbde3a6640aa56d9d533`.
This does not establish complete release correctness or benchmark readiness.

Fresh source qualification failed: core27/27, security58/58 and PostgreSQL265/265
passed; OGC API58/66 passed with eight failures. All eight exercise fractional
GeoJSON timestamps: expected `1970-01-01T00:00:00.1234567Z`, actual
`1970-01-01T00:00:00Z`. The current trunk revert changed the shared feature
builder back to whole-second formatting. The prepared-schema regression tests
retain the full timestamp requirement; they were not weakened. Later selections
were not executed after this failure. The receipt and failed TRX are retained,
and the driver cleaned all nine owned resources. This candidate cannot be called
qualified or used for final results until the precision regression is repaired
and the replacement source is verified.

At the subsequent live check, all five release/repair PRs remained open and
mergeable with both required gates successful. The fleet lander timestamp still
had not advanced. No new AOT performance result exists, and the user should not
quiet the machine for final timing yet.

## Timestamp integration repair and shepherding checkpoint

PR5343 now integrates current trunk at head
`d283abbcb0741b224327aac80e9fa1d14840803a`. Its shared GeoJSON builder explicitly
retains `TemporalExtentHelpers.FormatOgcTemporalValue`, so whole-second output
keeps its shape while fractional timestamps retain seven digits. The eight
existing failing regression assertions were not changed. No other reverted
contract was restored by this repair. A temporary hold prevents admission before
the combined-source regression passes.

[Fresh PR Gate36897330107](https://github.com/honua-io/honua-server/actions/runs/36897330107)
completed successfully, including all six affected server shards and the full
required build/test execution proofs. A requested Codex review reported account
quota exhaustion. The repository's independent
[Claude review36901046350](https://github.com/honua-io/honua-server/actions/runs/36901046350)
then passed and posted a clean attestation at the exact repaired head. The trusted
Review Gate remains red while the deliberate hold remains; it was not overridden.

The repaired frozen combined source is
`f1f040344cfd25986dc1bf6044b23a795053eaee`, branch
`qualification/release-timestamp-repair-20261001`. It differs from failed
candidate `f0ba192` in only the shared builder (two insertions, one deletion).
Its fresh Release compilation finished in33m30s with zero errors and48 uncoded
SourceLink warnings. Changed-file formatting and the same six selected test
projects are being verified under the shared lock. All earlier passes/failures
remain attributed to their own sources. A corrected production full-profile AOT
export is live in
[run36898796298](https://github.com/honua-io/honua-server/actions/runs/36898796298),
with no shipping aliases moved. Immutable image acquisition and a both-product
HTTP oracle driver are prepared but not executed for this source yet.

The prior failed qualification's nine resources were cleaned, and its exact
terminal controller was removed after retaining its logs and failure receipt.
The new qualification controller is live and must not be reclaimed prematurely.
All five release/repair PRs remain open. The four unchanged PRs still have both
required gates green and zero unresolved threads. The host lander timestamp has
not advanced; this session still cannot connect to its user systemd bus. Normal
serialized admission remains pending, with no manual/admin merge or state edit.
The user was asked whether the WSL service restart succeeded; no answer was yet
received at this checkpoint. No final timing or new speed claim was made.

## Corrected AOT qualification and final admission handoff

The complete fresh-source PostgreSQL17 qualification passed536/536, with zero
failures/skips: core27, security58, provider265, OGC API66, GeoServices108 and
WFS12. The OGC TRX independently contains all eight passing precision variants.
All11 owned fixtures were cleaned. Older PostgreSQL16/18 compatibility receipts
still apply only to their recorded previous source; they were not relabelled.
The temporary PR5343 hold was removed and trusted Review Gate refreshed to
success. All five current PR heads have green required gates, no holds and zero
unresolved threads, but none has merged.

Corrected production AOT image:
`ghcr.io/honua-io/honua-server@sha256:842bf147f3f7884159983719e1db60bf013413781a77e0947899a78710df0018`.
Source: `f1f040344cfd25986dc1bf6044b23a795053eaee`.
Cloud export: [36898796298](https://github.com/honua-io/honua-server/actions/runs/36898796298).
The raw registry manifest hashes to842bf147; its configuration digest matches
the hosted Docker image ID. Filesystem diffIDs, architecture, actual runtime
configuration and source/native labels match the local image. Inspection-only
missing versus empty/false legacy fields and missing versus null `Cmd`,
`OnBuild`, `Volumes` were recorded explicitly; non-null runtime differences
would still fail the gate.

Image acquisition retained a WSL Windows credential-helper failure, then
configuration-identity assertion failures. An isolated empty Docker configuration
resolved the credential helper. Read-only diagnosis proved that Buildx was
available: the later failures were omitted versus null inspection fields, not
a missing plugin. The final raw-manifest/configuration/layer proof passed.
These attempts remain under `timestamp-repair-aot-acquisition-v{1,2,3,4}-20261001/`.

The corrected Native AOT HTTP smoke passed24/24 rows,12 per product, with valid
semantic/fairness checks, production test-schema headers disabled and native
executable/CoreCLR absence verified. Its2s warmup/3s measurement is correctness
smoke, not publishable performance evidence. Both owned attempts cleaned their
resources. Report SHA256:
`491a5caa3df628a30af1168b27840f02884c705c58324d3310274af5ccc04c87`.
The exact terminal qualification and oracle controllers were removed only after
dependencies completed and logs/receipts were retained. The older measured-JIT
coordinator remains for existing prerequisites.

[Final normal-admission handoff](https://github.com/honua-io/honua-server/pull/5345#issuecomment-5937948231)
records the repaired heads and evidence without changing the CI repair's COVERS.
The user restarted fleet watch. Its watcher resumed at2026-10-01T19:07:52Z
and its normal serialized lander resumed at19:08:21Z. CI repair
[#5345](https://github.com/honua-io/honua-server/pull/5345) merged at19:09:07Z
as `22ae8be27175f733ad47b678e8ef01fbc649bedf`; ancestry in fetched trunk was
verified. The lander also merged documentation/certification PR #5347, giving
trunk `d2cf2fd27523494245d6ace35dc411655ae5354d`, and dispatched
[trailing CI36912211773](https://github.com/honua-io/honua-server/actions/runs/36912211773).
That run remains pending. The four optimization PRs retain their exact green
heads and zero unresolved threads but are still open behind the trunk brake.
No manual/admin merge, second lander caller or brake-state override was used.

The newer pre-repair trunk run36890294472 differs from the old XML assertion
failure: its Catalog/ImageServer support shard exhausted the18-minute budget
while still producing output. The retained timing artifact records1081 seconds,
exit124, `capacity_exhausted`, last output4 seconds before exit and no completed
TRX. The Catalog/ImageServer shard passed in the subsequent unchanged-budget
trailing run36912211773. That run's server image scan passed, but its filesystem
scan still failed on client-tooling urllib3 2.7.0 (CVE-2026-97687/CVE-2026-97689,
reported fixed version2.8.0).

[CI follow-up #5358](https://github.com/honua-io/honua-server/pull/5358), initial head
`c89c4db32f59942a47e742a7a9f019078ba01327`, closes tracking issue #5357. It changes
only the support shard's caps18/28→30/40 minutes, the two client/conformance
urllib3 pins2.7.0→2.8.0, and evidence documentation. Every filter/path/project,
other dependency pin and server/Native AOT input is unchanged. Full CI router
validation passed under the shared build semaphore:1539 test classes covered,
21 exact declared partitions and76 populated filters. Both full requirements
graphs resolved against PyPI (23 OWSLib packages,35 conformance packages).
Matching Trivy0.70.0, verified against its release digests/checksums, passed a
repository vulnerability scan over13 targets with zero fixed HIGH/CRITICAL
advisories. This is not a secret-scan or whole-matrix proof. The initial local
scanner database-download failure from the WSL credential helper was retained;
the passing attempt used a temporary isolated Docker credential configuration.
The full managed pre-PR suite was not claimed: its dry run selects FULL; these
specific equivalent checks and their limits are disclosed in the PR. Codex
review reported an account quota limit, and the allowed independent Claude
review was requested at the exact head. The trusted Review Gate is green with
description "No reviewer objections; review trails this merge (fix-forward
admission)"; this is not claimed as a completed independent review. The PR Gate
and requested independent review remain pending.
The fixed source is still fully qualified, but that does not make the whole
trailing matrix green.

The independent review at c89c4db32 did post its clean attestation and returned
`verdict=clean`, with exactly one matching attestation. The evidence checker
confirmed consistency and then failed because GitHub CLI rejects `--slurp`
combined with `--jq`. That failed workflow is retained as run36915468887;
it is not described as a successful workflow or a reviewer objection.

The current repair head is `d6241371e4682245338afb674e65310fd8d014ce`. Its further
changes pipe paginated API output to external jq, add a regression fixture in
the existing reviewer suite and record the evidence. Trusted application ID,
latest-result selection and fail-closed behavior are preserved. The fixture
exercises separate pages, newer failures, foreign applications, unrelated and
missing checks, and malformed JSON against the actual workflow expression.
[Exact-head hosted router job110553529049](https://github.com/honua-io/honua-server/actions/runs/36917001634/job/110553529049)
passed both that new test and the complete router suite. The redundant local
attempt was cancelled with exit130 while still queued, before acquiring any
shared build slot or executing tests; its receipt is retained. The temporary
hold was removed only after this hosted proof was recorded. A new independent
review was requested at d6241371e. The remaining build gate and whole trailing
matrix are still pending. No application or Native AOT input changed.

The new image/source requires a new campaign and calibration binding; the old
prepared strict candidate is historical. The final comparison has not started.
The user should not quiet the machine yet: normal merges/final serving-content
proof and mandatory calibration must be ready first. There is still no isolated
load-generator endpoint or valid calibration evidence.

Current receipts under `results/jit-optimization-batch-20260929/`:
`release-timestamp-repair-pg17-v1-20261001/receipt.json`,
`timestamp-integration-repair-proof-20261001.json`,
`timestamp-repair-aot-cloud-success-20261001.json`,
`timestamp-repair-aot-acquisition-v4-20261001/receipt.json`,
`durable-timestamp-repair-aot-smoke-v1-20261001/receipt.json`,
`harness-control-checkout/results/timestamp-repair-aot-smoke-v1-20261001/`, and
`release-ready-handoff-20261001.json`. The previous handoff was preserved before
updating it to the corrected source; both readiness/publication flags remain
false.

## Normal merges and fresh optimization head, 20:43 UTC

CI repair [#5358](https://github.com/honua-io/honua-server/pull/5358) merged through
the fleet's serialized lander at2026-10-01T20:23:52Z, producing trunk
`484a03baf8f0da5ce731fb2b332e2a476e6b9ea9`. Its current-head PR Gate passed;
independent review posted a clean attestation for d6241371e. That review workflow
still used the old default-branch CLI expression and failed after its clean
attestation; the expression repair became available on trunk only after merging.
No override, manual/admin merge, matrix cancellation or second lander was used.

The earlier trailing run36912211773 is now terminal: all106 jobs were enumerated.
Only Docker Build & Integration Test and its CI Gate aggregator failed. All
server shards and AOT Build Verification passed at source d2cf2fd27. These checks
are source-labelled and do not prove the optimization release or its performance.
The next old-pin run36914999953 at dc7109c2f still has three active jobs and the
same Docker failure. Repaired-trunk run36921286867 at484a03baf is queued with no
jobs yet. Neither active nor queued run was cancelled.

PR [#5343](https://github.com/honua-io/honua-server/pull/5343) now has head
`1b2829ffff1aea96a94aae8b173817401b98b7e0`, a normal non-force merge of actual
trunk484 into its previously qualified d283abbcb head. The entire application
`src` tree and shared .NET build/package settings are unchanged. Its fresh
PR Gate36921770987 has passed format, selection and router jobs; build and six
affected application shards remain active. Independent review posted
[a clean exact-head attestation](https://github.com/honua-io/honua-server/pull/5343#issuecomment-5940149397)
at20:41:26Z; workflow completion remains a separate check. #5349, #5351 and
#5354 retain their earlier green exact-head gates. No optimization PR is merged
at this checkpoint.

Generated-artifact PR #5346 changed `docs/gis/data/feature-catalog.json`, which
Honua.Ai embeds as `Honua.Ai.Catalog.feature-catalog.json`. The existing qualified
f1f040344 Native AOT candidate therefore cannot be labelled as the final merged
runtime content. A fresh production AOT build and oracle smoke are required
after all four optimization PRs land. The frozen application optimization scope
is unchanged. Final timed traffic remains unstarted.

New receipts: `trailing-ci-36912211773-terminal-jobs-20261001.json`,
`pr5343-trunk-ci-refresh-20261001.json`,
`fixed-trunk-ci-36921286867-jobs-2043-20261001.json` and
`old-pin-trunk-ci-36914999953-jobs-2043-20261001.json` under the existing evidence
root. Repeated observations and unsuccessful attempts remain retained.

## Fleet recovery and three optimization merges, October 2, 07:21 UTC

The WSL boot at20:49 UTC interrupted fleet watch after the earlier restart.
At07:04 UTC, the actual user service was inactive and no watcher was running.
The existing disabled service was started with `systemctl --user start
honua-fleet-watch.service` at07:05:13 UTC. Its configuration and enablement were
unchanged. It recognized green trunk484a03baf and resumed normal admission.
No second lander, manual merge, brake override or matrix cancellation was used.

[Repaired full trunk matrix36921286867](https://github.com/honua-io/honua-server/actions/runs/36921286867)
is terminal success at484a03baf. Paginated enumeration confirms106/106 terminal
jobs, all successful or deliberately skipped, including successful Docker,
Native AOT verification and CI Gate. #5343's fresh gate36921770987 also passed
its build and every selected application shard; independent exact-head Claude
review workflow36922074245 passed. Both are stronger evidence than a pending
run or attestation alone.

The fleet merged #5343 as `6fb935393275f05e0416f595d4a5bd7127cc904e`, then
#5349 as `55673ba0b79623efa07aaebdab3504f456b0f3ac` and #5351 as
`67cf3e12cb8b707664741eb7be0d63d672f9c2d7`. Overlaps were deferred between
passes by normal policy. Unrelated control-plane repair #5359 also landed as
`b9311dd0c0bd541b9dc7a7f7edbc2c46911c04a6`; it must be accounted for in final
build content and qualification. #5354 is still green and mergeable at its
existing b71d85af6 head, but four commits now await verification since the last
green source. Its hold is the normal budget, not a failed review or conflict.

Candidate `53fbe4359aca83755bd36f52f8563e08bae9dd5f` combines the frozen, already
qualified four-optimization source with actual landed trunk through67cf3e12c.
Its merge was conflict-free. Compared with f1f040344, the application change is
only the landed AWS Batch cancellation repair; its two test files and embedded
catalog update are included. The new selected qualification retains all six
previous suites and adds the affected AWS Batch/cancellation handoff tests.
It uses one shared build slot and fresh PG17 fixtures. This pre-merge candidate
is not claimed as final trunk, final image, or a performance result.

The first attempt failed before building because Docker Desktop restored the
shared `/tmp/geobench-feature-campaign-1000.lock` file bind as an empty directory
after reboot. No tests or fixtures ran. The directory was confirmed empty and
unused, and its exact metadata was recorded. An unprivileged repair failed and
was retained. A separately owned helper replaced only that invalid node with a
regular shared lock, then cleaned itself. The failed qualification controller
was removed by exact identity after its logs and exit state were retained.
The launcher now verifies/creates the regular lock and checks the build-slot
file before Docker creation. Retry `merged-release-candidate-pg17-v2-20261002`
is actually running and building, holding shared slot1. No active lock inode
or foreign controller was replaced or removed.

Receipts: `fleet-recovery-and-green-trunk-20261002.json`,
`fixed-trunk-ci-36921286867-terminal-{run,jobs}-20261002.json`,
`pr5343-fresh-gate-terminal-20261002.json`,
`merged-release-candidate-preparation-20261002.json`,
`measurement-lock-repair-v{1,2}-20261002.json` and both qualification attempts.
Final timing and publication flags remain false. Once #5354 lands, final
application/build content must match the qualified candidate or be requalified;
the production Native AOT build will use the actual merged source.

## Final merged-source export prepared, 07:37 UTC

An isolated manual export is prepared and pushed at workflow commit
`a86701f87f06df617cfa710ae6ee75549f648149`, branch
`qualification/aot-export-final-20261002`. It has not been dispatched and is
not a PR against trunk. The production Dockerfile, full build profile, SDK and
runtime image pins remain unchanged. It uses the same production boundary
verifier, native liveness check and uniquely tagged export as the successful
earlier qualification; no shipping alias is moved.

The manual input must be an exact40-hex commit, equal the checkout and be a
real trunk ancestor. Before compilation/export,15 Git tree/blob identities must
match the candidate53fbe4359: application source, build settings, restore helper,
production recipe/context filter, certification data, both AI contract fixtures
and embedded API/catalog content. `global.json` is absent in the qualified
source; its continued absence is checked explicitly. The workflow also requires
the exact owned qualification branch. Shell syntax checks passed for every run
block; the installed YAML parser checked the workflow/input structure. Local
content verification matched all15 candidate identities and rejected current
trunk67cf3e12c for its missing page optimization. The unmerged candidate also
fails the trunk-ancestor requirement. No positive final-source hosted execution
is claimed before #5354 merges.

At this observation, the same qualification controller2350be47b is still
actually running in its fresh build phase with current heartbeats, no errors,
and no completed tests yet. The two actual trunk runs36976906927 and36977326611
remain queued/pending. Active shadow-batch run36976867238 belongs to the lander
and is not a trunk verdict; its observed jobs contain no failures. No run was
cancelled or restarted. The prepared export receipt is
`final-aot-export-preparation-20261002.json`; immutable workflow/content hashes
and the limits of validation are retained there.


## All performance merges and hosted final verification, 17:30 UTC October2

The normal lander merged [#5354](https://github.com/honua-io/honua-server/pull/5354)
as `6e574b5158c3f8bd48f35c93ff57ee231f818732`. The resulting actual trunk
source36581bd298 includes all four frozen optimizations. Exact Git ancestry
and15 runtime/build objects match the expected candidate; `global.json`
remains absent. No application source or production Dockerfile was modified
for the qualification workflow.

Before that merge, the full matrix at67cf3e12cb passed, with106 of106 jobs
accounted for and Docker/AOT/CI Gate successful. It covers the first three
performance merges; it is not claimed as final-source verification. A second
actual WSL restart interrupted the local53fbe4359 qualification at07:47 UTC
(exit255, OOMKilledfalse, no completed tests). All four owned child resources
and the terminal controller were removed by verified exact identities, with
logs and the interruption/cleanup receipt retained. The existing fleet watch
service was verified inactive and started at17:06 UTC. No autostart setting,
merge brake, fleet budget or shipping alias was changed.

[Hosted final qualification37041193232](https://github.com/honua-io/honua-server/actions/runs/37041193232)
uses isolated workflow commit `87a6d0663b38e2eeba84b4eb071e878b46a9faca`
and checks out exact merged source36581bd298. Native export and seven selected
managed suites run on separate hosted machines. The managed driver uses the
pinned SDK/PostGIS17/Redis fixtures, source-stamped fresh compilation,
nonempty TRX results with zero failures/skips, required method coverage,
and all eight fractional timestamp variants. It retains failed attempts.
Workflow YAML, Bash syntax, Python compilation and diff checks passed;
hosted execution remains the actual correctness proof. Both jobs were queued
at dispatch. No final timing is authorized by this dispatch.

Receipts: `final-merged-source-proof-20261002.json`,
`final-hosted-qualification-dispatch-20261002.json`,
`trunk-three-optimization-ci-36977326611-terminal-jobs-20261002.json`,
`durable-merged-release-candidate-pg17-v2-20261002/interruption-and-cleanup.json`
and the current release PR snapshot. The previous handoff is archived as
`release-ready-handoff-before-final-merge-20261002.json`.


## Final image acquisition and oracle prepared, 17:40 UTC October2

The hosted managed-correctness job is actually running and passed checkout,
service readiness and exact merged-input verification. Native export remains
queued. The prepared acquisition verifies whole-workflow success, both artifact
digests, all seven TRX files and required methods, the pinned SDK/spec, source,
all15 build-input objects, recipe, registry manifest, runtime configuration and
layer identities. The independent TRX join was checked against retained
historical fixtures; this does not claim any final-source test pass.

The final-image both-product diagnostic oracle driver and owned launcher are
prepared with the same immutable harness/dataset/server pins and all12 rows
per product. They require successful final-source acquisition and managed
verification. No acquisition, oracle traffic or final timing has started.
Recipe hashes are recorded in `final-aot-postrun-preparation-20261002.json`.

WSL had again recreated the shared measurement bind as an empty root-owned
directory at reboot. A read-only Docker probe confirmed its actual type.
There was no measurement-lock holder or active GeoBench controller. The exact
empty invalid node was replaced by an owned helper with inode/mtime checks;
the regular lock was verified and that helper removed by exact identity.
Receipt: `measurement-lock-repair-v3-20261002.json`. No active regular lock,
foreign container or fleet setting was changed.


## Final merged-source managed verification passed, October2

The hosted managed-correctness job110951472791 completed successfully in18m26s.
Its artifact ZIP digest matches GitHub's recorded digest. All seven TRX files
match their receipt hashes, all cases passed, and the requested source,
workflow commit, pinned SDK/spec and exact owned container cleanup were checked.
Total558: core27, security58, PostgreSQL265, OGC API66, GeoServices108, WFS12
and cloud handoff22. The independent TRX-definition join confirms all11 required
native-reader methods, all five page-ownership/geometry methods, the indexed
scope and validated security snapshot methods, both cloud test classes, and
exactly eight passing fractional timestamp variants. This is final-source
managed correctness evidence, not Native AOT performance evidence.

The two earlier foundation PRs5325 and5339, the four final performance PRs and
both CI repair PRs are all merged and exact Git ancestors of source36581bd298.
Receipts: `all-relevant-performance-and-ci-merges-proof-20261002.json` and
`final-hosted-managed-qualification-v1-20261002/verification.json`, with the
raw ZIP, all TRX/log files and terminal job JSON retained alongside them.
The Native AOT candidate job remains live in production compilation. Final
image acquisition, both-product oracle, quiet-machine confirmation and
publication calibration remain pending. No final timing has started.


## Final production Native AOT ready for quiet-machine window, October2

[Hosted qualification37041193232](https://github.com/honua-io/honua-server/actions/runs/37041193232)
completed successfully: production full-profile Native AOT build, serving-image
boundary validation, native liveness, unique image export, and the seven-suite
558-case managed correctness job. Actual source is36581bd298; the isolated
workflow commit is87a6d0663. No shipping alias or default workflow was changed.

Final immutable image:
`ghcr.io/honua-io/honua-server@sha256:b2549f8d3d1e6eac54d697d45de31e0f8b921accb34f083eda44612e72ac1f66`.
Registry config digest:
`sha256:711b3a45b42402db55498aa9aba32d967e1c6dfb20e03fc80eaa21514dfcbb5e`.
Both artifact ZIP digests, all seven TRX files, required methods/eight timestamp
variants, all15 build-input objects, production recipe/profile, exact source,
registry manifest, runtime configuration and layer identities were checked.
The historical image842bf147 remains recorded at its own source; it was not
relabelled as final.

The short both-product oracle passed24/24 rows: twelve each for Honua and stable
GeoServer with its matching OGC extension. Each attempt is passed and cleaned,
with no fairness failure. Honua executed the native `/app/Honua.Server`, with
no CoreCLR mapped and production test-schema headers disabled. Its runtime
budget is4CPU/4GiB, matching the database/server contract. This two-second
warmup/three-second measurement smoke proves correctness only. It is valid
and explicitly not publishable performance. Report SHA256:
`8b83b22a3b1a995f69b09d534cbe6bf9e7e0f73b29991bb828bdd782ef1d44ea`.
Both stacks and the terminal owned smoke controller were cleaned by exact
identity. An initial postrun audit expected a command list; the runtime schema
records a command string. The assertion was corrected to the exact native path,
with no campaign rerun or cleanup before the correction; the note is retained.

The fresh comparison directory is
`harness-control-checkout/results/aot-final-merged-comparison-v1-20261002`.
It pins the new image, stable GeoServer, PostgreSQL17 and k6; contains all12
selected point scenarios, five alternating server pairs, seed42,180s warmup
and120s measurement; and records an empty attempt ledger. Preparation started
no server stack or traffic. Its terminal owned coordinator was removed.
Coordinator hostname: `gb-aot-final-merged-20261002`.
New calibration binding:
`2457da4fcbde08108b4040380a6b4913a1a9d920e9fd29ab3031e1955ac315bc`.
Older candidate/calibration bindings cannot be reused for this image.

The user must confirm the machine is quiet before timing. Strict launch and
publication also require the missing isolated generator/observer calibration
for this binding; quiet WSL alone does not supply it. Approximately10hours are
needed for the five paired point-feature repetitions, plus preparation/drain
and calibration. The final-source trailing CI run37040748373 is still live in
AOT Build Verification, with all other then-visible jobs terminal and no
failures reported. No current AOT throughput/latency ratio is claimed.

Receipts: `final-hosted-qualification-terminal-20261002.json`,
`final-merged-aot-acquisition-v1-20261002/receipt.json`,
`durable-final-merged-aot-smoke-v1-20261002/{receipt,cleanup}.json`,
`final-strict-campaign-preparation-20261002/receipt.json` and the current handoff.
The previous handoff is preserved as
`release-ready-handoff-before-final-aot-ready-20261002.json`.


## Final-source CI passed and evidence ready for review, October2

[Final-source trunk CI37040748373](https://github.com/honua-io/honua-server/actions/runs/37040748373)
completed successfully at exact merged source36581bd298. All106 paginated job
records were accounted for, with unique IDs and terminal success/skipped
conclusions; AOT Build Verification and CI Gate explicitly succeeded. Earlier
live snapshots remain observations rather than terminal verdicts. Terminal
run/job receipts are retained as
`final-trunk-ci-37040748373-terminal-{run,jobs}-20261002.json`.

The Native AOT image,558-test managed verification,24-row both-product oracle
and fresh comparison manifest are complete and verified. The documentation
contains no final-source AOT speed claim. Final timing still requires the
pending user quiet-machine status and source-bound isolated-generator/observer
calibration. The five paired measured repetitions and publishable report have
not been produced. Missing calibration keeps strict launch/publication closed.

## Quiet-machine calibration started, October2

The user confirmed "the machine is quiet" before local calibration. WSL had
restarted with approximately40GiB available, compared with24GiB in the previous
manifest. The first collector's host-fingerprint preflight rejected that drift
before any server stack or traffic started. Its failure and terminal controller
identity were retained, and only that verified owned controller was removed.

A fresh manifest preserves the pinned source, images, dataset, harness, resource
budgets, scenarios and paired order while recording the actual current host.
Directory: `harness-control-checkout/results/aot-final-merged-comparison-v2-20261002`.
Calibration binding:
`5926851b4d2a4bf3881e9f4c6836902a3d92227f9e7c6ad46ad75bc286e34444`.
The previous manifest remains intact and cannot supply calibration for this
changed configuration. The shared measurement lock had been restored as an
empty root-owned directory after restart; an exact inode/mtime guard, no-holder
check and empty active-container inventory preceded replacement of that invalid
node. No active regular lock or foreign resource was changed.

Owned controller `gb-local-observer-final-aot-v2-20261002` started three local
observer-off/on pairs for each product, restricted to `mixed:vus:10`, using
180s warmup and120s measurement per treatment. It holds shared build slot1,
uses the normal measurement lock, checks all immutable inputs and performs
fresh-fixture oracle/pressure preflights. Failed/interrupted runs and all raw
samples remain visible in separate calibration ledgers. This collector does
not populate the final comparison attempt ledger or approve publication.

Local calibration takes roughly one hour plus provisioning and drain. Its
results and overhead checks are pending; no final AOT speed ratio is claimed.
A separate load-generator calibration still must pass before the five paired
strict comparison repetitions can start. The current host being quiet does
not substitute for that evidence.

Receipts: `measurement-lock-repair-v4-20261002.json`,
`final-strict-campaign-preparation-v2-20261002/receipt.json` and
`local-observer-final-aot-v{1,2}-20261002/{launch-receipt,receipt}.json`.

## Local calibration complete; full AOT diagnostics started, October2

All six scheduled local calibration pairs completed: three fresh owned
fixtures per product, each with180s warmup and120s measurement for both
observer treatments. All measured responses passed the precomputed oracle;
late completions were counted separately. Every attempt passed pressure and
postrun configuration checks and was cleaned up. The controller exited0.
An independent pass recomputed the complete report, rechecked every retained
artifact hash, validated runtime image/CPU/memory identities, confirmed Native
AOT without CoreCLR, and verified that all six fixture owners had no resources
remaining. The publication gate was kept separate from these correctness checks.

| Product | Median throughput change, observer on/off | Median p95 change | Within5% |
| --- | ---: | ---: | --- |
| Honua | -2.28% | +2.00% | Yes |
| GeoServer | -11.33% | +17.03% | No |

These are calibration deltas for `mixed:vus:10`, not product speed ratios.
Every repetition, including the earlier large variation, remains in the report.
The local WSL setup fails the publication overhead gate, and separate-generator
calibration remains absent. Quiet-machine confirmation alone did not satisfy
the comparison contract. The strict comparison attempt ledger remains empty.
Calibration report SHA256:
`38d19d9f023192412bd531a06f5b9161dc15e807a89aef12ce29f161c219522a`.
Independent verification: `local-observer-final-aot-v2-20261002/independent-verification.json`.

After calibration fully drained, owned controller
`gb-final-aot-local-diagnostic-v1-20261002` started a separately labelled
**local diagnostic** campaign at
`harness-control-checkout/results/final-aot-local-diagnostic-v1-20261002`.
It uses the same final production Native AOT image/source and frozen harness,
all twelve point scenarios, three alternating paired repetitions,30s warmup
and30s measurement, fresh isolated fixtures, and shared build/measurement locks.
Expected coverage is72 measured scenario rows. Its binding is
`3e79999300883a942a361e3e3e36d1597ee59961b2101eaa5af8e8d4dd9693ac`.
The launcher checks the terminal calibration controller, independent verification,
complete cleanup, and exact fingerprints before starting traffic. This campaign
can provide current diagnostic throughput/latency figures; it cannot substitute
for five strict repetitions or authorize publication. Results are pending.

Driver/launcher receipts: `final-aot-local-diagnostic-v1-20261002/`.

## Final production Native AOT diagnostics complete, October2

All six scheduled product runs finished and cleaned up: three fresh paired
repetitions, with seed42 alternating Honua/GeoServer, GeoServer/Honua,
Honua/GeoServer. Each of the twelve scenarios used30s warmup and30s measurement.
Warmup, measured and drain traffic remained separate. All72 measured rows
passed, with470,043 semantically valid completions, zero invalid responses or
cancellations, and724 late completions excluded from measured throughput.
Every measured response was validated against precomputed PostGIS expectations;
no oracle database queries ran during measurement.

This is **local diagnostic evidence only**, covering OGC API feature queries
on the deterministic100K-point dataset. It does not cover WFS, rendering, tiles,
GeoServices REST, larger datasets, lines or polygons. Literal-prefix coverage
does not establish escaped-underscore behavior. Honua's `automatic-bounded`
profile used six source-query connections, with4CPU/4GiB for each server and
database. The generator had8CPU/4GiB. No exact response cache or adaptive
admission was enabled. The host was the same40GiB WSL configuration recorded
for the local calibration.

Final source: `36581bd29870101d103ea16e3ba215a2a98811fe`.
Production full-profile Native AOT image:
`ghcr.io/honua-io/honua-server@sha256:b2549f8d3d1e6eac54d697d45de31e0f8b921accb34f083eda44612e72ac1f66`.
GeoServer3.0.1 plus matching OGC extension used local immutable image ID
`sha256:32b61aed98bca6cc0821fbcdab9dbc5b9b22b6fa1af6d51d396fb64e63dac491`;
this image has no registry RepoDigest. Harness:
`869d19e75bdf456c508b561d966652921cfd9dc5`.
Dataset SQL SHA256:
`2ca9025b025361a85e7e0866a80748d29dacd44d27987ce75631a7473189a525`.

Ratios below are **Honua / GeoServer within each paired repetition**. The table
reports the median of three paired ratios and their complete range. Throughput
above1 favors Honua; p95 below1 favors Honua. These paired medians can differ
from the ratio of the separate per-product medians. Each repetition and its
p50/p95/p99 remain in the raw report; no averaged overall percentile or winner
score was calculated.

| Scenario | Honua median req/s | GeoServer median req/s | Paired throughput ratio (range) | Paired p95 ratio (range) |
| --- | ---: | ---: | ---: | ---: |
| equality | 166.83 | 172.23 | 1.20 (0.75–1.27) | 0.80 (0.76–1.29) |
| range | 135.27 | 186.37 | 0.95 (0.71–1.01) | 1.05 (0.94–1.36) |
| prefix | 134.30 | 112.93 | 1.26 (1.06–1.46) | 0.91 (0.70–1.16) |
| bbox-small | 315.47 | 405.60 | 0.78 (0.65–1.06) | 1.27 (0.85–1.57) |
| bbox-medium | 107.43 | 70.80 | 1.71 (1.40–2.35) | 0.66 (0.47–0.86) |
| bbox-large | 75.47 | 25.73 | 3.52 (2.93–3.67) | 0.31 (0.27–0.39) |
| page-shallow | 117.57 | 155.80 | 0.97 (0.75–1.01) | 0.99 (0.96–1.40) |
| page-medium | 119.57 | 113.70 | 0.95 (0.85–1.05) | 1.07 (0.89–1.07) |
| page-deep | 71.77 | 50.60 | 1.62 (1.42–2.73) | 0.65 (0.39–0.71) |
| empty | 588.07 | 765.13 | 1.03 (0.77–1.33) | 0.58 (0.38–0.64) |
| bbox-boundary | 582.00 | 701.77 | 0.88 (0.83–1.02) | 0.67 (0.48–1.06) |
| mixed:vus:10 | 159.17 | 110.20 | 1.55 (1.44–2.28) | 0.56 (0.40–0.59) |

The measured outcome is a mixed bag. Medium/large bbox reads, deep pagination,
prefix filtering and mixed traffic had throughput ratios above1 in every pair.
Small bbox reads were about22% behind at the paired median, and boundary reads
about12% behind. Wide ranges and the failed calibration make small differences
inconclusive. These figures do not establish that Honua wins in all areas.

An independent verification recomputed the full report and matched both JSON
and Markdown byte for byte, rechecked every artifact hash and runtime budget,
verified actual `/app/Honua.Server` execution without CoreCLR in all three
Honua fixtures, and confirmed all six fixture owners were absent. The terminal
diagnostic controller exited0 without OOM and was removed by exact identity.
Failed calibration/preflight attempts and historical artifacts remain visible.
The quiet-machine window is finished; no further quiet period is needed now.

Campaign: `harness-control-checkout/results/final-aot-local-diagnostic-v1-20261002`.
Binding: `3e79999300883a942a361e3e3e36d1597ee59961b2101eaa5af8e8d4dd9693ac`.
JSON report SHA256:
`1a25bc39cff0a3844b136198b526667eb55b404e6929b00b5563663ccde868f1`.
Markdown report SHA256:
`376c408b0ca3fb1e8acbfd6470816523da16d842e36f170d17a48c03c40f0127`.
Independent verification and exact cleanup receipts:
`final-aot-local-diagnostic-v1-20261002/{independent-verification,cleanup}.json`.

**Strict comparison and publication remain blocked.** The local observer
calibration failed GeoServer's5% gate, with11.33% throughput and17.03% p95
variation. Genuine separate-generator calibration is still missing. The strict
comparison ledger is empty; its five paired180s/120s repetitions have not run.
The next step requires a controlled setup with passing, fingerprint-bound
calibration before those repetitions and publication review. Repeating noisy
local attempts until a favorable result appears would not satisfy that contract.
