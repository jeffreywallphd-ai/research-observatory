# CAP-04.S01.T02 — complete diagnostic report publication

Increment from approved `61fb2bb8b331a975ea6baf7a0546946598ac7b68`.
Task remains IN_PROGRESS. Approved scope and rights/security policy unchanged.

Native report save accepts only project, preview, revision and cancellation
identity. The shared Windows folder chooser retains destination authority in
native code; the renderer receives only a generated basename and byte count.
The diagnostic CSV contains ordinal/line locations, status and bounded codes,
not scholarly text, source names, paths or hashes. It is not a grant of
content-bearing export permission.

Private authenticated pages pin the Core/project session and exact current draft.
Native validates identity, stable record count, contiguous ordinal coverage,
multiple warning rows, one header and terminal completeness. Streaming is bounded
to a page plus a 128 KiB verification buffer; the report limit is 256 MiB.
Every page is fetched from Core, never accepted from a renderer blob.

Selected-directory ancestor handles deny replacement. A create-new sibling stage
uses an exclusive read/write/delete handle; flush and readback digest verification
precede publication. Same-handle rename refuses existing destinations. Lock,
operation and native project/launch guards cover the local rename only; network,
flush, verification and rejected-result cleanup occur outside those mutexes.
Unpublished owned stages are deleted by handle, not a newly resolved path.
Successful rename immediately marks publication. Later cancellation cannot undo
the file or relabel success; an uncertain response tells the user to check their
selected folder before retrying, not that nothing was saved.

## Preflight and selected checks

Reviewer `w2_document_packet_preflight` identified that a historical terminal
report page checks no prior record rights. Closure: native export requires the
current head revision to equal the requested revision, including a final separate
Core authorization. An actual repository per-record revocation regression rejects
the old revision before publication. Core authorization and native rename are
distinct linearization points, not a claimed cross-process transaction.

Before implementation the new private-route test failed 404. Core report identity,
pagination/final authorization and earlier-record revocation tests then passed
(two cases, 1.864s). Native tests cover exclusive staging, cleanup, destination
collision, malformed/substituted/non-progressing pages, request authority,
owner/picker restrictions and cancellation after publication. A helper streams
100,000 synthetic source records with 200,000 diagnostics and one header; seven
report checks passed together in 0.41s. This is not a full 100k project/UI benchmark.

Renderer tests cover path-free exact requests, strict basename receipts, and late
success after cancellation. The built journey exercises complete real-Core report
pagination and keyboard focus in both themes, with explicit native chooser/save
doubles. An initial locator matched both notice and live announcement and was
narrowed to the workspace; a later run correctly rejected a stale build manifest
after native inputs changed. Neither failed run counts as qualification.

Selected candidate qualification: these affected native/source/picker/transport,
Core report/intake and renderer tests, product build, formatting/types, private
API-schema isolation and inventory/architecture checks. Fresh checks and
independent exact-candidate review follow the commit. No full W1 replay.

Follow-up read-only implementation advisory found no material blocker and
confirmed the authorization/cleanup/publication distinctions. It ran no tests
and is not approval. The rebuilt renderer/Core report journey passed in 7.574s.
Initial native compilation exposed Boolean binding types and missing Rust
create-new write flags; these were corrected before the passing helper runs.
Force-terminating the native process can leave a hidden content-free partial
stage; it never becomes the completed report name. Ordinary failure/cancellation
cleanup is tested, not generalized to an unobserved process-kill guarantee.

Basis: Microsoft documents [handle-based file operations](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-setfileinformationbyhandle)
and [non-replacing rename](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_rename_info).
No native-window/actual-principal/packaging claim is made by helper tests or browser
doubles. Duplicate/count/coverage projection, undo, delimiter integration and
remaining native/scale qualification still precede whole-task submission.
