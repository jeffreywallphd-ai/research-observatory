# CAP-04.S03.T02 — independent adverse pre-submission review 02

Reviewer: `agent:/root/w2_t02_disposition`, independent of the task owner.
Reviewed candidate: `531ff646aae5119afcf202f0e5883b74832489c2`.
Reviewed tree: `ffc54f55af05ab25dd766a948f314b5b4183753b`.
Claim base: `691205f48cf8ee80b323a9971413f7da1d0608e1`.
Approved W2 packet: `c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`.
Experience authority: `RO-UI-ACADEMIC-MINIMAL-1.7`.

**Disposition: adverse; F-IMPACT-EDGE-03 is OPEN and blocking.** This is
an exact-candidate incremental pre-submission review, not a formal task
disposition, task approval or integration approval. It does not close
F-EXACT-IMPACT-01 or F-IMPACT-GRAPH-02 from
[review 01](CAP-04.S03.T02.pre-submission-review-01.md). Their original adverse
record remains immutable; no finding closure is claimed here.

The review followed the repository's independent-review and verification-breadth
guidance, the [approved S03 task contract](../../planning/slice-plans/CAP-04/CAP-04.S03-canonical-work-version-and-identity-reconciliation.md#92-cap-04s03t02---implement-probabilistic-duplicate-candidate-generation-and-review)
and [task-start acceptance map](CAP-04.S03.T02.task-start.md). It selected one
previously untested incremental risk: graph-input removal beneath a pending
dependency run, after remediation added fresh-preview continuation and
predecessor cancellation. No broad test suite was run.

## Candidate and raw evidence binding

Before probing, independent Git reads established that the reviewed candidate
and `b3cba265425505abaaac800d2f83f2057d2d41d5` have the same tree shown above;
`git diff --exit-code` between them returned success with no differences.
HEAD and the tree were checked again after the probe and were unchanged.
Branch naming changed during coordination without changing HEAD or source.
This probe does not assess reconstruction procedure or provide qualifying
evidence for unrelated checks.

The raw ignored evidence is retained at these repository-relative paths:

| Artifact | SHA256 |
|---|---|
| `artifacts/tmp/CAP-04.S03.T02-graph-edge-removal-probe-01.py` | `f55ed22868e4054e425979a37585d9015f08b04adcfd57c7fcbd5ee89b2ebbbd` |
| `artifacts/tmp/CAP-04.S03.T02-graph-edge-removal-probe-01.log` | `d556bf3553e0f592f1fcc03314a6daa8b7cd55c999a1cab331ffa78653cdcc5a` |

The original ignored review-01 ledger,
`artifacts/tmp/CAP-04.S03.T02-pre-submission-independent-findings-01.md`,
was rehashed and remains
`ba80e637bac75fe7a2c3493af1d3b5366bbdb410c4cf45d058136cd080f2c684`.
Digests bind artifact bytes; the execution observation below establishes what
ran. The probe creates and cleans a disposable synthetic canonical SQLite
fixture. No real research records or product files were changed.

## F-IMPACT-EDGE-03 — continuation accepts graph removal and abandons a pending effect

**Severity: P2. Blocking: yes. Status: OPEN.**

**Criterion and contract.** CAP-04.S03.T02 C2/C3; approved S03 §9.2 persistence,
audit and restart obligations; S03 §8 requires resumable dependency-graph
updates. The task-start map's Atomic dependencies and Durable operation rows
require honest pending/stale state and recovery without false completion.
The incremental continuation control must preserve authenticated predecessor
effects or reject a changed graph that removes them.

**Candidate location and defect.**
`services/core-api/src/research_observatory_core/reconciliation_repository.py:1688`
accepts any changed graph digest as grounds for continuation. It authenticates
the saved run, items, checkpoint and command semantics, then starts a fresh
preview-derived child, links it and cancels the predecessor. It does not check
that the graph change retains the predecessor's affected outputs or that the
new graph is an append-only extension. A valid saved run can therefore be
superseded by an empty, immediately completed child after an original material
edge disappears. Subsequent worker calls report no pending work.

**One targeted reproduction.** From the repository root, on the candidate above,
the exact command used repository-relative executable and artifact paths:

```powershell
& .venv/Scripts/python.exe -B artifacts/tmp/CAP-04.S03.T02-graph-edge-removal-probe-01.py 2>&1 | Tee-Object -FilePath artifacts/tmp/CAP-04.S03.T02-graph-edge-removal-probe-01.log
$probeExit = $LASTEXITCODE
exit $probeExit
```

The retained script uses the existing `ReviewRepositoryTests` synthetic fixture,
adds one dependent evidence revision beneath Work A, and commits a human merge.
It confirms the root has one unprocessed impact. Using the disposable database,
it saves and temporarily drops `material_dependencies_no_delete`, deletes
exactly the direct A-to-consumer dependency edge, and restores the exact trigger
SQL before canonical reopening or worker execution. Canonical schema validation
succeeds. A fresh repository instance then advances the worker twice, inspects
the saved root and continuation, queries public `stale_states`, and exercises
fresh-only consumption. This is a storage-corruption boundary probe, not a claim
that an authorized application command permits deleting immutable edges.

The process exited **0**, with explicit assertions confirming the adverse
behavior. Measured command wall time was **3.638 seconds**. Exact observed output:

```text
{"event": "intent.draft.saved", "level": "INFO", "reasonCode": "intent-draft-saved", "timestamp": "2026-09-27T10:30:29.825Z", "traceId": "11111111111111111111111111111111"}
root before: ('running', 1, 0)
graph corruption: {'removed_edges': 1, 'remaining_origin_edges': 0, 'schema_restored': True}
worker advancement: (True, False)
root after: ('cancelled', 1, 0)
continuation runs: (('completed', 0, 0),)
consumer evidence: {'saved_root_items': 1, 'materialized_stale_causes': 0}
fresh-only consumer denied: True
CONFIRMED: edge removal is accepted as continuation; pending effect is never materialized.
```

**Observed consequence and limit.** The authenticated predecessor retains its
one impact item, but the worker cancels it without processing that item and
accepts a completed zero-item child. No stale cause is materialized for the
consumer, and the next worker call reports no work. Fresh-only consumption
still denies the consumer because the original impact item remains. Thus this
probe proves lost propagation and incorrect recovery completion; it does not
prove false-fresh access or loss of the original audit record.

**Smallest adequate closure.** Before publishing a continuation or cancelling
its predecessor, verify that the fresh plan preserves predecessor effects with
at least their prior material disposition, or authenticate that the graph change
is a permitted append-only extension. Removal or weakening of a required
predecessor effect must deny integrity without adding a child/link/cancellation
or changing saved counts. Preserve the original pending effects, audit and
fresh-only denial. Add the smallest regression using this graph-removal fixture
before repairing the control; retain the valid graph-growth recovery regression
and existing saved-run/item/checkpoint corruption checks. Do not weaken the
engine's graph/authority guard to obtain recovery.

Formal closure requires a subsequently submitted immutable candidate and
criterion-linked evidence. This review supplies no closure or approval.
