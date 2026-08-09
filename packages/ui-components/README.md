# UI components

Owner: Research Observatory maintainers
Boundary: Accessible reusable interface components consuming governed tokens and portable contracts.

`@research-observatory/ui-components` provides accessible, framework-local
React primitives for the approved Academic Minimal experience. Components
consume semantic custom properties from `@research-observatory/ui-tokens` and
never own project, scholarly, filesystem, process, credential, or service state.

Version `1.0.0` includes:

- `Typography`, `Icon`, `Button`, and `Field`;
- `DataTable` with an explicit caption and column contract;
- `DialogSurface`, `Notification`, `StatusBadge`, and `Panel`; and
- neutral, info, success, warning, danger, and violet tone variants.

Status always includes visible text. `Notification` uses `role=status` for
nonurgent information and `role=alert` for danger. `Field` binds label,
description, and error text to its control. Dialog focus trapping/restoration,
global shortcuts, and live-region scheduling are owned by `CAP-01.S02.T02`.

`catalog.html` is the governed local component catalog. The desktop verifier
checks its light/dark contrast, semantic roles, minimum controls, token lineage,
and horizontal fit at 100%, 150%, and 200% zoom. React server-render tests bind
the catalog semantics to the exported component APIs.
