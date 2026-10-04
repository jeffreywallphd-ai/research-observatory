# Design-first UI change gating

`tools/ui_change_gate.py` is the pull-request and foundation guard for researcher-facing implementation. It compares an immutable Git base and head, rather than trusting the working tree, and activates when renderer files under the governed UI roots in `ui-change-policy.json` change.

Every activated change must have one current task contract at `artifacts/evidence/ui-change/<task-id>.json`. Only the exact adopted continuation in versions 1.3 and 1.4 below may also retain its separately authenticated historical amendment contract in the full task-base range. The current contract must match `design/ui-change.schema.json`, list the exact changed implementation files, cite the exact approved reference ID/version/package SHA-256 and approval commit, identify the claimed task owner, and match the task's `experience_change` field in `planning/backlog.yaml` or one of the exact authenticated amendment/restoration authorities below. The task must be active and its full `base_sha` must equal the validated range base. Governed implementation entries must be regular Git blobs; symlinks, gitlinks, trees, and other redirected object types fail closed.

## Change kinds

- `intentional-design-change` changes a normative route, navigation, token, workflow, required region, interaction, accessibility behavior, or theme behavior. The base and head reference IDs must differ. The new `APPROVAL.yaml` must declare `approval_kind: human`, use an `approved_by: human:<identity>` distinct from the implementation agent, supersede the base reference, and be committed after the change base but strictly before every implementation commit. Ordinary tasks require `human-and-agent-review`; only the exact opt-in 1.2 amendment below uses the separately authenticated owner approval and independent review substitute.
- `approved-reference-implementation` creates implementation that conforms to the unchanged approved reference, including first implementation of an already approved page or workflow. It cites focused conformance evidence and does not alter the reference.
- `defect-restoration` returns drifted code to the unchanged approved reference. It records the defect, expected approved behavior, and focused passing restoration evidence; no new design approval is needed. Until CAP-00.S06.T04 installs a governed implementation-conformance verifier, the task must retain `human-and-agent-review` so a self-asserted restoration cannot classify arbitrary new behavior as a defect fix.

Changing both the approved reference and implementation in one commit is rejected because approval must be a distinct earlier commit. An implementation agent cannot self-approve by changing identity labels: intentional approval must use a human identity, differ from `implementationAgent`, match the approval record, and remain protected by the repository's human review gate.

## Commands

For a task branch, validate the whole task/PR range:

```powershell
.venv\Scripts\python.exe tools\ui_change_gate.py --repo . --base <task-base-sha> --head HEAD
```

The foundation profile uses `UI_CHANGE_BASE_SHA` when CI supplies the pull-request or push base. A manual dispatch requires an explicit immutable base SHA. Locally, the gate uses the sole active task's governed `base_sha` when that task carries `experience_change` or is the exact authenticated active `CAP-05.S01.T01` continuation below. It fails on ambiguous or invalid active-task state and falls back to `HEAD^` only when no UI task is active. CI performs a full-history checkout so commit ordering and ancestry are verifiable. The pull-request template records the same lineage for reviewers, but prose or a checked box cannot replace the committed contract.

The gate fails for a missing, extra, malformed, renamed, or stale contract; incomplete changed-file coverage; unknown or mismatched task metadata; forged reference hashes; a nonhuman or self approval; same-commit approval and implementation; intentional implementation without a newer approved reference; or restoration/conformance work that also modifies the reference.

## Exact intentional amendment (opt-in 1.2)

The owner-approved `ECR-0009` authorizes one additive lane for the materialized
`W2.A01.T02` attachment interaction. Its `schemaVersion: "1.2"` contract uses
`changeKind: "intentional-design-change"`, reference ID
`RO-UI-ACADEMIC-MINIMAL-1.8`, version `1.8`, predecessor
`RO-UI-ACADEMIC-MINIMAL-1.7`, and a closed `intentionalAmendmentAuthority`
object naming `W2.A01`, `ECR-0009`, control task `W2.A01.T01`, and
`planning/reference-approvals/RO-UI-ACADEMIC-MINIMAL-1.8.json`. These exact
labels select the route; they do not prove approval or claim authority.
No other amendment or ordinary task may use 1.2, and 1.0/1.1 contracts cannot
carry this authority object.

