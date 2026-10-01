# Source-specific rights contract

`rights-policy.schema.json` carries the versioned `CAP-04.S04.T02` policy-revision
and historical decision values. A policy belongs to one project, retained
reconciliation assertion revision and `SourceAddress`, opaque copy ID/location,
and resource class. Each permission names one action, purpose, and destination
context. A Work identity, connector page alone, source-reported license or
open-access observation, and legacy import defaults cannot grant a different
source, copy, resource or action.

`sourceObservation` holds a protected snapshot of the exact retained record's
reported license, terms and access status, with its source assertion revision,
address, provider, source digest and retrieval time. It is separate from every
action permission. A reported license or open-access flag alone cannot grant an
action; imported records without typed source terms remain explicitly
not-reported/unknown. The Core publisher verifies connector record bytes against
the retained assertion before attaching this snapshot.

The value vocabulary covers `store`, `inspect`, `index`, `derive`, `model-use`,
`quote`, `export`, and `share`. Permission assertions retain their evidence,
license observation, entitlement source, categorical confidence, actor scope,
recording time and expiry. `unknown`, source-only observations, conflicts,
expired grants and confirmation-required outcomes do not authorize use. A
decision document records the exact evaluation and is an audit fact, not a
reusable permission witness.

`authorityKind` distinguishes a current explicit `policy` decision from a
`legacy-import-bridge` decision or `none`. The bridge can only describe a
confirmed retained import assertion's local metadata copy for the four Corpus
membership actions (`store`, `inspect`, `derive`, `index`). Its single governing
assertion ID and `sourceAssertionSha256` bind that exact retained assertion; the
protected repository verifies the digest and current import permission. The
pure model and portable reader only validate the document shape. A policy or
unknown decision may carry the retained source digest after protected lookup,
while pure evaluation leaves it null.

Core loads the current policy and rechecks project, authenticated actor, Intent,
privacy and rights inside the protected action transaction using a trusted
clock. The portable reader validates untrusted values but cannot supply those
authorities or authorize network dispatch, model use, export or sharing.

The current protected publisher accepts only a retained source assertion's
local metadata copy: its copy ID must equal that assertion revision ID. Two
retained source assertions for the same Work may therefore have different
policies and decisions. Acquired full text, derived text, embeddings, and other
physical copies remain unavailable for publication until their own protected
copy provenance exists. The contract can describe them, but it does not turn
an unverified copy or reported license into an entitlement. The publisher leaves
`licenseObservationRevisionId` null until a separately identified typed witness
is retained; the policy's source snapshot is not a permission or entitlement.

Run `python packages/contracts/rights/generate_schema.py --check` to compare the
schema with the strict Python value models. Run
`node packages/contracts/rights/generate.mjs --check` to compare the generated
TypeScript reader and schema digest. The synthetic fixtures exercise both
readers. Neither command changes the process version negotiation contract.
