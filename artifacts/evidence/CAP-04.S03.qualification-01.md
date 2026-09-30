# CAP-04.S03 integrated qualification

CAP-04.S03, **canonical work, version, and identity reconciliation**, has a
complete criterion-linked slice packet for independent disposition. This record
does not approve the slice, W2 exit, or release. The approved W2 packet is frozen
at `c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`; the applicable slice plan is
`planning/slice-plans/CAP-04/CAP-04.S03-canonical-work-version-and-identity-reconciliation.md`,
especially sections 8 and 10–17. The final tested candidate is
`608d53830727ede882866482ebe0d9e495f62725`. The product implementation is
unchanged from the independently approved linked correction
`c3d4ae5a4b9c44f857749dcb25a4ebd9989461e2`; subsequent changes add reviewed
benchmark controls/baseline and the four named scenario tests, without changing
the frozen matcher, thresholds, gold labels, security authority, migrations, or
approved experience reference.

## Criterion-to-proof matrix

| Approved area | Evidence and actual boundary |
|---|---|
| T01 exact identity and source preservation | `CAP-04.S03.T01.json` and `T01.review-R01.json` approve identifier normalization, unique exact links, invalid/reassigned/conflicting identifiers, immutable source assertions, protected SQLCipher persistence, current rights, and rollback/reopen. The fresh 206-test slice run re-executes exact, repository, migration, and native source convergence cases. Registry verification is not inferred. |
| T02 candidates and human review | `CAP-04.S03.T02.R02.json`, `T02.review-R02.json`, and the linked `W2.C03.T01.json`/`review-R01.json` bind frozen scoring, gold precision/recall, revision-keyed feature cache, impact/uncertainty review priority, provenance, protected batch publication, complete merge/split partitions, and durable candidate ordinals. Fresh `test_known_qualification_corpus_meets_original_precision_and_recall_targets` retains 1092 true positives among 1142 cross-source returned pairs against 1115 gold pairs (precision 0.9562171628721541; recall 0.979372197309417), with 50 false positives and 23 missed pairs. These are known qualification labels, not an unseen holdout or an acceptance probability. |
| T03 versions, warnings, and downstream impact | `CAP-04.S03.T03.json` and `T03.review-R01.json` approve preprint/manuscript/version-of-record and sourced notice relationships, exact preference lineage, retraction/correction warning and dependent-output review, preserved history, retry, cancellation, and reopening. Fresh `test_native_review_retry_reversal_and_restart_preserve_protected_history`, `test_correction_keeps_historical_preference_and_immediately_denies_dependent_reuse`, and portable version-fixture cases pass. Version decisions remain human decisions. |
| Named section 8 identity ambiguities | Fresh `test_named_identity_ambiguities_preserve_distinct_sources_for_review` exercises homonymous authors, translated titles, conference/journal manifestations, and group authors without changing configuration. Same author name alone does not retrieve a pair. Translated titles with the same DOI do not enter the fuzzy queue in this fixture; their title disagreement and direct review-only comparison remain visible, while existing exact-identifier tests govern unique DOI linking. Conference/journal and group-author pairs enter the review queue with distinct source/revision identities, conflicting DOIs, and human-review-only disposition. This is bounded scenario characterization, not general translation understanding or perfect recall. Existing tests cover missing year/features, title revision, identifier conflict, corrections, retractions, merge/split, and concurrent decisions. |
| Integration, denial, cancellation, restart | The fresh reconciliation suite passes 206 cases at the exact candidate, including actual Windows native supervisor/generated client/React/Core/DPAPI/SQLCipher, accepted imports plus retained connector, candidate review, split/merge, sourced retraction, lost-reply retry, restart, current rights, malformed/stale source and command denial, partial propagation, cancellation, and fault rollback. Provider HTTP and source records are synthetic; no live-provider or installed-package result is claimed. |
| Contract, migration, and recovery | Fresh selections pass 31 migration-chain, 11 protected-storage, 37 shared-contract, and 15 dependency-impact cases. They cover populated predecessor fixtures, additive schema 14–16 transitions, backup/interruption/retry/reopen, long admitted Windows paths, retained historical state, generated Core API parity, and graph continuation. Portable `work-versions.v1.json` validates against public schemas and can be consumed without private repository modules. No later-slice implementation is claimed. |
| Security, privacy, rights, UX, architecture | Task evidence and the fresh integration run cover current project/Intent/rights admission, local protected storage, redacted diagnostics, bounded resources, source-aware warnings, keyboard/focus, responsive and light/dark React review paths, and native route denial. The approved presentation reference remains `RO-UI-ACADEMIC-MINIMAL-1.7`; T02/T03 UI-change records and task checks bind its conformance. Fresh Core contract generation, architecture, repository-structure, fixture-corpus, test-file lint/format/types all pass. No spoken screen-reader session, complete native-DPI matrix, or new visual inspection is claimed at this test-only successor. |
| Section 12 observability and provenance | Exact source receipts, candidate feature scores/flags/configuration, 103 candidates from the protected benchmark fixture, durable review priority/decision and version history expose volume, feature, conflict, merge/split, and warning facts without converting diagnostics to scholarly evidence. There is no measured researcher agreement or later correction rate; these remain unavailable rather than fabricated. The benchmark's timing counters are qualification evidence, not product telemetry. |
| Section 11 performance | Independently approved immutable baseline `214292cf8f636a2d8ebecd31d4f0e9f7b618d928f7efaf1bbaeae0a78b627d9f`; three fresh child processes at `608d5383` each pass the smaller of the measured baseline plus 20% and the original absolute ceiling. Details below. |

