# CAP-04.S05.T02 Windows LPAC feasibility gate

This is a failed, test-owned feasibility probe for the claimed task, not qualifying
completion evidence. It does not amend approved CAP-04.S05 §9.2 or ADR-0028. The
ordinary-AppContainer comparison is diagnostic only and cannot be used as a fallback.

## Host, exact inputs, and rerun

- Host observed by Python: Windows 11 x64, build 26200 (`AMD64`); Python 3.14.6;
  Rust 1.96.1. Initial claim HEAD: `e19f6f28f7fbc2c3fd6421935591a590884240bb`;
  R26–R28 ran after partial-work commit `2cc9b3c0df9dfe1fffb3cd498bd88b19942cbb54`.
  Earlier source was uncommitted, and R26–R28 use ignored diagnostic sources;
  no log is a commit-bound acceptance receipt.
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
- The bounded follow-up scripts
  `artifacts/tmp/CAP-04.S05.T02.user_sid_deny_probe.py`,
  `artifacts/tmp/CAP-04.S05.T02.r27_probe.py`, and
  `artifacts/tmp/CAP-04.S05.T02.r28_probe.py` replay only against new,
  disposable AppContainer profiles under the normal user identity. R27/R28
  use the ignored R27 native diagnostic image and package inventory. They
  restore test-owned descriptors and delete the profile in `finally`.

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
denied in R24. R26 and R27 also denied a synthetic parent environment-secret
sentinel. A public egress request was not made; public egress remains unproven.

Through R28, two mandatory conditions remained failed; the R29a–e native
follow-up below updates the second condition for its tested fixture only:

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
2. Through R28, no no-plaintext-write boundary had passed. The real LPAC native
   probe created files in its redirected `AC` profile and `AC/Temp` despite
   package-SID `DENY(W)` and explicit `DENY(WD,AD,DC)` on those directories
   (R23/R24). An ordinary-user-SID write deny on just the three directories
   blocked the sampled new-file creations (R26), but R27 showed append,
   overwrite, alternate-data-stream creation, and deletion remained allowed
   on pre-existing files in both AC and Temp. R27's owner/DACL change calls
   returned Win32 5, but its user and OWNER RIGHTS deny ACEs were not applied
   to every pre-existing file. R28 applied both deny classes to all 15 staged
   objects, including the runtime image; `CreateProcessW` then failed with
   Win32 5 before the worker started. R28 therefore establishes no worker
   denial result. All test-owned profile folders were removed after each
   experiment. Cleanup does not prove the during-execution no-write invariant.

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
| `artifacts/tmp/CAP-04.S05.T02.user-sid-deny-single-R26.log` | `31312294525cda479962117352336c67b83ffb10f40760516029ac30710d5aba` | Directory-only user write deny blocked sampled creates; owner/DACL tamper was untested. |
| `artifacts/tmp/CAP-04.S05.T02.r27-owner-rights-adversarial.log` | `7a2d5fb5b433511cdfe82fcbc94391212700f545bad21881f0cec2f276f2c197` | Existing-file append/overwrite/ADS/delete succeeded; owner/DACL calls returned 5; cleanup succeeded. |
| `artifacts/tmp/CAP-04.S05.T02.r28-recursive-file-acl.log` | `e64b525b7cc959fec79498a15d8eaac007973b108d9655e7f10e65b9c2bc74f2` | Recursive file/dir ACLs blocked process creation; all 15 descriptors restored and profile deleted. |

R04–R13 used successive ignored diagnostic-source revisions. The hashes above
bind the logs and preserved binaries, not a claim that the current ignored
source revision generated every historical log.

The follow-up scripts and generated image are ignored local diagnostic inputs,
not committed product assets. Their exact SHA-256 digests are:

