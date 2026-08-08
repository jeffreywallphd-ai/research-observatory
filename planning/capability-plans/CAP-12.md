---
plan_schema_version: '1.1'
document_type: capability-decision-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-12
title: University-hosted deployment, institutional identity, collaboration, and operations
status: proposed
execution_mode: long-running-capability-campaign
decision_completion: complete
open_blocking_decisions: []
slice_ids:
- CAP-12.S01
- CAP-12.S02
- CAP-12.S03
- CAP-12.S04
- CAP-12.S05
- CAP-12.S06
decisions:
- id: CAP-12-D01
  title: Client architecture
  candidates:
  - Keep one desktop UI and place local/remote implementations behind a versioned client gateway
  - Fork the desktop into a separate institutional application
  recommendation: Keep one desktop UI and place local/remote implementations behind a versioned client gateway
  recommendation_basis: One experience and domain contract prevents semantic drift between deployment profiles.
  selected_option: Keep one desktop UI and place local/remote implementations behind a versioned client gateway
  status: accepted
  required_adr: ADR-REMOTE-CLIENT
- id: CAP-12-D02
  title: Institutional pilot topology
  candidates:
  - Use hardened OCI containers on one institution-controlled server with Compose or Podman; add Kubernetes only by ADR
  - Require Kubernetes before the first university pilot
  recommendation: Use hardened OCI containers on one institution-controlled server with Compose or Podman; add Kubernetes only by ADR
  recommendation_basis: A single-server profile reduces operational burden while preserving container portability.
  selected_option: Use hardened OCI containers on one institution-controlled server with Compose or Podman; add Kubernetes only by ADR
  status: accepted
  required_adr: ADR-INSTITUTIONAL-TOPOLOGY
- id: CAP-12-D03
  title: Hosted persistence
  candidates:
  - Use PostgreSQL, S3-compatible objects, Qdrant and Temporal behind existing ports
  - Reuse shared filesystem and ad hoc background jobs
  recommendation: Use PostgreSQL, S3-compatible objects, Qdrant and Temporal behind existing ports
  recommendation_basis: Production adapters preserve local semantics while adding concurrency, durability and operations.
  selected_option: Use PostgreSQL, S3-compatible objects, Qdrant and Temporal behind existing ports
  status: accepted
  required_adr: null
- id: CAP-12-D04
  title: Authentication
  candidates:
  - Use system-browser OIDC authorization code with PKCE and short-lived sessions
  - Embed university credentials inside the desktop webview
  recommendation: Use system-browser OIDC authorization code with PKCE and short-lived sessions
  recommendation_basis: OIDC federation and PKCE are appropriate for native clients and avoid password handling.
  selected_option: Use system-browser OIDC authorization code with PKCE and short-lived sessions
  status: accepted
  required_adr: ADR-INSTITUTIONAL-IDENTITY
- id: CAP-12-D05
  title: Authorization
  candidates:
  - Combine role permissions, project/data attributes and default-deny PostgreSQL RLS
  - Use UI-hidden buttons as the primary access control
  recommendation: Combine role permissions, project/data attributes and default-deny PostgreSQL RLS
  recommendation_basis: Defense in depth must be enforced at API and data boundaries.
  selected_option: Combine role permissions, project/data attributes and default-deny PostgreSQL RLS
  status: accepted
  required_adr: null
- id: CAP-12-D06
  title: Project isolation
  candidates:
  - Carry project and organization scope through every repository, object, vector, workflow and audit operation
  - Filter projects only in service-layer queries
  recommendation: Carry project and organization scope through every repository, object, vector, workflow and audit operation
  recommendation_basis: Isolation tests must cover every storage and execution plane.
  selected_option: Carry project and organization scope through every repository, object, vector, workflow and audit operation
  status: accepted
  required_adr: null
