---
id: ADR-0044
title: Bind native parsing contracts to existing document authority
status: Proposed
date: 2026-10-07
deciders: []
linked_tasks:
  - CAP-05.S02.T02
decision_scope: Documentary mapping of native raw source receipts and their parent-authenticated Core port to accepted ADR-0028/0029 and version-1 staged IR; no new security, product scope, framework or release authority.
affected_paths:
  - packages/contracts/documents/README.md
  - packages/contracts/documents/generate_parser_schema.py
  - packages/contracts/documents/native-structure.v1.schema.json
  - services/core-api/src/research_observatory_core/ports/native_parsing.py
supersedes: []
superseded_by: null
---

# ADR-0044: Bind native parsing contracts to existing document authority

## Context

CAP-05.S02.T02 implements the already approved native JATS/TEI/XML/HTML outcome.
ADR-0028 owns isolation and the narrow broker; ADR-0029 owns source-preserving
staged structure and explicit human acceptance. The existing version-1 IR and
protected parsing port remain the downstream boundary.

Independent R01 found that four changed protected contract/port paths lacked a
changed indexed task-linked companion. Unchanged accepted ADRs govern the
implementation but do not satisfy the same-change-set documentary check. This
Proposed record supplies that trace; it is not an accepted architecture decision
and does not edit or amend the frozen Wave packet or accepted records.

## Candidates

1. Add physical byte offsets as another IR locator/version. That would alter the
   accepted consumer contract and create unnecessary migration semantics.
2. Retain qualified source elements and original byte anchors in a versioned
   protected raw artifact, then validate and project into the existing IR.
   Use this implementation detail within the approved native parsing task.

## Decision

The additive native raw schema records original digest/length/format, qualified
element names, decoded attributes, nearest source parents, original half-open
byte anchors, explicit/empty/implicit close kind and owned decoded-text runs.
Original byte coordinates and decoded Unicode-code-point coordinates remain
distinct. Each element projects to one named staged node/text projection; NFC
is local to that element so inline composition cannot fabricate child offsets.

`AuthenticatedNativeDelivery` is parent-owned authority separate from worker
JSON. The trusted runtime supplies actual producer/job/attempt and a hashed,
length/media-bound artifact receipt. Core validates exact source binding and
strict raw shape/relationships before building staged version-1 IR. The worker
parses originals; Core imports the port/value contract and has no canonical
writer, path, source key, fetch or acceptance grant through this interface.

Known bibliography targets are source observations. Missing targets produce
conservative unresolved output with raw targets/entry identities and warnings;
duplicate candidates remain ambiguous. Tables preserve source row/group ancestry
in the raw artifact while semantic IR cells use its existing direct-table-parent
rule. Unsupported elements/geometry retain source type, text and locations.
Figures retain observed captions without invented previews or enrichment.

## Consequences

Existing IR/request/result wire versions and consumers remain unchanged. The
new raw artifact is protected research data and supplies no producer, storage,
rights, session or researcher authority by itself. Failure/cancellation cannot
publish partial canonical structure. Existing encrypted storage and current
protected read/delivery decisions remain governed by their accepted contracts.
This documentation supplies no new runtime permission, scope or verification
waiver; actual isolation, persistence and Docling integration remain T03.

Rollback disables the failed native adapter without lowering isolation or
changing source format admission. Retain originals, protected raw/staged
artifacts, prior attempts and any independently accepted revisions. This
additive interface requires no database migration or accepted-head rewrite;
retry uses a new attempt under the existing current-authority checks.

## Verification

Preserve the exact failed R01 ADR diagnostic and disposition. The same claimed
base-to-corrected-candidate ADR check must pass, covering every originally
reported protected path. Fresh native/parser/protected-source, schema, affected
quality and architecture evidence qualifies the exact corrected candidate;
independent review replays this finding without rewriting the prior round.
Packaged real-principal/resource/offline/restart/recovery, integrated slice,
fresh Wave qualification and separate human release remain required.

## Task links

- `CAP-05.S02.T02`
