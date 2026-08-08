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
python tools/taskctl.py --file planning/backlog.yaml capability start CAP-XX --agent <agent> --branch <branch> --base-sha <sha> --profile LOC --platform windows-x64
python tools/taskctl.py --file planning/backlog.yaml status
```

Use repository-specific `taskctl` subcommands for claim, evidence, review, and transition as defined by the installed tool and `planning/README.md`.

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

## Evidence

A completion claim must link every criterion to a named test, report, artifact, source commit, and reviewer outcome. If evidence is incomplete, keep the task or slice in progress/review; do not mark it done with persuasive prose.

## Independent review

Use a fresh agent context when possible. The reviewer challenges scope, architecture, tests, denial/failure/recovery paths, privacy/security, rights, UI contracts, platform behavior, hidden TODOs, and whether evidence actually proves the acceptance criteria.

## Experience work

Do not change the UI reference after implementation merely to make code appear conformant. Update and approve the reference first for intentional changes. Restoration to the approved reference may proceed without a new reference ID.
