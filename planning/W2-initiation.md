# W2 initiation — Windows local evidence foundation

Working assessment, refreshed 2026-09-19. **Planning in progress; not an approved execution
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
No task or product criterion is removed. The runner-progress allocation below
adds an explicit bounded support deliverable to CAP-04.S01.T01; it is not hidden
in the parser criteria or counted twice.

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
   All original product criteria remain unchanged; CAP-04.S01.T01 adds only the
   separately bounded optional runner-progress criterion described below.
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
  and authenticated viewing. Exact offline asset identities, resource limits and
  a bounded sequential-range design are now selected for independent review;
  [feasibility observations](W2-feasibility.md) do not qualify production behavior.

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
| CAP-05.S01.T01 | CAP-04.S05.T02 also precedes attachment format/password inspection; untrusted inspection cannot run unsandboxed before the later parser. |
| CAP-05.S05.T03 | CAP-05.S04.T02 supplies original-page/deep-link navigation. |
| CAP-05.S06.T02 | CAP-05.S05.T01 supplies reference reconciliation for corrections. |
| CAP-04.S01.T03 | Commit canonical source-record/manifest IDs first; CAP-04.S03 owns later work/version reconciliation. No duplicate engine or backward dependency. |

The four dependency additions are proposed W2 planning edits, mirrored in the
backlog and task sections, not completion/state changes. A real protected-storage
probe measured whole-source verification and writer contention; it supports a
bounded existing-stream adapter, not a new cache. ADR-0029 includes the missing
cancellation hook and exact admission/qualification limits. Packaged end-to-end
viewer, parser and LPAC proof remains implementation work. These findings are
ordinary packet work, not extra human gates.

## UX journey to refine in the existing contracts

Independent mapping found one material reference addition: CAP-04.S05's local
publisher-trust and project-permission review in Source Manager. Prepare one
compact panel using existing components and the design-first route; no new page,
marketplace or Application Settings redesign. The [inert 1.7 proposal](W2-reference-proposal.md)
now supplies that panel and its normative interaction contract; validation/review
and human approval remain pending. The remaining journeys fit 1.6.
Keep the exact inherited ADR-0026 workflow catalog 1.5 binding unchanged.

| Contribution | Existing route / return context |
|---|---|
| CAP-04.S01–S03 | Source Manager → Ingestion Review → Corpus Canvas; manifest opens Audit & Lineage as a supporting tool. |
| CAP-04.S04–S05 | Corpus Canvas/source inspection and Source Manager; configuration or trust review returns to the same source and current primary workflow. |
| CAP-05.S01–S03 | Selected corpus work/version → acquisition → Task Center/Parsing Quality → exact Document Reader revision. |
| CAP-05.S04–S06 | Document Reader ↔ Parsing Quality; human-accepted correction/reparse → scoped Audit & Lineage impact → originating selection. |

These are governed reference destinations, not claims that future workspaces
already exist. Do not auto-complete scholarly stages when import or parsing ends.

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
an explicitly separated support portion of CAP-04.S01.T01.

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

Allocation identity **W2-RUNNER-PROGRESS** is a two-hour subset of the mixed
CAP-04.S01.T01 estimate (16 product + 2 support). It is an accounting label, not
a new task/state/controller. The unapproved task contract explicitly identifies
the support deliverable and separate control review. At the ceiling, preserve
any failed evidence and record deferral without leaving partial runner changes;
continue the parser work. Optional control perfection cannot block the product.

Defer broader harness recovery/caching, historical-fixture overhaul, orchestration
redesign and extra UX instrumentation to W3 or later, selected only when valuable.
Use the existing prerequisite checks for the actual selected command; a new
universal preflight framework is not needed.

## Estimate basis and shared accounting

The two structured capability assessments itemize all **33 atomic tasks** in
**engineering-hours**: 236 for CAP-04 and 294 for CAP-05, **530 total** including
the two-hour support allocation once. These are planning estimates of developer
effort, not measured duration, model cost or a promise of 530 hours of elapsed
agent work. No slice/capability total is added again to its children.

Basis: 12–18 hours for an ordinary existing-boundary vertical; 20 hours for
reversible ambiguous reconciliation; 28 hours for real isolation, packaged
Docling or the protected viewer. Estimates include focused implementation,
tests, review/remediation and an apportioned share of slice/checkpoint/Wave
qualification. No additional unitemized qualification estimate is counted.
Resource and packaging tasks carry greater uncertainty; update forecasts openly
without rewriting the eventual approved denominator.

The single planned refactoring allocation is W2-RUNNER-PROGRESS (2 hours).
The read cancellation hook is necessary new viewer behavior, not unrelated
cleanup. No major redesign/refactoring is selected. Broader harness, historical
fixture and optional performance optimization remain deferred.
If this exact estimate is approved, the subsequent supplemental allowance is
79.5 engineering-hours (15% of 530), starting at zero with W2 approval. This is
not current spending authority or an invitation to use the allowance. The
preselected two hours are already in scope; only excess/supplemental work draws
against that future allowance, with no carryover from W1.

## Retained qualification risks and proportionate follow-up

### Execution checkpoints (not human gates)

After approval, claim only taskctl's dependency-eligible tasks in the single W2
campaign. Use these risk clusters for integrated checks; no additional leases,
approval controllers or repeated whole-repository suites:

1. **CAP-04.S01–CAP-04.S03:** import → four source contracts → reconciliation;
   verify idempotency, protected replay/redaction, conflicting identities and
   cancellation/restart with the existing Core/provenance boundary.
2. **CAP-04.S04–CAP-04.S05 plus CAP-05.S01:** rights → SDK/LPAC → acquisition;
   prove actual denied files/secrets/network, exact trust/permission transitions,
   quarantined inspection and resumable encrypted acquisition before relying on it.
3. **CAP-05.S02–CAP-05.S04:** packaged offline parser → immutable anchors →
   viewer; qualify minimum-tier resources, verified-range cancellation/contention,
   exact-revision navigation and real renderer/native/accessibility wiring.
4. **CAP-05.S05–CAP-05.S06:** citations/structures → human correction/reparse;
   check preserved history, uncertain links and selective staleness, then perform
   the fresh full W2/G2 qualification and separate release decision.

Each checkpoint records exact shared-contract inputs and the union of affected
checks plus a clean build/smoke. Later checks reuse valid earlier evidence only
under the existing input-closure rules; fresh Wave qualification is not cached.
Additive migrations preserve immutable old revisions and encrypted recovery
copies; failure does not downgrade schema, overwrite accepted heads or delete
originals. Broad historical cleanup remains outside this plan.

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

1. Independently review the seven selected recommendations and three shared
   Proposed ADRs, including resource/admission choices and retained qualifications.
2. Review all eleven slice contracts, the bounded proposed reference, and the
   explicit dependency/migration/recovery/checkpoint handoffs. Resolve blocking
   findings without silently moving scope or thresholds.
3. Review structured initiation-assessment 2.0 data and all 33 atomic estimates
   in one unit, with the shared maintenance allocation counted once. They are
   now itemized, but remain unapproved and reviewable.
4. Validate and independently review the complete W2 packet; then request one
   immutable pre-Wave approval. Only after that approval and normal integration/
   readiness requirements may the W2 campaign start.

The authored packet now has selections and estimates; independent disposition,
exact architecture/reference approval and normal clean-worktree prerequisites
remain unmet. Do not request execution approval on the strength of schema checks
alone. Implementation, gate relaxation and later Waves remain unauthorized.
