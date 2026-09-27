# CAP-04.S02 source-performance baseline 01

This is a proposed measured baseline pending the separate independent baseline
disposition. Calibration is explicitly nonqualifying; neither this note nor the
hash pin asserts a performance pass, slice completion or release approval.

## Bounded input publication

Predecessor and calibration candidate:
`c8a3c3ba7deea9accf24587e4f4674a92ecc68bb`.
Authority: approved CAP-04.S02 sections 10–11 and 15–17 under complete W2 approval
`c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`, plus benchmark evidence requirements in
`docs/automation/project-automation-guide.md` section 8.3. The measurement control
already has independent disposition in
`artifacts/evidence/CAP-04.S02.qualification-controls-review-01.md`.

The exact delta adds
`tests/fixtures/scholarly-metadata/source-performance-baseline.json` and replaces
only the pending `BASELINE_SHA256` constant in
`tools/source_performance_check.py`. This note records the evidence and boundary.
No methodology, workload, regression allowance, absolute ceiling, product code,
security/rights authority, approved reference, migration, test assertion or
historical evidence changes. This publishes required measured qualification
inputs; it adds no supplemental refactoring allocation.

Baseline raw SHA256:
`d21fc40e3fedb71ecf0e0b274055d047b2fec4bb4278a1642894534d3c323822`.
The precursor measurement-tool Git/file SHA256 is
`f18935bbe14ab615ab887c6813cf9d7d39df3bccbfddddf16896d4e949afcd74`.
The initial pending hash denied qualifying use until measured inputs existed.
Independent review must authenticate these bytes before a separate fresh
qualifying invocation. Rollback before acceptance restores the pending pin and
retains the calibration and any adverse evidence; it does not invent a pass.

## Executed calibration

```text
python -B -s -X pycache_prefix=artifacts/tmp/CAP-04.S02.performance-calibration-01-unused-bytecode tools/source_performance_check.py --report artifacts/tmp/CAP-04.S02.performance-calibration-01.json --calibrate
```

Actual normal Windows principal, fixed clean candidate, source/installed-runtime
locks and fresh parent/child bytecode prefixes. No competing heavy verification
or shared-input edits. Exit 0; `status: MEASURED`, `performanceQualifying: false`.
The producer reports 247.4937678000424 seconds; the execution wrapper reports
259.98795830004383 seconds, including its invocation boundary. These are separate
measured intervals, not a savings estimate.

Aggregate report SHA256:
`e07561457bb29d02e264ed5f327d51064f51b54b045420d529d0328608224097`.
The report records 380 exact source/test/fixture/contract/tool input hashes,
installed dependencies and runtime identity, actual hardware, method and all
three raw child reports/logs. The baseline retains each child's relative path
and exact digest, every raw metric and the captured source-input-set digest.
No samples were removed or replaced. Maxima are computed from all three samples.

| Metric | Largest observed calibration value |
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

Every future qualification sample must remain within its reviewed maximum plus
20%, and the unchanged absolute 30-second/512-MiB ceilings. The distribution is
min/median/max of three repetitions; no inferred percentiles or probabilities.
Cold means a fresh protected project/process with uncached synthetic provider
page; cache means a fresh authorized invocation using the same scientific page
and zero provider dispatch. Three providers return 100 records per page;
Unpaywall returns its supported singleton. The separate concurrent broker probe
requires two calls, one in flight, at least one second between starts and an
actually completed rate wait.

Measured hardware: Windows 11 build 10.0.26200, AMD64, Intel64 Family 6 Model 183
Stepping 1, 20 logical CPUs and 16984227840 bytes physical memory. The exact
hardware object is retained in the baseline and must match qualification.
No account names, user paths, sessions or private runtime settings are published.

## Verification and review sequence

Commit this bounded input publication, then execute the existing six fail-closed
source-performance control tests, affected lint/format/type checks and actual
baseline validation. Authenticate every raw calibration report/log and recompute
the ten maxima during independent review of that exact candidate. Record that
review separately; keep shared HEAD fixed throughout each selected check group.
After acceptance, run a fresh three-process qualification without `--calibrate`.
Keep any failed invocation and its false qualifying flag; never relax a ceiling
to conceal a failure. Final slice evidence composes these exact results with the
already reviewed task, correction and integrated source evidence.

The workload uses real DPAPI/SQLCipher, Core and durable publication with
synthetic HTTP and ASGI/native context. OS caches are not flushed. It does not
qualify live provider latency, minimum hardware, installer performance, native
GUI or a spoken screen-reader session. The rate probe substitutes authority,
store and transport; it does not establish protected concurrent-runtime
performance. Previously disclosed full-quality failures, unavailable symlink
checks and remaining full-profile/platform/Wave obligations stay open.
