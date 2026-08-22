# Planning guide

This file is the repository's high-level planning router. Planning state and identity live in the files referenced below, not in chat history or this summary.

## Roadmap and execution hierarchy

```text
Roadmap
  -> Durable Wave campaign
      -> Capability contribution
          -> Ordered slice
              -> Task
      -> Risk-cluster integration checkpoints
      -> Wave exit / next-wave activation gate
```

- `backlog.yaml` is authoritative for IDs, dependencies, waves, gates, status, claims, leases, and evidence references.
- Waves are the primary execution axis. Every wave has one sequential exit gate;
  the same gate activates the next wave, except the final roadmap gate.
- Capability aliases are the default human presentation. Numeric capability IDs
  remain immutable dependency/evidence keys.
- Slices are ordered within a capability. Descriptive slice labels are the
  default presentation, while numeric slice IDs preserve sequence and history.
- `backlog.schema.json` is its executable Draft 2020-12 structural contract; every `taskctl` command validates it before reading or mutating state.
- `capability-plans/CAP-XX.md` resolves cross-slice and material implementation decisions.
- `slice-plans/CAP-XX/*.md` expands the existing tasks into a coherent implementation and verification contract.
- `review-site/` is generated from the backlog and Markdown plans. It includes
  wave/gate breakdowns plus capability and slice views and is not a parallel authority.
- `../docs/planning-implementation-plan.md` and `status-summary.md` are generated from `backlog.yaml`; every section is read-only and `foundation` rejects drift.

Regenerate and verify the human-readable backlog views after every authoritative
ledger mutation:

```bash
python tools/backlog_views.py --repo .
python tools/backlog_views.py --repo . --check
```

Generation writes only when content changes, so repeating it against unchanged
YAML preserves the files byte-for-byte and does not change modification times.
The renderer parses and hashes one immutable backlog byte snapshot, compares
canonical UTF-8 output bytes (including line endings), and rejects source or
output paths that resolve outside the canonical repository. Check mode detects
corrupt bytes without decoding them; generation replaces them atomically or
returns an actionable I/O failure. Edit `backlog.yaml`, never a generated view.

## Default planning and execution lifecycle

1. Determine the earliest unfinished global Wave and its exit gate.
2. Run `planctl wave prepare WN`; create every missing contributing capability
   and slice plan.
3. Resolve every material capability and cross-capability decision, interface,
   risk, rollback/recovery duty, and verification obligation for the Wave.
4. Generate the static review site and review the complete Wave packet from its
   Wave page, using capability/slice pages for full rationale or overrides.
5. Classify every contributing capability decision by binding Wave, then
   approve every decision binding in the active Wave and every Wave slice plan
   together at one immutable commit. Inherited and future decisions remain
   nonbinding context. A partial packet cannot start execution.
6. Start `WN` as one durable Wave campaign.
7. Claim only the next dependency-eligible READY task across the Wave. Use
   risk-selected task checks and commit-bound evidence.
8. Integrate and independently review each slice. Record accumulated
   affected-profile checkpoints when a shared interface, migration, security
   boundary, or coherent risk cluster closes.
9. After all Wave slices are approved, run the complete affected/full suite and
   cross-capability end-to-end qualification once.
10. Submit the Wave for independent review. Only an APPROVED Wave completion may
    proceed to the Wave exit / successor activation gate.

One pre-Wave approval binds the complete Wave packet. The campaign remains the
same across ordinary process or session interruptions and across capability
boundaries. Later-Wave plans remain reviewable but do not expand the active Wave.

### Controlled enabler change requests

Never replace or repeat an `APPROVED` Wave approval. If consequential new
evidence requires a bounded control/enabler change, pause the Wave with no
ordinary task in `IN_PROGRESS` or `REVIEW`, create a hash-bound ECR packet, obtain
independent packet review and explicit human approval, and record that approval
in `wave-amendment-approvals/`. The original Wave approval plus ordered
append-only amendments is the authority chain; the legacy effective projection
remains readable but is not mutation authority.

