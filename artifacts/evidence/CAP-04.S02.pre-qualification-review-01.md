# CAP-04.S02 independent slice pre-qualification review

Reviewer: `agent:w2-t03-review`. Date: 2026-09-26.
Observed HEAD: `035f11a3546658ed9c694acbae1c1a3ac4907724`.
Product candidate: `1e68cab433f194bf5d834bedc974bdac5a4f7cb6`.
The intervening commit contains task evidence and planning projections only;
the reviewed product inputs are unchanged. Authority is the approved
`planning/slice-plans/CAP-04/CAP-04.S02-open-scholarly-source-adapters.md`
sections 8, 10–15 and 17 at W2 approval
`c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`, with ADR-0027.

Disposition: **preflight only; slice approval remains pending**. This note
preserves two blocking slice-evidence findings. It does not change any approved
task disposition, task status, product authority or baseline. No producer suite
was rerun for this read-only comparison. Only this review note was written.

## Evidence boundaries

The three independently approved task manifests remain bound to their actual
candidates:

| Manifest | Candidate | Contribution |
|---|---|---|
| `artifacts/evidence/CAP-04.S02.T01.json` | `e5c57e9784d7f06957d9e5e850a916002110d87f` | Public schemas, strict identity/outcome/cursor/version invariants and generated contracts. |
| `artifacts/evidence/CAP-04.S02.T02.json` | `16b1524278b9e9ad9e52c322aa4b0fba0bb6fef0` | OpenAlex/Crossref mapping, protected publication, retry/cache/current authority, TLS and worker composition. |
| `artifacts/evidence/CAP-04.S02.T03.json` | `1e68cab433f194bf5d834bedc974bdac5a4f7cb6` | Graph/OA mapping, private native configuration, DPAPI/SQLCipher, current Intent, inspection and affected UI/control qualification. |

The five new qualification files were inspected as uncommitted inputs at this
HEAD: `tools/source_performance_check.py`,
`tests/connectors/test_source_performance_check.py`,
`tests/connectors/test_source_slice_runtime.py`,
`tests/connectors/source_public_handoff.py` and
`tests/connectors/source_rate_wait.py`. Their draft development results are not
committed qualification. Exact-candidate control review, committed integrated
execution, calibration, independent baseline review and fresh benchmark results
remain due. The pending baseline hash intentionally prevents qualification.

## Criterion-to-evidence map

