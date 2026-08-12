# Desktop application

Owner: Research Observatory maintainers
Boundary: Tauri/React desktop composition, routes, shell, and local user experience.

This module may call privileged operating-system behavior only through narrow
Tauri commands or versioned Core API contracts. It must not embed service,
storage, parser, model-provider, or project-authority implementations.

`component-manifest.json` is the generated desktop version contract. It must
mirror the single product version in `packaging/product-version.json` and remain
compatible with packaged sidecars.

## Development

Use the repository-pinned Node, pnpm, Rust, and Python runtimes. The renderer is
strict TypeScript and React 19; Tauri 2 is the only native host. Production and
development make no remote-network request. The renderer receives only the
narrow, typed Core-supervision commands introduced by CAP-01.S03; it does not
receive ambient shell, process, filesystem, or credential access.

Launch from the repository root with `dev.cmd`; the batch launcher is also
callable as `./dev.cmd` from Git Bash. It selects the checkout-local toolchains,
and the app's `pnpm dev` script rebuilds the ignored development sidecar before
starting Tauri. No system Python or machine-wide Node selection is used by the
launched application.

```powershell
pnpm --dir apps/desktop lint
pnpm --dir apps/desktop typecheck
pnpm --dir apps/desktop test
pnpm --dir apps/desktop build
cargo test --workspace --locked
```

`pnpm build` produces two deliberately separate outputs:

- `product-dist/` is the only Tauri `frontendDist` used by production and
  development. It contains authored React behavior for implemented capabilities,
  currently one CAP-01 project-home route, plus an exact product manifest.
- `dist/` is an offline reference-conformance fixture used only by verification.
  It is never configured as a Tauri frontend and is not a product or development
  application.

The product assembler rejects reference-only pages, workflow fixtures,
unexpected artifacts, stale source hashes, and any Tauri configuration that
points away from `product-dist/`.

## Functional application boundary

The React product implements only behavior owned by completed capabilities. The
approved UI reference supplies semantic tokens, layout intent, accessibility
requirements, and page/workflow contracts; its HTML, illustrative prose, mock
research records, future-capability routes, and nonfunctional actions are not
product source.

The current product exposes only `index.html`, the page that the reference
coverage catalog assigns to CAP-01. `Ctrl+K` focuses the real command search,
`Ctrl+/` opens the keyboard-shortcut dialog, `Alt+H` returns focus to project
home, skip navigation is first in the tab order, dialog focus is restored, and
status changes use one polite live region. The shell contains no fabricated
project, source, study, model, or workflow data.

It also exposes a truthful local-service supervision boundary. In the Tauri
host, Core starts automatically, reaches readiness over numeric loopback, and is
polled for crash state. Blocking native lifecycle work is dispatched away from
the Tauri main thread. Startup can be cancelled; stop completes before retry is
offered; crash retry is bounded; and
the renderer receives only exact state, attempt, retry, and opaque diagnostic
fields. Outside Tauri, the same product bundle reports the bounded
`RO-CORE-SUPERVISOR-UNAVAILABLE` state instead of pretending that Core is
running. Command input remains mounted across startup, failure, cancellation,
and recovery. Raw exceptions, paths, URLs, credentials, process output, and
stack traces are never rendered or copied. On Windows, Core is created suspended,
placed in a kill-on-close Job Object, and resumed only after containment is active;
graceful, forced, and host-exit cleanup therefore apply to the complete process tree.

The legacy reference-activation modules are isolated behind
`src/reference-main.tsx` for conformance tests and are not imported by the
product entry. Project storage, scholarly workflows, sources, models, and
manuscript surfaces must remain absent from the product bundle until their
owning capability supplies real contracts and behavior.

CAP-01.S04 adds one capability-owned functional diagnostics workspace. It reads
only the narrow native supervision/support commands, shows current component
versions, runtime health, bounded resource use, storage availability, and
code-only recent diagnostics, and links eligible desktop actions to Core trace
IDs. It does not copy a diagnostics page, sample records, or illustrative prose
from `design/ui-reference/`.

Support export is an explicit preview-then-export operation. The native host
retains one exact preview, caps its JSON at 65,536 bytes, exports those exact
reviewed bytes once under the application-data `support-exports` directory, and
rejects redirected or pre-existing destinations. Project documents, imported
sources, manuscript content, search/query text, credentials, environment
variables, raw process logs, process identifiers, and absolute storage paths
are excluded by construction. The local output path is displayed separately
and is never embedded in the bundle.
