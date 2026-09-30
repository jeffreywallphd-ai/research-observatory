# CAP-04.S03 measured performance baseline 01

This proposed immutable baseline is pending independent review. The three
calibration samples are explicitly nonqualifying; neither this note nor the
hash pin is a performance pass, slice approval or release decision.

Authority: approved CAP-04.S03 sections 10–11 and 15–17 under complete W2
approval `c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`, plus project
automation guide section 8.3. The benchmark controls were independently
approved for calibration at `346bb2b1086902d2067947bebbf0128c49bc8560`
in `CAP-04.S03.qualification-controls-review-02.md`.

## Bounded input publication

Calibration producer commit: `81930fe594f754bf4f0d43e0e7405af8a8a8bcfe`.
The candidate delta adds only
`tests/fixtures/scholarly-duplicates/reconciliation-performance-baseline.json`
and replaces the pending `BASELINE_SHA256` in
`tools/reconciliation_performance_check.py`. No workload methodology, absolute
ceiling, product code, scoring/gold data, rights/security authority, approved
reference, migration, task history or release criterion changes.

Baseline raw SHA-256:
`214292cf8f636a2d8ebecd31d4f0e9f7b618d928f7efaf1bbaeae0a78b627d9f`.
Calibration producer tool SHA-256:
`e18f95682e79f7a432280d37c9343d3046e7c559f6ff11d005df340dff547466`.
The pinned bytes cannot authorize qualification until independent review
authenticates the original measurement chain.

## Executed nonqualifying calibration

```text
python -B -s -X pycache_prefix=artifacts/tmp/CAP-04.S03.performance-calibration-02-unused-bytecode tools/reconciliation_performance_check.py --report artifacts/tmp/CAP-04.S03.performance-calibration-02.json --calibrate
```

Exit 0; aggregate `status: MEASURED`, `performanceQualifying: false`, three fresh
Windows child processes and protected projects; producer elapsed
389.54123209998943 seconds. Report SHA-256:
`f73eb2cbb07ad01da7daa32145ce9e10d45e125baabc4f30e17ba7ac6dd0475d`.
Execution log SHA-256:
`86d3e5f9778e60019b4343182464f14f228a13236ba1928ec8a5bfd3b25d3cb5`.

The report retains 481 exact source/test/fixture/contract/tool input hashes
(canonical map digest
`6b69b35ee10358bc4b681cb88237580530e22fc2fbb8d89fe5bf5ac33d3720f3`),
installed dependencies (map digest
`682e199239f88ccb2935e6a8a41da2b739042216ddc528e2de7506bab6f20121`),
runtime identity (digest
`d40cf9d823bcbafeeab9282683c6b8dec4f2958a534c1066ba5b8ac0be5cd546`),
hardware, method and every raw child sample/report/log binding. The baseline
retains each raw metric, complete sample binding and these aggregate identities.
Its maxima are recomputed from all three raw rows; no sample is omitted.

| Metric | Largest calibration observation | Absolute ceiling |
|---|---:|---:|
| Frozen-kernel cold preparation plus retrieval | 8.98001219984144 s | 30 s |
| Separate kernel feature preparation | 0.05943619995377958 s | 30 s |
| Prepared-input kernel retrieval | 9.15264099999331 s | 30 s |
| Protected cold batch | 34.43647990003228 s | 120 s |
| Protected new-job warm batch | 29.7280005000066 s | 120 s |
| First 100-candidate page | 13.473082200158387 s | 20 s |
| Later three-candidate page | 13.548108899965882 s | 20 s |
| Whole-child peak working set | 213217280 bytes | 536870912 bytes |

Every future qualification sample must fit both its independently reviewed
calibration maximum plus 20% and the fixed absolute ceiling. The recorded
distribution is min/median/max of three repetitions, without invented
percentiles. The earlier 10-second page figure was a provisional preflight
suggestion. The measured page distribution supports the separately reviewed
20-second ceiling in the control candidate; this note does not silently change
an approved budget.

Measured hardware: Windows 11 build 10.0.26200, AMD64, Intel64 Family 6 Model
183 Stepping 1, 20 logical CPUs and 16984227840 bytes physical memory.
Cold means fresh process/project/application cache, not flushed OS cache.
Measured batches use real DPAPI, SQLCipher, worker admission, source authority
and revision-bound cache. Synthetic project data, Crossref transport and
ASGI/native context are explicit substitutions; setup alone substitutes worker
capacity. No native GUI, installer, live-provider or minimum-hardware
performance claim is made. Researcher agreement and error-correction rates
remain unavailable.

The first calibration attempt remains at
`artifacts/tmp/CAP-04.S03.performance-calibration-01.json`, SHA-256
`a0e1db8b5434796134ef6872ad545243ac76e2d3b9e06ebebc160fd437f4bebd`.
It failed before any sample because the checkout of one otherwise clean JSON
fixture had CRLF bytes while its committed blob and LF attribute required LF.
Its exact committed bytes were restored, Git's index refreshed without a staged
content change, and calibration 02 started with a fresh report and bytecode
prefix. The failed attempt was not relabeled or reused.

## Required independent baseline disposition

Before qualification, authenticate the MEASURED report and execution log;
all three original child result/log bytes and their binding hashes; each
sample's accuracy, source count, candidate content and raw metric projection;
the 481 committed source inputs; actual runtime/dependency and hardware
identity; and equality of baseline method/maxima to the complete raw samples.
The validator pins reviewed bytes and checks method, complete finite positive
metrics and budgets; it does not automatically reauthenticate every historical
ignored artifact. The reviewer must do that separately and record limits.

After approval, run a fresh three-process qualification without `--calibrate`.
Any failure remains failed; do not relax a ceiling to conceal regression.
