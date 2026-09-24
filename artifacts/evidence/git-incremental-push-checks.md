# Incremental push privacy checks

Owner-requested bounded Git-control maintenance, 2026-09-24. Predecessor:
`96d4dee55cacee5040d5cf1ee45ef654eff9777e`. This is not CAP-04.S02.T02 completion
or permission to integrate unfinished product work into main.

## Delta and invariants

The owner requested checking only new commits on pushes, for all branches.
The existing supported destinations remain unchanged. The guard obtains fresh
heads/tags from the exact policy-approved remote with a 30-second timeout and
checks that each destination still matches Git's original push advertisement.
It scans outgoing ancestry minus resolvable, already-published commit ancestry
and the fixed approved historical baseline. Cached local tracking refs, dry-runs,
and successful local commits are not proof of remote publication.

Unpublished intermediate commits and merge-side parents, full changed blobs,
new/copied paths, commit metadata, ref names, secrets and ignored/private output
remain checked. Unknown remote objects yield no exclusion. Remote failures,
malformed advertisements and changed destination tips deny rather than skipping
checks. No scanner rule, baseline, artifact admission or historical preservation
semantics are relaxed. Deliberate installation still requires independent review
and resealing the unchanged preservation rules to the new checker bytes.

## Verification selection

The initial new-branch regression failed before implementation because incremental
remote selection did not exist. Six focused new boundary tests then passed.
The complete affected privacy module passed 48 tests in 164.868 seconds during
development, including real temporary Git remotes and installed hooks. These
development observations are not represented as committed-candidate qualification.

Final candidate checks select the new incremental cases, installed-hook ordinary
push/commit denial, sealed preservation, scanner/ref-name denial, and affected
Ruff checks. The one loop-binding lint correction and explicit timeout case are
included in the final selection. Unchanged product/import/native/performance
suites are not rerun. The already-completed development module is not repeated
merely for presentation; independent review and the real non-uploading push
dry-run must still finish before activating/reporting this repair as complete.
