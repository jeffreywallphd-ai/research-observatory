# CAP-05.S03.T02 — passage anchors

Claim base: `45ea077cfd651802c265e09679f3843156a00c5a`.
The active W2 campaign owns this task; `CAP-05.S03.T01` is DONE and independently
approved. Authority is the approved S03 slice section 9.2, accepted ADR-0029,
ADR-0013/0024 canonical identity and provenance, existing protected object and
current native-session/Intent/rights boundaries, and the inherited Document
Reader reference in `RO-UI-ACADEMIC-MINIMAL-1.9`.

| Material boundary | Planned proof |
|---|---|
| Clicking the same anchor after restart identifies the exact accepted revision and passage. | Real SQLCipher/encrypted-object reopen plus renderer selection/highlight; later accepted heads do not move historical anchors. |
| Structural IDs, source revision, project, projection, span and quote agree. | Wrong revision/node/project/range, repeated quote, changed command and corruption cases fail explicitly; no fuzzy reassignment. |
| NFC Unicode 16.0.0 offsets count code points, including supplementary characters and CRLF normalization. | Authored synthetic expectations plus explicit renderer code-point/UTF-16 conversion. |
| Geometry retains unrotated top-left source coordinates, normalized rectangle, source dimensions and rotation. | Rotated/scaled geometry fixtures; unavailable coordinates display a structural/text fallback. Geometry is block-level when the parser reports only a block rectangle. |
| Protected selector/context creation is atomic, immutable and idempotent. | Existing canonical derived Document identity, protected artifact, provenance, source-revision dependency and outbox; failure before commit and exact/changed retries. No separate anchor identity store. |
| Every create/read/list action uses the current native principal, exact copy, Intent/privacy and rights. | Real composition denial after lock, rights/actor change, substituted identities and corrupt ciphertext. Research text stays encrypted and out of diagnostics/deep-link URLs. |
| A common anchor read is bounded and does not load the whole PDF or normalized IR. | Authenticate the small retained context artifact and canonical authority; instrument forbidden original/IR reads and measure the actual selected path. Creation/outline inspection separately authenticates normalized structure. |
| Reader follows source → selected passage → return journey in both themes and keyboard/reflow states. | Approved three-region inert structured-text reader, exact revision/status, visible fallback, focus and return checks; protected state clears on lock/close. |

First tests precede product edits: selector identity/range/normalization/geometry
and explicit fallback tests, followed by durable restart/retry/denial tests at
the existing encrypted repository boundary. A brief read-only independent design
preflight under task-start planning step 4 is incorporated. It found no authority
gate and emphasized exact selector agreement, current rights on replay, separate
derivative versus original-byte authentication, canonical ledger integrity,
context-relative Unicode offsets, and late-response clearing on lock.

PDF.js source-byte rendering belongs to CAP-05.S04; this task must label its real
structured-text view. Context/citation-link APIs and broken-dependent propagation
belong to CAP-05.S03.T03. No parser replacement, lighter parsing tier, evidence
verification, automation-framework improvement, or replay/tuning of the accepted
CAP-05.S02.T03 warm timing overage is included. Full repository/desktop/documents
profiles and broader platform/packaging qualification remain slice/Wave work;
task checks select the affected contract, persistence, native and reader risks.

Committed qualification50 exposed two missed integration checks: the new
persistence module must use the existing named adapter boundary rather than
reside in the business package, and the sidecar required-module inventory must
remain sorted and match the explicit packaging fixture. Preserve that failed
run. Move only this adapter to the established root-level location, compose it
through the existing revision adapter and portable SourceAnchorRepository port,
register its exact name, and update the new module fixture. Architecture and
packaging regressions must pass; no generic storage exemption or new automation
behavior is introduced.

Independent R01 finding adds the missed criterion3 acceptance row: public
portable contracts, the new port and product check registrations require a
changed indexed documentary ADR with exact affected-path coverage. ADR adverse57
reproduces the gap; append T02's implementation mapping to existing Proposed
ADR0046 and run the existing ADR change-set check before resubmission. Retain all
passing functional54 outputs and prior failures with their exact candidates;
no accepted decision or frozen approval is edited.