## Fresh checks and measured performance

The worktree and selected inputs stayed fixed and clean during each qualifying
run. Focused 19-case ambiguity/exact/frozen-gold checks pass. The full affected
reconciliation selection passes **206 tests in 652.345 seconds** (wrapper
654.757 seconds). Fresh additional selections pass 31 migration cases in
36.032 seconds, 11 protected-storage cases in 2.377 seconds, 37 shared-contract
cases in 11.982 seconds, and 15 dependency-impact cases in 2.507 seconds.
Core API contract, architecture, repository structure, fixture corpus, and
affected test-file lint/format/types pass. Commands, exact candidate, raw log
paths and SHA-256 bindings are in `CAP-04.S03.qualification-01.json`. An
initial invocation named a nonexistent `tools/fixture_check.py`; its retained
nonqualifying log is superseded by the actual
`tools/fixture_corpus_check.py --repo .` PASS. No test or assertion was weakened.

Final qualification:

```text
python -B -s -X pycache_prefix=artifacts/tmp/CAP-04.S03.performance-qualification-02-unused-bytecode tools/reconciliation_performance_check.py --report artifacts/tmp/CAP-04.S03.performance-qualification-02.json
```

The raw report is `artifacts/tmp/CAP-04.S03.performance-qualification-02.json`,
SHA-256 `18cc838e972b1d94b2b67ef7a22a3e6c180f5bc99af552605b4d906de0876199`.
It records `status: PASS`, `performanceQualifying: true`, 482 committed input
hashes, current runtime/dependencies/hardware, each original child result and
log, and min/median/max distributions. Producer elapsed 389.3026608999353
seconds. The reviewed Windows 11 build 10.0.26200 AMD64 host has Intel64 Family
6 Model 183, 20 logical CPUs, and 16984227840 bytes physical memory. Every raw
sample passed individually; none was dropped or averaged into a pass.

| Metric | Largest fresh observation | Effective reviewed limit |
|---|---:|---:|
| Kernel cold, seconds | 8.89783630007878 | 10.776014639809727 |
| Feature preparation, seconds | 0.06010389979928732 | 0.0713234399445355 |
| Prepared retrieval, seconds | 9.081792799988762 | 10.983169199991972 |
| Protected cold, seconds | 34.52603850001469 | 41.32377588003874 |
| Protected warm, seconds | 30.012152299983427 | 35.67360060000792 |
| First page, seconds | 13.307880700100213 | 16.167698640190064 |
| Later page, seconds | 13.393534099915996 | 16.257730679959057 |
| Peak working set, bytes | 213319680 | 255860736 |

The kernel uses the frozen 2463-record DBLP/ACM qualification split,
105451 comparisons, 1273 total/1142 cross-source returned pairs, and 1092
true positives. Each protected sample uses 202 accepted import records plus one
retained connector source, 203 records, 103 candidates, distinct cold/warm
requests and jobs, zero warm feature recomputations, matching full candidate
content, complete 100/3-item pages, and zero provider dispatch during
measurement. DPAPI/SQLCipher and durable worker admission are real. Setup uses
synthetic transport and ASGI/native context with setup-only capacity
substitution; OS caches are not flushed, setup/reopen/close time is excluded,
and peak memory covers each whole child. This is source-based Windows evidence,
not installer, minimum-hardware, live-provider, native-GUI, or researcher
agreement/correction-rate qualification. Runtime identification explicitly
does not authenticate all standard-library/OS inputs.

The prior three-process PASS at `6214f599` is retained at its own 481-input
candidate as `performance-qualification-01.json`; it is not relabeled
qualification for the final 482-input test successor. Calibration 01 failed
before samples on a physical checkout/Git newline mismatch and remains FAIL.
Calibration 02, the independent baseline review, and the adverse then approved
control reviews retain their original candidate and nonqualifying scope. The
independent reviewer separately authenticated the final report, all three
child result/log pairs, all 482 committed inputs, environment identities, raw
workload/metrics, distributions, and limits; final slice disposition remains
separate.

## Remaining Wave boundaries

The task/control/native/UI proofs retain their exact historical candidates and
principal limits; the fresh slice checks above bind `608d5383`. Previously
disclosed 55 broad quality errors in 13 unchanged files and two unavailable
Windows symlink-token tests remain W2 obligations, not waived passes. The
checkpoint/full repository and affected-profile matrix, cross-capability
happy/failure/denial/cancellation/migration/restart/recovery, required Windows
packaging/platform, security/privacy/rights/accessibility/performance
qualification, independent W2 review, and separate human G2 release decision
remain due at their documented stages. No external release or push is authorized
by this packet.