The gate checks the immutable ECR packet and its proposal-file hashes, the
introduced human approval record, materialized task identity and complete
inventory, committed independent `W2.A01.T01` review, and the current
`W2.A01.T02` owner, lease, branch and original task base. It checks the new
reference approval and published package against the reviewed proposal and
every governed reference and implementation path in the full task-base range.
Every intermediate commit counts, including a file added and later reverted;
redirected Git objects, extra UI contracts, files outside the approved
renderer/reference/evidence envelope, and mixed control/product edits deny
qualification. Taskctl may record backlog transitions in separate commits;
no commit may change `planning/backlog.yaml` together with governed reference
or renderer files. Admitted `.d.ts` typed product-source files also require
publication first and separate backlog transitions; the gate records them
apart from governed `uiFiles` and rejects hidden add/revert history. The
separate reference-publication commit
must follow the human decision and strictly precede every renderer commit.
The complete contract is evaluated with the T02 task base and current `HEAD`;
producer labels and a successful partial or mock check cannot replace
the committed evidence chain. Independent T02 review checks whether each
enumerated renderer file actually belongs to the approved interaction.

This lane substitutes the authenticated ECR owner decision plus the independent
T01 control/security review and T02 task review for amendment task fields that
the v4.1 task schema forbids. It does not supersede ADR-0003 or weaken the
ordinary intentional-change rule. Proposed ADR-0035 documents the exact
protected gate change, and the T01 ADR/control review must be committed before
T02 begins. The staged T02 renderer keeps production choose/drop unavailable;
real native/Core attachment and native-only path handling remain in the
resumed `CAP-05.S01.T01`. Neither amendment adoption nor this gate result is W2
release approval.

## Adopted attachment UI continuation (opt-in 1.3)

The owner-approved `ECR-0010` authorizes a distinct lane for the original,
ordinary `CAP-05.S01.T01` after adoption of `W2.A01` and completion of the
separately reviewed `W2.A02.T01` control task. The immutable ordinary task has
`agent-review`, no `experience_change`, and original claim base
`6506c68461144747b0ee9be10853211717aa381d`. A later or shorter base must
not hide its inherited 1.7-to-1.8 publication and renderer history. The lane
does not create a new reference: Academic Minimal 1.8 remains the unchanged
approved package, and T01's work is classified against it.

Only this task may use `schemaVersion: "1.3"` with
`changeKind: "defect-restoration"`, reference
`RO-UI-ACADEMIC-MINIMAL-1.8` version `1.8`, predecessor
`RO-UI-ACADEMIC-MINIMAL-1.7`, and the existing `restoration` description of
approved interruption/restart behavior. Its closed
`adoptedContinuationAuthority` selects `W2.A02`/`ECR-0010`/`W2.A02.T01`
and inherited `W2.A01`/`W2.A01.T02` with the exact inherited
`artifacts/evidence/ui-change/W2.A01.T02.json` contract. It declares the
authenticated `adoptionCommit` and `reactivationCommit`, separate
`inheritedUiFiles`/`inheritedUiCommits` and
`resumedUiFiles`/`resumedUiCommits`, and an independently committed
`classification` with task-namespaced path, SHA-256 and introduction commit.
These are assertions to verify against committed authority, not an agent's
permission to select a convenient history. Versions 1.0-1.2 cannot carry this
object; version 1.3 cannot combine it with their authority objects.

In the full original-base range the gate admits exactly two contracts: the
unchanged, independently reviewed historical `W2.A01.T02` v1.2 contract and
the current T01 v1.3 contract. It authenticates W2 and W2.A01 approvals, the
approved 1.8 publication and T02 exact reviewed candidate, W2.A01 adoption,
the W2.A02 approval/control review and explicit ordinary-task reactivation,
and the current T01 owner, unexpired lease, branch and unchanged 6506 base.
The reviewed W2.A01.T01, reference-verifier/ADR-0036, active UI-gate/fixture,
GOV-MAINT-0025 quality-inventory and W2.A02.T01 chains must each account for
their attributed control commits. Neither a filename nor a historical task
label substitutes for its exact independent review and Git ancestry. The
W2.A01.T01 predecessor is its exact approved R02 candidate; reviewed
W2.A02.T01 commits may change only the six ECR-0010 control-source files and
their task-owned evidence or generated workflow projections. Independent review
does not turn an extra product file into approved control scope. The
original T01 definition is checked against the immutable W2 packet Git blob,
not only the current backlog projection. Every governed reference, renderer,
typed-source, backlog and gate-control commit is attributed to the proper
segment, including paths changed and later reverted. A T01 reference rewrite,
extra contract, redirected object, unattributed control edit or foreign live
claim denies qualification.

