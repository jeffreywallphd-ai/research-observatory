# Portable contracts

Owner: Research Observatory maintainers
Boundary: Schemas, API definitions, events, and generated client sources shared across processes.

Contracts must not expose operating-system paths, database connection objects,
framework components, provider SDK types, or other deployment-specific details.

`core-api/` contains the hand-authored runtime projection schema and the exact,
deterministically generated OpenAPI document for the local Core process. Service
tests regenerate the document in memory and reject any committed contract drift.