The one-time bootstrap is non-executable until independently approved. Only then
may `taskctl amendment materialize` create the exact approved task IDs and change
the paused campaign to `amendment-hold`; this marker also makes older taskctl
schema/tool pairs fail closed. Activation leases only the amendment. Ordinary
Wave work and its exit gate stay denied until every amendment task is `DONE` and
independently approved, the amendment exit review is `APPROVED`, and adoption
records a Wave control/security checkpoint. Adoption restores scope `wave` but
leaves the campaign `PAUSED` for an explicit normal resume.
Bootstrap `CHANGES_REQUESTED` or `BLOCKED` reviews are never overwritten. Commit
the bounded remediation and its new evidence, then use `taskctl amendment
bootstrap-resubmit` to append the prior attempt and freeze the strict-descendant
candidate. Materialization, activation, claims, evidence, reviews, and adoption
all revalidate the bootstrap packet and immutable task definitions.

Amendment exit is also packetized. Commit the exit evidence, then use
`taskctl amendment submit WN.ANN --agent <agent> --from <exit-evidence>`.
The packet binds the codex branch, evidence Git blob, approved ECR exit
criteria, and selected checks. Independent review uses `taskctl amendment
review ... --from <review-ledger>`; adverse rounds, findings, and explicit later
closures remain append-only. Adoption uses a separately committed checkpoint
record through `taskctl amendment adopt ... --from <checkpoint-evidence>` and
revalidates the exact approved review state. Missing, substituted, stale,
forked, dirty, or unreviewed evidence fails closed. Legacy amendments remain
readable without invented exit-review history.

#### Governance recovery request fallback

Use a GRR only when evidence demonstrates that the ordinary ECR controller or
schema cannot represent or safely enforce its own next append-only amendment.
The GRR packet freezes the complete predecessor authority chain, recovery hold,
bootstrap-only path/outcome boundary, and the identity of the later ECR that
must be approved separately. Independent packet review and exact-commit human
approval precede B00. `recoveryctl` then freezes criterion-linked evidence and
append-only independent review rounds; adverse review requires a strict
descendant `bootstrap-resubmit`.

An approved B00 is immutable. If new evidence proves that the approved repair
amendment still cannot cross its exact materialization boundary, create an
inert sequential `GRR-NNNN.SNN` packet rather than reopening B00 or installing a
second hold. After independent packet review and exact-commit human approval,
`supplement-start` installs only `GRR-NNNN.BNN` under the existing hold and
raises the control revision. Its evidence, adverse remediation, and independent
review are append-only. Ordinary task/amendment/Wave/gate mutation remains
denied until the latest supplemental bootstrap is APPROVED.

An ACTIVE recovery hold is stronger than ordinary scheduling: every taskctl
mutation fails closed except the exact later amendment lane after B00 is
independently APPROVED and that ECR has its own immutable approval. The GRR does
not approve that amendment. The hold is released only after the amendment is
ADOPTED with an independently approved exit and bound security checkpoint, and
release still leaves the Wave PAUSED for explicit ordinary resume.

```bash
python tools/recoveryctl.py --repo . validate GRR-NNNN --require-approved
python tools/recoveryctl.py --repo . status GRR-NNNN
python tools/recoveryctl.py --repo . bootstrap-start GRR-NNNN --agent <agent>
python tools/recoveryctl.py --repo . bootstrap-submit GRR-NNNN --agent <agent> --implementation-commit <HEAD> --evidence <manifest>
python tools/recoveryctl.py --repo . bootstrap-review GRR-NNNN --reviewer <independent-reviewer> --from <ledger>
python tools/recoveryctl.py --repo . bootstrap-resubmit GRR-NNNN --agent <agent> --implementation-commit <HEAD> --evidence <manifest>
python tools/recoveryctl.py --repo . supplement-start GRR-NNNN.SNN --agent <agent>
python tools/recoveryctl.py --repo . supplement-validate GRR-NNNN.SNN --require-approved
python tools/recoveryctl.py --repo . supplement-status GRR-NNNN.SNN
python tools/recoveryctl.py --repo . supplement-submit GRR-NNNN.SNN --agent <agent> --implementation-commit <HEAD> --evidence <manifest>
python tools/recoveryctl.py --repo . supplement-review GRR-NNNN.SNN --reviewer <independent-reviewer> --from <ledger>
python tools/recoveryctl.py --repo . supplement-resubmit GRR-NNNN.SNN --agent <agent> --implementation-commit <HEAD> --evidence <manifest>
python tools/recoveryctl.py --repo . release GRR-NNNN --agent <agent>
```

