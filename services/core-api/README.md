# Core API

Owner: Research Observatory maintainers
Boundary: Packaged Python modular monolith and local application composition root.

Domain and application policies remain separated from adapters. This module
owns local API composition and transactional coordination; resource-intensive
activities execute through worker contracts rather than inside request handlers.
