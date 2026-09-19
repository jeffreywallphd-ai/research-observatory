# CAP-04.S01.T02 — terminal summary continuation status

Independent checkpoint-15 review of `738aa845540646f8f1ad8f03263023cc97c9a015`
was NOT APPROVED: P2, terminal continuation status disappeared. A cancelled
original retried through Task Center could fail with `rights-denied`, yet summary
status and scheduling returned the original cancelled job. No denied summary was
published. The reviewer ran 15 focused checks in 17.216 seconds, with no other
material blocker in the reviewed increment; this does not approve the task.

Missed acceptance row: status must retain the actual latest matching continuation
identity, terminal state and diagnostic, including after service reconstruction.
Immediate cause: lookup considered active jobs and accepted results, but skipped
unsuccessful terminal continuations before falling back to the original job.

Before remediation, add the real-service regression for failed and then cancelled
continuations, both live and reconstructed. Add a one-result direct-continuation
lookup and follow the recorded lineage, not UUID ordering across generations.
Same-parent sibling retries use creation time then ID as a deterministic tie-break.
Keep cancellation/recovery enumeration active-only. Exact configuration matching and accepted-result priority
remain unchanged. Replay this finding and the affected worker/parser/queue checks;
do not repeat unrelated W1 qualification.
