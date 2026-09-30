# CAP-04.S03 independent slice review 02

- Reviewer: `agent:/root/w2_c02_review`, independent of the campaign/task owner.
- Corrected evidence delivery: `810b5efa4d8453436d692c2e5bc4298f4371cd69`.
- Tested candidate: `608d53830727ede882866482ebe0d9e495f62725`.
- Governing W2 approval: `c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`.
- Disposition: **approved for CAP-04.S03 slice completion**.
- Open findings: **none**. Both R01 evidence findings are explicitly closed below.

This is an independent slice disposition under approved S03 sections 8 and
10–17 and the repository verification/review procedure. It does not itself
change taskctl state, integrate code, approve W2 exit, authorize release or
change the frozen product, experience, rights, migration or security authority.
Taskctl recording and subsequent checkpoint, Wave and human release decisions
remain separate.

## Exact reviewed records

| Artifact | Raw/Git-byte SHA-256 |
|---|---|
| `artifacts/evidence/CAP-04.S03.qualification-02.json` | `c5ca0a965002b17427c740fee24c08c2f89eadfd776f715b8fc70f2f7436e556` |
| `artifacts/evidence/CAP-04.S03.qualification-02.md` | `3f3b8e53080992d430d0c72669fbe799f447baa040c3ebab740ff814b07d369d` |
| Preserved `artifacts/evidence/CAP-04.S03.qualification-review-01.md` | `64fbc71b97774e600f3e3994e2351ff86bdf1d4d2f436063ca37b358d865e764` |

R01 was introduced at `0503ad82c7fce2d3f1347f9d437a9543e511038e` and remains
unchanged. Original packet 01 remains at
`0b536d173b37d478d556723735c0390807b00def`, with JSON SHA-256
`568dfa31906ca2554c2899ef4307c5ba7a8a38ff5dff8ec3e656b9494d7a40c4` and
Markdown SHA-256
`aa424f9ff59c250856c10ddbd435394bb6aca73f9ce6c3b21b01a6d63687fb85`.
The successor identifies these exact records without replacing their bytes or
rewriting their adverse disposition.

## Finding replay and closure

### F-S03-SLICE-EVIDENCE-01 — P2, previously blocking: closed

Packet 02 removes `named-scenarios` from committed qualifying `checks` and puts
it in `developmentChecks` with `evidenceRole: precommit-development` and
`candidateCommit: null`. Its source-equivalence statement is separate from
execution provenance. The genuine 19-test development pass remains bound to
the original log SHA-256
`1edef855084ec08b7884b194f995e6989e2df85a980f792e9792e55ac547a0ab`.
The narrative no longer describes that run as execution on a committed candidate.

The 12 remaining qualifying check records are exactly the original records
apart from removing that misclassified entry. Committed scenario proof comes
from the already authenticated 206-case reconciliation run at `608d5383`,
which re-executes the named ambiguity, exact-identity and frozen-corpus cases.
Its log SHA-256 remains
`5466360a6071b92363f6acc8d45977cc0f78a7cadb3a4db6cbd1e2511d31b262`:
206 tests in 652.345 seconds, OK, without suite skips. No unchanged suite
replay was required or represented as a new execution in this review.

### F-S03-SLICE-EVIDENCE-02 — P3, previously nonblocking alone: closed

The successor correctly distinguishes these original reports:

| Run | Actual HEAD | Selected inputs | Disposition |
|---|---|---:|---|
| Calibration 02 | `81930fe594f754bf4f0d43e0e7405af8a8a8bcfe` | 481 | MEASURED, nonqualifying |
| Qualification 01 | `6214f599253db999bda2ee2e692604dda67a531b` | 482 | PASS at its own candidate |
| Qualification 02 | `608d53830727ede882866482ebe0d9e495f62725` | 482 | PASS at the final tested candidate |

The prior qualification report authenticates to
`3b3a9480acec83c9394e22b20135ab0516cb66460571501a97e6bd139b6ab14b`.
Both qualification input maps contain the same paths; only
`tests/reconciliation/test_candidates.py` changes bytes between them. The
named scenarios therefore did not add a selected path. The prior report is
explicitly historical and is not relabeled as final-candidate qualification.

The reviewer inspected and independently replayed the focused provenance
check. Packet 01 exits 1 with both retained findings; packet 02 exits 0. The
script and original red/green logs authenticate to the exact hashes in packet
02. Its timestamp check is a bounded regression against this known chronology,
not a universal execution-attestation mechanism. The earlier owner-confirmed
execution order, original reports and independent R01 audit remain the basis
for that chronology; a filesystem timestamp alone is not treated as proof.

## Incremental authentication and unchanged scope

All **41 artifact bindings** match their declared original raw bytes or exact
Git-blob bytes. Historical Git-bound records also match their current committed
bytes. All **12 qualifying check logs plus the one development log** match
their declared SHA-256 values. The original 35 bindings, final performance
object and qualifying check contents are unchanged; the six additional bindings
preserve packet 01, R01, and the focused regression script/results.

