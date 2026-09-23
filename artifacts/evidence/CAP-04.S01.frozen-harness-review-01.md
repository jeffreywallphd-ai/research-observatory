# CAP-04.S01 frozen qualification harness preflight

Bounded verification increment; predecessor
`f850468ef679651b34af44611aa39c8d147c6074`, initial candidate
`1cde4b6ccf8b9253cd37f961057ddca191058798`. No product behavior, timeout,
security authority, migration, reference or acceptance criterion changes.
It adds one opt-in real frozen-Core journey and narrow harness control tests.
No full task/profile suite replay. Native observations are recorded separately.

Independent reviewer: `/root/w2_commit_increment_review`. Initial pre-execution
review found two blockers; the package was not executed at that candidate:

1. Readiness imported a helper using ambient proxy/default redirects while
   carrying a bearer token. Other requests already used a private opener.
   Correction shares proxy-disabled, redirect-denying GET/POST transport and
   strict readiness validation against the authenticated handshake. New readiness
   regression failed before implementation (missing ready method), then passed.
2. Manifest member reads used the second import's preview with the original
   manifest revision. Production correctly rejects that authority substitution.
   Correction reads through the returned manifest's original preview, retaining
   latest-commit discovery through the second import. A focused address regression
   checks the accepted preview and rejects another project's manifest. Production
   cross-preview denial is unchanged.

Five harness control tests and focused Ruff pass after these corrections.
Exact committed recheck and independent closure are still required; this owner
note does not self-approve the corrections or claim frozen execution succeeded.
Risk selection: new HTTP/control-pipe test authority, explicit synthetic-vault
key permission, real child-process ownership/cleanup, authenticated immutable
artifact bytes, no content/token logging, durable reimport/restart outcomes.
The test uses ordinary production protection and an explicitly authorized
synthetic project; it does not inspect existing secrets, alter sign-in settings,
launch the full production desktop or establish signing/performance/crash proof.

## Appended pre-execution closure and setup attempt

Reviewer independently approved both corrections at
`cd03f8c13c71744bc8461f9d9cab3540cd376bb7`. Exact-candidate five control tests
passed (0.002s), plus Ruff/format. Reviewer authenticated the package report
SHA256 `756ced212ed46a95b21322bdcd224c3c4d6e3a2bc19fb712f3df1995800ea13f`
and all 710 files/48,318,165 bytes against schema, inventory and build contract.

The first actual invocation failed before Core launch: the reused package guard
reported `Core package snapshot write denial is ineffective` on the original
build directory. Retained report:
`artifacts/tmp/import-frozen-windows-rqfizlcd/result.json`; log:
`artifacts/tmp/CAP-04.S01.frozen-qualification-01.log`. No project key was created.
The guard restored its temporary deny entry; its empty probe was moved into the
failed fixture, preserving it and restoring the original exact package inventory.

Cause established to the bounded level needed here: the runner guarded original
build output instead of using the existing benchmark's disposable-copy route.
No claim is made about a deeper Windows ACL cause. The same guard on a fresh
copied package passed write denial and exact inventory validation without any
Core launch. That fixture is retained in the producer repository under
`artifacts/tmp/cap04-snapshot-guard-3sk81owu`.
The runner now copies into a short-path confined disposable directory, guards
and verifies that copy throughout both child lifetimes, and leaves original
package bytes untouched. Neither the guard nor its assertions were weakened.
Independent incremental review remains required before retry.

## Appended cancellation-contract correction

Independent pre-execution review approved the disposable-copy correction at
`77fe2993f90ce1a880794ab0ce1646d9795b0a68`. Attempt 02 then launched frozen
Core and reached synthetic intake and cancellation, but failed before commit:
the harness expected an empty latest-commit result from a cancelled preview.
Production correctly returned HTTP 409 / `RO-CORE-IMPORT-REVIEW-UNAVAILABLE`.
Retained report: `artifacts/tmp/import-frozen-windows-1ahoyg0a/result.json`;
log: `artifacts/tmp/CAP-04.S01.frozen-qualification-02.log`. Its synthetic
project/key and package copy remain retained; this is not a passing journey.

The missed boundary was cancellation revoking review authority, not deletion of
audit data. The harness now checks the empty result before cancellation, requires
the precise denial afterwards, and independently counts canonical publication
tables in only its newly created protected database. Counts must be zero after
cancellation and exactly two sources, one manifest, three members and one seal
after reimport/restart. The count audit uses the existing protected connection
and the exact synthetic project ID; it neither enumerates vault entries nor
changes product behavior. A focused control test verifies project-scoped reads
and connection closure on failure. Independent incremental review and a fresh
focused execution remain required; no broader suite replay is selected.

## Appended scientific-identity correction

The reviewer approved the cancellation correction at
`c710adb5baa0f955ecc71f7b604b5caec99f2d5a`. Attempt 03 executed at
`8d932f185b9037b4d08c2f749fd36197c1057859` (only a pending performance
baseline JSON was added; harness/product bytes were unchanged). It proved zero
publication counts after cancellation, then failed a new-preview manifest-equality
expectation. Retained report: `artifacts/tmp/import-frozen-windows-j8spugmv/result.json`;
log: `artifacts/tmp/CAP-04.S01.frozen-qualification-03.log`.

Root cause: the harness conflated identical source bytes with identical scientific
input authority. ADR-0027 binds the immutable mapping-profile revision as well as
source, selection and decisions. Public `begin-review` creates a new profile for
each preview; the public mapping command does not select a prior profile. The
existing publication test `test_same_file_new_preview_reuses_source_assertion_ids`
therefore requires source-record reuse, not manifest equality. Its distinct
`test_same_scientific_import_reuses_manifest_and_records` covers identical draft
authority. No product defect or scope change is inferred from this failed assertion.

The corrected frozen journey explicitly checks both outcomes: replay of the same
draft returns the exact manifest; a new preview/profile records a new manifest
with zero created and two reused source records. After restart both manifests
must retain identical ordered members/source identities, and exact database counts
must be two sources, two manifests, six members and two seals. Cancellation still
requires all-zero counts. The preceding expectation of one manifest was harness
error, not an accepted contract being relaxed. All three failed invocations remain
retained; no production test, deadline, identity algorithm or protection changes.

Independent review at `d75f791a2713ba0f2f8bb44a00736b4050e0cabb` agreed with
the scientific-identity correction but requested a P2 public-response-shape fix:
the assertion used internal `mapping.profileId`; `ImportManifestView` exposes
`mappingId`. No execution occurred at that candidate. The correction uses the
public field and adds a focused public-shape regression that also rejects newly
created records, a reused profile identity or changed source bytes. The regression
failed before its helper existed. Root cause was using the domain manifest rather
than the API projection when writing the assertion; the request/response contract
is now an explicit harness acceptance boundary. Prior findings remain preserved.
