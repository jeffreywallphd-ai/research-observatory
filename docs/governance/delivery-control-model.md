# Delivery control model

## Status and origin

The repository's planning model is a project-specific control system, originally
assembled with ChatGPT rather than adopted verbatim from a named industry
framework. It combines recognizable practices—roadmap waves, stage/exit gates,
capability decomposition, vertical slices, task-level evidence, and independent
review—but this exact vocabulary and hierarchy is not an external standard.

The model was refactored on 2026-08-13 first to remove an ambiguity in which a
capability spanning several waves could make a future gate appear to be the
current program blocker, and then to make the Wave itself the approval and
durable execution unit. Existing numeric IDs, approvals, evidence, and Git
history remain preserved.

## Canonical control hierarchy

```text
Roadmap
  -> Durable Wave campaign
      -> Capability contribution
          -> Ordered slice
              -> Task
      -> Risk-cluster integration checkpoints
      -> Wave exit / next-wave activation gate
```

- **Wave** is the planning approval, durable execution, integration,
  qualification, and handoff unit. Work does not enter a Wave until its
  activation gate and complete pre-Wave packet are approved.
- **Capability** describes a durable product outcome and may span Waves. It
  contributes slices and decisions; it does not own the campaign lease.
- **Slice** is an ordered, end-to-end integration/review step inside a capability.
  Slice numbering has real dependency meaning and is not removed.
- **Task** is the atomic claim and commit-bound evidence unit.
- **Gate** is a sequential human decision at a wave boundary. `G1` means W1 exit
  and activation of its declared successor wave(s); it is not "capability gate 1."

Every wave has exactly one exit gate. A gate may activate more than one parallel
successor wave, and a terminal gate may activate none. Gate approval is legal
only after every task in the preceding wave is `DONE`, every slice in that wave
is independently `APPROVED`, the complete Wave suite and independent Wave review
are approved, prior gates are approved, and criterion-linked evidence supports
the decision.

Every slice has exactly one scalar wave assignment. A capability may therefore
appear in several waves, but the same slice cannot be scheduled into several
Wave campaigns or disappear from the Wave inventory. The generated planning
site and backlog validator enforce this relationship.

## Identity and presentation

Numeric capability IDs (`CAP-01`) and slice IDs (`CAP-01.S04`) are immutable
foreign keys used by dependencies, schemas, evidence manifests, plans, and Git
history. They do not imply capability priority. Human-facing tools present stable
descriptive capability aliases first (`CAP-windows-desktop-runtime`) and derive a
descriptive slice label from its title (`SLICE-authenticated-desktop-service-contract`).
The canonical ID remains visible beside the alias.

## Planning and approval

The complete pre-Wave packet is approved once at one immutable commit. It
contains every contributing capability decision classified as binding in that
Wave, every Wave slice plan, the cross-capability dependency/interface map,
material risks, migration and recovery obligations, verification levels, and
the Wave exit criteria. A subset cannot authorize execution. Inherited and
future decisions remain visible for dependency analysis but outside the active
approval.

Historical capability and slice approvals remain evidence. When a later Wave
packet reuses an already approved capability decision, the Wave approval binds
the exact current decision bytes without erasing the earlier approval.

### Append-only amendment authority

An approved Wave cannot be reapproved or edited in place. A material control or
enabler defect discovered during execution interrupts the Wave at a quiescent
boundary and uses a hash-bound ECR plus ordered `WN.ANN` amendment record. The
base approval and all earlier amendments remain immutable. Human approval of the
ECR authorizes only its named bootstrap and task inventory; task materialization
requires independent bootstrap review, and ordinary Wave execution stays held.

Adoption requires all amendment tasks to be independently approved, an
independent amendment-exit disposition, and a Wave control/security checkpoint.
Explicit deferral or withdrawal is also append-only and must state a reviewed
safe-resume condition. Missing, forked, reordered, rewritten, stale, or
self-reviewed authority fails closed. A repeated `planctl wave approve` command
is never an amendment mechanism.

Bootstrap review attempts are append-only. A changes-requested or blocked
disposition remains bound to its candidate and evidence; remediation uses a
strict-descendant `bootstrap-resubmit` transition and cannot overwrite that
attempt. The submission branch is frozen with each attempt so permanent history
remains valid after integration to `main`; only submission and review entry
points compare it with the live checkout. Every executable amendment state must
continue to match the approved packet's immutable task fields, an independently
approved bootstrap, the paused Wave `amendment-hold`, its campaign state, and
the single active-amendment marker. Any impossible cross-field combination fails
validation.

Task review control uses one atomic evidence-plus-submit transition and one
immutable packet per RNN round. Each packet binds the candidate, evidence,
criteria, changed paths, verification selection, and exact open-finding replay.
An independent review appends one consolidated severity-ranked ledger; findings
may close only through explicit later closure records, and approval is illegal
while a blocking finding remains open. After two adverse rounds, the next
submission must add root-cause escalation. Pre-control tasks remain valid with a
truthful latest-review projection and no fabricated append-only history.

New controlled submissions also freeze a non-empty set of canonical verification
command IDs. Historical packets may lack that optional field, but no later
submission may silently omit it. That non-empty set marks prospective control;
a completed marked round without telemetry is invalid and cannot be silently
omitted from the read-only projection. A completed post-control round appends one
strict privacy-safe timing event derived from the immutable submission and
review. The projection contains only control IDs, timestamps and duration,
outcome, finding counts by severity and blocking status, canonical command IDs,
and remediation linkage. Narrative fields, identities, Git/evidence identities,
paths, raw commands or output, prompts, source or research content, secrets,
user-data paths, and chain-of-thought are outside the telemetry contract. Legacy
rounds are never backfilled, pending rounds receive no invented duration, and a
stored event that differs from its exact derived projection fails validation.

## Review and verification cadence

- **Task:** narrow deterministic checks chosen by credible failure likelihood,
  followed by a focused independent disposition of scope, evidence truth, and
  changed risk. High-risk boundaries receive expanded adversarial task review.
- **Slice:** independent acceptance, affected integration, failure/denial, and
  adversarial review. This is the default deep-review unit.
- **Integration checkpoint:** accumulated affected-profile checks and interface
  review when a shared contract, migration, security boundary, platform adapter,
  or coherent risk cluster closes. A checkpoint is evidence, not a human gate.
- **Wave exit:** one complete affected/full matrix, cross-capability end-to-end
  scenarios, packaging, security, accessibility, performance, restart, recovery,
  clean-build reproducibility, and independent Wave review.

Reviewers use one consolidated finding ledger. Remediation review replays prior
findings plus the incremental risk boundary instead of restarting the entire
audit. Required findings are severity-ranked, reproducible, and tied to approved
acceptance criteria; useful adjacent improvements outside that boundary become
backlog work unless they expose a material safety or correctness defect.

## Why this control model is retained

The retained strengths are unusually strong traceability, explicit denial and
recovery evidence, independent integration review, local-first safety, and clear
human authority at consequential transitions. The refactor reduces work-in-
progress, fragmented approvals, repeated broad test runs, ambiguous gates, and
cross-capability integration surprises without discarding audited history. It
resembles a hybrid of rolling-wave planning, stage-gate governance, risk-based
testing, and evidence-based continuous delivery; it
should be evaluated as this repository's governed system rather than assumed to
inherit guarantees from any one methodology.
