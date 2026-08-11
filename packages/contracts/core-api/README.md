# Core API contracts

`core-runtime.schema.json` defines the framework-neutral runtime identity,
state, version, and capability projection. `openapi.json` is generated from the
FastAPI application and committed so desktop/client generation can detect API
drift before runtime.

These contracts contain no OS paths, socket assignment, credentials, research
content, provider types, or deployment-specific framework objects. Version or
semantic breaking changes require the compatibility and ADR controls declared
in the repository architecture.
