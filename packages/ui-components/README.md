# UI components

Owner: Research Observatory maintainers
Boundary: Accessible reusable interface components consuming governed tokens and portable contracts.

`@research-observatory/ui-components` provides accessible, framework-local
React primitives for the approved Academic Minimal experience. Components
consume semantic custom properties from `@research-observatory/ui-tokens` and
never own project, scholarly, filesystem, process, credential, or service state.

Version `1.2.0` includes:

- `Typography`, `Icon`, `Button`, and `Field`;
- `DataTable` with an explicit caption and column contract plus accessible,
  bounded pagination. It renders 50 rows by default and rejects page sizes
  above 200 so a 10,000-row input cannot restore eager DOM rendering;
- `DialogSurface`, `Notification`, `StatusBadge`, and `Panel`; and
- neutral, info, success, warning, danger, and violet tone variants;
- `EvidenceStateBadge` variants for observed, extracted, inferred, verified,
  disputed, adjudicated, and stale evidence; and
- `UncertaintyState` variants for unknown, not reported, not applicable, and
  ambiguous values.
- `BoundaryStatePanel` variants for loading, empty, offline, denied, stale,
  partial, failed, and recovery-required operation states. The component
  supports bounded progress, retry, cancellation, continued local work,
  retained content, and copyable opaque diagnostic references.

Evidence and uncertainty components always render their identity as visible
text, so their meaning never depends on color. `Notification` uses `role=status` for
nonurgent information and `role=alert` for danger. `Field` binds label,
description, and error text to its control. Dialog focus trapping/restoration,
global shortcuts, and live-region scheduling are owned by `CAP-01.S02.T02`.
Boundary components never accept raw exception text, secrets, URLs, paths, or
stack traces as diagnostics. Their public copy surface accepts only bounded
`RO-...` references; adapters retain and redact technical details outside the
renderer. Failure states do not unmount caller-owned retained content.

`catalog.html` is the governed local component catalog. The desktop verifier
checks its light/dark contrast, semantic roles, minimum controls, token lineage,
complete evidence/uncertainty inventory, accessible-name references, and
horizontal fit at 100%, 150%, and 200% zoom. Package-local type, runtime, and
tree-shaking tests bind the catalog semantics to the exported public APIs.

The desktop verification profile also runs the governed 10,000-row
`DataTable` benchmark. It alternates the first and last accessible pagination
windows, verifies that no more than 50 rows enter the markup, retains every
sample, and enforces both the 100 ms batch budget and the immutable 20 percent
regression threshold in
`verification/baselines/ui-components-data-table-performance.json`.
