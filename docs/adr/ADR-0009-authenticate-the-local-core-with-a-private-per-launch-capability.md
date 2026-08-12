---
id: ADR-0009
title: Authenticate the local Core with a private per-launch capability
status: Accepted
date: 2026-08-12
deciders:
  - CAP-01 repository-owner capability and slice-plan approval at b0e318137b2aa3ccf34f6a21a587419991d24b03
linked_tasks:
  - CAP-01.S04.T01
decision_scope: Local Core launch credential generation, private transfer, HTTP authentication, peer and authority validation, origin policy, rotation, and cleanup.
affected_paths:
  - apps/desktop/src-tauri/**
  - services/core-api/**
  - packages/contracts/core-api/**
  - docs/adr/**
  - quality-scope.json
  - tests/service/**
  - tools/core_sidecar_performance_check.py
supersedes: []
superseded_by: null
---

# ADR-0009: Authenticate the local Core with a private per-launch capability

## Context

The desktop and packaged Core communicate over a dynamically assigned loopback
HTTP endpoint. Loopback binding alone does not distinguish the desktop from
another process in the same user session, while placing a secret in process
arguments, environment variables, files, stdout, the handshake, or renderer
state would expose it through ordinary inspection or diagnostics. ADR-0008
delegated authenticated transport to CAP-01.S04 but did not select the
credential construction or transfer path. Its handshake nonce is intentionally
observable to the supervising native process and is suitable for process
binding, not as the private bearer credential.

## Candidates

1. Reuse the handshake nonce as a bearer token. This sends the credential over
   stdout after Core has started and makes an authentication secret part of a
   portable diagnostic contract.
2. Have the native host generate a per-launch 256-bit capability with the
   operating-system CSPRNG and send it through inherited stdin before the
   suspended child resumes. Keep it outside renderer and portable contracts.
3. Put a stable token in an environment variable, command argument, preferences
   file, or local credential store. This increases persistence and inspection
   surfaces and adds no benefit for a process-lifetime capability.
4. Replace local HTTP with a platform-specific named pipe immediately. This can
   provide a narrower kernel boundary but would prematurely replace the approved
   portable REST contract and require separately qualified platform adapters.

## Decision

Adopt candidate 2. The Tauri native host generates 32 random bytes for every
Core launch or retry through the operating-system CSPRNG. It creates Core
suspended, writes one exact `auth <64 lowercase hexadecimal bytes>\n` record to
the inherited control pipe, flushes it, attaches the process to its Job Object,
and only then resumes execution. The capability is never placed in arguments,
environment variables, files, stdout, the startup handshake, renderer state,
ordinary logs, crash diagnostics, or support data. Native buffers are zeroed
when no longer needed. Core parses the bounded record before binding, retains
only a SHA-256 digest, and rejects malformed or missing startup authentication.

Every HTTP request must originate from a numeric loopback peer, carry exactly
one canonical `Host: 127.0.0.1:<assigned-port>` value, omit `Origin`, and present
exactly one current `Authorization: Bearer <capability>` value. Proxy-header
interpretation is disabled. Comparison is constant-time over digests. Missing,
stale, duplicate, malformed, remote, cross-origin, and authority-confused
requests fail with fixed non-secret responses. The readiness probe follows the
same authenticated path; there is no unauthenticated health exception.

This decision refines the future-work boundary in ADR-0008 without changing its
process ownership, handshake, lifecycle serialization, or containment choices.
The handshake nonce remains a public per-process binding value. Hosted profiles
must replace this local capability adapter with their approved identity boundary
without changing the domain or API contracts.

## Consequences

An unrelated local process cannot call Core without the unpersisted launch
capability, and browser-originated requests are denied even if they learn the
ephemeral port. Restart invalidates the prior token. Because Core is deliberately
unreachable without native supervision, standalone HTTP development must use an
explicit test composition rather than a default unauthenticated server.

Rollback removes authenticated API activation and returns the renderer to the
bounded Core-unavailable state; it must not introduce an unauthenticated local
fallback. Changing entropy, transfer, allowed origins, authority rules, or
renderer exposure requires a superseding decision and security review.

## Verification

- Python unit and real-process tests for exact startup-record parsing, current,
  missing, malformed, stale, duplicate, cross-origin, wrong-authority, and remote
  requests, plus fixed secret-safe failures;
- locked Rust tests for operating-system token generation, rotation, canonical
  encoding, readiness authentication, zeroing ownership, and inherited-pipe
  transfer before resume;
- real packaged-sidecar supervision and performance lifecycles using the
  authenticated readiness path;
- ADR, architecture, Python quality, service, and security-focused checks.

## Task links

- `CAP-01.S04.T01`