| R26–R28 input | SHA-256 |
|---|---|
| R26 runner `artifacts/tmp/CAP-04.S05.T02.user_sid_deny_probe.py` | `5d83b9879a6cca2b7bd8980b7f8f9e463706fbf05f27bf448a6edd7fa9c9e39a` |
| R27 crate manifest | `03ab9655ec6b154e9a9e6196cbb914cd79e5f56d1769accff38ed66f98805cd2` |
| R27 crate lock | `998efc3d84d70b83e63463f500b226e1ab6c637389f4c6ced9d84f3142931b6a` |
| R27 worker source | `b8690dc8862653eac29f56e980af6a1631de882c10843c988d1bc07fb19038b1` |
| R27 package builder | `9df4a93f875533caf72fabc7fac74de497cae06c6d04ca860d5dafdf5fe368bb` |
| R27 runner | `23784757582d77e9ad636c4324902d181ce052749e150dbccb25786555177501` |
| R27/R28 package inventory | `f8557a4c51e18db435f9a0217da714fecbe6a583416a257a21644a41174da291` |
| R27/R28 packaged EXE | `b08e6ed3256ff79e96a1f65253fbce78e63f0211593c069fc8da355d28eac90e` |
| R28 runner | `1e27e4829c2b0298d4617286a7ac4c69dbbc3b61eaf45a5c0c3989e6e4f5b1c9` |

R27 queried the three directory owners: each matched the ordinary user. Its
AC/Temp environment paths matched the paths returned by
`GetAppContainerFolderPath`, but canonicalization inside the worker returned
no path, so canonical equivalence remains unproved. The R27 ordinary-user
inherited Full Control ACE included WRITE_DAC, while both owner/DACL change
calls returned 5 under the combined directory-only denies. The pre-existing
files retained write access. R28's per-object deny was verified on AC, Temp, two
existing files and the runtime image, but the process never launched. The
R28 CreateProcess failure may reflect a loader access request denied on that
image or an ancestor; its exact requested access was not traced.

## R29a–e separate-runtime native follow-up

These ignored diagnostics used fresh, disposable AppContainer profiles and a
separate test-owned native runtime copy. All ACL changes applied only to those
test-owned trees; each run restored any saved DACLs, deleted its profile with
`DeleteAppContainerProfile` (HRESULT 0), removed its runtime copy, and left no
matching residual directory. R29a stopped before launch because the trusted
runtime-root restoration handle unnecessarily requested `WRITE_OWNER` (Win32 5).
R29b used `READ_CONTROL|WRITE_DAC` and launched the separate image, but an early
worker `is_dir` check returned false on AC/Temp, so no adversarial matrix ran.
R29c retrieved the worker's AppContainer token SID but its in-worker
`GetAppContainerFolderPath` call returned `0x80070005`; no matrix ran.
R29d used the parent's verified `GetAppContainerFolderPath` result to supply
exact disposable AC/Temp/runtime *adversarial targets* in its ignored test
frame. Every worker denial probe completed, but the parent attempted its
independent file-integrity read while the disposable DACLs were still locked,
receiving `PermissionError`. It did not qualify file integrity. This test-only
target frame is not the approved production IPC contract, which remains
path-free.

R29e repeated the **same R29d native image and adversarial operations**, moving
only the trusted parent integrity checks to after worker exit, job termination,
and restoration of saved disposable DACLs but before deletion. On Windows 11
x64 build 26200, the parent verified the launched LPAC token: exact created
AppContainer SID, zero capabilities, and an access decision denying
ALL_APPLICATION_PACKAGES. Worker SID and test targets matched the parent's
fresh `GetAppContainerFolderPath` AC path, its Temp child, and the staged image
directory. For each of AC, Temp, and runtime, create, append, overwrite, ADS,
subdirectory, delete, and rename attempts were denied. The runtime EXE's
append/overwrite/ADS attempts were denied. Owner and DACL change attempts on
AC, Temp, runtime directory, and image returned Win32 5; follow-up creates
remained denied. The unrelated-read sentinel, outside-write sentinel, direct
loopback, and synthetic parent environment-secret checks denied. After DACL
restoration, all seeded contents and names were intact, ADS was absent, and
the staged runtime matched its exact package inventory. All 12 profile and six
runtime DACL restorations returned 0; both disposable roots were absent.
The R29e harness returned `qualified: true` for this **native test-owned
boundary probe**, not for CAP-04.S05.T02 or the Python connector worker.

