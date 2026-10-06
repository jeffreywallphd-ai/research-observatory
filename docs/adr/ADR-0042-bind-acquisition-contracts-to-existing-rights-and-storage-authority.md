---
id: ADR-0042
title: Bind acquisition contracts to existing rights and storage authority
status: Proposed
date: 2026-10-06
deciders: []
linked_tasks:
  - CAP-05.S01.T02
decision_scope: Documentary association of CAP-05.S01.T02's exact-copy acquisition schemas, Core ports and additive v24 storage/recovery contracts with already accepted rights, privacy, isolation, identity and migration authority; no new security, execution or release authority.
affected_paths:
  - packages/contracts/README.md
  - packages/contracts/documents/acquisition-*.v1.schema.json
  - packages/contracts/storage/sqlite-migration-recovery-v23.snapshot.json
  - packages/contracts/storage/sqlite-migration-recovery.schema.json
  - packages/contracts/storage/sqlite-profile.schema.json
  - packages/contracts/storage/sqlite-profile.v1.json
  - services/core-api/src/research_observatory_core/ports/acquisition.py
supersedes: []
superseded_by: null
---

# ADR-0042: Bind acquisition contracts to existing rights and storage authority

## Context

The approved CAP-05.S01.T02 task implements permitted OA location selection and
download. ADR-0029 already selects bounded acquisition, exact source/license and
checksum retention, encrypted staging, inspection and safe restart. ADR-0019
requires current project privacy and task confirmation; ADR-0027 separates source
observations from permissions and credentials; ADR-0028 supplies the signed LPAC
inspection boundary. Existing canonical identity/provenance and SQLite migration
contracts remain authoritative.

Portable location, selection and receipt schemas plus persistence/staging ports
make these implementation boundaries explicit. Additive schema v24 requires
current profile/recovery metadata and the immutable previous v23 recovery snapshot.
The unchanged protected-path checker requires a changed, indexed task-linked
record for these contracts. This Proposed companion records their implementation
remit, like ADR-0038; it does not amend the frozen W2 packet, accept a new decision,
authorize egress or qualify release. Accepted predecessors remain unchanged.

## Candidates

1. Reuse source-level rights for every location and leave acquisition authority
   implicit in adapter calls. This offers fewer types but cannot distinguish
   alternative copies or prove exact confirmed authority. Reject under the
   approved per-copy rights and portable-boundary decisions.
2. Publish exact-copy observation, selection and receipt contracts, use typed Core
   ports and add immutable relational projections under existing canonical
   authority. This adds explicit schema and compatibility proof while retaining
   the accepted architecture. Select as implementation detail.

## Decision

Location values bind the retained assertion, source revision/address/ordinal,
provider field key, URL, license and version with an exact digest. Observations
are never grants. Selection binds exact Work/version revisions, the location and
its digest, an optional expected checksum and bounded explicit redirect hosts.
The receipt records actual bytes/checksum, selected source, current policy and
confirmation digests, bounded attempts/redirects and transfer time; missing
source observations or expected checksums remain missing.

Acquisition orchestration consumes persistence and inspected-staging protocols.
The existing document attachment adapter owns current association, rights and
SQL transactions, composed by main. No database connection enters the business
port. Durable admission and terminal outcomes reuse canonical workflow revisions
and atomic provenance/outbox/dependencies; these facts are not dispatch consent.

Schema v24 adds location, attempt, result and candidate-source projections without
changing earlier DDL/fingerprints. Current profile/recovery contracts describe
that version; the v23 snapshot preserves exact earlier interpretation. No parser,
cryptographic format, plaintext spool, broader worker capability, new external
service, range concatenation or governed experience is introduced.

## Consequences

Windows x64 local/lab remains the qualification target. Public commands carry
identities rather than unrestricted URLs/paths. Current Intent, privacy, native
session, researcher confirmation and per-copy permissions still fence every
operation; no credential/cookie/proxy authority is inherited. Failed/cancelled
content has no canonical document association; typed inspection cancellation
remains distinct from failure and metadata stays usable.

The additional projections require verified forward migration from literal v23
and increase invariant/recovery test surface. Existing project protection and
object envelopes are unchanged. Recovery restores the verified predecessor
backup; it never downgrades security, rewrites earlier approvals/rights or claims
a failed acquisition succeeded. Broader S01 and W2 qualification remain required.

## Verification

Task evidence names fresh acquisition/location/transport tests and the actual
owned HTTPS, SQLCipher, encrypted-store and signed-LPAC Windows principal case.
Directly affected attachment/rights/API tests preserve operation-denial ordering,
source/license retention and restart. Literal v23 migration tests authenticate
counts/ciphertext and all material interruption points. Portable schema, current
storage/recovery, quality, API, unchanged architecture and base-to-candidate ADR
checks close the changed contract surface. Independent task review dispositions
the preserved admission/session/typed-cancellation findings and adverse receipts.
No mock, this Proposed record or task approval substitutes for integrated slice,
fresh Wave, production packaging or the separate human release gate.

## Task links

- `CAP-05.S01.T02`