The T01 classification independently judges the **current committed product**
against the unchanged approved 1.8 reference. It binds exact candidate,
reviewer, criteria, captures, report hashes, complete T01 UI commit/path list,
current Git blobs and producer-input snapshot. The existing capture reader
authenticates the Core, native Rust, renderer, contract, build and checker
inputs. The gate separately derives every T01-owned test, fixture, worker or
other product input outside that snapshot and requires the classification's
exact `dependentInputFiles` and Git blobs. Missing or stale captures, an
omitted dependent input, or any later input touch including add-and-revert
invalidates the classification. It is not task approval or a substitute for
native/Core evidence.

One historical mixed commit has an exact-identity exception:
`9727f1b195e7dee300e7f3df3c289e7739fb0fdc`. Its sole-parent tree must
show `quality-scope.json` strictly appending exactly nine newly introduced,
canonical, regular `.py` files while preserving every earlier entry, order,
metadata and root; the same commit changes exactly the two approved 1.8
restoration renderer files and no other gate control. The gate verifies the
immutable commit/tree and same-commit Python introductions. This is not a
reusable mixed-commit allowance or prior independent approval of that product
commit; the resumed T01 full-candidate independent review examines it after
submission. Every other mixed control/product commit denies. For the sole
authenticated active continuation task, automatic base selection uses 6506,
never `HEAD^`; other task/version routes retain their existing rules.

Proposed ADR-0037 supplies ADR-0001's association for the protected control
change and does not supersede Accepted ADR-0003 or grant UI authority itself.
Focused schema and real-Git hostile/compatibility checks and expanded
independent control/security/ADR review precede W2.A02 exit. Adoption leaves
W2 paused; explicit Wave resume, current conformance classification, the
original task's full-base gate and independent task review, the unresolved
intermittent D3D startup denial, later slice/Wave checks and human release
decision remain separate obligations. A partial UI-gate result cannot complete
T01 or W2.

## Approved 1.8 desktop activation continuation (opt-in 1.4)

The exact owner-approved `ECR-0011` adds reviewed `W2.A03.T01` control/witness
work and later `W2.A03.T02` desktop consumer work before the original
`CAP-05.S01.T01` can resume. Version 1.4 is available only to that original
task as `defect-restoration` over its unchanged `6506c684...` claim base. It
retains the entire version 1.3 `adoptedContinuationAuthority` object unchanged,
including the historical post-A02 `reactivationCommit`. Its additional required,
closed `referenceActivationAuthority` names exactly `W2.A03`/`ECR-0011`,
`W2.A03.T01`/`W2.A03.T02`, the approved 1.8 reference approval path, the
committed 1.8 presentation witness path, the publication/witness/A03 adoption
commits, the separate post-A03 ordinary-task reactivation, and the four
activation/baseline/assembly consumer paths and their ordered commits.
Versions 1.0–1.3 cannot carry the new object; version 1.4 cannot omit either
authority object or select another task or change kind.

The gate derives these assertions from Git, the exact independently reviewed
ECR-0011 approval and B00 bootstrap, separate materialization/activation,
completed task submissions, S01/exit/adoption records, original W2 approval,
the A01/A02 history, and the exact frozen, independently reviewed
CAP-04.S05.T03 R01–R03, GOV-MAINT-0026, and W2.C10.T01 predecessors. The T03
admission covers only its three historical product/control commits, including
its temporary sample-source move and per-commit path/mode history. T01's single
committed 1.8 witness introduction must follow its claim, and independent T01
approval must precede the T02 claim and every T02
source edit. Each reviewed task's source must remain inside its packet envelope;
task-owned evidence and generated planning projections are separate workflow
outputs. The gate attributes the witness and seven T02 source paths to those
reviewed amendment ranges, rather than treating them as original T01 product
work. After adoption, the original task may touch only T02's three shared test
modules within this envelope, after its authenticated reactivation and with
both sides of each commit under its active claim; its independent classification
must bind those dependent inputs. The witness, controls, four activation
consumers and all other amendment source stay frozen. It rejects a foreign or
shortened base, changed mode or bytes, extra UI
contract, hidden add/revert, unreviewed control/product input, stale lease or
classification, and any consumer file touched after its reviewed T02 segment.

