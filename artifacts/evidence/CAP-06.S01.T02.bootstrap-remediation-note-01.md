# CAP-06.S01.T02 pre-submission remediation

This note records implementation development under approved CAP-06.S01.T02 and
Accepted ADR-0057. It supplies no task disposition, Wave qualification or release
approval. The task remains IN_PROGRESS until fresh committed-candidate evidence
and independent review are complete.

Qualification01 at `01237dd0742c4f0775e5251cb3a228bd66929de1` finished FAIL:
12 of15 groups passed; search, rights and migration compatibility each had one
Windows staged-project rename setup ERROR. All tracked inputs, HEAD, producer
and installed runtime inventories remained equal. The complete report is retained
at `artifacts/tmp/CAP-06.S01.T02.qualification-01/report.json`, SHA256
`fb9a92351daa85e5600ef780f3bb307c53a2941b5e8b111488a3cdd3bacd5147`.
No failed group is relabeled PASS.

Independent preliminary reviews identified two material implementation defects:

- T02-F01: several lawful rows matching one query leaf duplicated an item's ID.
  Failure-first protected text/title/year cases and a Core multi-projection case
  reproduced the defect. The final compiled item selection now uses DISTINCT,
  preserving compound Boolean set semantics and stable ordering.
- T02-F02: constructor interruption could leave unbound partial derivative files
  that both normal recovery and retirement refused. Windows CREATE_NEW files now
  retain kernel delete-on-close ownership until a complete canonical per-role
  witness/seal commits. Exact normal guards are reacquired before SQLCipher;
  durable empty-schema acknowledgement precedes source admission. Never-admitted
  partial files use exact witnessed cleanup, including missing roles; initialized
  files retain authenticated protected recovery. Unknown files are preserved.

The original three-case failure-first observation had four failed assertions and
one cleanup ERROR. After correction its three cases passed (58.888 unittest
seconds). Additional review exposed mixed-case unknown-name inventory and mutex
release after an ancestor-close error; both failed before their corrections.
Handle conversion also passes O_NOINHERIT atomically. No guard or assertion was
weakened, and no new schema or product authority was introduced.

Native bootstrap development02 passed29 tests in215.744 unittest seconds
(218.857928 recorder seconds), including14 abrupt owned-child process phases:
each creation role, durable witness, each retention role, guard handoff, schema
transaction/commit and initialization acknowledgement. Tests preserve the prior
selected results and retire only owned interrupted files. The report is
`artifacts/tmp/CAP-06.S01.T02.bootstrap-regressions-02/report.json`, SHA256
`2082222056affc00c7fcad64b74ee606231bfcc95ea2496f77cc172808c9afe5`.
This is development proof, not the later committed-candidate qualification.

The separate actual Windows file probe02 proved deletion after ordinary close
and owned TerminateProcess until same-handle FileDispositionInfoEx cancellation;
after cancellation the exact file identity survived both. Its report SHA256 is
`174f68e664db0d570db4a8ba9a7a635092599baa76c7bc3501a15c888d49f67f`
at `artifacts/tmp/CAP-06.S01.T02.windows-bootstrap-probe-02/report.json`.
Probe01's parent-stat observation race and incomplete output remain preserved.
Neither probe nor the crash matrix establishes sudden power-loss or driver-crash
behavior. The crash child transfers synthetic fixture keys/actor context through
stdin; it does not prove Native authentication. Separate Native/DPAPI composition
retains its explicit injected-context and capacity-fixture limits.

The staging-rename ERROR cause remains UNKNOWN. Independent source inspection
found no demonstrable leaked handle. Current-process native handle/close-result
diagnostics observed40 basic fixture setups and20 full protected setups, including
the repository-local temporary path shape; all completed with no rename or close
failure. Those non-reproductions do not establish a cause or erase the original
errors. Reports remain at
`artifacts/tmp/CAP-06.S01.T02.project-rename-trace-01/report.json` (SHA256
`6c0d469f36d0d7276ec53b721851e8720efebde0e739c9e6cb6d852976fb0ef6`)
and `artifacts/tmp/CAP-06.S01.T02.project-rename-trace-02/report.json` (SHA256
`380d657e25cefd54fe901b9942e67f031af1548d28785e4979bef258c7c2cb09`).
Fresh qualification will run its selected groups serially to isolate the next
observation, with unchanged assertions and all original adverse results retained.

Core commands remain usable without the renderer. HTTP/ranking/snippets/UI,
slice performance, later platforms, installed packaging and full Wave/release
qualification remain at their approved owning boundaries; no AI mode is planned.
