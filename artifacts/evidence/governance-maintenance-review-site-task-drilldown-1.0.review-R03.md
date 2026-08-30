# Independent remediation review R03: dynamic planning-review task drill-down 1.0

- **Candidate commit:** `7abaad3b75c9aa9d9a338d510c4cd4a1e2385137`
- **Candidate predecessor:** `ca99b2a18383e9de9fd5cf570c91570b7425bd24`
- **R02 implementation commit:** `f97f5c631ac96663700ac4767e60fa421c97a83d`
- **Prior ledgers:** `artifacts/evidence/governance-maintenance-review-site-task-drilldown-1.0.review.md` and `artifacts/evidence/governance-maintenance-review-site-task-drilldown-1.0.review-R02.md`
- **Disposition:** `APPROVED`
- **Scope:** Commit-bound, risk-selected replay of the four R01 findings and `PRTD-R02-F01`, plus the incremental deterministic byte-comparison boundary: temporary regeneration safety, recursion, complete file inventory, normal determinism, and bounded performance. No product, planning, task, approval, or repository state was changed. The protected untracked `artifacts/evidence/W1.A04.B00.json` witness was not read, staged, edited, or deleted.

## Finding replay

| Finding | R03 disposition | Evidence |
| --- | --- | --- |
| `PRTD-R01-F01` — authored task plans omitted | **Remains closed.** The focused whole-corpus test passes all 337 authored task pages, including both repository heading forms and hash-bound plan projections. Normal exact regeneration passes. |
| `PRTD-R01-F02` — dependencies falsely rendered as none | **Remains closed.** Ordered dependency projection and canonical links remain source-derived; normal exact regeneration and the focused corpus test pass. |
| `PRTD-R01-F03` — branch/base claims omitted | **Remains closed.** Top-level owner/branch/base projection remains exact; normal exact regeneration and the focused corpus test pass. |
| `PRTD-R01-F04` — new test outside governed Python scope | **Remains closed.** Governed Python quality passes all 168 declared files. |
| `PRTD-R02-F01` — visible evidence can be falsified while metadata remains intact | **Closed.** `generated_site_byte_errors` regenerates the complete site from authoritative repository inputs into an OS temporary directory and byte-compares every generated file and the exact file inventory. Independent replay of the R02 attack now fails validation for both altered pages even though the manifest and `data-*` metadata remain intact. |

## Findings

No blocking or non-blocking findings.

## R02 adversarial replay

In a temporary copy of the generated site, the review preserved all metadata while:

1. replacing the visible `CAP-19.S01.T01` approved-plan article with fabricated text;
2. replacing the visible dependency label `CAP-18.S01.T03` with `CAP-00.S00.T00`; and
3. replacing the visible `CAP-03.S04.T01` branch with `fake/branch`.

The exact candidate validator exited 1 and reported:

- `CAP-03/CAP-03.S04.T01.html: visible content differs from deterministic regeneration`
- `CAP-19/CAP-19.S01.T01.html: visible content differs from deterministic regeneration`

An independent temporary-copy inventory probe added `UNEXPECTED.txt`; `generated_site_byte_errors` returned `Generated review-site file inventory differs from deterministic regeneration: missing=[] extra=['UNEXPECTED.txt']`.

## Incremental risk assessment

- **Write safety:** The actual `--site` tree is enumerated and read only. The retained manifest is copied into a fresh `TemporaryDirectory`; `build_site` cleanup and its generation lock are scoped to that temporary output and sibling lock path. No source or committed review-site path is passed as the regeneration output.
- **Recursion:** `plan_review_check` calls `build_site`; `build_site` does not invoke `plan_review_check`. The focused subprocess regression completed without recursion or nested validator growth.
- **Inventory:** The check compares the complete relative file set before comparing bytes, denying both stale/extra and missing generated files. Common-file byte comparison then denies any visible or non-visible drift.
- **Timestamp determinism:** Only the existing manifest is seeded. `build_site` retains its `generated_at` value and regenerates all other content from authoritative sources; normal validation therefore compares exact bytes without a clock exception.
- **Performance:** Normal validation of 491 generated files completed in 10.431 seconds on this Windows workspace. The seven-test focused suite, including a second complete tamper validation, completed in 20.562 seconds. This is bounded for the changed review-site control and creates no new controller, task state, approval, or universal task-level suite.
- **Cleanup:** Both normal and adversarial temporary regenerations completed and removed their temporary directories/lock files through context-managed cleanup. Repository status remained limited to the pre-existing protected untracked witness before this ledger was written.

## Checks performed

- `git rev-parse 7abaad3` -> `7abaad3b75c9aa9d9a338d510c4cd4a1e2385137`; `git rev-parse 7abaad3^` -> `ca99b2a18383e9de9fd5cf570c91570b7425bd24`.
- Exact predecessor-to-candidate diff review — three paths only: the bounded maintenance evidence addendum, focused task-drill-down regression, and existing planning-review validator.
- `git diff --check ca99b2a18383e9de9fd5cf570c91570b7425bd24 7abaad3b75c9aa9d9a338d510c4cd4a1e2385137` — pass.
- `.venv\Scripts\python.exe -m unittest -v tests.foundation.test_plan_review_task_drilldown` — pass, 7 tests in 20.562 seconds.
- `.venv\Scripts\python.exe tools/plan_review_check.py --repo .` — pass: 19 capabilities, 111 slices, 337 tasks, 487 HTML pages; 10.431 seconds. This invocation includes the new exact 491-file deterministic regeneration comparison.
- `.venv\Scripts\python.exe tools/quality_check.py --repo .` — pass: 168 governed files formatted, lint-clean, and type-safe.
- Independent R02 visible-content tamper replay — correctly rejected with exit 1 and exact errors for both altered task pages.
- Independent extra-file inventory probe — correctly rejected.

## Browser limitation

The earlier ledgers truthfully record that in-app `file://` control was denied by browser URL policy. R03 does not bypass that policy. Structural HTML, link inventories, native `<details>/<summary>`, exact generated bytes, and visible-content tamper denial are proven; live visual layout, focus order, keyboard operation, and assistive-technology behavior remain the disclosed manual check and are not represented as completed.

## Conclusion

Candidate `7abaad3b75c9aa9d9a338d510c4cd4a1e2385137` closes `PRTD-R02-F01` with one generic, deterministic comparison inside the existing validator. All prior findings remain closed, normal generation is byte-exact, both reviewer-visible tampering and file-inventory drift fail closed, and the temporary regeneration boundary is safe, non-recursive, and bounded. The exact candidate is approved for integration within the recorded maintenance scope.
