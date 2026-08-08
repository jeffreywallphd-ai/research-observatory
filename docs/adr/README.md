# Architecture decision records

ADRs record material architecture choices and the evidence behind them. Accepted
ADRs supersede the Systems Design only within their explicit decision scope.
Backlog state remains authoritative for task execution and completion.

## Create a record

Use the next stable four-digit identifier and link at least one governed task:

```powershell
python tools/adr_new.py --repo . --id ADR-0002 --title "Decision title" --task CAP-XX.SXX.TXX --affected "packages/contracts/**"
```

The command creates a Proposed Markdown record and adds it to `index.json` in
one operation. Complete every template section, run the ADR checker, and obtain
the review required by the linked task. Never reuse an identifier or edit an
Accepted record to reverse its decision; create a superseding ADR.

## Decision states

| State | Meaning |
|---|---|
| `Proposed` | Under review; may accompany a protected-path change but is not architecture authority until accepted. |
| `Accepted` | Governs the stated scope and may supersede the baseline or earlier ADRs. |
| `Rejected` | Retained as decision history; never architecture authority. |
| `Superseded` | Historical accepted decision replaced by the ADR named in `superseded_by`. |

State transitions require an indexed record update, linked task evidence, and
review. `Superseded` requires a valid successor; an Accepted successor lists the
older record in `supersedes`.

## Review and protected interfaces

`architecture-protected-paths.json` lists source and documentation paths whose
semantics define module boundaries or stable interfaces. CI must run:

```powershell
python tools/adr_check.py --repo . --base <merge-base> --head HEAD
```

For each changed protected path, the same change set must contain an indexed
Proposed or Accepted ADR whose `affected_paths` pattern covers that path and
whose `linked_tasks` exist in the backlog. An unindexed ADR, a stale index entry,
a nonexistent task link, or an uncovered protected path fails closed.

Use `TEMPLATE.md` when reviewing the required context, candidates, decision,
consequences, compatibility/security/profile impact, rollback, and verification.
[`ADR-0001`](ADR-0001-machine-checked-architecture-boundaries.md) is the initial
task-linked example and records the boundary contract installed by CAP-00.S02.
