# CAP-04.S02 qualification-controls independent review 01

Reviewer: `agent:w2-t03-review` (independent of the campaign owner).
Disposition: **approved for the bounded qualification-control increment**.
Reviewed candidate: `1ccf0f923572aab5f553b2b7de6879d75a0a326c`.
Predecessor: `035f11a3546658ed9c694acbae1c1a3ac4907724`.
Unchanged product candidate: `1e68cab433f194bf5d834bedc974bdac5a4f7cb6`.

This disposition covers the six new qualification Python files, their quality
inventory registration, and the explanatory evidence notes. It does not approve
a product correction, performance baseline, slice completion, Wave exit or
release. Approved CAP-04.S02 sections 8 and 10–15 at W2 approval
`c85a59f3a293f8e3f2eaf6454682c9a14b1efa55` remain the authority. No product,
experience, security, migration or release criterion is changed by this increment.
The predecessor task approvals and adverse preflight observations remain intact.

## Authenticated execution

The owner executed the three selected unittest modules at the fixed committed
candidate, using the canonical `fixed_inputs` guard and fresh parent/child
bytecode prefixes. The reviewer inspected the producer, receipt and executed
log, independently compared all 380 captured source hashes with both candidate
Git blobs and current bytes, and found no mismatch. The product trees under
`apps/`, `services/` and `packages/` have no changes from the product candidate.
The candidate diff passes whitespace checking. The producer's post-run guard
completed before PASS publication; the run finished before review-note writing.

| Evidence | SHA-256 |
|---|---|
| `artifacts/tmp/CAP-04.S02.qualification-controls-01.json` | `d714e9ac0fe7bb96ed76ebff90bdc876fba6cec5693cf7abc1d341231acb4c29` |
| `artifacts/tmp/CAP-04.S02.qualification-controls-01.log` | `0410395cd0282f96eb83afd81908f166e300ed84d9c6ffad744787e340a8d38f` |
| `artifacts/tmp/CAP-04.S02.qualify-controls-01.py` | `7f792b8b862684ddc460956c852b62ee5a3e5ef8f0bcb72b011b42bb6fee6ea5` |
| `artifacts/tmp/source-slice-0_z5smkx/result.json` | `0ed99199bd4c52822fff7145b5b713eaaf5325a1b676b37fa30fbb9c35452b65` |

All 10 named tests passed, with no skips: six in
`tests.connectors.test_source_performance_check`, three in
`tests.connectors.test_connector_network_failures`, and the integrated case in
`tests.connectors.test_source_slice_runtime`. The test runner reports 93.648
seconds; the guarded wrapper reports 149.986743 seconds and exit code 0. These
are distinct measured intervals. The receipt binds 6,218 installed dependency
files, aggregate SHA-256
`a33f2b7e2f65de1ae295caca7441834038d7283580384846a02b36ee7d2be243`,
and the CPython executable/process/DLL identities. Its explicit
`stdlibAndOsClosureAuthenticated: false` remains a limitation; this review does
not turn it into complete OS/stdlib identity or authorize cached proof reuse.

The protected result initially denied the reviewer's sandbox read. A subsequent
approved owner-context read independently hashed and projected its actual bytes;
the final result hash above is not based solely on an owner-transcribed summary.
The log identifies that exact result path. Its four-provider cold/cache matrix
contains 5 OpenAlex, 5 Crossref, 1 Unpaywall and 5 Semantic Scholar records per
phase, with one synthetic provider dispatch on each cold phase and zero on each
cache phase. Nine integrated synthetic dispatches include the failure, recovery,
timeout, reset and cancellation boundaries. Restart, cancellation preservation
and boundary flags are true; retained exception codes are `timeout` and
`provider-unavailable`. Public handoff records keep model-use, export and share
rights unknown.

The separate concurrent broker probe records two calls, maximum concurrency one,
1.069350 seconds between wire starts and a completed 0.997268-second requested
wait taking 1.012436 seconds; total probe time is 1.142243 seconds. This establishes
actual waiting in the explicitly substituted broker probe, not protected-runtime
concurrency. Functional timings at count five are not performance qualification.

## Control and finding disposition

The reviewed performance producer requires an immutable independently reviewed
baseline hash, exact method and workload inventory, finite positive bounded
metrics, and all raw calibration samples. It compares every qualifying sample
against both the reviewed allowance and absolute ceilings. Calibration remains
nonqualifying, failure replaces stale PASS, and raw child reports are parsed and
hashed from the same confined byte snapshot. The pending baseline hash continues
to deny qualifying execution; this review supplies no baseline approval.

Parent and child bytecode isolation closes the earlier source-hash bypass. The
regression actually demonstrates that `-B` alone can consume valid-timestamp
poisoned bytecode, while a fresh prefix loads current source. Canonical helper
paths, selected-source/dependency locks, committed-byte checks, fresh child
directories and final identity checks preserve the selected execution boundary.
The public-schema consumer verifies actual OA/graph/source content and rejects
provider, partial-result and retrieval-time substitutions. Restart assertions
inspect the exact retained last record/query and cancelled invocation rather
than merely counting results or checking an intermediate cancellation state.
No new material false-pass or evidence-authority weakening was found.

**F-SLICE-01: closed at this candidate for the stated timeout/reset proof gap.**
The original finding in `CAP-04.S02.pre-qualification-review-01.md` remains
unchanged. `test_hanging_partial_read_times_out_and_retries_with_cleanup` drives
the actual broker deadline after partial bytes;
`test_connection_reset_after_partial_bytes_is_unavailable_and_retries` raises an
actual transport read error; and
`test_cancel_during_hanging_read_closes_stream_and_lease_without_retry` exercises
cancellation during the hanging read. Their assertions cover bounded attempts,
stream closure, zeroed synthetic secret leases, released provider lane, typed
failure and absence of successful body/cache/checkpoint publication. The
integrated protected-project test also retains timeout/reset failed pages and
unchanged preceding checkpoints across a new Core runtime. These checks close
the missing exception-path evidence without changing or reopening the original
task approval.

**F-SLICE-02: remains open.** Ordinary runtime latency/retry visibility and honest
duration guidance still require the planned linked correction and its own
regression/integration review. Benchmark timings cannot close that product gap.
The proposed separate protected diagnostics projection is compatible with the
Core-owned boundary only if it retains project/session/preview and inspection
authorization, bounded content-free measurements, strict typed decoding and the
exact native route allowlist. This is architectural preflight, not approval of
unimplemented correction code or a changed contract.

## Preserved limits and next gate

The integration uses real DPAPI, SQLCipher, durable workers and protected
publication, with synthetic HTTP and explicit ASGI/native-context substitution.
Its restart is a new runtime over retained state, not an OS process kill. Native
GUI, manual Save, TLS, accessibility and prior reference checks keep the exact
historical candidates and limitations recorded in the task reviews. No live
service, minimum-hardware, OS-cache-flush or installer-performance result is
claimed. Earlier broad-quality failures and Windows-token symlink skips remain
Wave obligations.

Calibration, immutable baseline review and a separate fresh benchmark remain
pending after the product correction. The final slice evidence matrix and
independent slice disposition are still required. No unchanged full-profile
replay is required by this bounded control review alone; fresh full affected
repository/profile and cross-capability qualification remain W2 exit work.
