---
id: ADR-0019
title: Enforce project privacy through append-only local policy and preview-bound cleanup
status: Accepted
date: 2026-08-22
deciders:
  - W1 repository-owner pre-Wave approval at c5bbd97c0cdc665eecb973f5862478ef7be97752
linked_tasks:
  - CAP-02.S04.T03
decision_scope: Project-scoped privacy, egress-consent, telemetry, retention, object-access, cache-cleanup, disclosure, and content-safe audit boundaries for the W1 local profile.
affected_paths:
  - apps/desktop/src/**
  - apps/desktop/src-tauri/src/supervisor.rs
  - packages/contracts/core-api/**
  - packages/contracts/privacy/**
  - packages/contracts/README.md
  - packaging/build-inputs.json
  - services/core-api/src/research_observatory_core/**
  - docs/architecture/privacy-controls.md
  - docs/architecture/README.md
  - planning/backlog.yaml
  - tests/contracts/test_privacy_policy_contract.py
  - tests/security/test_privacy_controls.py
  - tools/core_api_contract.py
  - tools/desktop_app_check.py
  - artifacts/evidence/ui-change/CAP-02.S04.T03.json
supersedes: []
superseded_by: null
---

# ADR-0019: Enforce project privacy through append-only local policy and preview-bound cleanup

## Context

The approved W1 CAP-02.S04 packet requires offline and telemetry-off defaults,
provider-egress choices with informed consent, local retention preferences,
cache cleanup, and accurate best-effort secure-deletion disclosures. The W1
profile has no provider adapter or remote telemetry pipeline. Its Core already
owns project-session authority, append-only settings and provenance tables, and
a tri-state object-access port.

A renderer-only preference would not enforce the data boundary. Treating a
network setting as standing consent to transmit would also collapse project
policy and task-specific researcher authorization. Claiming secure physical
erasure after ordinary filesystem deletion would be false on common SSD,
journaled, snapshotted, backed-up, or hard-linked storage.

## Candidates

1. Store privacy preferences in renderer local storage. This is easy to render,
   but is not project-scoped canonical state and cannot govern Core access.
2. Treat an enabled provider preference as ongoing content-egress approval.
   This removes task-specific preview and is broader than the approved W1
   authority.
3. Persist complete project policy revisions append-only in Core, default to
   offline and telemetry off, require an exact current disclosure token before
   recording any non-offline preference, and translate policy to the existing
   object-access tri-state. Keep provider content at `require-confirmation` and
   require a separate task preview when such a capability is implemented.
4. Promise secure cache erasure after recursive deletion. This cannot be
   established portably and would mislead researchers.

## Decision

Adopt candidate 3 and explicitly reject candidate 4. Core owns seven
project-scoped settings as one append-only revision: network policy, remote-model
approval, telemetry mode, operational-log retention, document retention,
rebuildable-cache retention, and the current egress-consent version. Missing
settings project deterministic defaults without mutating the project: offline,
preview every task, telemetry off, fourteen-day operational-log retention,
project-lifetime documents, and thirty-day cache retention.

Changing the network preference does not transmit data. Offline denies
controlled egress. Metadata-only continues to deny document/object content.
Approved-provider content returns `require-confirmation`, never `allow`; a later
provider task must display its exact payload and obtain separate researcher
confirmation. Every non-offline policy revision requires the exact versioned
will-send/will-not-send acknowledgement. Returning offline removes that consent
version. Remote telemetry is not implemented; `local-diagnostics-only` remains
on-device and is separate from durable scholarly provenance.

Retention values are policy, not implicit destructive authority. Document
review intervals never automatically delete source documents. Operational-log
retention excludes the append-only lifecycle audit and scholarly provenance;
no current W1 project operational-log class is silently pruned. A future
maintenance executor must use this policy and an independently tested storage
classification rather than infer deletion rights from age alone.

Cache cleanup inventories only the project `cache` directory without following
redirects, returns bounded counts/bytes plus an expiring opaque preview, and
requires the exact project/token confirmation. Commit atomically renames the
active cache into project-local staging, creates a fresh cache, records a
content-free provenance hash, and rolls back before reporting failure when the
commit cannot complete. Staging removal is best effort and may be reported as
pending. Canonical state, objects, configuration, documents, logs, exports,
models, and shared caches are outside this action.

The disclosure says logical removal is performed but physical media erasure is
not guaranteed. SSD wear levelling and remapping, filesystem journals,
snapshots, backups, and hard links remain explicit limitations. Audit/log events
contain codes, revisions/hashes, counts, and trace identifiers only; they do not
contain project paths, document content, prompts, credentials, provider tokens,
or cache filenames.

## Consequences

Policy survives Core restart and project relocation through canonical project
state. Optimistic revision checks prevent stale forms from overwriting a newer
local decision. The native bridge strictly allowlists exact generated request
shapes, and the desktop can present the approved settings experience without
receiving a filesystem capability beyond the already governed project root.

W1 records but does not exercise provider eligibility or remote telemetry.
Provider registration, payload classification/redaction, rights checks,
retention compatibility, destination allowlisting, and exact per-task consent
remain future governed work. Automatic retention execution likewise remains
outside T03 until storage classes and recovery duties are implemented.

Rollback can stop exposing the settings UI while retaining append-only rows;
unknown later revisions fail closed to offline/unavailable rather than silently
widen access. Cache removal is irreversible at the application layer after its
atomic commit, so preview and confirmation cannot be bypassed.

## Verification

- strict portable profile and generated OpenAPI/client decoding;
- offline, telemetry-off, consent, optimistic-revision, restart, and malformed-policy tests;
- object-access allow/deny/require-confirmation boundary tests;
- cache preview, stale/racing inventory, exact confirmation, canonical exclusion,
  rollback, redirect, and physical-erasure disclosure tests;
- content/path-free provenance and diagnostic assertions;
- native request-whitelist denial tests for missing, extra, mismatched, and out-of-range fields;
- approved-reference desktop accessibility and will-send/will-not-send interaction checks;
- independent privacy review and the complete W1 exit security matrix.

## Task links

- `CAP-02.S04.T03`
