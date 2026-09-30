# CAP-04.S03 independent slice review 01

- Reviewer: `agent:/root/w2_c02_review`, independent of the campaign/task owner.
- Evidence delivery: `0b536d173b37d478d556723735c0390807b00def`.
- Tested candidate: `608d53830727ede882866482ebe0d9e495f62725`.
- Governing W2 approval: `c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`.
- Disposition: **changes requested; one blocking evidence finding**.
- Scope: independent deep CAP-04.S03 slice review. This record does not change
  taskctl state, integrate code, approve W2 exit, authorize release or approve a
  change to the frozen product/reference/rights/migration authority.

The reviewed packet is exactly:

| Artifact | Raw/Git-byte SHA-256 |
|---|---|
| `artifacts/evidence/CAP-04.S03.qualification-01.json` | `568dfa31906ca2554c2899ef4307c5ba7a8a38ff5dff8ec3e656b9494d7a40c4` |
| `artifacts/evidence/CAP-04.S03.qualification-01.md` | `aa424f9ff59c250856c10ddbd435394bb6aca73f9ce6c3b21b01a6d63687fb85` |

The delivery adds only those two artifacts after the tested candidate. Product
source, public contracts and renderer/native implementation are unchanged from
the independently approved W2.C03.T01 correction. The approved S03 plan body is
unchanged from the W2 approval; subsequent frontmatter records that approval.

## Severity-ranked finding ledger

### F-S03-SLICE-EVIDENCE-01 — P2, blocking: precommit execution labelled as committed qualification

Criterion: AGENTS exact-committed-candidate evidence; S03 sections 10, 15 and 17;
task-operations evidence truth and preservation of actual execution boundaries.

The packet's `checks[id=named-scenarios]` assigns candidateCommit
`608d53830727ede882866482ebe0d9e495f62725` to the focused 19-test log, and the
Markdown describes the selected checks as fresh on the fixed clean candidate.
The owner confirmed that this focused execution preceded the commit. The log's
recorded modification time is 2026-09-30 12:44:10Z; the candidate commit time is
12:44:21Z. These times corroborate the owner's original and confirmed chronology;
file timestamps alone are not treated as execution attestation.

Exact affected log:
`artifacts/tmp/CAP-04.S03.named-scenarios-01.log`, SHA-256
`1edef855084ec08b7884b194f995e6989e2df85a980f792e9792e55ac547a0ab`.
Its 19 passing tests in 8.845 seconds are genuine development evidence. The
subsequent commit preserves the tested source, but cannot retroactively make
that execution a committed-candidate qualifying run.

This is an evidence classification defect, not a failed test or product defect.
The independently authenticated fresh 206-case run at `608d5383` includes the
same named scenario test, exact cases and frozen-corpus benchmark; it already
supplies committed-candidate proof for these outcomes.

Required closure: retain the original packet/log and this adverse record;
append a superseding packet that explicitly classifies the 19-test execution as
precommit development evidence, separates any source-equivalence association
from its actual execution provenance, and uses the fresh 206-case run for
committed scenario qualification. Correct descriptions/counts of fresh checks.
No unchanged suite replay is required to repair this claim.

### F-S03-SLICE-EVIDENCE-02 — P3, nonblocking alone: historical input count is wrong

Criterion: S03 sections 11 and 15 and automation guide section 8.3 require exact
benchmark input identity and truthful distinctions between historical runs.

The Markdown calls qualification 01 at `6214f599253db999bda2ee2e692604dda67a531b`
a 481-input run. Its original authenticated report contains **482** input hashes:
`artifacts/tmp/CAP-04.S03.performance-qualification-01.json`, SHA-256
`3b3a9480acec83c9394e22b20135ab0516cb66460571501a97e6bd139b6ab14b`.
Final qualification 02 also contains 482. Calibration 02, before baseline
publication, contained 481. The owner confirmed this distinction.

Required correction in the append-only successor: state 482 for both qualifying
runs and 481 for calibration 02. The named scenarios changed an existing test
file's bytes rather than increasing selected path count. Preserve each report
at its actual candidate. Current qualification 02's metrics, input count and
baseline binding are correct; this error does not invalidate their execution.

## Authentication completed

All **35 artifact bindings** match their declared Git-blob or original raw bytes.
All **13 check-log bindings** match their declared SHA-256 values. The finding
above concerns classification of one of those executions, not a digest mismatch.
The reviewer inspected the logs and actual test assertions, rather than treating
hashes or passing booleans as independent proof of behavior.

The fresh integrated log
`artifacts/tmp/CAP-04.S03.slice-reconciliation-01.log` authenticates to
`5466360a6071b92363f6acc8d45977cc0f78a7cadb3a4db6cbd1e2511d31b262` and ends
with 206 tests in 652.345 seconds, OK, without suite skips. Fresh selected logs
also report 31 migration-chain cases, 11 protected-storage cases, 37 shared
contract cases and 15 dependency-impact cases. Core API generation,
architecture, repository structure, declared fixture corpus, and affected
test-file lint/format/types pass at their stated scope. The failed invocation of
nonexistent `fixture_check.py` remains an error; only the later actual
`fixture_corpus_check.py` result is accepted.

The reviewer additionally read both original runtime reports published by the
206-case run and verified their raw digests and equality with logged reportData:

- `artifacts/tmp/reconciliation-native-_iceb_vo/result.json`, SHA-256
  `723055ddb89609035ba37c5a8db8731f3d0c88329df2e8e3ae194e057cb69a14`.
