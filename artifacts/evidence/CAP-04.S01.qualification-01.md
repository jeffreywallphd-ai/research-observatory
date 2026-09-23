# CAP-04.S01 integrated qualification

Draft; no slice completion or approval claimed until all pending rows close.

Authority: the complete W2 packet at
`c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`, including
`planning/slice-plans/CAP-04/CAP-04.S01-reference-library-and-file-imports.md`.
Tasks CAP-04.S01.T01–CAP-04.S01.T03 have independent approved dispositions.
No approved packet, criterion, security authority or experience reference changed.

## Evidence matrix

| Slice boundary | Evidence and exact scope |
|---|---|
| Five-format fidelity, malformed isolation, raw/unknown fields, bounded parsing | CAP-04.S01.T01.json and review-R01 at 3d5cdd9e; named parser/contract tests retain adverse macro/warning findings and closures. Fresh parser scale measurements are in the slice performance report. |
| Mapping, corrections, group review, exclusions/undo, complete reports | CAP-04.S01.T02.json and review-R01 at 552eae1c; reviewed checkpoint lineage and real built renderer/Core interactions. Native bridge doubles are not native proof. |
| Atomic canonical IDs/manifests, current rights, predecessor/replay, publication failure/cancellation | CAP-04.S01.T03.json and review-R01 at 42efdbd9; 65 selected atomic/guard/worker cases at c136912f plus final renderer and three-process proof. No Work merge or verified scholarly claim is inferred. |
| Interrupted publication and process recovery | Five-case final journey at 42efdbd9: 39.537s, no skips; log SHA256 d6f325701fc1a3002cae72c0fd77c8c30d0ec2dde783af917668df5b09ef5665. Three-process report import-commit-process-5mnyex6r/result.json SHA256 11cd9a17372254e7f5442396e82e6e106f14d7e6cbe9dc0af815710f2d19f11d. Normal close/rollback, new processes, preserved resume authority; not abrupt-kill/stale-lock proof. |
| Migration, privacy and malicious/bounded input | Retained task reviews identify exact protected v11→v12 and v12→v13 migration/rollback fixtures, current and off-page rights denials, formula handling, malformed/oversized inputs, redacted reports and forged authority/receipt rejection. Unchanged task evidence is not relabeled a fresh profile execution. |
| Native researcher path, restart, same-draft replay and semantics | CAP-04.S01.native-qualification-01.md at f850468e (product 42efdbd9): real Windows dialogs/bridge/DPAPI/SQLCipher, isolated Python-backed native probe. Keyboard and semantic tree observed in both themes; no spoken screen-reader or production-native-package claim. |
| Frozen production Core composition | CAP-04.S01.frozen-harness-review-01.md: final c959ccdc attempt04 PASS26.388s, two actual frozen processes, loopback HTTP/control pipe, normal protected vault synthetic keys. Cancellation leaves zero canonical outputs; same-draft replay, distinct-profile source reuse and restart preserve identities. No installer/signing or crash-recovery claim. |
| Representative 100k workload, regression limits and bounded memory | cbc5e073 invocation FAILED: parser and two review samples passed, first commit sample passed; second commit sample interrupted at 900.874s against its 900s worker observation limit. See CAP-04.S01.performance-qualification-01.md. Failure retained; no overall performance qualification or minimum-hardware, OS cold-cache or UI-read-latency claim. |
| Public downstream handoff | Two public-contract consumer tests PASS at 77037d3c; exact public manifest/members/rights from frozen run, only public JSON schemas, immutable source IDs, exclusions/provenance, unknown rights and current reauthorization. |
| Import-pane visual/accessibility closure | Built-renderer test PASS at 77037d3c: 1542 computed text contrast samples (minimum 4.748), bounded table/document geometry, heading focus, semantic headers, light/dark at 1440x900, 1280x720 and 720x450. Independent approved-reference comparison of retained crops; capture limits below. Complements retained native keyboard/semantics rather than replacing them. |
| Architecture, generated contracts, quality and reference conformance | Task evidence preserves affected architecture/API/native/client/reference checks. New qualification-only files receive focused quality/inventory checks; product source is unchanged. |