- id: CAP-12-D07
  title: Provisioning readiness
  candidates:
  - Model stable subject IDs and groups now; add SCIM only when institutional lifecycle automation is required
  - Build a proprietary user directory and manual account lifecycle
  recommendation: Model stable subject IDs and groups now; add SCIM only when institutional lifecycle automation is required
  recommendation_basis: Federated identity should remain portable without prematurely mandating provisioning infrastructure.
  selected_option: Model stable subject IDs and groups now; add SCIM only when institutional lifecycle automation is required
  status: accepted
  required_adr: null
- id: CAP-12-D08
  title: Collaboration semantics
  candidates:
  - Use immutable revisions, optimistic concurrency and explicit conflict/adjudication objects
  - Use last-writer-wins updates
  recommendation: Use immutable revisions, optimistic concurrency and explicit conflict/adjudication objects
  recommendation_basis: Scholarly disagreement and simultaneous review cannot be safely collapsed.
  selected_option: Use immutable revisions, optimistic concurrency and explicit conflict/adjudication objects
  status: accepted
  required_adr: null
- id: CAP-12-D09
  title: Offline cache
  candidates:
  - Allow encrypted, rights-bounded read cache with explicit expiration and no offline writes by default
  - Mirror whole institutional projects locally
  recommendation: Allow encrypted, rights-bounded read cache with explicit expiration and no offline writes by default
  recommendation_basis: Remote projects must preserve rights and conflict guarantees while providing limited resilience.
  selected_option: Allow encrypted, rights-bounded read cache with explicit expiration and no offline writes by default
  status: accepted
  required_adr: null
- id: CAP-12-D10
  title: Rights enforcement
  candidates:
  - Evaluate entitlements at acquisition, view, derivation, export and cache boundaries
  - Check license only when a document is downloaded
  recommendation: Evaluate entitlements at acquisition, view, derivation, export and cache boundaries
  recommendation_basis: Institutional source rights continue to govern downstream use and redistribution.
  selected_option: Evaluate entitlements at acquisition, view, derivation, export and cache boundaries
  status: accepted
  required_adr: null
- id: CAP-12-D11
  title: Model egress
  candidates:
  - Use institution policy to route local, private hosted or approved external models with fail-closed payload checks
  - Let each user send any project content to any provider
  recommendation: Use institution policy to route local, private hosted or approved external models with fail-closed payload checks
  recommendation_basis: Private manuscripts and licensed text require enforceable egress governance.
  selected_option: Use institution policy to route local, private hosted or approved external models with fail-closed payload checks
  status: accepted
  required_adr: null
- id: CAP-12-D12
  title: Retention and legal hold
  candidates:
  - Use versioned policy, deletion workflow, legal-hold override and auditable exceptions
  - Use one hard-coded deletion interval
  recommendation: Use versioned policy, deletion workflow, legal-hold override and auditable exceptions
  recommendation_basis: Institutional records require explainable retention and exception handling.
  selected_option: Use versioned policy, deletion workflow, legal-hold override and auditable exceptions
  status: accepted
  required_adr: null
- id: CAP-12-D13
  title: Observability
  candidates:
  - Use OpenTelemetry with project/tenant context and strict content redaction
  - Centralize raw prompts, source passages and reports in logs
  recommendation: Use OpenTelemetry with project/tenant context and strict content redaction
  recommendation_basis: Operations require traceability without duplicating sensitive research content.
  selected_option: Use OpenTelemetry with project/tenant context and strict content redaction
  status: accepted
  required_adr: null
- id: CAP-12-D14
  title: Disaster recovery
  candidates:
  - Declare service-specific RPO/RTO, encrypted backups and regularly exercised restore drills
  - Assume database replication is sufficient recovery
  recommendation: Declare service-specific RPO/RTO, encrypted backups and regularly exercised restore drills
  recommendation_basis: Recovery evidence must include relational, object, vector and workflow state.
  selected_option: Declare service-specific RPO/RTO, encrypted backups and regularly exercised restore drills
  status: accepted
  required_adr: null
