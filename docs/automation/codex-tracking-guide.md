# Research Observatory coding-agent tracking guide

> **Repository destination:** `docs/automation/codex-tracking-guide.md`. This becomes operational guidance only after it is installed in the target repository.

## Default unit

Work within one approved durable Wave campaign. Do not select work outside the
Wave while it has an executable dependency-eligible slice/task. Capability
boundaries do not end the campaign; complete Wave qualification does.

## Before editing

1. Read root `AGENTS.md`, `docs/README.md`, and `planning/README.md`.
2. Confirm the complete pre-Wave packet is approved at one immutable commit and readiness passes.
3. Read the Wave page, relevant capability packet, active slice plan, affected ADRs/architecture, and UI reference.
4. Claim the task with branch, worktree, base SHA, and lease.
5. Generate the task contract and changed-path verification set.
6. Stop before editing if a required authority or approved plan is missing.

## Command sequence

```bash
python tools/planctl.py --repo . wave ready WN --require-approved
python tools/taskctl.py --file planning/backlog.yaml validate
python tools/taskctl.py --file planning/backlog.yaml wave start WN --agent <agent> --branch <branch> --base-sha <sha> --worktree <absolute-repository-path> --profile LOC --platform windows-x64
python tools/taskctl.py --file planning/backlog.yaml status
python tools/backlog_views.py --repo .
python tools/backlog_views.py --repo . --check
```

Use repository-specific `taskctl` subcommands for claim, evidence, review, and transition as defined by the installed tool and `planning/README.md`.
Every subcommand first applies the committed Draft 2020-12 schema; `validate`
then applies identity, dependency, campaign, gate, lease, evidence, and legal
state invariants that JSON Schema cannot express by itself.
After any successful ledger mutation, regenerate the comprehensive plan and
status summary. Both files are wholly generated; `foundation` fails if they are
missing, stale, or hand-edited.

If `status` reports `STOPPED AT WAVE AMENDMENT`, do not start, resume, or claim
ordinary Wave work. Follow the exact `taskctl amendment` command in the handoff.
The ECR proposal, immutable approval record, base/amendment authority chain,
legal alternatives, and resume condition must remain visible. An approved Wave
is never reapproved; only the append-only amendment lane may authorize the
bounded task inventory.

The normal task transition is:

```bash
python tools/taskctl.py next --profile LOC --platform windows-x64
python tools/taskctl.py claim CAP-XX.SXX.TXX --agent <agent> --branch <branch> --base-sha <full-sha> --worktree <absolute-repository-path> --profile LOC --platform windows-x64
python tools/taskctl.py checks CAP-XX.SXX.TXX
# Commit the implementation and run the declared checks on that exact HEAD.
python tools/taskctl.py submit CAP-XX.SXX.TXX --agent <agent> --from artifacts/evidence/CAP-XX.SXX.TXX.json --note "<summary>"
python tools/taskctl.py review CAP-XX.SXX.TXX --reviewer <reviewer> --result approved --from artifacts/evidence/CAP-XX.SXX.TXX.review-R01.json
python tools/taskctl.py review-telemetry
```

`block`, `renew`, atomic task `submit`, Wave pause/renew/checkpoint/submit, and slice
submit verify lease ownership. There is no campaign-override claim flag. Release
gates cannot be approved twice, out of sequence, or while their preceding wave
contains an incomplete task or unapproved slice. Every mutation validates the prospective ledger before an
atomic compare-and-swap replacement; stale writers and failed replacements do
not overwrite the prior file.

Start/resume/claim metadata is bound to the actual current Git branch, full
`HEAD`, and canonical worktree. Evidence is a single-read snapshot whose base,
branch, commit ancestry, exact changed-file scope, named passing checks, complete
criterion map, empty unverified list, clean tracked/untracked worktree, digest,
and logical uniqueness are checked again on later validation. Task owners cannot
review their own task; Wave campaign owners cannot review their own slice or Wave. Approved
release gates remain semantically tied to a fully DONE and independently
integrated preceding wave.

The atomic task submit freezes the candidate, evidence, criteria, changed paths,
check selection, and exact open-finding replay in one RNN packet. A task review
ledger contains ordered structured findings and explicit closures; approval is
denied while a blocking finding remains open. Follow-up evidence must use
`supersedes.path`, set `baseCommit` to that prior attachment's commit, and
declare the complete incremental diff. Completion does
not excuse non-empty `unverifiedItems`. The only exception is the explicitly
marked `pre-exact-evidence-hosted-ci-residual-v1` migration for four pinned
CAP-00.S03 records; their paths, commits, hashes, task IDs, and exact hosted-CI
residual text are fixed and the marker is invalid everywhere else.

