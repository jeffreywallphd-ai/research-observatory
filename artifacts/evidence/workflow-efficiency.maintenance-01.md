# Workflow efficiency — bounded maintenance

Authority: the owner requested implementation of the proposed workflow
improvements. GOV-MIG-0001 permits bounded independently reviewed automation
maintenance. This record is not a Wave/product approval or a new controller.

Predecessor: `637d3fce92e02c9d1ced47e24a43e21c543b8c65` on the existing Wave
branch. W1 is quiescent PAUSED in ordinary scope; W1.A08 is adopted. The
unapproved ECR-0009 proposal is not execution authority. No live backlog,
product, release, remote, user-data or authentication mutation is part of the
maintenance implementation.

## Intended delta and risk

Tier 2 evidence/control maintenance, split into independently reviewable
components without new approval gates:

1. Reconcile retired recovery guidance; codify fixed acceptance scope,
   nonduplicative review, risk-selected tests, stable verification inputs and
   truthful timing/cost reporting in the existing operating contract.
2. Add one generic linked corrective-task route in the existing task adapter,
   inheriting completed-task authority and normal review controls without an
   ECR/bootstrap/adoption cycle. Preserve the original task and amendment.
3. Generate automatic factual transition/test receipts; test an isolated,
   explicitly bounded stdlib workload. Unsupported/unknown runtime closure is
   fresh-only, not an optimistic cache hit.
4. Automate sealed, baseline-backed preservation checks for private metadata
   at the same typed logical fields and raw bytes. Keep full unmasked credential
   scans and independently pinned installation boundaries.
5. Project linked corrections in the existing Wave and backlog review views.

No journal cutover, new recovery/controller generation, architectural/product
scope expansion, fresh native/packaging claim, privacy-baseline advance,
historical rewrite, remote side effect or release approval is authorized.
Existing independent review and full Wave qualification obligations remain.

## Acceptance closure and selected proof

| Criterion | Material boundary | Selected proof |
|---|---|---|
| WF1 | Guidance/operating contract cannot authorize acceptance drift or weak evidence | Protocol negative tests plus cross-document review. |
| WF2 | One linked correction, exact inherited authority and preserved history | Synthetic real-Git/taskctl tests for claim, persistence, submission, review, old-reader denial, release/hold/dependency/stale-state rejection. |
| WF3 | Receipt truth and stable isolated execution | Real child-process pilot; failure, drift, timeout, output/provenance/publication negatives; fresh-only when closure unavailable. |
| WF4 | No new account/path/credential disclosures | Real-Git index/history/hook tests; typed-field and raw-byte equality; aliases, duplicates, copied fields, credentials and parser/installer pin substitutions. |
| WF5 | Corrections cannot disappear from human progress | Projection and tampering tests; original empty-collection output compatibility. |

Changed-path lint/type/format and affected workflow/security regressions are
required. Full W1 product/native/packaging qualification is deferred to W1 exit;
this maintenance does not run ordinary user data or services. Independent
review binds the actual final candidate, not this implementation intention.

## Predecessor byte bindings

Git preserves all exact predecessor files at the commit above. SHA-256 of the
affected entry/control files before edits:

| File | SHA-256 |
|---|---|
| AGENTS.md | 1b13d3718673525ff1d5ec09d941ccd4f081b1609abe24dbaa4a0d4ca9eeee94 |
| agent-protocol.json | 9d9e7ca89845a2876e1e15eeeacc8a8b17f4f9d653396ea3b966852f947842b3 |
| tools/taskctl.py | 40e5e014b343cde302d93d215150c269769c62e1edaebd371a31f1f7d4784d60 |
| planning/backlog.schema.json | 793c0f1186bba263460009a300b8f3c09c4e8b47e62982743a9551db8dfa208d |
| tools/prospective_privacy.py | 70dd83e4056b2a3b36563a4cea71de39aea51f69c288289593b6a1b2d5845bcb |
| tools/install_privacy_hooks.py | 01eb4122a06397e2c2a3e01add13eaee85d0824ba27e8e61cd0a35e8ab76dbaf |

## Initial observations (not completion evidence)

- Protocol substitution tests first failed for all six newly constrained
  fields; after implementation all 8 protocol tests passed (0.006 s observed
  test time; another run 0.005 s).
- Two corrective view tests first failed because their new projection APIs did
  not exist; after implementation, those plus the summary/plan correction test
  passed (3 tests, 0.021 s).
- An initial multi-file patch was rejected atomically on an unmatched context;
  no partial file edit occurred. Corrected patches were then applied.

Final candidate, measured checks, limitations and independent disposition are
recorded separately after implementation. No savings, token/credit amount or
completion is inferred from these initial observations.
