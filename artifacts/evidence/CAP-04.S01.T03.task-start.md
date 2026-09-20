# CAP-04.S01.T03 — idempotent import commits and manifests

Claim base: `b55c1285b33d17fca7b8ef37ed8ce16d1c83610a`.
Authority: approved W2 packet `c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`,
CAP-04.S01 sections 2–8, 9.3 and 10–15; ADR-0013/0024/0025/0027.
Dependency CAP-04.S01.T02 is DONE with independent R01 approval.

## Material acceptance and proof

| Boundary | Required outcome and planned proof |
|---|---|
| AC1 / scientific identity | Versioned identity binds source, parser, immutable mapping profile/revision, ordered selected keys and complete effective-draft digest. Pure one-pass tests distinguish changed corrections, inclusion, rights, project and parsing settings; preview identity is not scientific authority. |
| Source identity | Re-import across previews reuses the project/source-digest/record-key assertion and existing Core UUIDv7 record. Changed source bytes create retained assertions, not destructive replacements or DOI-based Work merges. Test same-file/different-preview and changed-file comparison. |
| Replay vs request | Project-unique scientific identity returns the existing manifest after current authorization. Changed command under a reused request ID conflicts. Test restart/reply-loss replay and changed decision/rights manifests with raw values unchanged. |
| Atomicity / provenance | Canonical records, immutable manifest membership/decisions, provenance/outbox/dependencies and accepted workflow output commit in one existing protected database transaction. Inject failure after material writes; no partial canonical import. Large membership is paged, not a truncated or oversized event. |
| Current authority | Validate selected project/session, exact current draft, accepted parse, all effective rights, worker configuration/lease/cancellation at final transaction and on replay. Test stale, off-page denied, cancelled, substituted project and expired authority. Hash equality is not authorization. |
| AC2 / real boundary | Real repository/worker/API path; ordinary process restart and cancellation/recovery. Narrow Windows protected-principal and built renderer/native wiring proofs where changed; preserve doubles and packaging limits explicitly. |
| AC3 / compatibility | Capture exact v12 predecessor before additive migration; encrypted backup, rollback failpoints and reopen preserve old previews/summaries. Update strict contracts, generated client, packaging inventory, fixtures and architecture only where affected. |
| Governed journey | UI reference 1.7: clear pre-commit summary, explicit action, durable status and navigable manifest; report source records awaiting reconciliation, safe next/back/return and late-response handling. CAP-04.S03 owns Work/Version reconciliation. |

## Sequence and boundaries

Start with identity characterization tests, then protected storage and transaction
tests, durable execution/API, and final wizard/manifest integration. Reuse the
existing Core ports, UUID minting, provenance and durable jobs; no import-only
database, new identity store, credentials or remote service. Changed-file
comparison uses an explicit predecessor, never a filename guess. Existing
mapping-profile identity stays immutable; do not alter earlier draft hashes.

The prior read-only adversarial preflight identified the same-connection commit
requirement, 64-input event bound, separate request/scientific identity, full
current-rights recheck and exact predecessor fixture. These are included above.
No mandatory new human gate identified. Full slice integration, reviewed 100k
performance baseline and frozen supervised journey remain slice/W2 qualification;
do not rerun unrelated completed W1 profiles.

## First publication review — missed acceptance rows

- Comparison reads an earlier manifest's historical decisions. Its current
  default and per-record store/inspect authority must still permit that use,
  including inside the final publication transaction. Add revoked-predecessor
  regression; denial must leave canonical counts unchanged.
- A generic accepted workflow output is not necessarily an import manifest.
  Replay must authenticate a sealed manifest and its complete scientific input
  identity, while permitting a valid reused manifest from an earlier request.
  Add actual queue-completed parser-receipt substitution regression.

Immediate root causes: the comparison path treated historical accepted metadata
as sufficient authority; replay reused the generic queue receipt check without
the import-specific semantic check. Preserve the first adverse disposition.
