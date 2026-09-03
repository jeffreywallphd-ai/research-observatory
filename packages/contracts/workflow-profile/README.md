# Governed workflow-profile contract

`workflow-profile.schema.json` is the Draft 2020-12 authority for the exact
approved scholarly workflow profiles, immutable project selections, navigation
stage state, and explicit profile migration.

Run `node generate.mjs` after changing the schema, a runtime template, or the
governed source catalogs. Run `node generate.mjs --check` to prove the committed
catalog fixtures plus TypeScript and Python decoders are current. Generation
fails unless `design/ui-reference/WORKFLOW_CATALOG.json` remains the exact
approved `RO-UI-ACADEMIC-MINIMAL-1.5` input and all fourteen profile identities
remain present in governed order.

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

A supporting-stage record is decoded only with the explicit current primary
stage state. Its return reference binds that state's aggregate/revision/hash and
project/selection/profile/stage context; arbitrary support aliases and
substituted returns fail closed. CAP-03.S06.T02-T04 own service lookup,
persistence, commands, progress, and desktop navigation; this task supplies the
portable contract and fixtures.
