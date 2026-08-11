# UI tokens

Owner: Research Observatory maintainers
Boundary: Generated and validated Academic Minimal semantic design tokens.

`@research-observatory/ui-tokens` is the versioned transport for the approved
Academic Minimal semantic token contract. `index.css` imports the governed
source directly, so downstream applications cannot drift through a copied
palette. `src/index.ts` exposes only stable token and state identities; visual
values remain authoritative in `design/ui-reference/assets/tokens.css`.

This import transports semantic values at build time; it does not authorize
shipping reference HTML, illustrative content, future-capability routes, or
prototype behavior. Product bundles must contain their own functional markup and
code and may expose only implemented capabilities.

The contract is version `1.0.0` and is bound to reference
`RO-UI-ACADEMIC-MINIMAL-1.3`. Changes to semantic meaning, contrast, or values
require a newer approved reference. Additive TypeScript helpers that preserve
the visual contract use normal semantic versioning.
