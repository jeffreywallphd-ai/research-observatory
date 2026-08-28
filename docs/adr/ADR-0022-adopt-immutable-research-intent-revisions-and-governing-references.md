---
id: ADR-0022
title: Adopt immutable research intent revisions and governing references
status: Accepted
date: 2026-08-28
deciders:
  - W1 repository-owner pre-Wave approval at 594e63be501711d67d17a4aef176bb9b6a8748be
linked_tasks:
  - CAP-03.S02.T01
decision_scope: Research intent revision identity, immutable predecessor lineage, decision state, human acceptance, and downstream governing-version references.
affected_paths:
  - packages/contracts/intent/**
  - packages/contracts/package.json
  - packages/contracts/tsconfig.json
  - packages/contracts/README.md
  - services/core-api/src/research_observatory_core/research_intent_contracts.py
  - services/core-api/README.md
  - services/core-api/packaging/sidecar-build.json
  - tests/contracts/test_research_intent_contracts.py
  - tests/packaging/test_core_sidecar_package.py
  - packaging/build-inputs.json
  - quality-scope.json
  - docs/architecture/research-intent-contracts.md
  - docs/architecture/README.md
supersedes: []
superseded_by: null
---

# ADR-0022: Adopt immutable research intent revisions and governing references

## Context

Every consequential research operation must be attributable to the researcher's
effective purpose, scope, evidence standard, autonomy, and stopping rule. A
mutable project-settings row cannot prove which intent governed an earlier
search, interpretation, model invocation, or claim. Embedding prior revisions
inside each new document would duplicate authority and make partial replacement
or truncation difficult to detect.

The W1 packet selects a versioned Research Intent Contract. T01 owns its
portable contract; persistence, current-pointer transactions, change-impact UI,
and service enforcement remain in T02, T03, and their downstream slices.

## Candidates

1. Keep one mutable intent document and retain only an update timestamp.
2. Copy the complete prior intent history into each new document.
3. Store immutable revision documents linked to the immediately prior revision,
   and let downstream objects carry one compact accepted-revision reference.

## Decision

Adopt candidate 3. Every revision has stable UUIDv7 intent, revision, and
project identities; an exact contract version; a bounded immutable content-hash
identity; creation actor/time; status; and a researcher-authored revision
rationale. Revision one has no parent. Each later revision names exactly the
immediately prior revision number, UUIDv7 identity, and content hash. The
predecessor is never embedded or overwritten.

Draft and proposed revisions have no decision. Accepted, rejected, and
superseded revision records carry a matching terminal decision with actor,
time, and rationale. Only a complete revision accepted by a human can produce a
`research-observatory-research-intent-reference`. That reference contains the
intent identity, exact revision identity and number, contract version, and
content hash required by downstream provenance. Drafts and other nonaccepted
states cannot be projected as governing.

The Draft 2020-12 schema is the language-neutral authority. A deterministic,
newline-portable generator embeds its canonical SHA-256 and emits checked-in
TypeScript and Python validators. Both reject unknown or unsafe object fields,
nonportable identities, invalid lineage and decision state, then return owned,
deeply immutable snapshots.

## Consequences

T02 must persist revisions append-only and update the single accepted current
pointer atomically without rewriting history. T03 and later services must accept
the compact governing reference rather than a mutable project setting or a
private persistence object. The content hash is the identity assigned by the
authoritative content boundary; it is not a self-referential hash calculated
from a field that contains itself.

This first contract version has no prior research-intent schema to migrate.
Future additive or breaking evolution must retain the contract version and
checked-in fixtures, and breaking changes require the domain compatibility and
ADR process.

## Verification

- Draft 2020-12 validation and deterministic TypeScript/Python generation;
- accepted revision and accepted-reference fixtures;
- valid revision-one and immediate revision-two lineage;
- denial of skipped, self-referential, unknown-field, and unsafe-key inputs;
- denial of nonhuman acceptance and incomplete accepted revisions;
- immutable owned snapshots and exact downstream reference projection; and
- Core sidecar/build-schema inventory coverage.

## Task links

- `CAP-03.S02.T01`
