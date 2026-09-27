# CAP-04.S03.T03 — Work versions and sourced status relationships

Claim base: `0738c2543db85af8189bd0948393698b04662de6`, after the approved
CAP-04.S03.T02 R02 disposition and local-main integration. The existing W2
campaign and immutable approval at `c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`
remain authority; readiness passed at task start.

## Authority and bounds

The authoritative backlog criteria are: (C1) users identify a preferred citable
version and see warnings, with correction/retraction marking dependent outputs
for review while retaining history; (C2) behavioral and material boundary tests;
(C3) relevant contracts, migrations, fixtures, documentation and audit behavior
without unrelated expansion. Approved slice CAP-04.S03 sections 4–9.3 and
CAP-04 architecture sections 5–9 govern the implementation. Accepted ADRs
0013/0014/0024/0025/0027 govern identity, storage, provenance, recovery and
scholarly authority. Systems Design 9.1–9.6 and 10.1–10.2 supply remaining
architecture. Reference `RO-UI-ACADEMIC-MINIMAL-1.7` governs the existing
Ingestion Review version-cluster and Retractions & corrections regions, shared
tokens, semantic states, keyboard/focus and workflow return behavior.

No later capability, live provider request, new provider, new ontology engine,
new experience reference, automatic scholarly adjudication, destructive history
replacement or refactoring is planned. Preferred citable status is a human
decision, never a rights grant or removal of a warning. Unreported dates and
unresolved source relationships remain explicit.

## Current boundary and exact predecessor

T02 supplies canonical source assertions, sealed Work membership and alias
revisions, human merge/split/assignment, candidate evidence, and authenticated
dependency-impact recovery. It has no WorkVersion authority yet. Version 15
has 70 tables and schema fingerprint
`6361c684264358e94c19c90bd67f6f2d47eda21c107d1012a3f86b5cf2faf949`.
Its profile fingerprint is
`1db7b16d30ea6c1b629ba935c68a542129855391ab69246f62696623d067cd37`.
Before product edits, the actual approved adapter produced literal schema and
populated synthetic fixtures, including cached candidate evidence, split/merge
decisions, an exact-source impact, and a 100-of-102 processed impact followed by
graph growth and a pending continuation. These fixtures test historical database
compatibility; their synthetic source resolver is not real-principal evidence.
No previous migration or fixture bytes may be changed to manufacture compatibility.

## Material acceptance closure

| Boundary | Intended behavior and proof |
|---|---|
| C1 version identity | Canonical Work, WorkVersion, source assertion, relation and human decision have distinct identities and exact revisions. Cover the preprint/accepted/VOR and notice taxonomy, strict DTOs, external IDs including arXiv suffixes, and no implicit chronology or similarity links. |
| C1 sourced relationship | Directed endpoints bind exact version revisions and retained assertion/field-selector/value digest evidence, human rationale and date precision. Positive correction/retraction/EOC cases plus self/cross-project/stale/substituted endpoint and evidence denial; competing assertions stay visible. |
| C1 preference | Explicit preferred-version decision binds current Work membership, selected revision, status snapshot and prior decision. No default survivor/newest preference; merge/split or changed evidence requires renewed review. A preferred retracted version still shows its warning. |
| Work membership | Every new Work head remains sealed. A version follows its exact source membership, not a current alias substituted for historical identity. A manifestation spanning split partitions is explicitly unresolved until a new human classification; retain old version/decision/relation revisions. Exercise merge → version → split → reopen, aliases and competing preferences. |
| C1/C3 atomic impacts | Publish version/status/preference, canonical provenance/outbox, explicitly owned impact intent and immediate fresh-input denial together. Fault each publication seam. Preserve unrelated outputs, old revisions and original command receipts. Test pending/partial impacts, graph growth, continuation checkpoint/owner/semantics, cancellation and restart. |
| Authority | Core resolves current project, accepted Intent, privacy and all supporting-source action rights for inspection, preview, commit and identical retry. Client identities/digests are preconditions only. Deny foreign sources, stale previews, changed command/actor and rights changes without partial publication. |
| C3 migration | Add version 16 through backed migration. Restore literal populated v15 schema/rows, preserve every predecessor row and fingerprint in backup, fail at each material step, retry and reopen. Exercise SQLCipher as well as plaintext test storage, and resume retained candidate/impact state. |
| Real principal | Extend the existing port, Core API, generated client and admitted native bridge. Fresh Windows supervised Core + SQLCipher/DPAPI + actual renderer path must exercise a version decision and warning, durable reread/restart and denial. Mocks and screenshots alone do not close this row. |
| Governed experience | Existing Ingestion Review region exposes versions even without a duplicate pair, source evidence, preference, warnings and safe review outcome. Preserve current workflow/return context, focus and drafts on ordinary recoverable failure; clear protected state on lock/close and discard late results. Test both themes, keyboard traversal and accessible text states. |
| C2/C3 handoff and truth | Portable contract fixture carries identities, exact revisions, sourced relations, status and preference without adapter imports. Each evidence claim names the case that actually executes it; synthetic/advisory/real-boundary evidence and deferred coverage remain distinct. |