Task evidence attachment and submission are atomic: use `taskctl submit <task>
--agent <agent> --from <manifest>`. The resulting RNN packet freezes the exact
candidate, criteria, changed paths, verification selection, and open finding
IDs. Independent task reviews use `taskctl review ... --from <ledger>` and append
severity-ranked findings and explicit closures without replacing older rounds.
Legacy task records remain readable through their latest `review` projection;
missing historical rounds are never synthesized.

### Release-gate stop review

When the global program position is a pending release gate, `taskctl next` must
produce a decision-complete stopped-gate handoff rather than a generic "no READY
task" message. The handoff identifies the gate criteria, incomplete preceding
wave tasks and slice reviews, pending upstream gates, and prerequisite planning-review
pages, alternatives, recommendation, and exact resume condition.

Distinguish two decisions:

1. If preceding-wave work or evidence is incomplete, the release gate is not
   approvable. The reviewer chooses whether to follow the recommended prerequisite
   sequence, defer the campaign, or authorize governed replanning. The gate stays
   `PENDING`.
2. Only after every preceding-wave task is `DONE`, every preceding-wave slice is
   independently `APPROVED`, and criterion-linked evidence
   exists may a human approve the gate with `taskctl gate approve`. That approval
   is separate from capability-plan approval, feedback export, task/slice review,
   and local Git integration.

Every stopped-gate response must repeat the directly openable `file://` and
repository-relative review links so the human can inspect the decision materials
without reconstructing them from chat history.

## Decision review and Other

Every decision page displays the documented candidates, preselected recommendation, and an `Other` option.

When `Other` is selected:

- the reviewer must enter a brief description in the Other field;
- the separate feedback/rationale textarea provides detailed reasoning, constraints, or acceptance conditions;
- exported feedback uses schema `1.1` with `selected_option: "__OTHER__"` and `other_option`;
- `planctl apply-feedback` adds `Other: <brief description>` to the canonical decision's candidate list and selects it;
- detailed rationale remains preserved in the archived feedback record; and
- implementation remains unapproved until the explicit complete Wave approval command.

A non-recommended documented candidate also requires detailed rationale.

## Canonical commands

```bash
python tools/planctl.py --repo . wave prepare WN
python tools/planctl.py --repo . wave review WN
python tools/planctl.py --repo . wave validate WN
python tools/planctl.py --repo . apply-feedback CAP-XX <feedback.json>
python tools/planctl.py --repo . wave approve WN --by "<reviewer>" --commit <git-sha>
python tools/planctl.py --repo . wave ready WN --require-approved
python tools/planctl.py --repo . ecr review ECR-NNNN
python tools/planctl.py --repo . ecr validate ECR-NNNN --require-approved
python tools/taskctl.py --file planning/backlog.yaml amendment status WN.ANN
python tools/taskctl.py --file planning/backlog.yaml wave start WN --agent <agent> --branch <branch> --base-sha <sha> --worktree <absolute-repository-path> --profile LOC --platform windows-x64
```

Any command that requests decisions or approval must print the Wave page's `file://` URI and repository-relative path; capability detail links accompany it when relevant.

## Templates and validation

