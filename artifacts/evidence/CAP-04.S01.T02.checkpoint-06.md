# CAP-04.S01.T02 — bounded review API and desktop transport

Base: `ca524fb2709e52395e1cddb9b8a12a13f8665f7e`. This is approved preview
implementation, not a canonical import or a task-completion claim.

The public review boundary supplies summary, ordinal record pages, separate
raw/candidate/effective field pages, index-selected CSV mappings, atomic grouped
corrections/exclusions and fixed-revision diagnostic fragments. Core derives the
actor/time and revalidates the open project. Strict JSON-list transport models
explicitly construct the unchanged tuple-based domain models. Mapping revisions
use the project profile high-water mark, including after undo.

Read-only preflight identified that repository limits exceed native transport
limits. Requests and measured response envelopes are now bounded at 900,000 bytes,
below the native 1 MiB limit. Summaries disclose abbreviation; detail pages retain
complete values. Group expansion is counted incrementally before publication and
rejected atomically above the existing 8 MiB repository limit. Reports advance
from the last scanned ordinal without restarting their iterator from zero.
Every page rechecks current rights; cancellation cannot produce a complete report.

Generated TypeScript decoders own immutable, bounded values, preserve all eight
rights dimensions, reject malformed responses and bind replies to the requested
identity/revision/cursor. The native allowlist admits only the seven exact review
shapes: no arbitrary file reads, intake or canonical commit route is exposed.
The generator quotes non-identifier property names so the existing `model-use`
wire action remains unchanged. OpenAPI and generated client are regenerated.

Tests preceded each new boundary; initial missing-module, missing-route,
missing-client and native missing-validator failures were expected red states.
A further group-size test reproduced full-group expansion before rejection, then
passed with incremental accounting. Development tests are not yet commit-bound
qualification; selected candidate checks and independent disposition follow.

Remaining task work: native file intake and complete staged report export,
duplicate/count projections, scalable undo orchestration, desktop wizard,
real native/Core/renderer end-to-end, accessibility and 100k-record qualification.
Full W1 profile replays remain unselected; CAP-04.S01.T03 retains canonical commits.
