---
id: ADR-0038
title: Bind sample connector page and port to existing plugin authority
status: Proposed
date: 2026-10-03
deciders: []
linked_tasks:
  - CAP-04.S05.T03
decision_scope: Documentary association of CAP-04.S05.T03's worker-page schema, Core plugin-job port and additive Python quality inventory with the already accepted W2 connector isolation, replay and provenance decisions; no new execution or rights authority.
affected_paths:
  - packages/contracts/connectors/connector-plugin-worker-page.schema.json
  - quality-scope.json
  - services/core-api/src/research_observatory_core/ports/plugin_jobs.py
supersedes: []
superseded_by: null
---

# ADR-0038: Bind sample connector page and port to existing plugin authority

## Context

The approved `CAP-04.S05.T03` task publishes a synthetic repository connector
and conformance suite after `CAP-04.S05.T02` established the signed Windows LPAC
worker. Accepted ADR-0028 already requires a bounded, versioned worker protocol,
Core validation, no ambient worker authority and no successful partial page.
Accepted ADR-0027 already requires protected scientific replay, cursor lineage,
sanitized response references and a record of broker redaction. The W2 packet
and approved slice make the public SDK example and its tests task scope.

The task changes three protected paths: a portable JSON Schema for the existing
worker page, a Core job-store port used to read a committed search predecessor,
and `quality-scope.json` entries for Python files newly added in the same
implementation commit. Architecture protection requires an indexed, task-linked
record for those changes. This Proposed companion documents their exact remit;
it does not itself accept a new decision, amend W2, authorize a plugin, change
rights, or qualify release. ADR-0027 and ADR-0028 remain the authority.

## Candidates

1. Leave the worker page implicit in Python models and call concrete repository
   methods from the service. This gives developers no closed portable output
   contract and would couple the port to its SQLite adapter. Reject.
2. Broaden the plugin interface with project, credential, network or filesystem
   authority to simplify a live sample. This violates the accepted LPAC and
   broker decisions and the local Wave's approved scope. Reject.
3. Publish the already bounded page as an alias-only JSON Schema, expose only
   predecessor fields through a structural Core port, and inventory the new
   Python checks. Keep Core-owned identity, redaction, policy, publication and
   rights decisions outside the worker page. Select as implementation detail.

## Decision

`connector-plugin-worker-page.schema.json` is the closed portable shape of one
`source-assertions-v1` worker page, including invocation and operation, source
assertions, continuation and cursor. Static conformance validates submitted
synthetic cases against both that schema and Core's closed scientific-request
parser; a local static pass never proves a candidate executes or has LPAC
authority. The sample lives under `docs/developer/sample_repository/`, outside
Core and renderer, and retains the signed package's relative fixed entry point.

`PluginJobStore.result` returns a structural predecessor view (`plan`,
`continuation`, `next_cursor`) rather than importing the concrete repository
adapter into the port. Core separately checks the current plan, exact committed
predecessor, query, page size and cursor before advancing. The worker receives
only its opaque invocation label. Core persists only sanitized broker bytes in
encrypted storage, records the broker's explicit redaction boolean, and binds
response references to published provenance. Historical pages without that
marker remain explicitly unknown; new publication requires true or false.

The same-commit `quality-scope.json` addition inventories seven new governed
Python files, without removing existing entries or admitting an already tracked
file through the new-file exception. The separate older desktop-test inventory
omission is a bounded-maintenance matter, not authority granted by this ADR.

## Consequences

Windows x64 local/lab is the only current execution qualification target; W6
platform adapters remain separate. Older three-argument plugins retain their
entry point. A plugin's reported fields, terms and IDs remain source assertions,
never Core rights, project identity or use/export permission. A signed manifest
and conformance result do not authorize network access or publisher trust; Core
and the researcher still make those decisions. The new page/ref fields add no
database DDL or migration and do not change frozen historical schema hashes.

The explicit schema and predecessor port increase contract and review surface,
but make false conformance passes and fabricated pagination observable. On a
failure, deny the page and preserve the earlier committed observation, audit
and adverse evidence. Rollback disables the unqualified sample or reverts this
unreleased implementation as a whole; it never downgrades LPAC, strips a
redaction marker from a new publication, or treats unknown rights as permitted.

## Verification

The task's exact-commit evidence must include synthetic valid/invalid
conformance cases (including alias-only output, extra/null scientific fields and
content-free diagnostics), encrypted broker-response/redaction publication and
reopen, cursor mismatch and predecessor denial, generated contract and
architecture checks, schema build-input inventory, focused static quality, and
the real signed Windows LPAC sample with zero capabilities. Independent review
replays the adverse findings and checks this record against ADR-0027/0028.
Broader slice and Wave qualification remain separate; neither a mock nor this
Proposed record is a substitute for them.

## Task links

- `CAP-04.S05.T03`
