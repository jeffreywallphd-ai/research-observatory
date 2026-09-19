# CAP-04.S01.T02 — protected scale observation selection

The first real protected diagnostic at e80 used production runtime composition,
Windows DPAPI/SQLCipher/actor/object providers and the actual worker. Its new
test file was not yet committed; this was exploratory, not candidate qualification.
Explicit substitutions: fresh synthetic project/vault/source, in-process ASGI
transport and supplied native workflow context/capability. No ordinary profile.

Retained report:
`artifacts/tmp/import-review-scale-windows-3of2md1a/diagnostic.json`.
HEAD and recorded backend inputs stayed unchanged. Intake: 4,600,010 bytes in
36 bounded chunks, 4.875s. Parse: all 100,001 IR rows (100k records plus header),
80.584s under the unchanged production 120-second limit. At the diagnostic's
240-second summary observation cutoff, attempt 1 was still running without a
diagnostic and had retained 94,900 summary rows. There was no accepted summary
completion. Canonical records remained zero. Peak whole-process working set:
133,091,328 bytes, including Core, runner and ASGI client. Total: 327.140s.
Paging, group traversal and reopen were not reached. This run is incomplete,
not a latency/resource pass. An earlier metadata-only setup invocation requested
an absent unused crypto distribution; it stopped before runtime composition and
was corrected to inventory the actual installed dependency.

Independent read-only assessment by `w2_document_packet_preflight` confirmed that
240 seconds is this new observer's cutoff, not an approved latency baseline or
product summary deadline. Approved slice section 11 requires bounded-memory 100k
evidence but supplies no 240-second summary limit. The production worker still
uses bounded pages, lease renewal, authority checks and cancellation.

Selected next run: a separately retained, committed-candidate functional check
with a 360-second summary and 1,200-second overall observation budget. The parser
deadline, worker authority/lease checks, per-request limits, expected counts,
complete pagination, restart consistency and canonical nonmutation assertions
remain unchanged. Any terminal failure still fails immediately. Keep the prior
incomplete result; do not relabel it or infer a performance baseline. Timings and
memory remain descriptive. Optimize only if actual contract/resource evidence
requires it, not merely to satisfy an arbitrary exploratory observation cutoff.
