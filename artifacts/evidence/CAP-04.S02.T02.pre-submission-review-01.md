# CAP-04.S02.T02 incremental pre-submission review

Reviewer: `agent:w2-s01-final-review`. This is advisory review, not task approval
or a formal RNN disposition. The initial implementation was backed up in
`96d4dee55cacee5040d5cf1ee45ef654eff9777e`; the resumed pre-edit HEAD was
`ad1df596877386c2b2f3d615cc26d0ffb3c5f763` (later Git-control changes only).
The reviewer used read-only inspection and new offline probes, without external
requests, UI or broad-suite replay.

| Finding | Material obligation | Reproduction and required closure |
|---|---|---|
| F01 | AC1/AC2 atomic checkpoint, claim and cancellation | Task Center cancellation at `publish` left a completed checkpoint while the job was cancelled. Atomically validate claim/lease/cancellation and commit page/checkpoint/output/job; prove expiry and interruption rollback. |
| F02 | AC1 truthful cache freshness | With a 5-second budget, response at t=0 and reads at t=4/t=8 both reported fresh hits with one wire call. Cache-only observation must not renew last remote validation; prove expiry and restart. |
| F03 | AC1/AC2 ADR-0027 replay/redaction | The same sanitized body changed from `applied` to `not-required` on hits and 304s. Carry original body-redaction provenance through both paths. |
| F04 | AC2 typed malformed-response boundary | JSON `1e400` decoded to infinity, then escaped `fetch` as a raw serialization error. Reject non-finite decoded numbers and return `incompatible-response`, never an accepted page. |

The implementing agent added failing reproductions before each remedy. Logs
remain under ignored `artifacts/tmp/` with the task prefix: publication-cancel
red-01 (prior session), atomic-publication-red-02, cache-red-01 and
json-overflow-red-01. Development successes do not close independent review;
final commit-bound evidence and disposition must explicitly replay F01–F04.

The review found no additional concrete authority-substitution issue in the
inspected consent/API/runtime composition. The implementing agent's subsequent
real runtime-factory test exposed conflicting shared resource policies and a
receipt-read lock inversion; those adverse attempts and the timed thread
diagnostic also remain retained. Candidate review must include their regressions,
the exact historical-Intent fixture repair and synchronized build inventories.
Live-provider, remaining-adapter and slice/Wave qualification stay separate.