## Sequence and selected coverage

First add literal predecessor characterization, a failing v15→v16 migration case,
and failing strict date/identity/evidence contract cases. Then implement the
normalized version authority and atomic repository behavior, followed by service,
wire/native/client and existing reference regions. Add focused fault, recovery,
rights and source-membership cases before their respective product changes where
practical. Real-principal tests require the integrated path and follow wiring.

Select reconciliation tests, directly affected migration/shared-contract and
dependency-impact checks, generated-contract/client checks, focused renderer and
native boundary checks, affected Python/Rust/TypeScript quality, architecture,
fixture/inventory/UI governance and planning validation. Full service/data/graph
profiles remain slice/checkpoint/Wave coverage unless a concrete wider failure
requires them earlier. Slice performance and fresh full W2 qualification remain
separate obligations; inherited skips and debt are not waived by this task.

Read-only independent task-start preflight from `/root/w2_t03_review` informed
the identity, membership, preference, owner-bound recovery and exact predecessor
rows. It found no new approval gate. This is an implementation worksheet, not a
new approved plan or task disposition.

## Advisory preflight follow-through

The bounded implementation preflight found that the first proposed v16 subtype
bindings admitted an existing Work genesis as a WorkVersion, and response DTOs
admitted self-predecessors and inconsistent placement states. These are missing
identity-invariant checks, not changed scope. Add direct canonical-subtype attacks
and impossible-response tests before tightening the bindings. Also bind preference
impacts to the actual prior decision kind and exact published owner endpoints,
and exercise JSON array decoding. The preflight is advisory, not approval; the
initial exploratory failures and later regressions remain distinguishable.

A second bounded preflight reproduced two preference failures: restoring original
membership after merge/split silently reactivated an old choice, and consumers
depending only on the preference remained fresh after membership changed. The
missing invariant was publication lineage and its material dependency. Regressions
now require explicit reselection after membership history changes and immediate
consumer denial followed by restart recovery. Preference publication follows its
new Work head and materially depends on it, preventing a cycle while preserving
old preference receipts. These observations remain advisory and exploratory until
the stable committed candidate is independently reviewed.

## Stale commit recovery finding

Read-only review of `13e1038eeb44fdd5b1a074afc065e6f885f12ec2` found that a
definitively refused stale version commit entered the same unresolved retry state
as a lost reply. The missed C1/C2 recovery row is: a proved unpublished stale
command releases its retry lock, retains the researcher's draft, and requires a
fresh context and preview; an ambiguous conflict still preserves the exact saved
command. The immediate cause was a generic conflict response with no authoritative
non-publication distinction. Add actual Core/API and renderer regressions before
repairing that distinction, including an authentic generic conflict after a saved
commit. A successful refresh must preserve valid draft choices and explicitly
invalidate missing source/endpoints rather than silently substitute them.
The same row includes a Work retired by a concurrent merge: the pre-publication
refusal must release retry, and the inventory must permit clearing stale selected
IDs even when those Works no longer appear on the current page.
