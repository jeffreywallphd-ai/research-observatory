# Planning guide

Use this entry before selecting, resuming, or changing planned work. Read the
identity rules and lifecycle below, then only the section triggered by the action:

| Action | Additional section |
|---|---|
| Prepare a new Wave/first capability or refresh a proposed contribution | Initiation assessment; templates and validation |
| Change approved authority or inspect an existing amendment | Authority changes |
| Submit task evidence or operate a lease | [Task operations](../docs/automation/codex-tracking-guide.md); not historical recovery material |
| Interpret an actual historical recovery record/hold | [Historical recovery](../docs/automation/project-automation-guide.md#23-governance-recovery-controller); do not use it for a new defect |
| Request feedback, approval, or handle a pending gate | Decision handoff |
| Investigate ledger/schema/readiness failure | Relevant validation section and the exact reported contract |

A read-only code question does not require this guide unless planning identity
or authority is involved. Linked references are conditional, not a reading list.

## Identity and generated views

`backlog.yaml` controls IDs, dependencies, Waves, gates, status, claims, leases,
and evidence. `backlog.schema.json` is its executable Draft 2020-12 contract;
taskctl also enforces semantic invariants. Do not hand-edit around transitions.

Waves are the durable execution axis; each exit gate activates the next Wave
except at the roadmap end. Capability aliases and descriptive slice labels
supplement immutable numeric IDs. Use full task designators in progress updates.

Capability plans resolve material/cross-slice decisions; slice plans expand
their existing tasks. `review-site/` is generated, not another authority.
`../docs/planning-implementation-plan.md` and `status-summary.md` are entirely
generated from the backlog. After every successful ledger mutation:

```bash
python tools/backlog_views.py --repo .
python tools/backlog_views.py --repo . --check
```

Generation uses one immutable backlog snapshot, compares canonical UTF-8 bytes,
confines paths to the repository, and atomically replaces changed outputs.
Unchanged outputs keep their bytes and modification times. Check mode detects
byte corruption without decoding; failures must be reported, not hand-repaired.

## Default planning and execution lifecycle

One pre-Wave approval binds the complete Wave packet at one immutable commit.

Every decision must present at least two credible candidates, a recommendation
and rationale; the reviewer records any override with its rationale.

1. Identify the earliest unfinished global Wave and its exit gate.
2. **Only for a proposed Wave:** prepare missing plans; assess the current
   implementation; resolve all binding capability decisions, ordered slices,
   cross-capability interfaces/dependencies, risks, rollback/recovery,
   verification, and exit criteria. Review and approve the entire packet once.
   Inherited/future context is visible but not authorized.
3. **For an approved Wave:** verify readiness and start or resume the same
   campaign using [task operations](../docs/automation/codex-tracking-guide.md#before-editing).
   Never reapprove or backfill its frozen planning packet.
4. Claim only the next dependency-eligible READY task in that Wave. Perform
   risk-selected task-start planning, implement, commit, verify, submit, obtain
   independent disposition, and integrate tested work locally.
5. Independently review each integrated slice; record affected risk-cluster
   checkpoints. Capability/slice boundaries do not create human approval stops.
6. After every Wave slice is approved, run fresh full affected/repository/profile
   qualification and independent Wave review. Only an APPROVED completion can
   proceed to the separate human exit/next-Wave activation gate.

The campaign survives process/session interruptions. An expired lease may be
renewed only by its recorded owner. Later-Wave work stays gated.

## Initiation assessment and controlled planning adaptation

Plans are working hypotheses during initiation. Before a new Wave packet is
frozen, assess the tested current implementation against the Vision, accepted
architecture, current primary best-practice sources for the core planned work,
and the proposed Wave outcome. When a capability is first planned, record the
same assessment at capability scope. A capability contributing to a later Wave
needs only a concise refresh of facts that materially changed.

Record the assessment in the capability plan under **Initiation assessment and
planning adaptation**. Include a capability baseline and a Wave-specific refresh
for each Wave in which its decisions or slices become binding. The generated
Wave packet makes those contributing assessments reviewable through its linked
capability plans; no separate controller or approval is created.

Each assessment must state:

- the implemented baseline relevant to the planned work, including sound
  boundaries to reuse and weaknesses or debt that would impair the outcome;
- whether the existing Wave/capability plan is still the best fit for the
  product Vision, accepted architecture, and current best practice;
- plan adaptations made for product fit rather than implementation convenience;
- support improvements added because the current implementation is too weak for
  the planned work; and
- the refactoring budget calculation and disposition of anything outside it.

Tested code remains authoritative evidence of current behavior, but current
behavior does not set the desired direction. Within accepted architectural
authority, Vision and best practice take precedence over adapting the plan to a
weak implementation. A conflict with an accepted ADR or higher-authority source
uses the repository mismatch/ADR process; it is not silently decided here.

Initiation planning must not decide a major refactor of completed work. An item
added by the assessment that alters previously implemented structure or behavior
is technical-debt refactoring. Calculate, at both
capability and Wave scope:

```text
refactoring share = assessment-added technical-debt refactoring effort
                    / pre-assessment forecast effort of already planned implementation work
```

The share must be no greater than `0.15`. Record the common estimation unit and
both values. Raw task count is acceptable only when the plan deliberately uses
size-normalized tasks. Do not rename or split refactoring to evade the limit.
Bind the pre-assessment baseline to its itemized atomic task IDs and estimates,
a recorded assessment date. Never count both a slice and its child tasks. Mixed
new/refactor items allocate the refactoring effort separately. The existing Wave
calculation deduplicates task and allocation IDs across capability contributions
and recomputes the arithmetic; independent reviewers determine whether the
baseline and estimates are credible. The approved Wave commit, rather than a
second planning-history controller, freezes the accepted record. Keep the core
of the plan new or previously planned product work.

For this rule, a major refactor includes changing an accepted architectural
decision, replacing a foundational runtime or data boundary, or restructuring
multiple completed capability outcomes. If necessary support exceeds the limit
or entails such a refactor, record it as future enabler/capability work or raise
an explicit roadmap/architecture decision. Do not conceal it in initiation
planning. A Wave or capability that cannot safely deliver its outcome within
the allowed support boundary is not ready for approval.

Proposed plans may be freely improved during this assessment. Once the complete
Wave packet is approved at its immutable commit, the assessment and resulting
scope are frozen with it and the normal append-only amendment rules apply.

## Authority changes

Routine debugging/restoration stays in its approved open task. A completed-task
regression uses the [bounded linked correction](../docs/automation/workflow-efficiency.md#use-the-linked-correction-route);
automation/evidence defects use [bounded maintenance](../docs/automation/workflow-efficiency.md#bounded-maintenance).
Neither route authorizes changed product scope or rewrites completed history.

Changes to approved scope, security authority, migration guarantees, governed
experience, or release criteria require append-only amendment and human approval,
including reductions/replacements. Pause at a quiescent boundary; bind the
predecessor and exact proposed scope, obtain independent packet review and human
approval, then use the [amendment procedure](../docs/automation/project-automation-guide.md#22-controlled-enabler-amendment-lane).
An approved Wave itself is never edited or approved again.

GOV-MIG-0001 retires new incident-numbered GRR/GCR requests and supplements.
Historical packets/controllers remain validation inputs, not a route for new
repairs. The generic kernel/store remain evidence-only; current W1 mutations use
the taskctl compatibility adapter. Do not infer activation from the migration
design or a receipt.

## Decision handoff

Before requesting a decision, override, approval, or readiness remedy, use the
[decision-complete handoff](../docs/automation/project-automation-guide.md#31-decision-complete-stopped-gate-handoff).
It includes supported openable packet links and repository-relative paths,
criteria, incomplete prerequisites, alternatives, a recommendation and exact
approval/resume condition. G1 means W1 exit/W2 activation.

If preceding work or evidence is incomplete, keep the gate PENDING and recommend
the prerequisite sequence, deferral, or governed replanning. Ask how to handle
the stop, not for premature release approval. Chat feedback, a feedback export,
planning approval, and local integration are not release approval.

Read [review-site instructions](../docs/automation/planning-review-site.md) only
for the needed operation. Decisions offer candidates plus Other. Other requires
a brief description and detailed rationale; non-recommended choices require
rationale. Applying feedback materializes the choice, never execution approval.

## Canonical planning commands

From the repository root; use the repository's configured Python environment.
These are action-specific examples, not a sequence to run on every resume.

```bash
# Proposed planning only:
python tools/planctl.py --repo . wave prepare WN
python tools/planctl.py --repo . wave validate WN
# Review/approval request only:
python tools/planctl.py --repo . wave review WN
python tools/planctl.py --repo . apply-feedback CAP-XX <feedback.json>
python tools/planctl.py --repo . wave approve WN --by "<reviewer>" --commit <git-sha>
# Approved campaign readiness; never approve it again:
python tools/planctl.py --repo . wave ready WN --require-approved
# Existing or proposed authority-changing amendment only:
python tools/planctl.py --repo . ecr review ECR-NNNN
python tools/planctl.py --repo . ecr validate ECR-NNNN --require-approved
python tools/taskctl.py --file planning/backlog.yaml amendment status WN.ANN
```

Execution commands live in [task operations](../docs/automation/codex-tracking-guide.md#command-sequence);
historical recovery mutation examples are intentionally absent here.

## Templates and validation

Use these only when creating/changing the corresponding plan or investigating
its validation failure:

- Capability: `capability-plans/TEMPLATE.md`,
  `capability-plans/capability-plan.schema.json`,
  `../tools/capability_plan_check.py`.
- Slice: `slice-plans/TEMPLATE.md`, `slice-plans/slice-plan.schema.json`,
  `../tools/slice_plan_check.py`.
- Site: `../tools/plan_review_site.py`, `../tools/plan_review_check.py`.
- Ledger: `backlog.schema.json`, `../tools/taskctl.py --file planning/backlog.yaml validate`
  (from repository root).
- Task-start worksheet: [task-start planning](../docs/automation/task-start-planning.md).

Missing classification or planning must be resolved before the complete Wave
approval. The prospective `planning_policy_version: initiation-assessment-1.0`
requires structured assessments and applicable refreshes for W2 and later.
Validation recomputes both 15% bounds and rejects invalid task identities and
major-refactor allocations; independent reviewers judge the underlying estimates
and product/architecture fit. It does not rewrite earlier approvals.

Backlog validation identifies structural/type/status/timestamp errors, duplicate
IDs, invalid parent namespaces/review metadata, missing dependencies and exact
dependency cycles. Mutations use exclusive-lock compare-and-swap publication;
races, invalid states and failed replacements leave the predecessor intact.
Schema-only validity is not authority for an illegal transition.

Evidence/lease checks and historical exceptions are documented once in
[task evidence](../docs/automation/codex-tracking-guide.md#evidence).
Read them before submission/review or when diagnosing that boundary.

## Replanning conditions

Reopen planning only for demonstrated infeasibility, consequential new evidence,
unavailable required service/credential/platform/hardware, higher-authority
conflict, required governed-reference change, or explicit user redirection.
Update only affected authorities, regenerate derived views, obtain required
approval, and resume the same campaign.
