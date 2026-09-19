# CAP-04.S01.T02 — actual native import review

Observed on Windows x64 at exact committed candidate
`e80c53e8b57be6a8ac09569a0f051a00459994fe`, with fixed product/native/Core
inputs. Synthetic fixture retained under
`artifacts/tmp/directory-dialog-cap04-s01-t02-native-0920c`.
No ordinary project, vault, sign-in setting or credential interaction.

The existing `build_project_probe()` helper built and authenticated the actual
product renderer and native fixture executable (SHA-256
`82cd61331cedddd3b640378ab60bdc8a05a08709a732d46fbb458305f771d900`).
It verified Cargo artifact identity and embedded Common Controls 6/asInvoker
manifest. Explicit fixture substitutions: test-owned policy/vault, default
project parent, temporary WebView/runtime locations and synthetic lifecycle
launcher. Actual renderer/Tauri IPC, native file/folder dialogs, workflow session,
supervised Core, Windows DPAPI providers, SQLCipher project/object storage and
durable worker were exercised. This is not a frozen production-package journey.

## Observed journey and durable outcomes

1. Fresh unlocked start required no credentials and opened no project. Created
   and explicitly opened a synthetic project using its preselected test parent.
2. Selected a 151-byte, three-record semicolon CSV through the actual Windows
   chooser, with only store/inspect rights confirmed. Four parsed IR rows include
   the header. Repeated title columns were initially conflicting.
3. Corrected the mapping to the second title column and DOI column (revision 2).
   Calculated the complete-draft summary through the real worker: three included
   records, one context row, one missing DOI, one DOI candidate group containing
   two records. Comparison retained distinct raw and accepted values; no merge.
4. Selected the candidate page and excluded its two records (revision 3).
   Downloaded the complete diagnostic CSV through the native folder dialog.
5. Closed normally, relaunched the same isolated fixture, selected/opened the
   project explicitly, and verified revision 3, mapping and exclusions survived.
6. Confirmed cancellation. The preview became terminal while source and audit
   remained. Closed normally; both lifecycle receipts report exit 0, no pending
   request and admission closed.

Post-close read-only audit through the actual protected database provider
confirmed one preview/chunk/seal, four IR records, one accepted parse completion,
draft revisions 1/2/3, two explicit record decisions, eight preview events and one
summary completion. Latest event: cancelled. Canonical record identities: zero.
The database is not plaintext SQLite; retained source SHA matches its 151-byte
seal. The 265-byte report has one header, both exclusion diagnostics and no raw
reference values, DOI, names or paths. Report SHA-256:
`c0663ca1a6e172d6f26794fb60d7b38215aadf3ff7e2e86d1e6206ae85119cf5`.
Ignored lifecycle logs, source, database and diagnostic report remain available.

## Preserved setup failures and defect

- Raw Cargo build omitted the example's required activation manifest and exited
  at startup with C0000139. The existing manifest-validating helper was used;
  no production assertion or boundary was relaxed.
- The clone lacked its ignored pinned-toolchain binding; a local junction to the
  existing toolchain restored the documented helper path.
- A source outside the fixture's permitted projects directory was denied before
  any import. The synthetic source was placed inside that boundary, not bypassed.
- The first shell audit ran under the sandbox identity and could not read the
  user-protected fixture. The approved unsandboxed read-only audit used its exact
  vault. The database wrapper denied a query-only PRAGMA; the final audit used
  permitted SELECTs only, without altering the wrapper.
- The native batch-list status lagged the selected pane. Preserve and close this
  finding through the focused regression/correction described in checkpoint-16
  disposition; this native run does not prove that later renderer correction.

## Packaging coverage and explicit deferral

At exact e80, the existing test
`CoreSidecarPackageTests.test_packaged_sidecar_runs_without_system_python_and_detects_missing_runtime_file`
passed in 22.834s from the clean short root checkout. It built the real frozen
artifact, validated its inventory/size, ran `--check` without system Python and
proved missing-runtime detection. The first identical check in the longer clone
path failed during packaging with a Windows path-length FileNotFoundError
(24.413s); retain that setup failure separately from the successful shorter run.

Checkpoint-16 named production packaging as upcoming integration work. This
append-only selection clarifies that package loading is now checked, while the
full frozen `--supervised` import/summary/report/restart journey remains required
at CAP-04.S01 integration/W2 packaging qualification. Independent authority
preflight found it is not an explicit T02 acceptance criterion; approved slice
section 9.2 and verification guide 8.1 reserve broad profiles for those stages.
This does not claim frozen equivalence or waive any demonstrated packaging defect.
