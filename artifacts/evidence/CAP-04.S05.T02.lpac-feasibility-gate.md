# CAP-04.S05.T02 Windows LPAC feasibility gate

This is a failed, test-owned feasibility probe for the claimed task, not qualifying
completion evidence. It does not amend approved CAP-04.S05 §9.2 or ADR-0028. The
ordinary-AppContainer comparison is diagnostic only and cannot be used as a fallback.

## Host, exact inputs, and rerun

- Host observed by Python: Windows 11 x64, build 26200 (`AMD64`); Python 3.14.6;
  Rust 1.96.1. Claim HEAD when probed: `e19f6f28f7fbc2c3fd6421935591a590884240bb`.
  These source files were uncommitted during the probes, so no log is a
  commit-bound acceptance receipt.
- Build the fixed native probe with
  `.venv\Scripts\python.exe tools\plugin_worker_probe_build.py --output artifacts\tmp\<fresh-native-package> --report artifacts\tmp\<fresh-native-report>.json`.
  Output paths must be new. The command uses the checked-in Cargo lock, offline
  dependencies, and a release build.
- Run the focused real-boundary test under the normal Windows user identity with
  `.venv\Scripts\python.exe -m unittest tests.connectors.test_plugin_lpac_boundary -v`.
  The default Codex filesystem sandbox identity cannot create a test-owned
  AppContainer profile (`0x80070002`); that is an identity limitation of the
  test harness, not an LPAC platform verdict.
- The ignored, local diagnostic scripts
  `artifacts/tmp/CAP-04.S05.T02.run_native_probe.py` and
  `artifacts/tmp/CAP-04.S05.T02.run_appcontainer_diagnostic.py` rerun the
  R13/R12 DLL comparisons against their preserved ignored package inventories.
  They are not production code or portable acceptance inputs.

| Input | SHA-256 |
|---|---|
| `Cargo.toml` | `1fce64d0ac40be813dc735aed7f5bf1b5d3cea5417c26c904e4a25152f1d020c` |
| `Cargo.lock` | `e79e3acb55eb2bbb68390da1204076b6c364de0e3dde2882253ab8dc6a7fa9f8` |
| `workers/windows/lpac_launcher.py` | `f0d578d017de020c8e0a46ccb878e1a3e36b9f19117eb5dd67d69e7328eb3da0` |
| `workers/windows/protocol.py` | `60949306574ebdc132085d3ac5f8e262ff4e9883d9a296f90a571017181c5e72` |
| `workers/windows/probe/Cargo.toml` | `cc0ee221767d5f9b1aedfecdf1f05508b76d65335560b8dafcc06824b4d1553f` |
| `workers/windows/probe/src/main.rs` | `28829d9d3c5de45ce808a4f88c110aac88ac54d4ce1f56de81fcefe3b9430062` |
| `tools/plugin_worker_probe_build.py` | `9a4b4934cd71e1483d49e4750477c4e3c28d4cd8eb047b0c0b595df44cbc203c` |
| `tests/connectors/test_plugin_lpac_boundary.py` | `5b82bc6502c262463daa1599e9c0e6b81682d02a7d13fa0a197cbcb46928c545` |
| Native R25 inventory JSON | `27347f1ef9e838d98c241fa14aad55cdde451b0508c5c70adec1f92457ed6bdb` |
| Native R25 packaged EXE | `7a553e8e73c0c07e4eaa3c9f42e296395a9e5b89c2304c8c1a43534722e0cfcf` |
| Python diagnostic inventory JSON | `e35a8ed0afcaa087e86e1600f9da235b73b61c436641c99c205002f69aae2b32` |
| Python diagnostic packaged EXE | `96de2b6a2c82b5f90fee3b6cc347735c2a8452d0b97996267dd831aeca79bb6a` |
| Python diagnostic `python314.dll` | `dd764da43011c90fb33cdc9ff88b0180537669f60f3d7d56b5095b33ce4b3cd7` |

The R25 native package is under ignored
`artifacts/tmp/CAP-04.S05.T02.native-probe-package-R25`; its inventory lists
every packaged file hash. The Python diagnostic image and runtime are under
ignored `artifacts/tmp/CAP-04.S05.T02.probe-package-debug`. No user path,
account name, or session identifier is recorded in this tracked packet.

## Observed boundary results

The trusted launcher creates a distinct AppContainer profile, explicitly
requests ALL_APPLICATION_PACKAGES opt-out with zero capabilities, verifies the
resulting token's AppContainer SID and LPAC-style access decision before resume,
passes only three listed pipe handles, and assigns a kill-on-close, one-process,
256 MiB Job Object. The native packaged worker starts inside that boundary and
receives a length-prefixed, nonce/sequence-bound private control frame. Its
test-owned unrelated read, outside write, and direct loopback attempts were
denied in R24. A public egress request was not made; public egress remains
unproven. The synthetic parent environment-secret check was added to the
fixture after R24 but has not received a completed real-boundary assertion.

Two mandatory conditions remain failed:

