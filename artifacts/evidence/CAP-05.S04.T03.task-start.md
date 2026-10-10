# CAP-05.S04.T03 — Rights-aware Reader actions

Claim base: `f27ab65fc54197143f07b7b92a87b5b70e2368e4`; owner
`codex-w2-implementation`, existing `codex/w2-implementation` W2 campaign.
CAP-05.S04.T02 is DONE, independently approved and integrated into local main.

Authority: [approved slice §9.3](../../planning/slice-plans/CAP-05/CAP-05.S04-source-viewer-and-evidence-inspection-experience.md),
[ADR-0029](../../docs/adr/ADR-0029-preserve-document-revisions-and-mediate-source-viewing.md),
existing protected source/copy rights, accepted Intent/privacy/session boundaries,
and approved Reader experience reference RO-UI-ACADEMIC-MINIMAL-1.9. The separate
explicit permitted-use review remains in the Reader provenance region; it records
source permission, then a separate action revalidates it. Neither publication nor
a cached decision executes an action. Read-only independent preflight by
`agent:/root/reader_anchor_review` found this bounded implementation within the
approved experience; no new amendment or automation framework work is planned.

## Acceptance closure

| Material boundary | Product behavior and proof |
|---|---|
| Restricted and unknown sources | Every copy/print/quotation export/anchor annotation export/original external-open path uses fixed Core purposes and exact per-copy policy. Button, keyboard, DOM/context-menu, browser print and direct Native paths cannot export unapproved text. Real protected repository/API tests plus mounted interaction and actual Native proof. |
| Explicit researcher permission | Native resolves the retained source assertion, candidate copy and address from opaque selectors. A distinct confirmed review uses trusted human, accepted Intent/hash, privacy fingerprint, exact predecessor and semantic command identity. Retry precedes ID/time minting; unrelated assertions, IDs and recorded/expiry times remain exact. Test stale predecessor, replay, unknown replacement, explicit denial, expiry, disputes, propagation pending and unrelated assertor. |
| Executing destination | Only an otherwise current `rights-further-authority-required` local export proceeds through the action-specific Native destination. Other non-allow results remain unavailable. Generic project-export, remote egress, entitlement and source-observation authority remain unchanged. Planned proofs cover real local output, isolated clipboard, local PDF printer and an owned inert external consumer. Windows printing is limited to the qualified local Microsoft PDF stream target; unsupported queues are unavailable before source text enters them. |
| Quotation identity and limits | Core resolves a retained exact anchor and returns only its exact quotation, original and normalized revisions, source assertion, Work/version, anchor revision, codepoint range, canonical citation label and policy basis. Context/prefix/suffix are not exported. Extraction stays unverified. The existing 2048-codepoint selection cap is a technical limit, not an invented quantitative license allowance. Annotation export contains selected anchor identifiers/geometry/confidence without surrounding or quoted text. |
| Original external opening | Explicit source export permission and a Native-selected local destination/application are required. Stream the original through existing bounded verified ranges; verify the complete original digest. No hidden Viewer plaintext cache, renderer path/URL/program/actor/grant, provider or network route. The authorized local deliverable remains outside project protection and is disclosed as such. |
| Fresh authority | Source, anchor, rights, trusted human, Intent, privacy, lock, Native window and session are rechecked after read/dialog and before publication. Changed authority prevents publication; historical decisions are not grants. Test changes during materialization and dialogs, denial and source substitutions. Core authorization and Native publication remain separate fences. |
| Cross-layer permission contract | Native and renderer decode the actual six-field `RightsUse` wire value, including explicit null provider/region/share-group fields. Fixed local uses reject a remote provider, region or share group. A real Native/Core check exposed the initial three-field fixture mismatch; API, Native and renderer regressions cover the exact contract. |
| Failure/recovery and privacy | Cancel, lost connection, denied rights, unavailable printer/application and failed write retain source/history. Hold create-new outputs, reject overwrite/reparse/network destinations, verify digest and clean owned incomplete plaintext on close/termination. Denial audit stores safe IDs/codes/hashes, never selected text or paths. No researcher clipboard inspection/save/restore or physical paper printing in tests. Actual Windows PDF callbacks are held during lock/cancellation to prove that flags do not release live ownership; sealed streams reject late writes. |
| Resource ownership | Reuse Viewer admission and bounded readers, keep issued unknown-drain ownership until physical closure, bound policy/quote/response allocations, and avoid whole-source copies. Lock/unmount denies stale UI completion. No 8/16 GiB model or hardware-tier runs. |
| Governed journey | Existing Reader regions, exact selected Work/version return, explicit source rights review, action-specific destination/plaintext disclosure, busy/denied/unavailable/cancel/error/retry states, keyboard/focus and accessible labels. Controls never silently grant permissions or send data on review. Check both primary Reader and alternate structured inspection. |

First tests are real encrypted canonical repository cases for missing permission,
explicit allowed quotation with identifiers, preserved assertions/retry, separate
action scopes and content-free denial. Add changed-policy delivery and material
OS publication/cancellation regressions as those adapters are implemented.
Synthetic accepted IR fixtures are labelled as authored synthetic structure, not
fresh parser/model execution.

Selected task coverage: affected Core/private API, contract schema, Native unit
and actual principal checks, mounted Reader journey, packaging/wiring and relevant
quality/experience checks on a committed candidate. Full profiles, cross-task
integration and fresh matrix remain at slice/Wave qualification. CAP-05.S04.T01's
approved 3-second latency evidence is retained; no further tuning or 20-open
replay. The accepted parser overage is retained without tuning. No claim of 2/3
GiB support, minimum hardware qualification, installer or Wave release follows
from these tests.

Native reference constraints: [clipboard ownership](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setclipboarddata),
[private window stations](https://learn.microsoft.com/en-us/windows/win32/winstation/about-window-stations-and-desktops),
[print confirmation](https://learn.microsoft.com/en-us/windows/win32/api/commdlg/ns-commdlg-printdlgw),
[held print stream](https://learn.microsoft.com/en-us/windows/win32/api/documenttarget/nf-documenttarget-iprintdocumentpackagetargetfactory-createdocumentpackagetargetforprintjob),
and [held-file deletion](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-setfileinformationbyhandle).
These documents inform implementation; they are not execution evidence.

Mandatory gate discovered at start: none. Task, slice, Wave and human release
gates remain required; this worksheet makes no completion claim.

Development preflight found a physical-driver call could hold lifecycle mutexes
and delay Lock. The supported local PDF path prepares output through a bounded
held `IStream`, then rechecks Core permission before publishing the file. No
printer pathname is handed to the driver. Unsupported physical queues fail
closed; no USB/paper-printer qualification is claimed. This is the smallest
local print implementation within the existing task, not new automation work.

The private clipboard proof currently has a platform prerequisite: Windows
denies named private window-station creation to the current non-elevated test
principal. The failed setup attempts remain in ignored development logs and
performed no clipboard access. A test against the researcher's shared clipboard
is not an alternative. Qualifying evidence remains pending.
