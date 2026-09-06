# Workflow efficiency without weaker acceptance

This is operating guidance under GOV-MIG-0001, not a new controller, approval,
or task state. It applies prospectively. Historical approvals, adverse findings,
evidence and released work remain immutable. The aim is deterministic acceptance
and traceability with less duplicate work, not a promise of zero defects.

## Reading map

Read only the sections triggered by the current action, completely and with
their prerequisites; reuse unchanged guidance already available in context.

| Action | Sections to read |
|---|---|
| Unsure which repair route applies | Choose the smallest lawful route |
| Restore an approved completed task | Use the linked correction route |
| Repair operating guidance or automation/evidence controls | Bounded maintenance; affected migration implementation only if needed |
| Start/remediate/review a task | Freeze acceptance; Review each boundary once; Fast checks first |
| Collect qualifying evidence | Stable snapshots and coordination; Automatic receipts and safe reuse |
| Reuse prior results instead of executing checks | Automatic receipts and safe reuse in full; unknown input closure means fresh checks |
| Touch privacy hooks, admitted historical metadata or prospective local bindings | Historical private metadata |
| Report efficiency, time, tokens or cost | Measure before promising savings |

## Choose the smallest lawful route

- Continue an open approved task for debugging and restoration inside its
  contract. Do not write a new plan for each failed test.
- A completed task's restorative defect uses a linked corrective task, with
  inherited authority and independently reviewed regression/integration proof.
  Preserve the original task and adopted amendment; do not reactivate them.
- An automation/evidence-control defect uses one bounded maintenance increment:
  exact predecessor, intended delta, invariant boundaries, selected tests, and
  independent control review. Reuse a concise evidence note; do not create a
  GRR, GCR, bootstrap or incident-specific controller.
- A change to approved product scope, security authority, migration guarantees,
  a governed reference or release criteria requires append-only amendment and
  human approval, including reductions/replacements. Destructive/irreversible
  actions, external effects, substantial spend and release decisions also
  require human authority. A correction label cannot confer it.

Use full task designators in progress updates. State the outcome being proved
and any genuine blocker, rather than narrating every command.

## Bounded maintenance

For an operating-guidance or automation/evidence-control defect that preserves
approved authority:

1. Stop the affected mutation at a quiescent, recoverable boundary.
2. Bind the exact predecessor bytes, intended delta, risk tier and invariants.
3. Make the smallest generic correction; no new GRR/GCR, bootstrap, control
   revision or identity-specific controller to repair another controller.
4. Run risk-selected checks, including real persistence/Git boundaries when
   affected. Documentation-only changes need route/link and obligation review,
   not unrelated product/platform suites.
