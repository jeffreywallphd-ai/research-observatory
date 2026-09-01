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

The W1 policy authorizes only `W1-exit` as an affected-selection deferred owner;
generic names and later gates such as `G2` are rejected by both the API and CLI.
`desktop:performance`, `data:project-lifecycle-performance`, and
`data:storage-maintenance-performance` are gate-bound and therefore always
remain in `deferredCommandIds` during affected selection, including unknown and
safety fallback. They are retained for one serial execution at W1 exit.

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

## Wave-exit union

The W1 exit matrix is a governed, deduplicated union of `ai`, `data`, `desktop`,
`e2e-local`, `foundation`, `graph`, `security-local`, and `service`. It executes
each active canonical command ID once and cannot be narrowed with `--profile` or
combined with affected mode. Disabled `server` and `cloud` profiles remain
release-gated and are not enabled by this union. All three governed performance
commands remain selected exactly once in the active W1 union.

```powershell
python tools/verify.py --wave-exit W1 --selection-only --report artifacts/tmp/W1-wave-exit-selection.json
python tools/verify.py --wave-exit W1 --report artifacts/tmp/W1-wave-exit-verification.json
```

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
