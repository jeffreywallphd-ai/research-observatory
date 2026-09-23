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
