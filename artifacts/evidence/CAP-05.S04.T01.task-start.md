# CAP-05.S04.T01 — secure local source viewer

Claim base: `1bd33a6ba180487b239e3315e302b6db6aaea123`.
Authority: frozen W2 at `c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`,
CAP-05.S04 sections 4, 7–12 and 19, accepted ADR-0016/0017/0029,
and RO-UI-ACADEMIC-MINIMAL-1.9 with its inherited Reader/workflow contract.
Taskctl selected this READY task after both dependency tasks were DONE.

| Material boundary | Implementation and planned proof |
|---|---|
| Controlled source access | Original and normalized revision identities remain distinct. Core resolves exact immutable attachment/copy/project/source binding, current native session, human Intent/privacy and per-copy inspect permission; substituted IDs and revoked authority deny delivery. Derived structured text retains its separate derive requirement. |
| Integrity and cancellation | Optional trusted cancellation checkpoints during whole-source authentication and bounded prefix reads. No bytes before final authentication. Cancellation rolls back/closes without quarantining healthy ciphertext; existing corruption/key-loss behavior stays intact. Real encrypted-object tests plus maximum-source cancellation/concurrent writer proof. |
| Admission and fairness | Source <=128MiB, range <=1MiB, one active read/project, eight queued operations. Exact duplicate coalescing retains each requester's cancellation/authority. Cancel obsolete work before admission; close the writer before delivery and permit metadata writes between ranges. |
| Native transport | Fixed typed viewer commands, bounded byte responses and exact range/source correlation; native root/session/token/window/generation remain trusted. Lock/close denies late delivery and drains owned work. Real renderer/native/Core integration, beyond unit doubles. |
| Inert source rendering | Locally pinned PDF.js worker, no document URL, active scripting/XFA/forms/actions/attachments or remote assets. Structured text is inert. Hostile/malformed/oversized fixtures and no-egress checks. |
| Viewer memory and latency | Virtualize visible pages/thumbnails, cancel stale renders and account for worker source allocation, transfers, surfaces and hostile decoding within 256MiB. The approved [LT01 supplement](CAP-05.S04.T01.latency-target-amendment-01.adopted.json) changes only representative 10MiB/50-page cold/warm p95 to <=3.0s over >=20 opens. Preserve 128MiB/500-page stress and cancellation/lease release <=1s. The original 1.5s criterion remains immutable history and a later optimization goal. |
| Experience and handoff | Approved Reader toolbar/outline/source/inspector and selected Work/Version return context; page navigation, zoom, text, sections, search and restricted external links. Keyboard/focus, reflow and both themes. T02 owns durable deep links/multiple highlights; T03 owns the rights-aware action broker. |
| Compatibility and evidence | Additive port cancellation, unchanged encryption/migration format and historical revisions. Focused affected tests first, exact committed candidate qualification and expanded independent review; S02–S04 checkpoint and fresh Wave matrix remain later gates. |

Read-only independent design preflight by `agent:/root/s04_t01_design_preflight`
found no implementation approval gate. Its material cancellation classification,
inspect-only, revision-mapping, transport, delivery and memory risks are included
above. It is advisory, not a task approval.

Owner direction remains binding: no 8GiB/16GiB tier qualification variants on
this host, no automation-framework source work after A05, and no investigation
or rerun of the accepted parser timing overage. The existing minimum-tier
qualification claim remains unproven. The resource/model successor packet must
be concrete and approved before dependent authority changes; it does not block
unaffected viewer implementation. No completion, hardware-tier qualification or
release claim is made by this worksheet.

## Current checkpoint and adverse evidence

The first actual Core/worker maximum-source diagnostic denied the SDK's ninth
concurrent range. The pinned worker now caps groups and serializes range-reader
admission; the 128MiB/500-page diagnostic reached the first and last page and
searched the last page. A separate cancellation advisory identified shared SDK
demands surviving operation cancellation. The viewer now retires that decoder
generation and drains admitted readers before replacement. Actual worker
operation-cancellation/recovery qualification remains required.

