# CAP-04.S02.T03 implementation checkpoint

This is a resumable checkpoint, not a task submission, approval or slice exit.
Owner: `codex-w2-implementation`; canonical checkout `.` on
`codex/w2-implementation`. Claim base remains
`d45d33dec00466f66c845d4a56fe002f82d6ba08`. Local main remains there until
required independent disposition. No remote push occurred.

## Committed implementation and observed checks

Candidate `04c42cc5e32a5b644114016cd983428ff9242dbe` includes the graph/OA
adapters, private native configuration, ordinary Intent egress route, generated
client and durable read-only source inspection. HEAD/source inputs were held
fixed during these runs; all paths below are under ignored `artifacts/tmp/`.
These are exact historical observations, not fresh proof of a later candidate.

| Check / log suffix after `CAP-04.S02.T03.` | Actual result |
|---|---|
| `connectors-qualification-01.log` | 83 tests PASS, 46.608s; mapping, current authority, transport/TLS, protected observations, failure/retry/cancel/restart and inspection. |
| `security-contracts-qualification-01.log` | 33 tests, 32 PASS / 1 directory-symlink privilege skip, 3.333s. Lost-root credential denial and generated contracts covered. |
| `native-unit-qualification-01.log` | 8 configuration/dialog + 29 supervisor + 1 exact capabilities fixture-route tests PASS. |
| `native-integration-qualification-01.log` | Actual native supervisor, normal Core, isolated Windows DPAPI vault and SQLCipher project PASS. Save/CAS/restart/closed-project denial, normal Intent impact/draft/acceptance, offline/revoked privacy denial, exact local preview and read-only inspection; no provider confirmation. |
| `renderer-unit-qualification-01.log` | 16 tests PASS; source settings/Source Manager/Intent. |
| `client-unit-qualification-01.log` | 21 generated-client tests PASS. |
| `browser-qualification-01.log` | 2 built-renderer journey tests PASS, 8.389s, both themes. Explicit native/Core doubles; no native claim. |
| `quality-qualification-01.log` | Ruff lint/format and mypy PASS across 29 changed Python files. |
| `types-lint-qualification-01.log` | Desktop typecheck/lint PASS. |
| `renderer-build-qualification-01.log` | Product and reference-fixture builds PASS. |
| `inventory-qualification-01.log` | API generation, 336-file quality inventory, architecture, clean build identity, backlog views and 492-page review-site validation PASS. |

Native integration report `CAP-04.S02.T03.native-integration-qualification-01.json`
SHA-256 `641cac12e82b92cced69d1bc9e449d20a34df6da72dd9f4ffa7c02b0239998a0`.
No synthetic contact plaintext was found in retained fixture files, public
requests or diagnostic outputs. This is not live-provider or GUI Save evidence.

## Packaging correction

The strict build-contract test failed because the registered hidden-module
inventory did not match the builder and its test. Commit
`40f0c7c8bad079c004738ff59df457bc57519fb3` adds only six lines in the packaging
contract/test: register inspection, update exact expectations and require both
settings/inspection in the actual executable archive. No runtime source changed.

At that clean candidate, `packaging-qualification-02.log` records 6 tests:
5 PASS and 1 file-symlink privilege skip, 34.847s. The actual PyInstaller executable
contains both modules, starts with only Windows system executables on PATH,
and detects a missing runtime file. SHA-256:
`bd433f8e95f39f9fa9f23fb6283d7244e36bcfc18b7b1721308bd91b58cccfd3`.
Focused lint/format/mypy PASS in `packaging-quality-03.log`. The earlier standalone
mypy invocation omitted its producer module and failed import resolution;
the corrected selection includes the test and `tools/core_sidecar_build.py`.

## Native and visual boundaries still to finish

- The development native window created/reopened the synthetic project and
  showed an owned Unpaywall form with empty contact and disabled preservation
  checkbox. Escape reported cancellation with contact still required. No Save
  occurred. Native focus restoration is not established by the browser double.
- At candidate 04c42cc5, GUI build hash
  `356aaadb086ec5130e61ba908d0f6a9fbe2ec95e8adc30776caa8fedfb742619`
  has verified Common Controls v6/asInvoker metadata. The window closed cleanly
  before its settings interaction; log `native-gui-qualification-01.log` ends
  with exit 0, admission closed and no pending dialog. Do not count it as GUI
  Save or folder-selection completion.
- The computer-use skill requires manual handoff for changing source settings.
  Prepare the isolated owned form, ask the user to enter only the synthetic
  contact and Save locally, then observe readiness, reopen without value
  disclosure, cancellation/focus and restart persistence. Never enter a real
  key, send a provider request or access ordinary user settings for this check.
- A new focused contrast/reflow test reproduced four dark policy links at
  3.595:1. The acceptance worksheet records this gap. One shared dark link rule
  now uses the existing approved brand token. Development rerun PASS across
  inventory/inspection, light/dark and 1440/1280/720 widths, with 12 captures in
  `source-visual-yopfet9_/result.json`; lowest sampled ratios 4.75:1 light and
  6.37:1 dark. Preserve failing `source-visual-nxv8wcnz/result.json`.
  Commit and freshly qualify the CSS/test increment before final review.
- Full reference tooling currently fails before token checks because
  `verification/extensions/desktop-ui.json` binds 1.6 while the published
  reference is 1.7. Historical witness/baseline identities were not relabeled.
  Focused product style/journey checks do not resolve whole-reference conformance;
  retain this distinct W2 control qualification gap.

## Review and resume order

Independent reviewer `/root/w2_s01_final_review` found no substantiated code
blocker at 40f0c7c8 after examining private configuration, secret boundaries,
Intent admission, public contracts, inspection and graph/OA failure integrity.
This is explicitly **not approval**. Initial reviewer sessions hit a usage
limit; one retry restored read-only review. No owner self-approval or state
transition occurred.

1. Finish the CSS/test/worksheet checkpoint and fresh affected visual checks.
2. Complete actual native Save/cancellation/focus/reopen proof with manual
   settings handoff; retain any adverse result and correct only its boundary.
3. Assemble exact-candidate criterion evidence, selected/deferred check rationale
   and authenticated outputs; do not relabel ancestor runs as fresh. Preserve
   both symlink skips and the full-reference activation failure.
4. Submit through taskctl, obtain independent commit-bound disposition, refresh
   generated views/site and fast-forward local main only after approval.
5. Complete CAP-04.S02 integrated slice qualification/review before the next
   dependency-eligible W2 task. Do not rerun completed unrelated W1/import suites.
