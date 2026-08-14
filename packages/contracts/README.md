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

`support-bundle/support-bundle.schema.json` is the portable, strict schema for
the CAP-01.S04 redacted support document. The native host and renderer own the
preview/export envelope because local output paths are privileged host state;
the path never appears in the portable support document. Schema version `1.0`
caps recent code-only diagnostics and defines the exact included and excluded
categories without admitting research content, credentials, raw logs, process
identifiers, or absolute storage paths.

`project/` defines the versioned, relocatable local project manifest and exact
classified storage layout. Its runtime decoder fails closed on unknown or
path-bearing manifest fields, and its portable inventory excludes every cache,
index, model-working, log, lock, and temporary entry.