## Candidate continuity and selection

The task implementations are ancestral to the slice qualification candidate.
Intervening increments add qualification controls, fixtures, evidence and state,
not product behavior. Retain exact source/input hashes and execution candidates in
each report; no installed-runtime cache receipt or fresh whole-profile claim is
made. Completed functional/native/migration suites are not rerun merely for a
new evidence note. Fresh benchmark and remaining handoff/UI checks cover the
specific previously open boundaries. Broader cross-capability/profile/installer,
signing and required-platform qualification remain W2 checkpoint/exit work.

Preserve all task checkpoint adverse findings and the three failed frozen-harness
attempts, prerequisite-only benchmark failures, and their reviewed corrections.
No adverse run is deleted or relabeled PASS. Productive large-import execution
still serializes ordinary reads behind publication; cancellation stays reachable.
This packet does not qualify ordinary-read latency or resolve later Work/Version
reconciliation.

Independent final slice disposition and taskctl submission remain pending.

## Handoff and visual execution

Candidate `77037d3cf151a01147a63c64e1608d63415f4c8d`, clean unchanged HEAD:

```text
python -B -s -m unittest tests.contracts.test_import_public_handoff tests.desktop.test_import_visual -v
```

Three tests PASS in 14.189s, exit 0, no skips. Log
`artifacts/tmp/CAP-04.S01.handoff-visual-01.log` SHA256
`2cdceeb79be48fa845e6456880cef74b9a6509b3e654aff9982846eebfe85e4b`;
report `artifacts/tmp/import-visual-ski_5g4p/result.json` SHA256
`a8a2112aa7519f2459451329b59667834ae26523fe1f348cf6bceb24eb8dccbc`.
The report binds all 12 capture hashes, built-document digest, Chromium
145.0.7632.6, Playwright 1.58.0 and available Segoe UI/Georgia/Consolas fonts.
Focused Ruff lint/format, mypy (the two new tests plus their existing typed
desktop helper) and the 304-file quality inventory passed at that candidate.

Independent reviewer `/root/w2_commit_increment_review` APPROVED the bounded
cbc5e073→77037d3c increment, authenticated all artifacts, recomputed contrast and
compared eight 1440/720 light/dark captures with approved reference 1.7/shared
controls. No blocking findings. Typography, themes, actions, wrapping, provenance
and textual states conform within this import scope. Narrow manifest crops
include an off-viewport fixed skip-link fragment consistent with Playwright's
beyond-viewport element capture. Retain the images; they are controlled crops,
not clean viewport/pixel-baseline evidence or a demonstrated product defect.
This disposition does not approve the still-open performance result or slice.

The privacy hook initially blocked the exact synthetic fixture's three
`recordKey` digests as generic API keys. Independent recomputation authenticated
them against the source fixture and frozen report. Only that exact blob and the
three complete finding fingerprints were admitted using the existing sealed
registry procedure; all 133 prior admissions and preservation were retained.
Checker, scanner policy/configuration and parser bytes remained unchanged.
The canonical interpreter resolved an initial installer alias rejection; no
hooks were disabled and no remote action occurred.

## Qualification-control preflight

The independent handoff reviewer authenticated exact equality of the proposed
fixture's three objects to the frozen report and found no material §13 omission.
The visual-control draft review identified two false-pass risks before execution:
it selected the wrong shared table wrapper and did not await theme identity.
The draft now selects `.ro-table-scroll` as well as `.ro-table-region`, requires
nonempty table measurements, and asserts the actual theme before sampling.
These were control-draft defects, not observed product failures. The committed
checks and independent increment disposition above close them. Visual claims are computed
text contrast, geometry and retained controlled snapshots, not a pixel-baseline
regression comparison, browser-zoom qualification or native/DPAPI proof.