Worktree checks passed: 33 focused real encrypted-object/private API/authority/
admission/fairness tests, 20 viewer/SDK tests, three mounted Reader checks,
affected lint, schemas and strict typing. The product assembles 195 fixed local
artifacts, including pinned CMaps/fonts, worker modules and license notices.
The updated 10MiB/50-page exploratory Core/worker open took about1.214 seconds.
These are advisory observations, not exact-candidate qualification, native/Wry
proof, minimum-tier qualification, a complete/peak footprint or20-open p95.

The unchanged shared product verifier rejects the new artifact inventory,
the Reader route and the stale1.8 reference selector. Its security helper rejects
the local-only worker/asset CSP against its earlier literal allowlist. EX01 is
not a generic later-task exemption. An attempted uncommitted shared-verifier
edit was withdrawn byte-for-byte; the patch and adverse diagnostics remain in
ignored task output. No framework source change is included. A bounded,
source-free verification-method proposal was initially considered. Fresh
independent authority review by `agent:/root/s04_method_gate_readiness` found
that proposal unnecessary: automation-guide section8.1 and the approved S04
plan make profile commands candidate coverage, not mandatory helper verdicts.
Ordinary task-owned proof may establish the current package/approved Reader/
local-only CSP while preserving adverse helper results and all material
functional/security/platform/UX/performance obligations. This does not infer
a generic EX01 exemption or waive any slice/Wave gate. The block validator
completed its atomic publication before cancellation could occur. Its actual
receipt is preserved; ordinary taskctl reopen committed successfully, retaining
the original base and owner. The task is IN_PROGRESS and the campaign remains
ACTIVE; no pause or new owner decision is requested.

The actual pinned-worker uncached-operation probe passed render and thumbnail
cancellation but timed out on search: terminating the decoder did not settle
the main-thread SDK text reader. The adverse run is retained at
`artifacts/tmp/CAP-05.S04.T01.worker-cancel-01.log`. Search now owns the public
SDK stream reader and cancels it during decoder retirement before worker
termination. Required regression proof includes settling the old search,
denying replacement byte admission until drain, and successful exact-source
reopen, rather than only ignoring a late UI update.
The corrected worktree passed all six actual-worker cases (search, render and
thumbnail while loading text or an uncached page), nine ownership unit tests
and strict typing. The actual-worker byte port is explicitly synthetic; this
does not qualify native transport, complete resource footprint or p95 latency.

## Candidate cancellation finding CRA01-F01

Independent candidate review at `1941bfa06bab014a7aca58c00275e87035ebc55d`
found that transport settlement was mistaken for physical reader drain. The
range pool could release a cancelled last waiter before its callback closed the
stream/transaction; Native discarded the cancel result and the renderer's
`allSettled` erased failures. This is a product defect within the existing task,
not an authority change or a request for another amendment.

The missed acceptance row is actual owner termination before replacement.
Regression proof holds real encrypted authentication after transport cancellation,
checks explicit pending denial at the one-second boundary, and permits replacement
only after acknowledged physical close. A coalesced live follower must survive.
Early/late registration and lost acknowledgements must never imply success.
Native range settlement must carry exact request-bound terminal disposition;
renderer unknown-drain failure remains latched after pending removal, retains its
range reservation until closure is established, and denies replacement. These
regressions are being added before remediation; no closure is claimed here.

## October 9 execution checkpoint and allocation finding

The partial machine record at `CAP-05.S04.T01.partial-observations-01.json`
preserves fourteen fresh Core checks at candidate
`0c89d757f856140d3d6993ffae65a13bacf4d228` and the actual Native results.
The manifest-assembled maximum-source handler test passed exact terminal drain,
an independent preserved writer commit and exact fresh tail retry in20.77ms.
The actual product renderer/Native/Core diagnostic reached page500, searched,
navigated499/500 and returned to its selected Work/version. Its kernel job peak
was623398912 committed bytes across the owned Native/Core/WebView descendants.
These facts do not establish representative percentile, minimum-tier,
immutable-package qualification or the separate256MiB owned-buffer budget.
Five descendants remained immediately after Native exit; owned job cleanup
terminated them. No normal complete shutdown or in-flight-close claim is made.

