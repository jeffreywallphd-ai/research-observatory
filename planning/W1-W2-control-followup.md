# Bounded W1–W2 control follow-up

Authority: the owner's 2026-09-13 W1 core acceptance and request for reasonable
test fixes plus selective UX automation improvements. This is a small maintenance
note, not a new Wave, campaign, approval tier or replacement for the backlog.
W2 design remains mutable and its execution unstarted.

## Selected work and limits

| Work | Bounded implementation / proof |
|---|---|
| Test fixtures | Correct two missing Core source imports and the obsolete privacy API request; supply its synthetic intent actor and generate its in-process capability token at runtime. Run only these previously blocked/failed modules or cases; preserve assertions. |
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

- Git ownership/clone: both formerly failing cases now pass from the canonical
  checkout under the normal execution identity. The earlier isolated-checkout
  ownership failure remains evidence; no global trust setting changed.
- CLI fixture cleanup still fails with Windows sharing/access errors under the
  normal identity. Resolve fixture-owned child/handle cleanup before relying on
  this case in a new qualification run; do not ignore the error or widen retries
  without cause. Application assertions were not the failing stage.
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

## Focused results

Candidate `a31119fe` passed the previously unloadable dependency-impact module
(15 tests, 1.966 s), selective-recalculation module (14 tests, 2.988 s), and two
reporting/profile-contract cases (0.003 s). Those completed checks are not replayed.
The privacy case advanced beyond its obsolete request but failed with the expected
fail-closed `RO-CORE-INTENT-ACTOR-UNAVAILABLE`: its fixture had omitted the now-required
intent service. The follow-up supplies the existing real service/repositories with
a synthetic actor, matching lifecycle tests; no real profile vault is consulted.
The retained failure is not overwritten by its targeted follow-up result.

At `95077c2b6be7fe03fff8fb501b72a2edc7bd096d`:

| Selected check | Result |
|---|---|
| Privacy consent/cache case with synthetic intent authority | PASS, 1 test, 0.275 s |
| Real-Git presentation-witness fixture, normal identity | PASS, 1 test, 67.633 s |
| Adopted-maintenance Git fixture, normal identity | PASS, 1 test, 129.625 s |
| CLI default/duplicate-flag case, normal identity | ERROR during fixture cleanup, 1 test, 3.929 s; retained/deferred |
| Review-site integrity | PASS, 492 HTML pages; no errors |
| Five affected Python files | Lint/format/type checks PASS |

The first narrow mypy invocation omitted the Core source search root and failed
import resolution. The corrected invocation used repository configuration,
`--no-namespace-packages` and process-local `MYPYPATH=services/core-api/src`;
no missing-import suppression or code relaxation was added. The privacy hook
initially flagged the old synthetic token literal; runtime generation resolved
that fixture finding. Hooks remained enabled and passed all commits.

Independent review found that Markdown summaries omitted the owner-only completion
limitation shown in HTML. At `f743739587db423e0c0fb19a608d19edf048f227`, one shared
formatter projects existing completion notes into both Markdown views. Its new
regression failed for both renderers before the fix, then passed (1 test); generated
views matched exactly, and both affected Python files passed lint/format/types.
Eighteen selected documentation links also resolved. No completed product suite
was rerun, and no application code changed.

Local site report: `artifacts/tmp/W1-W2-review-site-check-01.json`, SHA-256
`a5543c24f548fb31dfdc795fb4a77181de0f2d6251de9656dab1cb2819089f6a`.
Raw outputs stay local; these focused results do not replace the earlier matrix.

Independent reviewer `/root/w1_continuation_preflight` **APPROVED** the bounded
control scope at `f743739587db423e0c0fb19a608d19edf048f227`, with no remaining material
findings. The projection finding is closed. This reasonable maintenance pass is
complete; the listed residual checks remain follow-up work, not a reopening of
W1 core acceptance or an assertion of full qualification. G1/W2 remains unchanged.
