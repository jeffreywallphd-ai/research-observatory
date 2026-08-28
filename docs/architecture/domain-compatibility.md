# Domain compatibility and version negotiation

The W1 domain boundary has one language-neutral compatibility policy shared by
TypeScript and Python. The exact policy, schema, and release fixtures live in
`packages/contracts/domain`; the generator binds both runtimes to their SHA-256
identities. A component does not decide compatibility from a loose version
range, transport convention, or implementation-specific fallback.
The prior schema-set identity is the exact project-manifest schema hash. The
current identity is the SHA-256 of the canonical ordered inventory containing
the domain-core and lifecycle schema paths and hashes; the generator rejects
either fixture if those governed bytes drift.

## Change classification

| Classification | Permitted change | Required authority |
|---|---|---|
| Additive | Add an optional field or widen what a reader accepts within the same major version. | No ADR or migration is attached to the proposal. |
| Deprecation | Mark a field for later removal within the same major version. | A versioned removal window and portable replacement are required. |
| Breaking | Add a required field, remove or rename a field, narrow a reader, add to a closed enum, add/change an event, change identity, or repurpose meaning. | A new major version, accepted ADR, and source-retaining tested migration or reader bridge are all required. |

Closed enums and event-type sets are deliberately breaking because the current
strict consumers reject unknown values. A proposal with unknown fields, an
invalid authority reference, a mismatched migration endpoint, or an unretained
source fails closed with stable content-free diagnostic codes.

## Current and prior contract

Version `1.0.0` is the canonical UUIDv7 reader/writer contract. The `0.1.0`
fixture is a compatibility-catalog snapshot of the UUIDv4 project-manifest
behavior governed by ADR-0012 and bridged by ADR-0013; it is not a claim that an
older generated domain-core module existed. Legacy input remains read-only,
retains its source, and enters the explicit
`legacy-project-uuidv4-to-canonical-uuidv7` reader bridge. No runtime may silently
reinterpret a UUIDv4 value as canonical UUIDv7 identity.

This task changes no persisted schema, so it introduces no database migration.
Future breaking changes must provide the migration or bridge named in their
accepted ADR, exact from/to versions, a repository-relative test fixture, and
preserved source suitable for rollback or retry.

## Events and process negotiation

Event envelopes carry an exact version. Unknown event types are denied and
audited using stable codes; unknown payload fields are rejected. Desktop and
sidecar advertisements are mandatory, while a server advertisement is optional
for the local-first profile. Each role appears once and advertises ordered,
unique exact contract and event versions plus one schema-set identity.

Negotiation first requires one contract family and an exact schema-set match,
then chooses the highest semantic version present in every advertisement for
both contract and event envelopes. Input order cannot change the result. Missing
roles, duplicate roles, schema drift, or no exact overlap deny startup or the
cross-process operation before data is interpreted. Failure objects expose only
stable codes and never copy paths, credentials, component payloads, or research
content.
