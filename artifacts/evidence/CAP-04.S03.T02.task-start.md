# CAP-04.S03.T02 — duplicate candidates and reversible review

Claim base: `691205f48cf8ee80b323a9971413f7da1d0608e1` on the existing W2
campaign. CAP-04.S03.T01 is DONE with independent approval and local integration.
Authority: the immutable W2 approval at
`c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`, the
[approved S03 plan](../../planning/slice-plans/CAP-04/CAP-04.S03-canonical-work-version-and-identity-reconciliation.md#92-cap-04s03t02---implement-probabilistic-duplicate-candidate-generation-and-review),
ADR-0013/0014/0024/0025/0027, and RO-UI-ACADEMIC-MINIMAL-1.7 ingestion
canonicalization/duplicate-decision regions. This worksheet records implementation
proof obligations; it does not change approved scope or acceptance.

## Current boundary and non-goals

T01 provides source-authorized exact reconciliation, immutable source assertions,
canonical Work revisions, original receipts and current-head inspection in schema
14. Retained import and connector inputs exist, but recent previews/jobs are not
an exhaustive accepted-source inventory. There is no reconciliation batch worker,
current merge membership/alias projection, native route admission or review UI.
Freeze an actual populated v14 predecessor before changing its DDL.

Probabilistic similarity only proposes human review. No automatic fuzzy merge,
invented source value/gold label, external query, cloud service, alternate identity
store, or T03 version/retraction graph is included. Preserve all old receipts,
identities, accepted decisions, source values and adverse evidence.

## Acceptance closure

| Material boundary | Observable result and planned proof |
|---|---|
| C1: labeled duplicate retrieval | Before scoring or tuning, freeze the licensed DBLP-ACM archive, exact member hashes/counts/decoding, provenance/attribution, component-disjoint development and qualification split, precision >=0.90 and recall >=0.95, and explicit pair/derived-cluster denominators. Authenticate fixtures offline. Report false positive/negative pairs and cluster overmerge/fragmentation separately; do not treat derived pair components as independent multi-source labels. |
| Candidate semantics | Deterministic bounded blocking/ranking uses title, authors, year, venue, pages, abstract and typed identifiers. Preserve missing/conflicting feature state, source/assertion/Work revisions, normalizer/scoring/config versions and contributions. Cache features by immutable source revision. Test ordering, absent data, title changes, homonyms, conflicting identifiers and synthetic three-record false bridges; no probability or automatic adjudication claim. |
| Current identity | Merge/split appends complete current source-membership and alias revisions; exact matching and inspection resolve current membership without rewriting old receipts. Test merge A/B, split, restart and fresh exact input for split-out B; reject alias cycles, stale or substituted predecessors and incomplete/overlapping partitions. |
| Unassigned assertions and historical aliases | Preserve T01 review-required/null-Work assertions in inventory and candidates. Human assignment binds the exact assertion/address and expected unassigned state. A split must explicitly route every affected inbound alias, including transitive aliases whose historical members span partitions; no survivor/order inference. Revision-qualified history bypasses current routing. Prove this with the additional actual populated v14 two-Work/unassigned-conflict fixture and post-split exact/retry tests. |
| Decision authority | Commands bind actor, action, exact compared Work/membership/decision revisions, candidate evidence/config, survivor, complete partition, alias plan and conflict dispositions. Current project/Intent/privacy and every contributor's historical/current rights apply to inspection, candidates, decisions and identical retries. Changed command-ID reuse conflicts; denial adds no canonical facts. |
| Atomic dependencies | Append same-aggregate Work revisions for surviving and retired identities with provenance, outbox and dependency-impact intent in one canonical transaction. Existing impact items deny fresh-only consumption before propagation advances; visible pending/stale state must be honest. Test injected publication failures, idempotent replay, restart during propagation and no nested-writer or post-commit crash gap. |
| Existing affected inputs | New exact/review outputs reject assertions, source revisions and prior human decisions already marked affected, including through bounded provenance manifests. Historical inspection and identical retry retain the original receipt while inspection exposes the review requirement. The read-only dependency preflight reproduced false-fresh output inheritance; add the regression before remediation. |
| Durable operation | Accepted-source inventory binds exact retained import/connector revisions, job/attempt and completion-event/outbox authority. A missing or substituted acceptance join must deny enumeration rather than hide a row or report false exhaustion. Long-running enumeration/reconciliation/candidate generation uses the existing durable queue and authority/cancellation guards. Test cancellation before publication, restart, bounded continuation, changed authority and partial failure without a false-complete result. |
| Compatibility | Freeze literal v14 schema plus actual published import and exact-reconciliation rows before new DDL. Prove additive migration, unchanged historical receipts/FKs, verified backup, tamper denial and rollback at material seams; preserve the older v13 fixture. |
| Real principal boundary | Exercise actual protected Windows project storage, Core, durable worker and generated client/native admission across accepted import/retained connector -> reconciliation -> candidate -> human merge -> split -> restart. Doubles support fault tests but cannot establish this boundary. |
| Governed journey | Systematic/living-review ingestion follows Source/Search and returns toward Corpus/Screening. Use approved side-by-side source assertions, identifiers, feature contributions, conflicts, affected objects and reversible merge/split decisions with shared tokens. Prove actual durable outcome, keyboard/focus/announcements, light/dark states, stale responses, cancel/return context and clearing on lock/project change. Future steps stay honest about availability. |
| C2/C3 and evidence truth | Criterion-linked domain/repository/migration/API/generated-client/native/UI/real-runtime checks, contract generation, affected type/lint/architecture/inventory/build/UI checks and documentation establish the changed boundary. Freeze committed candidate and selected inputs during qualification; independent expanded review precedes completion/integration. |

## First tests and verification selection

Begin with frozen-fixture authentication and predecessor capture, then failing
candidate/missing-feature/false-bridge and merge/split/current-route tests before
product implementation. Add publication fault, stale-predecessor, retry and rights
denial checks as the exact adapter seam is established. The final real-principal
and UI tests require the new wiring; they will be written alongside it and run
fresh at the committed candidate, not represented by unit doubles.

Read-only adversarial preflight by `agent:/root/w2_t03_review` is incorporated in
the current-membership, same-aggregate dependency, inventory, frozen predecessor
and real-boundary rows. Its advice is not an independent task disposition.
The subsequent read-only identity preflight by `agent:/root/w2_c02_review`
adds explicit unassigned and transitive-alias obligations. Historical membership
backfill follows predecessor chains/numeric revisions, never UUID order. The
original populated v14 fixture remains unchanged; an additional fixture captures
two Works and an unassigned identifier bridge before any new DDL.

The accepted-output preflight reproduced two false-exhaustion paths with two
successful jobs sharing one canonical output: substitution of one completion
event, and substitution of one attempt. The immediate cause was filtering or
trusting joined rows before authenticating the exact job's completion binding.
Add both corruption regressions before remediation; restoration of fixture
trigger DDL keeps normal schema validation active. This remains advisory review,
not a task disposition.

The owner-inventory advisory reproduced an accepted job for a newly excluded
record paired with the older included manifest from the same preview. Generic
queue acceptance proves canonical output publication, not import-specific command
meaning. The owner must bind the accepted attempt's preparation and complete
effective import identity to its stored request and returned manifest. Add the
changed-inclusion substitution regression and preserve legitimate manifest reuse
for identical scientific identity across distinct requests or draft revisions.
The same advisory found that descendant validation omitted executor equality:
an otherwise valid child snapshot could change from local to server. Preserve
the full executor binding across each edge, alongside definition, Intent, policy,
configuration and exact parent job/run. Add the substitution regression first.

The batch-publication advisory (`agent:/root/w2_t03_review`, F-BATCH-01)
identified a one-level provenance packing limit: 4,097 material leaves became
65 manifest inputs, still exceeding the common 64-input envelope and therefore
failing below the advertised batch bound. Repeat packing with separate material
and historical branches. A structural adapter-probe regression traverses 4,097
material plus 65 historical leaves and checks that none are lost or promoted;
real smaller batch and review tests cover canonical transaction integration.
This is not a large-corpus performance measurement. The advisory also identified
preparation lease exhaustion; a real queue test advances two source reads by
20 seconds each and verifies live renewal and explicit failed-job continuation.
Worker integration must still prove complete enumeration against the bound
snapshot, including omitted members and addresses arriving after the boundary.

Worker-lifecycle advisory by `agent:/root/w2_c02_review` added three concrete
integration obligations. A stale Task Center cancellation must be rejected before
rolling back provisional lease renewals; a valid cancellation persists independently
of the expired pre-writer lease and converges through existing queue recovery.
Task Center refresh must obtain a current committed revision while publication
holds the lifecycle fence. The read-only projection pins that already-authorized
fence; it does not introduce a mutation authority. Finally, project close, failed
open cleanup and shutdown must signal every composed worker before draining any
of them, including an active import with idle reconciliation. Retained failing
API tests preceded these fixes. Additional cases cover close before registration,
failed drain retaining the open project, exact Intent changes after enumeration,
saved request/enqueue failure across restart, and accepted commit/lost response.
These are development proofs, not a task disposition or protected-runtime/UI
qualification. The full generated client/native and protected Windows journey
remains required.

The candidate/API advisory by `agent:/root/w2_t03_review` identified two missed
projection boundaries. Batch polling must read job state and accepted output in
one read-only snapshot while publication owns the writer; a writer transaction
in that path blocks the stop mutex. Add a real status-poll-then-cancel regression.
Historical candidate pages must also identify their authenticated frozen inventory
and disclose newly accepted inputs outside it. Add an unrelated accepted import
after publication and verify that historical scores remain unchanged while the
inventory comparison changes. These findings do not change the approved scope.

The client/native advisory by `agent:/root/w2_t03_review` reproduced acceptance
of an unrelated returned Work for a two-partition split when only command and
plan digests matched. Require exact returned membership, survivor/predecessor
identity, new-identity separation, alias destinations and dependency-run count.
It also reproduced rejection of a valid 20,000-affected/20,000-unknown impact
preview at the client's/native transport's smaller response bound. Add both
regressions first; align inspection/context/preview response allowances with
Core's bounded 4 MiB inspection contract while retaining other route limits.

The UI advisory by `agent:/root/w2_c02_review` found that Back and a failed
parent refresh could discard a reply-lost decision's exact retry command;
changing a displayed contributor left the original pair's score ambiguously
associated with the new pair; and identical title/provider labels prevented
identifying split members. Add browser regressions for both navigation paths,
score/source association and distinct immutable source labels with explicit
preview partitions. Preserve the original scoring evidence and same-command
retry. These restore the approved decision and recovery contract.

The first real browser/Core review-context request returned 422: FastAPI parses
JSON arrays as Python lists, while strict tuple containers rejected the valid
wire representation before the route ran. Permit array-to-immutable-tuple
conversion only on the affected bounded containers; retain strict scalar types,
unknown-field denial and full partition validation. Keep the failed browser
run and add malformed-container/scalar/authority denial checks.

The actual browser/current-rights regression additionally requires the parent
candidate evidence to clear when a child comparison receives a denial. Clearing
only comparison fields leaves a score and review action from revoked evidence.
Change the effective record rights (not an overridden batch default), establish
Core's 403, then verify both regions clear without publishing a decision.

Full unchanged deployment profiles are deferred to the S03 checkpoint/Wave
qualification; they are not waived. Existing historical type errors and Windows
symlink-token skips remain explicit Wave obligations. No mandatory new approval
gate has been discovered. Approved implementation adds no supplemental refactoring
budget allocation; any later unrelated refactoring requires its accounting route.

The first complete task-range quality pass at `3998d9c6` found three new tables
using the prohibited generic `payload_json` name and five new triggers missing
from the expected inventory. Preserve the existing scalar-storage assertions.
Use dedicated bounded feature, candidate-set and explanation documents, with
direct SQL rejection of unknown/missing fields, wrong types and exceeded bounds;
refresh only unreleased v15 authority and preserve frozen v14 bytes. The same
pass exposed missing build-schema inventory, documentary ADR/UI evidence and
test annotations. These are acceptance closure, not scope changes.

Independent pre-submission review additionally reproduced exact-link dependency
impacts left pending because worker continuation selected human-review runs only.
Authenticate exact-command-owned runs, preserve current invalidation authority,
and prove dependent stale-state publication through worker restart. Keep the
failed reproduction and distinguish it from the already-passing review-origin
propagation test.

The same independent review reproduced a second recovery failure: material graph
growth after publication invalidates the frozen propagation preview. Preserve the
engine's snapshot check. Authenticate each owner-bound root and append a fresh,
same-semantics continuation, its predecessor checkpoint, and predecessor
cancellation atomically. Prove restart, partial propagation, failed publication,
lost acknowledgement, substituted ownership and bounded repeated graph growth.
Old impact items and stale causes must continue denying fresh-only consumption.

Incremental continuation review found that graph growth could mask corruption of
the saved preview, run authority, item manifest or checkpoint. Add graph-independent
validation of saved run authority and audit history before considering recovery,
including each historical continuation. A corruption-plus-real-growth regression
must deny without publishing a child or changing the predecessor's state.
The recovery discriminator itself also needs protection: seal every original and
continuation run's complete typed snapshot, including graph/preview digests and
bounds. First reproduce a substituted graph digest without actual growth, then
require integrity denial. Preserve the legacy impact engine's hash contract.

Final incremental review confirmed that a removed material edge can turn a
pending effect into an empty completed child, while the original item continues
denying fresh reads. The missed boundary is retention of the predecessor's
effects across re-preview. Reproduce removal and non-material weakening before
repair; require every predecessor output/kind/disposition/confidence/review duty
in the new preview before appending any continuation or cancellation. Additional
effects are allowed; lost or weakened effects deny recovery without mutations.
