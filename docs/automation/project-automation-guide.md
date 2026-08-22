# Research Observatory project automation guide

> **Repository destination:** `docs/automation/project-automation-guide.md`. In the setup kit this file is seed content; after installation, root `AGENTS.md` and `docs/README.md` delegate detailed automation here.

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

Before start:

1. Every slice in the Wave has a plan generated from `planning/slice-plans/TEMPLATE.md`.
2. Every contributing capability packet covers cross-slice and material decisions.
3. Every decision presents at least two credible candidates, a recommendation, and rationale.
4. The recommendation is recorded as the completed selected decision unless a reviewer overrides it.
5. Required ADR and experience-reference changes are approved.
6. Every contributing capability decision is classified by binding Wave. The
   complete active Wave packet—every decision binding in that Wave and every
   Wave slice plan—is approved together at one immutable commit. Inherited and
   future decisions are nonbinding context.
7. `planctl wave ready WN --require-approved` passes.

After start, execute tasks and ordered Wave slices continuously. Do not
request approval for ordinary debugging, code organization within approved
boundaries, documented fallbacks, independent review, or transitions to the next
approved slice in that Wave.

### 2.1 One approval and durable-Wave meaning

The start prompt links the Wave page, which classifies all contributing
capability decisions as binding, inherited, or future context and aggregates
the Wave slice plans, cross-capability dependencies, review cadence, risks, and
exit criteria. `planctl wave ready WN --require-approved` fails if any decision
is unclassified, any binding component is missing, or the one commit-bound Wave
approval is missing. Future-Wave decisions remain outside the packet.

One Wave run is durable and resumable. A process or session may restart, but the
campaign remains active across capability boundaries until every ordered slice
is independently approved, integration checkpoints are complete, the full Wave
matrix passes, and independent Wave review approves qualification.

### 2.2 Controlled enabler amendment lane

Do not rewrite or repeat an approved Wave packet. For consequential control or
workflow evidence, pause the Wave at a safe boundary and use an immutable ECR:

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

For ordinary and amendment tasks, use `taskctl submit <task> --agent <agent>
--from <manifest>` as the atomic evidence-and-submission transition. It freezes
an immutable RNN packet containing candidate/evidence, acceptance-criteria,
changed-path, selected/deferred-check, rationale, and open-finding identities.
The independent reviewer supplies one structured severity-ranked ledger through
`taskctl review ... --from <ledger>`. Reviewed rounds and explicit finding
closures are append-only. Remediation must replay the exact open IDs against the
incremental evidence boundary, and the third submission with open findings must
record root-cause escalation. Older task histories retain only their truthful
latest-review projection; automation never invents missing rounds.

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

A permitted gate stop is an active decision handoff, not merely a status report.
Before yielding, the agent must run `taskctl next` and the relevant `planctl
review` commands, then provide:

1. the gate name, status, criteria, and exact evidence needed for eventual approval;
2. whether approval is currently legal, with counts/identities of unfinished
   preceding-wave work and any upstream pending gates;
3. directly openable `file://` and repository-relative links for the affected
   wave and prerequisite capability packets;
4. credible alternatives and their consequences;
5. a recommended option with rationale; and
6. the exact condition and command shape for approval and Wave resumption.

When prerequisites are incomplete, recommend keeping the gate pending, pausing
the blocked Wave, completing and approving prerequisite Waves in order, and
returning with criterion-linked evidence. Alternatives are explicit deferral or
governed replanning; neither is implicit gate approval. Never ask a human to
"approve the gate" while `taskctl gate approve` would reject the state.

## 4. Planning automation

```bash
python tools/planctl.py --repo . wave prepare WN
python tools/planctl.py --repo . wave review WN
python tools/planctl.py --repo . wave validate WN
python tools/planctl.py --repo . wave ready WN --require-approved
python tools/planctl.py --repo . wave approve WN --by <reviewer> --commit <git-sha>
```

`prepare` creates missing plans as proposed scaffolds. The planning agent must replace placeholders with researched decisions and pass decision-complete validation.

Every decision/approval request must include both links printed by `planctl review`.

### Other decisions

The generated site adds `Other` to every decision without modifying canonical plan candidates until feedback is applied. Selecting Other requires:

