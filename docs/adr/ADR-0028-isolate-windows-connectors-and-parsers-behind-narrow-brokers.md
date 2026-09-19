---
id: ADR-0028
title: Isolate Windows connectors and parsers behind narrow brokers
status: Accepted
date: 2026-09-13
deciders:
  - human:repository-owner; W2 design/architecture approval recorded 2026-09-19
linked_tasks:
  - CAP-04.S05.T01
  - CAP-04.S05.T02
  - CAP-04.S05.T03
  - CAP-05.S02.T01
  - CAP-05.S02.T03
decision_scope: W2 Windows x64 connector/parser process authority, broker IPC, plugin trust, resource limits and failure behavior; no replacement of Core workflow ownership.
affected_paths:
  - workers/**
  - services/core-api/src/research_observatory_core/connectors/**
  - services/core-api/src/research_observatory_core/parsing/**
  - packages/contracts/connectors/**
  - packages/contracts/documents/**
supersedes: []
superseded_by: null
---

# ADR-0028: Isolate Windows connectors and parsers behind narrow brokers

## Context

Systems Design 16.4/17 requires plugins outside Core/renderer, scoped secret
delivery, destination enforcement and isolated parsing. ADR-0025 supplies durable
jobs and staged outputs but an ordinary same-user child is not a sandbox.
W2 must contain malicious connector code and hostile document processing without
granting access to project databases, vaults, other jobs or unrestricted network.
CAP-04.S02 first supplies reviewed first-party provider operations and bounded
data contracts; it does not enable third-party code loading. The hostile-plugin
execution boundary is delivered in CAP-04.S05 before any SDK plugin is enabled.
CAP-05.S02.T03 explicitly depends on CAP-04.S05.T02, so parsing cannot claim that
later boundary early. No backward dependency from first-party metadata contracts
to the SDK is introduced.

[Microsoft's AppContainer launch guidance](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)
describes unpackaged process creation with a capability-scoped token and the
LPAC opt-out from All Application Packages. This supports the proposed mechanism;
it is not evidence that this application's Python/native dependencies run inside it.

## Candidates

1. Ordinary child plus Job Object and application allowlists: simple crash/resource
   containment, but inherited user authority fails the hostile-code boundary.
2. Windows Less Privileged AppContainer (LPAC), no direct network, explicit
   read-only runtime/assets, and narrow parent brokers: native local isolation
   without a VM, with real packaging/ACL compatibility work to qualify.
3. Separate VM/container service: stronger additional separation, but introduces
   virtualization/installation prerequisites and substantial local resource and
   operational cost for this prototype. Retain as a future alternative if native
   isolation is demonstrated infeasible; not an automatic fallback.

## Decision

Select candidate 2 under the recorded [W2 design/architecture approval](../../artifacts/evidence/W2.design-architecture-owner-approval-01.md).
Complete W2 packet approval remains required before implementation; the sandbox
is not already supplied or proven by W1.

- Launch a dedicated worker image, not a Core process with reduced API exposure.
  Apply LPAC before untrusted code executes; grant no network, registry/COM,
  broad filesystem or inherited user-profile capability. Explicit read/execute
  ACLs cover only the signed runtime and selected read-only assets. No writable
  project, vault, ordinary profile or plaintext temporary directory is granted.
  Treat writable AppContainer-profile locations as a boundary to deny and test,
  not implicitly safe scratch space.
- Core creates job-specific authority and private IPC with an explicit inherited
  handle allowlist. Workers receive bounded input streams, opaque job/input IDs
  and permitted operations, never filesystem paths, database/key handles or
  source credentials. Output is bounded framed data on the same private channel;
  Core validates schema, job binding, limits and provenance before encrypted staging.
  There is no generic shell, arbitrary URL, arbitrary file or unrestricted RPC call.
- Connectors request typed provider operations through the ADR-0027 broker.
  The broker rechecks active project policy, declared permissions, endpoint and
  size/time budgets, redirect destinations and resolved addresses. Deny loopback,
  link-local/private destinations and credential forwarding across origins.
  A malicious connector cannot turn a permitted provider call into arbitrary egress.
  Parser jobs have no network broker operations at all.
- Use a kill-on-close Job Object for descendant lifetime/resource accounting,
  not as the security boundary. Default to one parser job; versioned launch
  profiles bound input/output size, CPU concurrency, committed memory and wall
  time. A timeout, malformed output or killed worker produces a typed failure;
  it never commits a successful partial document or silently retries without limit.
- Reuse ADR-0025 cancellation/checkpoints and fencing. Parent death kills the
  owned process tree; restart reconciles encrypted staged outputs and releases
  test/job-owned resources. Never terminate an unrelated process by name.
- W2 connector SDK manifests contain API version, fixed entry point, package/file
  digests, permitted operations/domains, resource profile and publisher key ID.
  Verify a detached Ed25519 signature over exact manifest bytes, then file hashes,
  against explicit local trusted keys before execution. No self-trust from a key
  bundled with a plugin. Built-ins ship in the signed application inventory;
  third-party publisher trust and per-project permissions require an explicit
  researcher action. Updated permissions require renewed consent. No marketplace,
  online key discovery, TUF service or arbitrary install script is introduced.

Qualify the packaged worker, LPAC token, denied ambient reads/writes and broker
denials early in **CAP-04.S05.T02**, then reuse that exact boundary for
document inspection in **CAP-05.S01.T01** and parsing in **CAP-05.S02.T03**.
Use private inherited anonymous pipes with length-prefixed UTF-8 JSON control
frames (1 MiB maximum) and separately bounded binary input/output frames. Protocol
version, job nonce, sequence and operation are mandatory; reject unknown/oversize/
duplicate frames and mismatched jobs before processing. No listening RPC server.
Connector capabilities are `lookup`, `search`, `references`, `citations`,
`open-access-locations` and `repository-metadata`; unsupported operations deny.
The last operation is a schema-validated public metadata endpoint, not arbitrary
HTTP. Downloads are a separate Core acquisition operation with current rights.
Limit connectors to 256 MiB committed memory, one active job per project and
60 seconds/job; provider requests have their stricter ADR-0027 budget. Exact
destination scheme/host/port/path templates are signed manifest data; wildcards,
user-info, file/data URLs and DNS-rebinding/redirect escapes deny. Secrets never
enter IPC. Package updates bind an exact digest and explicit enable decision even
when permissions are unchanged; increased permissions require renewed consent.

If LPAC or mandatory no-plaintext-write behavior cannot work,
fail closed and present evidence for a revised decision. Do not fall back to an
ordinary same-user process or silently give broader capabilities.

## Consequences

The security boundary is more work than merely adding subprocess calls, but it
is required product functionality, not optional control-system polish. Core's
existing workflow and encrypted storage remain authority. Worker dependency
locks are separate from Core; payload contracts remain platform-neutral.

Local installation must declare any test-owned profile/ACL setup and cleanup;
this planning record does not authorize changing existing user security settings.
No real projects, vaults or credentials are needed for adversarial proof. Runtime
rollback disables the failed adapter and retains original/staged ciphertext;
it does not downgrade isolation. W6 supplies separately qualified platform adapters.
OS/kernel compromise, administrator access and compromised trusted Core remain
outside this worker boundary and must not be claimed as protected.

## Verification

Use a packaged adversarial worker and synthetic sentinel files/credentials:
deny unrelated read/write, other-job IPC, direct internet/loopback, environment
credential access, arbitrary broker URLs, permission escalation, manifest/file
tamper and unsigned/untrusted plugins. Verify actual LPAC token/capabilities,
resource exhaustion, handle inheritance, parent death, cancellation and restart.
Prove CPU PDF conversion without ambient temporary writes or asset downloads.
Mocks/manifest inspection alone cannot qualify the sandbox. Retained W1 scanner
and worker-qualification gaps must be diagnosed for this affected boundary,
not inherited as passing results.

## Task links

- `CAP-04.S05.T01`
- `CAP-04.S05.T02`
- `CAP-04.S05.T03`
- `CAP-05.S02.T01`
- `CAP-05.S02.T03`
