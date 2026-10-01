# Verification profiles

`tools/verify.py` owns the canonical profile and command graph in
`verification-profiles.json`; every invocation validates that contract before
running commands. Direct `--profile` mode executes the complete qualification
inventory for the requested profiles and prints a nonblocking breadth warning.
For ordinary task work, start with `taskctl checks <task>` and select focused
checks or preview Git-derived affected selection before executing it.

```powershell
python tools/verify.py --list
python tools/verify.py --profile foundation
python tools/verify.py --profile desktop --report artifacts/tmp/desktop-verification.json
python tools/verify.py --profile service --profile data
```

Each enabled profile is independent and includes the foundation gate where
appropriate. Output names every command, exit status, duration, captured
diagnostic output, aggregate status, and failure cause. Execution stops within a
profile at the first failed command; another explicitly requested profile still
runs and is reported. An unknown profile exits safely with code 2. A recognized
release-gated profile exits with code 3 and its gate reason.

## Deterministic affected selection

Affected mode derives the complete changed-path set from Git; callers cannot
submit or narrow a path list. Both revisions must resolve to commits, the base
must be a full 40-character commit and an ancestor of the optional head, and an
empty or unsafe path set fails closed. `HEAD` is the default affected head.

```powershell
python tools/verify.py --profile foundation --affected-base <40-character-base> --deferred-gate W1-exit --selection-only --report artifacts/tmp/affected-selection.json
python tools/verify.py --profile service --profile data --affected-base <40-character-base> --affected-head <40-character-head> --deferred-gate W1-exit --report artifacts/tmp/affected-verification.json
python tools/verify.py --profile service --profile data --affected-base <40-character-base> --deferred-gate W2-exit --selection-only --report artifacts/tmp/W2-affected-selection.json
```

The separate `verification/affected-selection.json` policy maps canonical
repository-relative Git paths to existing command IDs. Selection preserves the
canonical command order and partitions every active command in the requested
profiles exactly once into `selectedCommandIds` or `deferredCommandIds`. Any unknown
path, or any path classified as safety-sensitive verification, evidence,
security, migration, dependency, or threshold control, selects the complete
requested active inventory except for governed gate-bound performance commands.
A matched rule that maps outside the requested profiles fails closed before any
unknown or safety fallback and names the missing command coverage; fallback can
never suppress a mapped security, migration, dependency, or threshold command.

The service profile activates `service:corpus` when `tests/corpus/test_*.py`
exists. Core API or portable-contract changes select that command in affected
service verification. Changes confined to `tests/corpus/**` select the corpus
suite and Python quality without pulling in unrelated service or packaging
suites; a change to its launcher also selects the suite. The corpus command
runs standard unittest discovery through
`tools/corpus_test_check.py`, which sets the child process's import paths to
this checkout's Core source and repository root and returns its actual exit
status. It needs no ambient `PYTHONPATH`; its Windows DPAPI/SQLCipher case must
execute on the required Windows x64 qualification platform.

The service profile requires `service:corpus-reports`. Its existing launcher,
`tools/corpus_report_test_check.py`, runs both `tests/corpus_reports` and
`tests/reports` against this checkout's Core source and returns the failing
suite's exit status. Core API or portable-contract changes select the report
suite in affected service verification. Changes confined to either report test
directory select Python quality and the report suite; a launcher change also
selects it. The command remains in complete service and W2 verification even
if a test directory disappears. The launcher then fails instead of silently
passing an incomplete suite.

The policy authorizes `W1-exit` and `W2-exit` as affected-selection deferred owners;
generic names, unconfigured Waves and human release gates such as `G2` are rejected
by both the API and CLI. Use the owner for the task's Wave. These labels record
deferred verification ownership; they do not approve a Wave or its release gate.
`desktop:performance`, `data:project-lifecycle-performance`, and
`data:storage-maintenance-performance` are gate-bound and therefore always
remain in `deferredCommandIds` during affected selection, including unknown and
safety fallback. They are retained for one serial execution at the named Wave
exit. Explicit task or slice benchmark requirements still need their own proof;
affected selection is an impact aid, not complete acceptance coverage.

Affected reports use schema `1.1` and include the exact base/head commits,
changed paths, requested profiles, selected and deferred command IDs, matched
rule IDs, controlled rationale codes and text, fallback classification, deferred
gate owner, inactive optional commands, and a SHA-256 of the canonical command
and profile inventory. `--selection-only` writes or prints this proof without
executing commands. It does not change `verification-profiles.json`, command
arguments, optional-command activation, baselines, performance methods, or
thresholds. Ordinary direct `--profile` execution retains the existing schema
`1.0` report and behavior; its warning is advisory and does not add a
confirmation or gate.

