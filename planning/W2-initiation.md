# W2 initiation — Windows local evidence foundation

Working assessment, 2026-09-13. **Planning in progress; not an approved execution
packet.** The [G1 owner decision](../artifacts/evidence/G1.owner-approval-01.md)
clears the upstream gate through a limited local-prototype exception. It does
not turn retained W1 gaps into PASS or approve W2 implementation. Live state,
identities and dependencies remain in [the backlog](backlog.yaml).

This note coordinates the two capability assessments, not a new controller,
approval tier or competing backlog. Finish the existing capability/slice packet
before requesting the single W2 approval. No W2 task has been claimed.

## Product outcome and complete contribution inventory

A researcher should be able to bring in references, inspect conflicting source
records, acquire permitted documents, and open an exact passage in its original
revision. Import, parsing and reconciliation must not manufacture evidence or
make scholarly acceptance decisions for the researcher.

The current forecast is **11 slices / 33 tasks**, three tasks in every row.
No task, dependency or product criterion is removed by this initiation increment.

| Contribution | Outcome / planning emphasis |
|---|---|
| CAP-04.S01 | Local reference import, preview and idempotent commit; malformed records remain inspectable. |
| CAP-04.S02 | Four official scholarly-source adapters; explicit partial availability, credential and rate-limit behavior. |
| CAP-04.S03 | Exact identity reconciliation, human-reviewed ambiguity, reversible merge and version/update history. |
| CAP-04.S04 | Corpus membership, discovery paths and action-specific rights; unknown rights are not permission. |
| CAP-04.S05 | Bounded connector SDK, real isolation and a sample/conformance path; not a plugin marketplace. |
| CAP-05.S01 | Local attachments and permitted acquisition; protected object storage, resumable jobs, usable metadata when full text is absent. |
| CAP-05.S02 | Secure structured parsing and pinned local Docling PDF processing; explicit degraded results and resource limits. |
| CAP-05.S03 | Immutable document revisions and multi-selector source anchors; never silently relocate evidence. |
| CAP-05.S04 | Secure source viewer, deep links and rights-controlled actions; return to the originating work. |
| CAP-05.S05 | References, citation contexts, tables and figures tied to source locations; uncertainty remains visible. |
| CAP-05.S06 | Separate quality dimensions, correction drafts and human-accepted reprocessing with selective staleness. |

Use the existing dependency order, not this table as a new execution schedule.
The first candidate remains **CAP-04.S01.T01 — reference-format parsers**, but
its READY projection is not permission to claim before W2 packet approval.
CAP-04.S05 and the document branch can be planned alongside each other; execution
still follows taskctl eligibility and the approved Wave campaign.

## Implemented baseline and adaptations

Baseline inspected at `4f58332a` (G1 recording); component qualification remains
the historical, explicitly limited evidence cited by the G1 decision.

- Reuse the existing Core-owned identity/revision, repository and provenance
  contracts (ADR-0013/ADR-0024), rather than inventing import-only identity or
  event stores. Provider identifiers remain assertions, not internal IDs.
- Reuse protected object streams and content-addressed objects. The existing
  `ObjectStore` port exposes verified reads, not decrypted paths. Viewer range
  access is a design gap to resolve, not an already implemented capability.
- Reuse durable workflow claims, checkpoints, cancellation and staged artifacts
  under ADR-0025. `WorkflowActivityContext` has no database/key handle. A worker
  activity is not, by itself, proof of hostile-plugin or parser isolation.
- Reuse project/intent context, supporting-tool return, dependency impacts and
  selective recalculation. No parallel workflow engine, navigation-state store
  or general orchestration rewrite is selected.
- Map proposed implementation locations onto the actual Core package under
  `services/core-api/src/research_observatory_core/`; older slice paths are a
  forecast, not a reason to relocate working W1 modules.

### Material planning mismatches to close before locking W2

1. Capability and all eleven unapproved slice procedures now require one complete
   W2 approval and the same Wave campaign. They reuse implemented W1 identity,
   provenance and jobs rather than the old not-yet-available fallback language.
   All 33 task acceptance blocks remain unchanged.
2. Slice plans now cite the current Academic Minimal 1.6 reference. The
   [reference approval](../design/ui-reference/APPROVAL.yaml) records **1.6**;
   its README's earlier "proposal" wording is stale and is not authority.
   Complete affected W2 page/journey mapping against that approval. Preserve ADR-0026's exact inherited 1.5
   workflow-catalog binding unless its governed migration is explicitly selected;
   do not relabel existing project selections or edit frozen reference history.
3. CAP-04.S02 no longer calls for credential-bearing exact request URLs. Proposed
   ADR-0027 separates protected scientific replay from current broker-injected
   authentication/contact values, including redaction of echoed response values.
   It still needs independent architecture disposition and acceptance with W2.
4. Protected storage does not currently promise seek/range semantics. Resolve
   the viewer stream design for **CAP-05.S04.T01** without adding plaintext
   temporary paths or unauthenticated content URLs.

These are recorded planning gaps, not new approved architecture. Existing source
authority governs the interim state; dependent implementation remains unstarted.

## Current primary-source refresh

