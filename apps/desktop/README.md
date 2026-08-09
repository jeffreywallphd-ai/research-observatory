# Desktop application

Owner: Research Observatory maintainers
Boundary: Tauri/React desktop composition, routes, shell, and local user experience.

This module may call privileged operating-system behavior only through narrow
Tauri commands or versioned Core API contracts. It must not embed service,
storage, parser, model-provider, or project-authority implementations.

`component-manifest.json` is the generated desktop version contract. It must mirror
the single product version in `packaging/product-version.json` and remain compatible
with the packaged sidecars.

## Development

Use the repository-pinned Node, pnpm, Rust, and Python runtimes. The renderer is
strict TypeScript and React 19; Tauri 2 is the only native host. Production builds
do not start a development server and the initial capability grants no privileged
commands.

```powershell
pnpm --dir apps/desktop lint
pnpm --dir apps/desktop typecheck
pnpm --dir apps/desktop test
pnpm --dir apps/desktop build
cargo test --workspace --locked
```

`pnpm build` recreates `dist/` from the exact approved UI reference, bundles the
React application runtime, and writes `dist/application-manifest.json`. The desktop
verification profile rejects missing, stale, redirected, or incomplete builds.

Routing and project-session transitions are pure renderer-domain modules. Filesystem,
process, credential, service, and storage access must be added only through reviewed,
typed Tauri commands or Core API contracts; renderer code must never import native
or service implementations directly.
