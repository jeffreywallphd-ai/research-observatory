# CAP-05.S06.T02 — independent pre-submission findings

Reviewed candidate: `bbd00cb8f8d604e00058fb571ffcb471fb01d48f`.
No task submission or formal review round existed at this candidate. The
independent agents `/root/parsing_quality_review` and
`/root/reader_table_figure_review` reported the following material P2 findings.
Their messages and the reproduced adverse outputs are retained; this record
does not invent a formal R01 or approve the subsequent remediation.

| Finding | Contract and immediate cause | Smallest reproduced regression |
|---|---|---|
| Guided stage/Return loses local ownership | Approved correction recovery and shared navigation: ApplicationRuntime's stage/Return callbacks assigned the workspace directly, bypassing the leave-page guard. | `tests.desktop.test_quality_workflow_navigation`: all six dirty/busy/unknown × stage/Return cases fail before the fix; `artifacts/tmp/CAP-05.S06.T02.navigation-adverse-03.log`. The mounted production root uses declared child/transport doubles, not Native authority proof. |
| Excluded reference text becomes derived metadata | Approved exclusion and immutable original evidence: field and identifier fallback scans read the retained ancestor without screening authenticated excluded intervals. | `tests.documents.test_document_correction_lineage.CorrectionLineageTests.test_excluded_reference_fields_and_identifiers_cannot_reappear_in_fallback_scans`; `artifacts/tmp/CAP-05.S06.T02.adverse-pre-submission-core-01.log`. Original raw observations stay retained; excluded derived title and active DOI must disappear while unaffected values remain usable. |
| Preview-only split tail is hidden | Reviewable proposed-versus-accepted correction: pagination counted only accepted nodes, hiding the21st proposed node after a split. | `tests.documents.test_document_correction_repository.DocumentCorrectionRepositoryTests.test_preview_only_tail_has_a_second_page_without_advancing_accepted_head`; the same Core adverse log. Real protected repository page returns20 accepted/20 proposed and incorrectly no continuation before the fix. |

Navigation adverse attempts01/02 were fixture setup failures (collapsed All tools
and an incorrect tool label), not product findings. Attempt03 establishes the
six product failures. The missed acceptance rows were updated before remediation.
The exact corrected committed candidate requires fresh checks and independent
finding closure before task completion.

The initial fixed-candidate producer
`artifacts/tmp/CAP-05.S06.T02.qualifying-focused-01.json` also remains FAIL.
Its passing child checks are preserved. ADR coverage and inherited architecture/
desktop lint findings remain explicit. Its own fixture-path assertion incorrectly
treated a JSON seed receipt as a bare path, stopping before the actual Wry journey;
that run provides no fresh renderer/Native/Core acceptance proof. Correcting only
the ignored task-owned producer does not change the shared automation framework.

The independent Native/UI advisory found no further concrete Native/codec/Reader
blocker. The Wry component host does not mount ApplicationRuntime or prove real
OS keyboard/UIA focus, an actual in-flight Lock/window replacement, shipping
installation, parser accuracy or full Wave qualification. These limits remain
separate from the narrow checks and later S06/W2 qualification requirements.