Reviewed 2026-09-13; these observations inform proposals, not live-provider proof.

| Source observation | W2 implication |
|---|---|
| OpenAlex supports keyless basic access and larger keyed budgets. [Authentication](https://help.openalex.org/api/authentication/) | Optional local key configuration, explicit unavailable/budget states, no assumed spend or committed key. |
| Crossref exposes a public API; supplied metadata can include third-party copyrighted abstracts. [REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) | Keep provenance and field-level rights; public retrieval is not blanket redistribution authority. |
| Unpaywall v2 requires a contact email. [API v2](https://unpaywall.org/api/v2) | Local private contact setting; unset means not configured, not zero OA results. Redact query contact values. |
| Semantic Scholar has shared public access and keyed limits/capabilities. [Official API](https://www.semanticscholar.org/product/api) | Source-specific admission, backoff and partial results; no single assumed quota for all providers. |
| Docling documents prefetched offline assets, explicit remote-service opt-in and resource limits. [Advanced options](https://docling-project.github.io/docling/usage/advanced_options/) | Pin and prepackage required assets; verify no runtime network dependency. Documentation is not Windows packaging proof. |
| W3C defines text quote/position and other selectors. [Web Annotation](https://www.w3.org/TR/annotation-model/) | Keep the multi-selector recommendation; application normalization, ambiguity and migration semantics still need exact fixtures. |

Before lock, resolve **CAP-04-D01/CAP-04-D04** (source permissions/replay and
connector isolation) and **CAP-05-D01** (local parser/runtime/assets). Compare
credible alternatives, record the selected implementation and required ADRs,
and perform only bounded feasibility checks necessary for those decisions.
No service account, live research query, installation or purchase was made for
this assessment. No replacement parser is silently substituted for Docling.

### Proposed shared architecture and bounded feasibility

Three records consolidate shared material boundaries; they are **Proposed**, not
accepted architecture or permission to start tasks:

- [ADR-0027 — source replay and private authentication](../docs/adr/ADR-0027-keep-scholarly-source-replay-separate-from-private-authentication.md):
  retain all four adapters, provider-specific configuration, encrypted scientific
  replay, source assertions and current action-specific rights.
- [ADR-0028 — Windows worker isolation and brokers](../docs/adr/ADR-0028-isolate-windows-connectors-and-parsers-behind-narrow-brokers.md):
  LPAC, no ambient network/project/vault access, bounded IPC, explicit publisher
  trust and per-project permissions; no marketplace or new workflow engine.
- [ADR-0029 — document revisions and source viewing](../docs/adr/ADR-0029-preserve-document-revisions-and-mediate-source-viewing.md):
  modular local Docling, exact-version anchors, human correction/reparse acceptance
  and authenticated viewing. Offline asset identities/resource limits and viewer
  transport feasibility remain explicit pre-approval gaps.

On 2026-09-13, a planning-only `uv 0.12.2` wheel resolution for Windows x64 /
Python 3.14.6 succeeded for `docling-slim[convert-core,format-pdf,models-local]==2.126.0`,
`docling-parse==7.16.0` and `docling-ibm-models==4.0.2`, with CPU-only PyTorch
selection. It resolved **73 packages**, including `torch==2.14.0+cpu` and
`torchvision==0.29.0+cpu`. The local hash-bearing output is
`artifacts/tmp/W2-parser-probe/requirements.lock`, SHA-256
`7b72b13d77dc465ed8403732ccf41996aee1ee1e71aa40590dd9547dafa3527f`.
Public PyPI/PyTorch metadata only; wheel-only resolution, keyring disabled,
no package installation/build, model download or application dependency edit.
An initial CLI invocation rejected incompatible `--no-build`/`--only-binary`
flags; the corrected wheel-only invocation exited 0, with a normalized upstream
version-specifier warning. This is not runtime, import, licensing, sandbox,
offline conversion, packaging or performance qualification, nor a shipping lock.

Independent planning preflight identified these material handoffs:

| Task | Required prerequisite / ownership clarification |
|---|---|
| CAP-05.S02.T03 | CAP-04.S05.T02 supplies the qualified worker boundary. |
| CAP-05.S05.T03 | CAP-05.S04.T02 supplies original-page/deep-link navigation. |
| CAP-05.S06.T02 | CAP-05.S05.T01 supplies reference reconciliation for corrections. |
| CAP-04.S01.T03 | Commit canonical source-record/manifest IDs first; CAP-04.S03 owns later work/version reconciliation. No duplicate engine or backward dependency. |

The three dependency additions are proposed W2 planning edits, mirrored in the
backlog and task sections, not completion/state changes. The viewer feasibility
check must include whole-file authentication, held metadata transactions,
concurrent writes, source/range limits and cancellation. Do not treat small
responses as bounded source work or add an encrypted cache without designing its
separate lifecycle. These findings are ordinary packet work, not extra human gates.

## UX journey to refine in the existing contracts

Start in an open project with its accepted intent and selected workflow.

- **Import to corpus:** choose a bibliography through a picker; preview raw and
  mapped values; exclude or correct records; inspect ambiguity; commit once;
  open the resulting corpus and manifest. Carry project, import and selection
  context. Cancellation leaves canonical state unchanged; return to preview
  with a specific recovery action, not a generic failure page.
- **Corpus to source:** select a work/version; attach or choose a permitted copy;
  monitor acquisition/parsing; open the highlighted source revision with rights,
  provenance and quality visible; return to the same corpus selection. Missing
  full text preserves the metadata record and offers attach/retry as appropriate.
- **Source to correction and back:** open the warning at its exact location;
  edit a draft; compare original/machine/corrected structure; accept explicitly;
  inspect affected dependents. Retain older revisions. Closing the project clears
  protected view state; it does not silently reopen work later.

Reuse existing components, tokens, workflow IDs, file/folder selection and sensible
destinations. Validate only materially changed reference behavior through the
existing design-first route. Add no new UX approval layer or universal walkthrough.
Task checks should cover carried/cleared context and return/failure paths, with
native evaluation reserved for real picker, focus, accessibility and packaged
wiring boundaries. A short goal-only exploration is useful if a consequential
journey remains unclear; advisory styling preferences do not become feature gates.

## One small automation increment

**Selected proposal: live verbose test progress in the existing runner.**
`tools/verify.py` currently captures each command's output until it exits;
`-v` already preserves unittest names and skip reasons. Forward output while
retaining the complete final stdout/stderr report, so a slow case or skip becomes
visible promptly. This is planned bounded maintenance, not implemented here and
not a hidden addition to a product task.

- Scope: `tools/verify.py`, focused cases in
  `tests/foundation/test_verify_runner.py`, and a short evidence note.
- Ceiling: one implementation/review session, approximately **two engineering
  hours**, shared once across W2, not once per capability. Defer unfinished
  optional work if it requires runner/process-containment redesign. This is a
  planning allocation, not a measured duration or claimed cost saving.
- Preserve command selection/order/arguments, exit codes, fail-stop behavior,
  complete diagnostics and existing terminal-report semantics. Partial output,
  a skip or interruption must never imply PASS. Do not publish raw output or
  account/path/credential values into tracked evidence.
- Proof: a disposable child emits partial-line progress before exit; both output
  streams and skip/failure reasons survive; failure prevents later commands;
  interruption does not produce successful terminal evidence. Run only focused
  new runner checks and synthetic process proof, followed by independent review.
- No automatic retries, result caching, resume engine, new receipt schema,
  dashboard, mandatory global preflight, new gate or weakening of assertions.

Before approval, give this shared allocation one identity under the existing
maintenance/accounting route and count it once in the itemized Wave estimate;
do not invent a product-task ID or double-count it across capability estimates.
The final accounting representation is still to be resolved during packet assembly.

Defer broader harness recovery/caching, historical-fixture overhaul, orchestration
redesign and extra UX instrumentation to W3 or later, selected only when valuable.
Use the existing prerequisite checks for the actual selected command; a new
universal preflight framework is not needed.

## Retained qualification risks and proportionate follow-up

The [completed control follow-up](W1-W2-control-followup.md) and G1 decision retain
the evidence; do not replay completed W1 suites simply to improve reporting.

| Retained issue | W2 planning disposition |
|---|---|
| Scanner failure and unidentified security skip | Identify the affected checks before depending on new network/plugin/parser boundaries; select narrow diagnostics/remedies. Unknown is not clean. |
| CLI fixture cleanup / historical binding cases | Repair only if the selected W2 proof depends on them; preserve errors. No broad retrospective repair mission. |
| Protected benchmark setup | Use disposable configured authority for new storage/parser measurements; setup failure is not a timing result. |
| Worker numeric qualification | Establish an explicit representative baseline for new connector/parser workloads before claiming resource compliance; retain the unaccepted W1 comparison. |
| Core/gateway timing overages | Keep accepted W1 exceptions and later values distinct; select optimization only if W2 materially depends on it. No threshold relaxation. |
| Hello deferral / native first-Tab uncertainty | Preserve the exact limitations; evaluate affected new native paths without claiming historical authentication/focus success. |

G2 remains the normal separate exit gate: ingest/reconcile/parse/inspect, exact
revision/anchor resolution, and traveling rights/discovery provenance. W2 still
requires fresh Wave qualification and independent review. The G1 exception is
not a W2 security, integrity, accessibility or release waiver.

## Next planning increment and approval boundary

1. Resolve the named material decisions and consolidate required ADR work by
   shared boundary, without a document for every routine implementation choice.
2. Refresh all eleven slice contracts, affected UX mappings, migration/recovery
   and checkpoint evidence. Keep current IDs and make any proposed dependency
   changes explicit through the canonical planning route.
3. Complete structured initiation-assessment 2.0 data and all 33 atomic task
   estimates in one unit, with the shared maintenance allocation counted once.
   No total or 15% allowance is claimed while those estimates are missing.
4. Validate and independently review the complete W2 packet; then request one
   immutable pre-Wave approval. Only after that approval and normal integration/
   readiness requirements may the W2 campaign start.

This kickoff is deliberately not approval-ready. Planning can continue without a
new human decision now; implementation, gate relaxation and later Waves cannot.
