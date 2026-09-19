# CAP-04.S01.T01 — streaming reference imports

Claim base: `f05ac90621d7cbe03abd53b880764f2d6a996445`.
Authority: approved W2 packet at `c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`,
CAP-04.S01 section 9.1, ADR-0027 ingestion rules and ADR-0013 identity boundary.
CAP-03.S03.T02 and CAP-02.S02.T03 are DONE. This task consumes an already-authorized
binary source stream; it does not open paths, mint canonical identities, persist
records, grant rights, call providers or change governed UI.

| Material boundary | Focused proof |
|---|---|
| AC1: five formats, raw fidelity and deterministic keys | Synthetic RIS/BibTeX predecessor fixtures plus genuine CSL item-array, DOI-list and CSV fixtures; repeated tags/keys/columns, unknown fields, nested/quoted/multiline data; compare different read-chunk sizes and original byte ranges. |
| AC1/AC2: malformed isolation | Valid–malformed–valid sequences; unterminated data explicitly quarantined when a safe boundary cannot be recovered; never hide invalid records. |
| AC2: identity/completeness | Keys bind ordinal, byte/line location and raw-record digest, not filename or normalized title/DOI. Complete traversal requires EOF and the expected full source digest; substitution, cancellation, timeout and read failure cannot report completion. |
| AC2: bounded untrusted input | Source/record/field/count/nesting limits; cancellation inside oversized input; explicit UTF-8/BOM and legacy encoding handling; no evaluation of BibTeX or spreadsheet cells; content-free failure codes. |
| AC2: real boundary/performance | Real temporary binary file, no seek/readline requirement; incremental consumption of 100k RIS/BibTeX/CSV records with measured memory, not a collected list. |
| AC3: portable handoff | Versioned ImportRecord schema, examples, documentation and schema-valid serialized parser output; raw values, normalization candidates, unknown confidence and unset human mapping remain separate. |
| AC4: bounded support allocation | Explicitly defer W2-RUNNER-PROGRESS with no runner edits. Product delivery takes priority; the approved task expressly permits this outcome. The locked W2 estimate/budget is not changed. |

Independent read-only preflight by `w2_ux_plan_review` identified the genuine-CSL
fixture gap and emphasized repeated raw fields, chunk-independent identity,
honest incomplete streams and cancellation inside long fields. Those checks are
included above. Existing fixture files will not be rewritten.

First proof: add failing service tests before product code. Select focused parser
unit/contract checks, lint/types, affected schema/quality inventories and the
streaming benchmark. UI/computer-use, canonical transactions, project restart and
full affected profiles remain CAP-04.S01 integration/W2 qualification obligations;
T02 owns preview/mapping, T03 owns import commits. No new human gate discovered.
