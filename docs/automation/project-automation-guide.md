# Research Observatory project automation guide

Read only the section for the current action. Use §2 for Wave/amendment scope,
§3 for an actual stop/decision, §5 for slice/Wave closure, §6 for intentional
experience changes, §8.1 for verification selection, §8.2 for review depth,
§8.3 for benchmark evidence, and §11 for local integration. §2.3 is historical:
read it only for a retained recovery record/hold, never as a new repair recipe.
Follow linked procedures only when their stated trigger applies.

## 1. Operating objective

Enable an AI coding tool to execute long-running, production-oriented Wave
campaigns while preserving architecture, evidence, security,
privacy, rights, research integrity, user-experience governance, and human
authority over consequential decisions.

## 2. Wave campaigns

Use Roadmap -> durable Wave campaign -> Capability contribution -> ordered Slice
-> Task -> risk-cluster checkpoint -> Wave exit gate. The controller owns one
Wave lease and selects its next dependency-eligible task across contributing
capabilities. Capability
numbers are immutable foreign keys, not execution order; descriptive aliases are
the default display. Slice numbers preserve real sequence and are shown beside a
descriptive slice label.

### 2.1 One approval and durable-Wave meaning

Before preparing a proposed Wave, use the complete
[planning lifecycle and initiation assessment](../../planning/README.md#default-planning-and-execution-lifecycle).
Every binding capability decision and ordered slice, cross-capability interface,
risk, rollback/recovery duty, verification matrix and exit criterion must be
decision-complete and approved together at one immutable commit.
Inherited/future decisions remain visible but unauthorized. Recommendations
are selected unless the pre-Wave reviewer records an override and rationale.

Readiness must pass before start/resume. Existing approved packets are immutable;
do not reapprove them or add a retrospective initiation gate.
One campaign survives process/session interruptions and capability boundaries.
Continue through independent slices, checkpoints, fresh full qualification and
independent Wave review; routine debugging or approved transitions need no new
human permission.

### 2.2 Controlled enabler amendment lane

Read this section only for an actual change to approved authority or an existing
amendment. Changes to approved scope, security authority, migration guarantees,
governed experience or release criteria require independent packet review and
explicit human approval, including reductions/replacements. Pause at a quiescent
boundary with no ordinary task IN_PROGRESS or REVIEW; bind the predecessor and
exact changed scope in an immutable ECR. Do not edit/reapprove the original Wave.

Routine restoration and control repairs instead use
[correction/maintenance](workflow-efficiency.md#choose-the-smallest-lawful-route).
An automation failure alone does not trigger ECR/bootstrap work.

For an authority-changing or already authorized amendment:

```bash
python tools/planctl.py --repo . ecr review ECR-NNNN
python tools/planctl.py --repo . ecr validate ECR-NNNN --require-approved
python tools/taskctl.py --file planning/backlog.yaml amendment status WN.ANN
python tools/taskctl.py --file planning/backlog.yaml amendment bootstrap-resubmit WN.ANN --agent <agent> --implementation-commit <head> --evidence <manifest>
```

The approved ECR is inert until its bounded bootstrap is implemented, evidenced,
and independently approved. Materialization must reproduce the packet's exact
task IDs and hashes. Activation creates a separate amendment lease while the
ordinary Wave remains paused. `status`, `next`, and `next-capability` must show a
decision-complete amendment stop; they must not advertise Wave start or repeated
Wave approval. Adoption requires independently approved tasks and exit review
plus a control/security checkpoint, and leaves the Wave paused for explicit
resume. Older tools must fail closed once executable amendment state exists.
After an ordinary session interruption, the recorded amendment owner renews an
expired active campaign with `taskctl amendment renew WN.ANN --agent <agent>`;
task leases are renewed separately. Renewal changes no scope, task state, Wave
hold, owner, branch, worktree, profile, platform, or approval authority.
If bootstrap review requests changes, record that disposition before remediation.
`bootstrap-resubmit` then appends the prior frozen candidate, evidence, and review
to the attempt history and opens a new review projection only for a strict
descendant candidate. Validation rechecks every attempt, the exact packet task
definitions, the Wave hold, campaign state, and active-amendment marker at every
subsequent transition. Each attempt also freezes its submission branch: stored
evidence is validated against that branch permanently, while the live checkout
branch is checked only when submitting or recording the independent review.

Exit and adoption use the same immutable discipline:

```bash
python tools/taskctl.py --file planning/backlog.yaml amendment submit WN.ANN --agent <agent> --from <committed-exit-evidence>
python tools/taskctl.py --file planning/backlog.yaml amendment review WN.ANN --reviewer <independent-reviewer> --result <result> --from <review-ledger>
python tools/taskctl.py --file planning/backlog.yaml amendment adopt WN.ANN --agent <agent> --from <committed-checkpoint-evidence>
```

The exit packet binds the evidence blob and Git commit, codex branch, approved
ECR criteria, and selected checks. The review ledger binds the exact submitted
backlog state and preserves severity-ranked findings and closures across later
rounds. Adoption accepts only a committed path/SHA/commit checkpoint reference
whose payload identifies the amendment and exact approved completion history.
Missing, replaced, stale, forked, dirty, or unreviewed evidence is denied.
Pre-control amendments stay truthful and receive no fabricated rounds.

### 2.3 Governance recovery controller

Historical only: GOV-MIG-0001 retires new GRR/GCR requests and supplements.
Read the following descriptions only to interpret a retained record or hold;
imperative examples describe that historical protocol, not present permission.
New control defects use [bounded maintenance](workflow-efficiency.md#bounded-maintenance).
Do not execute a historical mutation without its still-applicable exact authority
and current-controller validation. No new recovery layer is authorized.

An existing ACTIVE historical hold denies ordinary mutations except its exact
separately approved lane. B00/BNN approval does not approve the later ECR or gate.
Keep the hold until the bound amendment adoption/security checkpoint authorizes
release; release still leaves the Wave PAUSED.

Before that migration, if the installed ECR schema/controller could not represent the next required
amendment, stop at a quiescent Wave boundary and use the separately reviewed
GRR workflow. Do not edit the approved Wave, reuse `wave approve`, or mutate the
broken lane before GRR approval.

```bash
python tools/recoveryctl.py --repo . validate GRR-NNNN --require-approved
python tools/recoveryctl.py --repo . status GRR-NNNN
python tools/recoveryctl.py --repo . bootstrap-start GRR-NNNN --agent <agent>
python tools/recoveryctl.py --repo . bootstrap-submit GRR-NNNN --agent <agent> --implementation-commit <HEAD> --evidence <manifest>
python tools/recoveryctl.py --repo . bootstrap-review GRR-NNNN --reviewer <independent-reviewer> --from <finding-ledger>
```

Evidence maps every approved B00 outcome and criterion, lists the exact
approval-to-candidate Git diff, records unique passing checks and an empty
unverified list, and stays within canonical root-confined paths. The controller
rejects absolute, backslash, dot-segment, traversal, symlink, junction, or
resolved escapes before access. Changes-requested or blocked B00 review uses
`bootstrap-resubmit` with a strict descendant and retains the earlier ledger.
After B00 approval, prepare the named ECR using the packet version bound by the
active recovery hold (v3 for a successor hold); its separate approval is
still mandatory. `recoveryctl release` is legal only after that amendment is
adopted with a bound security checkpoint and leaves the Wave paused.

If approved B00 execution reveals a latent defect that prevents only the exact
approved repair amendment from materializing, use the existing hold's
sequential supplemental lane:

```bash
python tools/recoveryctl.py --repo . supplement-start GRR-NNNN.SNN --agent <agent>
python tools/recoveryctl.py --repo . supplement-submit GRR-NNNN.SNN --agent <agent> --implementation-commit <HEAD> --evidence <manifest>
python tools/recoveryctl.py --repo . supplement-review GRR-NNNN.SNN --reviewer <independent-reviewer> --from <finding-ledger>
python tools/recoveryctl.py --repo . supplement-resubmit GRR-NNNN.SNN --agent <agent> --implementation-commit <HEAD> --evidence <manifest>
```

The packet and approval precede `supplement-start`. The latest BNN remains the
only executable recovery unit; until its independent approval, taskctl denies
the repair amendment and every ordinary mutation.

An approved amendment may install a task-specific historical-candidate recovery
only when replaying the product change would destroy truthful evidence lineage.
The controller is not a general reopen or override. It must name one exact task,
approved amendment, recovery hold, historical commit chain, evidence contract,
changed-path set, and executable check inventory in a committed canonical
manifest. The transition remains unavailable until amendment adoption, its
bound control/security checkpoint, hold release, and an explicit ordinary Wave
resume are all independently visible in the backlog.

```bash
python tools/taskctl.py --file planning/backlog.yaml recover <exact-task> \
  --agent <wave-owner> --branch <codex-branch> --base-sha <clean-HEAD> \
  --worktree <canonical-repository-path> --profile <profile> --platform <platform> \
  --from artifacts/evidence/task-recovery/<exact-task>.json
```

Recovery recomputes Git existence and ancestry, full historical task-state
hashes, the target's immutable task contract, the approved amendment task
inventory, the base-to-candidate paths, immutable evidence-contract bytes,
approved-reference identity, and the manifest's fixed checks. It repeats the
amendment and target-contract checks immediately before its one
compare-and-swap mutation. That mutation preserves the complete original
blocked state in an append-only projection and moves the task only to
`IN_PROGRESS` with a new lease and execution base. A competing backlog write is
rejected without overwrite. Recovery cannot attach evidence, enter review,
approve the task, approve a slice or Wave, or approve a release gate. All normal
commit-bound evidence and independent reviews still follow.

### 2.4 Current task submission

Ordinary/amendment task evidence uses atomic `taskctl submit` and independent
`taskctl review`. Read [task evidence and review](codex-tracking-guide.md#evidence)
before those actions; it defines exact-commit packets, append-only findings,
root-cause escalation and historical compatibility. These are current operations,
not part of the retired recovery recipe.

## 3. Permitted pause conditions

Pause only for:

- approved choice demonstrated infeasible;
- material new evidence creating a consequential unplanned decision;
- unavailable required external service, credential, platform, or hardware;
- higher-authority conflict;
- required approved UI-reference change;
- destructive/external action or substantial unapproved spend; or
- explicit user direction.

Record the condition, update only affected authorities, regenerate review pages, obtain necessary approval, and resume the same Wave campaign.

### 3.1 Decision-complete stopped-gate handoff

Use this section only for an actual decision/override/approval request or gate
stop, not ordinary status updates. Inspect current `taskctl next` output and run
the relevant `planctl wave review WN` / `planctl ecr review ECR-NNNN` command.
Reuse a current generated packet while its inputs remain unchanged; do not
regenerate it for every explanatory message. Before yielding, provide:

1. the gate name, status, criteria, and exact evidence needed for eventual approval;
2. whether approval is currently legal, with counts/identities of unfinished
   preceding-wave work and any upstream pending gates;
3. directly openable links supported by the active client, plus repository-
   relative paths, for the active Wave, relevant capability/slice details and
   every prerequisite packet that materially informs the gate. Use the exact
   generated destinations; prefer absolute local Markdown links in Codex.
   Include a literal `file://` URI only where useful and permitted;
4. credible alternatives and their consequences;
5. a recommended option with rationale; and
6. the exact condition and command shape for approval and Wave resumption.

When prerequisites are incomplete, keep the gate pending and recommend the
legal prerequisite sequence in the earliest unfinished Wave; never claim a
locked successor Wave. Distinguish incomplete work inside the current Wave
from a future gate mentioned by a later slice. G1 is W1 exit/W2 activation,
not a capability or slice stage. Return with criterion-linked evidence. Alternatives are explicit deferral or
governed replanning; neither is implicit gate approval. Never ask a human to
"approve the gate" while `taskctl gate approve` would reject the state.

## 4. Planning automation

For proposed plans/readiness use [planning commands](../../planning/README.md#canonical-planning-commands).
For feedback/export/Other, approval UI or site generation, read the applicable
[review-site section](planning-review-site.md). Other and non-recommended choices
require rationale; applying feedback never approves execution. Do not run
planning commands as a routine task-start checklist.

## 5. Task and slice execution

Use [task operations](codex-tracking-guide.md) for claims, leases, exact-commit
evidence and independent disposition. After claim, use
[task-start planning](task-start-planning.md) only for risks the task can affect;
it is not another approval gate or compulsory standalone document.

A slice completes only after:

- every task passes criterion-linked verification;
- the slice works end to end with adjacent completed slices;
- failure, cancellation, restart, and recovery paths are tested where relevant;
- documentation and migrations are complete;
- no hidden TODO or deferred production blocker remains; and
- an independent reviewer approves the slice.

A Wave completes after all tasks and slices pass, triggered integration
checkpoints are recorded, the complete affected/full suite passes, and an
independent reviewer approves cross-capability qualification. Capability status
is derived from its accepted contributions across Waves.

## 6. Design-first experience-reference governance

Intentional user-facing changes follow this order:

```text
Update style/workflow/page/HTML reference
-> validate reference
-> explicit human approval and new reference ID
-> update material plans
-> implement application
-> run conformance checks
```

Restoring code to an already approved reference needs no new reference or design
approval. Read only affected reference pages/contracts. Never change the reference
after implementation just to make code appear conformant.

The implementation must expose a conformance manifest and pass route, required-region, workflow, token, accessibility, interaction, responsive, theme, and controlled visual-regression tests.

The approved reference is never a deployable application artifact. Do not copy
its HTML, illustrative records, future-capability routes, or nonfunctional actions
into production or development bundles. Implement only the functional regions and
workflows owned by the active capability; keep the full reference in isolated
design/conformance tooling.

## 7. Evidence

Before evidence submission, read [task evidence](codex-tracking-guide.md#evidence)
and [stable snapshots](workflow-efficiency.md#stable-snapshots-and-coordination).
Receipt/input trust is governed by [safe reuse](workflow-efficiency.md#automatic-receipts-and-safe-reuse).
No receipt replaces criterion mapping, execution provenance or independent review.

## 8. Verification and CI

Run fast deterministic checks on every PR; Windows desktop qualification is required during W0-W5. macOS/Linux qualification is added in W6. Expensive live-provider, large-corpus, installer matrix, and performance work belongs in scheduled or release profiles unless a slice explicitly requires it earlier.

### 8.1 Verification breadth by workflow stage

Verification is selected by credible failure likelihood, not by replaying every
available suite at every task:

- **Task implementation and task review:** run focused tests for the changed
  modules, contracts, denial/failure boundaries, and directly affected
  integrations. Run affected lint, format, type, schema, planning, architecture,
  UI, security, or platform checks only when the changed paths can plausibly
  invalidate them. Use the task-start acceptance-closure rows to explain why
  each selected check can prove a material criterion or failure boundary.
- **Slice integration and slice review:** run affected end-to-end, contract,
  failure/denial, cancellation/recovery, accessibility, security, and performance
  checks required by credible slice risk. Do not automatically replay the full
  deployment profile.
- **Integration checkpoint:** when a shared interface, migration, security
  boundary, platform adapter, or coherent cluster of roughly three to five
  slices closes, run the union of affected profiles plus a clean build/smoke
  path. Record contract identities, open risks, and evidence. This is not a
  human approval gate.
- **Wave qualification:** run the complete affected/full repository and
  deployment-profile matrix once, with cross-capability end-to-end, packaging,
  security, accessibility, performance, restart, recovery, and clean-build
  checks.

Task `verification_profiles` and `verification_commands` define coverage domains
and candidate commands. They do not, by themselves, require every command in a
full profile at ordinary task scope. An earlier full-profile run is justified
only by an explicit task acceptance criterion, credible profile-wide impact from
shared verification/build/security/toolchain or dependency/runtime changes, or
an observed failure that cannot be localized. Evidence must name the changed-path
risk analysis, selected checks, any early broad-suite rationale, and the broader
coverage deferred to slice, checkpoint, or Wave review. A reviewer should not demand an
unchanged full-profile replay without identifying a concrete impact path.
`taskctl checks <task>` labels this distinction, offers an affected-selection
preview only when the claim has an exact base, and retains `--raw` for consumers
that need the unchanged command inventory.

### 8.2 Review efficiency and depth

Use [independent review](codex-tracking-guide.md#independent-review) for task
dispositions and finding/closure rules. Slice review is the default deep audit;
checkpoints examine accumulated affected interfaces and risks, and Wave review
qualifies cross-capability release evidence. Do not repeat the same audit at
each boundary. High-risk task review and all explicit criteria remain required.

Use the [efficiency reading map](workflow-efficiency.md#reading-map) before
replaying checks or reusing proof. On the first adverse finding, update the missed
acceptance row and add a focused regression before remediation. Retain all
adverse rounds; the third-submission root-cause requirement is unchanged.

### 8.3 Benchmark evidence

Read this section only when producing/reviewing performance evidence or changing
a benchmark, package-execution boundary or baseline.

Performance baselines are reviewed inputs, not output fields that a benchmark may
rewrite. A benchmark must bind its fixture and methodology, reject non-finite or
out-of-budget baseline values, compare against an immutable reviewed baseline hash,
and write reports only to the confined ignored artifact directory. Establish or
change a baseline only with criterion-linked evidence and independent review.
Artifact benchmarks must authenticate the complete package manifest, inventory,
entrypoint, build contract, and approval evidence before executing code; run an
immutable verified snapshot and recheck it around each lifecycle. Baselines must
retain the raw samples, exact measured hardware, measurement-tool commit/bytes,
and package identity needed to reproduce the comparison. Diagnostic or
measurement-only modes are explicitly nonqualifying, and any failed invocation
must invalidate or overwrite a stale PASS report at the requested destination.
The qualifying invocation must also authenticate the current executing tool and
clean Git state. A package snapshot boundary must deny transient creation,
replacement, deletion, and rename for the whole measured process lifetime—not
only compare inventory before and after execution.

### 8.4 Coverage inventory

Read when maintaining verification profiles or checking Wave coverage, not as
an instruction to run every check for each task. Maintain checks for:

- backlog, plans, and review-site integrity;
- architecture boundaries;
- lint, formatting, and type checks;
- unit/integration/end-to-end tests;
- schema, migration, backup/restore, and recovery;
- security, secrets, dependencies, and supply chain;
- UI-reference conformance and accessibility; and
- platform-specific packaging and smoke tests.

## 9. Safe autonomy

Automate local, reversible, bounded actions. Human authorization is required for external communication, production publication/signing, real credentials, destructive operations, material spend, architecture/experience changes outside approved plans, privacy/rights uncertainty, ethics decisions, study conduct, authorship, final claims, and release approval.

## 10. Instruction maintenance

When changing operating guidance, check affected conditional links, canonical
ownership and instruction conflicts. Preserve substantive obligations and test
representative inspection, task, correction, maintenance, UX, verification and
gate scenarios. Do not create another controller or load unrelated product
guides merely to shorten documents. External setup packs are not runtime authority.

## 11. Local main integration

Integration advances a local Git ref; it does not approve a task/slice/Wave/gate,
change dependencies, or authorize remote effects.

1. Commit the bounded unit and run risk-selected checks against that exact
   candidate with HEAD and inputs stable. Require a clean worktree and successful
   checks; do not integrate known failing work.
2. Complete the required pre-integration independent task/control disposition.
   Keep later slice/Wave/release reviews pending until their own criteria pass.
3. Inspect branch ancestry and `git worktree list --porcelain`. If local main
   diverged, stop for explicit reconciliation, preserve both histories and rerun
   affected checks. Never force, reset or discard either history.
4. During an unfinished campaign or pending review/release gate, keep its branch
   checked out. When local main is an ancestor of the tested branch and is not
   checked out in another worktree, advance it locally without switching:

   ```bash
   git fetch --no-tags --no-write-fetch-head --no-auto-maintenance . <tested-branch>:refs/heads/main
   ```

   The source `.` is this local repository, not a remote. Use the actual tested
   branch, without `+` or force flags. If main is checked out elsewhere, coordinate
   a clean fast-forward there without disturbing its user's work; do not bypass
   Git's checked-out-branch protections.
5. Verify the local main ref equals the tested candidate. Preserve all recorded
   review, approval and release states. Do not push/publish/sign without separate
   explicit authority.
6. Switch to local main for routine operation only after all requested work,
   required reviews and release gates are complete and the worktree is clean.
   Never switch while uncommitted work or an unmet review/release gate remains.