The ignored inputs and logs below are local diagnostic evidence, not a
commit-bound acceptance receipt. R29a/b share the R29 image; R29d/e share the
R29d image. All hashes are SHA-256. The run-specific harness and log basename
is under `artifacts/tmp/CAP-04.S05.T02.`; the native source is each ignored
`r29*-worker/src/main.rs`, and the inventory is the corresponding ignored
`r29*-package.json` (R29c uses `r29c-tokenprofile-package.json`). The harness
basenames, in run order, are `r29_probe.py`, `r29b_probe.py`, `r29c_probe.py`,
`r29d_probe.py`, and `r29e_probe.py`. R29e ran under the normal Windows user
identity with `.venv\Scripts\python.exe artifacts/tmp/CAP-04.S05.T02.r29e_probe.py`
against the hash-verified ignored R29d package.

| Run | Harness SHA-256 | Worker source SHA-256 | Packaged EXE SHA-256 | Inventory SHA-256 | Log basename and SHA-256 |
|---|---|---|---|---|---|
| R29a | `4438d90195c0de7b10bfd93f3920654d4f533d0e9d12becaf3d06914603c5c50` | `0ceae0e9631391bb8a543aad7de5f1e218a1272f0b5efe96f2a328f7ad988003` | `208cbc4b92294341114c0bcdcc1618f99f6210a635322bf7a7d35da44788bc47` | `6c152714a10042d979e5c670dbab12dcadcd85b5bb1d0e8ee0efa3a1f9521597` | `r29-separate-runtime-readonly.log` `7be9f531a68713a6f21f03c79c78b6073e80b50542464260c8be172436e6e07f` |
| R29b | `0417596affc0d5eeadec7d41ce245785f264c4845f6e6033c3eaddf3bdd13ec8e` | same R29 source | same R29 EXE | same R29 inventory | `r29b-separate-runtime-readonly.log` `74d580d26c2f0f5ab5dc270c10ef588bdb245aedb5961b1cb2bb007773f2a753` |
| R29c | `4999c2c5e94ecf5ff7dfceacd7bb0e46c0e026dc75f6ba111070393e6440ff22` | `de31e001a079defb869bf838e346108dbaf5cae09603f92feaab2e0e2c545242` | `6b3a9500dde484b05dc4a6a3539959476a8fbcf2c842eea8fbc97cc08b2f37ef2` | `7d11c1d77daa09361a471cb2b523604c1c99ec99e0db4d4d0541c373f90dd9b8` | `r29c-tokenprofile-separate-runtime.log` `1a4c323a115725b33fb4ec73d96a391c3ac61a117d3f8232aab6d5d737d65c39` |
| R29d | `c8df905d1b8b8b477f6a9e2164b7032851eab12713bf7b7036cb1c654a85ffb4` | `ff3db5d9112260f0c6e14d1a5624f14f8c8f157b08a2f79da287f16e54ec0d04` | `1d045e6ea27ad9ccb17296bd8043c8f929622fef317d5412239146b299927e64` | `8319f74d751194d30f31c9d9a0f98cfc5ff6960379d692e84a18c3c876f85a1c` | `r29d-targeted-matrix.log` `5f6467a3a141de3960bbb6c2c285c22e07a1931b1522184b129ad8d684542859` |
| R29e | `5722f682dfbeac1bf66d759558fdd0525fc905380b8f386b68ae49bf3fd49dc8` | same R29d source | same R29d EXE | same R29d inventory | `r29e-postrestore-integrity.log` `5fd0ac3c947f12a84de3651ea25127d4cbb45c9680510ea0c6d5caa3cd9df508` |

