---
id: ADR-0060
title: Bind protected lexical generations to accepted storage authority
status: Proposed
date: 2026-10-16
deciders: []
linked_tasks:
  - CAP-06.S01.T02
decision_scope: Documentary CAP-06.S01.T02 implementation under Accepted ADR-0057; no new architecture authority.
affected_paths:
  - services/core-api/src/research_observatory_core/derivative_keys.py
  - services/core-api/src/research_observatory_core/ports/derivative_keys.py
  - services/core-api/src/research_observatory_core/ports/credential_store.py
  - services/core-api/src/research_observatory_core/lexical_catalog_repository.py
  - services/core-api/src/research_observatory_core/lexical_index_io.py
  - services/core-api/src/research_observatory_core/lexical_index_store.py
  - services/core-api/src/research_observatory_core/lexical_source_repository.py
  - services/core-api/src/research_observatory_core/lexical_index_repository.py
  - services/core-api/src/research_observatory_core/search/canonical_schema.py
  - services/core-api/src/research_observatory_core/search/compiler.py
  - services/core-api/src/research_observatory_core/migrations/runner.py
  - services/core-api/src/research_observatory_core/migrations/versions/v0029_lexical_index_generations.py
  - services/core-api/src/research_observatory_core/storage.py
  - services/core-api/src/research_observatory_core/object_store.py
  - services/core-api/src/research_observatory_core/document_revision_repository.py
  - services/core-api/src/research_observatory_core/rights_repository.py
  - packages/contracts/security/credential-store-profile.schema.json
  - packages/contracts/security/credential-store-profile.v1.json
  - packages/contracts/storage/sqlite-migration-recovery.schema.json
  - packages/contracts/storage/sqlite-profile.schema.json
  - packages/contracts/storage/sqlite-profile.v1.json
  - quality-scope.json
  - tools/architecture_check.py
supersedes: []
superseded_by: null
---

# ADR-0060: Bind protected lexical generations to accepted storage authority

## Context

Approved CAP-06.S01.T02 requires incremental lawful metadata/document indexing,
safe rebuild and interruption recovery in the actual protected FTS5 build.
Accepted ADR-0057 selects separate protected derivatives, purpose-scoped keys,
canonical change authority and validated shadow generations. ADR-0012 governs
portable package file classes; ADR-0020 governs protected canonical storage;
ADR-0029 preserves immutable document and source identity.

This Proposed record documents concrete implementation under that authority.
It does not amend the frozen W3 packet, Accepted ADRs, permissions, experience
reference or release criteria. ADR-0059's pure query contract remains unchanged.

## Candidates

1. Store FTS rows in the canonical database. This reduces cross-store coordination,
   but couples replaceable projections to authoritative research history and
   contradicts the selected separate derivative lifecycle.
2. Use a separate generation-scoped SQLCipher database with its own text mirror
   and external-content FTS5 table, plus canonical content-free generation and
   source-change records. This needs explicit checkpoints, recovery and fencing,
   while preserving authoritative research and rebuildable storage separation.

## Decision

Implement candidate2 through the existing Core data-adapter boundary. The five
exact root adapters are `lexical_catalog_repository`, `lexical_source_repository`,
`lexical_index_repository`, `lexical_index_store` and `lexical_index_io`. Register
only those basenames in the existing architecture checker; preserve its detection
logic and deny their import by ordinary business modules and ports. Query
grammar/contracts/compiler remain storage independent. Core commands are usable
without a renderer; T03 owns HTTP, ranked results, snippets and UI composition.

Schema29 additively appends immutable source changes, generation identities,
events and selections, plus expiring owner/epoch-fenced writer leases. It starts
from the exact populated schema28 predecessor after a verified protected backup;
earlier cells, objects and migration history remain intact. Source outbox and
change sequence publication share one canonical transaction. Exact null-revision
index-controller events are excluded to prevent feedback; scholarly changes are
not suppressed. Rights recheck completion publishes content-free change authority
so lawful regrant can be indexed after completed propagation.

Derivative keys bind project, generation, purpose, canonical-key version and
package lifecycle. Ordinary leases require current authority. A private retirement
helper can use only the exact retained key version after authenticating the held
main-file identity against canonical Retired metadata, repeatedly checking current
Native/actor/nonselection authority. It returns no content or reusable store.
Reader drain and owned DELETE eligibility precede revocation; post-revocation
interruption can retry owned cleanup without recreating a key.

The protected mirror preserves complete accepted normalized projections, exact
source/document/projection IDs and codepoint ranges. Current source-specific
rights are checked before reading and again before promotion/delivery. Complete
authorized items remain together in bounded query batches, preserving Boolean
semantics across rows. Incremental private commits and canonical acknowledgements
are separate transactions; uncertain gaps require validation or a fresh shadow.
Promotion atomically rechecks source watermark, current authority, cancellation,
integrity, physical ownership and expected selected predecessor.

## Consequences

Private text stays in protected objects/derivatives; WAL and temporary storage
retain the selected protection and lifetime controls. Derivative files stay
excluded from portable backup/export. Rotation, relocation and restore rebuild
under fresh authority. Restricted or stale inputs cannot become current query
results even while physical cleanup is pending.

Separate stores require explicit restart, acknowledgement-gap and cleanup
handling. A failed shadow preserves the earlier valid selection. A valid new
selection with obsolete cleanup pending remains Ready and reports that pending
work. Schema rollback is restoration of a verified predecessor backup through
existing recovery authority, never a destructive downgrade or history rewrite.

Windows x64 remains the current qualification platform. No model, AI-mode,
headless launcher, new deployment, dependency, worker read grant, egress or spend
authority is introduced. Existing API operations remain available. The portable
storage and credential profiles, affected guide and quality inventory reflect
the additive implementation; historical contracts/fixtures remain preserved.

## Verification

`tests/search/test_index_migration.py` checks the frozen populated protected v28
fixture, exact preservation, verified backup, material fault rollback/retry and
actual DPAPI key handling. Catalog/service/source tests challenge stale owners,
substituted rows/files, denied text, regrant, cancelled promotion, incremental
acknowledgement gaps, fresh/rebuilt equivalence and retirement retry.

`tests/search/test_protected_lexical_store.py` and the owned crash child exercise
actual SQLCipher FTS5, encrypted main/WAL, integrity, interruption replay and
guarded path cleanup. `test_windows_derivative_index.py` and
`test_native_index_service.py` exercise current-user DPAPI, Native lifecycle,
reopen, relocation and portable recovery exclusion without the UI. Synthetic
parser/source/capacity fixtures retain their explicit limits.

`tests/foundation/test_architecture_check.py` verifies root-only registration and
business/port/nested denial. Fresh affected architecture, ADR, quality,
storage/credential contracts, earlier migration and document/rights compatibility,
API generation and availability checks accompany exact-candidate evidence and
expanded independent review. Development observations are not qualification;
slice performance/UI and full Wave qualification remain separate obligations.

## Task links

- `CAP-06.S01.T02`