1. The packaged PyInstaller/Python 3.14 worker exits before user code with
   `LoadLibrary: Access is denied` on its hash-verified `python314.dll` (R04).
   Native LPAC diagnostics can read that DLL, open it for `GENERIC_EXECUTE`,
   map it without import resolution, and load its direct PE imports and an
   unsigned minimal native DLL; normal `LoadLibraryW` still fails with Win32
   error 5 (R08, R09, R13). The same Python DLL loads in an ordinary,
   zero-capability AppContainer when LPAC's ALL_APPLICATION_PACKAGES opt-out
   is disabled (R12). CPython's Windows DLL entry point only records the
   module handle, so the unresolved denial is in loader/import/CRT startup,
   not a proved Python-code permission request. No exact denied dependency
   or read-only resource has been identified for a safe ACL fix.
2. The real LPAC native probe can create files in its redirected AppContainer
   `AC` profile and `AC/Temp`. The exact test-owned DACLs include package-SID
   `DENY(W)` after staging (R23). Additional explicit package-SID
   `DENY(WD,AD,DC)` on both directories also left both writes allowed (R24).
   The test therefore fails closed with `lpac-ambient-authority-not-denied`.
   All disposable profile folders were absent after the failed probes;
   this verifies cleanup of these test-owned profiles, not the required
   during-execution no-write invariant.

| Ignored local log | SHA-256 | What it establishes |
|---|---|---|
| `artifacts/tmp/CAP-04.S05.T02.lpac-default-sandbox-failure.log` | `3df7df2a6af805848559d7a039e2b3f7eb3fa0fded3c4478039af5238a9c24b6` | Sandbox identity cannot create profile. |
| `artifacts/tmp/CAP-04.S05.T02.lpac-profile-stage-R04.log` | `f9be17f27957e499d83b641acdff117c4430ddf2f47020adbf68b5e409ab30e9` | Python DLL LPAC load failure and staged ACL. |
| `artifacts/tmp/CAP-04.S05.T02.native-lpac-image-map-R08.log` | `236cd65fd57bc7932796b83fe4722c9c7537c899d37bf0f24ee48c0f9d31133f` | Read/map/import comparison. |
| `artifacts/tmp/CAP-04.S05.T02.native-lpac-minimal-dll-R09.log` | `1f7df528c7b66789132423266f74c221abadd11ea127529b4f1d4eb4ef9829bb` | Minimal DLL loads; Python DLL fails in LPAC. |
| `artifacts/tmp/CAP-04.S05.T02.ordinary-appcontainer-native-R12.log` | `0c65203f1d05d7a4b41536a610cee81fc2bea48ebc591ac3884191341a101306` | Diagnostic ordinary AppContainer Python DLL load succeeds. |
| `artifacts/tmp/CAP-04.S05.T02.native-lpac-execute-search-R13.log` | `96c0cb9b824b9209e7f081a2dd377770e9c3eb516953ba33c99893293cbdef1a` | DLL execute open succeeds; restricted search still fails. |
| `artifacts/tmp/CAP-04.S05.T02.native-lpac-profile-acl-R23.log` | `95abe327380088c2692749b5de320b3f28cd4e311407022e217374ecf0b90c88` | Post-deny AC and Temp ACLs. |
| `artifacts/tmp/CAP-04.S05.T02.native-lpac-profile-explicit-deny-R24.log` | `8646334227923703b528b10619c2dd736e5a641bc8359b5795e3682e14c43286` | Real LPAC writes still allowed after explicit deny. |

R04–R13 used successive ignored diagnostic-source revisions. The hashes above
bind the logs and preserved binaries, not a claim that the current ignored
source revision generated every historical log.

## Selected partial checks

The focused grant, trust, broker, v21/legacy-migration, and sidecar package
selection ran 56 `unittest` cases. Fifty-five passed and one symlink case was
skipped under the sandbox token; the strict sidecar inventory assertion failed
because its expected module list omitted the new `plugin_broker` module. That
expected list was corrected and the exact assertion passed on rerun. The
packaged sidecar build and artifact verification passed in the original run.
`core_api_contract.py --check`, targeted Ruff checks, the framed-control test,
`cargo fmt --check`, `cargo check --locked --offline`, and `git diff --check`
passed. The focused real LPAC test cannot create a profile under the default
Codex sandbox token (`0x80070002`); the separate normal-user R24 probe reached
the worker and failed the approved no-write invariant. These checks validate
partial components only, not T02 acceptance. The full `service` and
`security-local` profiles are deferred until the affected boundary can run
and the task has a complete candidate.

## Decision and exact resume condition

CAP-04.S05.T02 cannot be submitted as complete. The native fixture proves a
real Windows LPAC launch and some denials, but executes no connector package,
does not reach brokered plugin calls, and fails the approved no-plaintext-write
condition. The project grant, trust, broker, migration, and recovery code on
the branch remains partial work; none substitutes for the real worker proof.

Resume within the approved design only after a reproducible Windows x64
package loads the approved Python connector runtime under verified LPAC,
and a packaged hostile worker cannot write to its redirected profile, temp,
project, or other local paths, or use direct loopback/public egress. Then
integrate exact verified package bytes, bounded data/control IPC, current
grant and publisher-trust revalidation (or immediate cancellation of workers
affected by trust revocation), broker policy checks, cancellation/restart
behavior, and independent
commit-bound task review. If the two failed invariants cannot be met without
weaker isolation or writable scratch, use the append-only ADR/scope amendment
route and explicit human approval before changing that boundary. Do not fall
back to ordinary AppContainer or same-user execution.
