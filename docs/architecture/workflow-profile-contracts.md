# Governed workflow-profile contracts

ADR-0026 governs the portable scholarly-path and navigation-state boundary. The
Draft 2020-12 schema in `packages/contracts/workflow-profile/` is the
language-neutral authority. Its deterministic generator binds the exact schema,
the approved Academic Minimal 1.5 workflow catalog, and the resulting profile
catalog hashes into matching immutable TypeScript and Python decoders.

## Governed catalog

The catalog contains exactly the fourteen profiles in
`RO-UI-ACADEMIC-MINIMAL-1.5`. Every profile records its own exact source hash,
version/revision, expected outputs, linear or revisitable cycle policy, ordered
primary page-contract stages, optionality, and complete-workbench support
policy. All registered supporting tools remain accessible and return to the
current primary stage.

The experience catalog does not specify stage-level checkpoint authority.
Consequently, the generated v1 contract records checkpoint state as `unknown`
with an explicit rationale. A later implementation cannot infer researcher
approval or completion from route order, a page visit, or an analytical job.
Changing profile content requires a new reviewed experience catalog and
governed reference, followed by an explicit contract/catalog version.

## Project selection and navigation state

`ProjectWorkflowSelection` binds one project, a full exact accepted Research
Intent reference, and an exact governed profile reference. It is an append-only
revision with a stable aggregate ID and distinct UUIDv7 revision ID: the first
revision has no predecessor; each later revision retains the aggregate ID,
names its immediate predecessor, and includes the matching impact preview. The
preview names affected prior stage-state revisions and their retain, map, stale,
review, or explicit drop disposition. It does not mutate those prior records.

`WorkflowStageState` has the same stable aggregate/distinct revision identity
shape and binds the exact selection and profile independently of
executor history. Its state vocabulary covers not-started, available, current,
in-progress, attention-required, blocked, completed, stale, and skipped with
rationale. Completed, attention, and stale states carry their corresponding
evidence or cause. A `passNumber` represents revisiting a cyclical stage without
erasing earlier passes. Primary state binds an approved stage/page contract;
supporting state binds an explicit return to a valid primary stage.

This contract contains no workflow run, logical job, physical attempt, queue,
worker lease, executor, database, filesystem, URL, credential, or inline
research-content field. ADR-0025 remains authoritative for analytical execution
and restartable job history. Later CAP-03.S06 service work may project both
boundaries, but cannot collapse them into one state machine.

## Profile migration and compatibility

`WorkflowProfileMigration` names exact source and target profile references,
preserves history, requires human acceptance, and covers every source stage
exactly once. Retain/map dispositions must name a valid target stage; unmapped
work remains explicit through stale, review, or reasoned drop dispositions.
Project selection changes use the same semantics in a concrete impact preview.

No workflow-profile records predate v1, so T01 creates no SQLite migration.
CAP-03.S06.T02-T04 own persistence, atomic commands/events, process-restart
proof, and desktop navigation. Once stored records exist, compatibility requires
an exact old reader or reviewed migration fixture; selection and stage history
is never rewritten in place.
