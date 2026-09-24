# CAP-04.S02.T03 acceptance closure

Claim base: `d45d33dec00466f66c845d4a56fe002f82d6ba08`.
Authority: approved CAP-04.S02 section 9.3 at W2 packet
`c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`, ADR-0027 and inherited
ADR-0017/0019/0025 boundaries. CAP-04.S02.T02 is DONE and independently approved.

| Material boundary | Selected proof |
|---|---|
| OA observations | Synthetic DOI resolution preserves all reported location URLs, host/license/version and access states. Unknown rights are not grants. Reject mismatched identifiers and unsupported queries; never fetch the returned full text. |
| Graph observations | Lookup, citation/reference direction and positive/negative recommendation seeds retain provider/query/time lineage. Reject normalized seed collisions and unresolved/null edges rather than invent IDs or silently claim empty coverage. |
| Admission and paging | Fixed HTTPS hosts, paths, methods and bounded POST body. Actual transport forwards exact JSON bytes. Response offset and advancing continuation bind the original provider/project/query; malformed/repeated/cross-query cursors deny. |
| Private configuration | Required Unpaywall contact uses broker-injected email; optional Semantic Scholar key uses x-api-key. Normal Core/worker wiring uses existing protected profile credentials. Missing/corrupt/unavailable settings are distinct from a successful empty result; recheck current configuration at cache/retry/new observation boundaries. |
| Secrets and authority | Current Intent, policy, exact confirmation and rights precede secret/network access. Rotation and nested/encoded echoes preserve lease cleanup and redaction; no values in diagnostics, SQLite, renderer, arguments or environment. |
| Durable outcome | Reuse the existing canonical page/checkpoint/workflow transaction. Real protected repository/worker tests cover provider failure, cancellation, interruption, restart/new confirmation, predecessor resume and preservation of prior accepted pages. |

First tests cover the mapping and wire contract before product edits. Focused
broker, transport/TLS, configuration, API/runtime and persistence checks follow.
The read-only independent preflight identified the hard-coded GET/empty-body
transport and absent production credential wiring; both are included, not left
as test-only configuration. No new identity store or schema migration is planned.

Configuration preflight also found that a lost DPAPI root above retained secret
records was recreated, making authenticated records appear absent. That would
misclassify a broken current connector configuration as optional keyless access.
A focused regression requires unavailable status, unchanged ciphertext and no
replacement root. The necessary fail-closed guard stays under the existing vault
lock; fresh empty-vault creation and restart remain supported. This is a direct
integration dependency correction, not a reopening of W1 acceptance or an
expansion of credential/recovery authority. Expanded security review applies.

Official API constraints checked 2026-09-24:
[Unpaywall REST API](https://data.unpaywall.org/products/api),
[OA location format](https://unpaywall.org/data-format),
[Semantic Scholar graph API](https://api.semanticscholar.org/api-docs/snippets),
[recommendation tutorial](https://webflow.semanticscholar.org/product/api/tutorial).
Unpaywall's retired search endpoint is not needed for the approved DOI OA
resolution outcome. Recommendation seed lists use a bounded HTTPS POST.

No live provider requests, account provisioning, real credential inspection,
full-text acquisition, canonical Work reconciliation or UI redesign is authorized
by these tests. Configuration values remain optional private local settings.
Source observations never confer downstream action permissions. Integrated
source-page UX, four-provider slice qualification and full Wave checks retain
their own required coverage; unit doubles are not live-provider evidence.
