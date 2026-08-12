---
id: ADR-0008
title: Supervise the local Core process through a portable native boundary
status: Accepted
date: 2026-08-12
deciders:
  - CAP-01 repository-owner capability and slice-plan approval at b0e318137b2aa3ccf34f6a21a587419991d24b03
linked_tasks:
  - CAP-01.S03.T03
decision_scope: Local Core startup handshake, desktop process-supervision port, Windows process-tree containment, restart policy, and renderer recovery projection.
affected_paths:
  - apps/desktop/**
  - services/core-api/**
  - packages/contracts/core-api/**
  - docs/adr/**
  - Cargo.toml
  - Cargo.lock
  - packaging/build-inputs.json
  - tools/desktop_app_check.py
  - tests/desktop/**
  - tests/service/**
supersedes: []
superseded_by: null
---

# ADR-0008: Supervise the local Core process through a portable native boundary

## Context

The Windows desktop must own exactly one compatible local Core process, wait for
application readiness rather than a listening socket, stop the complete process
tree on shutdown, diagnose crashes without exposing research content or secrets,
and prevent an unbounded restart loop. The approved CAP-01.S03 plan also requires
the supervision contract to remain replaceable by later macOS and Linux adapters.

## Candidates

1. Use a broad renderer-accessible shell/sidecar plugin. This supplies convenient
   process events but expands renderer permissions and couples policy to a
   framework-specific command surface.
2. Put a narrow process-supervisor port in the native Rust host, with a Windows
   Job Object adapter and exact renderer state commands. Core emits a strict
   inherited-pipe handshake and accepts graceful shutdown only from inherited
   stdin.
3. Install Core as a machine service or require users to run it separately. This
   weakens application ownership, complicates local privacy and upgrades, and
   conflicts with the no-administration product requirement.

## Decision

Adopt candidate 2. The Rust supervisor is the process authority. It accepts only
the canonical target-triple executable, clears the inherited environment, sets a
fixed local profile, creates the process suspended and without a terminal window,
assigns it to a Windows Job Object configured with `KILL_ON_JOB_CLOSE`, and only
then resumes its primary thread. This closes the child-escape window before Core
or any descendant can execute. A single strict JSON
handshake binds protocol, build, PID, numeric-loopback endpoint, nonce,
capabilities, database-compatibility range, and a stable startup diagnostic. The
supervisor then requires the exact versioned `/readyz` response.

Potentially blocking start, retry, and stop commands run on Tauri's async runtime
through blocking-worker dispatch rather than its main thread. Lifecycle operations
are serialized: a stopping process cannot be replaced until graceful or forced
tree termination finishes. Concurrent start requests return the same active
process. Graceful shutdown uses the inherited control pipe and has a five-second
force-termination boundary.
Unexpected exit is detected through the owned child handle. At most three start
attempts are allowed during an application lifetime; exhaustion enters a distinct
recovery-required state. Native output is drained into a bounded sequence of
opaque codes only; state diagnostics are stored separately so late log collection
cannot change the renderer-visible state. The renderer can start, poll, retry, stop, and request redacted
diagnostics through application-defined commands, but it receives no endpoint,
nonce, PID, raw process output, path, environment, or ambient shell permission.

The portable supervisor interface is process-state and policy oriented. CAP-14
may replace the Windows Job Object adapter with a platform process-group adapter
without changing the handshake or renderer projection. CAP-01.S04 owns use of the
nonce for authenticated API transport; this decision does not expose the endpoint
to renderer code prematurely.

## Consequences

The desktop owns startup, readiness, crash recovery, and shutdown without a
system Python installation or terminal. Windows is the release-authoritative
adapter for the current wave. The native host adds small pinned Serde and
Windows-API dependencies, while later platforms require separately qualified
containment implementations.

Rollback removes the native commands and returns the application to the bounded
supervisor-unavailable UI; it must never leave a separately managed Core process
behind. Changing protocol compatibility, restart policy, renderer exposure, or
containment semantics requires a superseding decision and migration tests.

## Verification

- strict Python handshake schema and real supervised-process shutdown test;
- locked Rust unit tests for handshake, readiness, diagnostic bounds, and state;
- real packaged-sidecar supervision check for duplicate start, async cancellation,
  graceful stop, crash observation, PID replacement, and restart-budget exhaustion;
- deterministic native fixtures for port-zero and malformed handshakes, early
  exit, readiness timeout, immediate descendant containment, hung shutdown,
  serialized stop/retry, and Job-handle-close cleanup;
- focused renderer tests for exact native decoding, recovery, cancellation, and
  secret-safe diagnostics;
- architecture, ADR, contract-inventory, and affected desktop application checks.

## Task links

- `CAP-01.S03.T03`
