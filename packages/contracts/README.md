# Portable contracts

Owner: Research Observatory maintainers
Boundary: Schemas, API definitions, events, and generated client sources shared across processes.

Contracts must not expose operating-system paths, database connection objects,
framework components, provider SDK types, or other deployment-specific details.

`core-api/` contains the hand-authored runtime/handshake schemas plus the exact,
deterministically generated OpenAPI document and transport-neutral TypeScript
client for the local Core process. `python tools/core_api_contract.py --repo .
--check` regenerates both artifacts in memory and rejects any committed drift.

The package is source-only and side-effect-free. Application code imports
`@research-observatory/contracts/core-api`; it never imports Core implementation
modules or reconstructs private launch state.
