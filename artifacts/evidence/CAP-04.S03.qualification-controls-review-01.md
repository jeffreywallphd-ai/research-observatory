# CAP-04.S03 qualification-controls independent review 01

- Reviewer: `agent:/root/w2_c02_review`, independent of the implementation owner.
- Candidate: `d1e43e9303c80c0713863939184a5fb255c234cf`.
- Predecessor: `dd43c45cef7e7581a1b02c75a373bd64748c5b78`.
- Disposition: **changes requested; two blocking findings**.
- Scope: qualification controls only. This is not task, slice, baseline,
  performance, integration, or release approval.

Authority reviewed: approved CAP-04.S03 sections 10–11 and 15–17 under W2
approval `c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`, project automation guide
section 8.3, and the applicable independent-review and bounded-maintenance
procedure. The candidate remained fixed and clean during inspection and probes;
this append-only note is the sole tracked-file change by this reviewer.

## Reviewed change and evidence

The exact six changed paths were inspected:

- `artifacts/evidence/CAP-04.S03.qualification-controls-01.md`
- `quality-scope.json`
- `tests/reconciliation/native_fixture.py`
- `tests/reconciliation/performance_workload.py`
- `tests/reconciliation/test_performance_check.py`
- `tools/reconciliation_performance_check.py`

The reviewer independently ran the six focused
`tests.reconciliation.test_performance_check` tests with the repository Python,
`-B -s`, and the Core source import path: all six passed (0.066 seconds reported
by unittest). No broad suite or additional protected workload was run.

A focused fault-injection probe exercised the actual `_protected` producer and
`sample_metrics` consumer. It substituted the surrounding client/runtime to
control scheduling and page replies; it is a control reproduction, not proof of
a product defect or real DPAPI/SQLCipher execution. Its retained output is
`artifacts/tmp/CAP-04.S03.qualification-controls-review-probes-02.log`, SHA-256
`9c6288c1178c784b6dd3b3caf02f41e7197183ce5765278d8589cb40adb0c2e4`.

The owner's nonqualifying smoke log was read and hashed:
`artifacts/tmp/CAP-04.S03.workload-smoke-d1e43e93.log`, 3,007,068 bytes, SHA-256
`2d7da69ea0e1ead1ae21e543f35686d85d1c130bc48e812f18cdfe1f152f5608`.
Its last JSON reports the expected kernel counts and a 203-record/103-candidate
protected workload, cold/warm times about 35.41/29.48 seconds and first/later
pages about 13.22/13.19 seconds. It lacks peak-memory measurement and three
repetitions. Its successful completion does not resolve the false-pass paths
below and is not calibration or qualification.

## Blocking findings

### F-S03-PERF-01 — High / P1: warm-cache observation starts after enqueue

Criterion: S03 section 11 requires revision-bound feature caching and truthful
warm/cold measurement; section 10 requires review of the stated outcome;
automation guide section 8.3 requires a bound, reproducible methodology.

At `performance_workload.py:101`, the warm request is prepared and scheduled
before the `feature_cache.prepare_record` observer is installed at line 106.
The real worker's `schedule` sets its wake signal before returning, and the
application starts its background pump. Therefore work can execute before the
observer exists. A later explicit `run_pending()` cannot count earlier work.

Reproduction: make the warm schedule response perform one real
`feature_cache.prepare_record(CandidateRecord(...))` call before returning;
then report the job succeeded and let the explicit drain have no work. The
actual producer reports `featureComputations: 0`, and `sample_metrics` accepts
the sample. The probe independently observed one early computation. This is a
deterministic ordering reproduction of the available background-worker race,
not an assertion that the retained smoke happened to take that ordering.

Smallest closure: install observation before warm prepare/schedule and retain
it through authoritative terminal status, covering background and explicitly
drained work. Add a regression that forces recomputation before schedule
returns and proves rejection. Preserve real worker admission and execution.

### F-S03-PERF-02 — High / P1: page counts can certify incomplete candidate output

Criterion: S03 sections 10–11 require representative end-to-end performance
evidence; sections 15–17 require truthful integrated proof. Automation guide
section 8.3 requires the measured workload to be bound to its fixture/method.