Every new controlled atomic submission must declare a non-empty
`verificationSelection.selectedCommandIds` list. IDs must be exact keys from
`verification-profiles.json`; raw commands remain in the evidence record and are
never substituted for privacy-safe IDs. Historical packets created before this
control may omit the optional frozen `selected_command_ids` field and are not
rewritten or backfilled. A non-empty frozen field is the prospective-control
marker: every completed marked attempt must contain its exact telemetry event,
and validation plus `review-telemetry` fail closed if that event is missing.

Each newly completed controlled review stores one prospective timing event. The
event is recomputed from its immutable round and is restricted to task,
amendment, attempt, and finding-control IDs; submitted/reviewed timestamps and a
nonnegative duration; outcome; severity, blocking, and total counts; canonical
command IDs; and remediation linkage. It never contains an actor or reviewer,
commit, hash, branch, path, rationale, root-cause narrative, review note, finding
body, evidence text, raw command/arguments/output, prompt, source content,
research data, secret, user-data path, or chain-of-thought. `review-telemetry`
prints only stored events in deterministic order, without a generation
timestamp. Pending submissions and pre-control or legacy review records produce
no synthetic event or duration.

## Decision requests

When a decision or approval is required:

1. regenerate the review site;
2. print its `file://` and repository-relative Wave link plus relevant capability detail links;
3. state whether recommendations are already decision-complete;
4. identify only unresolved or changed items;
5. explain that Other requires a brief description and detailed rationale; and
6. do not treat exported feedback as implementation approval.

At a stopped release/readiness/design gate, also include the gate criteria,
current legal approval state, unfinished prerequisites, active/blocked/prerequisite
review links, alternatives, recommendation, and exact approval/resume condition.
If the gate is not currently approvable, ask the human to choose how to handle
the stop; do not ask for premature gate approval. `taskctl next` prints the
minimum release-gate handoff and must be included or faithfully summarized.

## Continuous execution

After approval, continue through tasks, slice integration, independent slice
review, triggered integration checkpoints, and the next approved slice in the active Wave. Ordinary test failure,
debugging, refinement inside the approved envelope, or a documented fallback is
not a human stop point.

One pre-Wave approval binds every contributing capability decision and slice
plan. The Wave campaign is the resumable execution unit. Close it only after the
last ordered Wave slice, full Wave suite, and independent Wave review; do not
reinterpret a capability or slice boundary as a routine approval prompt.

Before claiming, use `taskctl next` and `taskctl show` to identify the active
Wave campaign's next `READY` task. Permitted scope is its objective, deliverables,
criteria, dependencies, profile/platform, and governing sources. At task scope,
select the narrowest checks from its declared verification coverage and the
changed-path impact map that exercise credible failure paths. Defer accumulated
affected-profile checks to risk-cluster checkpoints and complete profiles to Wave
exit unless an explicit criterion or profile-wide impact requires earlier execution,
and record the breadth rationale in evidence.
Completion is commit-bound criterion evidence, submission, required review,
clean tested local main integration, and continuation to the next eligible task
or slice gate.

## Evidence

A completion claim must link every criterion to a named test, report, artifact, source commit, and reviewer outcome. If evidence is incomplete, keep the task or slice in progress/review; do not mark it done with persuasive prose.

After required checks pass and the bounded work is committed, fast-forward the
tested branch into local `main`. Keep any pending review or approval state
pending in the backlog: local Git integration is not a substitute for a workflow
transition. Stop on branch divergence and never push without explicit authority.

## Independent review

Use a fresh agent context when possible. Every task receives a focused
independent disposition of scope, evidence truth, changed contracts, and
credible failure paths. Expand task review for security/credential boundaries,
migrations or destructive I/O, automation/evidence controls, public or
cross-process contracts, and explicit plan requirements. Deep/adversarial review
defaults to the slice. The reviewer challenges scope, architecture,
tests, denial/failure/recovery paths, privacy/security, rights, UI contracts,
platform behavior, hidden TODOs, and whether evidence actually proves the
acceptance criteria.

Maintain one consolidated finding ledger. Required findings are severity-ranked,
reproducible, and criterion-bound. A remediation review replays every prior
finding plus the incremental changed-path risk boundary; it does not restart the
whole audit. Move nonmaterial adjacent improvements to the backlog, and escalate
recurring findings after a second remediation to root-cause/control review.

## Experience work

Do not change the UI reference after implementation merely to make code appear conformant. Update and approve the reference first for intentional changes. Restoration to the approved reference may proceed without a new reference ID.
