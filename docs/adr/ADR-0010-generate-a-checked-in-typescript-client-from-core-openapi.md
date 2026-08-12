---
id: ADR-0010
title: Generate a checked-in TypeScript client from Core OpenAPI
status: Accepted
date: 2026-08-12
deciders:
  - CAP-01 repository-owner capability and slice-plan approval at b0e318137b2aa3ccf34f6a21a587419991d24b03
linked_tasks:
  - CAP-01.S04.T02
decision_scope: OpenAPI authority, TypeScript client generation, checked-in artifact policy, compatibility evaluation, and native authenticated transport.
affected_paths:
  - services/core-api/**
  - packages/contracts/**
  - apps/desktop/src/**
  - apps/desktop/src-tauri/**
  - tools/core_api_contract.py
  - quality-scope.json
  - docs/adr/**
supersedes: []
superseded_by: null
---

# ADR-0010: Generate a checked-in TypeScript client from Core OpenAPI

## Context

The desktop must consume the same portable HTTP contract that later deployment
profiles use, while the local per-launch credential remains confined to native
code. Hand-maintained request and response types can drift from FastAPI. A
browser-oriented generator or direct renderer HTTP client would either add a
network-dependent build step or expose the local credential and endpoint to the
renderer.

## Candidates

1. Hand-maintain TypeScript interfaces and calls beside the React application.
2. Generate a client during every developer build with a downloaded external
   generator and do not commit the output.
3. Deterministically generate and commit OpenAPI 3.1 plus a transport-neutral
   TypeScript client, bind the output to the exact OpenAPI SHA-256, and fail a
   local/CI check when either artifact drifts.
4. Let the renderer call authenticated loopback HTTP directly.

## Decision

Adopt candidate 3. FastAPI response models and route declarations produce the
canonical sorted `packages/contracts/core-api/openapi.json`. The repository
generator derives TypeScript response types and the complete operation-ID union,
emits strict boundary decoders and typed client methods, records its version and
the exact OpenAPI SHA-256, and writes the checked-in
`packages/contracts/core-api/generated.ts`. `--check` regenerates both artifacts
in memory and rejects any byte drift. Generation uses the frozen repository
Python environment and does not download code or schemas.

The generated client depends only on a small `CoreApiTransport` port. Local
desktop production consumes the same route and response contract through its
native Tauri boundary. Native code selects the owned loopback endpoint, attaches
the private launch credential and a fresh trace ID, allows only generated
method/path shapes, bounds response bytes, strips all but safe headers, and
returns no credential or endpoint to React. A hosted adapter may later implement
the transport port with its approved identity system.

API compatibility is explicit SemVer. This client is `1.0.0`; Core declares its
API version and an inclusive-minimum/exclusive-maximum supported client range.
The native supervisor validates `/runtime/version` before publishing readiness,
so the desktop fails closed to the existing functional recovery surface when
service identity, schema identity, major version, or range is incompatible.
RFC 9457 problem
details cross the boundary only after exact decoding and preserve one opaque
trace ID plus safe remediation.

## Consequences

Contract changes require regeneration and review of a visible generated diff.
Client compilation, exact OpenAPI bytes, runtime decoders, and native path
allowlisting jointly detect drift. The committed output makes clean and offline
builds reproducible. The native adapter is slightly more code than direct fetch,
but it preserves the credential boundary selected by ADR-0009.

Rollback may remove operations from both the service and generated artifacts,
but must leave incompatible pairs rejected. It must not restore a hand-written
renderer client or expose the launch credential.

## Verification

- exact OpenAPI and generated-client regeneration checks;
- TypeScript compilation plus decoder, compatibility, problem, pagination, and
  event-stream tests;
- Rust method/path, header-injection, response-size, trace-correlation, and
  authenticated real-process tests;
- service tests for served response/OpenAPI equality and safe problem details.

## Task links

- `CAP-01.S04.T02`
