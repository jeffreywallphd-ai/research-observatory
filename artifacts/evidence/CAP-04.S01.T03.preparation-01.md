# CAP-04.S01.T03 — commit authority and provisional staging

Builds on independently reviewed storage candidate
`3603e6dfd7b0e6780266520688c95660fe032b9d`; not task completion.

Commit jobs bind exact source/draft/parser, researcher Intent, policy, recovery
epoch, explicit request identity and optional prior manifest. Request identity
is separate from scientific identity: changed inputs under one request conflict.
Continuation validates its actual cancelled/failed predecessor. Existing parser
and summary job definitions remain unchanged.

The protected repository stages at most 100 real draft rows per page, retaining
literal decision rights/bases, warnings and source digests. It checks current
draft/parse identity and running lease before and after projection, validates
complete claim configuration before taking its writer reservation, and rejects
rights denial even on excluded retained rows. Staging and hashing do not create
SourceRecords, manifests or accepted outputs. No service/UI route exposes this
increment yet. Current Intent/policy/session guards belong to forthcoming service
wiring; final publication must use fresh trusted time, one transaction and explicit
worker completion rather than treating a stale-lease exception as success.

New module tests initially failed to import absent implementations. Initial
request-replay test incorrectly rebuilt random workflow definition identities
instead of replaying the exact submission, triggering the queue's expected
authority conflict. The queue test now replays the exact submission and rejects
changed input under its request key. Service-level replay lookup remains pending;
freshly constructing a definition is not that lookup. No queue invariant changed.

Exploratory checks: three preparation tests passed in 2.821 seconds; cancellation
and excluded-storage-denial tests passed in 1.904 seconds; exact claim/input test,
request replay/conflict and continuation tests passed in focused runs. Formatting
corrected initial import ordering and long lines. Product mypy passed for both
new modules. Commit-bound checks and independent disposition follow. Atomic
publication, retry/reply loss across previews, large input publication, API/UI,
native protected-principal and packaged execution remain pending.