- id: CAP-12-D15
  title: Administration experience
  candidates:
  - Design a bounded institution operations console only after governed UI-reference approval
  - Expose database and cluster tools directly to research users
  recommendation: Design a bounded institution operations console only after governed UI-reference approval
  recommendation_basis: Operational controls need role-appropriate, approved interaction design.
  selected_option: Design a bounded institution operations console only after governed UI-reference approval
  status: accepted
  required_adr: ADR-INSTITUTIONAL-ADMIN-UX
- id: CAP-12-D16
  title: Pilot acceptance
  candidates:
  - Run a complete research-group workflow under institutional security, rights and recovery controls
  - Approve deployment after infrastructure smoke tests
  recommendation: Run a complete research-group workflow under institutional security, rights and recovery controls
  recommendation_basis: The institutional product is only complete when scholarly work succeeds end to end.
  selected_option: Run a complete research-group workflow under institutional security, rights and recovery controls
  status: accepted
  required_adr: null
- id: CAP-12-D17
  title: Audit trail
  candidates:
  - Append security, rights, collaboration and admin events to tamper-evident provenance/audit records
  - Store only conventional web access logs
  recommendation: Append security, rights, collaboration and admin events to tamper-evident provenance/audit records
  recommendation_basis: Research decisions and institutional controls require durable accountability.
  selected_option: Append security, rights, collaboration and admin events to tamper-evident provenance/audit records
  status: accepted
  required_adr: null
- id: CAP-12-D18
  title: Service compatibility
  candidates:
  - Use explicit API capability negotiation and supported-version windows
  - Assume desktop and server are always upgraded together
  recommendation: Use explicit API capability negotiation and supported-version windows
  recommendation_basis: Independent desktop/server release cycles need safe compatibility behavior.
  selected_option: Use explicit API capability negotiation and supported-version windows
  status: accepted
  required_adr: null
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-12 — Capability decision and execution plan

> **Capability approval gate — proposed, recommendations resolved.** The planning agent has researched the credible alternatives and preselected the documented best-in-class recommendation for every material decision. Those choices are complete decisions. Reviewers may confirm the defaults or override a choice with explicit rationale; one approval then authorizes this packet and all contained slice plans at an immutable commit. No separate decision-selection stop is required.

<div class="visual-flow"><span>Review all slices</span><b>→</b><span>Confirm or override resolved defaults</span><b>→</b><span>Approve once</span><b>→</b><span>Run long capability campaign</span><b>→</b><span>Production readiness review</span></div>

## 0. Control and authority

| Field | Value |
|---|---|
| Capability | `CAP-12` — University-hosted deployment, institutional identity, collaboration, and operations |
| Baseline / supplemental release | 1.3 / 1.3.4 |
| Status | PROPOSED — recommendations resolved; capability approval pending |
| Execution mode | Long-running capability campaign |
| Slice count | 6 |
| Decision count | 18 |
| Review page | planning/review-site/CAP-12/index.html |

Authority order is Vision → accepted ADRs → Systems Design → authoritative backlog → approved capability packet → approved slice plans → approved UI reference for user-facing changes → automation rules and code/tests. The backlog remains authoritative for IDs, dependencies and status. This packet owns the architectural and product selections needed to execute the capability without repeated approval stops.

## 1. Capability outcome and production-ready exit

**Objective.** Run the same scholarly application against institution-controlled services and storage while preserving the desktop client, domain contracts, evidence lineage, and rights-aware governance.

The desktop uses a versioned client gateway; institution-hosted adapters implement the same repositories, objects, vector search and workflows using PostgreSQL, S3-compatible storage, Qdrant and Temporal. The first reference pilot is a hardened single-server container deployment.

The capability is not complete merely because its atomic tasks are checked off. Production readiness requires the following capability exits:

- The desktop can switch between local and university connection profiles without a forked interface or incompatible project semantics.
- University services provide SSO, project isolation, collaboration, licensed-source enforcement, durable workflows, observability, backup, and recovery.
- A pilot research group completes a full workflow under institution-approved security and operations controls.

