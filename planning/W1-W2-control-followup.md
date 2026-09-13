# Bounded W1–W2 control follow-up

Authority: the owner's 2026-09-13 W1 core acceptance and request for reasonable
test fixes plus selective UX automation improvements. This is a small maintenance
note, not a new Wave, campaign, approval tier or replacement for the backlog.
W2 design remains mutable and its execution unstarted.

## Selected work and limits

| Work | Bounded implementation / proof |
|---|---|
| Test fixtures | Correct two missing Core source imports and the obsolete privacy API request; generate the in-process test capability token at runtime. Run only these previously blocked/failed modules or cases; preserve assertions. |
| Diagnostic reporting | Add verbose output to the existing 14 unittest discovery commands so case IDs and skip reasons are retained. One focused inventory regression protects the configuration. No new runner or automatic retries. |
| UX planning | Extend existing Wave/capability assessment and task-start rows with user goals, cross-page context, outcome, recovery and continuation. No duplicate journey registry. |
| UX review | Keep existing styling/workflow/accessibility/visual controls. Add conditional, bounded goal-only exploration for uncertain important journeys; model opinions are advisory unless tied to an existing material requirement. |

The supplied UX brief was advisory input, not authority. It has not been copied
into the repository. Retained capabilities already include approved tokens and
shared styles, workflow IDs, route/keyboard/accessibility checks, reference/product
separation, provenance and human approval. Recent desktop/reference results were
observed passing; that is not population-level usability evidence.

Defer a new UX framework, mandatory personas or scorecards, new state-machine
schemas, extra approval gates, new browser tools, universal walkthroughs, new
visual budgets and broad retrospective UX redesign. The brief's research/vendor
claims were not independently revalidated and are not adopted as facts here.

## Remaining issues — do not reopen W1 core delivery

- Git ownership/clone and intermittent CLI fixture cleanup: verify the intended
  execution identity and bounded child cleanup; no global trust change or ignored
  cleanup error. Use a focused case, not a completed suite replay.
- Protected benchmarks: use disposable configured authority, not ordinary user
  storage or a plaintext substitution. Do not reinterpret setup failures as timings.
- Scanner: diagnose the retained scanner failure with sanitized output; a failed
  scanner is not a clean security result.
- Foundation/historical validation and the reported security skip: retain exact
  gaps, and avoid another broad historical-fixture overhaul.
- Gateway timing: retain measured overages for future optimization; no threshold
  changes or repeated measurements merely to obtain green output.

Initial setup/fixture repair is time-boxed to 30 minutes of that work. If a fix
expands into a redesign, stop that item and report the concrete remaining risk;
do not make control perfection a prerequisite for W2 planning. Before W2 execution,
decide which remaining checks materially protect its new functionality and which
need an explicit scoped disposition. Do not silently waive security obligations.

Changes are confined to control documentation, test fixtures, reporting and W1
owner-status projection. No application behavior, frozen UX reference, historical
approval or future Wave packet is rewritten. Record focused results and independent
review alongside this note; do not claim a fresh full-suite qualification.
