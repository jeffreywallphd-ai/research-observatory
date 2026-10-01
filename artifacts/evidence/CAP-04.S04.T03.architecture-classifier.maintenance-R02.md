# CAP-04.S04.T03 architecture-classifier maintenance for R02

Predecessor: `722481ddbfcd4b54d4ee712f5c258c2e3a42c227` (clean tracked checkout before this correction). Risk tier: high for data-boundary enforcement. This is a bounded verification-control repair under `docs/automation/workflow-efficiency.md#bounded-maintenance`; it changes no approved product behavior, storage authority, migration guarantee, architecture contract, or prior review finding.

| Exact predecessor path | SHA-256 |
|---|---|
| `tools/architecture_check.py` | `f0a135cde8dfef863154ab2e6260261aeb75894668b00a11b3ed15b4a5ceda3b` |
| `tests/foundation/test_architecture_check.py` | `23f7d333c4a4ab362fff1225293d4d15d9f0fe4c05707d80d0b0924266e61b56` |
| `services/core-api/src/research_observatory_core/corpus_source_projection.py` | `2969497cf4f406c1a5dd23e5686816fbece991f449defafb6ec7378d3eb173eb` |

At that predecessor, `python tools/architecture_check.py` exits 1 because it calls the new root-level SQL projection helper a business module and rejects its `sqlite3` import and `execute` calls. The intended control delta adds only `corpus_source_projection` to the existing root repository-adapter classifier. This admits the exact root helper while retaining SQL-denial for a nested file of the same name and concrete-adapter import denial from business and port modules. The regression failed against the predecessor classification before the control edit and passed afterward. No new control revision or refactoring is introduced.

Selected proof: the 13-case architecture unit suite, the repository architecture checker, and affected Python format/lint/type checks passed. The repository quality check and independent R02 review remain required before commit-bound evidence or integration. Reverting this correction restores the false-positive gate failure; it has no data-recovery effect.