The independent capability reviewer must trace each exit to immutable task, slice and end-to-end evidence; verify failure, denial, cancellation, restart, migration, security, accessibility and relevant platform behavior; and confirm that no concealed TODO or deferred production blocker remains.

## 2. Slice map and end-to-end dependency logic

| Slice | Title | Outcome | Wave | Priority | Depends on |
|---|---|---|---|---|---|
| `CAP-12.S01` | Desktop remote connection mode and API abstraction | The canonical client can connect securely to a university project home while retaining local caches and clear deployment context. | W10 | P2 | CAP-11.S06.T03 |
| `CAP-12.S02` | Institutional service and data-plane foundation | A deployable server stack implements the shared domain services with production-grade relational, object, vector, and workflow infrastructure. | W10 | P2 | CAP-12.S01.T01, CAP-03.S04.T03 |
| `CAP-12.S03` | Institutional identity, authorization, and project isolation | University users authenticate through OIDC and access only permitted projects, sources, models, and administrative functions. | W10 | P2 | CAP-12.S02.T03 |
| `CAP-12.S04` | Team collaboration and scholarly adjudication | Research groups can share projects, assign work, compare decisions, discuss disputes, and retain scholarly plurality. | W10 | P2 | CAP-12.S03.T03, CAP-08.S06.T02 |
| `CAP-12.S05` | Licensed sources, institutional rights, retention, and compute policy | Institutional entitlements and unpublished materials are governed consistently across search, storage, model egress, collaboration, and export. | W10 | P2 | CAP-12.S03.T02, CAP-04.S05.T03, CAP-07.S01.T03 |
| `CAP-12.S06` | Institutional operations, disaster recovery, and pilot acceptance | The university edition is observable, supportable, recoverable, and validated with a real research group. | W10 | P2 | CAP-12.S04.T03, CAP-12.S05.T03 |

Slices execute in backlog dependency order. A later slice may introduce an adapter or test fixture for an earlier contract, but it may not redefine an approved cross-slice decision. Each slice concludes with integration and independent review, after which the same campaign proceeds directly to the next ready slice. The capability pauses only for demonstrated infeasibility, a missing external prerequisite, unavailable required hardware, a genuinely new consequential human decision, a higher-authority conflict, or an approved design-reference gate.

## 3. Decision-making protocol

Before approval, the planning agent must verify every candidate against the Vision, architecture, other capability contracts, current official standards, primary research where appropriate, existing code and representative environments. Reviewers may accept the recommendation, select another listed option, or request a revised candidate set. Each accepted selection must include rationale and any ADR/reference requirement. Once approved, routine implementation, debugging, testing and slice transitions do not reopen the decision.

A decision may be reopened only when implementation evidence demonstrates infeasibility or material new evidence changes the risk/architecture boundary. The agent must document the failed assumption, strongest feasible alternatives, migration effect and recommendation on the static review page, obtain focused approval, and resume the same campaign.

## 4. Decision register

