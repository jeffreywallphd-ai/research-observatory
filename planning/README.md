# Planning guide

Use this entry before selecting, resuming, or changing planned work. Read the
identity rules and lifecycle below, then only the section triggered by the action:

| Action | Additional section |
|---|---|
| Prepare a new Wave/first capability or refresh a proposed contribution | Initiation assessment; templates and validation |
| Add or review refactoring during an approved Wave | Locked-Wave refactoring budget; authority changes if scope changes |
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

These commands update Markdown, not `review-site/` HTML. After status, review,
or task-start worksheet changes, also regenerate the HTML using the
[task command sequence](../docs/automation/codex-tracking-guide.md#command-sequence).
Validate the regenerated site before committing it.

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

Use rolling-wave planning: the current approved Wave is detailed and understood;
distant Waves describe provisional outcomes, dependencies, assumptions, and risks.
Their existing slice/task details are forecasts, not immutable commitments.
Refine or replace those unapproved details as earlier Waves deliver evidence.
Only the upcoming Wave's binding inventory must be decision-complete for its
approval; do not force distant decisions or full slice designs prematurely.
Preserve immutable IDs/history and distinguish inherited binding authority from
unapproved future context.

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
- the itemized implementation estimate, planned redesign/refactoring, and
  disposition of deferred work, including changes inherited from earlier Waves.

Tested code remains authoritative evidence of current behavior, but current
behavior does not set the desired direction. Within accepted architectural
authority, Vision and best practice take precedence over adapting the plan to a
weak implementation. A conflict with an accepted ADR or higher-authority source
uses the repository mismatch/ADR process; it is not silently decided here.

There is no percentage limit on assessment, replanning, or refactoring selected
while the upcoming Wave is unapproved. Major redesign may be included when
needed for product fit, current practice, or earlier Wave changes. This includes
replacement of a foundational runtime/data boundary or restructuring completed
outcomes, provided the required ADR, migration/recovery, experience, and human
approvals are resolved before implementation. A mutable plan is not permission
to rewrite an earlier approval or execute later-Wave work early.

Record one estimation unit and itemized atomic task estimates for the resulting
plan, including explicit redesign/refactoring allocations. Mixed tasks identify
their refactoring portion. Never count both a slice and its children or count a
shared allocation twice. Reviewers assess product value, estimates, and
architecture fit; the complete Wave approval freezes the selected scope and
estimate. Future portions of a cross-Wave capability remain mutable; its already
binding decisions require amendment or an approved architectural successor.

Proposed plans may be freely improved during this assessment. Once the complete
Wave packet is approved at its immutable commit, the assessment and resulting
scope are frozen with it and the normal append-only amendment rules apply.

## Locked-Wave refactoring budget

After approval, supplemental technical-debt refactoring beyond the selected
scope must satisfy `R <= 0.15 * P`. `P` is the itemized implementation effort
frozen at the current Wave's original approval; `R` is cumulative supplemental
refactoring performed plus committed remaining refactoring effort in that Wave.
The budget protects delivery of the agreed features while allowing improvements.
Approval of the next Wave resets the budget: its own locked estimate becomes
`P` and supplemental consumption starts at zero. Neither unused allowance nor
past spending carries forward. Refactoring deferred into that Wave is classified
there as explicitly approved planned scope or a later supplemental allocation;
the same work must not be charged twice or hidden between Waves.

- Charge capability, slice, task, correction, maintenance, and amendment work to
  this one Wave budget. Child allocations are subsets, not fresh 15% allowances.
  Refactoring software delivered in a past Wave is charged to the executing
  Wave, never to the past Wave's unused allowance or a future Wave.
- Redesign/refactoring explicitly selected before the Wave was frozen is planned
  scope and remains executable. Only additions or overruns beyond its approved
  allocation enter `R`; otherwise allowing major redesign at initiation would
  become an unusable approval. Do not retroactively relabel added work as planned.
- Include structural cleanup and debt repayment wherever performed. Ordinary
  implementation and defect restoration are not automatically refactoring, but
  mixed work must charge its actual refactoring portion. Do not relabel cleanup
  as debugging, split tasks, or exclude abandoned/spent work to evade the budget.
- Keep the original `P`, unit, approval commit, atomic task IDs, and allocation
  identities fixed. Amendments and estimate increases do not enlarge `P` or
  reset `R`. Use estimates from one recorded basis, not raw task counts unless
  deliberately size-normalized. Check forecast before commitment and reconcile
  spent/remaining effort at review and checkpoints without double counting.
- Record the cumulative calculation and prior allocation references in existing
  task/amendment evidence; independent review checks completeness and arithmetic.
  No new campaign, task state, or controller is required. The existing historical
  ECR per-packet checks alone do not establish this cumulative budget.

The budget is not a change allowance for immutable criteria or architecture.
Even below 15%, scope/security/migration/experience/release changes still require
the normal amendment and human approval. Above the limit, defer optional work
to an unapproved future Wave for unrestricted replanning. If required work cannot
fit, stop only that affected work and present an explicit owner decision about
deferral or a separately authorized exception; never infer one from general
permission to continue. New major redesign normally belongs in upcoming planning.

Apply this rule prospectively without rewriting frozen assessments, amendments,
or historical exceptions. For an active older Wave, append an evidence-based
reconciliation of its original approved estimate and known prior supplemental
allocations before claiming more refactoring capacity. Missing historical effort
is unknown, not zero; do not invent precision or assume unused budget. Previously
authorized work remains authorized under its exact recorded scope. This policy
change itself neither approves a new product refactor nor reopens a released task.

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
approval. New W2-and-later packets use
`planning_policy_version: initiation-assessment-2.0`: structured assessments,
itemized estimates and applicable refreshes, without an initiation percentage
cap or blanket ban on major redesign. Validation rejects invalid identities and
duplicate allocations; reviewers check architectural authority and the locked
execution budget. Version 1.0 validation remains for historical records, not new
approvals. Neither version backfills earlier approved packets.

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
