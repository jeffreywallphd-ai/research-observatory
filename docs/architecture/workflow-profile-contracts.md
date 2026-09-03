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
names its immediate predecessor, binds an immediate new revision of the same
Research Intent aggregate, and includes both the matching impact preview and an
immutable accepted-migration reference. That reference carries exact source and
target profiles, prior and target intents, migration identity/content hash, and
the human acceptance decision identity/content hash. The preview names affected
prior stage-state revisions and their retain, map, stale, review, or explicit
drop disposition. It does not mutate those prior records.

Selection lineage and Research Intent lineage are independent append-only
chains. The parent selection is the immediately preceding *selection* revision
and may therefore cite an older same-profile intent after intervening intent-only
revisions. On a profile change, the accepted migration—not the parent selection—
binds the actual immediately preceding and target Research Intent revisions.
Persistence must resolve the cited migration and human decision by their exact
IDs and content hashes.

`WorkflowStageState` has the same stable aggregate/distinct revision identity
shape and binds the exact selection and profile independently of
executor history. Its state vocabulary covers not-started, available, current,
in-progress, attention-required, blocked, completed, stale, and skipped with
rationale. Completed, attention, and stale states carry their corresponding
evidence or cause. A `passNumber` represents revisiting a cyclical stage without
erasing earlier passes. Primary state binds an approved stage/page contract;
supporting state binds an explicit return reference to the exact current primary
stage-state aggregate, revision, content hash, project, selection, profile,
stage/page, pass, and current status. Portable validation receives that current
primary state explicitly and rejects an omitted or one-field-substituted return.
Supporting state keys are deterministically derived from their registered page
contract, so an arbitrary alias cannot acquire navigation authority.

This contract contains no workflow run, logical job, physical attempt, queue,
worker lease, executor, database, filesystem, URL, credential, or inline
research-content field. ADR-0025 remains authoritative for analytical execution
and restartable job history. Later CAP-03.S06 service work may project both
boundaries, but cannot collapse them into one state machine.

## Profile migration and compatibility

`WorkflowProfileMigration` names exact source and target profile references,
preserves history, requires human acceptance, and covers every source stage
exactly once. `retain` means the same stage key and page contract in the target;
`map` means an explicit different valid target; `mark-stale`,
`requires-review`, and `drop-with-rationale` preserve the prior record without a
target. A migration binds consecutive revisions of one Research Intent and a
human `accepted` decision. Project selection changes use the same disposition
semantics in a concrete impact preview and reference the exact accepted
migration; a service may look up the bound migration hash but cannot substitute
its authority.

No workflow-profile records predate v1, so T01 creates no SQLite migration.
CAP-03.S06.T02-T04 own persistence, atomic commands/events, process-restart
proof, and desktop navigation. Once stored records exist, compatibility requires
an exact old reader or reviewed migration fixture; selection and stage history
is never rewritten in place.