| ID | Decision | Candidates | Recommendation | Basis | ADR |
|---|---|---|---|---|---|
| `CAP-12-D01` | Client architecture | A. Keep one desktop UI and place local/remote implementations behind a versioned client gateway<br>B. Fork the desktop into a separate institutional application | **Keep one desktop UI and place local/remote implementations behind a versioned client gateway** | One experience and domain contract prevents semantic drift between deployment profiles. | ADR-REMOTE-CLIENT |
| `CAP-12-D02` | Institutional pilot topology | A. Use hardened OCI containers on one institution-controlled server with Compose or Podman; add Kubernetes only by ADR<br>B. Require Kubernetes before the first university pilot | **Use hardened OCI containers on one institution-controlled server with Compose or Podman; add Kubernetes only by ADR** | A single-server profile reduces operational burden while preserving container portability. | ADR-INSTITUTIONAL-TOPOLOGY |
| `CAP-12-D03` | Hosted persistence | A. Use PostgreSQL, S3-compatible objects, Qdrant and Temporal behind existing ports<br>B. Reuse shared filesystem and ad hoc background jobs | **Use PostgreSQL, S3-compatible objects, Qdrant and Temporal behind existing ports** | Production adapters preserve local semantics while adding concurrency, durability and operations. | None |
| `CAP-12-D04` | Authentication | A. Use system-browser OIDC authorization code with PKCE and short-lived sessions<br>B. Embed university credentials inside the desktop webview | **Use system-browser OIDC authorization code with PKCE and short-lived sessions** | OIDC federation and PKCE are appropriate for native clients and avoid password handling. | ADR-INSTITUTIONAL-IDENTITY |
| `CAP-12-D05` | Authorization | A. Combine role permissions, project/data attributes and default-deny PostgreSQL RLS<br>B. Use UI-hidden buttons as the primary access control | **Combine role permissions, project/data attributes and default-deny PostgreSQL RLS** | Defense in depth must be enforced at API and data boundaries. | None |
| `CAP-12-D06` | Project isolation | A. Carry project and organization scope through every repository, object, vector, workflow and audit operation<br>B. Filter projects only in service-layer queries | **Carry project and organization scope through every repository, object, vector, workflow and audit operation** | Isolation tests must cover every storage and execution plane. | None |
| `CAP-12-D07` | Provisioning readiness | A. Model stable subject IDs and groups now; add SCIM only when institutional lifecycle automation is required<br>B. Build a proprietary user directory and manual account lifecycle | **Model stable subject IDs and groups now; add SCIM only when institutional lifecycle automation is required** | Federated identity should remain portable without prematurely mandating provisioning infrastructure. | None |
| `CAP-12-D08` | Collaboration semantics | A. Use immutable revisions, optimistic concurrency and explicit conflict/adjudication objects<br>B. Use last-writer-wins updates | **Use immutable revisions, optimistic concurrency and explicit conflict/adjudication objects** | Scholarly disagreement and simultaneous review cannot be safely collapsed. | None |
| `CAP-12-D09` | Offline cache | A. Allow encrypted, rights-bounded read cache with explicit expiration and no offline writes by default<br>B. Mirror whole institutional projects locally | **Allow encrypted, rights-bounded read cache with explicit expiration and no offline writes by default** | Remote projects must preserve rights and conflict guarantees while providing limited resilience. | None |
| `CAP-12-D10` | Rights enforcement | A. Evaluate entitlements at acquisition, view, derivation, export and cache boundaries<br>B. Check license only when a document is downloaded | **Evaluate entitlements at acquisition, view, derivation, export and cache boundaries** | Institutional source rights continue to govern downstream use and redistribution. | None |
| `CAP-12-D11` | Model egress | A. Use institution policy to route local, private hosted or approved external models with fail-closed payload checks<br>B. Let each user send any project content to any provider | **Use institution policy to route local, private hosted or approved external models with fail-closed payload checks** | Private manuscripts and licensed text require enforceable egress governance. | None |
| `CAP-12-D12` | Retention and legal hold | A. Use versioned policy, deletion workflow, legal-hold override and auditable exceptions<br>B. Use one hard-coded deletion interval | **Use versioned policy, deletion workflow, legal-hold override and auditable exceptions** | Institutional records require explainable retention and exception handling. | None |
| `CAP-12-D13` | Observability | A. Use OpenTelemetry with project/tenant context and strict content redaction<br>B. Centralize raw prompts, source passages and reports in logs | **Use OpenTelemetry with project/tenant context and strict content redaction** | Operations require traceability without duplicating sensitive research content. | None |
| `CAP-12-D14` | Disaster recovery | A. Declare service-specific RPO/RTO, encrypted backups and regularly exercised restore drills<br>B. Assume database replication is sufficient recovery | **Declare service-specific RPO/RTO, encrypted backups and regularly exercised restore drills** | Recovery evidence must include relational, object, vector and workflow state. | None |
| `CAP-12-D15` | Administration experience | A. Design a bounded institution operations console only after governed UI-reference approval<br>B. Expose database and cluster tools directly to research users | **Design a bounded institution operations console only after governed UI-reference approval** | Operational controls need role-appropriate, approved interaction design. | ADR-INSTITUTIONAL-ADMIN-UX |
| `CAP-12-D16` | Pilot acceptance | A. Run a complete research-group workflow under institutional security, rights and recovery controls<br>B. Approve deployment after infrastructure smoke tests | **Run a complete research-group workflow under institutional security, rights and recovery controls** | The institutional product is only complete when scholarly work succeeds end to end. | None |
| `CAP-12-D17` | Audit trail | A. Append security, rights, collaboration and admin events to tamper-evident provenance/audit records<br>B. Store only conventional web access logs | **Append security, rights, collaboration and admin events to tamper-evident provenance/audit records** | Research decisions and institutional controls require durable accountability. | None |
| `CAP-12-D18` | Service compatibility | A. Use explicit API capability negotiation and supported-version windows<br>B. Assume desktop and server are always upgraded together | **Use explicit API capability negotiation and supported-version windows** | Independent desktop/server release cycles need safe compatibility behavior. | None |