The committed activation keeps its prior configuration except the approved 1.8
ID and package. The baseline keeps its pinned renderer settings and has exactly
33 approved product pages in both themes, with 66 schema-valid entries; both
assemblers declare the same exact 1.8 selectors. This structural lineage check
does not prove the PNG contents or desktop runtime. T02's guarded pinned
capture and independent baseline review, the current T01 classification and
native/Core evidence, joined slice checks, W2 qualification, and human release
decision remain separate.

### Exact protected activation correction

The owner-approved ECR-0012 permits only W2.A04's separately reviewed five-source
correction within the existing v1.4 lane. No new contract field or schema is
introduced. Authenticate its immutable packet/owner/independent review, B00,
separate materialization/activation/claim, source submissions and task review,
integrated S01, exit and separate security adoption checkpoint. The new Proposed
ADR-0040 links A04.T01 and A03.T02 and is introduced with one appended registry
entry; prior entries, registry metadata, accepted ADRs and ADR-0039 stay unchanged.

Only exact `a211f241` with sole `ca8b1448` parent represents the combined T02
claim/block/A03 pause without an intermediate committed IN_PROGRESS claim. Bind
its complete frozen record and unchanged DONE T01; do not generalize that
exception. Adoption returns the exact PAUSED predecessor with T02 BLOCKED.
Separate later A03 activation must leave T02 blocked; supported reopen retains
its original base, definition/hash, criteria, owner, branch/worktree and matching
lease. Every consumer source commit follows reopen under that active claim.

Attribute every reviewed A04 correction commit separately from T01 and T02 while
walking T02's entire retained range. Inert ECR-0012 authority and task-owned
workflow output do not admit extra source, mixed delivery or hidden add/revert.
Task and exit evidence paths come from authenticated frozen submission and
review references, including superseding remediation manifests; a filename alone
grants no authority. Keep S01 contribution rounds at immutable contiguous
`W2.A04.S01.review-NN.json` paths. Replay their existing finding/closure format,
independent reviewed-task bindings and introduction order; the latest approval
must close every earlier open finding and bind the current approved candidate.
Missing/forked/stale/forged authority, altered completed history, missing return,
premature activation/reopen, extra ADR/index changes and redirected/dirty inputs
deny. Preserve original-task base/two-contract inventory, current classification,
capture input closure and all prior v1.0-v1.4 denials. T02's actual retained-base
ADR check, actual captures, native/Core, slice/Wave qualification and human
release remain separate obligations.

## Linked completed-task restoration (existing 1.0)

An admitted `Wn.Cnn.T01` linked correction uses the existing v1.0
`defect-restoration` contract at exactly
`artifacts/evidence/ui-change/<correction-id>.json`. The gate consumes taskctl's
existing committed origin, spec, paused predecessor, inherited contract, approval
and review-history checks. It does not add `experience_change` or `review_gate`
to the correction or borrow the DONE origin's owner or base. The authenticated
origin must retain its `human-and-agent-review` obligation, or be the exact
completed approved-reference implementation of an authenticated, adopted
human-approved amendment. That alternative authenticates the immutable packet,
original UI contract at its reviewed candidate/base, and independent review
history; it never synthesizes an amendment task's forbidden `review_gate`.
An ordinary `agent-review` origin with no experience/amendment metadata may
instead use ADR-0003's installed-conformance alternative. It authenticates the
exact human-approved Wave packet and its distinct approval introduction,
unchanged task/slice scope and reference, the previously completed verifier,
and the origin's immutable independent review. Approval must precede the original
claim; the packet cannot already contain an active or completed origin.
Ordinary submit/review transitions
may share a delivery commit; the exact prior claimed state, frozen submission,
review ledger and resulting attempt history must still authenticate. The older
amendment route retains its separate-submission-commit requirement.

