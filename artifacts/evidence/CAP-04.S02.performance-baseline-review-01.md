# CAP-04.S02 independent performance-baseline review 01

Reviewer: `agent:/root/w2_t03_review`, independent of the campaign owner.
Date: 2026-09-27.
Disposition: **approved as the immutable measured baseline for subsequent fresh
qualification**. No performance pass, slice completion, Wave exit or release
approval is supplied by this disposition.

Reviewed publication candidate:
`c81c63f2760a97368f00bb993a9559b18681b5c7`.
Predecessor and calibration candidate:
`c8a3c3ba7deea9accf24587e4f4674a92ecc68bb`.
Authority remains approved CAP-04.S02 sections 10–11 and 15–17 under W2 approval
`c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`, with the benchmark requirements in
`docs/automation/project-automation-guide.md` section 8.3. The existing bounded
producer review is `CAP-04.S02.qualification-controls-review-01.md`.

## Exact scope and execution identity

The three-file publication adds the baseline and owner evidence note and changes
only `BASELINE_SHA256` in `tools/source_performance_check.py`. The reviewer
compared all three current files with their exact candidate Git blobs. No
product, method, fixture, assertion, allowance, absolute ceiling, permission,
reference, migration or prior evidence is changed. Shared HEAD remained fixed
through this review. The reviewer reran no producer or test suite and wrote only
this independent note; no source, backlog or Git ref was changed.

| Artifact | SHA-256 |
|---|---|
| `tests/fixtures/scholarly-metadata/source-performance-baseline.json` | `d21fc40e3fedb71ecf0e0b274055d047b2fec4bb4278a1642894534d3c323822` |
| Calibration tool bytes at the predecessor | `f18935bbe14ab615ab887c6813cf9d7d39df3bccbfddddf16896d4e949afcd74` |
| Published tool bytes at the reviewed candidate | `08139bc4f503b42c5fbae9ed2f550a24a7da3738ad8d172a4a353c014f955346` |
| `artifacts/evidence/CAP-04.S02.performance-baseline-01.md` | `0a26338d9644d301e565ebf9e3e19dbcb39ac7dbd396a49e0341ec82da138044` |
| `artifacts/tmp/CAP-04.S02.performance-calibration-01.json` | `e07561457bb29d02e264ed5f327d51064f51b54b045420d529d0328608224097` |
| `artifacts/tmp/CAP-04.S02.performance-calibration-01.execution.json` | `f92ee376c80f27a5ce5e7384b5a9fc6ca3a4fb1df311137adbc8a9a06641e789` |
| `artifacts/tmp/CAP-04.S02.performance-calibration-01.log` | `86d3e5f9778e60019b4343182464f14f228a13236ba1928ec8a5bfd3b25d3cb5` |

The retained execution record identifies `--calibrate`, exit 0 and identical
starting/ending calibration HEAD. The aggregate is `MEASURED`, with
`performanceQualifying: false` and reuse disabled. Its measured producer interval
is 247.4937678000424 seconds; the wrapper interval is 259.98795830004383 seconds.
These are different boundaries, not two competing measurements or a performance
pass. The producer runs three fresh children under fixed source/dependency locks,
fresh parent/child bytecode prefixes and final identity checks before publication.

All 380 captured source/test/fixture/contract/tool hashes independently match
their calibration Git blobs. Their canonical input-map digest matches the
baseline's `9363f4096dfd34dbfe0238c2311fc26fc9412df0bc5737c3a9976c50bcdbef35`.
Among these inputs, the only current difference is the declared tool hash pin.
The reviewer also compared the current runtime identity and installed dependency
inventory with the calibration record: both match. The latter contains 6,218
files, aggregate `a33f2b7e2f65de1ae295caca7441834038d7283580384846a02b36ee7d2be243`.
The explicit `stdlibAndOsClosureAuthenticated: false` remains a limitation;
this review does not authorize result reuse or claim complete OS/stdlib closure.

## Raw samples and retained maxima

Ordinary sandbox reads of the original children were denied. A subsequent
approved owner-context read independently hashed and parsed all three original
reports and logs. Each original report equals its aggregate `rawSample`, each
derived metric equals both the aggregate metric and baseline raw metric, and
the exact paths/digests equal the baseline's `sampleBindings`. These findings do
not rely solely on a transcribed projection.

All paths below are under `artifacts/tmp/source-performance-1ihs6yaw/`.

| Sample | `sample-N/result.json` SHA-256 | `sample-N/raw.log` SHA-256 |
|---|---|---|
| 1 | `ecd1589d2e8ad8efe98422d40d16c7be71ca5032ca230c6d38b4a232890a038a` | `729364a5ea61813e67a637fc4f08d9d2233917212c421e76634f4a50d55c342b` |
| 2 | `1d8302c34617128c6080a2db37192dbea83dd7bc5a9d82bbec7a34002939a899` | `fcb540c384087fc84a7478a33905a9476ae04c8fdf38ea4bb39e38c4f4369dbc` |
| 3 | `c95231d9cec62af6edd081f0795c4be736e4e81324841f37f44e2b36df8d0874` | `f6c557e86da2354ab838d73717843b509b54aea547bc9c015b3ae46f5ed20a2d` |

