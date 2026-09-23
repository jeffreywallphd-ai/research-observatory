# CAP-04.S01 integrated native observations

Candidate: `f850468ef679651b34af44611aa39c8d147c6074`; product candidate
`42efdbd9a179dfabe3343474adeaabcd4acad204`. The intervening commit contains task
evidence/state only. This record is partial slice evidence, not slice approval.

## Identity and scope

The Windows x64 native probe was built from 42efdbd9 with the real renderer,
native bridge/dialogs, production Core composition, SQLCipher, DPAPI and durable
workers. Executable SHA256:
`d11bde023db56da53d70f1d7b429768f36aa20750a05ddb4f802a4e44356d6db`.
Startup uses the Python native-integration sidecar and explicit isolated vault;
this is not frozen production-package or authentication proof. HEAD/product
inputs stayed fixed throughout substantive observation and restart at f850468e.
No ordinary projects, vault, credentials or security settings were used.

Retained ignored fixture:
`artifacts/tmp/directory-dialog-cap04-s01-slice-20260923-02`.
Logs: `artifacts/tmp/CAP-04.S01.native-qualification-02.stdout.log` and
`artifacts/tmp/CAP-04.S01.native-qualification-03.stdout.log` (stderr counterparts
retained). Both exits report exitCode 0, admission closed and no pending operation.
The initial sandbox launch -01 had no targetable window and was safely stopped;
its fixture/logs remain. It is setup failure, not passing product evidence.

## Observed native journey, September 22–23

1. Fresh unlocked startup required no credentials and opened no project.
   Created a synthetic project using the preselected isolated parent folder;
   explicitly opened it and navigated to Ingestion & Reconciliation.
2. Chose the synthetic semicolon CSV using the actual Windows file dialog.
   Confirmed only local store/inspect rights; other permissions remained unknown.
3. Corrected the duplicate title-column mapping, excluded a row, exported the
   diagnostic CSV using a native folder dialog, then undid exclusion. Effective
   mapping revision 2 and draft revision 4 contained three included metadata
   records plus one context/header row. Summary disclosed one DOI candidate group,
   not a scholarly work merge.
4. A separate read-only protected-database audit before explicit commit observed
   zero source records and zero manifests, with four retained draft revisions.
   Explicit confirmation produced three source records, one manifest, four
   manifest members and one seal. The UI reported awaiting reconciliation.
5. Physical Escape stopped automation before a repeat confirmation was observed.
   No replay result was inferred. The app subsequently exited normally; after
   renewed user permission the same fixture was restarted with lifecycle-resume.
   Startup again opened no project. The real folder chooser selected the retained
   synthetic project; only the explicit Open project action opened it.
6. The saved preview recovered mapping 2/draft 4, summary and committed status.
   Explicit same-draft commit replay retained the identical manifest and counts.
   Manifest identity and membership digest matched the earlier observation.
7. Light and dark views exposed the same controls/status, warning/rights text,
   summary and records. The manifest exposed heading, region, table and column
   headers. Tab from its toggle visibly focused the scrollable manifest table.
   Native UIA focused_element reported the document rather than that region;
   this is visible keyboard-focus/semantic-tree evidence, not a spoken screen-
   reader session or an automated contrast measurement.
8. Confirmed cancellation of the already-committed synthetic preview. UI showed
   cancelled, disabled further publication, explained retained source/audit and
   committed records, and offered importing the file again. A protected-database
   audit still observed 3 records/1 manifest/4 members/1 seal/4 draft revisions.
   Closed the isolated window normally; no cleanup of retained data was requested.

## Stable result identifiers and report privacy

- Manifest: `01a0cbec-bb0f-79eb-ae42-627631f4a290`.
- Membership SHA256:
  `a78cec14bf03afed61d6d2c8bf01f69fc8ce7c4b74551e70ee009ade4a29b8a9`.
- Source SHA256:
  `7cbe3bdb76e3e94346299d448ba1a0e19eda6958d4d59e719ed4d003116ef851`.
- Export: `projects/import-diagnostics-9e9683a4ef4f9fb28b02bdd269467984.csv`
  under the fixture; revision 3 before undo, 216 bytes, SHA256
  `dbc3dcd53b91ecd62242f0474f0e6542dc6729f7c407baade3c3625fab867724`.
  Read content contained row/line/status/diagnostic codes only, no bibliography
  values, names, DOI values or filesystem paths.

## Remaining boundaries

This native replay is the same draft, not a second file-intake comparison.
Cancellation occurred after commit, not during the native publication window.
Retain reviewed real-Core interrupted-publication/rights/denial evidence, with
its narrower substitutions stated. Frozen execution, fresh reviewed performance,
downstream public-contract handoff and independent slice disposition remain.
Do not replace those with this narrative or rerun unrelated completed suites.

The user separately authorized synthetic project-key creation in the ordinary
Windows-protected vault for the forthcoming frozen-package test. That permission
does not authorize inspecting existing secrets, real projects or sign-in changes.
