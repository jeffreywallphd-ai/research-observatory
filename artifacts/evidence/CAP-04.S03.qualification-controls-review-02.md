# CAP-04.S03 qualification-controls independent review 02

- Reviewer: `agent:/root/w2_c02_review`, independent of the implementation owner.
- Candidate: `346bb2b1086902d2067947bebbf0128c49bc8560`.
- Predecessor: `d1e43e9303c80c0713863939184a5fb255c234cf`.
- Disposition: **approved for nonqualifying calibration; both prior findings closed**.
- Scope: incremental qualification-control review. This is not a baseline,
  performance, product-task, slice, integration, or release disposition.

Authority remains the approved CAP-04.S03 sections 10–11 and 15–17 and project
automation guide section 8.3. The five-path incremental diff contains the
retained adverse review, the remediation note, producer/test changes, and four
additional sample-validation conditions. It changes no product, matcher, gold
fixture, rights policy, approved reference or release criterion.

The prior review at
`artifacts/evidence/CAP-04.S03.qualification-controls-review-01.md` remains
byte-preserved, SHA-256
`99e007fff4fd22d41065afb81426e652dd18a9e3653c989324a5749e3c3d9f9e`.
Its findings and limitations are retained rather than replaced by this note.

## Finding closure

**F-S03-PERF-01 — closed.** `_run_batch` now installs the warm feature observer
before preparation and scheduling and keeps it installed through the terminal
status read. This covers computation in the schedule response and the actual
background worker. The regression forces a real feature-preparation call during
enqueue and now requires rejection. The independent rerun passed. Review of
the call site confirms the protected producer uses this helper for both phases.
Cold/warm request, job and set identities must still differ.

The added terminal loop waits through runnable/running states and rejects a
still-nonterminal job after its deadline. A focused reviewer probe exercised
runnable -> running -> succeeded and a nonterminal timeout. Both behaved as
intended. Synchronous calls are not interrupted by that polling deadline; the
existing child-process timeout and every-sample elapsed-time budget remain the
outer bounds. No worker admission or source-authority substitution was added.

**F-S03-PERF-02 — closed.** Each measured API page must bind the requested set,
request and cursor. Every strict `CandidateExplanation` is content-hashed.
After timed requests and project close, protected database inspection obtains
the exact cold/warm set pair hashes and verifies the complete stored ordinal
inventory. Cold/warm inventories must match. `_verify_page_digests` rejects
duplicate expected hashes, gaps, repeats, substitutions, wrong ordering and
incomplete coverage; the observed page hashes must equal the durable hashes at
every ordinal. The independent rerun of the unchanged-count repeated-pair and
substituted-pair regressions passed. Call-site inspection confirms those hashes
come from the actual API items and actual selected durable set revisions.

The extra strict decoding and database inspection occur outside measured page
request times. The exported sample retains a content-free digest and equality
result. The consumer now requires a true equality result and a correctly formed
digest. Focused negative probes rejected false equality and malformed digests.

## Verification and evidence limits

The reviewer independently executed:

```text
PYTHONPATH=services/core-api/src
.venv/Scripts/python.exe -B -s -m unittest -v tests.reconciliation.test_performance_check
```

All eight focused tests passed; unittest reported 0.066 seconds. The additional
reviewer polling/consumer probes are retained at
`artifacts/tmp/CAP-04.S03.qualification-controls-review-probes-03.log`, SHA-256
`d6465fa873eddd47694685f6b26bca2dbec0d8be8a25ea82b478870c588d4013`.
These are control tests, not a substitute for actual protected execution.

The owner's retained working-candidate smoke was read and authenticated at
`artifacts/tmp/CAP-04.S03.workload-remedy-smoke-03.log`, SHA-256
`d9e7fa3c3ab92b5a7e22e3a1a0336d8c3308611633d40e95728a93cfad487d09`.
It reports the frozen kernel counts, 203 protected records/103 candidates,
distinct cold/warm jobs, zero observed warm computations, equal candidate
content, two complete pages and zero measured provider dispatch. This is one
nonqualifying smoke without peak-memory measurement; it is not a fresh
three-process calibration or post-baseline qualification. The reviewer did not
rerun an expensive protected workload or unrelated suites.

The source/installed-input guards, fresh bytecode settings, baseline separation,
absolute ceilings and per-sample regression rules are unchanged. The R01
baseline-provenance validation limitation remains explicit: before independently
approving baseline bytes, authenticate the original nonqualifying calibration
report, all three raw sample/log hashes, hardware, tool commit/bytes, source and
runtime/dependency identities, and agreement between samples and retained
metrics. No unpublished baseline or measured performance result is approved
here. Live-provider, installer, native-renderer, minimum-hardware and researcher
agreement/correction-rate claims remain outside this benchmark.

No additional material blocker was found in this incremental scope. The owner
may proceed to nonqualifying three-process calibration, then separate immutable
baseline review and fresh qualifying measurement. HEAD and reviewed inputs
remained fixed throughout this review; this append-only note is the reviewer's
only tracked-path addition. No taskctl, Git or product mutation was performed.
