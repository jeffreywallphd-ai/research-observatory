# Contract tests

Owner: Research Observatory maintainers
Boundary: Portable schema and cross-process compatibility tests.

Tests cover producer/consumer compatibility, invalid payloads, migrations, and
the absence of deployment-specific values in portable interfaces.

Research Intent coverage exercises all seven epistemic-mode branches, valid and
invalid revision lineage, explicitly incomplete drafts, human-only acceptance,
mode/use-case/stopping compatibility, temporal and egress boundaries, immutable
ownership, and exact downstream governing references in both generated
runtimes.

Workflow coverage exercises one executor-neutral definition across local and
server profiles, separate run/step/job/attempt/human-task transitions,
serialize/reload replay, retry and checkpoint ownership, monotonic progress,
committed artifact disposition, immutable human decisions, security-lock
denial, and the exact legacy operation projection bridge in both generated
runtimes. Real SQLite/process restart remains an integration responsibility of
`CAP-03.S04.T02`.

Workflow-profile coverage authenticates the exact fourteen-profile governed
catalog, immutable Research Intent/profile selection lineage, ordered and
cyclical stage metadata, primary versus supporting navigation state, current,
completed, attention, and stale projections, and complete history-preserving
profile migration in both generated runtimes. It deliberately rejects
analytical job state at this boundary; CAP-03.S06.T02-T04 own persistence and
application behavior.