The launcher configured a three-handle allowlist and assigned the suspended
worker to a kill-on-close Job Object before resume; R29e did not independently
enumerate child handles or test parent-death killing. It did not test public
internet egress, every ambient filesystem location, other-job IPC, binary
input/output frames, hostile connector execution, broker authorization,
resource exhaustion, cancellation/restart, or production runtime signing.
Inside the locked AC/Temp, `is_dir` and canonicalization returned false/null
even though the raw target and environment paths matched the parent-queried
profile; canonical equivalence remains unproved. The Python 3.14 packaged DLL
still fails under LPAC, so native R29e cannot qualify the approved Python
connector execution or its no-write invariant.

## Matched Python DLL loader diagnostic after R29e

One bounded follow-up compared a copy of the packaged Python 3.14.6
`python314.dll` with a copy of the host-installed Python 3.14.3 DLL. Version
resources identified both versions, and their source digests were verified
before staging. A local PE import check found the same 19 direct DLL names and
no delay imports in either image. Two ignored, two-file packages used the
**same native framed loader EXE**, relative layout, per-object read-only
runtime ACL sequence, LPAC launcher, and recursive disposable-profile no-write
ACLs; only `python314.dll` bytes differed. Each package ran in its own fresh
LPAC process and AppContainer profile. The original installed DLL and existing
security settings were not changed.

Both runs verified a zero-capability LPAC token with ALL_APPLICATION_PACKAGES
denied. The DLL could be opened for read and `GENERIC_EXECUTE` in each worker,
but absolute-path `LoadLibraryW` failed with immediate `GetLastError=5` for
**both** 3.14.6 and 3.14.3. After each process exited, the parent verified the
profile content and runtime inventory were intact, restored all 12 profile and
four runtime DACLs, received `DeleteAppContainerProfile` HRESULT 0, and found
both disposable roots absent. This matched-layout result does not support a
3.14.6-specific DLL regression as the sole cause. It does not identify the
denied dependency/resource or prove a Python worker can start: the minimal
two-file package is not the full PyInstaller runtime, and no Python code ran.
No ordinary-AppContainer fallback is authorized.

## R30 process-local loader-notification follow-up

A fresh, ignored native diagnostic compared the same two-file Python 3.14.6
package, read-only runtime ACL sequence and recursive disposable-profile
no-write ACL sequence in zero-capability LPAC and ordinary AppContainer. The
ordinary AppContainer case was a diagnostic comparison, not an approved worker
fallback. The worker registered `LdrRegisterDllNotification`, queried its own
process signature and image-load mitigation policies, attempted absolute-path
`LoadLibraryW` on the packaged DLL, then loaded `VERSION.dll` as a callback
positive control. Its notification callback copied only bounded module names
into a fixed buffer and reported them after loading returned.

In LPAC, the Python DLL again failed with Win32 error 5 and **zero notifications
before the control load**. The subsequent `VERSION.dll` load succeeded and
reported `msvcrt.dll` and `VERSION.dll`, establishing that notifications worked
in that same LPAC process. In ordinary AppContainer, the same Python DLL loaded
and eight notifications appeared before the control, ending with
`python314.dll`. Both processes reported successful mitigation-policy queries
with signature and image-load flags zero. Thus those queried policy flags do
not explain the tested difference; no notification identifies the denied
resource. The callback cannot observe a failed file or policy check, so the
result does not prove where the denial occurred or that all relevant
mitigations match. No Python code or plugin ran in the LPAC case.

Both runs verified their token mode and zero capability count. Both disposable
profiles and runtime copies passed post-restore content/inventory checks, all
saved DACLs were restored, `DeleteAppContainerProfile` returned success, and
the disposable roots were absent. The ignored raw log contains no recorded
account/profile path or traceback. This is diagnostic evidence only, not a
commit-bound acceptance receipt or production worker qualification. R30 did
not repeat the hostile no-write/egress matrix; post-run integrity cannot rule
out a transient write during worker execution.

