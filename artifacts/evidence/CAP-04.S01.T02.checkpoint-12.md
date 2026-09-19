# CAP-04.S01.T02 — bounded draft undo

Increment from approved `3219f5acdadb3f6656f964703bde079bc3c3bbc3`.
Task remains IN_PROGRESS. No schema migration or new product authority.

The authenticated command accepts an expected revision, not a caller-selected
restore target. Core walks the effective edit stack; repeated undo and edits
after undo do not resurrect an abandoned branch. Every undo appends an audited
revision through existing compare-and-swap, accepted-attempt and rights checks.
All eight permissions retain the checkpoint-03 restriction: undo cannot grant
an action that current default or per-record rights disallow.

Setwise sparse-history comparison replaces per-record recursive lookups. Equal
immutable decisions can be skipped after default-rights comparison; changed
decisions require both permitted value and researcher-confirmed basis. Composite
key lookups keep large correction values out of Python materialization. This is
not a special bypass or a renderer-authorized rights transition.

Before implementation, the new API sequence returned 404 and a 300-record
regression detected scalar per-ordinal rights traversal. Tests now cover repeated
undo, no remaining target, stale requests, supplied-target denial, edits after
undo, retained historical revisions and all-action denial beyond the visible
page. Generated-client ownership/decoder checks and native exact-body/range
validation cover the public boundary. The built UI/Core journey uses keyboard
undo in both themes and checks durable inclusion, retained corrections and focus.

Exploratory failures retained: an eight-preview rights fixture reused a fixed
worker idempotency key and failed setup; it now uses explicit permission resets
within one preview. The UI fixture reused an excluded record across themes; it
now explicitly includes and verifies the row before exclusion/undo. Neither
change relaxes product assertions. A mistaken native name filter ran zero tests;
the corrected exact filter ran and passed the intended validator.

Query-only diagnostics: 100k decisions / 10,001 revisions took 0.095s in the
isolated SQLite test; independent in-memory SQLCipher checks measured 0.069s at
1,001 revisions and 0.088s at 10,001. Instrumentation found rights evaluation
only for the ten changed decisions. These are not encrypted-disk, API deadline,
full-project or native-window qualification. They support retaining synchronous
single-edit undo rather than adding an unnecessary durable job for this command.

Selected checks cover the changed repository, authenticated routes, generated
client, native validator and actual built renderer/Core composition, plus their
types/lint/contracts and product build. Exact-candidate checks and independent
review follow commit. Unchanged migrations and full W1 suites are not replayed.
Duplicate/count projection and remaining task-level principal/scale proof remain.
