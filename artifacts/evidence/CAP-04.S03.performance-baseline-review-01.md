# CAP-04.S03 measured-baseline independent review 01

- Reviewer: `agent:/root/w2_c02_review`, independent of the implementation owner.
- Candidate: `4fcd9f1e066caebf98024016364ecb90a0e17b18`.
- Predecessor and calibration commit: `81930fe594f754bf4f0d43e0e7405af8a8a8bcfe`.
- Disposition: **approved immutable baseline; no blocking findings**.
- Scope: baseline input and historical calibration evidence under approved
  CAP-04.S03 section 11 and project automation guide section 8.3. This is not
  performance qualification, product-task, slice, integration or release approval.

The approved baseline is exactly
`tests/fixtures/scholarly-duplicates/reconciliation-performance-baseline.json`,
raw SHA-256
`214292cf8f636a2d8ebecd31d4f0e9f7b618d928f7efaf1bbaeae0a78b627d9f`.
The three-path candidate diff adds those bytes, the accompanying evidence note,
and their exact hash pin. No methodology, ceiling, workload, product, scoring,
gold data, security/rights authority, approved reference, migration, task history
or release criterion changes.

## Historical chain authenticated independently

The reviewer read original local artifact bytes and verified the following:

- Calibration report:
  `artifacts/tmp/CAP-04.S03.performance-calibration-02.json`, SHA-256
  `f73eb2cbb07ad01da7daa32145ce9e10d45e125baabc4f30e17ba7ac6dd0475d`.
  It records MEASURED, calibration mode, performanceQualifying false, disabled
  evidence reuse, no baseline comparison, and all three repetitions.
- Original execution log:
  `artifacts/tmp/CAP-04.S03.performance-calibration-02.log`, SHA-256
  `86d3e5f9778e60019b4343182464f14f228a13236ba1928ec8a5bfd3b25d3cb5`.
  It records repetitions 1, 2 and 3, without omissions.
- Historical tool bytes at the calibration commit:
  `tools/reconciliation_performance_check.py`, SHA-256
  `e18f95682e79f7a432280d37c9343d3046e7c559f6ff11d005df340dff547466`.
  The calibration commit is an ancestor of this candidate. Its only change
  after the reviewed remediation candidate was delivery of the R02 review note.
- All 481 report input hashes match their exact Git blobs at the calibration
  commit. The complete input-map canonical digest is
  `6b69b35ee10358bc4b681cb88237580530e22fc2fbb8d89fe5bf5ac33d3720f3`.
  Current selected-path inventory differs only by the newly added baseline;
  the tool change is solely the pending-hash replacement.

Each original child result and raw log was independently read and hashed. The
bindings below agree with both the aggregate report and baseline. All paths are
under `artifacts/tmp/reconciliation-performance-d7g5o3qn/`.

| Repetition | Result | Result SHA-256 | Raw log SHA-256 |
|---|---|---|---|
| 1 | `sample-1/result.json` | `ad1b1c7e1cc09639c24dfacd3c6629555fe834bdb90aa37049c5254082d386e2` | `3ce5b9eda714400b7c00ca7440466f0fc59e6c2b40d15d83269e21854d56d74d` |
| 2 | `sample-2/result.json` | `1a347806137c4bfba149a69e10921c4c35c2e3470f399bd43be2be67b817177f` | `08cfa59e387b80feaf04e492ea586ecea7e0ed95cd1767d073a994ec2f15f586` |
| 3 | `sample-3/result.json` | `cd30944cdd54a13291a19b681af3fc50981ddb4be69743536b50d948fb9f6b85` | `3f3c12df83e2b189ae2c78c15ae3b1eed8b273065822edb50762c0c797d14455` |

Each corresponding log is `sample-N/raw.log`. Parsed result JSON equals its
aggregate rawSample exactly. Separate sample directories, distinct synthetic
candidate-content identities, and each log's setup/measured application
lifecycles agree with the reviewed fresh-child producer. This review
authenticates retained execution evidence; it does not claim independent
observation of historical operating-system process IDs.

## Samples, budgets and environment

The reviewer independently projected timing/memory fields from each original
raw sample, checked workload facts, and recomputed all eight maxima and all
min/median/max distributions. These match the aggregate metrics and every
baseline rawMetrics row exactly. No sample was discarded or averaged into a
passing result. Every value is finite, positive and within its absolute ceiling.