This alternative additionally requires `restorationClassification` in the v1.0
contract, containing `path`, `sha256` and introduction `commit` for the existing
`<correction-id>.ui-classification-Rnn.json` independent restoration disposition.
The existing record's `taskDefinitionSha256` is the exact original-task snapshot
digest; `resumedUiFiles` and `resumedUiCommits` cover all governed implementation
history from the correction base. Its current producer, independently reviewed
product/reference captures and measured conformance authenticate through the
same capture reader used for resumed amendments. The field names retain that
existing format; they do not create an amendment or new approval state. A missing
record, self-review, invalid capture, unsupported merge or later UI/reference
edit (including a revert) denies qualification. Installed verifier status alone
and producer-declared focused checks never suffice. Automatic base selection can
identify an eligible claim before these final proof artifacts exist.
The complete current capture producer snapshot also authenticates Core, contract,
build and checker inputs. Any later touch to those inputs or an admitted
correction product/test path invalidates the judgment, including add/revert
history; unchanged UI files alone are insufficient.

Unsupported origins fail closed. Focused conformance evidence and the existing independent,
commit-bound corrective integration review remain required. No new approval,
classification record type, schema version or workflow layer is introduced.

This live authority lane requires current `HEAD`, the current branch and
repository-relative worktree, the correction's full admission base, claimed owner,
and an unexpired matching lease. Its base must precede admission and authenticate
the unchanged paused predecessor and prior corrective history. Automatic base
selection includes the sole active admitted UI correction even before its UI
contract exists and after evidence-only commits; competing or invalid live claims
fail closed. Ordinary v1.0 and resumed-amendment historical behavior is unchanged.

Only the exact admitted governed UI paths may be touched. Every commit is checked,
including paths later reverted and intermediate redirected Git objects. The spec
and current approved reference must remain untouched throughout the correction;
restoration uses the reference at the correction base, not a superseded origin
reference. Reverting all UI changes cannot erase the evidence requirement. Taskctl
admits only this exact task-owned UI evidence path as additional delivery when the
correction has governed UI scope, not a general evidence-directory allowance.
All existing reference, scope, control-maintenance and independent review denials
remain in force; gate success is not task completion or human release approval.

Separately reviewed control maintenance may occur while a linked correction is
quiescent. Use the existing bounded-maintenance candidate → evidence → independent
review chain, with exact source hashes and control-only scope. Every otherwise
inadmissible path-changing commit in the correction's full range must belong to
exactly one such chain; a reviewed filename never admits later edits, add/revert
history, mixed product changes or extra delivery. The UI gate and task submission
both enforce this attribution. Historical callers retain their earlier cutoff.
This does not change the correction spec, original base, criteria or approvals.

For source remediation within that same maintenance increment, optional identical
`sourceCommits` arrays in its evidence and final independent review bind the
complete ordered predecessor-to-candidate sequence. Every sole-parent source
commit includes its exact changed paths and regular-file blob/SHA-256 bindings;
all stay inside the existing control envelope plus the exact maintenance note.
Final inventories cover the union of touched paths at the final candidate.
Omissions, merges, forged intermediate content, deletions and mixed product work
fail closed. Evidence-only and review-only deliveries remain immediate and
immutable. Preserve adverse findings and their closures; final acceptance does
not claim an earlier candidate passed. Without the optional arrays, the original
single-source-commit rule is unchanged.

Mandatory protected-interface ADR association may accompany that authenticated
maintenance chain as one new indexed **Proposed** companion. Its regular,
non-executable document and single appended index entry must be introduced
together once. Every prior ADR byte, index entry/order and registry metadata
remains unchanged throughout source history. No accepted status, decider,
supersession or new architecture authority is admitted. The companion must
contain the required review sections, link existing tasks including an active
correction's exact origin, and name only concrete actually changed protected
control or admitted correction paths. Wildcards, unrelated scope, intermediate
rewrites/reverts and later unauthenticated touches fail. Existing exact source,
evidence and independent-review bindings authenticate both new documents.
This is documentary association under ADR-0001, not an ADR-check exemption,
general authority-file allowance, or permission to change approved decisions.

