# CAP-04.S01.T03 — isolated native commit and replay

Candidate: `3d87c3545c6908512054c5cbdb08e0445a488d8d`.
Debug integration-harness binary SHA-256:
`8d946ce6d7015fdebd717eb22bb856e92883a109121cd54313c2e63ab6d4983e`.
**PASS within the following observed scope**, not packaged/release or whole-task
qualification. No source, renderer or native inputs changed during execution.

The existing lifecycle harness started an isolated application-data directory,
vault, protected project and actual built React/Tauri/Core on the interactive
Windows desktop. Its historical synthetic window title is not the task ID.
Only generated bibliography data and a newly created test project were used.

Observed through the native UI:

1. Created and opened a theory-synthesis project without entering credentials.
2. Opened Ingestion & Reconciliation, chose CSV and confirmed local store/inspect
   rights for the generated fixture. Other rights remained unknown.
3. Used the real Windows file picker. The first selection was outside the
   harness's confined projects folder and was correctly rejected before intake;
   this was a fixture placement error, not a product permission change. A new
   copy inside the permitted fixture folder imported successfully.
4. Inspected the complete summary: two included records, zero excluded metadata
   records, one CSV context/header row and one retained header warning.
5. Used Review commit, then the explicit Commit this draft action. The UI reported
   `Committed — awaiting reconciliation`, not resolved works or verified claims.
6. Opened the immutable manifest. It showed two new source records, zero reused,
   all three source-row decisions, parser/mapping/draft identities, source and
   membership digests. The context row remained excluded and its warning visible.
7. Repeated review/commit of the same draft. The same manifest returned.

Independent read-only connections to this fixture under the same interactive
Windows principal confirmed both before and after replay: three parse rows,
two canonical import source records, one manifest, three members, one seal and
one accepted commit output. Actual DPAPI/SQLCipher was used; no credentials,
ordinary vault, real research project or sign-in setting was accessed.

Windows UI automation accessibility indexes sometimes pointed to stale/off-screen
rectangles or could not address an owned dialog. Fresh screenshots and native
keyboard navigation completed the actions. This does not establish screen-reader
qualification. Retained generated-client/renderer tests separately cover focus,
lost reply, navigation and post-commit cancellation. This session did not repeat
all those suites or prove packaged execution, large-scale publication, native
restart/cancellation, or full slice qualification.
