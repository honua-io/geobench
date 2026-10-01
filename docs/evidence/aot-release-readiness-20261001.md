# Frozen release and Native AOT readiness — October 1, 2026 (UTC)

The user froze further optimization for this release and requested a production
Native AOT image before quieting the machine for final measurements. **The setup
is not ready for final timing or publication yet.** No final comparison was started.
The latest performance evidence remains the [three-pair JIT diagnostic](jit-production-three-pair-20261001.md),
which excludes the native/metadata and pagination patches.

## Frozen scope and correctness

The release includes [bounded planning/shared GeoJSON #5343](https://github.com/honua-io/honua-server/pull/5343),
[native decoding #5349](https://github.com/honua-io/honua-server/pull/5349),
[authorized metadata reuse #5351](https://github.com/honua-io/honua-server/pull/5351)
and [response-owned pages #5354](https://github.com/honua-io/honua-server/pull/5354).
Policy batching #5352 is checkpointed and excluded. Exact-count/page batching,
further projection/ID work and direct output rewriting are deferred.

Native/metadata source `cf49cb77d31e7a56ed81870b8e10ab6e7a427a61` passed a
fresh source-stamped Release JIT build, changed-file format and all519 selected
cases on PostgreSQL17. PostgreSQL18 passed all265 provider cases using the
identical hash-verified assemblies. PostgreSQL16 retained four failures in the
volatile-policy prepared-query fixture. Its pinned image runs PostgreSQL16.4;
those tests used a startup role option while authenticating as the fixture
superuser. PostgreSQL documents a [role-reset bug affecting versions before16.5](https://www.postgresql.org/support/security/CVE-2024-10978/).
This is a plausible explanation, not a passing test verdict. Current test-only
repair authenticates as the restricted LOGIN role and asserts the pooled identity.
No runtime recovery or RLS rule was weakened.

Independent pagination source `c3f597df357978b120a90fea23f61aaa05ca92ef`
passed fresh Release JIT compilation, changed-file format and all55 selected OGC
GeoJSON/query/geometry/identifier cases. The hosted architecture test found two
new methods missing tier attributes; head `b71d85af6714b70a2257c807db1f0668166002f6`
adds UnitTheory/UnitTest. Serving files are unchanged from the local pass.

The combined frozen source is now `da06c51de0bc8579601fc86bc5ddcafabaed7a70`,
branch `qualification/release-20261001-r2`. It includes both test-only corrections.
A fresh six-project Release JIT qualification is running on PostgreSQL16 with
mandatory native, metadata and page regression identities. PostgreSQL17/18 reuse
checks and full HTTP oracle remain pending. Prior failures, logs and cleanup
receipts remain retained; they were not silently replaced.

## Cloud production AOT acquisition

[Production boundary run36819900206](https://github.com/honua-io/honua-server/actions/runs/36819900206)
is compiling frozen source `4c54532a512ec55246c3d4f1578ff89c5036bab1` using the
unchanged production Native AOT Dockerfiles. The current combined source has
identical serving/build inputs; its only subsequent patch changes test login.
That run verifies the image and exports build cache, but does not publish a
pullable application image.

[Qualification export run36820832934](https://github.com/honua-io/honua-server/actions/runs/36820832934)
checks out exactly `da06c51de0bc8579601fc86bc5ddcafabaed7a70`, waits for the
successful generic boundary job/cache, and builds `docker/Dockerfile.aot` with
full profile, native compilation, the exact revision label, and
`RUNTIME_PACKAGE_REVISION=20261001` to refresh runtime OS packages. It retains
production SDK/runtime digest pins and verifies the native serving boundary and
HTTP liveness before pushing this isolated tag:

`ghcr.io/honua-io/honua-server:qualification-aot-da06c51de0bc8579601fc86bc5ddcafabaed7a70-36820832934`

The tag is an intended output, **not yet an acquired image or successful build**.
The branch-only manual export workflow does not update shipping/nightly/trunk
aliases, alter the production Dockerfile, disable gates or promote unmerged code.
Its receipt records image ID/digest, production recipe blob, source, arguments
and installed runtime packages. Its workflow head is
`a9ed6349a49a0e6721383e4a41b1addeaeb8e974`; the checkout/build source is the
separate explicitly recorded release SHA above.

## Readiness gate

Finish current-source local and exact-head hosted checks, full HTTP oracle,
normal PR merges and verified source-content identity. Acquire the actual AOT
image by digest and verify its executable/runtime and installed packages before
final timing. The normal server lander currently retains a trunk CI brake;
#5343 has green required PR gates but remains open. Do not bypass that brake.

Only after the image/setup are qualified should the user quiet the shared machine
and authorize the final timed campaign. Twelve scenarios with five pairs and
180-second warmup/120-second measurement take roughly10hours, plus preparation,
drain and calibration. Quiet WSL does not establish the separate isolated
load-generator calibration required by publication gates. That evidence remains
missing; strict publication must fail closed until it is supplied.

## Retained receipts

Under `results/jit-optimization-batch-20260929/`: current-source qualification
preparation/driver/launcher, `release-candidate-v2-pg16-v1-20261001/`, prior
`native-metadata-pg16-v7-20261001/` failure and PG18 pass, the55-case pagination
pass, and `aot-cloud-boundary-launch-20261001.json` /
`aot-cloud-export-launch-20261001.json` bind the live jobs and exact source.
These artifacts do not yet claim final benchmark readiness.
