# Desktop application

Owner: Research Observatory maintainers
Boundary: Tauri/React desktop composition, routes, shell, and local user experience.

This module may call privileged operating-system behavior only through narrow
Tauri commands or versioned Core API contracts. It must not embed service,
storage, parser, model-provider, or project-authority implementations.

`component-manifest.json` is the generated desktop version contract. It must mirror
the single product version in `packaging/product-version.json` and remain compatible
with the packaged sidecars.
