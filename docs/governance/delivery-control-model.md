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
