# Workflow-context keyboard verifier — bounded maintenance

Predecessor: `545a5643b3de74a8e8e82b5dedb3fc56da4c6c0c`.
Exact predecessor Git blobs:

- `tools/product_layout_measurements.py`: `f9568afc70fef3755ea8a7148c7177c7735e9a9f`
- `tests/desktop/test_product_layout_measurements.py`: `6730d734ce473b00f4f5f559a8229f854f120db0`

Risk: evidence correctness. W1.C04.T01 is independently approved and DONE;
this is a separate control repair, not additional product scope or a reopened
task. No styling, reference, criterion, authority or refactoring change.

## Defect and invariant-preserving repair

The built-frame development check selected a hidden Diagnostics button inside
collapsed All tools as the workflow keyboard starting point. Geometry and
computed visibility alone do not establish an available focus target. Retain
`artifacts/tmp/W1.C04.T01.frame-development-01.json`, SHA-256
`d35813284273940f727efbdd49ebf9db302f4e09981203c7c7a95cbe3be568b5`;
downstream unexecuted checks are not independent application failures.

Filter only predecessor candidates using browser visibility, inert ancestry and
effective disabled semantics. Explicitly require successful starting focus.
Preserve the required action inventory, real Tab traversal, disabled skipping,
at least two-pixel focus outline, viewport bounds, and untabbable-action negative.
Do not open disclosures, mutate tabindex, directly focus required actions, or
silently omit an unreachable enabled action. Summary and first-legend controls
remain eligible under the browser's own semantics.

## Development evidence and selected qualification

RED attempt 01: two tests, one failed subcase and three errored subcases;
13 owned processes drained, root exit 1, 2.438 seconds. Inert and disabled-fieldset
predecessors reproduced the wrong starting point; a focus-refusing predecessor
exposed a false pass, and a missing predecessor produced an opaque script error.
The simple initially closed-details fixture already passed the old helper;
the actual built-frame failure above supplies that separate reproduction.
Report SHA-256 `79d6745b115bb33f58228a6bfe9d36be17d1644af6ff9d609f443f35d719f2d6`;
log SHA-256 `cd63daf03ed7475464ce87f5b3608c69aa098840d9fc527d47c0d90f7ebc0d24`.

Independent producer preflight found unsafe potential attribution of unowned
output after failure and a missing under-lock producer-hash recheck. Original
ignored producer 01 is retained; successor 02 removes the child report-file
write, keeps frame JSON in exclusively owned stdout, hashes only successfully
created logs and rechecks its identity under lock. Reviewer
`agent:/root/c04_evidence_review` cleared successor SHA-256
`80cd0cef43f5c97c36e11a5d7d20accfdab14ea2b46340a3f36bd6d4bd2bedcd`
for bounded fresh execution, not acceptance of results. RED remains development
evidence only. A development lint/format failure was corrected without changing
assertions. Development attempt 02 then passed both regressions and quality/
format checks; report SHA-256
`0db083bc6307616350f064e9d222149bbc87fe44a374ce6e631fbb2b53a05b56`.

Commit this bounded unit, then freshly run the full affected layout-measurement
module, Python lint/format and actual built-frame checker. Bind exact candidate,
selected inputs, owned process drainage, report/log hashes and retained failures
in the evidence delivery. Obtain independent control disposition before local
integration. Broader profiles, native/principal/accessibility/performance and
packaged Windows checks remain fresh W1 obligations; browser fixture transport
is not proof of those boundaries. No evidence reuse is claimed.

No ordinary project, vault, sign-in policy, credentials, protected witness,
excluded sibling contents or remote effects are in scope.
