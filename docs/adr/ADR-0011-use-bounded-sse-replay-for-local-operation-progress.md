---
id: ADR-0011
title: Use bounded SSE replay for local operation progress
status: Accepted
date: 2026-08-12
deciders:
  - CAP-01 repository-owner capability and slice-plan approval at b0e318137b2aa3ccf34f6a21a587419991d24b03
linked_tasks:
  - CAP-01.S04.T02
decision_scope: Local operation status, pagination, cancellation, progress-event transport, replay, and backpressure boundary.
affected_paths:
  - services/core-api/**
  - packages/contracts/core-api/**
  - apps/desktop/src/**
  - apps/desktop/src-tauri/**
  - docs/adr/**
supersedes: []
superseded_by: null
---

# ADR-0011: Use bounded SSE replay for local operation progress

## Context

The portable API needs a progress seam before CAP-03 supplies durable workflow
state. Progress is server-to-client, ordered, and relatively low frequency.
WebSocket would add bidirectional session state and a second protocol without a
current collaboration or high-frequency requirement. A permanently open local
HTTP stream would also complicate native credential ownership and shutdown.

## Candidates

1. Poll only the operation-status endpoint.
2. Use a WebSocket for all progress and commands.
3. Use authenticated Server-Sent Events with monotonically increasing sequence
   IDs, bounded replay, explicit reconnection position, and REST cancellation.
4. Emit private Tauri events without a portable Core API contract.

## Decision

Adopt candidate 3. Core exposes typed operation status, deterministic
identity-ordered pagination, idempotent cancellation for cancellable states,
explicit terminal conflicts, and `text/event-stream` progress frames. Every
event carries operation identity, monotonic sequence, state, progress, terminal
disposition, and trace identity. The client reconnects using `afterSequence` and
rejects malformed, extra-field, mismatched-ID, or non-monotonic frames.

For the Windows local adapter, each authenticated request returns the currently
retained delta and closes. The generated client advances the last accepted
sequence before the next request. This bounded replay shape avoids an unbounded
native read, makes cancellation and app shutdown deterministic, and provides
backpressure by limiting retained events and response bytes. CAP-03 will replace
the current in-memory registry with durable workflow state without changing the
portable response or replay semantics.

WebSocket remains reserved for later presence or genuinely high-frequency
bidirectional collaboration. Commands continue through versioned REST endpoints;
the renderer never bypasses the native authenticated transport.

## Consequences

Temporary disconnection does not lose retained progress, and polling status
remains an authoritative reconciliation path. A client that falls behind the
future retention boundary must refresh status before resuming. The current task
intentionally exposes no public operation-creation route; deterministic fixtures
qualify the extension point without implementing CAP-03 workflow behavior.

Rollback can fall back to status polling while preserving cancellation and trace
semantics. Changing to WebSocket, allowing unbounded retention, or weakening
sequence validation requires a superseding decision.

## Verification

- service fixtures for pagination, status, cancellation, terminal conflict,
  missing identity, SSE replay, and trace-linked problem details;
- generated-client tests for monotonic frames, exact response shapes, cursor and
  operation identity bounds, and safe failure decoding;
- native bounded-response and route-allowlist tests;
- slice integration for restart, cancellation, recovery, security, and the
  <=100 ms warm local request budget.

## Task links

- `CAP-01.S04.T02`