## Local receipt pilot (not a profile replacement)

`python tools/verification_receipt.py --repo .` runs only the three-file,
pure-stdlib governance-receipt unit workload from an in-memory source snapshot.
It writes unique attempts under ignored `artifacts/tmp/verification-receipts/`,
including failed or incomplete attempts, safe output digests and measured timing.
It does not launch Research Observatory or touch the live backlog.

This initial pilot is producer-asserted diagnostic evidence. Installed stdlib/OS
closure is not fully authenticated, so `--reuse-receipt` deliberately refuses
reuse; it never treats a prior PASS as a current run. Require the receipt's
matching delivery record and independent candidate/evidence review before citing
it. Existing profile execution and the fresh full Wave-exit matrix are unchanged.
See `workflow-efficiency.md` for the complete reuse/trust conditions.

## Wave-exit union

The governed profile unions are:

- W1: `ai`, `data`, `desktop`, `e2e-local`, `foundation`, `graph`, `security-local`,
  and `service`.
- W2: `data`, `desktop`, `documents`, `e2e-local`, `foundation`, `graph`, `search`,
  `security-local`, and `service`. This is the task-profile union in the frozen W2
  packet approved at `c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`.

Each union executes every active canonical command ID once, with no deferrals,
and cannot be narrowed with `--profile` or combined with affected mode. Disabled
`server` and `cloud` profiles remain release-gated. All three governed performance
commands remain selected exactly once when active in either union. Optional
commands activate through their existing paths/globs; inactive commands remain
reported as such, not as executed proof.
The W2 union includes the active `service:corpus` and
`service:corpus-reports` suites exactly once each through its service profile.

```powershell
python tools/verify.py --wave-exit W1 --selection-only --report artifacts/tmp/W1-wave-exit-selection.json
python tools/verify.py --wave-exit W1 --report artifacts/tmp/W1-wave-exit-verification.json
python tools/verify.py --wave-exit W2 --selection-only --report artifacts/tmp/W2-wave-exit-selection.json
python tools/verify.py --wave-exit W2 --report artifacts/tmp/W2-wave-exit-verification.json
```

The W2 profile union does not replace the approved slice/checkpoint matrix,
opt-in packaged and scale journeys, or separate workload performance checks.
Fresh Windows x64 cross-capability, rights/privacy, accessibility, packaging,
restart/recovery and clean-build proof, independent Wave review and the separate
human G2 decision remain required. See the approved
[W2 checkpoint clusters](../../planning/W2-initiation.md#execution-checkpoints-not-human-gates)
and [verification breadth](project-automation-guide.md#81-verification-breadth-by-workflow-stage).

## Profile ownership

| Profile | Intended checks |
|---|---|
| `foundation` | Repository, runtime, architecture, agent protocol, ADR, CI, Python quality, packaging-input smoke, unit, and backlog integrity. |
| `desktop` | Desktop unit tests plus governed UI conformance. |
| `service`, `data` | Core API/contracts and storage/migration behavior. |
| `documents`, `search`, `ai`, `evidence`, `graph`, `novelty` | Capability-specific unit/integration suites. |
| `e2e-local` | Local happy, denial, cancellation, restart, and recovery workflows. |
| `security-local` | Foundation plus the pinned live scanner and security policy unit/boundary tests. |
| `server`, `cloud` | Explicitly blocked until their later release gates. |

Each domain owns its corresponding `tests/<profile>/` directory. Empty early
suites are intentional extension points, but the inherited foundation gate
prevents a named profile from becoming an unconditional no-op.

## Desktop UI extensions

The desktop profile declares six activation-controlled commands for UI-reference
integrity, semantic tokens, route/page contracts, workflows, accessibility, and
visual regression. CAP-00.S06 installs their tools and creates
`verification/extensions/desktop-ui.json`; from that commit forward the existing
desktop profile automatically invokes all six. Before activation, the JSON report
lists each skipped command and the owning installation slice.

The activation also enables the desktop regression suite installed by
CAP-00.S06. On Windows x64, install the exact locked browser once with
`.venv\Scripts\playwright.exe install chromium`. The profile then emits separate
reference, token, route, workflow, accessibility, and visual reports under
`artifacts/tmp/`. See [`ui-conformance-verification.md`](ui-conformance-verification.md)
for the pre-application fixture boundary and approved baseline-change procedure.

Reports under `artifacts/tmp/` are local scratch. CI and task evidence may retain
selected reports under governed artifact paths with an explicit retention rule.