| Requirement | Existing proof and planned completion | Status |
|---|---|---|
| Section 8: 429, Retry-After, 5xx, circuit recovery | `test_connector_broker.py` tests `test_retry_rate_limits_and_terminal_authentication`, `test_retry_after_beyond_budget_does_not_retry_early`, `test_advertised_delay_beyond_budget_returns_without_sleeping` and `test_shared_provider_lane_serializes_dispatch_and_recovers_circuit`; T03 connector run includes these. New integration adds actual worker 503/fresh-request recovery. | Covered by reviewed task proof; integrated run pending. |
| Section 8: timeout and connection reset | The broker has deadline and network-exception handlers, but existing tests do not drive these material branches. A manually constructed timeout result does not exercise them. | **Open F-SLICE-01.** |
| Section 8: malformed/missing/schema drift, cursor expiry, duplicate page | `test_connector_transport.py`, `test_scholarly_mapping.py`, `test_graph_oa_mapping.py`, `test_connector_contracts.py` and `test_connector_persistence.py` cover bounded parsing, typed failure, request/cursor identity, repeated cursor/record rejection, checkpoint CAS and idempotence. | Covered by reviewed task proof; retain exact test/candidate references. |
| Sections 8/10: cancellation, interruption, restart and authoritative recovery | `test_interrupted_completion_rolls_back_page_and_checkpoint_across_restart`, `test_queue_cancellation_at_publication_boundary_cannot_advance_checkpoint`, lost-acknowledgment and session/Intent fencing tests. New integrated run cancels in-flight transport, drains/closes, opens a new Core runtime, and requires a cancelled job, absent invocation observation and unchanged preceding checkpoint. | Existing failure proof plus fresh integrated closure pending. |
| Section 10: unit, contract and compatibility | T01 contract/schema proof and T02/T03 exact generation/client tests; strict unknown-field and cross-field checks retain their separate meanings. The new public consumer validates serialized schemas without Core/storage imports. | Covered; final input-impact and contract inventory must be recorded. |
| Sections 10/17: clean-state integrated vertical behavior | New `test_four_sources_cache_failure_denial_cancellation_and_restart` creates a clean protected project, configures synthetic local settings, runs all four adapters through normal Core/worker publication, confirms fresh-cache invocations and inspects retained records after runtime restart. DPAPI, SQLCipher and jobs are real; ASGI/native context and HTTP are explicit substitutes. | Fresh committed execution pending; no live service or installer claim. |
| Sections 10/13: downstream handoff | `source_public_handoff.py` consumes public JSON schema shapes, checks actual provider/source identities, versions, OA host/license, graph seed/direction and restrictive action rights; source inspection compares the exact projected last record/query and scientific digest. | Earlier false-pass preflight closed; fresh committed evidence pending. |
| Section 10: security, privacy and rights | Task proof covers current Intent/privacy/configuration/retention gates, alternate API/session denial, SSRF/TLS, bounded response parsing, echoed-secret redaction and lease cleanup. `test_connector_authority.py` and `test_graph_oa_broker.py` separate missing configuration, cache authority and unknown action rights. | Covered within stated task/principal limits; F-SLICE-01 adds exception-path evidence. |
| Section 10: accessibility/UI and approved reference | T03 built journey checks cover keyboard/focus, failed versus unconfirmed submissions, literal hostile text, paging and read-only inspection. Contrast/reflow samples cover two themes and three widths. Native GUI18 covers actual reopen, Escape/Cancel and focus. Approved reference 1.7 and semantic 1.5 remain distinct. | Compose exact historical proofs; no new screen-reader-session or fresh GUI claim inferred. |
| Sections 10/14: migration and retained history | Existing stores/migrations are reused. Protected idempotence/CAS/rollback and retained observation tests remain applicable; T02 compatibility checks exercise prior Intent fixtures and the actual upgrade path. Source/adapter versions are explicit. | No new product migration in the qualification increment; retain compatibility rationale. |
| Sections 10/17: architecture and clean build | Task architecture/build and packaged-sidecar evidence exists. Qualification-only additions need their registered quality/inventory checks; no new product dependency boundary is introduced. | Focused control checks pending; no unchanged full-profile replay justified by labels alone. |
| Section 11: batching, required fields, cache and rates | Task compile/mapping tests cover bounded batch/projection semantics. New benchmark measures three fresh processes with 100-record OpenAlex/Crossref/Semantic Scholar pages, singleton Unpaywall and fresh cache hits; separate concurrent broker probe uses actual clock/sleep. | Baseline review and fresh comparison pending. |
| Sections 11/12: estimated duration and operational observations | Retained pages contain response byte length, typed errors, rate/cache state, warnings and cursor fields. The supplied proof does not yet identify ordinary runtime latency/retry accounting or an exposed duration estimate. Benchmark samples are qualification observations only. | **Open F-SLICE-02.** |
| Sections 15/17: consolidated evidence and independent slice disposition | All task reviews exist. Assemble the final slice matrix, exact candidates/hashes, approved plan/reference/ADR identities, handoff, selected/deferred rationale and independent disposition after findings and qualification close. | Pending; not supplied by task approval or this preflight. |

## Blocking findings

### F-SLICE-01 — timeout/reset exception paths lack criterion-linked proof

Severity: material evidence gap. Blocking: **slice disposition**.
Criteria: section 8 explicitly requires timeout and connection reset, with
canonical state, retry/cancel, recovery and provenance expectations; section 10
requires the material failure matrix.