At `performance_workload.py:139`, protected pagination verifies aggregate
counts, item counts and cursor progress, but never checks candidate identities
or content. Only the warm set is paged; cold/warm revision-bound candidate
content is not compared. `sample_metrics` accepts the resulting count-only
summary. A workload that substitutes or repeats records can consequently
qualify as a complete 103-candidate retrieval.

Reproduction: return 100 distinct pair identities on the first page, then repeat
its first three identities on the later page, retaining recordCount 203,
candidateCount 103 and cursors 0/100/end. Both `_protected` and `sample_metrics`
accept the result. The probe returns 103 rows but only 100 unique pairs. The
current six control tests do not cover this case.

Smallest closure: authenticate each measured page's set and exact ordinal
against the durable revision-bound candidate identity/content, reject repeated
or substituted pairs, and compare the complete cold/warm candidate content.
Keep any extra protected inspection outside the timing boundary. Retain only
content-free counts/digests in exported evidence. Add regressions for a repeated
later-page pair and changed/substituted content with unchanged counts.

## Other reviewed controls and explicit limits

The committed-source input inventory includes the producer, fixture, Core,
contracts, tests, frozen CSV/JSON data, lockfile and imported measurement tools.
The runner holds Windows file locks and checks committed bytes before and after
measurement, binds installed dependencies/runtime, requires a fresh absent
bytecode prefix, and starts children with `-B -s -P`. This is a source benchmark,
not package/installer attestation. Runtime identity explicitly does not claim
authenticated standard-library/OS closure. No broader package claim is approved.

Calibration and qualification are correctly separated in the inspected code;
the baseline pin is still pending. The control tests cover nonfinite/budget
rejection, every-sample gating, stale-PASS replacement, child directory/bytecode
configuration, and final-publication failure. They do not by themselves prove
the producer outcomes in the two findings.

The proposed 20-second page ceiling is consistent with the disclosed roughly
13-second smoke and does not relax an approved 10-second baseline: the earlier
10-second suggestion was provisional. The absolute ceilings remain combined
with each independently reviewed calibration maximum plus 20%, with every
sample gated. No measured resource baseline or minimum-hardware claim is
approved by this note.

`validate_baseline` enforces the exact reviewed-byte pin, method, metric
inventory, three raw metric rows, maxima and absolute ceilings. `run` separately
checks current hardware equality, calibration-commit ancestry and historical
tool bytes. It does **not** require or authenticate the calibration report hash,
input hashes, runtime/dependency identity or child sample/log bindings, nor
derive retained rawMetrics from original rawSample data. A validator-only probe
confirmed acceptance of a pinned object without those fields. This is a
documented limit of current machine validation, not a claim that an unpublished
baseline has violated authority. Before baseline approval, independently bind
the original MEASURED/nonqualifying report, all three sample/log hashes, exact
hardware/tool/source inputs and raw metrics. If the revised control claims to
enforce that chain automatically, add denial tests for missing or substituted
provenance and metric/sample disagreement. Reviewed bytes alone must not be
described as automatic authentication of their contents.

Per-child result bytes are parsed and hashed from one read, and their log hashes
are retained in the parent report together with exact candidate/input identities.
That is a useful chain for later independent authentication, provided all raw
artifacts are retained and rehashed at baseline/slice review. It does not repair
the missing observations above.

The synthetic fixture preserves the two-record default and adds a bounded
202-record mode. Setup-only capacity substitution, synthetic Crossref transport,
ASGI/native context, retained owner-source access and no provider dispatch during
measurement are disclosed. Protected content remains local; exported samples
omit research content and paths. This review found no additional concrete
product-authority or rights bypass in the six-file increment. It does not prove
live-provider, native-renderer, installer or minimum-hardware performance, nor
researcher agreement/correction rates.

## Resume condition

Retain this adverse note. Remediate the two producer findings with failing
regressions first where practical, then obtain incremental independent closure
at the new committed candidate. Only afterward proceed to nonqualifying
three-process calibration, separate immutable-baseline review and a fresh
qualifying run. Product task history and approved slice authority remain intact.
