# CAP-04.S01 integrated qualification

Qualification evidence is complete. Final slice disposition is recorded separately
through taskctl; this document does not itself approve the slice or W2 release.

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
| Representative 100k workload, regression limits and bounded memory | Fresh complete attempt03 at 7ef91f94 PASS: six parser measurements, two review and two commit samples under unchanged reviewed limits. Both commits preserve exact durable facts, full membership traversal, replay and fresh-runtime identity. Original cbc5e073 attempt01 failure and owner-interrupted attempt02 remain adverse, not relabeled PASS. Exact bindings and limits below; no minimum-hardware, OS cold-cache or UI-read-latency claim. |
| Import identity-verification correction | W2.C01.T01.json and independent review-R01 bind the exact correction and control delivery candidate54f1fda6. At e663f327,66 affected tests PASS74.271s, including multi-page identical identity, four-versus-seven protected connections, between-page authority loss, rights, guards, cancellation and atomic failure/replay. One fresh transaction per page; no cross-page cache, schema, deadline or security-authority change. |
| Public downstream handoff | Two public-contract consumer tests PASS at 77037d3c; exact public manifest/members/rights from frozen run, only public JSON schemas, immutable source IDs, exclusions/provenance, unknown rights and current reauthorization. |
| Import-pane visual/accessibility closure | Built-renderer test PASS at 77037d3c: 1542 computed text contrast samples (minimum 4.748), bounded table/document geometry, heading focus, semantic headers, light/dark at 1440x900, 1280x720 and 720x450. Independent approved-reference comparison of retained crops; capture limits below. Complements retained native keyboard/semantics rather than replacing them. |
| Architecture, generated contracts, quality and reference conformance | Task evidence preserves affected architecture/API/native/client/reference checks. Qualification controls received focused quality/inventory review; the later two-module internal product correction received its own affected checks and independent disposition. The separate immutable interruption-note control fix has24 linked-gate and14 corrective-workflow tests plus exact independent maintenance review. |

## Candidate continuity and selection

The original task implementations are ancestral to the qualification candidate.
Most intervening increments add controls, fixtures, evidence and state. The
exception is W2.C01.T01 at e663f327: import draft projection and identity
verification now share one fresh protected read transaction per page. Public
validation, scientific identity, current authorization, bounded guards and final
atomic publication remain unchanged; named regression and fresh performance
evidence cover this internal change. Earlier native/frozen/public-handoff/visual
observations retain their exact earlier product candidates and stated limits.
They are not relabeled as executions of the corrected candidate.

The fresh benchmark's 173 recorded source/tool/contract hashes were independently
matched after the control-only delivery; installed runtime was not changed.
This is candidate continuity, not a new benchmark or a cache authorization.
Retain exact input hashes and execution candidates in each report. Completed
functional/native/migration suites are not replayed merely for an evidence note;
no fresh whole-profile claim is made. Broader cross-capability/profile/installer,
signing and required-platform qualification remain W2 checkpoint/exit work.

Preserve all task checkpoint adverse findings and the three failed frozen-harness
attempts, prerequisite-only benchmark failures, and their reviewed corrections.
No adverse run is deleted or relabeled PASS. Productive large-import execution
still serializes ordinary reads behind publication; cancellation stays reachable.
This packet does not qualify ordinary-read latency or resolve later Work/Version
reconciliation.

Independent final slice disposition and taskctl submission follow this committed
matrix; all original task approvals and correction review remain immutable.

## Complete performance execution and adverse preservation

Fresh actual-Windows-principal invocation at clean fixed candidate
`7ef91f94a4213972960e9321142c0e7138e90984`:

```text
python -B -s tools/import_performance_check.py --report artifacts/tmp/CAP-04.S01.performance-qualification-03.json
```

PASS, exit 0, `performanceQualifying: true`, 3343.781887s. Reuse disabled; source,
tool, contracts and installed-runtime inputs remained locked throughout, with
unchanged HEAD and final equality checks. No competing heavy verification.
Report SHA256 `bac4797a1fad85ea4de84942a5d781eaef1d255fb5359035764f4e3d63f0b9ff`;
matching console log SHA256
`d9bfe2630a65aec7c8c26362d9a4d428d30675249fbf2b530cebbc05008f4d65`.
Reviewed baseline SHA256
`6b5a7f196046423ce3fbc07f8d79af642a15b0ce353994b4f7ea0e4a11a34a92`;
executing tool SHA256
`b69cc6e1ab05a357ecc85bf11af21148385c5785cd3622ffb868d3a293e8433a`.
The aggregate binds actual hardware/runtime, methodology, source closure and raw
samples. It is real protected Core/DPAPI/SQLCipher/durable-worker proof using
ASGI/synthetic native context, not a new desktop packaging observation.

| Sample | Elapsed seconds | Worker seconds | Peak working-set bytes |
|---|---:|---:|---:|
| Review1 |521.231429|258.123312|141627392|
| Review2 |521.845353|258.916945|142872576|
| Commit1 |1095.993442|878.152392|154816512|
| Commit2 |1092.481683|875.556697|154071040|

Unchanged review limits: 624.577878s elapsed, 303.832916s worker, 166305792 bytes.
Unchanged commit limits: 1200s elapsed, 900s worker, 184939315 bytes. Slowest worker
headroom is 21.847608s; retain the narrow observed margin without claiming general
throughput or expanding this correction into optional optimization. Every sample
passed first-attempt completion. Each commit has exactly 100000 source records,
one manifest, 100001 members, one seal and one accepted commit output, complete
1001-page traversal, replay and fresh-runtime reopen. Six 100k parser measurements
cover RIS/BibTeX/CSV; maximum traced memory 30117 bytes.

Retain attempt01 report SHA256
`25f8ac372e90261cfdb06960d5ae11357fab3da32f47a69c48f8fa2d0beb7498`
as the original failure, including censored second-commit 900.874s observation and
zero canonical outputs after teardown. Retain attempt02 report SHA256
`72f354ef633850764ef4ede8fcbecd8de13bafe5998fc0eb35be40332cd5e519`
as an owner-interrupted incomplete run, neither product regression nor qualifying
PASS. Both remain under their original `artifacts/tmp/CAP-04.S01.performance-qualification-0N.json`
paths. W2.C01.T01.json records the exact 66-test log, initial failing connection
regression, control checks and candidate-specific scope. No adverse evidence was
deleted, threshold relaxed or prior approval rewritten.

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
This historical disposition did not approve the then-pending performance result
or slice; the completed performance evidence is recorded above.

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
