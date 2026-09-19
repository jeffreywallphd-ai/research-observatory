# W2 Source Manager reference proposal

**Proposed, not approved.** Candidate `RO-UI-ACADEMIC-MINIMAL-1.7` is an inert
copy under [W2-reference-1.7](W2-reference-1.7/source-manager.html#connector-review).
The active approved 1.6 package and all W1 approvals remain unchanged.

Purpose: close the independent UX finding for CAP-04.S05 without a new page,
marketplace, styling system or control framework. All other 1.6 experience contracts
remain inherited; fourteen workflow sequences are unchanged. This is not a
migration of ADR-0026's durable 1.5 workflow selections.

| Candidate | Tradeoff |
|---|---|
| **Recommend: inline Source Manager review** | Keeps publisher/package identity, project permission and safe next action beside the selected source; existing components and context return. |
| Separate Application Settings publisher-management page | Centralizes trust but adds navigation and another governed surface; unnecessary for this small local SDK. |

The normative delta is [style §1.3](W2-reference-1.7/STYLE_GUIDE.md#13-connector-trust-and-project-permission),
the Source Manager required-region entry and its linked HTML. It distinguishes
local trust from project consent, shows permission increases, preserves cancellation
and focus, and defines disable/quarantine without deleting scholarly evidence.
No real publisher, credential, project or destination is used in the mock.

Validate the proposed package and changed-page theme/reflow/keyboard states before
requesting exact reference approval with the complete W2 packet. A proposed-status
failure from the active-reference checker is expected and must not be relabeled
as approved. Do not activate the reference, change product baselines or implement
the experience before human approval. Active-reference conformance remains 1.6
until the normal approved-reference publication step.
