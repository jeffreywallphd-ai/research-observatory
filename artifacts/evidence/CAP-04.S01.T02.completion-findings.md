# CAP-04.S01.T02 — final interaction findings

These are pre-submission findings, not invented taskctl review rounds. Preserve
earlier checkpoint adverse findings and their independently reviewed closures.

| ID | Finding / source | Smallest closure |
|---|---|---|
| CF01 (P2) | Actual e80 native run: batch badge remained runnable/ready after the selected pane showed ready/cancelled. | Guarded authoritative pane replies update the matching list item; pending lists retain newer replies. No extra polling or cache. |
| CF02 (P2) | Independent `w2_ux_plan_review` readiness audit: background parse and summary completion updated non-live badges only. | Existing shared live region receives deduplicated status transitions. No new notification framework or styling. |

The missed experience/async rows were appended to the task-start worksheet before
the respective product fixes. CF01 regression first failed at the ready badge
(10.218s); initial correction passed (15.825s). CF02 regression then failed at the
missing live announcement (10.277s). Both tests used the actual built renderer,
generated client and real fixture Core composition with explicit native doubles.

Corrected exploratory run passed in 17.132s: running-to-ready list status, mapping,
summary/candidates in both themes, completion announcements, unchanged-refresh
announcement suppression, grouped correction/exclusion/undo, report, cancelled
list status, delayed older list response, and late status after unmount. Types,
desktop lint and focused Python lint also pass. These are pre-commit results;
exact-candidate verification and independent disposition still follow.

CF01's read-only correction preflight found no material ownership, race or cursor
blocker. CF02 readiness audit otherwise found the required T02 journey implemented.
Neither preflight is whole-task approval. Canonical commits/manifests remain T03;
Work/Version reconciliation remains CAP-04.S03; broader packaged, accessibility,
security and integration matrices remain slice/Wave qualification.
