# Research Observatory coding-agent tracking guide

> **Repository destination:** `docs/automation/codex-tracking-guide.md`. This becomes operational guidance only after it is installed in the target repository.

## Default unit

Work within one approved capability campaign. Do not select unrelated globally ready tasks while the active capability has an executable next slice/task.

## Before editing

1. Read root `AGENTS.md`, `docs/README.md`, and `planning/README.md`.
2. Confirm the active capability is approved and readiness passes.
3. Read the capability packet, active slice plan, affected ADRs/architecture, and UI reference.
4. Claim the task with branch, worktree, base SHA, and lease.
5. Generate the task contract and changed-path verification set.
6. Stop before editing if a required authority or approved plan is missing.

## Command sequence

```bash
python tools/planctl.py --repo . ready CAP-XX --require-approved
python tools/taskctl.py --file planning/backlog.yaml validate
python tools/taskctl.py --file planning/backlog.yaml capability start CAP-XX --agent <agent> --branch <branch> --base-sha <sha> --worktree <absolute-repository-path> --profile LOC --platform windows-x64
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

The normal task transition is:

```bash
python tools/taskctl.py next --profile LOC --platform windows-x64
python tools/taskctl.py claim CAP-XX.SXX.TXX --agent <agent> --branch <branch> --base-sha <full-sha> --worktree <absolute-repository-path> --profile LOC --platform windows-x64
python tools/taskctl.py checks CAP-XX.SXX.TXX
# Commit the implementation and run the declared checks on that exact HEAD.
python tools/taskctl.py evidence CAP-XX.SXX.TXX --agent <agent> --from artifacts/evidence/CAP-XX.SXX.TXX.json
python tools/taskctl.py submit CAP-XX.SXX.TXX --agent <agent> --note "<summary>"
python tools/taskctl.py review CAP-XX.SXX.TXX --reviewer <reviewer> --result approved --note "<disposition>"
```

`block`, `renew`, `evidence`, `submit`, capability pause/renew/submit, and slice
submit verify lease ownership. There is no campaign-override claim flag. Release
gates cannot be approved twice or while their preceding wave contains an
incomplete task. Every mutation validates the prospective ledger before an
atomic compare-and-swap replacement; stale writers and failed replacements do
not overwrite the prior file.

Start/resume/claim metadata is bound to the actual current Git branch, full
`HEAD`, and canonical worktree. Evidence is a single-read snapshot whose base,
branch, commit ancestry, exact changed-file scope, named passing checks, complete
criterion map, empty unverified list, clean tracked/untracked worktree, digest,
and logical uniqueness are checked again on later validation. Implementation or
campaign owners cannot review their own task, slice, or capability. Approved
release gates remain semantically tied to a fully DONE preceding wave.

Follow-up evidence must use `supersedes.path`, set `baseCommit` to that prior
attachment's commit, and declare the complete incremental diff. Completion does
not excuse non-empty `unverifiedItems`. The only exception is the explicitly
marked `pre-exact-evidence-hosted-ci-residual-v1` migration for four pinned
CAP-00.S03 records; their paths, commits, hashes, task IDs, and exact hosted-CI
residual text are fixed and the marker is invalid everywhere else.

## Decision requests

When a decision or approval is required:

1. regenerate the review site;
2. print its `file://` and repository-relative capability links;
3. state whether recommendations are already decision-complete;
4. identify only unresolved or changed items;
5. explain that Other requires a brief description and detailed rationale; and
6. do not treat exported feedback as implementation approval.

## Continuous execution

After approval, continue through tasks, slice integration, independent slice review, and the next approved slice. Ordinary test failure, debugging, implementation refinement inside the approved envelope, or use of a documented fallback is not a human stop point.

The approval is valid only when it covers the capability packet and every slice
plan at one immutable commit. A capability campaign is the durable execution
unit: resume it after ordinary process/session interruption and continue through
all slices and capability-wide production qualification. Never reinterpret a
slice boundary as a request for another routine approval.

Before claiming, use `taskctl next` and `taskctl show` to identify the active
campaign's next `READY` task. Permitted scope is its objective, deliverables,
criteria, dependencies, profile/platform, and governing sources. Required checks
are its declared verification commands plus changed-path checks. Completion is
commit-bound criterion evidence, submission, required review, clean tested local
main integration, and continuation to the next eligible task or slice gate.

## Evidence

A completion claim must link every criterion to a named test, report, artifact, source commit, and reviewer outcome. If evidence is incomplete, keep the task or slice in progress/review; do not mark it done with persuasive prose.

After required checks pass and the bounded work is committed, fast-forward the
tested branch into local `main`. Keep any pending review or approval state
pending in the backlog: local Git integration is not a substitute for a workflow
transition. Stop on branch divergence and never push without explicit authority.

## Independent review

Use a fresh agent context when possible. The reviewer challenges scope, architecture, tests, denial/failure/recovery paths, privacy/security, rights, UI contracts, platform behavior, hidden TODOs, and whether evidence actually proves the acceptance criteria.

## Experience work

Do not change the UI reference after implementation merely to make code appear conformant. Update and approve the reference first for intentional changes. Restoration to the approved reference may proceed without a new reference ID.
