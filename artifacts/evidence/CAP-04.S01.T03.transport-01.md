# CAP-04.S01.T03 — public transport implementation checkpoint

Continues reviewed service checkpoint `ad03ffc89c29bd48cc3ffdacadf519cc76bcf205`.
This is incremental implementation, not task completion or native UI proof.

Adds bounded authenticated commit preparation, explicit execution, durable
request discovery/status/cancellation and immutable manifest paging. Core mints
request IDs; renderer memory is not restart authority. Generated client decoders
own input snapshots and reject incoherent output, substituted identities and
unbounded pages. Native bridge matches these exact operations. Error disclosure
does not falsely promise no publication after an uncertain reply.

Development checks: the first three API tests failed on absent routes (3/3,
2.666s), then passed after implementation (3/3, 5.078s). Expanded API plus service
restart checks passed (6/6, 12.023s); saved-request discovery subsequently passed
(1/1, 2.488s). Five initial generated-client checks passed. Python lint, format,
four-file typecheck and architecture passed. Native allowlist check passed
(1 test, 29.34s build), with existing unused `NativeImportAction::Status` warning.
An exploratory preparation probe exposed a missing `new_uuid_v7` import; fixed
before the passing discovery test. The first native command failed on missing
tools import path; corrected its environment, not product behavior.

Fresh exact-commit checks/disposition follow separately. Deferred: renderer
journey, actual native/Core crossing, cold/warm large manifest paging and final
publication guard/lease qualification. Read-only preflight recommends a bounded
adapter-local rights memo invalidated by exact draft/parse/seal authority, plus
separate guarded verification pages before the atomic writer. No new gate.
