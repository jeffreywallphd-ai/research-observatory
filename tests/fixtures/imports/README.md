# Import handoff fixture

`public-handoff-v1.json` contains only the public `manifest`, `members` and
`rights` objects from the synthetic frozen-Core qualification result
`artifacts/tmp/import-frozen-windows-c5bzzq30/result.json` (SHA256
`1df5d398477eb6f8a8eaa615fa4882e397f2fe37344103b7649bf3a60ad66373`,
candidate `c959ccdcd836966501922ec533b9a31ea45987f7`). The values are exact
observations, not invented scholarly records. No account, path, credential,
runtime session or private bibliography is included.

The wire contracts are `ImportManifestView`, `ImportManifestPage` and
`ImportRights` in `packages/contracts/core-api/openapi.json`; the generated
client supplies bound manifest/member reads. The portable ingestion IR remains
`packages/contracts/ingestion/import-record.schema.json`. Public member pages
provide source revision IDs and decisions, not bulk source payloads. Core
consumers use the existing repository ports to resolve protected source data;
they must not read private tables or infer filesystem layout.

`tests/contracts/test_import_public_handoff.py` is a deliberately small downstream
consumer example. With JSON Schema alone it checks this complete three-row page
against its manifest, preserves two source revisions and the excluded header's
warning, and carries parser/mapping/source provenance plus the rights snapshot.
It rejects partial or mismatched membership. General consumers paginate through
the generated client's bounded API; this example does not implement a paginator.

A source record is not a reconciled Work or Version. CAP-04.S03 must preserve
these IDs when linking later results; CAP-04.S04 can retain the manifest decision
and discovery/rights lineage. Historical rights are not a current permission
grant: current project and action authorization must be checked again before
inspection, derivation, export or other use. Unknown permissions remain unknown.
