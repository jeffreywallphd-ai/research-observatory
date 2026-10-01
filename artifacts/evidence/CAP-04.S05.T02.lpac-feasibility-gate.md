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

## R34 source-built runtime and packaged-worker comparison

The official CPython 3.14.6 source archive was verified against its published
SHA-256 (`143b1dddefaec3bd2e21e3b839b34a2b7fb9842272883c576420d605e9f30c63`).
An ignored, isolated source variant removes only the `2 RT_MANIFEST
"python.manifest"` resource line from `PC/python_nt.rc`; the source manifest
file itself is unchanged. Comparing all 5,100 extracted source files by hash
found exactly that one source difference. The variant sits inside this Git
checkout, so CPython build metadata can incorporate changing checkout state;
these local diagnostic binaries are source-input-reproducible, not yet
bit-reproducible production outputs. The x64 Release `pythoncore` build used local MSVC
BuildTools and CPython's pinned `zlib-ng-2.2.4` source dependency at commit
`a502e047655c31db29601def76ad6539acacf43d`. Its `python314.dll` is
6,860,288 bytes, SHA-256
`c8fccb6977142f060aab4de5b8b9ec371a9422b8b3468a4566abc0b26f7c561b`,
and has VERSION resource type 16 but no `RT_MANIFEST` type 24. An initial build
without zlib headers failed; the later bounded build succeeded. Neither result
is production packaging or a task receipt.

One fresh R30-style load probe gave that exact DLL read/execute-only runtime
access and the same disposable, read-only/no-write profile setup under a queried
zero-capability LPAC token. `LoadLibraryW` returned success and eight loader
notifications ending in `python314.dll`; `VERSION.dll` remained a positive
control. All 12 profile and four runtime DACLs were restored, both disposable
roots were absent, and profile deletion succeeded. This proves the core DLL
loads under the tested boundary, not Python initialization or connector safety.
The raw ignored host log is
`artifacts/tmp/cpython-3.14.6-manifest-variant/loader-lpac-host.log`
(SHA-256 `404312f066da122eb79b8f7ee1af92ee54c27ecbbc4a6eedcdabdf273ea1e18d`).

The R34 full PyInstaller probe then copied the original 58-file diagnostic
package, replacing only that exact core DLL. Under fresh zero-capability LPAC
and R29e-style no-write ACLs, execution reached Python module imports but
stopped at `socket.py`: importing the original `_socket.pyd` raised `DLL load
failed ... Access is denied`. That `.pyd`, like all nine included CPython
extensions, still embeds `RT_MANIFEST` type 24. The worker exited 1 with no
framed response. The harness verified no outside write, an intact read sentinel,
restoration of all 12 profile and 64 runtime DACLs, profile/runtime integrity,
successful profile deletion and absence of both disposable roots. The error is
preserved as adverse evidence; a core-DLL-only substitution does not qualify a
connector or prove full egress/write denial. No real project or credential was
used.

| R34 ignored input/output | SHA-256 |
|---|---|
| Source variant `PC/python_nt.rc` / unchanged `PC/python.manifest` | `47a869fe938a2bb7c0ef8d5a4ed2fcf5d182faa52aea5ad347203c7fbbb86b3e` / `7193b1d7f106dea927ec1687ff840302d88f6d352452c7207c68446454a22ba2` |
| Full-worker harness / prepared package inventory | `a76c63fd8de608de9857b63b47327f8ddbeaac73b55e2047af9ca0aa67ec5494` / `e625ad99e941584e837cdad4eb9f2f33a60201a74e39f9bd4d618033cc01fa47` |
| Raw launch failure / LPAC run log | `4d9fd53e30d9355310be4b25eea0906d9ced08dd48ee7be15349d191e2f0876a` / `b3f31a5bcc0ed5c9d398db2ac310390a44c220c1166b4daa2d8df6fdebe324ca` |

## R35 source-built `_socket` and Winsock initialization

The same isolated CPython variant built a manifest-free x64 `_socket.pyd`
(SHA-256 `cbf865e599e543ef3b28383691827f1a16d0f32c4a98873df7cf0a348790b652`,
VERSION resource only, `PyInit__socket` export). A fresh 58-file package
substituted this extension and the immutable R34 core DLL; its inventory SHA-256
is `34d6d45094aa2ec63c0a94ff262f7d5df011e20df10ddd2b04dc2b6633e57e52`.
An earlier R35 preflight raced a concurrent MSBuild reference rebuild of the
active source DLL and stopped at a file read before profile creation. It did not
launch LPAC; the successful later preflight used the separately snapshotted,
hash-verified R34 core DLL. No host-wide ACL was changed.

