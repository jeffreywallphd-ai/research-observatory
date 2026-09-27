# CAP-04.S03.T03 — retained pre-submission findings

The independent read-only reviewer `/root/w2_t03_review` examined candidate
`13e1038eeb44fdd5b1a074afc065e6f885f12ec2` under the unchanged approved W2,
CAP-04.S03 and reference 1.7 authority. This advisory record is not a formal
task disposition or an approval.

The blocking C1/C2 recovery finding was that a stale, unpublished version commit
received the same generic 409 as an ambiguous saved-command conflict. The renderer
then disabled Back, refresh and editing indefinitely while offering an identical
retry that could never succeed. The worksheet now records the missing recovery
invariant and immediate cause. The actual Core/API and browser regressions failed
on the old implementation; the generic-conflict-after-publication characterization
passed. Raw adverse output is retained in
`artifacts/tmp/CAP-04.S03.T03.stale-red-01.log` (three cases, two failures).

The repair gives only pre-publication stale refusal a dedicated response. After
Core proves absence of the command, the narrow preview check translates a stale
predecessor or mismatched preview digest. Replay, authorization, integrity and
publication errors remain outside this translation. Renderer recovery retains
valid input, requires fresh evidence, invalidates unavailable selections explicitly
and keeps the saved command on generic conflicts/lost replies. Nine exploratory
API/version-renderer cases passed in
`artifacts/tmp/CAP-04.S03.T03.stale-green-01.log`. The reviewer inspected this
incremental repair and found no material regression, without claiming test
execution or formal evidence authentication. Fresh candidate proof and independent
commit-bound disposition remain required.

Further inspection found that a concurrent merge can retire a selected Work
before the version digest comparison. A direct repository regression first
failed with `reconciliation-work-retired`; this exact pre-publication condition
now receives the same non-publication distinction. The inventory can clear all
selected IDs, including retired/off-page IDs. The adverse case is retained in
`artifacts/tmp/CAP-04.S03.T03.retired-red-01.log`; candidate qualification must
prove this extension as well.

Earlier identity/placement and preference-lineage findings remain in the
task-start worksheet and their regressions; none is erased by this finding.

## First committed qualification attempt

The stable `13e1038e` run retained these producer receipts under `artifacts/tmp/`:
`CAP-04.S03.T03.core-qual-01.json`,
`CAP-04.S03.T03.desktop-qual-01.json`, and
`CAP-04.S03.T03.foundation-qual-01.json`.

The full reconciliation run passed 182 cases in 593.789 seconds; dependency,
migration-chain and shared-contract groups also passed. Foundation checks found
the missing changed/indexed documentary ADR and missing task experience lineage.
ADR-0033 and the existing approved-reference lineage address those omissions;
no frozen approval or accepted architectural decision is changed.

Native library tests reported 147 passes, six failures and one ignored settings
witness. The six unchanged import-source/report failures were caused by temporary
source ancestry outside the authorized workspace. A targeted rerun with temporary
storage confined to ignored repository artifacts passed on the same candidate.
The next native run uses that confined temporary directory; no assertion, ACL,
policy, hook or admission rule is weakened. Original failures remain available.

Affected Python typing, client/desktop tests, types, build and native formatting
passed in that attempt. A later exploratory four-file lint found one overlong
new assertion string; splitting the literal preserves its exact assertion.
Current candidate qualification supersedes these observations only as fresh
proof, never by relabeling the old attempt.