- `artifacts/tmp/reconciliation-runtime-zq5erto1/result.json`, SHA-256
  `b47eb90df83e20a2e56f7396bff965aba624f1215732c3b2b866fe5d47f8c3e8`.

Task T01 R01, T02 R02, T03 R01 and W2.C03.T01 R01 remain independently approved
at their original candidates; their evidence digests and ancestry authenticate.
Original T01/T02 pre-submission adverse artifacts, T02's evidence-only R02,
T03's identity/preference/recovery/migration findings, the two adverse benchmark
control findings and their R02 closures were reviewed without erasing history.
The current suite explicitly re-executes the material closure cases.

## Criterion assessment apart from the evidence finding

- **Identity, sources and human authority:** exact normalization/association,
  conflicting or reassigned identifiers and scoped person/container/location
  identities remain separate from registry verification. Immutable source
  addresses and current Work-head inspection retain observed and corrected
  fields. Fuzzy scores are candidate evidence, not probabilities or authority to
  merge. The four newly named ambiguity subcases close the explicit fixture gap;
  translated titles are correctly characterized as not retrieved in that fuzzy
  fixture, with exact DOI linking governed separately.
- **Review ordering, history and versions:** W2.C03.T01 records impact/uncertainty
  ordering as a versioned parameter dependency while retaining frozen scoring,
  candidate content and durable ordinals. Historical reads and accepted retries
  preserve prior order. Complete source partitions and alias plans make
  merge/split reversible. WorkVersion and sourced notice/preference identities
  remain distinct; changed membership/status requires review, and old preference
  history cannot silently reactivate.
- **Integrated trust and recovery:** the actual native supervisor/generated
  client/production React/Core/Windows DPAPI/SQLCipher journey spans retained
  import and connector sources, candidates, split/merge, sourced retraction,
  lost-reply retry and process restart. Current source/Intent/rights denial,
  exact command identity, stale/unpublished versus ambiguous-published recovery,
  atomic fault seams, bounded cancellation and owned dependency continuation
  are covered. Removal/weakening of pending graph effects remains denied.
- **Migration and compatibility:** literal populated v13/v14/v15 predecessors,
  additive v14–v16 migration, encrypted backup/rollback/retry/reopen and retained
  impact history are exercised. Admitted long-backup paths preserve predecessor
  fingerprints, public path authority and real mixed-spelling WAL locks. This
  does not claim universal long-path support for unrelated storage operations.
- **Experience and handoff:** approved reference 1.7 and its T02/T03 records are
  preserved. Existing source inspection and fresh browser/native tests support
  protected-state clearing, late-response denial, keyboard/focus, themes,
  responsive review, warnings and retained drafts. The portable WorkVersion
  fixture/public JSON schemas and generated-client tests carry exact revision,
  source, relation and preference standing without a downstream consumer using
  private repository modules. No later capability implementation is required.
- **Observability:** durable exact receipts, candidate volumes/features/flags,
  algorithm/configuration, review decisions and version history retain the
  relevant count/distribution/conflict facts. They are not confused with runtime
  diagnostics. Researcher agreement and later-correction rates remain unavailable;
  no observation, denominator or scholarly conclusion is invented.

## Performance assessment and retained limits

The final report at
`artifacts/tmp/CAP-04.S03.performance-qualification-02.json`, SHA-256
`18cc838e972b1d94b2b67ef7a22a3e6c180f5bc99af552605b4d906de0876199`, remains a
valid PASS for the tested candidate. The reviewer's earlier direct audit
authenticated all three original child result/log pairs, all 482 selected Git
and worktree input hashes, current tool/runtime/dependencies/hardware, raw
sample projections, distributions and every individual metric against both
ceilings. This delivered packet accurately carries that final measurement.

The baseline SHA-256 remains
`214292cf8f636a2d8ebecd31d4f0e9f7b618d928f7efaf1bbaeae0a78b627d9f` with its
independent historical-provenance review. Calibration remains nonqualifying;
failed calibration 01 is retained. No maximum, allowance or absolute ceiling
was changed to obtain a pass.

Performance scope remains the known 2463-record DBLP/ACM kernel and protected
202-import-plus-one-connector fixture, three fresh children, unflushed OS caches,
setup-only capacity substitution, synthetic transport/ASGI native context, real
measured worker admission and protected storage, and whole-child peak memory.
There is no live-provider, installer, native-GUI, minimum-hardware or human
agreement/correction-rate qualification. Runtime identity explicitly excludes
authenticated standard-library/OS closure.

This review does not claim a new spoken screen-reader session, complete native
DPI/shell accessibility matrix, new visual inspection or fresh packaged install.
Historical broad typing errors, native warnings/settings witness limitations and
Windows-token symlink obligations remain due at their existing checkpoint/Wave
stages; selected checks are not full-profile passes. Fresh cross-capability and
required Windows packaging/platform qualification, independent W2 review and
the separate human release gate remain required.

## Next review boundary

No additional product or integration blocker was found in this deep review.
Approval is withheld for F-S03-SLICE-EVIDENCE-01. Preserve this adverse record and
append the precise evidence correction, including F-S03-SLICE-EVIDENCE-02.
Incremental R02 review should authenticate that successor and the unchanged
tested inputs, rather than replaying unchanged suites. This reviewer executed
read-only authentication only and did not alter product, approved packet,
planning, taskctl or Git. This note is the sole tracked-path addition.
