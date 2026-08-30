# Independent remediation review R02: dynamic planning-review task drill-down 1.0

- **Candidate commit:** `f97f5c631ac96663700ac4767e60fa421c97a83d`
- **Candidate predecessor:** `8ba967cd1735d92781a18042a240f10808548cb4`
- **Original R01 candidate:** `df41ee045a4816e53a92180f1df58fa6196e36f1`
- **Prior ledger:** `artifacts/evidence/governance-maintenance-review-site-task-drilldown-1.0.review.md`
- **Disposition:** `CHANGES_REQUESTED`
- **Scope:** Commit-bound, risk-selected replay of `PRTD-R01-F01` through `PRTD-R01-F04`, followed by review of the incremental parser, task projection, validator, generated-site, and quality boundary. No product, planning, task, approval, or repository state was changed. The protected untracked `artifacts/evidence/W1.A04.B00.json` witness was not read, staged, edited, or deleted.

## R01 finding replay

| Finding | R02 result | Evidence |
| --- | --- | --- |
| `PRTD-R01-F01` — 253/337 task plans omitted | **Closed for the generated candidate.** `extract_task_section` now accepts both repository heading forms, rejects duplicate identities, and site generation fails if any authored task section is absent. The manifest carries the source-section SHA-256. Independent corpus replay found 337 task entries, 0 missing plans, and 0 manifest/source plan-hash mismatches; the legacy `CAP-19.S01.T01` plan is visibly present in its generated page. The remaining validator-truth defect is recorded separately as `PRTD-R02-F01`. |
| `PRTD-R01-F02` — dependencies falsely rendered as none | **Closed for the generated candidate.** The generator now reads ordered `dependencies`, emits canonical links and task-keyed dependency attributes, and the validator compares manifest and page inventories to the backlog. Independent replay found 0 dependency-manifest mismatches; `CAP-19.S01.T01` visibly renders `CAP-18.S01.T03`. |
| `PRTD-R01-F03` — branch/base claim omitted | **Closed for the generated candidate.** Top-level owner, branch, and base SHA take precedence with legacy nested-claim fallback. Independent replay found 0 claim-manifest mismatches; `CAP-03.S04.T01` visibly renders owner `codex`, branch `codex/w1-windows-local-runtime`, and base `c9260e1e981fea84a651dd59104aad12e1fb8d8e`. |
| `PRTD-R01-F04` — governed Python quality scope incomplete | **Closed.** `tests/foundation/test_plan_review_task_drilldown.py` is listed in `quality-scope.json`; formatting, lint, and typing pass all 168 governed files. |

## New blocking finding

### P1 / blocking — PRTD-R02-F01 — The validator trusts metadata assertions while allowing falsified visible task evidence

The remediation adds authoritative hashes and task values to manifest entries and `data-*` attributes, but `tools/plan_review_check.py:739-791` verifies the attributes rather than the visible content they purport to bind. A temporary-copy adverse probe preserved those attributes while:

1. replacing the complete visible `CAP-19.S01.T01` task-plan article with `FABRICATED APPROVED PLAN`;
2. changing the visible dependency code from `CAP-18.S01.T03` to `CAP-00.S00.T00` while retaining the original dependency attribute and link; and
3. changing the visible `CAP-03.S04.T01` branch to `fake/branch` while retaining the authoritative branch attribute.

Running `.venv\Scripts\python.exe tools/plan_review_check.py --repo <repo> --site <temporary-mutated-site>` still exited 0 and reported `Planning review site: pass - 19 capabilities, 111 slices, 337 tasks, 487 HTML pages`. No repository file was modified by this probe.

**Impact:** A syntax-valid generated-site commit can display fabricated approved implementation intent or false dependency/claim information to the reviewer while the strengthened validator reports success. The exact candidate's committed pages are currently truthful—independent deterministic regeneration produced 0 byte differences—but the validator does not itself establish the claimed visible evidence truth and can allow the same class of false projection to recur.

**Required closure:** Make the validator derive and compare visible task-plan, dependency, and claim content from the authoritative sources rather than accepting parallel self-asserted attributes. A generic exact temporary regeneration/byte comparison is acceptable if it remains a check rather than a new controller or approval gate; targeted canonical-content comparison is also acceptable. Add an adverse regression that preserves all manifest values and `data-*` markers, mutates the visible plan/dependency/claim content, and requires validator failure.

## Checks performed

- `git rev-parse f97f5c6` -> `f97f5c631ac96663700ac4767e60fa421c97a83d`; `git rev-parse f97f5c6^` -> `8ba967cd1735d92781a18042a240f10808548cb4`.
- Exact incremental diff review from `8ba967cd1735d92781a18042a240f10808548cb4` to the candidate: R01 remediation evidence, generator, validator, focused test, quality-scope entry, manifest, and regenerated task pages only.
- `git diff --check 8ba967cd1735d92781a18042a240f10808548cb4 f97f5c631ac96663700ac4767e60fa421c97a83d` — pass. The broader original-candidate-to-remediation check also passed.
- `.venv\Scripts\python.exe -m unittest -v tests.foundation.test_plan_review_task_drilldown` — pass, 6 tests.
- `.venv\Scripts\python.exe tools/plan_review_check.py --repo .` — pass: 19 capabilities, 111 slices, 337 tasks, 487 HTML pages.
- `.venv\Scripts\python.exe tools/quality_check.py --repo .` — pass: 168 files formatted, lint-clean, and type-safe.
- Independent source/manifest corpus replay — 337 tasks, 0 missing plans, 0 dependency-manifest mismatches, 0 claim-manifest mismatches, and 0 source/manifest plan-hash mismatches.
- Deterministic temporary regeneration retaining committed `generated_at` — 491 committed files, 491 regenerated files, 0 SHA-256 differences.
- Temporary visible-content tamper probe described in `PRTD-R02-F01` — validator incorrectly passed.

## Browser limitation

R01 already records that the in-app browser rejected local `file://` reload under URL policy. No bypass was attempted in R02. Native `<details>/<summary>`, exact structural inventories, static links, and deterministic bytes remain proven; live visual layout, focus order, keyboard operation, and assistive-technology behavior remain an explicit manual check and are not relied upon for this disposition.

## Conclusion

The remediation closes all four R01 defects in the exact generated candidate, but the new evidence bindings are not enforced against the content a reviewer actually sees. Because a reproducibly falsified task page still passes the validator, the evidence/control surface is not ready for integration. Close `PRTD-R02-F01` with one generic visible-content or exact-regeneration check and append-only re-review; no new workflow identity, approval, or controller is warranted.
