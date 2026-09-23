# CAP-04.S01.T03 — cancellation and process-restart closure

Working increment based on `ddc3b980ef65c0c1ef26766fbc02f2a8462f596c`;
not yet exact-candidate task completion evidence.

## Cancellation affordance

Read-only independent preflight found that the automatic commit-status poll
sets the same busy flag as a mutation. A read waiting behind the publisher
therefore disables the otherwise interruptible Cancel route. A real built
renderer/generated-client/Core regression first **FAILED** in 11.725s at the
enabled-button assertion, before product editing.

Separate status-read/action pending states now allow only Cancel during a
commit-status read. The parent disabled gate remains authoritative. A synchronous
operation ref denies duplicate cancellation; generation fencing prevents a
superseded read from overwriting state, errors, announcements or mutation busy
state. No API, authorization, route, styling or governed-reference change.

Three delayed-response orderings cover old success/failure during cancellation
and old success after cancellation. They also test the parent's busy gate and
duplicate activation, use actual Core cancellation and assert no canonical
records/manifests. The native bridge and scheduler start are explicit fixtures,
not native host or concurrent-writer proof; the latter has separate API tests.

The first four-case run passed its first cancellation case but then hit three
setup errors: the test's database context committed/rolled back without closing
its handle. Added explicit `closing()` to both fixture count probes; no product
storage behavior or assertion was weakened. Preserve that failed run (7.391s).
After closing those test-owned handles, all four renderer cases passed in
27.625s. Desktop lint then exposed its existing text-only `any` check matching
that English word in the prior cancellation announcement, not a TypeScript
type. Removing that unnecessary word preserves the exact retention claim and
avoids an unrelated lint-framework change; the durable-state assertion remains.
The quality-scope inventory check also found four earlier T03 test modules not
yet listed. Registered those alongside the new process test and selected their
format/lint checks; no scanner or scope rule was relaxed.

## Real process restart

The small protected fixture runs real production Core composition in three
spawned processes. First it pauses after an actual transactional source write,
then uses normal project close to stop/roll back/drain. The process exits; a new
Core process checks zero canonical/accepted output, reopens and permits the
existing-policy automatic retry. A third process discovers and replays the same
accepted request/result. Every project session and Core instance is new; the
authorized native resume epoch is intentionally retained.

The initial development run **PASS** in 11.209s. All three processes exited zero;
exact attempt history is first `failed/dependency-unavailable`, second
`succeeded`, with no extra retry. One source record, one manifest/seal/accepted
commit and two members remain unchanged on final replay. Fixture and logs:
`artifacts/tmp/import-commit-process-qw8n6spa`. This run preceded final commit;
fresh committed-candidate proof follows separately.

This closes ordinary process-restart proof, not abrupt Core kill/stale-lock
recovery, Windows UI, packaging or benchmark qualification. No ordinary profile
vault or real project is used. Failure cleanup terminates only the exact
test-owned child; isolated fixtures are retained under ignored artifacts.
