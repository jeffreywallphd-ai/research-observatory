# W2 Source Manager reference proposal

**Owner approved; published as reference 1.7.** The exact reviewed proposal
remains unchanged under [W2-reference-1.7](W2-reference-1.7/source-manager.html#connector-review).
The [owner approval](../artifacts/evidence/W2.design-architecture-owner-approval-01.md)
authorizes the [published reference](../design/ui-reference/source-manager.html#connector-review)
and plan rebinding, not W2 execution. All W1 approvals and the preceding reference
remain preserved in Git history.

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

The retained proposal snapshot deliberately retains its original Proposed metadata;
it is evidence of the reviewed bytes, not the active approval record. Published
reference 1.7 records the owner authority and preserves the approved design.
Product baselines and implementation are not changed by this publication. The
complete W2 packet still requires final validation, independent review and its
single immutable execution approval.
