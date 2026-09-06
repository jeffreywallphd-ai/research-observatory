# Coding-agent task operations

Read this guide only when operating planned work. For selection/claim/resume,
read Before editing and Command sequence; for submission, read Evidence; for
review/remediation, also read Independent review. Decision and integration
procedures are linked at the action that needs them. Read-only questions do not
require a claim or campaign mutation.

## Before editing

1. Follow the current AGENTS.md route and planning lifecycle. Reuse unchanged
   guidance already available; do not open every linked guide or reference page.
2. At Wave start/resume, confirm complete immutable approval and readiness.
   An approved Wave is not reapproved after an ordinary interruption.
3. Read the current backlog task/dependencies and approved capability/slice scope.
   Inspect affected ADR/architecture sections; read experience contracts only
   when user-facing behavior is affected. Generated pages help navigation but
   do not replace canonical plans.
4. Claim only the next dependency-eligible READY task inside the active Wave.
   An interrupted owned task uses its legal resume/reopen/renew transition,
   not a second claim or invented base.
5. After claim, read [task-start planning](task-start-planning.md). Map only
   material acceptance/failure boundaries to tests before product edits.
   This adds no approval or mandatory standalone document.
   If adding refactoring, apply [locked-Wave accounting](../../planning/README.md#locked-wave-refactoring-budget)
   before committing effort; include past-Wave work in the current Wave total.
6. Stop only for an actual unmet authority, dependency, safety or feasibility
   gate; ordinary failed tests are work to resolve inside approved scope.

Completed restorative tasks use [linked correction](workflow-efficiency.md#use-the-linked-correction-route).
Control defects use [bounded maintenance](workflow-efficiency.md#bounded-maintenance).
Do not apply the ordinary claim sequence to those routes blindly.

## Command sequence

From repository root with the configured Python environment. Run only the
command matching current state; inspect `--help` if its arguments are unclear.

```bash
# Readiness at approved Wave start/resume:
python tools/planctl.py --repo . wave ready WN --require-approved
# Start a new approved campaign OR resume its recorded PAUSED campaign:
python tools/taskctl.py --file planning/backlog.yaml wave start WN --agent <agent> --branch <branch> --base-sha <full-sha> --worktree . --profile LOC --platform windows-x64
python tools/taskctl.py --file planning/backlog.yaml wave resume WN --agent <agent> --branch <branch> --base-sha <full-sha> --worktree . --profile LOC --platform windows-x64
# Choose, inspect, and claim only the eligible task:
python tools/taskctl.py --file planning/backlog.yaml next --profile LOC --platform windows-x64
python tools/taskctl.py --file planning/backlog.yaml show CAP-XX.SXX.TXX
python tools/taskctl.py --file planning/backlog.yaml claim CAP-XX.SXX.TXX --agent <agent> --branch <branch> --base-sha <full-sha> --worktree . --profile LOC --platform windows-x64
python tools/taskctl.py --file planning/backlog.yaml checks CAP-XX.SXX.TXX
# After committing implementation and verifying that exact candidate:
python tools/taskctl.py --file planning/backlog.yaml submit CAP-XX.SXX.TXX --agent <agent> --from artifacts/evidence/CAP-XX.SXX.TXX.json
python tools/taskctl.py --file planning/backlog.yaml review CAP-XX.SXX.TXX --reviewer <independent-reviewer> --result approved --from artifacts/evidence/CAP-XX.SXX.TXX.review-R01.json
# After any successful ledger mutation:
python tools/backlog_views.py --repo .
python tools/backlog_views.py --repo . --check
# After status, review, or task-start worksheet changes, also refresh the HTML site:
python tools/planctl.py --repo . wave review WN
# Before committing regenerated HTML:
python tools/plan_review_check.py --repo .
```

The backlog-view commands update Markdown only. Refresh the HTML site after each
visible task/Wave/gate transition; do not wait until the next approval request.
Check affected pages against the backlog before calling the review site current.

Use the actual branch, full current HEAD, canonical worktree, concrete
profile/platform and matching owner/lease. New supported bindings store
`worktree: "."`; preserve existing non-null historical spelling.
Task `block`, `renew`, `submit`, and campaign/slice mutations enforce ownership.
Only the recorded owner may renew an expired lease. There is no override claim.

Cancellation requires owner authorization within the current active slice;
never rewrite an existing cancellation. An approved release gate requires every
preceding-Wave task to remain DONE; reopening those tasks is denied because no
implicit gate-reset transition exists.

If an amendment hold is reported, read the exact approved packet and
[amendment procedure](project-automation-guide.md#22-controlled-enabler-amendment-lane);
do not resume ordinary work until its adoption. If an actual retained recovery
hold is reported, read the [historical recovery section](project-automation-guide.md#23-governance-recovery-controller)
and the named authority; a command printed in old evidence is not new authority.
New control failures use bounded maintenance, never a new GRR/GCR/supplement.

## Continuous execution

The resumable Wave campaign continues across capability and slice boundaries.
After each task's evidence, required review and local integration, select the
next eligible task or perform the required slice/checkpoint review. Finish fresh
Wave qualification and independent Wave review before the human exit gate.
Never claim a later locked Wave or turn ordinary debugging into a human stop.

For verification breadth, use [stage-specific selection](project-automation-guide.md#81-verification-breadth-by-workflow-stage).
For repeated checks or reuse, apply only the triggered sections in the
[efficiency reading map](workflow-efficiency.md#reading-map).
An unchanged full profile is not a routine task checklist.

Before an actual decision request or gate stop, follow the
[decision-complete handoff](project-automation-guide.md#31-decision-complete-stopped-gate-handoff).
Do not ask for gate approval while prerequisites are incomplete.

## Evidence

Commit implementation, then verify the exact candidate with stable inputs.
Evidence must map every acceptance criterion to named passing machine checks,
reports/artifacts and exact commit. Narrative alone cannot complete work.

Taskctl's atomic submit reads one manifest snapshot and freezes candidate,
criteria, changed paths, check selection and open-finding replay as an immutable
RNN packet. The manifest must live under the repository and bind current HEAD,
claimed base/ancestry, branch, exact base-to-commit changed files, complete
criterion map, checks, and empty `unverifiedItems`. Dirty tracked source,
unrelated untracked files, worktree/branch drift and duplicate attachments fail
closed. Stored evidence paths are relative; validation rechecks the complete
manifest with line-ending-canonical hashes.

Follow-up evidence names `supersedes.path`, uses that attachment's commit as
`baseCommit`, and lists the complete incremental diff. DONE status does not
relax evidence requirements. The four pinned pre-policy CAP-00.S03 hosted-CI
residuals alone retain `pre-exact-evidence-hosted-ci-residual-v1`; exact task,
path, commit, digest and residual text are immutable. Never extend that exception.

Every mutation validates schema and semantic identity/dependency/gate/evidence
rules before atomic compare-and-swap publication. Stale writers or failed
replacements cannot overwrite the predecessor. After successful mutation,
regenerate backlog views; do not hand-edit generated output.

Every new controlled atomic submission must declare a non-empty
`verificationSelection.selectedCommandIds` list. IDs must be exact keys from
`verification-profiles.json`; raw commands remain in the evidence record and are
never substituted for privacy-safe IDs. Historical packets created before this
control may omit the optional frozen `selected_command_ids` field and are not
rewritten or backfilled. A non-empty frozen field is the prospective-control
marker: every completed marked attempt must contain its exact telemetry event,
and validation plus `review-telemetry` fail closed if that event is missing.

Each newly completed controlled review stores one prospective timing event. The
event is recomputed from its immutable round and is restricted to task,
amendment, attempt, and finding-control IDs; submitted/reviewed timestamps and a
nonnegative duration; outcome; severity, blocking, and total counts; canonical
command IDs; and remediation linkage. It never contains an actor or reviewer,
commit, hash, branch, path, rationale, root-cause narrative, review note, finding
body, evidence text, raw command/arguments/output, prompt, source content,
research data, secret, user-data path, or chain-of-thought. `review-telemetry`
prints only stored events in deterministic order, without a generation
timestamp. Pending submissions and pre-control or legacy review records produce
no synthetic event or duration.

## Independent review

Use an independent agent, with fresh context when practical. Task reviewers
cannot be task owners; slice/Wave reviewers cannot be campaign owners.
Review the exact committed candidate and its evidence, not an unbound summary.

Every task receives a focused disposition of scope, evidence truth, changed
contracts and credible failure paths. Expand review for security/secrets,
migrations/destructive I/O, evidence/automation controls, public/cross-process
contracts or explicit criteria. Deep/adversarial review defaults to the slice.

Use one severity-ranked, reproducible, criterion-bound finding ledger.
Approval is denied while a blocking finding is open. Preserve adverse rounds
and explicit closures; remediation replays prior findings plus incremental risk,
not the entire speculative audit. A third submission with open findings requires
root-cause analysis. Missing legacy rounds are not invented.

Before remediation, update the missed acceptance row and add the smallest
regression that would have caught it. Optional adjacent improvements become
backlog candidates unless they expose material safety/correctness defects.
Owner styling acceptance does not remove substantive quality duties.

## Integration

After the required independent disposition and passing checks, use
[local-main integration](project-automation-guide.md#11-local-main-integration).
Advance the tested local ref without changing pending gate state or switching
the campaign checkout prematurely. Divergence requires explicit reconciliation;
no force, discarded history or remote push is authorized by task completion.
