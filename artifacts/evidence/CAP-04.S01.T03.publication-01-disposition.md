# CAP-04.S01.T03 publication-01 independent disposition

**CHANGES REQUESTED for this bounded atomic publication increment.**
Reviewer: `w2_document_packet_preflight`.
Candidate: `e7523d782f1bb4145ea1dc4aadf96f585d297b72`.
Base: `78952f814ec496da6f037dbf01b82b3ccc1a9998`.
This is not task completion, real-principal, UI or 100k qualification.

## T03-PUBLICATION-01-F01 — P1: comparison bypasses current predecessor rights

Location: `services/core-api/src/research_observatory_core/import_commit_repository.py:228-235`
(`_comparison`; candidate line numbers).

The comparison query reads the explicit predecessor's historical member decision
and draft default-rights JSON without checking that predecessor preview's current
default and effective record rights. Current-head authorization elsewhere applies
to the new input preview, not this separate historical input. Immutable historical
permission is therefore used despite a current revocation.

Reproduction using the existing isolated publication fixture: publish predecessor
A; revise A's current first record to `inspect=denied` with a
`researcher-confirmed` basis; verify historical `draft_page(A, revision=1)` denies;
prepare a permitted changed preview B with the same unique DOI and A as explicit
predecessor; publish B. Publication succeeds and stores `comparison=updated` with
a non-null previous SourceRecord revision. The probe confirmed both the historical
read denial and the subsequent comparison success.

Material criterion: current action-specific rights must govern use of retained
source assertions (ADR-0027 and the task's current-effective-rights invariant).
Preserving historical bytes does not authorize their current inspection or use.

Smallest closure: authenticate the explicit predecessor's actual current
preview/draft and relevant current default/per-record store/inspect permissions
before historical comparison, and recheck inside the publication transaction.
Discovery/counting must not bypass denied records outside a returned page. A
revocation must deny and roll back the new publication, without changing the
immutable predecessor or granting other rights dimensions. Add the demonstrated
revocation regression and retain permitted-predecessor comparison coverage.

## T03-PUBLICATION-01-F02 — P2: successful queue replay is not manifest authority

Location: `services/core-api/src/research_observatory_core/import_commit_repository.py:442-450`
(`publish_commit` completed-output branch; candidate line numbers).

The completed branch resolves a generic accepted output revision and labels it an
import manifest without authenticating an actual sealed `import_manifests` row,
complete membership or its scientific/input identity. Generic queue acceptance
does not prove these domain facts.

Reproduction using a fresh isolated fixture after ordinary preparation: obtain
the actual accepted parser receipt revision; wrap it with the adapter's `_output`;
call the real queue `stage_artifact` and `complete` for the commit job; call
`publish_commit` directly. The method returns the parser receipt as the manifest
output, while `import_manifests` and `import_source_records` both contain zero
rows and the queue job is succeeded. No database rows were forged directly.

Material criterion: T03's accepted import result must refer to a real immutable
manifest and resulting canonical identities; ADR-0025's exact accepted output
binding cannot substitute for that domain validation.

Smallest closure: validate successful replay against the exact sealed accepted
manifest, complete membership and immutable source/draft/scientific identity,
as well as the full accepted workflow output reference. Reject parser receipts
and unrelated manifests even when the generic queue receipt is valid. Preserve
legitimate lost-reply and same-scientific-input/new-request replay; the original
manifest's attempt need not equal the replaying request's attempt. Add these
negative substitutions alongside existing positive replay cases.

## Coverage and evidence limits

Reviewed exact Git source/test/evidence changes, shared-transaction ownership,
current new-input authority, staged-row verification, streamed complete identity
and membership, provenance/dependencies, rollback boundaries and scientific
replay. The bounded implementation contains the canonical writes, seal, staged
output and queue completion within one protected database transaction. Existing
rollback and expiry cases do not cover either finding above.

Owner-reported exact-candidate checks: publication plus preparation 17 tests PASS
in 21.238 seconds; Ruff/format two files, mypy one file and architecture PASS.
No suite was rerun for this review. Two isolated fixture probes confirmed the
findings. During concurrent separate worker work, the corrected probe loaded
`workflow_executor.py` from the exact candidate Git blob in memory; repository
and fixture source matched the candidate. It used only synthetic fixture data
and explicit connection closing, and exited successfully. An earlier combined
probe had a probe-owned unclosed database connection that prevented its second
fixture setup; that failed invocation is not qualifying evidence.

The existing publication/preparation notes and previous adverse findings remain
unchanged. Runtime Intent/privacy/session guards, worker integration, API/UI,
real-principal and large-input qualification remain pending rather than inferred
from this bounded disposition.
