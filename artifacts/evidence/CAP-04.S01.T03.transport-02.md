# CAP-04.S01.T03 — transport finding remediation

Preserve `transport-01-disposition.md` at candidate
`c75b3e1f0b5ef0635aa3472f7a44f4ed0a8121b7`: CHANGES REQUESTED,
T03-TRANSPORT-01-F01 (P2). Earlier exact checks passed 16 Python cases in 27.572s,
26 client cases, TypeScript compilation, generated contract drift and the native
allowlist test (5.93s build). Passing checks did not cover UUID ordering.

Added service regressions for descending valid UUIDs and reopened request and
manifest discovery. They failed separately (1.185s and 2.852s) against UUID
sorting. The two focused cases then passed in 4.094s after selecting internal
insertion order on the existing append-only tables. IDs and caller timestamps
are not sequence authority; prior rows remain untouched. No schema change.

Renderer work is a separate current delta: shared review/confirmation controls,
Core-prepared requests, explicit start, cancellation, durable recovery, optional
earlier-batch comparison, and paged navigable manifests. An initial real renderer
test found Escape focus attempted while the target was still disabled; defer
focus until React commits the state update. Corrected journey passed in 7.429s
in both themes with real Core/storage/worker and explicit native doubles,
including reply loss, replay and navigation. Initial fixture cleanup and imported
TestCase discovery mistakes were corrected; their failures remain in tool output.
No native application or Windows principal proof is claimed by this renderer run.

Final exact-candidate checks and independent closure follow separately. Task
remains IN_PROGRESS. Large-input rights paging and publication guard/lease
qualification remain unfinished; no completion or release approval is implied.