The reviewer recomputed all min/median/max distributions and all ten maxima from
all three samples. None was omitted, substituted or averaged away.

| Metric | Approved measured maximum |
|---|---:|
| OpenAlex cold | 3.3920939000090584 s |
| OpenAlex cache | 3.0657525999704376 s |
| Crossref cold | 3.3457566000288352 s |
| Crossref cache | 3.1201019999571145 s |
| Unpaywall cold | 3.215129000018351 s |
| Unpaywall cache | 2.7346579999430105 s |
| Semantic Scholar cold | 3.2385351000120863 s |
| Semantic Scholar cache | 2.7987034999532625 s |
| Separate real-wait broker probe | 1.1417519999668002 s |
| Peak working set | 188821504 bytes |

Each child contains the complete eight-phase provider matrix: 100 OpenAlex,
100 Crossref, one Unpaywall and 100 Semantic Scholar records in each applicable
cold/cache phase. Cold phases dispatch once; fresh cache invocations dispatch
zero times. Each child records four integrated provider calls, preserved restart
state and eight retained diagnostics. The benchmark intentionally disables the
separate failure/cancellation workload; its earlier reviewed functional proof
retains that role.

The separate concurrent broker probes each make two calls with maximum
concurrency one. Wire-start intervals are 1.081947600003332,
1.071840099990368 and 1.0756010999903083 seconds. Actual waits exceed their
requested waits in all three samples. This proves the declared real-clock probe,
not protected concurrent-runtime performance.

The baseline, aggregate and current hardware observation agree exactly:
Windows 11 build 10.0.26200, AMD64, Intel64 Family 6 Model 183 Stepping 1,
20 logical CPUs and 16984227840 bytes physical memory. The exact object, including
processor/vendor and OS fields, remains in the hashed baseline. Method objects
also agree exactly. Subsequent qualification must match this hardware and gate
every raw metric at the smaller of 1.2 times its reviewed maximum and the unchanged
30-second/512-MiB absolute ceiling. All baseline maxima are finite, positive and
below those absolute ceilings. No threshold relaxation is approved.

## Exact-candidate checks and disposition limits

`artifacts/tmp/CAP-04.S02.baseline-checks-01.json` has SHA-256
`92b847f282be0433902d5a35f88649d2fc3c64617e36cae55cb1dd7ef12e100f`.
Its inspected producer `CAP-04.S02.baseline-checks-01.py` has SHA-256
`33469c77f149522a68adda0f2661df83ecb47266f6d70fce2f7f1c5bbc21dfd2`.
All five recorded checks bind the reviewed candidate, exact command, elapsed
interval, exit 0 and matching retained log digest:

| `artifacts/tmp/` log | SHA-256 |
|---|---|
| `CAP-04.S02.baseline-unit-01.log` | `e0e2775803cec859ed7dcb704de0aa9df6d9000ded9d9a8bcd0425da77a7b104` |
| `CAP-04.S02.baseline-lint-01.log` | `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18` |
| `CAP-04.S02.baseline-format-01.log` | `fd2299c9f1c6dc869070883e281051bfe93aacf66c1a3b0069f45b4aa410ca50` |
| `CAP-04.S02.baseline-types-01.log` | `8e63ae22e8213e327a5e9cbd584067681681bd8ef7f25c869877887ccdcfc4ff` |
| `CAP-04.S02.baseline-baseline-01.log` | `918fdc07328f3b31e36cbb97e2eae13d52cd05fdfa9a09610121cc56f3377aaf` |

The unit log contains six unskipped passing fail-closed control cases, 0.143
seconds at the test-runner boundary. Ruff, format and focused mypy pass; the actual
pinned-baseline validator accepts ten metrics and three retained samples.
No material baseline-integrity or authority blocker remains.

This is measured local protected-Core/DPAPI/SQLCipher work with synthetic HTTP
and ASGI/native context. Cold means a fresh process/project, not flushed OS
caches. It supplies no live-provider latency, minimum-hardware, installer,
fresh native GUI or spoken screen-reader claim. Prior native/TLS/accessibility
proof retains its original candidates and limits. Known broad-quality failures,
Windows-token symlink skips and full repository/profile, packaging and
cross-capability Wave obligations remain open.

A separate fresh three-process qualifying invocation is still required against
these approved immutable bytes. Preserve any failed attempt; do not rewrite the
baseline to obtain a pass. Consolidated slice evidence and independent slice
disposition follow only after that qualification. This note changes neither
the original task approvals nor the already recorded F-SLICE-01/F-SLICE-02
closures.
