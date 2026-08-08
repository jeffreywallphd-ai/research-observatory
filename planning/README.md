# Planning guide

This file is the repository's high-level planning router. Planning state and identity live in the files referenced below, not in chat history or this summary.

## Hierarchy

```text
Capability
  -> Slice
      -> Task
```

- `backlog.yaml` is authoritative for IDs, dependencies, waves, gates, status, claims, leases, and evidence references.
- `capability-plans/CAP-XX.md` resolves cross-slice and material implementation decisions.
- `slice-plans/CAP-XX/*.md` expands the existing tasks into a coherent implementation and verification contract.
- `review-site/` is generated from the Markdown plans and is not a parallel authority.

## Default planning and execution lifecycle

1. Select one eligible capability.
2. Run `planctl prepare CAP-XX`; create any missing capability or slice plan from the governed templates.
3. Inspect all slices and adjacent capability contracts before implementation.
4. Research each material choice; document credible candidates, best-in-class recommendation, rationale, required ADR/reference impact, and compatibility constraints.
5. Adopt the recommendation as the completed selected decision unless a reviewer records an override.
6. Generate the static review site and provide its direct link.
7. Obtain one explicit approval for the capability packet and all contained slice plans at an immutable commit.
8. Start the capability campaign.
9. Complete tasks and slices in dependency order with slice-wide integration and independent review.
10. Complete capability-wide production qualification and independent capability review.

The default is sustained execution. Do not insert routine approval stops after the capability is approved.

## Decision review and Other

Every decision page displays the documented candidates, preselected recommendation, and an `Other` option.

When `Other` is selected:

- the reviewer must enter a brief description in the Other field;
- the separate feedback/rationale textarea provides detailed reasoning, constraints, or acceptance conditions;
- exported feedback uses schema `1.1` with `selected_option: "__OTHER__"` and `other_option`;
- `planctl apply-feedback` adds `Other: <brief description>` to the canonical decision's candidate list and selects it;
- detailed rationale remains preserved in the archived feedback record; and
- implementation remains unapproved until the explicit capability approval command.

A non-recommended documented candidate also requires detailed rationale.

## Canonical commands

```bash
python tools/planctl.py --repo . prepare CAP-XX
python tools/planctl.py --repo . review CAP-XX
python tools/planctl.py --repo . decisions CAP-XX
python tools/planctl.py --repo . validate CAP-XX
python tools/planctl.py --repo . apply-feedback CAP-XX <feedback.json>
python tools/planctl.py --repo . approve CAP-XX --by "<reviewer>" --commit <git-sha>
python tools/planctl.py --repo . approve CAP-XX --feedback <feedback.json> --by "<reviewer>" --commit <git-sha>
python tools/planctl.py --repo . ready CAP-XX --require-approved
```

Any command that requests decisions or approval must print the capability page's `file://` URI and repository-relative path.

## Templates and validation

- Capability template: `capability-plans/TEMPLATE.md`
- Capability schema: `capability-plans/capability-plan.schema.json`
- Slice template: `slice-plans/TEMPLATE.md`
- Slice schema: `slice-plans/slice-plan.schema.json`
- Capability validator: `../tools/capability_plan_check.py`
- Slice validator: `../tools/slice_plan_check.py`
- Site generator: `../tools/plan_review_site.py`
- Site validator: `../tools/plan_review_check.py`

A missing plan must be scaffolded, fully researched, decision-complete, validated, reviewed, and approved before its capability starts.

## Replanning conditions

Reopen planning only for:

- demonstrated infeasibility of an approved choice;
- materially new evidence creating a consequential decision;
- unavailable required external service, credential, platform, or hardware;
- conflict with a higher-authority source;
- required governed experience-reference change; or
- explicit user redirection.

Update only the affected decision, ADR, plan, or reference; regenerate review pages; obtain approval; then resume the same capability campaign.
