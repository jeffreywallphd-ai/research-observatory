# Independent review: dynamic planning-review task drill-down 1.0

- **Candidate commit:** `df41ee045a4816e53a92180f1df58fa6196e36f1`
- **Predecessor commit:** `3e05ca07fc669a8d45cf3cc843ea8387d7757d0d`
- **Disposition:** `CHANGES_REQUESTED`
- **Review scope:** Commit-bound, read-only review of the generated Wave -> capability -> slice -> task drill-down, task pages and optional task-start worksheets, generated manifest and validator integrity, evidence truth, and credible regressions. No product, planning, task, approval, or repository state was mutated. The protected untracked `artifacts/evidence/W1.A04.B00.json` witness was not read, staged, or modified.

## Findings

### P1 / blocking — PRTD-R01-F01 — The task-plan extractor drops approved task detail for 253 of 337 generated task pages

`tools/plan_review_site.py:61-66` recognizes only headings shaped like `### 9.N \`<TASK-ID>\``. Approved slice plans also use the repository's earlier heading shape `### <TASK-ID> — ...`; for example, `planning/slice-plans/CAP-19/CAP-19.S01-reviewer-protocol-roles-and-independence.md:228` contains an authored `CAP-19.S01.T01` section, while `planning/review-site/CAP-19/CAP-19.S01.T01.html:54` says, “No task-specific Section 9 plan was found.” A read-only corpus audit over the manifest's 337 task entries and their source plans found 253 empty `extract_task_section` results. The focused test at `tests/foundation/test_plan_review_task_drilldown.py:96-105` covers only the new numbered/backticked shape, and `tools/plan_review_check.py` checks generic page markers rather than requiring the source task section to be found and rendered.

**Impact:** The primary requested drill-down omits approved implementation intent from about 75% of task pages even though both the focused tests and site validator pass. Reviewers can therefore mistake an extraction failure for absent task planning.

**Required closure:** Parse every repository-supported task heading shape using the immutable task identity, require each authored task section to resolve exactly once, bind that section (or its source hash/range) in the manifest/validator, and add both a legacy-heading regression and a whole-corpus assertion that all 337 authored tasks have nonempty task-plan projections.

### P1 / blocking — PRTD-R01-F02 — Every authored task dependency projection is false

`tools/plan_review_site.py:1918` reads `task.get("depends_on", [])`, but authoritative task records use `dependencies`. For example, `planning/backlog.yaml:27349-27350` gives `CAP-19.S01.T01` dependency `CAP-18.S01.T03`, while `planning/review-site/CAP-19/CAP-19.S01.T01.html:47` renders `Dependencies: None`. A read-only backlog/manifest/page audit found all 337 authored task pages have nonempty `dependencies` and all 337 render the empty-dependency branch. The validator compares task identity/title/status and review history, but not the rendered dependency projection (`tools/plan_review_check.py:699-751`), so the false pages pass validation.

**Impact:** The pages label this section “Authoritative task record” while suppressing the dependency boundary that governs readiness and review scope. This is a material evidence-truth defect.

**Required closure:** Project the authoritative `dependencies` field, retain canonical cross-capability links where a task page exists, and make the validator compare the exact ordered dependency inventory rendered on every task page against the backlog. Add a regression using a real current-schema task rather than a synthetic alternate schema.

### P2 / blocking — PRTD-R01-F03 — Branch and base-commit claim data are omitted for every authored task that has them

`tools/plan_review_site.py:1916` assumes a nested `claim` object and `tools/plan_review_site.py:1951` falls back to top-level `owner` only. The backlog stores `branch`, `base_sha`, and `lease` at task top level. The active `CAP-03.S04.T01` record has branch `codex/w1-windows-local-runtime` and base `c9260e1e981fea84a651dd59104aad12e1fb8d8e` at `planning/backlog.yaml:11011-11028`, but its task page renders branch/base as `none`. A read-only audit found all 36 authored tasks with a top-level branch or base value have at least one such false `none` projection.

**Impact:** The review page loses the exact branch/base boundary needed to understand a claimed task and can present an in-progress task as unbound to a candidate history.

**Required closure:** Render the actual top-level task claim schema (including lease only if intentionally in scope), validate the rendered claim values against the backlog, and cover the active claimed task plus a completed task in regression tests.

### P2 / blocking — PRTD-R01-F04 — The candidate fails the governed Python quality boundary

The candidate adds `tests/foundation/test_plan_review_task_drilldown.py` but does not add it to `quality-scope.json` (whose nearby planning-review inventory currently includes `tests/foundation/test_plan_review_amendments.py` at line 128). Running `.venv\Scripts\python.exe tools/quality_check.py --repo .` exits 1 with `ERROR: governed Python files are unlisted: tests/foundation/test_plan_review_task_drilldown.py`.

**Impact:** The new regression suite is outside the repository's declared formatting, lint, and type-check inventory, and the candidate does not satisfy its own stated affected planning-check boundary.

**Required closure:** Add the new test to the existing quality scope and rerun the governed quality check. This is maintenance of an existing check, not a new approval or controller.

## Checks performed

- `git rev-parse df41ee0` and `git rev-parse df41ee0^` resolved the exact candidate and predecessor above.
- `git diff --check 3e05ca07fc669a8d45cf3cc843ea8387d7757d0d df41ee045a4816e53a92180f1df58fa6196e36f1` — pass.
- `.venv\Scripts\python.exe -m unittest -v tests.foundation.test_plan_review_task_drilldown` — pass, 5 tests. This proves generated inventory/link markers, native `<details>` structures, canonical task-page names, and helper-level worksheet behavior, but its synthetic task-plan fixture does not represent both approved heading styles.
- `.venv\Scripts\python.exe tools/plan_review_check.py --repo .` — pass: 19 capabilities, 111 slices, 337 tasks, 487 HTML pages. The findings above show that the validator currently proves structural self-consistency but not all authoritative task-field values.
- Deterministic temporary regeneration using `build_site` with the committed `generated_at` retained — 491 committed files, 491 regenerated files, 0 SHA-256 differences.
- Read-only corpus projection audit — 253/337 task-plan sections missing; 337/337 nonempty task dependencies rendered as none; 36/36 task pages with branch/base data omit at least one value.
- `.venv\Scripts\python.exe tools/quality_check.py --repo .` — fail due to the unlisted new governed test (PRTD-R01-F04).
- `.venv\Scripts\python.exe tools/repository_structure_check.py --repo .` — pass: 12 required modules.
- Optional worksheet inventory — zero `artifacts/evidence/*.task-start.md` files currently exist. The exact-path absence projection and helper-level present/absent behavior pass, but no committed assigned worksheet exists for end-to-end body/hash verification in this candidate.

## Browser limitation

The attempted in-app reload of the local `file://` review site was rejected by the browser URL policy. No policy bypass was attempted. Deterministic regeneration, HTML parsing, exact inventory/link validation, and the use of native `<details>/<summary>` elements are sufficient evidence for generated-file identity, structural hierarchy, and static navigation targets. They are not evidence of final visual layout, focus order, keyboard behavior, or assistive-technology behavior in an actual browser; that remains an explicit manual check after remediation, consistent with the maintenance evidence boundary.

## Conclusion

The commit deterministically generates a complete structural task-page inventory and retains optional worksheets as non-gating, but it is not ready for integration. The generated pages omit most authored task plans, falsely erase every task dependency, omit real claim bindings, and fail the repository's existing governed Python quality check. The candidate must be remediated and independently re-reviewed against these four append-only findings.
