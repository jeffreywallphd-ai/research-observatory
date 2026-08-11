# Core API contracts

`core-runtime.schema.json` defines the strict framework-neutral health and
readiness response variants, including runtime identity, state, version, and
capabilities. `openapi.json` is generated from the FastAPI application and
committed so desktop/client generation can detect API drift before runtime.

These contracts contain no OS paths, socket assignment, credentials, research
content, provider types, or deployment-specific framework objects. Version or
semantic breaking changes require the compatibility and ADR controls declared
in the repository architecture.
