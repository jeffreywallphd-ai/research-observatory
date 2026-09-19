# CAP-04.S01.T02 — checkpoint-06 adverse review

Candidate: `8ac575a70c62a0c07aef930ef9fba141fb064a00`; base:
`ca524fb2709e52395e1cddb9b8a12a13f8665f7e`. Independent reviewer:
`w2_document_packet_preflight`. Disposition: CHANGES REQUIRED; one P2 blocker.

The seven generated import methods serialize caller input, await transport, then
compare the reply against that same caller-owned object. Independent Node-24
reproduction dispatched revision 1, mutated the command to revision 2 while
pending, returned revision 2, and observed acceptance despite sending revision 1.
This violates the exact identity/revision/cursor response-binding claim.

Immediate cause: response ownership was implemented, but request ownership across
the asynchronous boundary was missed. Before remediation, add the acceptance row
and deferred-transport mutation regressions. Capture one owned request snapshot
before dispatch, then use it for serialization and response checks in all seven
methods. Regenerate the client and replay this finding plus incremental risk.

No other material blocker was found in the bounded API/rights/project, transport
size, group expansion, mapping high-water or diagnostic paging review. Independent
synthetic 100-record page traversal took 0.629 seconds; not native/100k qualification.

Fresh clean-candidate qualification had passed: 47 selected Python tests in
21.532 seconds; eight native transport tests; 21 generated-client tests; contracts
and desktop typechecks; ten-file Ruff/format/Mypy; quality inventory; architecture;
clean build manifest. Those results do not override this finding. Do not integrate
this candidate until independently reviewed remediation closes P2. No task R01
or completion is claimed; prior adverse evidence remains preserved.
