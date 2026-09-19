# CAP-04.S01.T02 — durable preview worker/service checkpoint

Base: `904a92d1be26ce7a9d343d609daa46e5e12514a3`. This is an in-progress
bounded implementation unit, not task submission or production qualification.
No new schema, canonical SourceRecord/import commit, external access or approval.

The new activity streams encrypted chunks into provisional IR with bounded
batches, cancellation and lease heartbeats. Its observed receipt binds complete
source-manifest, parser configuration and ordered IR identity; the existing queue
alone accepts outputs. Exact declarative workflow binding includes source,
parser/limits, rights, privacy, real Intent context and recovery epoch. It permits
local preview with a draft Intent without inventing acceptance. A scoped worker
cannot claim/recover other document activities. New bounded queue queries support
idempotent scheduling and complete paginated recovery inspection.

The service uses actual project authority, repository ports, encrypted objects,
admission and the supervisor. It drains ordinary close, rebuilds bindings after
reopen and cancels a mismatched epoch before claim. The persisted ADR-0013
manifest/domain Intent bridge is read and checked explicitly; direct equality
between those two legitimate IDs would reject normal lifecycle-created projects.
Foreign-project adapter substitution is denied.

Tests preceded the missing workflow/service implementations. Exploratory runs
found and corrected wrong workflow history keys, non-hash idempotency shape,
incomplete unknown-progress heartbeat fields, and the manifest/domain identity
comparison. One restart test initially assumed backoff after lease recovery;
inspection confirmed existing recovery deliberately makes the fenced retry
immediately available. Its assertion now tests actual required replay/once-only
acceptance, not an invented backoff requirement. An intermediate misplaced
protocol decorator was corrected. No prior valid test was weakened.

Qualification selection: new activity/workflow/service tests; existing local
executor tests for changed admission/recovery signatures; focused Intent
creation/read compatibility; changed Python quality, architecture/inventory and
sidecar metadata. Full W1 profiles are not selected. The new service fixture uses
real encrypted objects with a synthetic key and an explicit development database
profile; deterministic capacity observations are not measured platform resources.

Pending within CAP-04.S01.T02: native persisted recovery context/control-pipe
handoff and startup composition; selected-file intake; strict API/native/generated
client; duplicate projection and desktop wizard/report; fresh actual native
principal, accessibility and large-page performance checks. The service is not
yet reachable from production UI. No formal R01, DONE or Wave-exit claim.
