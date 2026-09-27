# CAP-04.S03.T01 — conservative identifiers and exact reconciliation

Claim base: `e09d313fdb86ff6ea260f04a56fdaf7063198a57`. The unchanged approved
W2 packet at `c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`, CAP-04.S03 section 9.1,
and accepted ADR-0013/0024/0025/0027 govern this implementation. Both task
dependencies are DONE and CAP-04.S02 has independent slice approval.

## Material acceptance closure

| Boundary | Intended behavior and prospective proof |
|---|---|
| Identifier equivalence | Versioned, typed DOI, PMID, arXiv, ISBN, ORCID, provider-ID, URL and title normalization preserves observed strings. Table-driven tests exercise wrappers, checksums, ASCII-only DOI case folding, reserved URL characters, arXiv versions, leading zeros and malformed Unicode/control input. Syntax validity never claims registry verification. |
| Identity and conflict | Exact reconciliation distinguishes scholarly work identifiers from person, organization, container and heuristic title keys. A unique compatible exact match links assertions; multiple matches, conflicting IDs, reassignment observations and invalid IDs retain explicit review flags. Titles and ORCID cannot silently merge Works. Tests challenge transitive bridges, namespace substitution and deterministic order. |
| Source precedence | Human-accepted corrections remain distinct from raw imported/provider assertions. No provider ranking silently declares disputed metadata true. All competing values and exact source addresses survive, with field selection and reasons inspectable. Source bytes, IDs and previous decisions remain immutable. |
| Current authority | Core resolves exact import-manifest/member or connector-page/ordinal addresses in the current project; callers cannot submit trusted provider values or grants. Current inspect/store/derive/index rights and project/Intent/privacy restrictions guard writes and replay/read. Cross-project, replaced revision, revoked rights, closed project and stale-source substitutions fail closed. |
| Durable aggregate boundary | Canonical UUIDv7 record identities/revisions reuse existing repositories and append-only source links. Publication, exact-ID lookup, idempotency, provenance/outbox and material dependencies commit together. A conflicting retry or injected failure leaves no partial canonical change. Restart recovers the same result and audit links. |
| Compatibility and migration | Preserve the exact committed schema-v13 predecessor before any additive schema change. Test upgrade, rejection of invalid predecessor state, immutable source rows, rollback/verified backup and protected database restart. Do not approximate an old schema using new DDL. |
| Real principal | A focused production-composition test must resolve actual retained import and connector sources through Core authority and the real project database/object store, then reconcile and reopen. Pure matcher tests alone do not qualify persistence, rights or application wiring. |
| Experience | T01 introduces the Core/domain contract and persistence path; CAP-04.S03.T02 owns the approved reconciliation review UI. No governed page, workflow, style or navigation is changed by this task. Public API/schema consumers receive explicit bounded states and immutable IDs. |
| Evidence | Select normalization, exact-engine, public-contract, affected repository/migration/service and real-boundary checks plus affected static/schema/architecture checks. Bind final passing results to a committed candidate. Full repository/profile and cross-capability qualification remain the S01–S03 checkpoint and fresh Wave exit obligations. |

First tests precede product edits where practical. Negative cases include invalid
checksums, Unicode DOI collisions, person-ID/work-ID substitution, conflicting
verified identifiers, source preservation, denied current authority, duplicate
command collision, concurrent publication, rollback and process restart.

The implementation must not add fuzzy scoring, merge/split adjudication, version
graph semantics, remote identity lookup, inferred permissions or new infrastructure.
Those are either later approved tasks or explicit non-goals. Long-running/batch
work must use the existing durable workflow fabric; a bounded single-source
transaction is not a replacement scheduler. Read-only independent preflight is
requested for the identity, current-authority and migration boundaries. No
mandatory new gate has been demonstrated.

## Implementation closure and proof limits

The independent read-only preflight identified the exact source address, entity
scope, full-candidate conflict, current local-action rights and genuine predecessor
boundaries. Those observations are incorporated into the source resolvers,
normalizer, transactional repository and tests. Syntax validity remains separate
from registry verification; no registry lookup or invented verification is added.

Protected source reads append access audit facts using their own connection.
Resolving them while holding a writer would deadlock. The lifecycle fence therefore
spans a source-resolution phase and a subsequent writer transaction that rechecks
the complete candidate set against the resolved snapshot. A newly encountered
concurrent source fails closed without partial publication. Concurrent tests retry
that bounded conflict and prove convergence to one Work.

The exact v13 schema and a populated synthetic committed-import database were
frozen before DDL changes. Migration tests restore those literal objects/rows,
verify their fingerprints, preserve source/audit facts, and exercise rollback,
verified encrypted backup and reopen. Existing predecessor migration expectations
advance their target to v14 while retaining their old source fingerprints, data
and failure assertions. SQL formatting changes to the new uncommitted DDL require
recomputing only the new target's actual schema/profile fingerprints.

Primary DOI syntax review corrected initial development assumptions about prefix
length/subdivision and suffix spaces. The normalizer and regression cases preserve
these valid distinctions; malformed controls remain rejected. Original source
representations and accepted corrections stay independently inspectable across
DOI-list, RIS, BibTeX, CSL-JSON and CSV handoffs.

`tests/reconciliation` covers normalization/conflicts, actual parser projections,
portable JSON/API contracts, real canonical publication, concurrency, atomic
failpoints, migration and Windows production composition. The production test uses
real DPAPI/SQLCipher and durable acquisition workers with synthetic provider HTTP,
then shuts down and recreates the application session, reopens the project and
checks replay, disputed fields and revoked contributor rights. It does not claim
a separately spawned OS process, live external API qualification or review UI
coverage. CAP-04.S03.T02/T03 and the S01–S03 checkpoint retain their approved scope.

Qualifying checks will run afresh against the committed candidate. Development
failures remain in local logs; they are not passing evidence or independent review.
