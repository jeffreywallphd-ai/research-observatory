# CAP-05.S04.T02 — adverse exact-revision navigation observation

Independent reviewer: `agent:/root/reader_anchor_review`.
Reviewed source candidate: `98f7fea87a88c359ea73d867e5472697ac2c45e6`.
Claim base: `780e1d8e79ad7136f9c362535e642adbfdeb5437`.

This is retained advisory adverse evidence, not a formal submitted-round
disposition or task-completion approval. Final Native/shipping Reader evidence
and the qualifying manifest were not yet available. No product, test, planning,
HEAD or selected qualification input was changed by this reviewer.

## CAP-05.S04.T02-ADVISORY-F01 — a successive link retains the prior accepted revision

Severity: high. Blocking: yes.
Criterion: backlog criterion 1 and accepted ADR-0029's authoritative exact
revision, retained prior links and no silent revision substitution.

Open a Reader link for accepted revision A, then open a second link for the same
project, attachment and original revision but accepted revision B. The second
link does not replace the Reader session identity. The selected revision stays
A. With existing saved anchors available, the context panel reloads and displays
A's passages in response to the B link. With no saved-anchor fallback, the panel
clears but still does not select B.

At the reviewed candidate, `DocumentViewerWorkspace.tsx` keys both the linked
entry and Viewer session using project/attachment/original IDs. Its source
initialization effect excludes the link's normalized revision, and its sole
automatic `setRevision(linked.selector.normalizedRevisionId)` runs inside the
initial accepted-revisions lookup. A later B link therefore cannot rerun that
selection. `ViewerAnchorContexts` no longer accepts the initial link because
its revision differs from the still-selected A, so it lists A's saved anchors.

### Reproduction and observed result

The ignored diagnostic command was:

```text
.venv/Scripts/python.exe -B artifacts/tmp/CAP-05.S04.T02.review-relink-01.py
```

The diagnostic used real headless Chromium for mounted UI behavior, with the
already built synthetic fixture ports/PDF decoder. It served
`artifacts/tmp/CAP-05.S04.T02.viewer-ui-fixture-04/document-viewer.js` with SHA-256
`fb540d8bbb9f4a3fa9e0271495605e851111e906f43760d244199831ed799764`.
Only the fixture's deep-link `normalizedRevisionId` expression was replaced in
memory with `state.reviewLinkRevision ?? revision`; product component bytes
were unchanged. The diagnostic producer SHA-256 is
`d30a5a95e814b69c2961a5ccbd9acdfad0d3dc399331cd939bcbbecc366775b1`.

Set the fixture's `noHandoff`, `linkMode` and `anchorMode` to true, then mount.
It displays two contexts for A
`00000000-0000-7000-8000-000000000003`. Set `reviewLinkRevision` to B
`00000000-0000-7000-8000-000000000099` and mount again without closing the Reader.
After the second render:

- The selected accepted revision remains A.
- Anchor resolver calls increase from 2 to 4.
- Both displayed context passages remain byte-for-byte equal to their A values.
- The page reports no JavaScript errors.

The diagnostic assertions passed with process exit code 0. This proves the
mounted exact-revision transition defect; it supplies no protected Native/Core
or shipping decoder qualification. The sandboxed browser setup attempt was
terminated after it stalled. An initial real-runtime attempt corrected a
diagnostic locator, and a second attempt exposed the empty saved-anchor variant;
neither was treated as product success or qualifying task evidence.

### Smallest adequate closure

Include the linked accepted revision in the entry/session identity (or establish
an equivalent explicit revision transition with complete stale-result fencing),
and add a mounted regression that opens two different exact accepted revisions
for one original without an intervening route close. Cover both an ordinary
handoff already present and a linked entry with no handoff. The second revision
and its exact contexts must replace the first, and late results from the first
must not publish. Fresh checks must bind the corrected committed candidate.

The implementation owner was informed promptly and acknowledged the defect.
Closure and the final independent disposition remain pending corrected-candidate
review and the completed evidence manifest. Preserve this adverse observation.