## Resumed amendment restoration (opt-in 1.1)

An immutable amendment task may resume after one separately approved, executed,
independently qualified and ADOPTED immediate paused-parent correction. It must
not rewrite its original `base_sha` or add fields forbidden by its approved task
schema. For this case only, a `schemaVersion: "1.1"` defect-restoration contract
adds `amendmentAuthority`: the correction ID, exact adoption and explicit parent
reactivation commits, separately attributed inherited/resumed UI file inventories,
and a committed independent restoration-classification reference. Top-level
`changedFiles` still covers the entire original-base range. A path may belong to
both segments; the full inventory is not the resumed three-file-style subset.

This lane authenticates the existing approval introductions, reviewed immutable
packets/task definitions, exact paused parent, actual adoption checkpoint and
independent task/exit ledgers. Every inherited UI-changing commit must occur in
one reviewed correction submission range, after reference publication. The new
reference must equal its reviewed proposal except enumerated publication metadata;
the superseded reference is checked at its original Git snapshot. Return preserves
the exact paused parent, and explicit activation preserves the original task base.
Ordinary Wave work and release gates stay unchanged. Nested/competing corrections,
unattributed edits, hidden add/revert paths, renames/type changes and merge ambiguity
are not supported. Existing narrow authority helpers read clean current authority,
so this opt-in contract requires `--head HEAD`; v1.0 historical validation is unchanged.

The independent `independent-ui-restoration-disposition` record binds the task/base,
immutable task-definition hash, classified producer commit, complete resumed UI
commit/path lists, current reference package, paired product/reference capture
manifest and independent visual disposition. It explicitly states whether the
approved task allows the restoration and explains the normative basis; an agent's
self-labelled fix or self-hashed manifest does not grant this judgment. A later UI
or reference edit, even if reverted, requires fresh classification. Later control-only
commits may retain it. Full capture validity and every task criterion remain the
formal evidence/review responsibility; this record is not task approval.

This authenticated amendment lane substitutes approved amendment/conformance authority
for the impossible amendment `experience_change`/`review_gate` fields. All ordinary
v1.0 denials remain in force. Gate/schema/quality changes still require the existing
exact control-only independent maintenance attestation, including late maintenance;
there is no blanket exemption. The maintenance envelope includes this canonical
contract document. Active tasks in an adopted correction's returned parent select
their original base even before a UI contract exists, never an evidence-only
`HEAD^` fallback. Git-bound approval records and the repository review process are
the authority boundary, not cryptographic authentication of a person's identity.

Strictly additive Python inventory is distinct from changing gate behavior. A
single-parent commit may add canonical, newly introduced regular Python files
under `services/`, `tests/` or `tools/` to `quality-scope.json`, before or after UI
implementation. Existing entries retain their order; metadata and governed roots
remain unchanged. The commit may not also change UI implementation or any other
UI gate control. Every commit is checked, including intermediate changes later
reverted. Missing, pre-existing or redirected sources, removal/reordering, and
all other quality-scope changes still require the existing independent control
maintenance process. This does not alter task or reference authority.

For an opt-in resumed amendment, authenticate its adopted correction before
classifying inherited control changes. An exact control-changing commit inside
one completed, independently reviewed correction submission is inherited work,
not self-modification by the resumed task. Its entire changed-path inventory
must be covered by that reviewed range. The range comes from authenticated
approval/submission/review/adoption records, never caller-supplied contract data.
Unknown, overlapping, extra-path, merge and later unreviewed changes remain denied;
the original task base and full per-commit traversal do not change.

Earlier bounded maintenance can use its existing
`bounded-governance-maintenance-independent-review` carrier instead of a newer
GOV-MAINT projection. Recognition authenticates its sole-parent candidate,
evidence-only and review-only deliveries, immutable full source hashes/blobs,
independent accepted disposition with no findings, and control-only scope before
the authenticated correction task start. It does not create a retrospective
approval or authorize product/launcher changes. Subsequent control modifications
still need their own exact review. The complete public UI gate must pass; these
individual provenance checks are not task completion evidence on their own.
