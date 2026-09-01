# Portable workflow contract

`workflow-contract.schema.json` is the Draft 2020-12 authority for immutable
workflow definitions, restart-reconstructable execution snapshots, and the
legacy operation projection bridge.

Run `node generate.mjs` after changing the schema or either runtime template.
Run `node generate.mjs --check` to prove that `generated.ts` and
`services/core-api/src/research_observatory_core/workflow_contracts.py` bind the
exact schema bytes.

The contract intentionally contains no SQLite/Temporal types, paths, URLs,
arbitrary commands, inline research content, credentials, or provider objects.
CAP-03.S04.T02 owns durable SQLite persistence and real worker restart. The v1
fixtures prove exact definition reuse across executor profiles, retry and
checkpoint history, immutable artifact disposition, auditable human decision,
unique transition identities, and the existing `op-*` compatibility
projection. Human request/claim authority and allowed dispositions are bound
to the exact history and definition; the legacy sequence is bound to the
workflow snapshot before its ETag is accepted.