All three samples report the frozen 2463-record kernel, 105451 comparisons,
1273 total/1142 cross-source pairs, 1092 true positives and 1115 gold pairs.
Precision equals 1092/1142 and recall equals 1092/1115. Each protected sample
reports 202 accepted import records plus one connector record, 203 sources,
103 candidates, distinct cold/warm requests and jobs, zero warm recomputations,
equal cold/warm candidate content, complete 100/3-item pages, and zero provider
dispatch during measurement. The reviewed producer authenticates page content
against durable protected ordinals; the original reported content digests were
preserved. No protected database was reopened during this baseline review.

The largest observations remain 8.98001219984144 seconds kernel cold,
0.05943619995377958 seconds feature preparation, 9.15264099999331 seconds
prepared retrieval, 34.43647990003228 seconds protected cold,
29.7280005000066 seconds protected warm, 13.473082200158387 seconds first page,
13.548108899965882 seconds later page, and 213217280 bytes peak working set.
Future qualification must gate every sample at the lesser of each approved
maximum times 1.2 and the unchanged absolute ceiling. No ceiling is relaxed by
this approval.

Baseline method and hardware equal the original report and reviewed producer.
The reviewer also recomputed current runtime, installed-dependency and hardware
identities and confirmed exact equality with the recorded values:

- Runtime canonical digest:
  `d40cf9d823bcbafeeab9282683c6b8dec4f2958a534c1066ba5b8ac0be5cd546`.
- Installed-dependency record canonical digest:
  `682e199239f88ccb2935e6a8a41da2b739042216ddc528e2de7506bab6f20121`,
  covering 6218 installed files. Its file-inventory digest is
  `a33f2b7e2f65de1ae295caca7441834038d7283580384846a02b36ee7d2be243`.
- Windows 11 build 10.0.26200, AMD64, Intel64 Family 6 Model 183 Stepping 1,
  20 logical CPUs, and 16984227840 bytes physical memory.

The runtime record explicitly leaves standard-library/OS closure unauthenticated.
The benchmark is source-based, not installer/package attestation. Setup-only
capacity substitution, ASGI/native context, synthetic source data/transport,
unflushed OS caches, whole-child peak-memory measurement, and excluded
setup/reopen/close timing remain disclosed. No live-provider, native GUI,
minimum-hardware, researcher-agreement or correction-rate claim is approved.

## Retained failure and review limits

Calibration 01 remains FAIL/nonqualifying with no samples at
`artifacts/tmp/CAP-04.S03.performance-calibration-01.json`, authenticated SHA-256
`a0e1db8b5434796134ef6872ad545243ac76e2d3b9e06ebebc160fd437f4bebd`.
Its report identifies a committed-input byte mismatch. It was not relabeled,
included as a sample, or reused as successful evidence. The later 481-blob
authentication establishes calibration 02's committed inputs independently.

The automatic baseline validator does not authenticate all historical artifact
provenance. This review performed that separate authentication for these exact
bytes; it does not enlarge the validator's guarantee. Prior adverse control
review and its R02 closure remain immutable. The R02 note hash is still
`76519d09f559a12e7718314663b73196facbc6f609cc387a8a925263c9be2e0d`.

Reviewer read-only verification receipts are retained at
`artifacts/tmp/CAP-04.S03.performance-baseline-review-checks-02.log`, SHA-256
`4d0267a07c2f26414caa6a2db2956457cac35fd5cf51dc245cfb3ef9e394caea`,
and `artifacts/tmp/CAP-04.S03.performance-baseline-review-environment-01.log`,
SHA-256 `952047bbdc569c5638505ae4fedc299624352a182f37df91c4c7e06f97d59ac4`.
The initial reviewer probe used an incorrect lifecycle event label and stopped;
the corrected probe checks the actual `runtime.started`/`runtime.stopping`
events. This was a reviewer assertion correction, not a product or evidence edit.

No qualification or broad suite was run. The candidate and shared inputs stayed
fixed; this append-only note is the reviewer's sole tracked-path addition.
After committing the review record, the owner may run fresh three-process
qualification against this approved baseline. A failed measurement remains
failed and requires investigation, not a silent baseline or budget change.
