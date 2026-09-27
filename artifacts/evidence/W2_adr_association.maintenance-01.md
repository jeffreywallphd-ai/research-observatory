# Preserve mandatory ADR association during linked corrections

Predecessor: `6854b45999909309c01124279dd104ff2c239d27`.
Risk tier: 2. W2.C02.T01 product execution is quiescent. The original task,
correction spec, approved Wave packet and accepted ADRs remain immutable.

The exact candidate passed 100 connector and 20 connector-contract cases, but
its ADR range check failed for six changed portable-contract paths. ADR-0001
and the ADR procedure require a changed indexed Proposed or Accepted record.
The correction spec excludes authority paths, and the separate maintenance
adapter also excludes every ADR/index path. An unchanged ADR, wider comparison
base or omitted check would not close this failure. Independent read-only
review confirmed this mismatch and recommended a narrow adapter repair.

Implement a documentary association within the existing independently reviewed
candidate/evidence/review chain. Permit one newly introduced Proposed ADR plus
one append-only registry entry. Require unchanged prior registry entries and
metadata, no accepted decision edits, no deciders/supersession/status grant,
existing task links, exact bounded affected paths, regular Git files, and one
joint immutable introduction. All source commits, hashes, delivery ordering,
independent disposition and existing control-only scope remain authenticated.
A Proposed record does not authorize architecture or product scope changes.

The companion records how this correction follows ADR-0027 and how mandatory
ADR association coexists with ADR-0001/0003 and bounded maintenance. It supplies
review context, alternatives, compatibility, privacy, rollback and verification;
it does not supersede or amend an accepted architecture decision.

Required proof: first demonstrate the valid association is rejected by the
current adapter. Add real-Git acceptance and denial cases for changed old index
metadata/entries/documents, unsupported states, authority fields, unknown task
links, wildcard/unrelated path scope, missing index pairing, rewritten/reverted
documents, and mixed product delivery. Exercise both maintenance attribution
and correction scope/submission. Retain prior denials and source-sequence cases.
Run affected gate tests, Python quality and actual ADR range checks at a fixed
committed maintenance candidate, then obtain independent control disposition.

Rollback is a separately reviewed revert of the adapter increment; preserve
the failed receipt and all history. Product submission remains blocked until
this maintenance chain and the ordinary UI classification/task proof pass.
No new controller, product authority, reference, migration or release decision.