Read-only independent allocation assessment identified a missed acceptance row:
bounded text/outline responses did not bound their Core artifact loading.
`_accepted` loads a complete accepted artifact, then revalidates its normalized
result, raw artifacts and manifests. A64MiB artifact can overlap its reader
buffer, slice and returned-byte copies while the PDF worker remains live.
This is a product resource defect inside T01's approved budget, not new scope.
Before remediation, add failure tests for allocation admission before protected
reads, cumulative charge across nested artifacts/manifests, unchanged general
revision readers, original availability after denied text, and bounded successful
text/outline with the actual protected adapter. Preserve full-source integrity,
current derivative rights and all acceptance validation; do not bypass `_accepted`
or silently reduce the parser's general64MiB artifact contract.

Actual pinned-decoder product tests cover authored active actions/links/widgets,
malformed page-tree denial and retry, oversized surface denial, compressed-content
expansion denial and fresh recovery. The first attempt's two fixture failures
(default empty canvas dimensions) remain retained; the corrected fixture declares
zero-sized initial surfaces. Worktree results are not exact-candidate approval.
The3s product target is explicitly selected by the owner; LT01 direct-record
procedure adoption remains pending. No repeated value decision is requested.

The allocation remediation uses a Viewer-only cumulative protected-artifact
ledger, preserving ordinary revision readers and all protected validation.
The source-sized decoder allowance frees room for structured inspection of
ordinary sources without changing parser limits. A shared window ledger and
reference-counted Core allowance keep old calls visible during retry/replacement.
Native structured deadline/disconnect failures retain admission as unknown drain.
Independent narrow assessment identified the outline denial-mapping and
structured transport-lifetime gaps; both are addressed in this product unit.

Worktree checks retained under `artifacts/tmp/CAP-05.S04.T01.artifact-*` include
twenty-one Core tests (one outline-status failure, followed by its passing focused
regression), twenty-six renderer tests, strict TypeScript, nine Native command
tests, six mounted Reader journeys and four actual pinned-decoder cases.
Sandbox-only fixture/cache failures are retained separately. The broad desktop
lint also reports two pre-existing unrelated source literals; it is not a clean
repository/profile claim. These results select affected product risks and do not
qualify a committed candidate, approve T01, adopt LT01 or complete W2.

## Approved LT01 adoption and current resume boundary

The owner explicitly approved the reviewed LT01 procedure exception on October 9.
The immutable [owner record](CAP-05.S04.T01.latency-target-amendment-01.owner-approval.json)
binds the proposal and independent readiness review. The authoritative
[criterion supplement](CAP-05.S04.T01.latency-target-amendment-01.adopted.json)
sets the representative first-page target to 3.0 seconds; it preserves the same
fixture, cold/warm p95 methodology, minimum repetitions, full authentication and
actual renderer/gateway/Native/Core measurement. Earlier pending-adoption notes
above remain historical observations, not the current authority state.

The current partial proof is retained in
[partial-observations-02](CAP-05.S04.T01.partial-observations-02.json), including
actual Native accepted text/outline, denial/resource/retry, maximum-source
cancellation and in-flight terminal-generation revocation, plus shipping-renderer
maximum-document use. Formal latency/resource qualification and independent T01
disposition remain required. Resume the same owned task through ordinary taskctl;
do not claim again or alter its original identity/base/dependencies. No task,
slice, Wave, minimum-hardware or release completion follows from LT01 adoption.

## Final composition acceptance row

Criterion 3 includes the existing Core dependency direction: the application
service receives its local read-adapter composition from `main`; it does not
select concrete revision or viewer adapters. The fresh architecture
characterization reported that missed dependency along with three checker
classification limitations. The correction injects one required composed
repository factory while retaining the same current actor, guard, occurrence
time, native-store reuse, protected context and delivery checks. The real Core
fixture composes those same adapters explicitly.

Final evidence must replay actual protected-source, rights, cancellation,
coalesced-follower and writer boundaries after this wiring correction. The
typed cancellation callback retains its default-bound exact group. Production
typing and all changed Python lint/format are selected; exploratory broad test
typing diagnostics remain failures rather than claims of functional defects.
The unchanged architecture helper's new-adapter inventory and relative-import
limitations remain adverse evidence. Substantive task-owned proof must resolve
the actual port import, adapter roles and required service injection without
changing the helper, shared quality scope or architecture authority.
