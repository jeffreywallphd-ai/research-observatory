# Governed workflow-profile contract

`workflow-profile.schema.json` is the Draft 2020-12 authority for the exact
approved scholarly workflow profiles, immutable project selections, navigation
stage state, and explicit profile migration.

Run `node generate.mjs` after changing the schema, a runtime template, or the
governed source catalogs. Run `node generate.mjs --check` to prove the committed
catalog fixtures plus TypeScript and Python decoders are current. Generation
fails unless `source/academic-minimal-1.5/WORKFLOW_CATALOG.json` remains the exact
approved `RO-UI-ACADEMIC-MINIMAL-1.5` input and all fourteen profile identities
remain present in governed order.

The repository-owned catalog/page-contract snapshots retain their original
approval provenance in `SOURCE_AUTHORITY.json`. Fixed hashes in the generator,
not replaceable hashes learned from that record, determine valid inputs.
Generation and runtime need no Git or active presentation directory. Academic
Minimal 1.6 changes presentation only: the exact-package
`presentation-compatibility.json` witness and conformance checks permit only
root reference ID/version substitutions. The independent control checkpoint
binds that witness before presentation consumers change. Semantic catalog,
selection, intent and navigation identities remain 1.5; no migration occurs.

The contract is intentionally separate from executor-neutral workflow history.
A profile describes the primary scholarly path and supporting-tool return
policy; a stage-state record describes navigation and research-gate status. It
does not contain logical jobs, physical attempts, queues, checkpoints, worker
leases, executor settings, database types, paths, URLs, research content, or
credentials.

Changing a selected profile creates an immediate immutable selection revision
and Research Intent revision, a bound impact preview, and an exact immutable
migration/acceptance reference. Migration declares exact from/to profiles and
intents, a disposition for every prior stage, preserved history, and a human
acceptance decision. `retain` keeps the same governed stage, `map` names a
different governed stage, and stale/review/drop dispositions have no target.
The parent selection remains the immediate selection predecessor even when its
intent reference predates intervening same-profile intent revisions; the
migration itself must bind the actual consecutive prior and target intent
revisions. T02 persistence resolves the migration and acceptance IDs/hashes.

A supporting-stage record is decoded only with the explicit current primary
stage state. Its return reference binds that state's aggregate/revision/hash and
project/selection/profile/stage context; arbitrary support aliases and
substituted returns fail closed. CAP-03.S06.T02-T04 own service lookup,
persistence, commands, progress, and desktop navigation; this task supplies the
portable contract and fixtures.