Every decision is resolved by the documented best-in-class recommendation: `selected_option` equals `recommendation`, status is `accepted`, and `decision_completion` is `complete`. Reviewers may override a selection before capability approval, but every non-recommended selection requires explicit rationale. Approval remains the one authorization gate for the capability and all slice plans.

## 5. Cross-slice architecture contract

The desktop uses a versioned client gateway; institution-hosted adapters implement the same repositories, objects, vector search and workflows using PostgreSQL, S3-compatible storage, Qdrant and Temporal. The first reference pilot is a hardened single-server container deployment.

Cross-slice invariants:

- Canonical scholarly records, evidence, accepted human decisions, rights state and provenance remain authoritative. Indexes, projections, caches, generated recommendations and operational dashboards are replaceable derivatives.
- Local, institutional and cloud profiles use the same domain identifiers, status semantics, evidence/provenance contracts and workflow meanings; infrastructure adapters may differ.
- Every long operation has stable identity, inputs/manifests, progress, cancellation, retry/checkpoint/restart and evidence records.
- Unknown, unavailable, denied, not reported, inferred, disputed, stale and failed remain distinct states.
- Provider, platform, database, cluster and UI framework objects do not escape their adapters into portable domain contracts.
- CAP-16–CAP-19 consume stable study/evidence/manuscript interfaces rather than internal storage tables or deployment SDK types.

## 6. Experience and workflow contract

Researchers keep the same adaptive workflow navigation. Deployment context, institutional policy, collaboration and rights state are explicit. New administrative surfaces require governed UI-reference approval.

Approved reference exposure: No new researcher-facing page is pre-approved for this capability; any user-facing administrative surface requires a governed reference update before implementation.

Researcher-facing behavior must preserve the selected project objective, numbered primary stages, previous/next actions, expected output, supporting-tool relationship, inspect–contest–adjudicate interaction and visible provenance. Intentional UI change follows reference first: update the style guide, workflow/page contracts and HTML mockups; run validators; obtain explicit approval and a new reference ID; then implement. A defect restoration to the approved reference does not need a new design decision.

## 7. Security, privacy, rights and research-integrity decisions

OIDC/PKCE, default-deny RBAC/ABAC and PostgreSQL RLS, project isolation, institutional egress policy, retention/legal hold and audited operations are mandatory.

The capability must treat documents, model files, provider responses, archives, URLs, imported data and rich text as untrusted. Least privilege, schema validation, path/destination controls, bounded resources, output encoding, redacted diagnostics and explicit egress policy apply at each trust boundary. The system may recommend and organize evidence but may not fabricate sources, permissions, performance, approval, methodological validity or completion evidence.

## 8. Capability-wide verification strategy

