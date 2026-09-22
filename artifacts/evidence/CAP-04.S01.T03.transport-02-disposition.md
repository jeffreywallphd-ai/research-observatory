# CAP-04.S01.T03 transport-02 independent disposition

**CHANGES REQUESTED for this bounded ordering-remediation/renderer increment.**
Reviewer: `w2_document_packet_preflight`.
Candidate: `9cade6ef75bce5e6437bdc76a7fe8bddb041959e`.
Base: `c75b3e1f0b5ef0635aa3472f7a44f4ed0a8121b7`.
This is not task completion or actual native/principal/large-input qualification.

## T03-TRANSPORT-01-F01 — CLOSED

Latest request and manifest lookup now use internal insertion order (`rowid`)
on the existing append-only relations, not random UUID magnitude or caller time.
The two new service regressions exercise out-of-order UUIDs and reopened
discovery for both paths, while retaining access to the earlier immutable rows.
The implementation note preserves their separate initial RED results (1.185 and
2.852 seconds) and subsequent two-case PASS (4.094 seconds). No migration,
identity rewrite or change to request/manifest authorization accompanies this
fix. The original transport-01 adverse disposition remains intact.

## T03-TRANSPORT-02-F01 — P2: preview cancellation falsely denies a completed import

Location: `apps/desktop/src/app/ImportReviewPane.tsx:138`
(`cancel`; candidate line number). This previously preview-only announcement is
now reachable after the newly integrated canonical commit flow.

After an import succeeds, the researcher can select Cancel this preview and
Confirm cancellation. The live region announces: "Preview cancelled. Its
incomplete source and audit remain retained; no canonical import was published."
The accepted canonical records and manifest remain present. The final clause is
therefore false, and the source need not be incomplete either.

Independent reproduction used the exact built renderer/client with the existing
real Core/storage/worker fixture and explicit native doubles. The existing
two-theme lost-reply/replay/navigation journey was extended only in memory with
post-commit preview cancellation and a synthetic-database retention query.
The probe exited 0: one case in 7.613 seconds. It confirmed one retained canonical
source and one retained manifest alongside the quoted false announcement. No
source/test file was edited and no ordinary user project was accessed.

Material criterion: evidence-first truthful durable outcomes and the approved
reference's safe, non-color, accessible state announcements. Cancelling a
preview cannot be represented as proof that no canonical import happened;
cancellation may also arrive after a commit has won its publication race.

Smallest closure: replace the unconditional no-publication/incomplete-source
claim with a truthful statement that preview cancellation preserves retained
source/audit and any already committed canonical records/manifests. Describe
pending cancellation only as requested unless its durable terminal outcome is
known. Add the post-commit cancellation case to the existing real renderer
regression and assert both retained canonical state and the live-region message.
No optional visual redesign or broader control change is needed.

## Incremental coverage and limits

Reviewed the exact renderer, parent wiring, ordering change, regression tests
and evidence against the approved 1.7 shared controls/accessibility and affected
import-review page contracts. The new pane uses explicit review/confirmation;
discovery does not start work. Preparation/start use the Core-provided request
identity, and uncertain replies direct the researcher to durable status rather
than claiming rollback. Scientific reuse follows the returned original manifest
preview. Async results are guarded by live/generation ownership, while parent
preview/revision keys dispose superseded panes. Existing shared buttons, panels,
status labels, tables and focus tokens are reused. Escape returns from the inline
confirmation to its initiating control after React updates the disabled state.
No further material blocker was confirmed in this bounded review.

Owner-reported fresh exact-candidate checks: eight API/ordering cases PASS in
16.752 seconds; built renderer/real-Core journey PASS in 7.651 seconds in both
themes with lost reply, replay, navigation and Escape; TypeScript typecheck,
lint and product build PASS. The final owner renderer run had clean teardown.
The independent probe above adds the missing integration boundary, not a full
suite replay. Existing exploratory focus and fixture failures remain recorded
in the implementation evidence.

The rights-scan paging complexity and publication guard/lease work remain
explicitly unfinished T03 scope. Native host/chooser doubles are not evidence
of actual native execution, protected-principal behavior, packaging or large
manifest navigation. This disposition neither waives nor claims those criteria.
