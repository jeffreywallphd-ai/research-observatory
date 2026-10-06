# CAP-05.S01.T02 — permitted open-access acquisition

Claim base: `7a51dc94734f8be6c4a64a0c29de458e96b347bc`; owner:
`codex-w2-implementation`. Dependency CAP-05.S01.T01 is DONE and independently
approved. Authority: approved S01 plan §9.2, ADR-0019, ADR-0027, ADR-0028 and
ADR-0029's acquisition decision. The accepted 128 MiB / five redirect /
120-second limits override older planning forecasts.

| Material acceptance boundary | Implementation and proof |
|---|---|
| Exact permitted location | Resolve URL/license/version from the protected retained ConnectorRecord and exact assertion/address/ordinal. Immutable location copies are observations; existing current per-copy store/inspect policies decide permission. Test missing permission, sibling/substituted location, changed policy and source digest. |
| Real destination and privacy | Core requires current accepted Intent/privacy, exact session-bound preview confirmation, and bounded explicit redirect hosts. Pin public DNS answers to the actual socket while preserving hostname TLS verification. Test mixed/private/mapped addresses, port/scheme/userinfo, redirects and absence of credentials/cookies/referrer/proxy authority. |
| Content, checksum and bounded streaming | Stream through existing encrypted staging and signed LPAC inspection. Bound wire/expanded source to 128 MiB, operation redirects to five, attempts to three, elapsed transfer to 120 seconds, and concurrent downloads. Request identity encoding; unsupported encodings fail closed. Test spoofing, oversize, wrong expected digest, truncation and cancellation; missing expected digest stays missing. |
| Atomic durable identity | Candidate and protected source/license/download receipt share one transaction. Final document commit rechecks provider-copy policy and includes it in canonical provenance/dependencies alongside local rights. Test publication fault rollback, revocation, restart, confirmation and metadata-only preservation. |
| Compatibility | Additive v24 migration from the exact v23 schema captured at the claim base before product edits; preserve earlier fixtures, rows, rights, ciphertext and verified rollback. The independent fixture review exposed a missing operation row in capture02. Preserve its adverse bytes, populate the synthetic operation in capture03, and assert ZIP-extracted counts before migration. Test interruption and repeat/restart. |
| Principal proof | Exercise actual protected repositories, encrypted object store and signed LPAC inspector with an owned synthetic HTTPS fixture. Distinguish injected fixture DNS/CA from public internet; no live scholarly query or real research data. |
| Experience | T02 owns Core selection/download contracts. The queue and renderer selection/error/entitlement journey belongs to T03; no governed UI changes in T02. |

Start with focused failing location/transport behavior tests and preserve their
raw output. Qualify the committed implementation with acquisition, attachment,
rights, affected storage/migration, Core composition, lint/type/contract checks
and expanded independent security review. Full documents/security-local profiles
and integrated UI journeys remain slice/checkpoint/Wave qualification; no
automation framework source work, new parser, generic URL downloader, standing
egress grant, plaintext spool, implicit permission or range-resume claim.

Read-only independent preflight found no scope conflict. Its concrete identity,
socket-pinning, whole-operation bounds, atomic publication and restart invariants
are incorporated above. No mandatory unmet gate was found.