In the bounded R35 LPAC run, the replacement `_socket.pyd` loaded, removing
R34's DLL-load denial. CPython `socket.py` then failed during Winsock startup
with `ImportError: WSAStartup failed: error code 10107`. The worker exited 1
without a framed response. [Microsoft's documented `WSASYSCALLFAILURE` 10107](https://learn.microsoft.com/en-us/windows/win32/winsock/windows-sockets-error-codes-2) is
a generic system-call failure, not proof of a particular denied capability or
direct egress. The pre-imported `socket` in this test worker prevents its other
probes from running. All 12 profile and 64 runtime DACLs were restored;
profile/runtime integrity and outside-write/read sentinels passed, profile
deletion succeeded, and both disposable roots were absent. This is an adverse
runtime result, not no-write or no-egress qualification. The approved LPAC
capability set and ACLs were not broadened.

| R35 ignored input/output | SHA-256 |
|---|---|
| Harness / package inventory | `2ca747f623bfc2000001f12510b848b6369a219bf03622604b1ae332ea531456` / `34d6d45094aa2ec63c0a94ff262f7d5df011e20df10ddd2b04dc2b6633e57e52` |
| Raw launch failure / LPAC run log | `607e93b647b065c411e225a6eb0d07b6a5c10fda463af8dff01613db539394c4` / `dcaf3b9a5381b33b652cbf0d46992ce7498f41291cf657619a949fe6128f78fe` |

## R36 isolated Python probe without eager socket import

A separate, test-only PyInstaller worker deferred its `socket` import until the
direct-network probe. It retained the synthetic framed control, token query,
unrelated-read, outside-write, profile/temp-write and parent-secret sentinel
checks. The fresh 58-file package contained the hash-verified manifest-free
R34 core and R35 `_socket` extension. It was not a connector or signed
production runtime.

The R36 LPAC worker returned a valid frame: queried AppContainer/LPAC identity,
zero capabilities and ALL_APPLICATION_PACKAGES denial all passed. Unrelated
read, outside write, profile write, temp write and synthetic parent secret were
denied. `socket` initialization again failed with 10107; the worker reported
`directLoopback: not-tested`, so R36 explicitly did **not** qualify direct
egress. The trusted harness independently found no outside write and an intact
read sentinel, restored all 12 profile and 64 runtime DACLs, verified
profile/runtime integrity, deleted the disposable profile and found both roots
absent. This provides a narrow packaged-Python no-write/read/secret observation,
not a full hostile-connector or public-egress proof.

| R36 ignored input/output | SHA-256 |
|---|---|
| Test worker source / packaged EXE | `92dcd59fb9237b154be50c35b9c49c55b862c66e225d54723629ad742a2be37c` / `a28124206fc3e44bbd1c5ff5b1f0952292ce3fc733315f2928c163008ae72a5e` |
| Base inventory / exact replacement inventory | `620d444c3a6067c08f4dbdfa5ca7c19268cd9ae4e41ccb602765ef4226c5ca4d` / `f521c927a52e273a204ad9f62eec0e5a7e0592a6b53d367d11e94cfbf5ea9e29` |
| Runner / LPAC run log | `1d0bf09048adbdc6b0d3c8aff8924bbf8b3706ded5d27c3f8353cc911e6576f4` / `84e570a0c6f1802db8eda5360226abcaba84ee4b0d1725729251dec95b2f2950` |

## R37 local-only network-startup discriminator

R29e's native `directLoopback: denied` had grouped Winsock-startup failure
with `connect` failure, so it could not establish which operation denied.
A fresh native fixture separated `WSAStartup`, `connectAttempted`, connect
outcome and local-listener acceptance. Its ordinary-user control initialized
Winsock and connected to a disposable `127.0.0.1` listener, which accepted.
Under a queried zero-capability LPAC token, `WSAStartup` returned 10107,
`connectAttempted` was false and the listener did not accept. This confirms
no loopback connection happened in this fixture, but **does not** prove a
`connect` denial or public egress denial. No external address was contacted
or host network setting changed. All 12 profile and six runtime DACLs were
restored, post-restore integrity passed, and disposable profile/runtime roots
were absent after cleanup. R29e's other no-write/read/secret observations are
unaffected; its network result remains historically preserved with this
correction.

| R37 ignored input/output | SHA-256 |
|---|---|
| Native EXE / inventory | `21b5be1e0df5b14c6cc4c428b5dbd9fa784a9eb3237f857895a385420f266b1d` / `e41efae908c2545552c126a69dbff14e9780b87ff9f52cc3a5fe75908861fc3d` |
| Runner / LPAC run log | `25fa4d7bf7615572bc60efbd4f02b59910e62e70df39a7e1f63dc77d63293697` / `0af7a76b7980f974bec7b9474efc8a04591b24a460dea15b9e712fa37ba23b49` |

## R38 coherent source-built extension import matrix

The same one-line CPython source variant produced manifest-free x64 builds of
all nine `.pyd` modules in the diagnostic Python package. Pinned CPython
external sources supplied bzip2, mpdecimal, OpenSSL, xz and zstd; zlib-ng was
already pinned for the core. A fresh 60-file PyInstaller package included the
immutable R34 core, all nine rebuilt extensions and the two dependency-named
OpenSSL DLLs alongside the original package files. Exact inventory rehash
passed. These local source-built binaries are unsigned diagnostics; the added
OpenSSL DLLs have valid PSF Authenticode signatures. No production signing or
installation was performed.

| CPython-pinned ignored external source | Verified Git commit |
|---|---|
| `bzip2-1.0.8` | `05301997b2f9590f49c672cf3dfd3d3dfa7ad521` |
| `mpdecimal-4.0.0` | `48316ec025c1ebe500854c332be0a12c640c7301` |
| `openssl-bin-3.5.7` | `3217be5a2a7e20dbc5f5b5160ef21a9c84de7138` |
| `xz-5.2.5` | `c6bc0c612605622aaef101a33a751f9de2ecc193` |
| `zstd-1.5.7` | `eef946ae8cf1591c0e5cc5f43486210768647c2e` |

An ordinary-user control imported all nine extensions. In a fresh LPAC run,
seven imported: `_bz2`, `_decimal`, `_hashlib`, `_lzma`, `_zstd`, `select` and
`unicodedata`. `_socket` failed at Winsock startup 10107, and `_ssl` failed
transitively because it could not import `_socket`. Neither was a PE load-denied
result. The worker made no socket, listener or network connection. Its framed
token proved zero-capability LPAC/AAP denial; unrelated read, outside write,
profile/temp writes and synthetic parent secret were denied. All 12 profile
and 66 runtime DACLs were restored, post-restore integrity passed, and the
disposable profile/runtime/sentinels were absent. This strengthens the
manifest-free packaging candidate, but leaves connector execution, network
egress, production signing and task qualification open.

ADR-0028 specifies a signed runtime, while the current disposable probe builder
and trusted Core sidecar build record exact hashes without a worker signing
stage. The local Windows SDK has SignTool, but no release signing identity or
credential hookup is selected in the repository. The R38 package contains
unsigned source-built PE files and is not release-qualified. Detached Ed25519
plugin-manifest signatures address publisher trust and do not supply Windows
runtime code signing. This is a separate packaging/release gap, not a reason
to weaken the LPAC or no-write boundary.

| R38 ignored input/output | SHA-256 |
|---|---|
| Source worker / EXE / base library | `0457635b9f3f0cd43d0dc3314396efb5724dfdfab6557c1b3a854f354c4806d2` / `d91fc6f9528537233358f20a9664501da4a15e86ff5cdc3f2eac6bc0f63bab48` / `853017d7f3423c633ba20849010fb799684acb93cbc8aabf70f812a9470ac950` |
| Exact 60-file package inventory / runner | `d3f2eafa39de3d9919db7ea0f6937280987884dd1d227202bb2d44367072ae18` / `7c63f124a13e830473a5db3b282d0ff284e13c9ee92a6db7007a689c31809465` |
| LPAC run log | `a3c9fcbd29b6f010baac89fdc95fe959e5048f0fec306c0dbfa91c9dd0b2fb64` |

## R39 local-only multi-API network diagnostic

A new native fixture tried raw Winsock, WinHTTP with explicit no-proxy mode,
and WinINet in direct/no-cache/no-cookie mode against only a disposable
`127.0.0.1` listener. The ordinary-user controls each reached that listener.
Under a verified zero-capability LPAC token, Winsock failed at `WSAStartup`
10107 before `connect`; WinHTTP failed at `WinHttpOpen` 12004; WinINet failed
at `InternetOpenW` 1008. The listener accepted zero LPAC connections. Thus
three local API paths failed closed before transport in this fixture, but no
LPAC `connect` or public-address send was attempted. The numeric errors do
not, by themselves, identify the exact denied resource. No external address,
proxy discovery or host network-setting change was used. All 12 profile and
six runtime DACLs were restored; profile/runtime integrity and cleanup passed.

| R39 ignored input/output | SHA-256 |
|---|---|
| Native source / EXE / inventory | `da8abe3da7668cacc9172e31f37f0c3be0fd4b47165048dbc851b5a0e58e3a87` / `6fcb073c95af3d6fedbc307cbb59f527ee1a7cc4d882badda167ea5d148a292b` / `059567e752d961a727d661f955399d6cdf4ce8851b2be07ebe7a9c58ff8274a2` |
| Runner / LPAC run log | `1b038d2e7899b563135c4304d9913035f8450fa27a6c9ae9240a971174812939` / `782bbb5bbdd23b4e360e1da3e3966d7212694230599b50e418549ae989e1f386` |

## R40 no-transport network-isolation policy query

A fresh native LPAC fixture called Microsoft's
[`NetworkIsolationDiagnoseConnectFailure`](https://learn.microsoft.com/en-us/windows/win32/api/networkisolation/nf-networkisolation-networkisolationdiagnoseconnectfailure)
and detailed variant for numeric TEST-NET-2/public and RFC1918/private
addresses. It made no DNS, socket or connection call. The ordinary-user
control and verified zero-capability LPAC both returned raw `0` from the basic
query, while the LPAC detailed query returned raw status 14 and error type 0.
Microsoft documents the basic return as `FALSE` when the calling AppContainer
lacks the required target capabilities and `TRUE` when it has them; the earlier
description of raw `0` as "success" was incorrect. The ordinary-user control
does not validate AppContainer capability-query semantics, and the detailed
form concerns a connection already attempted. Without a capability-bearing
LPAC positive control or actual transport attempt, R40 provides no decisive
public-egress denial witness. The result is **inconclusive**, preserved rather
than promoted to a pass. All 12
profile and six runtime DACLs were restored; integrity and disposable cleanup
passed.

| R40 ignored input/output | SHA-256 |
|---|---|
| Native source / EXE / inventory | `fe0e9130a6f7782c0b85df3f8e84474e62695bffc46317de4bb500eb0cb6e56b` / `9a18eef2bc5a6b7ac8392d0924605e0b4c1465716f44aa28d84f6313dfe5d69c` / `4c4c64f2b0ed2c80e3bf2983f022055c738122ba5389164db6c3df7727829a07` |
| Runner / LPAC run log | `e9d191c991547ea6f72ee17f3d9bea1ecc9b492bccc84280fbf4f49499174fa7` / `3a48e077ace13f1f49dff7442e9f70d5f4209e1c8cd33a5ab827c61eb714c455` |

## R41 offline test-signing and exact signed-byte LPAC probe

A bounded offline signing experiment copied the R38 60-file package, generated
a disposable self-signed code-signing test identity without installing it in a
Windows certificate store, and used local SignTool with no timestamp service
to sign exactly the worker EXE, source-built Python DLL and nine `.pyd` files.
The post-sign 60-file inventory matched every staged file; only the eleven
intended PE hashes changed. The Python runtime binaries remained x64 and
manifest-free with the same imports/exports. Authenticode showed the matching
test signer but an untrusted root, as expected; a one-byte tamper caused a
distinct signature hash mismatch. The private PFX was overwritten and removed
from the ignored fixture, and no matching certificate was found in the checked
CurrentUser/LocalMachine My, Root or TrustedPeople stores. Persistence of any
orphaned provider key container was not independently checked. The test signer
is **not** a production trust identity.

One fresh LPAC probe used those exact signed bytes. Its ordinary-user control
imported all nine extensions; LPAC imported the same seven as R38, while
`_socket` failed at Winsock startup 10107 and `_ssl` failed transitively.
Framed protocol, token and the focused no-write/read/secret probes passed;
all 12 profile and 66 runtime DACLs were restored, post-restore integrity
passed, and disposable roots/sentinels were absent. The signed-byte result
shows the offline signature did not change this diagnostic LPAC behavior.
It does not qualify a production signer, connector execution or public egress.

| R41 ignored input/output | SHA-256 |
|---|---|
| Signing staging script / SignTool driver | `a3cfe17b85c4c803161f89b1eaeddcd2c253904f04fff6adb2632e3c27835326` / `c9af1e4af33b4429fd3ffbcefb390b1c05d87ccfb5d77e3748152d15ba33c331` |
| Signed package inventory / sanitized signing results | `78c269289cf5117acaf253b5cbc56011e977430db88ed6727fd5ea4a0336a357` / `7d372fda3bbc2c136e8f9d3840b54190d27876970bb1c3dbe8ea515bfee9cb8f` |
| Tamper-control result / projected LPAC inventory | `5f473220ff8f1781473f909d6ae947f86d5df8eef13e72f0ced260308fffe987` / `7fdafdf69131ee075c7bddf158cd46e02cebe17f7ccc5ac88c54a769a25ad008` |
| LPAC wrapper / run log | `93b30cfefbe0fd3a81b844b6cc0051f22e3e54657c2bf43a2272505c7beff1a4` / `1a8a231428e6964403630fb7eeba896bbbcf62f8fba7e7280825c618dddae220` |

## R42 synthetic signed connector execution vertical

An ignored, test-owned vertical used the T01 Ed25519 exact-package admission
code, disposable local publisher trust and an explicitly enabled synthetic
project grant. Current authorization produced an exact plan before launch.
Its fresh 61-file source-built package included a fixed, signed-manifest
`plugin/connector.py` asset. The ordinary-user control could reach the local
listener and synthetic sentinel targets. In verified zero-capability LPAC,
the connector's **own code executed** and returned a framed synthetic result.
It reported unrelated/other-project/vault reads, outside/export/profile/temp/
runtime writes and inherited synthetic environment secret denied. Socket
initialization failed at 10107 before `connect`; the local listener received
no LPAC connection. Direct transport/public egress remain unproven.
This connector attempted creation of new files, not append, overwrite,
alternate-stream creation, deletion, rename or DACL changes on seeded files;
R29e's separate native fixture exercised those operations. The combined
observations do not make R42 alone a complete packaged-Python no-write matrix.

A forbidden `export` broker-call shape was rejected by the current schema and
one content-free `operation-denied` event was read from the actual synthetic
grant repository. That audit was arranged by the diagnostic harness, not by a
product worker-broker IPC integration. All 12 profile and 68 runtime DACLs
were restored; snapshots, profile deletion and disposable cleanup passed.
The Ed25519 test seed was a fixed public fixture value in the ignored runner;
no private-key file was written, and disposable trust/grant/audit state and
sentinels were removed. No real project, vault or credential was used. This closes the earlier
"no connector code ran" limitation for a test-owned vertical, while product
dispatcher, broker IPC, durable execution, production signing and public
egress remain open.

| R42 ignored input/output | SHA-256 |
|---|---|
| Runner / worker source / hostile connector template | `d8c847055e4d402e738754d9e432577add8d07dd48b2edc3b87f70d3b673177d` / `cd557972c52ccd69b29539653569fba4f52ffab4a9becfe3da6c8d793b084291` / `887b0215eef158a42ccbed9485a8ecde8f92ac516f08ed8a9d9a01dada558a8c` |
| Exact manifest / Ed25519 signature | `c59645914dfd34dbe7c0a3823309d066fc7fb66eddcbe15d82248396d94a5e81` / `3e5586389e32f7f7b5066e158d8c59eb2bda448d2132b6de8014188e0255d8db` |
| Plugin asset / worker EXE / 61-file inventory | `3b263989dabeebb738ee6ecfaf2c1b742fc7fb408b2e9be40e3dab339d6b32c8` / `917dc9b54ae2ca3e9683f515326ca68608aff23eb78155e0c8ed82b358239b0c` / `a4357ec7defe8d6a192f3d600be9dd8882dd4c6c64a1dbc0c1da3f3564b31d8f` |
| LPAC run log | `2641e6236b69fbc241ac592c7510c9be0b490e1c0b510ea496a8fbccce6fa6b3` |

## R43 checked-in probe-stage correction and retained no-write failure

At commit `6b2b47a2`, the checked-in disposable native probe reports Winsock
startup, whether `connect` was attempted, its result and error separately.
The trusted launcher rejects malformed or allowed network reports, and the
focused test now makes an ordinary-user positive connection to its local
listener and checks the listener after the LPAC run. This repairs the R29e
false-positive label; it does not claim a public-egress test or connector host.
Focused `cargo fmt --check`, offline Cargo check, Ruff and two Python unit
cases passed on the committed change. A fresh real LPAC focused test on that
commit still failed: `lpac-ambient-authority-not-denied:profileWrite,tempWrite`.
The checked-in probe launcher's existing directory-only ACLs therefore continue
to permit disposable profile/temp writes; its listener assertion was not
reached after that failure. The test was **not** weakened or marked passing.
The test-owned AppContainer profile count with the probe prefix was zero
afterward. R29e's separate recursive no-write ACL diagnostic remains the
candidate to integrate after the task's full feasibility gate.
An independent read-only reviewer approved the bounded false-positive
correction at exact commit `6b2b47a26ab1018835519d1b850f157a1a91baff`
with no blocking finding. The reviewer confirmed malformed/allowed reports
fail closed and noted that `connectErrorCode` also carries a socket-creation
error when `connectAttempted` is false. That naming note does not change the
explicit stage semantics. The review is **not** a T02 disposition.

| R43 ignored output | SHA-256 |
|---|---|
| Focused real LPAC test failure log | `43809e575d834a460cf75e659dd2469bc1a815940074b3772fc33bdd934f258` |

## R42b connector-originated existing-file no-write matrix

One fresh ignored diagnostic reused the R42 source-built worker package and
loaded a new exact Ed25519-admitted synthetic Python connector asset. Ordinary
user positive controls succeeded for 25 seeded-file operations: append,
overwrite, alternate-stream creation, delete and rename in each of disposable
LPAC profile, Temp and runtime, and synthetic project and vault locations. In
verified zero-capability LPAC, the connector's own code attempted and reported
denial for all 25. Project/vault contents and owner/DACL snapshots matched after
the run; R29e-style post-restore profile/runtime integrity passed. All 12
profile and 68 runtime DACLs restored; the disposable profile, runtime,
synthetic project/vault/trust and sentinel roots were absent after cleanup.
This extends R42's new-file checks; it does not test connector-originated
owner/DACL changes because this source-built Python package lacks `_ctypes`.
The profile/Temp/runtime post-restore snapshots did not enumerate alternate
data streams, so these three roots do **not** have independent post-run proof
that an empty stream was absent after an open-then-failed-write sequence.
Project/vault stream absence was checked; R29e tested stream absence and
owner/DACL operations in a separate native fixture. The connector's
`_socket` import again failed at `WSAStartup` 10107 before `connect`; public
egress and direct transport denial remain unproven. The `operation-denied` and
`ambient-write-denied` audit codes were arranged by the test harness, not a
product dispatcher/broker. Release signing and product IPC remain open. An
independent read-only audit matched the runner, connector, manifest, signature,
inventory and log hashes, verified that the packaged connector invokes all 25
operations and that fresh seeds, ordinary positive controls, LPAC token checks,
post-restore integrity and cleanup are wired. It flagged the missing
profile/Temp/runtime stream inventory above and agreed the formal task resume
condition remains unmet.

| R42b ignored input/output | SHA-256 |
|---|---|
| Connector template / runner | `198e9ed03b4d31eb4d95d3c29c7b143b923c49877c117738dce0ccda12d52565` / `c9ad066f68ccc08c38ab62f28fcf7310d3d2858fd54a382b34dba5ec26a4f0bc` |
| Exact manifest / signature / 61-file inventory | `dfd30f24d8020a086cf07f63e6aee0c0f200f8e8f0ba86414bb556fbb2cb7972` / `bbbd20b566eadc93228af55dd3fe35eb8b2307fe61427eb8ddd487cca8b18601` / `e7c05c4b75df3f8ab92153c023b050a15f51315f94d26a628566b706dd95c958` |
| Real-user LPAC run log | `da0b2ce74a6731f1960f66e7ad09492ea215f43403bd3a7e01ba6a9b7fc305e3` |

## R44 matched no-transport policy-query control

The R40 network-isolation fixture was repeated under two separately created,
verified LPAC tokens: the exact zero-capability token and a positive-control
token carrying only `internetClient` (`S-1-15-3-1`). Both opted out of All
Application Packages. Neither run used DNS, a socket, `connect` or network
transport. Both returned `0` for the numeric TEST-NET-2/public and
RFC1918/private basic queries, and detailed status 14/error type 0. The
internet-capable positive control therefore did **not** discriminate the API
on this host and unpackaged fixture. R40's raw `0` cannot be promoted to a
public-route denial verdict. This is adverse diagnostic evidence, not a reason
to weaken the direct-egress criterion. Each case restored 12 profile and six
runtime DACLs, passed snapshot integrity, deleted its disposable profile and
runtime root, and left the outside-write sentinel absent. An initial default-
sandbox attempt failed before any policy query with profile-creation
`0x80070002`; the final normal-user run exited zero. No broader capability was
used for a product worker. An independent read-only audit matched the runner,
log, native source, EXE and inventory hashes, verified the enabled
`internetClient` token SID and LPAC opt-out before worker resume, and confirmed
both controls' identical raw results and cleanup. It likewise found no
transport verdict or task-resume proof.

| R44 ignored input/output | SHA-256 |
|---|---|
| Positive-control runner / final log | `fc5148641a3f1879590c6f9d92004b32bf83758712712c3c34308f33bf20b3ee` / `582544abd8200100583625b9e4f5f1a243390ba893132be8d91200407d740f60` |
| Reused R40 native source / EXE / inventory | `fe0e9130a6f7782c0b85df3f8e84474e62695bffc46317de4bb500eb0cb6e56b` / `9a18eef2bc5a6b7ac8392d0924605e0b4c1465716f44aa28d84f6313dfe5d69c` / `4c4c64f2b0ed2c80e3bf2983f022055c738122ba5389164db6c3df7727829a07` |

## R45 matched Winsock initialization control

A new fixed native fixture called only `WSAStartup(2.2)` and `WSACleanup` on
success; it made no socket, DNS, connection or public transport call. The
ordinary-user control initialized and cleaned up successfully. Verified
zero-capability LPAC returned 10107, as did a separate verified LPAC with
exactly one enabled `internetClient` SID (`S-1-15-3-1`). Both LPACs opted out
of All Application Packages. Thus an `internetClient` token addition alone
does **not** resolve this fixture's Winsock initialization failure; the zero-
capability failure cannot be attributed uniquely to absent network capability.
This is a test-only capable-token control, not a product permission change or
public-egress witness. Both final arms restored eight profile and four runtime
DACLs with exact owner/DACL SDDL match, kept content snapshots intact, deleted
the disposable profiles, and removed runtime roots.

Preliminary attempts are retained: an extra Rust PDB failed exact inventory
preflight before profile creation; two later runs reached zero-capability
`WSAStartup` 10107 but a strict descriptor comparison found that DACL-only
restore left the disposable inheritance-protection state changed. Those runs
deleted their disposable profiles and runtimes, did not reach the capable-token
arm, and are not counted as qualified controls. The final runner restored and
verified that descriptor state for both arms. Diagnostic basenames use `r43`
internally; this packet calls the comparison R45 to distinguish it from the
tracked R43 probe correction. No tracked task/product authority was changed.

| R45 ignored input/output | SHA-256 |
|---|---|
| Native source / EXE / inventory / final runner | `73757d58c5ffe89acab40661a2107a09750621b1fe9613c3ba45e8ae60ccd8b5` / `797757d0e2e9dc34cacbaa9c93ba421ed629be227a199ca8e429afa0ae6f26e8` / `153653b28f049a0db357863d073c50eb911a962e425f379a0f52813baa78d006` / `befdad50445818c7dcbba1be9cddabafda73d90cd34c18f53bba7f90a615b77e` |
| Preflight / two adverse preliminary logs | `7c9f34b671343d42f748551c73e3d6bf79f757d58cf4e4fbe43992d578d4358f` / `15a050b73b05468325e219863c026da29a931ba56f79aea99011ff49f05acf48` / `b6c1215da0fb6e344abbbd61ec2ce1fb943fb086afb1d478d3fe8960c27e4f7a` |
| Final matched run log | `85e7eea3254f2001234cfaa5d827d2756375f44c9290ee5915874b8b96c4ba72` |

## R42c/R42c2 alternate-stream integrity follow-up

R42c attempted to close the R42b alternate-data-stream observation gap, but
its host-side `FindFirstStreamW` scan ran after restrictive ACL installation
and returned error 5 **before** the LPAC worker launched. The harness restored
12 profile and 68 runtime DACLs, checked content, deleted the disposable
profile/runtime and then found zero named streams in its post-restore scan.
That failed prelaunch attempt is retained, not counted as connector evidence.

R42c2 moved the baseline stream scan before the restrictive ACLs and enumerated
streams on every seeded file/directory after worker exit and DACL restoration,
before cleanup. An ordinary connector positive control created and enumerated
named streams in all five target domains. The LPAC baseline was ADS-free, the
exact admitted synthetic Python connector again reported denial for its 25
seeded-file attempts, and the post-run enumeration found **zero named streams**
in profile, Temp, runtime, synthetic project and vault. This closes the
specific R42b empty-stream loophole for those test-owned targets. The
zero-capability LPAC token, 12/68 DACL restorations, profile/runtime content,
project/vault content and owner/DACL snapshots, disposable deletion and
synthetic trust/sentinel cleanup passed. Connector-originated owner/DACL
mutation, direct public/loopback transport, product dispatcher/broker audit
and release signing remain unqualified. `_socket` still failed at
`WSAStartup` 10107 before `connect`.

| R42c/R42c2 ignored input/output | SHA-256 |
|---|---|
| R42c adverse prelaunch log / raw launch-error line | `8607fa8a8dd4ccfcf45d3ffbda4024cbd068f7126d9b5018ff58468bf3c8830b` / `21d2d1a7378d57284642f00d3e9f0f95aafd0c0dba13c4de0beaf4bb2fc946c5` |
| R42c2 connector template / runner | `2b48dfd07ad8b665e37ecde80f4828a32e402d4a46dfcd64729c8366ac051d1c` / `d3fb3e0ddfb22127ed7c1b286d66928a11357241da19b0fc9217e3f5232c3c7f` |
| Exact manifest / signature / 61-file inventory | `186c46e0b83afc8f8f940efcc2e6bf99e8e3c29e6af1a270e97e1985d61e4f1e` / `08655f65588b07560fe62eaed85bdcedd39eee30937dcc19285092723625adec` / `ba9da67526dc366593871faacb4e4d70e98d567206e71a29e7423a445945347f` |
| Final real-user LPAC run log | `3b32e0ec456ec8aaee35a8bd7018bb8f2e57edebdaf6a3a110d8864caf1e502c` |

An independent read-only audit matched the R42c2 inputs and all 61 package
files, verified the positive-control stream enumerator sees even an empty
named stream, and traced the post-restore/pre-deletion five-root scan. It
agreed the ADS observation gap is closed for this test-owned run while the
task's broader security and product obligations remain unmet.

## R46 test-only registryRead Winsock discriminator

Microsoft's [LPAC launch guidance](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)
states that an LPAC cannot open registry keys without `registryRead`. A new
matched diagnostic reused the exact R45 one-file native EXE, which calls only
`WSAStartup(2.2)` and `WSACleanup` after success. Ordinary-user control returned
0. Verified zero-capability LPAC returned 10107. A separate verified LPAC
with only `registryRead` returned 0 and cleaned up successfully; a third with
`registryRead` plus `internetClient` also returned 0. Every LPAC retained the
All Application Packages opt-out. This strongly localizes the Winsock startup
failure to access enabled by `registryRead` in this fixture; it does not name
the exact registry object or prove transport behavior. The diagnostic made no
socket, DNS, `connect` or public-network call. All three test-owned LPACs
restored eight profile and four runtime DACLs with exact owner/DACL SDDL and
content matches, deleted profiles and runtime roots, and left the product
zero-capability token unchanged. **Adding `registryRead` to the product worker
would change ADR-0028 security authority and is not approved.** An independent
read-only audit matched the EXE/inventory and log hashes, checked exact token
capability sets and cleanup, and agreed that this is a strong association on
this host, not identification of the exact registry object or public-route
qualification.

| R46 ignored input/output | SHA-256 |
|---|---|
| Runner / exact one-file inventory / reused native EXE | `1f4faa330a290ac3a8a88069c3c4898ba5e22b03bf07e2d3c89a13836a91a993` / `153653b28f049a0db357863d073c50eb911a962e425f379a0f52813baa78d006` / `797757d0e2e9dc34cacbaa9c93ba421ed629be227a199ca8e429afa0ae6f26e8` |
| Final no-transport run log | `af6387e6ec8a3041aa5af3737c4a053620e0f6cba68dcee03170f7a1063116f4` |

## R47 registryRead network-isolation query control

The exact R40 no-transport native policy-query EXE ran under ordinary user,
zero-capability LPAC, test-only `registryRead` LPAC, and test-only
`registryRead` plus `internetClient` LPAC. Tokens and All Application Packages
opt-out were checked before resume. For numeric TEST-NET-2/public and
RFC1918/private targets, the basic API returned raw `0` in **every** arm.
The detailed API returned status 14 for both targets in zero-cap LPAC,
1753 (`EPT_S_NOT_REGISTERED`) for both in `registryRead`-only LPAC, and
0 for both in the combined-capability LPAC; error type was 0 throughout.
No arm attempted DNS, a socket, connection or transport, although the
detailed API contract concerns a server to which connection was attempted.
These non-target-specific values do not establish a public-route denial or
make R40/R44 qualifying evidence. Each LPAC restored eight profile and four
runtime DACLs with owner/DACL SDDL and content matches, deleted its profile
and runtime root, and left product authority unchanged. An independent
read-only audit matched the exact image/inventory and logs, verified token
sets and cleanup, and agreed no public-egress criterion was met.

| R47 ignored input/output | SHA-256 |
|---|---|
| Runner / reused one-file inventory / native EXE | `006e6e850d732e317f8b3b66e730e9ca7d2e57c313f18e3c251de7ec7f6b1eea` / `4c4c64f2b0ed2c80e3bf2983f022055c738122ba5389164db6c3df7727829a07` / `9a18eef2bc5a6b7ac8392d0924605e0b4c1465716f44aa28d84f6313dfe5d69c` |
| Final no-transport run log | `ab3e77a1d59bb7b826dd89f22bbe979d9ea82e437fc96b391f25e9c3b558c7c6` |

## R48 local-only Winsock socket-creation discriminator

A fixed native image attempted only `127.0.0.1` against a disposable listener.
The ordinary-user control initialized Winsock, created a socket, connected,
and produced exactly one accepted listener connection. Verified zero-capability
LPAC stopped at `WSAStartup` 10107 with no socket or `connect`. A separate
**test-only** LPAC carrying `registryRead` alone initialized Winsock but socket
creation returned 10013 (`WSAEACCES`) before `connect`; its listener had zero
receipts. Token capability sets and All Application Packages opt-out were
checked before resume. This is real-principal socket-creation denial under a
more permissive diagnostic token, plus fail-closed startup under the exact
product zero-capability token. It is **not** a destination-specific loopback
`connect` denial or a public-route observation. There was no DNS, public
address or external traffic and no product-token change. Both LPAC cases
restored eight profile and four runtime DACLs with exact owner/DACL SDDL and
content matches, deleted profiles and runtime roots.

| R48 ignored input/output | SHA-256 |
|---|---|
| Runner / one-file inventory / native EXE | `cb314741ac4d89b19170cc5f00cdb9b71d67177abe9b78760b3b2a4548516145` / `e41efae908c2545552c126a69dbff14e9780b87ff9f52cc3a5fe75908861fc3d` / `21b5be1e0df5b14c6cc4c428b5dbd9fa784a9eb3237f857895a385420f266b1d` |
| Final local-only run log | `7cc19a798fdc0474301885443b95eeecc511fea8d472d393aad7a9661baee76c` |

## R49 no-transport socket-capability positive control

The same one-file test-owned native EXE called only `WSAStartup`,
`socket(AF_INET, SOCK_STREAM, IPPROTO_TCP)`, `closesocket` on success and
`WSACleanup`. It never called `connect`, listen, send, receive or DNS. The
ordinary control created and closed a socket. Verified zero-capability LPAC
again stopped at `WSAStartup` 10107 before socket creation. A separate
test-only `registryRead` LPAC initialized Winsock but `socket` returned 10013
(`WSAEACCES`). Adding `internetClient` **only to that diagnostic token** made
socket creation and close succeed. This is a matched real-principal positive
control showing network capability affected socket creation after the
registry-dependent startup prerequisite on this host. It strengthens the
fail-closed direct-network feasibility case for the exact zero-capability
worker; it does not claim a destination-specific `connect` or public packet.
All token SID/count and LPAC opt-out checks passed. Each of the three
disposable LPAC arms restored eight profile and four runtime DACLs, matched
exact owner/DACL SDDL and content snapshots, and removed profiles/runtimes.
No product capability or host network setting changed. An independent
read-only security audit matched the exact source/EXE/inventory/log hashes,
token sets and cleanup, and agreed this supports **reopening T02 for
implementation only** under ADR-0028's fail-closed direct-network boundary.
It did not treat this as a public-route verdict, task acceptance or release
qualification.

| R49 ignored input/output | SHA-256 |
|---|---|
| Native source / EXE / inventory / runner | `59cc49efde9aa7debb83b4b2d2e441005c1952e32839a01b4061a270c58e410e` / `a2097794aa92959210d509ae50967c6762601526bfa187f6ad66c9c8a4f607fb` / `7acfa09eb43180dfb3fd786ffd28accc6d6191a36e66af22ead31423762fdc8c` / `dad915810706d496133eaf72d3b6060b01cc9674b58c90d22da665c82ec1ec64` |
| Final no-transport run log | `3fa6a00aa346532060c819f6d5a4d325c31ba0a2f986c173c184a6ef3ec8e40e` |

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
test-owned native LPAC no-write/read/secret matrix; R37 clarifies that its
loopback result stopped before `connect`. The original Python
connector image fails before user code; R30 narrows that loader stage. R31
made a manifest-free source build a credible test candidate; R34 proved its
core DLL loads and reaches Python imports, while R35 proved a matching
`_socket.pyd` loads before Winsock initialization fails. R36 proved narrow
packaged-Python read/write/secret denials; R38 imported seven rebuilt
extensions, with `_socket`/`_ssl` still failing during initialization. R32 and R33 preserve
the adverse dependency-only and strict-search results. R42 and R42b executed
an exact admitted synthetic Python connector inside verified LPAC: the sampled
ambient read/new-file checks and 25 connector-originated existing-file
attempts reported denial. R42c2 additionally found no named streams across
the five seeded domains after the LPAC run, closing R42b's post-run ADS
observation gap for those targets. The separate R29e native fixture exercised
owner/DACL changes and stream absence.
No run identifies the exact original manifest resource denial or proves a
direct `connect`/public egress denial. R39 adds three local API startup denials,
R40's policy query is inconclusive; R44's matched `internetClient` LPAC
positive control also returned raw `0` and did not resolve it. R41 confirms
the same import behavior on test-signed bytes without satisfying release
signing. R45 shows `internetClient` alone does not repair LPAC
`WSAStartup`; R46 shows test-only `registryRead` alone does, strongly
localizing the startup prerequisite without authorizing it for the product or
proving public transport denial. R47's registry-capability policy-query
controls still gave no target-specific public-route verdict. R48 observed
socket-creation denial 10013 in test-only `registryRead` LPAC after successful
Winsock initialization, while the zero-capability LPAC stopped earlier; it
did not observe a public address or destination-specific `connect`. R49
confirmed the same test-only `registryRead` socket failure becomes a successful
socket creation only when `internetClient` is added in a positive-control
token, without network traffic. R43 corrected the
checked-in probe's network-stage reporting but retained its real profile/temp
write failure. The product worker has not reached brokered calls or durable
dispatch, and the test-harness audits do not qualify product audit integration.
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

### R49 feasibility disposition for task continuation

R42c2 established connector-originated denial and post-run integrity for the
seeded no-write matrix under the source-built zero-capability LPAC worker.
R46/R49 separated the registry-dependent Winsock initialization prerequisite
from the network capability: the zero-capability worker fails closed before
socket creation; a test-only `registryRead` LPAC reaches `socket` but gets
10013; adding `internetClient` **only in the positive control** permits socket
creation. R39 also observed local-only WinHTTP/WinINet startup denials. An
independent security reviewer read ADR-0028's direct-network-denial criterion
as permitting these real OS pre-transport denials for **early feasibility and
taskctl reopening**, without requiring a public packet or destination-specific
`connect` at this stage. That disposition does not amend ADR-0028, grant
`registryRead`/`internetClient` to product code, or qualify the final task.

On reopening, implement and verify the **exact product** signed worker and
private broker path with zero network/registry capabilities and the R29e/R42c2
no-write controls. Preserve the remaining public-route observation limit in
the task security review; do not convert it into a claim of a tested public
`connect`. If final independent review concludes the approved direct-internet
criterion needs a destination-specific observation rather than a proven
pre-transport denial, stop submission and use the decision/amendment route
before changing any verification obligation. Product broker/audit, resource
limits, cancellation and restart/recovery remain entirely open.