| R30 ignored input/output | SHA-256 |
|---|---|
| Native worker source `artifacts/tmp/CAP-04.S05.T02.loaderdiag-control-worker/src/main.rs` | `54c240236c4e7675d5f88f461ac6bdc67131e913bacb2c327af1e041559273d1` |
| Worker `Cargo.toml` / `Cargo.lock` | `8efee4b9962868608744caca26512d33283f6f12d9e904c9e900644baaf09d17` / `03419592143215c267fb3b2a7d12878ba8a1c9c31cc47f93ccfab71b69506840` |
| Package builder `artifacts/tmp/CAP-04.S05.T02.make_loaderdiag_control_package.py` | `11c63c0daa680de3e8a97f693bb60e3b8bf5c1119e3dcd3d274800e2ecdc4e1a` |
| Runner `artifacts/tmp/CAP-04.S05.T02.loaderdiag_control_probe.py` | `dd886a7fa77073cc08e79ff2373213137639984f97bb927a08ab80969fc2b83c` |
| Package inventory / native EXE | `7e51f544369ce74e4023eb8b6373d76f62819c96dd02ea8acf1f0dade97ed1a2` / `fe264b53e7210720d4ceb65502c23191dcb3c5cabe2f6d4855ea5f9b2874671a` |
| Packaged `python314.dll` | `dd764da43011c90fb33cdc9ff88b0180537669f60f3d7d56b5095b33ce4b3cd7` |
| Raw log `artifacts/tmp/CAP-04.S05.T02.loaderdiag-control-matched.log` | `6cd5576736325a7990754ff2dfa3d9a8b0b3f828a86ffefe2992fe41266ecf60` |

## R31–R32 embedded-manifest discriminators

