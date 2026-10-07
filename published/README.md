# Approved result records

New approved, curated result packages live in **published/<run-id>/**. Raw runs
remain local and ignored under **results/<run-id>/**. A run appearing in results
is not approved. Neither the runner nor the publisher approves a run.

The historical tracked results/baselines/, results/releases/ and loose result
fixtures retain their existing paths and consumers. They are not automatically
moved or relabeled by this workflow.

## Review and promote

Finish the run, review the methodology and relevant audits, and retain the raw
evidence. For broad protocol runs, capture the fairness audit's output and
require its successful exit status before continuing:

    python3 scripts/audit-fairness.py \
      --results-dir results/<run-id> --servers honua,geoserver \
      --strict-equal-db-budget > results/<run-id>/fairness-audit.txt

Warnings still need review and disclosed limitations. This packaging command
does not rerun a benchmark, independently endorse its conclusions, or replace
the fairness, oracle, image, timing, calibration and reproducibility gates.

Create a pending plan with only the records to be reviewed:

    python3 scripts/publish-results.py plan <run-id> \
      --artifact report.md --artifact report.json \
      --artifact benchmark-metadata.json --artifact fairness-audit.txt \
      --artifact system-cards/honua.json \
      --artifact system-cards/geoserver.json \
      --artifact honua-response-shapes.json \
      --artifact geoserver-response-shapes.json > /tmp/geobench-review.json

The plan includes the exact file sizes and SHA256s and has decision: pending.
After an operator actually approves these bytes, edit the plan to record:

- decision: approved, approved_by, and approved_at with a timezone,
  for example 2026-10-07T12:00:00Z.
- reference: an HTTPS issue/comment/review record documenting the decision.
- harness_revision: the full commit used for the original run. Do not substitute
  the current publisher checkout's commit for an older run.
- limitations: reviewed caveats, especially fairness warnings.
- raw_evidence_reference, when available: a durable HTTPS archive/reference
  for the excluded raw recordings. Keeping them in local results alone does
  not make them available to other reviewers.

The operator's reference records the scientific approval. The command validates
that explicit record and its bound artifact hashes; it does not authenticate
the reviewer or query the linked service. Changes after review require a fresh
approval, rather than silently publishing changed data under an old decision.

Preview, then explicitly apply, then verify:

    python3 scripts/publish-results.py promote <run-id> \
      --approval /tmp/geobench-review.json --dry-run
    python3 scripts/publish-results.py promote <run-id> \
      --approval /tmp/geobench-review.json --apply
    python3 scripts/publish-results.py verify <run-id>
    git add published/<run-id>

Review the staged package through the normal PR process. The promotion command
does not commit, push, upload, or post approval on the operator's behalf.

For a feature comparison campaign, select report.md, report.json and
campaign.json instead of the broad protocol metadata/fairness/card set.
The campaign manifest and report retain that contract's configuration, budgets,
calibration binding, harness snapshot hashes, attempts and validation receipts.
The publisher requires comparison mode, valid: true, publishable: true and
no reported publication failures. Diagnostic/failed campaigns cannot be
promoted even if an approval file claims approval. Include any additional
curated system cards/audits needed for the reviewed conclusions.

## Package and retention contract

Each approved destination contains the selected files, approval.json, and
publication.json recording source-run location, original harness revision,
approval/evidence references, SHA256s and sizes. The publisher verifies a local
staging package, rechecks the original inputs, then renames the complete package
into place. A per-run exclusive lock prevents cooperating concurrent promoters.
Existing destinations and uncertain leftover locks are never overwritten or
stolen; verification is a separate idempotent operation.

An interrupted promotion can leave a hidden staging directory and publishing
lock. Both are ignored. Inspect them and confirm no promoter is running before
removing only that run's abandoned staging/lock paths.

Only named report/audit/metadata JSON, Markdown, saved fairness text and copied
system-card records are selectable. Records must be valid UTF-8, at most 4 MiB
each, and at most 16 MiB across at most 64 files. Raw k6 JSONL/NDJSON recordings,
source/harness trees, build outputs, databases, .env and arbitrary directories
are not copied. Link/junction escapes, nested Git checkouts, hardlinks and
recognizable credentials are refused. The allowlist and credential checks are
defense in depth: review every selected record for private or sensitive data,
redact metadata before approval if needed, and record the resulting exact hashes.

Promotion always copies curated records and preserves the original run. Verify
the committed package and any separately archived raw evidence before deciding
on retention. Raw cleanup is a separate explicit operator action; the publisher
never deletes runs, legacy baselines, release records or source trees.
Before any raw cleanup, check the owning worktree's Git lock, operational
markers, live run/process activity and retention instructions. Preserve locked
or active run trees even when their outputs are ignored. An ignore rule marks
local output; it does not authorize deletion or establish that a run is idle.

## Working checkout placement

Keep Git clones and worktrees alongside the repository, outside results and
published, for example /home/mike/honua-io/wt-geobench-<purpose>:

    git worktree add ../wt-geobench-experiment -b experiment origin/trunk

Results is an output area, not a workspace. A runner's immutable harness input
snapshot is raw evidence, not a working Git checkout; it stays out of the
curated package, which records its hashes and the original harness revision.
