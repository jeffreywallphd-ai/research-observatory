# Register the new protected-import Python module

Predecessor: `341566cb6b4f2e591e4bacc60ee19e33d6d8d89a`.
Implementer: `agent:/root`. Risk tier: 2, limited to inventory metadata.

Append exactly
`services/core-api/src/research_observatory_core/ingestion/protected_import_profiles.py`
to `quality-scope.json`. This module was introduced by the predecessor under
the approved W2.C35.T01 product scope. The existing complete-discovery checker
requires its registration. Preserve all 734 previous entries in their original
order, every metadata field and all six governed roots. Do not change the
checker, its settings, any framework implementation, product code or UI authority.

The source commit contains only this note and that single inventory addition.
Use the existing bounded control-only evidence and independent-review route;
this is no new ECR or controller. Necessary finite procedural authority is
recorded in `W2.completion-preauthorization-20261014-01.md`.

Selected checks compare the actual committed inventory with its predecessor,
confirm the exact two-file source boundary and registered source blob, and call
the unchanged `quality_check.load_scope` against actual governed discovery.
Require exactly 735 unique governed Python files, including the new module.
Preserve any adverse result. Product typing, regression, scale and packaged
boundary checks remain separate pending work; inventory registration is not a
task, Wave or release approval. Independent review precedes local integration.