- Backlog schema: `backlog.schema.json`
- Backlog structural and semantic validator: `../tools/taskctl.py --file backlog.yaml validate`
- Capability template: `capability-plans/TEMPLATE.md`
- Capability schema: `capability-plans/capability-plan.schema.json`
- Slice template: `slice-plans/TEMPLATE.md`
- Slice schema: `slice-plans/slice-plan.schema.json`
- Capability validator: `../tools/capability_plan_check.py`
- Slice validator: `../tools/slice_plan_check.py`
- Site generator: `../tools/plan_review_site.py`
- Site validator: `../tools/plan_review_check.py`

A missing classification for any contributing capability decision, binding
decision packet, or Wave slice plan must be scaffolded, fully researched,
validated, reviewed, and included in the one pre-Wave approval before the
campaign starts.

Backlog validation reports JSON paths for structural/type/status/timestamp errors,
rejects duplicate capability, slice, task, wave, and gate IDs while indexing,
enforces slice/task parent namespaces and complete approved-review metadata,
and names missing task or slice dependency targets and exact task dependency-cycle
paths. Do not edit around these checks or treat schema-only validity as permission
for an otherwise illegal workflow transition.

`taskctl` mutations are compare-and-swap writes under an exclusive backlog
lock. A command refuses to replace the ledger if another writer changed it,
if IDs moved, or if the resulting schema/semantic state is invalid; a failed
temporary write or replace leaves the previous ledger intact. The lock marker
is ignored by Git.

Execution commands require one concrete profile/platform and the matching
active Wave lease. Task `block`, `renew`, `evidence`, and `submit` require
`--agent` to match the task lease owner; Wave/slice mutations similarly require
the campaign owner. Start, resume, and claim also require the actual
current branch, full current `HEAD`, and canonical absolute Git worktree; stored
identities are trimmed. An interrupted PAUSED Wave resumes through `resume`.
An expired lease may be renewed only by its recorded owner:

```bash
python tools/taskctl.py wave renew WN --agent <agent>
python tools/taskctl.py renew CAP-XX.SXX.TXX --agent <agent>
```

Commit the implementation and required verification before attaching evidence.
The manifest must live under the repository, name the current full Git `HEAD`,
descend from the claimed `base_sha`, map every acceptance criterion exactly,
list the truthful base-to-commit changed-file scope, contain named passing checks,
and declare no unverified items. The manifest is read once; that same immutable
snapshot is validated and hashed. Dirty tracked source, unrelated untracked files,
branch/worktree drift, and logically duplicate attachments are rejected. Stored
evidence paths are repository-relative; complete manifest revalidation and
line-ending-canonical hashes detect later content, task-ID, base, branch, check,
criterion, commit, or verification drift.

A follow-up manifest must identify a prior attachment with `supersedes.path`, use
that attachment's commit as `baseCommit`, and list the exact incremental Git diff;
partial file lists are invalid. DONE or approved status never relaxes the empty
`unverifiedItems` rule. Four pre-policy CAP-00.S03 hosted-CI residuals carry the
`pre-exact-evidence-hosted-ci-residual-v1` reference marker and are immutably
pinned by task, path, commit, canonical digest, and exact residual text. The
marker cannot be applied to new or modified evidence.

Task reviewers must be independent from the task owner; slice and Wave reviewers
must be independent from the Wave campaign owner. Cancellation is an owner-authorized transition
inside the current active slice and cannot rewrite an existing cancellation.
An approved release gate remains valid only while every task in its preceding
wave is DONE; reopening such a task is denied because no implicit gate-reset
transition exists.

## Replanning conditions

Reopen planning only for:

- demonstrated infeasibility of an approved choice;
- materially new evidence creating a consequential decision;
- unavailable required external service, credential, platform, or hardware;
- conflict with a higher-authority source;
- required governed experience-reference change; or
- explicit user redirection.

Update only the affected decision, ADR, plan, or reference; regenerate review pages; obtain approval when required; then resume the same Wave campaign.
