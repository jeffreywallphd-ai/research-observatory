# Verification profiles

`tools/verify.py` is the task-facing verification entry point. Its canonical
profile and command graph lives in `verification-profiles.json`; every invocation
validates that contract before running commands.

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

## Profile ownership

| Profile | Intended checks |
|---|---|
| `foundation` | Repository, runtime, architecture, agent protocol, ADR, CI, Python quality, packaging-input smoke, unit, and backlog integrity. |
| `desktop` | Desktop unit tests plus governed UI conformance. |
| `service`, `data` | Core API/contracts and storage/migration behavior. |
| `documents`, `search`, `ai`, `evidence`, `graph`, `novelty` | Capability-specific unit/integration suites. |
| `e2e-local` | Local happy, denial, cancellation, restart, and recovery workflows. |
| `security-local` | Local security, dependency, secret, license, and vulnerability policy. |
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

Reports under `artifacts/tmp/` are local scratch. CI and task evidence may retain
selected reports under governed artifact paths with an explicit retention rule.