Concrete boundary:
`services/core-api/src/research_observatory_core/connectors/broker.py:274`
uses an actual deadline, with timeout classification at line 306 and network/
protocol/reset classification at line 308. In the reviewed test inventory,
`tests/connectors/test_connector_persistence.py:206` constructs a page with
`error="timeout"`; it proves persistence behavior for that page, not exception
classification, interrupted stream cleanup, lease cleanup or bounded retries.
The new integration's synthetic 503 and user cancellation do not substitute for
these exceptions. TLS certificate denial and response-close failure cover
different branches.

Smallest closure: add focused deterministic cases driving the real broker
exchange deadline and a connection/read reset, including a partial response
where relevant. Assert the typed failure, bounded attempt/cancellation behavior,
closed response/cleared secret lease and absence of successful publication or
checkpoint advancement. Compose the established protected publication proof
where appropriate; a broad service/search replay is unnecessary. Record fresh
committed results. If a new product defect is demonstrated, use the linked
correction route for the completed task; merely adding missing qualification
tests does not revoke task approval.

### F-SLICE-02 — operational observability and duration estimate are unmapped

Severity: material evidence gap pending targeted authority/runtime inspection.
Blocking: **slice disposition until mapped or corrected**.
Criteria: section 11 requires an exposed estimated search duration; section 12
requires per-provider requests, latency, response size, status/error class,
retries, rate state, cache hit, schema warning and cursor progress, while keeping
private terms and payloads out of ordinary diagnostics.

Concrete evidence reviewed: `ConnectorResultPage` in
`services/core-api/src/research_observatory_core/connectors/contracts.py`
retains several scientific/result fields. `connector_worker.py:274` projects
provider, operation, state, updated time and diagnostic code; its explicit log
call at line 492 is the bounded worker-unavailable event. Public inspection at
line 311 provides protected query and observation information.
`apps/desktop/src/app/SourceTestPane.tsx` and `SourceRequestHistory.tsx` expose
job/recovery and scientific inspection states. The submitted evidence has not
mapped a production latency/retry observation or duration-estimate path to the
remaining requirements. Workflow attempt count alone would not prove the
broker's distinct internal HTTP retry count.

This is **not yet a finding that a particular UI redesign is required**. First
inspect the approved Source Manager/page/workflow contracts and any existing
runtime diagnostics or Task Center path. Close with exact code/contract mapping
and a focused assertion if coverage already exists. If a completed-task defect
is demonstrated, use the linked correction route and preserve approved
experience/security authority. Do not substitute benchmark timings, invent an
estimate or treat diagnostics as scholarly provenance. Any estimate must state
its supported basis and limits rather than imply known live-provider latency.

## Preserved limits and remaining sequence

- Original manual native Save is historical at
  `a8955b86f75d628f2e23c7eac336de66c332b098`; final task native GUI/API evidence
  is at `1e68cab433f194bf5d834bedc974bdac5a4f7cb6`. The new control candidate
  does not relabel either run as fresh. Reference history/conformance at
  `36085017c1c4f92e3e08bd1c2587f1bb9296ee1c` remains ancestor-bound.
- The new runtime restart is new Core composition over retained state, not an
  OS process-kill test. Synthetic HTTP plus prior real local TLS establish
  different boundaries. Native GUI observations, browser doubles and protected
  API tests retain their actual roles; none alone proves the others.
- No live calls are authorized by ADR selection. Optional live smoke requires
  separately configured authority. Missing configuration is tested as denial,
  never relabeled live availability.
- Benchmark claims are limited to measured workstation hardware/OS, local
  synthetic page/cache work and a separate real-wait broker probe. No OS cache
  flush, minimum-hardware, live latency, installer performance or protected
  concurrent runtime claim is established. Retain all raw samples and the
  independently reviewed immutable baseline before a separate fresh comparison.
- The earlier 55 quality errors in 13 unchanged files and two Windows-token
  symlink skips remain explicit Wave qualification obligations. This note does
  not turn them into passes or demand unchanged full-profile task reruns.
- After focused finding closure, authenticate the exact committed controls,
  integrated execution and fresh benchmark; assemble the slice evidence bundle
  and obtain independent slice disposition before campaign advancement.