All **482 final selected input hashes** were independently checked against
both Git at `608d5383` and current physical worktree bytes. After that tested
candidate, the complete diff comprises only packet 01's two files, R01's note,
and packet 02's two files. Commit `810b5efa` itself adds only packet 02.
Product, tests, contracts, migration code, benchmark tool, fixture, baseline,
limits and approved authorities are unchanged. HEAD was clean and fixed during
authentication. This review replays the two findings and the incremental
evidence risk; it does not infer approval from a receipt or cache an independent
disposition.

## Slice criterion disposition

The completed deep R01 source/test/contract assessment remains applicable to
these identical inputs. Its non-evidence findings were not suppressed or
converted to approvals by this successor. Task T01 R01, T02 R02, T03 R01 and
linked correction W2.C03.T01 R01 retain their original approved candidates and
evidence. Earlier task and benchmark adverse findings remain preserved with
their actual closure evidence.

- **Identity and human authority:** exact identifier associations, scoped
  person/container/location identities, conflict/reassignment denial, immutable
  source addresses and separate current Work-head inspection preserve meaning.
  Syntactic validity is not registry verification. Fuzzy comparison and the
  named ambiguity fixtures retain uncertainty and require human merge/split
  decisions; translated-title characterization does not claim fuzzy retrieval.
- **Ordering, history and versions:** durable impact/uncertainty review ordering
  is separate from frozen retrieval scores and retains its parameter dependency.
  Historical ordinals/retries remain stable. Complete partitions and alias plans
  support reversal. Version, sourced notice and preference lineage remain
  distinct; changed membership/status prevents silent reuse of stale decisions.
- **Integrated authority and recovery:** the fresh native supervisor/generated
  client/production React/Core/Windows DPAPI/SQLCipher journey exercises retained
  import and connector sources through candidates, merge/split, retraction,
  retry and process restart. Current Intent/source rights, denial, bounded
  cancellation, rollback and dependency continuation are covered at their actual
  boundaries. The original protected runtime reports were directly read and
  authenticated in R01, including agreement with the suite's published data.
- **Compatibility and handoff:** populated v13/v14/v15 predecessors, additive
  v14–v16 transitions, encrypted backup/rollback/retry/reopen and retained graph
  history are covered. Public version contracts and portable fixtures support
  downstream consumption without private repository imports. Admitted Windows
  long-backup-path and WAL tests do not imply universal long-path support.
- **Experience, privacy and observability:** unchanged reference 1.7 and task UI
  records, fresh browser/native behavior, current-rights clearing, focus and
  retained-command recovery support the approved workflow. Durable receipts,
  candidate features/configuration, conflict/volume facts and review/version
  history retain scholarly provenance separately from redacted diagnostics.
  Researcher agreement and later-correction rates remain unavailable.

The remaining selected checks retain the authenticated 31 migration-chain,
11 protected-storage, 37 shared-contract and 15 dependency-impact passes, plus
Core API generation, architecture, repository structure, fixture corpus and
affected lint/format/types. The original bad fixture-check invocation remains a
nonqualifying error; the actual `fixture_corpus_check.py` result supplies proof.
No full-profile result is inferred from these selections.

## Performance and remaining limits

Final qualification report SHA-256
`18cc838e972b1d94b2b67ef7a22a3e6c180f5bc99af552605b4d906de0876199`
and immutable baseline SHA-256
`214292cf8f636a2d8ebecd31d4f0e9f7b618d928f7efaf1bbaeae0a78b627d9f`
remain unchanged. The independent baseline and control reviews, retained failed
calibration, three original child result/log pairs, raw sample projections,
distributions, hardware/runtime/dependency identity and both per-sample ceilings
were authenticated in the prior audit. This correction changes none of them.
Every sample passes the smaller of baseline plus 20% and the absolute ceiling.

Scope remains the known 2463-record DBLP/ACM kernel and protected 202-import-plus-
one-connector workload: 203 sources, 103 candidates, complete 100/3-item pages,
distinct cold/warm requests and jobs, zero warm feature recomputations and zero
provider dispatch during measurement. Full API candidate content is compared
with durable ordinals and cold/warm results. Gold precision/recall are known
qualification outcomes, not unseen-holdout or acceptance-probability claims.

These are source-based Windows measurements with real protected storage and
worker admission, synthetic transport/ASGI native context, setup-only capacity
substitution, unflushed OS caches and whole-child peak memory. Setup/reopen/close
time is excluded. Standard-library/OS input closure is explicitly unauthenticated;
evidence reuse remains disabled. No live-provider, installer, minimum-hardware,
native-GUI benchmark or researcher agreement/correction-rate result is claimed.

This review does not add a spoken screen-reader session, full native DPI/shell
matrix, new visual inspection or packaged install. Previously disclosed broad
typing failures, native warnings/settings witness limits and Windows-token
symlink obligations remain at their checkpoint/Wave boundaries. Fresh affected
checkpoint/build checks, full repository/profile and cross-capability Wave
qualification, required Windows packaging/platform proof, independent W2 review
and the separate human release decision remain required and are not waived.

No material slice blocker remains. The reviewer made only read-only
authentication and focused provenance replays before adding this note; product,
approved packet, old evidence, planning, taskctl and Git were not modified.
