# CAP-04.S04.T01 pre-acceptance architecture review

Date: 2026-09-30 (America/New_York)  
Independent reviewer: `w2_s04_adr_review`  
Scope: ADR-0034 and the versioned CorpusItem contract/migration candidate under the owner-approved W2 packet at `c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`.

The reviewer recommended **Accept ADR-0034** within approved `CAP-04.S04.T01` scope. The v1 schema, generated reader and lifecycle remain byte-identical. The v2 generator constrains the change to an envelope version and one closed aggregate kind; its catalog binds the corpus schema, exact v1 fixture, bridge test and ADR. Mixed v1/v2 process advertisements deny and no v2 process export was added. The portable discovery edge carries root context, source, direction, canonical time and predecessor; the protected writer verifies those relationships. Populated v16 and encrypted migration/recovery checks passed in the pre-acceptance review. No approved scope, security authority or recovery guarantee expansion was found.

One nonblocking hardening finding was closed before candidate freeze: direct SQL
could insert an initial corpus row with non-default review, duplicate or
availability even though the portable contract and protected writer denied it.
The v17 initial-state CHECK now requires the same fixed entry condition, and
negative direct-SQL cases plus the populated-v16 migration suite pass. This
pre-acceptance review is not the commit-bound task disposition.

Decision attribution: the repository owner approved the W2 scope at the packet commit above; the later versioning route is a bounded implementation architecture decision by `codex-w2-implementation`, subject to the independent review recorded here. This record does not claim the owner approved ADR-0034's exact design before it existed.
