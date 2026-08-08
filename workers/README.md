# Worker fabric

Owner: Research Observatory maintainers
Boundary: Isolated, idempotent CPU, GPU, and I/O activities.

Workers consume versioned contracts, carry project and provenance context, and
support safe retry and cancellation. They do not become an alternative source
of canonical project state.

`component-manifest.json` is the generated worker sidecar version contract. It
must mirror the single product version in `packaging/product-version.json`.
