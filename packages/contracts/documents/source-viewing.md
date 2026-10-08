# Protected local source viewing

CAP-05.S04.T01 implements accepted ADR-0016/0017/0029 and the inherited
Document Reader experience in approved RO-UI-ACADEMIC-MINIMAL-1.9. It adds no
source envelope, database migration, cache of original plaintext or new actor
authority. T02 owns durable deep links; T03 owns rights-aware copy, print,
external-open and export actions. Those actions remain unavailable in T01.

## Transport and identity

| Renderer command | Fixed private Core route | Delivery |
|---|---|---|
| `document_viewer_source` | `/native/document-viewer/source` | Exact source metadata |
| `document_viewer_range` | `/native/document-viewer/range` | Native validated raw ArrayBuffer IPC |
| `document_viewer_text` | `/native/document-viewer/text` | Exact accepted text chunk |
| `document_viewer_cancel` | `/native/document-viewer/cancel` | Native stop signal; original range supplies terminal disposition |

The renderer names the project, attachment, original revision, optional accepted
normalized revision and bounded operation fields. Native adds its selected root,
current Core session and private capability; Core resolves the current trusted
human, Intent, privacy and per-copy rights. No path, URL, token, session, actor,
policy or rights field is accepted from the renderer. These private routes are
excluded from OpenAPI and reject renderer-origin HTTP requests.

Every range request has its own UUIDv7. Integer half-open ranges are at most
1MiB and contained in the original's at-most-128MiB length. Core's response binds
request ID, start/end and the full source identity before native decodes base64
and returns raw bytes. Native fences delivery by actual window, protected lock
generation and current supervisor/project connection. The renderer receives no
Core base64 envelope or credential. Native response limits include worst-case
base64 and metadata overhead; text is at most 4096 Unicode code points.

The source identity includes project, attachment, document/original revision,
candidate, source assertion, Work/Work revision, Version/Version revision,
digest, length, format and acquisition provenance. Accepted structured text must
resolve to that exact source, accepted normalized revision, element and offset.
Current derive permission is rechecked after the artifact context closes; inspect
permission alone allows the original but cannot authorize derivative delivery.

## Reads, cancellation and recovery

Each original range authenticates the whole encrypted source, then discards its
prefix in bounded chunks. The owned stream and transaction close before delivery.
Trusted non-I/O stop signals are checked during authentication, prefix discard
and delivery. Cancellation rolls back and closes its owner; it does not kill a
database thread or quarantine healthy ciphertext. Corruption retains the existing
quarantine behavior. A fresh retry rechecks all current authority.

One owned range worker admits one active read per project and eight waiting
operations. Only exact project/session/actor/authority/source/range keys coalesce;
each waiter retains its own stop and fresh delivery check. HTTP disconnects reach
the cooperative reader. Project actions remain reentrant and FIFO, so waiting
metadata writers can run between ranges. Native remembers a cancellation that
arrives before registration, scoped to its actual window and opaque key; bounded
cancellation-memory exhaustion fails closed.

Cancelling IPC is a stop signal, not a drain acknowledgement. The original
range promise resolves bytes only after physical close, or rejects a closed
native disposition with schema version, project, request and a `drained` boolean.
Native errors after Core issuance acknowledge termination only from Core's exact
root/project/session/request registration: its correlated private response binds
schema version, project, native session, request and `drained`. Core waits at most
one second for participation to end; last-member cancellation additionally waits
for the actual active callback to close its stream and transaction. An independently
authorized coalesced follower retains collective ownership. Unknown registration,
lost transport or deadline expiry is not successful drain. Bounded terminal records
support late cancellation; unconsumed early markers cannot expire into admission.

The renderer consumes the original range disposition, never settlement of the
stop signal. Unknown drain poisons the byte session after pending-map removal,
denies replacement, and retains its in-flight reservation; a later confirmed
terminal result can release that reservation but cannot erase a missed deadline.
Native likewise retains bounded unresolved admission ownership. Cancelled native
owner/project/request identities remain denied if a delayed duplicate arrives.

Original inspection adds no source anchor, structural acceptance or scholarly
claim. Successful object verification retains the existing verification metadata
behavior; cancelled transactions do not advance it. Search queries, decoded text,
PDF actions and copied research text are not written into viewer diagnostics.

## Local decoder and admission

The shipping dependency is exactly `pdfjs-dist@6.4.299` (Apache-2.0); its bundled
worker SHA-256 is checked by the product build. Unique, fail-closed transforms
cap contiguous range groups at 1MiB with 64KiB chunks and serialize actual SDK
range-reader admission. The SDK retains its existing missing-chunk bookkeeping;
deferred demands hold no source bytes or native/Core lease. Closing the document
prevents them from acquiring a range reader. This does not add a renderer byte
queue or enlarge Core's eight-waiter limit. A changed dependency or patch anchor
fails the build. Preserve the upstream package
license in packaging; the existing exact lockfile supplies dependency provenance.

The dedicated module worker is local. Its source has no document-controlled
module or asset URL. Automatic streaming/prefetch, XFA, annotations, forms,
document scripts/actions/attachments, system fonts, native image decoding, WASM
and remote worker fetches are disabled. Main-side fonts/CMaps come only from the
fixed bundled filename inventory on the application's origin. Their shared
8MiB pool includes concurrent input chunks and concatenation, with coalescing of
immutable application-asset requests. This does not cache an original source.
The exact CMap/font and license digests live in the product's
`apps/desktop/pdfjs-assets.json`; product packaging checks every shipped resource
against that inventory and ships the upstream and font notices. The worker and
lazy Reader modules have fixed local artifact names, separately from `app.js`.

Admission accounts for bounded Core/native/range copies, the worker's source and
decoder backing stores, decoded message clones, all tracked canvas surfaces and
the bounded thumbnail window. Worker constructors, copies and the native font
encoder are guarded before allocation. Other uncounted native allocation paths
are unavailable. Map/Set message contents are counted; hidden native clone storage
is rejected. Every retained message graph keeps its clone charge until its last
owned child is collected. Closing cancels reads/renders/assets, terminates the
worker immediately and clears owned surfaces and references.

Page navigation that interrupts outstanding work, and Cancel search, retire the
entire decoder generation because the pinned SDK shares its missing-chunk
bookkeeping across operations. No deferred demand from that generation can enter
the carrier after termination. Replacement work awaits the admitted readers'
drain, capped at one second, and reopens the same opaque source with fresh Core
authority. A failed drain denies replacement. The Reader preserves the selected
Work/version, page and zoom while its existing loading state restores the page.

The fixed reservations are accounting bounds, not measured live or peak memory.
Actual Tauri/Wry/Core wiring, cancellation and writer drain at the maximum source,
hostile decoder behavior, complete resource footprint, and the accepted cold/warm
20-open latency criterion remain separate qualifying evidence obligations. A
synthetic byte bridge, unit double, screenshot or live-memory snapshot cannot
establish those claims. Owner-directed smaller model options and deferred larger
hardware tiers require their own approved successor and are not authorized here.
