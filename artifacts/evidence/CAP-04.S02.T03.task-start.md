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
| Native configuration journey | Source Manager Configure opens an owned native form, never a renderer secret field. Shared dialog admission prevents overlap; navigation/project/lock/close invalidates pending input. Cancel/Escape before Save admission changes nothing and restores focus. Existing values are not prefilled or returned; preserve flags require the exact current CAS version. |
| Save acknowledgment | Admission is a short protected state transition, not network I/O under the security mutex. Once transmission is possible, lost acknowledgment or stale context means save-unconfirmed, never cancelled/unchanged. No automatic retry; reopen to inspect current presence/status and explicitly edit from its current version. A changed version alone cannot identify the earlier writer. Test both sides of admission, competing writes and dropped replies. |
| Normal researcher permission path | Preflight found the Intent form omitted existing egress policy and native validation rejected it, leaving fresh projects local-only. Restore ADR-0023's existing policy vocabulary in the approved Scope/evidence region, through unchanged impact/draft/acceptance. Preserve unfamiliar destinations and approved-redacted mode; never grant authority from Test. Prove native optional-field compatibility and the fresh-project permission journey. |
| Durable inspection and recovery | Preflight found transient job notices and generic Task Center rows cannot identify an uncertain source submission. Add a bounded read-only view over existing protected operations/observations, showing exact request/preview identity, source/query, time, outcome and coverage. Reopening reads accepted facts without rerunning the provider or inferring zero coverage. |

Development checks (not candidate qualification): real native supervisor/Core
and isolated DPAPI/SQLCipher save, stale-write denial, replacement and restart
pass through `source-configuration-native-integration.mjs`. The first harness
run lacked workflow-session startup authority; the explicit fixture-session
composition now uses the normal authority. Built renderer light/dark checks
pass explicit preview/send, unavailable/ambiguous outcomes and navigation-away
focus behavior. They exposed and fixed focus restoration before React re-enabled
the Configure button. The shared current-runtime fixture also needed the
existing local-only `egressPolicy` projection; historical fixtures remain intact.

Native GUI launch preparation must use `build_project_probe()` from
`tests/service/test_native_project_contract.py`, not plain `cargo build`:
the example needs the existing Common Controls v6/asInvoker manifest. Plain
build attempts failed before UI startup with `STATUS_ENTRYPOINT_NOT_FOUND`;
the existing helper verifies the actual embedded manifest. No system settings,
dependency pins, or production privileges were changed to repair that attempt.

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

Incremental preflight exposed duplicate preview IDs when generic Task Center
retry continuations appeared in recent source history. A real queue regression
reproduced the failure. The recent projection now excludes continuation runs
and exact lookup remains bound to the original confirmation's idempotency key;
Task Center keeps the continuation history. This changes no retry authority.
Focused inspection tests cover absent/pending/accepted observations, rights,
bounded offsets, exact restart recovery and no redispatch. Normal Core restart
also preserves inspected OA location host/license data. All remain development
observations until committed-candidate qualification and independent disposition.

The repeated-inspection renderer regression first failed in both themes:
selecting the same preview ID did not trigger a new read. Each explicit selection
now carries a fresh UI request identity; the passing test also proves record
paging, literal rendering of hostile markup, OA host/license display and no
additional provider confirmation. The new Intent interaction test proves
explicit destination selection, impact invalidation, draft persistence and no
automatic acceptance. Its first draft fixture returned stale revision 1 on
reload; fixing that double preserved the product assertion.

The isolated native GUI created and opened its synthetic project successfully,
but its historical fixture guard denied the read-only capabilities GET. A new
failing/passing native regression adds only that exact route, with no body,
query, conditional header or idempotency key; project-root restrictions remain.
The window closed cleanly with no pending dialog. Native settings interaction
is still pending; no provider request or ordinary user-profile access occurred.

Focused rendered contrast/reflow qualification exposed a material accessibility
gap: Source Manager policy links inherited the shell's light-theme link token
in dark mode (3.595:1 on the card background, below the required 4.5:1).
The missing acceptance check is actual rendered link contrast in both themes,
not token-name parity alone. Reuse the approved dark brand token in the existing
shared link rule; retain the failing report and require contrast, reflow and
theme captures at all three supported desktop widths before disposition.