The packaged Python 3.14.6 DLL contains an embedded `RT_MANIFEST` resource at
ID 2. Its XML specifies `asInvoker`, supported Windows versions and
`longPathAware`, and depends on Microsoft.Windows.Common-Controls v6. Microsoft's
[side-by-side resource guidance](https://learn.microsoft.com/en-us/windows/win32/sbscs/using-side-by-side-assemblies-as-a-resource)
states that DLL manifest ID 2 participates in loader activation. These facts
motivated two fresh, ignored, test-owned DLL-copy comparisons. Neither copy is
a production artifact or a signed-plugin/runtime qualification.

- **R31, manifest hidden from the loader:** one four-byte PE resource-type ID
  field was changed from 24 to `0x7fff` on a disposable DLL copy. Its size,
  executable code and imports were unchanged; only two byte positions in the
  file differed from the original (offsets 6526488 and 6526489). With the
  same R30 native EXE, zero-capability LPAC token, read-only runtime and
  disposable-profile no-write ACL sequence, `LoadLibraryW` **succeeded** and
  eight loader notifications included `python314.dll`. This strongly associates
  the original pre-notification denial with processing the embedded manifest,
  but does not identify a denied resource or prove Python initialization.
- **R32, Common-Controls dependency removed only:** Microsoft `mt.exe` embedded
  a manifest retaining ID 2, `asInvoker`, supported-OS entries and
  `longPathAware` while removing only the Common-Controls dependency. PE code
  and imports were unchanged. The same LPAC load **still failed** with Win32
  error 5 and zero pre-control notifications. Thus the Common-Controls
  dependency alone does not explain the denial. Suppressing the manifest as a
  loader manifest, rather than removing that one dependency, distinguished R31.

Both runs verified zero-capability LPAC with ALL_APPLICATION_PACKAGES denied,
restored all 12 profile and four runtime DACLs, confirmed post-restore profile
and runtime integrity, deleted the disposable AppContainer profile successfully
and found the disposable roots absent. Neither ran Python code or repeated the
hostile no-write/egress matrix; post-run integrity cannot rule out transient
writes. No original runtime DLL, installed Python, host security setting or
tracked product file was altered. A source-built Python 3.14.6 runtime without
the DLL manifest is now a bounded ADR-0028-conforming *candidate to test*, not
an approved worker. The package's native extension DLLs also require their
own manifest/load qualification.

| R31–R32 ignored input/output | SHA-256 |
|---|---|
| Original Python 3.14.6 DLL / shared native EXE | `dd764da43011c90fb33cdc9ff88b0180537669f60f3d7d56b5095b33ce4b3cd7` / `fe264b53e7210720d4ceb65502c23191dcb3c5cabe2f6d4855ea5f9b2874671a` |
| R31 modified DLL / inventory / runner / log | `79c7ec3f33315683099933ede83783bb0740c085a603e8b79fa0eb6f6dc4d68b` / `9e186f9ad674eb7dd8b9f5fd13c5d376ea2d9d6ef24126980d2f2690c1fea3f1` / `1610b9c0611548241d2c3ceebda4dfff16b6cff95686499e9bcf200c5e36cef5` / `692fa85690aad2a4838ec455fa61ebfb4d1bb5160cf6eddfb44c8c1b1e14f224` |
| R32 no-dependency manifest / modified DLL / inventory | `48ff4a9ec1b2b31f2940351fe58a78e3b1a5d36ede558d4370633ed3f3a235ed` / `0ba28292c108a9b42f5e599286d9c65fb4a0e521a2f3a2a6106e6b24f6c8a07c` / `9e334ceedb5dc4841159d8e57e1573842df65541358702316c0aff0709889d2a` |
| R32 runner / log | `86e317ee1ecd6ad047e3833995e524e006f5c64c3e2c0bb20df5e81fcaca9b85` / `6481a63debe01eb75aaf8aaa5b3f8567353a68699b09fdba86a4ac040fa2ffa` |

## R33 strict dependency-search comparison

A separate fresh package retained the **unmodified**, hash-verified Python
3.14.6 DLL and invoked absolute-path `LoadLibraryExW` with only
`LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32` (`0x900`).
Unlike R13's broader `0x1100` search, this excluded ordinary application/user
search locations for dependencies. Under the same verified zero-capability
LPAC and disposable read-only/no-write setup, it still returned Win32 error 5
with zero notifications before a successful `VERSION.dll` callback control.
Profile/runtime post-restore integrity, all saved DACL restorations, profile
deletion and disposable-root absence passed. This rules out a simple standard
dependency-search-path correction; it does not identify the denied resource
or qualify the worker. No Python or plugin code ran.

| R33 ignored input/output | SHA-256 |
|---|---|
| Worker source `artifacts/tmp/CAP-04.S05.T02.loaderstrict-worker/src/main.rs` | `b447c8afe776bb7993e3e3423aeb278d9f76021abe3068a4c5c2f602d18f5cad` |
| Package builder / inventory | `fc39e5d7fdd867bb64f55032c3f3dc2084d77ef1c258e0ded2d316d3285dafb6` / `b84f62988fdf594d8c1635ff9ef01099437ad73ff0ae6cda7cdddbb26d9299e2` |
| Runner / raw log | `5a32fbe580303f899a2af76af09d397640a0c91647e08740968190b4643f9f31` / `99a182b68c9232067e1b3918f4c8e63ca9539430f7a689fcee15b89e57327318` |

### Host-authorized resource trace if the source-build route fails

The exact resource behind the Python DLL's LPAC `LoadLibraryW` error 5 is
still unknown after R33. A bounded fallback diagnostic is one fresh, synthetic-only worker
launch under [Microsoft Process Monitor](https://learn.microsoft.com/en-us/troubleshoot/windows-client/shell-experience/troubleshoot-apps-start-failure-use-process-monitor),
filtered to the unique test worker process and stopped immediately after the
load failure. Process Monitor requires elevation and may load a system driver;
its raw trace can include unrelated local file, registry, and process activity
even when the later view is filtered. It is not covered by the existing W2
product approval. Obtain explicit host-owner authorization before downloading
or running it. Keep the binary and trace in ignored local files, do not upload
the trace, and remove the test-owned trace and any temporary diagnostic setup
after extracting only the denied resource and minimal content-free finding.
Any proposed permission change must then be checked against ADR-0028 before
another worker run; registry/COM or broader profile authority needs an approved
amendment, not a diagnostic shortcut.

| Ignored diagnostic input/output | SHA-256 |
|---|---|
| Packaged 3.14.6 source DLL | `dd764da43011c90fb33cdc9ff88b0180537669f60f3d7d56b5095b33ce4b3cd7` |
| Host-installed 3.14.3 source DLL | `1ac15e2224581fc678bbd17728b9aa538d47b891b72c76499ef07e54cd74f151` |
| `artifacts/tmp/CAP-04.S05.T02.dllpair-worker/src/main.rs` | `4d671749cc81ffa17aa6f55d3ebb35fa31b14f99b5418878c80f6ce52d1bb4f4` |
| DLL-pair worker `Cargo.toml` / `Cargo.lock` | `8efee4b9962868608744caca26512d33283f6f12d9e904c9e900644baaf09d17` / `03419592143215c267fb3b2a7d12878ba8a1c9c31cc47f93ccfab71b69506840` |
| Shared native EXE in both packages | `797e0a7d58e0288605d3642b102d11319597a62e62118d6529a52e7d8745306e` |
| `artifacts/tmp/CAP-04.S05.T02.make_dllpair_packages.py` | `3c9c188a026f91c0e480b60a979439521b41ab2e1e372a737293f3a84c5080c1` |
| 3.14.6 / 3.14.3 package inventory JSON | `aa13b42a7e3833be5e19f947b2cfc420f02fcea96ec11acad72feb76ffca71d8` / `1ab849e8c83e00163f429ad01d293e5a59dabca65d81d4339010657ad91ae91` |
| `artifacts/tmp/CAP-04.S05.T02.dllpair_probe.py` | `8a41804df12a132efd9dd067c0c0dda62793ca52110d1ccd57acdee69a339ff1` |
| `artifacts/tmp/CAP-04.S05.T02.dllpair-lpac-3146-vs-3143.log` | `1de9d6e934ee7d463563f0ba1132f8b98edb93dc18aba415fa0651568bf773a7` |

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
Codex sandbox token (`0x80070002`); the separate normal-user R24/R27 probes
reached the worker and failed the approved no-write invariant, while R28
failed at process creation. The later native R29e matrix passed its specified
no-write and direct-denial checks; it did not load Python or execute a
connector. These checks validate
partial components only, not T02 acceptance. The full `service` and
`security-local` profiles are deferred until the affected boundary can run
and the task has a complete candidate.

## Decision and exact resume condition

CAP-04.S05.T02 cannot be submitted as complete. R29e proves the specified
test-owned native LPAC no-write and direct-denial matrix, but the approved
Python connector image still fails before user code. R30 narrows the observed
loader stage. R31 makes a manifest-free source build a credible test candidate,
while R32 and R33 preserve the adverse dependency-only and strict-search
results. None identifies the denied resource or changes the gate. The native
fixture executes no connector package and does not reach brokered plugin calls.
The project grant, trust, broker, migration, and recovery code on the branch
remains partial work; none substitutes for the real worker proof.

Resume within the approved design only after a reproducible Windows x64
package loads the approved Python connector runtime under verified LPAC,
and a packaged hostile worker cannot write to its redirected profile, temp,
project, or other local paths, or use direct loopback/public egress. Then
integrate exact verified package bytes, bounded data/control IPC, current
grant and publisher-trust revalidation (or immediate cancellation of workers
affected by trust revocation), broker policy checks, cancellation/restart
behavior, and independent
commit-bound task review. If a packaged Python LPAC worker cannot meet the
required no-write and no-egress invariants without weaker isolation or writable
scratch, use the append-only ADR/scope amendment
route and explicit human approval before changing that boundary. Do not fall
back to ordinary AppContainer or same-user execution.
