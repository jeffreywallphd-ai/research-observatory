# Research Observatory project automation guide

> **Repository destination:** `docs/automation/project-automation-guide.md`. In the setup kit this file is seed content; after installation, root `AGENTS.md` and `docs/README.md` delegate detailed automation here.

## 1. Operating objective

Enable an AI coding tool to execute long-running, production-oriented capability campaigns while preserving architecture, evidence, security, privacy, rights, research integrity, user-experience governance, and human authority over consequential decisions.

## 2. Capability-first campaign

Use Capability -> Slice -> Task. The controller selects one eligible capability and remains in it until all slices and capability-wide exit criteria pass.

Before start:

1. Every slice has a plan generated from `planning/slice-plans/TEMPLATE.md`.
2. The capability packet covers cross-slice and material slice decisions.
3. Every decision presents at least two credible candidates, a recommendation, and rationale.
4. The recommendation is recorded as the completed selected decision unless a reviewer overrides it.
5. Required ADR and experience-reference changes are approved.
6. The capability packet and all slice plans are approved at one immutable commit.
7. `planctl ready CAP-XX --require-approved` passes.

After start, execute tasks and slices continuously. Do not request approval for ordinary debugging, code organization within approved boundaries, documented fallbacks, independent review, or transitions to the next approved slice.

### 2.1 Approval prompt and full-campaign meaning

The capability-start approval prompt must enumerate or link the capability and
all contained slice decisions, name their single immutable approval commit, and
ask for one approval of the complete packet. `planctl ready CAP-XX
--require-approved` must fail if any slice is missing, unresolved, unapproved,
or approved at a different plan state. Partial slice approval never starts a
campaign.

One campaign run is durable and resumable. A process or session may restart, but
the active campaign remains the execution unit until every slice and the
capability qualification are complete or a permitted pause condition occurs.
Slice completion is an internal integration/review boundary, not a new human
approval prompt.

## 3. Permitted pause conditions

Pause only for:

- approved choice demonstrated infeasible;
- material new evidence creating a consequential unplanned decision;
- unavailable required external service, credential, platform, or hardware;
- higher-authority conflict;
- required approved UI-reference change;
- destructive/external action or substantial unapproved spend; or
- explicit user direction.

Record the condition, update only affected authorities, regenerate review pages, obtain necessary approval, and resume the same campaign.

## 4. Planning automation

```bash
python tools/planctl.py --repo . prepare CAP-XX
python tools/planctl.py --repo . review CAP-XX
python tools/planctl.py --repo . validate CAP-XX
python tools/planctl.py --repo . ready CAP-XX --require-approved
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
capability. State its permitted scope from the task deliverables and acceptance
criteria, use its declared verification commands/profiles and changed-path impact
map to select risk-proportionate checks, bind evidence to the implementation
commit, complete required review, and then move to the next eligible task. Do not
use a globally READY task to leave an active campaign.

A slice completes only after:

- every task passes criterion-linked verification;
- the slice works end to end with adjacent completed slices;
- failure, cancellation, restart, and recovery paths are tested where relevant;
- documentation and migrations are complete;
- no hidden TODO or deferred production blocker remains; and
- an independent reviewer approves the slice.

A capability completes only after all slices plus capability-level security, privacy, rights, accessibility, performance, migration, backup/restore, platform, and end-to-end criteria pass.

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
- **Slice integration and slice review:** after the last task, run each affected
  full deployment profile once, plus slice-wide end-to-end, failure,
  cancellation, restart, recovery, accessibility, security, and performance
  checks required by the slice plan.
- **Capability qualification:** run the complete approved cross-slice matrix and
  capability-level platform/release checks.

Task `verification_profiles` and `verification_commands` define coverage domains
and candidate commands. They do not, by themselves, require every command in a
full profile at ordinary task scope. An earlier full-profile run is justified
only by an explicit task acceptance criterion, credible profile-wide impact from
shared verification/build/security/toolchain or dependency/runtime changes, or
an observed failure that cannot be localized. Evidence must name the changed-path
risk analysis, selected checks, any early broad-suite rationale, and the broader
coverage deferred to slice or capability review. A reviewer should not demand an
unchanged full-profile replay without identifying a concrete impact path.

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
7. After the requested work is fully complete and integrated, leave the repository checked out on local `main`; retain the campaign branch for audit, but do not leave it checked out for routine operation.
