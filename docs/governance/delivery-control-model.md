# Delivery control model

## Status and origin

The repository's planning model is a project-specific control system, originally
assembled with ChatGPT rather than adopted verbatim from a named industry
framework. It combines recognizable practices—roadmap waves, stage/exit gates,
capability decomposition, vertical slices, task-level evidence, and independent
review—but this exact vocabulary and hierarchy is not an external standard.

The model was refactored on 2026-08-13 to remove an ambiguity in which a
capability spanning several waves could make a future gate appear to be the
current program blocker. Existing numeric IDs, approvals, evidence, and Git
history were preserved.

## Canonical control hierarchy

```text
Roadmap
  -> Wave
      -> Capability-wave increment
          -> Ordered slice
              -> Task
      -> Wave exit / next-wave activation gate
```

- **Wave** is the primary program-order axis. Work does not enter a wave until
  its activation gate is approved.
- **Capability** describes a durable product outcome and may span waves. One
  capability contributes a separately approved increment to each applicable wave.
- **Slice** is an ordered, end-to-end integration/review step inside a capability.
  Slice numbering has real dependency meaning and is not removed.
- **Task** is the atomic claim and commit-bound evidence unit.
- **Gate** is a sequential human decision at a wave boundary. `G1` means W1 exit
  and activation of its declared successor wave(s); it is not "capability gate 1."

Every wave has exactly one exit gate. A gate may activate more than one parallel
successor wave, and a terminal gate may activate none. Gate approval is legal
only after every task in the preceding wave is `DONE`, every slice in that wave
is independently `APPROVED`, prior gates are approved, and criterion-linked
evidence supports the decision.

Every slice has exactly one scalar wave assignment. A capability may therefore
appear in several waves, but the same slice cannot be scheduled into several
wave increments or disappear from the wave inventory. The generated planning
site and backlog validator enforce this relationship.

## Identity and presentation

Numeric capability IDs (`CAP-01`) and slice IDs (`CAP-01.S04`) are immutable
foreign keys used by dependencies, schemas, evidence manifests, plans, and Git
history. They do not imply capability priority. Human-facing tools present stable
descriptive capability aliases first (`CAP-windows-desktop-runtime`) and derive a
descriptive slice label from its title (`SLICE-authenticated-desktop-service-contract`).
The canonical ID remains visible beside the alias.

## Planning and approval

Capability-wide material decisions are researched and approved once. Slice plans
are approved progressively for the active wave. Future-wave slice plans remain
visible for dependency analysis but need not be decision-complete until their
wave approaches activation. Historical approvals that covered a capability and
all of its slices remain valid; they do not authorize work outside the current
global wave.

## Why this control model is retained

The retained strengths are unusually strong traceability, explicit denial and
recovery evidence, independent integration review, local-first safety, and clear
human authority at consequential transitions. The refactor reduces work-in-
progress, premature detailed planning, ambiguous gates, and long capability
locks without discarding audited history. It resembles a hybrid of rolling-wave
planning, stage-gate governance, and evidence-based continuous delivery; it
should be evaluated as this repository's governed system rather than assumed to
inherit guarantees from any one methodology.
