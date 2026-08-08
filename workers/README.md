# Worker fabric

Owner: Research Observatory maintainers
Boundary: Isolated, idempotent CPU, GPU, and I/O activities.

Workers consume versioned contracts, carry project and provenance context, and
support safe retry and cancellation. They do not become an alternative source
of canonical project state.