The verification program combines task tests, slice integration, capability end-to-end acceptance and independent review. It must include:

- Contract and schema compatibility across all six slices and affected neighboring capabilities.
- Representative success paths plus material denial, cancellation, restart, migration and recovery paths.
- Security, privacy, rights and research-integrity attack fixtures.
- Accessibility and governed-reference conformance for user-facing work.
- Performance, endurance, resource and cost evidence against declared profiles.
- Clean-environment packaging/deployment tests for each applicable target.
- Criterion-to-evidence manifests tied to the reviewed commit and immutable fixture/model/provider versions.

## 9. Long-running execution contract

After one-time approval, `taskctl capability start CAP-12` selects the first dependency-ready slice and continues through the capability. The agent does not ask again about settled options. Each task produces machine-linked evidence; each slice receives independent integration review; the campaign immediately advances when the next slice is ready. If a classified blocker occurs, the agent preserves work, records the exact affected decision/assumption and provides the static review URL rather than creating an unstructured chat approval.

## 10. Plan and approval checklist

- [ ] Every slice has exactly one structurally valid plan using the governed template.
- [ ] All listed decisions have a selected option, rationale and accepted status.
- [ ] Required ADRs and design-reference changes are accepted.
- [ ] Dependencies, credentials, source/model licenses, hardware and fixtures are available or have approved deterministic substitutes.
- [ ] Capability and slice plans are approved by the same reviewer at the same immutable commit.
- [ ] `python tools/planctl.py ready CAP-12 --require-approved` passes.
- [ ] Static review site matches plan hashes and provides the approved decision record.

## 11. Research and technical basis

| Key | Source | Publisher | Planning use |
|---|---|---|---|
| `OIDC` | [OpenID Connect Core 1.0 incorporating errata set 2](https://openid.net/specs/openid-connect-core-1_0.html) | OpenID Foundation | Institutional and cloud identity federation. |
| `PKCE` | [RFC 7636: Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636) | IETF | Native-app authorization-code protection. |
| `NIST_ZERO_TRUST` | [Zero Trust Architecture SP 800-207](https://csrc.nist.gov/pubs/sp/800/207/final) | NIST | Identity- and policy-centric institutional access. |
| `OTEL` | [OpenTelemetry Specification](https://opentelemetry.io/docs/specs/otel/) | OpenTelemetry | Portable traces, metrics and logs. |
| `TEMPORAL` | [Temporal Documentation](https://docs.temporal.io/) | Temporal | Durable hosted workflow execution. |
| `POSTGRES_RLS` | [PostgreSQL Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) | PostgreSQL | Default-deny row-level data isolation. |
| `SLSA` | [SLSA Specification 1.2](https://slsa.dev/spec/v1.2/) | OpenSSF / Linux Foundation | Build provenance and supply-chain assurance. |
| `SCIM` | [RFC 7644: SCIM Protocol](https://www.rfc-editor.org/rfc/rfc7644) | IETF | Provisioning and lifecycle interoperability. |
| `PROV_O` | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) | W3C | Interoperable research provenance. |
| `NIST_AI_SSDF` | [Secure Software Development Practices for Generative AI and Dual-Use Foundation Models SP 800-218A](https://csrc.nist.gov/pubs/sp/800/218/a/final) | NIST | AI-specific secure development practices. |

Official documentation and standards define platform behavior; primary scholarly sources and reporting standards define research-method requirements. Versions, licenses, provider contracts and current target support must be rechecked at capability approval and pinned in accepted ADRs/manifests. A cited source supports a recommendation but does not replace project-specific benchmarks, threat analysis, institutional policy or expert methods review.

## 12. Approval record

| Field | Value |
|---|---|
| Decision completion | Complete — resolved by best-in-class recommendations |
| Packet approval | Pending |
| Approved by | — |
| Approved at | — |
| Approved commit | — |
| Decision feedback | Export from `planning/review-site/CAP-12/index.html` and apply with `planctl`; feedback alone does not approve execution. |