- a concise brief description;
- detailed rationale in the separate feedback field; and
- export of schema `1.1` feedback.

`planctl apply-feedback` appends `Other: <brief description>` to the canonical candidates and selects it. It archives the complete feedback, regenerates the site, and leaves approval pending.

## 5. Task and slice execution

A task claim records agent, branch, worktree, base SHA, lease, and expected scope. A task contract includes goal, non-goals, dependencies, inspect/change scopes, canonical sources, criteria, required checks, security class, human gates, and evidence outputs.

At each iteration select only the dependency-eligible `READY` task in the active
Wave campaign. State its permitted scope from the task deliverables and acceptance
criteria, use its declared verification commands/profiles and changed-path impact
map to select risk-proportionate checks, bind evidence to the implementation
commit, complete required review, and then move to the next eligible task. Do not
use a globally READY task to leave the active Wave.

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

The implementation must expose a conformance manifest and pass route, required-region, workflow, token, accessibility, interaction, responsive, theme, and controlled visual-regression tests.

The approved reference is never a deployable application artifact. Do not copy
its HTML, illustrative records, future-capability routes, or nonfunctional actions
into production or development bundles. Implement only the functional regions and
workflows owned by the active capability; keep the full reference in isolated
design/conformance tooling.

## 7. Evidence

Each task evidence manifest must identify exact commit, changed files, commands, exit status, reports, artifacts, criterion mapping, unverified items, and reviewer disposition. Evidence must be machine-verifiable and stored by reference/hash rather than narrative alone.

## 8. Verification and CI

Run fast deterministic checks on every PR; Windows desktop qualification is required during W0-W5. macOS/Linux qualification is added in W6. Expensive live-provider, large-corpus, installer matrix, and performance work belongs in scheduled or release profiles unless a slice explicitly requires it earlier.

### 8.1 Verification breadth by workflow stage

Verification is selected by credible failure likelihood, not by replaying every
available suite at every task:

- **Task implementation and task review:** run focused tests for the changed
  modules, contracts, denial/failure boundaries, and directly affected
  integrations. Run affected lint, format, type, schema, planning, architecture,
  UI, security, or platform checks only when the changed paths can plausibly
  invalidate them.
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

### 8.2 Review efficiency and depth

Every task receives a focused independent disposition of scope, evidence truth,
changed contracts, and credible failure paths. Expand that task review for
authentication/secrets, migrations or destructive I/O, evidence and automation
controls, public/cross-process contracts, security policy, or an explicit plan
requirement. Deep/adversarial review defaults to the slice. A slice reviewer evaluates the acceptance surface,
changed contracts, denial/failure paths, and integration evidence rather than
repeating every implementation step.

Maintain one consolidated finding ledger per slice and Wave. Each required
finding includes severity, a deterministic reproduction, the violated contract
or criterion, and the smallest acceptable closure. Remediation review replays
all prior findings plus the incremental changed-path risk boundary; it does not
restart a broad speculative audit. Adjacent improvements outside the approved
acceptance surface become backlog items unless they expose a material safety,
data-integrity, security, or production-correctness defect. Escalate recurring
findings after the second remediation to root-cause/control review instead of
continuing unbounded patch-and-rereview loops.

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

At minimum maintain checks for:

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

## 10. Setup verification

After seed installation, verify root `AGENTS.md`, `docs/README.md`, and `planning/README.md` delegate correctly to this guide. The external setup pack is not required for operation.

## 11. Local main integration

The default handoff for tested repository work is the local `main` branch:

1. Run the task contract and changed-path checks against the exact commit to integrate.
2. Require a clean worktree and successful checks; never integrate known failing work.
3. Fast-forward local `main` to the tested branch when histories permit.
4. If histories diverge, stop for explicit reconciliation, then rerun affected checks before merging.
5. Preserve task, review, approval, dependency, and release-gate state exactly as recorded; a Git merge is not workflow approval.
6. Do not push local `main`, publish artifacts, or update a remote without separate explicit authorization.
7. After the requested work is fully complete and integrated, leave the repository checked out on local `main`; retain the Wave branch for audit, but do not leave it checked out for routine operation.
