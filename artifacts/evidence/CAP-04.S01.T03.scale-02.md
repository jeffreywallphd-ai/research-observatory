# CAP-04.S01.T03 — protected 100k functional diagnostic

Candidate `ddc3b980ef65c0c1ef26766fbc02f2a8462f596c`.
The earlier interrupted/lease-expired run in `scale-01.md` remains adverse evidence.

Fresh opt-in `ImportCommitScaleWindowsTests` **PASS**: one test in 1115.577
seconds. Diagnostic elapsed time: 1115.246519 seconds. The production 30-second
renewable lease and all product deadlines remained unchanged. First attempt
succeeded; no automatic retry was observed.

| Durable outcome | Observed |
|---|---:|
| Canonical source records | 100000 |
| Import manifests / seals / accepted commit outputs | 1 / 1 / 1 |
| Immutable manifest members, including the header context row | 100001 |
| Complete manifest traversal | 1001 pages / 100001 rows |
| Identical request replay and fresh runtime reopen | Passed |

Source fixture: repeated synthetic CSV v1, 4600010 bytes / 36 encrypted chunks,
SHA-256 `c98a9e5dbe1a92373bc4137ea6aa3c6ae758e2f1d30f2ca53837502cb2f115a3`.
Retained ignored fixture: `artifacts/tmp/import-commit-scale-windows-q0c40rd6`;
raw output: `artifacts/tmp/import-commit-scale-100k-02.log`.
Final `diagnostic.json` SHA-256:
`22e00d9802a5cd65b8a048d2849e71f301cf32543216ffa82d069f1fb8f36e47`.

## Measurements and limits

- Project/intake 5.472s; parse 81.789s; commit worker 896.235s; cold manifest and
  complete paging 76.700s; identical request replay 0.460s; runtime reopen 54.357s.
- Within the commit worker: staged-page writes 64.398s, identity validation
  267.773s and atomic publication 330.953s. These are phase observations, not a
  complete additive decomposition of worker time.
- Whole-process working set: baseline 109592576 bytes; maximum observed
  146001920 bytes; Windows peak counter 154116096 bytes. Private usage baseline
  92413952 bytes, maximum observed 128917504 bytes. Includes Core and the test
  runner; no tracemalloc.
- Windows 11 build 26200, AMD64, Intel64 family 6/model 183/stepping 1,
  20 logical processors, Python 3.14.6. These are observed machine facts, not
  minimum-hardware qualification.
- Actual execution-principal DPAPI, SQLCipher, isolated local vault, production
  Core composition and automatic durable worker. ASGI transport, native context,
  capability, source and project/vault locations are explicit fixtures. No
  ordinary user projects, credentials or sign-in policy were accessed.
- HEAD and the diagnostic's exact Core/contracts/config/helper/test inputs
  stayed fixed. No concurrent test/build workload. New desktop regression,
  separate process fixture and evidence notes were prepared outside those
  inputs during the latter part of the run; no whole-application clean-snapshot
  claim is made.
- This is functional evidence with **diagnostic-only performance**, not a
  reviewed baseline, ordinary-read responsiveness, native, packaged or Wave
  qualification. The worker finished close to its 900-second observation cap;
  do not represent this timing as a comfortable performance margin. Ordinary
  status reads can still wait behind publication's lifecycle mutex.

The preceding protected 1000-record pilot at the same candidate passed in
16.470s, with one manifest, complete membership, no retry, successful replay and
reopen. Its retained fixture is `artifacts/tmp/import-commit-scale-windows-c13tt9oc`.
Neither pilot nor this diagnostic completes CAP-04.S01.T03 on its own.
