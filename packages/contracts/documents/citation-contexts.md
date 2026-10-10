# Citation contexts

Under accepted ADR-0029, citation enrichment appends a separate encrypted
`citation-collection.v1` revision. It preserves the accepted structure and
original. Reported citation IDs remain revision scoped; inferred markers use
immutable collection-revision/order addressing and exact source selectors.
Neither extraction nor a link establishes scholarly support or verification.

The opaque command binds the accepted document revision, the exact current
reference-collection revision and the expected citation head. Core also records
the consumed protected reference payload digest. Native/project/human authority,
Intent, privacy, inspect/derive, target-source rights and material-input
freshness fence preparation, atomic publication, retry and delivery. Reference
refresh invalidates retained contexts until an explicit citation refresh.
Publication uses the existing canonical writer, human provenance, outbox and
complete material inputs. Cancellation, CAS conflict or precommit failure
preserves prior history. Exact retries and restart do not duplicate revisions.

Core builds the bounded Reader delivery inside that same publication transaction,
on both a new extraction and an exact retry. It uses the authenticated accepted
document, reference collection and source after current equality, head, payload,
catalog and material-input checks. Projection validation/failure and the final
precommit cancellation check roll back canonical publication together. The
ordinary repository return remains the immutable collection. The delivery path
retains the cumulative Viewer admission ledger, fixed multiplier 128 and 24-MiB
frame allowance while avoiding duplicate protected reads after publication.

Authenticated JATS, TEI and HTML links preserve each reported target member.
Missing members are unresolved; duplicate source identities are ambiguous.
Numeric, grouped/ranged and author-year/narrative patterns are marked inferred.
Numbers require reported reference labels; reference order supplies no label.
Unreported superscript roles and external destinations remain unresolved.
Known nonbibliographic callouts are excluded from flattened paragraph pattern
matching; citation patterns inside footnote bodies remain eligible.
No operation creates a Work, opens a URL or supplies an invented confidence.

Raw markers, paragraph context and inferred sentence boundaries retain accepted
node/projection/ranges and source anchors. Native raw contributors establish
child-to-parent offsets across CRLF and Unicode normalization. If composition
prevents an exact containing-text range, that range remains unavailable while
the child's source anchor stays exact. Repeated markers are never located by
an unqualified text search. Without authenticated native offsets, separately
projected reported descendants are not reinterpreted as parent patterns.

Collections have at most 1,000 markers, 128 members per marker, 65,536 codepoints
per marker/context and 16 MiB encoded data. Extraction has cooperative
cancellation and a five-second bound. Oversized numeric ranges are unresolved
rather than expanded. These are operation limits, not a hardware qualification.

`citation-reader-page.v1` exposes one context per page, bounded at 64 KiB UTF-8:
256 marker codepoints, 1,024 codepoints around a context marker, four target
members and four reference previews per member. Counts, truncation, inferred
boundaries and unavailable ranges are explicit. The exact node-relative text
offset drives source jumps; cursor reads pin the citation revision. Reference
inspection rechecks its exact reference ID/order/revision under current rights.
The current rights-fenced `citation-reader-notice.v1` reveals only an opaque
head and content-free unavailable/resource-limit status, permitting explicit
CAS refresh. Lock/return discards protected previews and late responses;
unknown issued Native requests retain admission until physical settlement.

The private Native/Core commands have closed input shapes and accept no caller
actor, source text, Work target, path, URL, policy or resource grant. JSON Schema
proves shape; Core enforces source, authority, freshness and graph invariants.
