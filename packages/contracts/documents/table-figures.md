# Protected tables and figures

CAP-05.S05.T03 derives separate encrypted observations from one immutable
human-accepted document. Existing canonical table, figure and cell node IDs,
source order, raw/NFC spans, rows, columns, merged spans, geometry and confidence
are retained. Extraction never verifies a cell or scholarly claim.

Native caption/label ownership and header roles require the exact retained
parser artifact and supported source namespace/container semantics. Retained
Docling relationships must reconstruct the exact accepted structure and identity
map. Missing or competing captions remain unavailable or ambiguous; first-row
headers are never invented. Sparse and split grids remain observations, without
dense expansion or automatic repair.

`table-figure-collection.v1` uses the existing canonical writer, encrypted object
store, schema-28 enrichment/index, human provenance, outbox and complete material
manifests. Every read, extraction, exclusion and retry rechecks current
Native/project/session/human/Intent/privacy and source inspect/derive authority.
Commands carry opaque IDs and an expected collection head. An exact retry adds
no history; refresh appends a revision and replacement impacts.

The explicit exclusion command carries the exact source/collection/node,
command ID and a human rationale of at most 256 codepoints. It appends an
unverified collection revision and preserves all original parse output and prior
observations. Refresh on this same accepted source preserves exclusions.
Exclusion is not permission to rewrite source evidence or certify other cells.

Operations allow at most 1,000 objects, 10,000 total cells and 16 MiB protected
JSON, with five-second cooperative cancellation. Conservative cumulative
admission precedes copied source text, range/anchor construction and whole-entry
serialization; projection reuse is charged for every output member. Large
dimensions never allocate a dense table.

`table-figure-reader-page.v1` exposes one object, eight cell previews and up to
four caption/label previews, each at most 512 Unicode codepoints, with explicit
counts/truncation and a 64 KiB UTF-8 cap. Cell paging pins the collection and
canonical object ID. Source jumps carry exact canonical nodes and offsets;
Core reads the accepted source again under current permission.

An original preview references only the protected original revision/digest and
reported unrotated source page/region. A cell-derived location is explicitly
distinguished from reported object bounds. The existing protected Reader renders
that original page beside the extracted observation. External graphics and
parser stage IDs never grant image delivery or trigger a fetch. Unreported or
unsupported previews remain unavailable.

The notice schema carries only a current rights-fenced opaque head and an
unavailable/resource-limit status. It cannot deliver prior text. Reader resource
admission stays owned until physical settlement; lock/close/source substitution
clears visible previews. No parser/model invocation, OCR, new hardware minimum,
network destination or accepted-v1/migration change is introduced.
