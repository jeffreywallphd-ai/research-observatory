# CAP-04.S04 source-overlap performance baseline proposal 01

The approved W2 packet is frozen at `c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`.
This proposal addresses CAP-04.S04 section 11 only. Calibration ran at the clean
commit `92be1b98779236418e614158f18f7af5cf82b404`; it is **MEASURED,
nonqualifying**, and does not approve the slice or W2 exit. The proposed baseline
is `tests/fixtures/corpus-reports/performance-baseline.json`, SHA-256
`6658a04b314e91c8f164c45f512aeeb1eedba96d22b881f3c97004674b7fdcaf`.

The calibration report is
`artifacts/tmp/CAP-04.S04.performance-calibration-02.json`, SHA-256
`d8fc6e7369ecbc5a0ab32db51d3f008e1f098fa85416e3fbaad86c898ca146ae`.
It retains three fresh child-process results and logs with individual SHA-256
bindings, all 525 selected committed input hashes, raw samples, hardware,
method, and min/median/max distributions. I checked all six child result/log
hashes against their physical bytes and each child result against the raw sample
embedded in the parent report. The runner byte SHA-256 is
`d4be5f67b69ba58e5840e7137043e5b12d9d6364de511b306210e7f9578b4036`;
the workload fixture byte SHA-256 is
`5827654568f38f9146d172c3fbdb23eeead36102e8047396a37761afbf5c5474`.

The retained first invocation,
`artifacts/tmp/CAP-04.S04.performance-calibration-01.json`, is **FAIL** before
samples: its first reported contract file had CRLF bytes in the physical checkout
although its committed blob has LF. I restored affected checkout files to their
exact committed physical bytes and refreshed the index without a staged or
committed content change; Git was clean before the successful calibration. The
failed preflight remains adverse evidence and establishes only its first named
byte mismatch.

The synthetic local fixture has 64 distinct canonical items, 67 discovery
paths, four source roots and six exact overlap pairs. It measures an incremental
path update, first report after project reopen **and that update**, a repeat
report on unchanged corpus facts, saved-report inspection, and both 32-item
drill pages. Real Windows current-user DPAPI, SQLCipher and Core/rights adapters
run in each child; provider transport is denied during measurement. Synthetic
setup and project reopen/close are excluded from operation timings, while peak
working set includes the whole child. OS caches were not flushed. This is
source-based Windows evidence, not installed-package, minimum-hardware, live
provider, or researcher-workflow performance evidence. Only one item bears the
four-source overlap, so this fixture does not independently prove large-corpus
scaling or minimum-hardware performance. Setup/reopen logs include worker
availability warnings outside the timed operations; this is not worker
throughput evidence.

The measured Windows 11 build 10.0.26200 AMD64 host has Intel64 Family 6 Model
183, 20 logical CPUs and 16,984,227,840 bytes of physical memory. Three-process
calibration elapsed 281.085 seconds. The table shows the largest raw sample and
the proposed per-sample limit: the smaller of that maximum plus 20% and the
runner's fixed absolute ceiling. Every future qualifying sample must pass;
averaging cannot hide a failure.

| Metric | Calibration maximum | Proposed effective limit |
|---|---:|---:|
| Incremental update, seconds | 0.3724796 | 0.44697552 |
| First report after reopen and update, seconds | 0.3548492 | 0.42581904 |
| Repeat report, seconds | 0.3777 | 0.45324 |
| Saved inspection, seconds | 0.2965144 | 0.35581728 |
| First drill page, seconds | 0.3369335 | 0.4043202 |
| Later drill page, seconds | 0.2844903 | 0.34138836 |
| Peak working set, bytes | 205,946,880 | 247,136,256 |
| Database/WAL growth, bytes | 970,752 | 1,164,902.4 |

Independent review of the exact proposed bytes, raw samples, hardware,
threshold and failure history is required before pinning the baseline hash in
the runner. The reviewed baseline is an input to a later fresh qualifying run,
never an output rewritten by that run.