5. Obtain independent review before integration when security, migration,
   evidence, public contracts or control authority are affected; then use the
   [local integration procedure](project-automation-guide.md#11-local-main-integration).

Reuse a concise maintenance/evidence note; this is not a new task state or human
approval gate. Preserve historical records, adverse findings and safety rules.
Any supplemental refactoring in a repair uses the current Wave's shared
[refactoring budget](../../planning/README.md#locked-wave-refactoring-budget);
the maintenance label does not exempt structural cleanup or debt repayment.
Actual authority changes use the amendment route above. The generic kernel/store
remain evidence-only; current W1 mutations use the taskctl compatibility adapter.
Read [migration detail](governance-automation-simplification.md) only when the
affected adapter, kernel, store or historical boundary requires it, not for
every maintenance increment.

## Use the linked correction route

The initial adapter supports an original DONE, independently approved task in
the current unreleased Wave. Its amendment, if any, must already be adopted.
Pause ordinary execution at a clean, committed boundary with no competing
task, review, recovery hold or unfinished amendment. Do not use this route to
repair a released Wave, change a governed reference, or introduce new criteria.

Commit one small spec at `artifacts/evidence/WN.CNN.T01.spec.json`, using the
next sequential correction number for that Wave. The spec has exactly these
fields: `schemaVersion: "1.0"`, `kind: "authority-preserving-correction"`,
`origin` (`taskId`, ancestral `commit`, and `sha256` of the canonical original
task snapshot), `reproduction`, `changedPaths`, and `impactAnalysis`.
Use `taskctl.corrective_origin_snapshot` and `taskctl.canonical_json_sha256`
for the snapshot digest; do not hash a rendered page or manually selected
subset. Exact product/test paths are required. The adapter deliberately rejects
authority, migration, permission and other unsupported paths; rejection is not
permission to relabel the change.

From the repository root, the command shape is:

```text
python tools/taskctl.py --file planning/backlog.yaml correct <original-task-id> --from artifacts/evidence/WN.CNN.T01.spec.json --agent <agent> --branch <branch> --base-sha <current-commit> --worktree . --profile LOC --platform windows-x64
```

This atomically appends and claims the correction in
`waves[].campaign.corrective_tasks`. It inherits the original title, objective,
criteria, dependencies and verification inventory. The original history stays
unchanged and the ordinary Wave stays PAUSED. Existing `show`, `checks`,
`next`, `status`, submission, review and telemetry commands include the new
full task designator; no new slice or amendment is invented.

Submit with the usual `submit <correction-id> --agent <agent> --from <manifest>`.
Alongside normal criterion evidence, the manifest's `correctiveIntegration`
binds `originSha256`, `authorityPreserved`, actual `affectedChecks`, explicitly
listed `reusedEvidence`, and a `rationale`. The independent review ledger adds
`corrective_integration` with the frozen `evidence_sha256`,
`authority_preserved`, `affected_integration_reviewed`, and `notes`. These are
review assertions, not substitutes for actual regression/integration evidence.
Approval is required before ordinary Wave resume. Failed reviews use the
existing append-only finding and remediation rounds.

New ordinary task/campaign bindings and Wave resume records use repository-
relative `worktree: "."`, resolved against the canonical backlog repository,
not the process working directory. Existing non-null historical bindings retain
their exact spelling. Legacy bootstrap/recovery-specific writers are not
modernized by this increment; they receive no new private-field exception.

## Freeze acceptance, not learning

At task start, identify the approved criteria and material failure boundaries.
Keep the acceptance-closure map as small as the risk permits. A review finding
must name the criterion or material contract it violates, a reproduction and
the smallest adequate closure. New evidence of a safety or correctness defect
still matters; an optional adjacent improvement does not become a stop condition.

Owner acceptance of styling closes discretionary cosmetic iteration. Retain
functional, accessibility, security, privacy and integrity checks. Record new
optional suggestions for later selection instead of repeatedly reopening a
completed styling result.

## Review each boundary once

| Stage | Required focus |
|---|---|
| Task | Independent disposition of scope, truthful evidence, changed contracts and credible failure paths. |
| Slice | Affected integration and adversarial behavior across the task boundaries. |
| Checkpoint | Accumulated affected checks, build/smoke, shared-interface identities and open risks. |
| Wave exit | Fresh full matrix, cross-capability qualification, independent Wave review and human release decision. |

High-risk tasks still receive expanded review. At later stages, cite and
authenticate already reviewed proof; rerun it only for changed inputs, inadequate
coverage, suspect provenance, observed failure, or an explicit fresh-run
criterion. Record that impact reason. Remediation replays open findings and the
incremental risk boundary, not the entire speculative audit. Reviews and human
approvals themselves are never cached or inferred from receipts.

## Fast checks first; essential native checks remain

Prefer deterministic unit, contract and real-boundary integration tests for
routine regressions. Use native/UI automation for behavior that those checks
cannot establish: OS dialogs, focus, accessibility, actual renderer/native
wiring, platform packaging and other required principal boundaries. A mocked
dialog does not prove a native dialog worked. A static check does not prove
runtime behavior. Select risk-appropriate evidence and label its limits.

Keep broad profiles at slice/checkpoint/Wave scope unless an explicit criterion,
shared-infrastructure impact or unlocalized failure requires them earlier.
`verify.py` affected selection is an impact aid, not a complete dependency
closure and not an automatic cache key. Full Wave qualification stays fresh.

## Automatic receipts and safe reuse

Prefer tool-generated facts over hand-transcribed command results. A receipt
should bind the candidate, exact inputs and producer, selected command,
exit/disposition, timing and output digests. It does not decide whether a test
proves a criterion. Keep criterion mapping and independent judgment explicit.
Transition receipts likewise report what was persisted; they never authorize
the next mutation or replace the backlog.

Evidence reuse requires all of the following:

1. A deliberately closed and reviewed input set: source, tests, fixtures,
   command arguments, configuration, toolchain, actual installed dependencies,
   environment and relevant platform facts. Version strings and lockfiles alone
   do not identify installed executable bytes.
2. Exact equality of those inputs and the required coverage. Unknown or changed
   input means run fresh; no optimistic fallback to a prior PASS.
3. Independently trusted producer/delivery provenance and the exact prior
   receipt digest. A JSON document's own hash is not proof of execution.
4. Clear `fresh` versus `reused` provenance. Never present old duration or a
   prior native/platform run as a fresh observation. Preserve failure attempts.
5. No fresh-run requirement. Native/principal proof, benchmarks and full Wave
   qualification are fresh-only in the initial local pilot.

The initial pilot is deliberately narrow: isolated pure governance-receipt unit
tests, not a general repository cache. Where installed runtime closure is not
fully authenticated, receipts remain useful but reuse stays disabled. Do not
add a build-system migration, cloud cache or signing service just to accelerate
small local tests. Expand reusable workloads only with measured benefit and
independent evidence-control review.

## Stable snapshots and coordination

Use a committed candidate for qualifying verification. Before a run, tell other
agents the exact input boundary and keep shared HEAD fixed until it ends.
Parallel work is useful only outside that boundary. For isolated test runners,
execute the verified snapshot itself, not the live worktree after hashing it.
Before/after equality alone does not prove absence of transient mutation.

If inputs change, keep the failed/drift receipt and rerun affected checks at the
new stable candidate. Do not reinterpret the result as a pass. Independent
workers must not commit while another worker is collecting commit-bound proof.

## Historical private metadata

Keep the approved privacy baseline fixed. A sealed, independently reviewed
preservation policy may automate equality checks for already admitted metadata
at the same typed logical fields and exact raw representation. It must reject
changed, moved, copied, aliased, newly disclosed or re-encoded private fields.
Existing exact historical admissions remain valid for their own bytes.

Run credential scanning on the full unmasked content, including historical
metadata lines. Never treat a preservation rule as a credential exception.
New local accounts, absolute user paths, sessions and runtime settings belong
in ignored machine-local files, not new repository fields. `.gitignore` is a
boundary for local files, not a scrubber for values inserted in tracked files.

## Measure before promising savings

Use automatic wall-clock durations for setup/snapshot, execution, review and
publication where actually observed. Keep historical producer time separate
from current lookup time. Report token, credit or monetary cost only when an
actual usage source supplies it; otherwise mark it unavailable. Do not infer
cost from elapsed time or invent a before/after baseline.

Pilot the new route on one bounded correction after independent control review.
Compare like-for-like criteria, findings, executed checks and measured elapsed
time. Report whether administrative work and repeats decreased without losing
coverage. A receipt/test pilot is not completion of the pending product task,
slice, Wave or release gate.
