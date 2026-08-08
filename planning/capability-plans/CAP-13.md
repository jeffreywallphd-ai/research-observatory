---
plan_schema_version: '1.1'
document_type: capability-decision-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-13
title: Managed cloud control plane, tenant data planes, governance, and SaaS operations
status: proposed
execution_mode: long-running-capability-campaign
decision_completion: complete
open_blocking_decisions: []
slice_ids:
- CAP-13.S01
- CAP-13.S02
- CAP-13.S03
- CAP-13.S04
- CAP-13.S05
- CAP-13.S06
decisions:
- id: CAP-13-D01
  title: Control/data plane split
  candidates:
  - Keep global control plane free of routine research content; place projects in regional tenant data planes
  - Store all tenant content in one global application database
  recommendation: Keep global control plane free of routine research content; place projects in regional tenant data planes
  recommendation_basis: The split supports residency, isolation and smaller blast radius.
  selected_option: Keep global control plane free of routine research content; place projects in regional tenant data planes
  status: accepted
  required_adr: ADR-CLOUD-TOPOLOGY
- id: CAP-13-D02
  title: Isolation tiers
  candidates:
  - Offer shared, isolated and dedicated tiers with explicit guarantees and migration paths
  - Use one implicit shared-tenancy model for all customers
  recommendation: Offer shared, isolated and dedicated tiers with explicit guarantees and migration paths
  recommendation_basis: Research organizations vary in risk, regulatory and performance requirements.
  selected_option: Offer shared, isolated and dedicated tiers with explicit guarantees and migration paths
  status: accepted
  required_adr: null
- id: CAP-13-D03
  title: Tenant context
  candidates:
  - Require validated tenant/project identity on every request, event, object key, workflow and metric
  - Infer tenancy from UI route or optional query parameters
  recommendation: Require validated tenant/project identity on every request, event, object key, workflow and metric
  recommendation_basis: Tenant context must be mandatory and testable across all planes.
  selected_option: Require validated tenant/project identity on every request, event, object key, workflow and metric
  status: accepted
  required_adr: null
- id: CAP-13-D04
  title: Orchestration
  candidates:
  - Use Kubernetes, GitOps and infrastructure-as-code for managed cloud only
  - Extend the university Compose profile manually into production cloud
  recommendation: Use Kubernetes, GitOps and infrastructure-as-code for managed cloud only
  recommendation_basis: Managed multi-region SaaS requires declarative scaling and repeatable controls.
  selected_option: Use Kubernetes, GitOps and infrastructure-as-code for managed cloud only
  status: accepted
  required_adr: ADR-CLOUD-ORCHESTRATION
- id: CAP-13-D05
  title: Cluster isolation
  candidates:
  - Default-deny network policies, namespace/resource quotas and stronger isolated/dedicated options
  - Trust application authentication inside a flat cluster network
  recommendation: Default-deny network policies, namespace/resource quotas and stronger isolated/dedicated options
  recommendation_basis: Kubernetes itself describes multi-tenancy as a spectrum requiring policy, fairness and data-plane controls.
  selected_option: Default-deny network policies, namespace/resource quotas and stronger isolated/dedicated options
  status: accepted
  required_adr: null
- id: CAP-13-D06
  title: Workload identity
  candidates:
  - Use cloud-native workload identity behind a SPIFFE-compatible service identity interface
  - Distribute long-lived service credentials in environment files
  recommendation: Use cloud-native workload identity behind a SPIFFE-compatible service identity interface
  recommendation_basis: Short-lived workload identities reduce credential theft and improve service authorization.
  selected_option: Use cloud-native workload identity behind a SPIFFE-compatible service identity interface
  status: accepted
  required_adr: null
- id: CAP-13-D07
  title: Cloud identity
  candidates:
  - Federate OIDC, require MFA policy support and separate human from workload identities
  - Maintain local SaaS passwords as the primary identity
  recommendation: Federate OIDC, require MFA policy support and separate human from workload identities
  recommendation_basis: Enterprise customers need federation and centralized access policy.
  selected_option: Federate OIDC, require MFA policy support and separate human from workload identities
  status: accepted
  required_adr: null
- id: CAP-13-D08
  title: Entitlements
  candidates:
  - Use versioned product entitlements and quotas independent of payment-provider objects
  - Gate features directly on billing-provider plan IDs
  recommendation: Use versioned product entitlements and quotas independent of payment-provider objects
  recommendation_basis: Domain entitlements must survive provider changes and support contracts/grants.
  selected_option: Use versioned product entitlements and quotas independent of payment-provider objects
  status: accepted
  required_adr: null
- id: CAP-13-D09
  title: Metering
  candidates:
  - Emit idempotent CloudEvents to an append-only usage ledger
  - Calculate billable usage from mutable operational metrics
  recommendation: Emit idempotent CloudEvents to an append-only usage ledger
  recommendation_basis: Billing and cost governance need replayable, deduplicated source events.
  selected_option: Emit idempotent CloudEvents to an append-only usage ledger
  status: accepted
  required_adr: null
- id: CAP-13-D10
  title: Cost normalization
  candidates:
  - Map cost and usage to FOCUS 1.4-compatible records and dimensions
  - Use provider-specific billing schemas throughout the product
  recommendation: Map cost and usage to FOCUS 1.4-compatible records and dimensions
  recommendation_basis: A normalized model supports multi-cloud reconciliation and internal cost attribution.
  selected_option: Map cost and usage to FOCUS 1.4-compatible records and dimensions
  status: accepted
  required_adr: null
- id: CAP-13-D11
  title: Elastic work queues
  candidates:
  - Separate interactive, batch, model, parser and maintenance queues with budgets and fairness
  - Run all jobs in one autoscaled queue
  recommendation: Separate interactive, batch, model, parser and maintenance queues with budgets and fairness
  recommendation_basis: Queue classes protect latency and prevent large tenants from monopolizing capacity.
  selected_option: Separate interactive, batch, model, parser and maintenance queues with budgets and fairness
  status: accepted
  required_adr: null
- id: CAP-13-D12
  title: Model routing
  candidates:
  - Route by data class, residency, tenant policy, quality, cost and availability with deterministic fallback
  - Use the cheapest available model globally
  recommendation: Route by data class, residency, tenant policy, quality, cost and availability with deterministic fallback
  recommendation_basis: Research confidentiality and reproducibility constrain model selection.
  selected_option: Route by data class, residency, tenant policy, quality, cost and availability with deterministic fallback
  status: accepted
  required_adr: null
- id: CAP-13-D13
  title: Cost controls
  candidates:
  - Apply budgets, reservations, quotas, anomaly detection and circuit breakers before work starts
  - Report unexpected cost after execution
  recommendation: Apply budgets, reservations, quotas, anomaly detection and circuit breakers before work starts
  recommendation_basis: Pre-execution controls are necessary for sustainable autonomous workloads.
  selected_option: Apply budgets, reservations, quotas, anomaly detection and circuit breakers before work starts
  status: accepted
  required_adr: null
- id: CAP-13-D14
  title: Encryption
  candidates:
  - Use envelope encryption with KMS-managed tenant/region keys and dedicated-key options
  - Use one application-wide encryption key
  recommendation: Use envelope encryption with KMS-managed tenant/region keys and dedicated-key options
  recommendation_basis: Key scoping enables tenant separation, rotation and dedicated guarantees.
  selected_option: Use envelope encryption with KMS-managed tenant/region keys and dedicated-key options
  status: accepted
  required_adr: null
- id: CAP-13-D15
  title: Residency/deletion
  candidates:
  - Bind projects to a region, version retention policy and prove deletion across primary, backup and derivative stores
  - Treat region as a UI preference
  recommendation: Bind projects to a region, version retention policy and prove deletion across primary, backup and derivative stores
  recommendation_basis: Residency and deletion claims must be technically enforced and auditable.
  selected_option: Bind projects to a region, version retention policy and prove deletion across primary, backup and derivative stores
  status: accepted
  required_adr: null
- id: CAP-13-D16
  title: Service reliability
  candidates:
  - Publish SLOs, error budgets, canary releases and automated rollback
  - Use uptime dashboards without release/error-budget policy
  recommendation: Publish SLOs, error budgets, canary releases and automated rollback
  recommendation_basis: Reliability objectives must govern change velocity and incident response.
  selected_option: Publish SLOs, error budgets, canary releases and automated rollback
  status: accepted
  required_adr: null
- id: CAP-13-D17
  title: Supply chain
  candidates:
  - Require signed images, SBOM and SLSA build provenance at deployment admission
  - Scan mutable latest images after deployment
  recommendation: Require signed images, SBOM and SLSA build provenance at deployment admission
  recommendation_basis: Cloud scale increases the impact of compromised build artifacts.
  selected_option: Require signed images, SBOM and SLSA build provenance at deployment admission
  status: accepted
  required_adr: null
- id: CAP-13-D18
  title: Launch gate
  candidates:
  - Require tenant-isolation, recovery, cost, security and complete desktop-cloud workflow evidence
  - Launch after infrastructure and billing are connected
  recommendation: Require tenant-isolation, recovery, cost, security and complete desktop-cloud workflow evidence
  recommendation_basis: SaaS readiness is an end-to-end product and governance claim.
  selected_option: Require tenant-isolation, recovery, cost, security and complete desktop-cloud workflow evidence
  status: accepted
  required_adr: null
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-13 — Capability decision and execution plan

> **Capability approval gate — proposed, recommendations resolved.** The planning agent has researched the credible alternatives and preselected the documented best-in-class recommendation for every material decision. Those choices are complete decisions. Reviewers may confirm the defaults or override a choice with explicit rationale; one approval then authorizes this packet and all contained slice plans at an immutable commit. No separate decision-selection stop is required.

<div class="visual-flow"><span>Review all slices</span><b>→</b><span>Confirm or override resolved defaults</span><b>→</b><span>Approve once</span><b>→</b><span>Run long capability campaign</span><b>→</b><span>Production readiness review</span></div>

## 0. Control and authority

| Field | Value |
|---|---|
| Capability | `CAP-13` — Managed cloud control plane, tenant data planes, governance, and SaaS operations |
| Baseline / supplemental release | 1.3 / 1.3.4 |
| Status | PROPOSED — recommendations resolved; capability approval pending |
| Execution mode | Long-running capability campaign |
| Slice count | 6 |
| Decision count | 18 |
| Review page | planning/review-site/CAP-13/index.html |

Authority order is Vision → accepted ADRs → Systems Design → authoritative backlog → approved capability packet → approved slice plans → approved UI reference for user-facing changes → automation rules and code/tests. The backlog remains authoritative for IDs, dependencies and status. This packet owns the architectural and product selections needed to execute the capability without repeated approval stops.

## 1. Capability outcome and production-ready exit

**Objective.** Deliver the same desktop-led product as a secure managed service with regional tenant isolation, elastic workers, metering, residency, support, and commercial operations.

A content-minimizing global control plane governs organizations and routing; regional data planes host tenant research state. Kubernetes, GitOps and infrastructure-as-code are cloud-only deployment choices with shared, isolated and dedicated tiers.

The capability is not complete merely because its atomic tasks are checked off. Production readiness requires the following capability exits:

- Organizations and tenant data planes provision through a governed control plane with tested isolation and residency.
- Cloud compute, model use, storage, quotas, billing, audit, incident response, backup, and disaster recovery meet declared service objectives.
- Cloud delivery preserves the local/university evidence, provenance, rights, and bounded-novelty semantics rather than weakening them for convenience.

The independent capability reviewer must trace each exit to immutable task, slice and end-to-end evidence; verify failure, denial, cancellation, restart, migration, security, accessibility and relevant platform behavior; and confirm that no concealed TODO or deferred production blocker remains.

## 2. Slice map and end-to-end dependency logic

| Slice | Title | Outcome | Wave | Priority | Depends on |
|---|---|---|---|---|---|
| `CAP-13.S01` | SaaS organization and tenant control plane | Organizations, regions, plans, policies, and tenant resources are provisioned through auditable lifecycle workflows. | W11 | P3 | CAP-12.S06.T03 |
| `CAP-13.S02` | Regional tenant data planes and isolation tiers | Tenant data is hosted in declared regions using pooled, dedicated-schema, dedicated-database, or dedicated-deployment isolation as policy requires. | W11 | P3 | CAP-13.S01.T03, CAP-12.S02.T03 |
| `CAP-13.S03` | Cloud identity, entitlement, metering, and billing | Organizations can govern membership and plans while usage is measured transparently by value-driving resource. | W11 | P3 | CAP-13.S01.T02 |
| `CAP-13.S04` | Elastic workers, models, search, and cost governance | Cloud analytical workloads scale by class without sacrificing reproducibility, rights, or budget controls. | W11 | P3 | CAP-13.S02.T02, CAP-07.S05.T02 |
| `CAP-13.S05` | Cloud security, privacy, residency, and compliance operations | Security and privacy controls operate continuously across tenant, regional, administrative, and software-supply-chain boundaries. | W11 | P3 | CAP-13.S02.T03, CAP-13.S03.T01 |
| `CAP-13.S06` | Desktop-cloud experience, service reliability, and launch gate | Cloud customers use the canonical desktop with clear synchronization, reliability, support, and service-status behavior. | W11 | P3 | CAP-13.S04.T03, CAP-13.S05.T03 |

Slices execute in backlog dependency order. A later slice may introduce an adapter or test fixture for an earlier contract, but it may not redefine an approved cross-slice decision. Each slice concludes with integration and independent review, after which the same campaign proceeds directly to the next ready slice. The capability pauses only for demonstrated infeasibility, a missing external prerequisite, unavailable required hardware, a genuinely new consequential human decision, a higher-authority conflict, or an approved design-reference gate.

## 3. Decision-making protocol

Before approval, the planning agent must verify every candidate against the Vision, architecture, other capability contracts, current official standards, primary research where appropriate, existing code and representative environments. Reviewers may accept the recommendation, select another listed option, or request a revised candidate set. Each accepted selection must include rationale and any ADR/reference requirement. Once approved, routine implementation, debugging, testing and slice transitions do not reopen the decision.

A decision may be reopened only when implementation evidence demonstrates infeasibility or material new evidence changes the risk/architecture boundary. The agent must document the failed assumption, strongest feasible alternatives, migration effect and recommendation on the static review page, obtain focused approval, and resume the same campaign.

## 4. Decision register

| ID | Decision | Candidates | Recommendation | Basis | ADR |
|---|---|---|---|---|---|
| `CAP-13-D01` | Control/data plane split | A. Keep global control plane free of routine research content; place projects in regional tenant data planes<br>B. Store all tenant content in one global application database | **Keep global control plane free of routine research content; place projects in regional tenant data planes** | The split supports residency, isolation and smaller blast radius. | ADR-CLOUD-TOPOLOGY |
| `CAP-13-D02` | Isolation tiers | A. Offer shared, isolated and dedicated tiers with explicit guarantees and migration paths<br>B. Use one implicit shared-tenancy model for all customers | **Offer shared, isolated and dedicated tiers with explicit guarantees and migration paths** | Research organizations vary in risk, regulatory and performance requirements. | None |
| `CAP-13-D03` | Tenant context | A. Require validated tenant/project identity on every request, event, object key, workflow and metric<br>B. Infer tenancy from UI route or optional query parameters | **Require validated tenant/project identity on every request, event, object key, workflow and metric** | Tenant context must be mandatory and testable across all planes. | None |
| `CAP-13-D04` | Orchestration | A. Use Kubernetes, GitOps and infrastructure-as-code for managed cloud only<br>B. Extend the university Compose profile manually into production cloud | **Use Kubernetes, GitOps and infrastructure-as-code for managed cloud only** | Managed multi-region SaaS requires declarative scaling and repeatable controls. | ADR-CLOUD-ORCHESTRATION |
| `CAP-13-D05` | Cluster isolation | A. Default-deny network policies, namespace/resource quotas and stronger isolated/dedicated options<br>B. Trust application authentication inside a flat cluster network | **Default-deny network policies, namespace/resource quotas and stronger isolated/dedicated options** | Kubernetes itself describes multi-tenancy as a spectrum requiring policy, fairness and data-plane controls. | None |
| `CAP-13-D06` | Workload identity | A. Use cloud-native workload identity behind a SPIFFE-compatible service identity interface<br>B. Distribute long-lived service credentials in environment files | **Use cloud-native workload identity behind a SPIFFE-compatible service identity interface** | Short-lived workload identities reduce credential theft and improve service authorization. | None |
| `CAP-13-D07` | Cloud identity | A. Federate OIDC, require MFA policy support and separate human from workload identities<br>B. Maintain local SaaS passwords as the primary identity | **Federate OIDC, require MFA policy support and separate human from workload identities** | Enterprise customers need federation and centralized access policy. | None |
| `CAP-13-D08` | Entitlements | A. Use versioned product entitlements and quotas independent of payment-provider objects<br>B. Gate features directly on billing-provider plan IDs | **Use versioned product entitlements and quotas independent of payment-provider objects** | Domain entitlements must survive provider changes and support contracts/grants. | None |
| `CAP-13-D09` | Metering | A. Emit idempotent CloudEvents to an append-only usage ledger<br>B. Calculate billable usage from mutable operational metrics | **Emit idempotent CloudEvents to an append-only usage ledger** | Billing and cost governance need replayable, deduplicated source events. | None |
| `CAP-13-D10` | Cost normalization | A. Map cost and usage to FOCUS 1.4-compatible records and dimensions<br>B. Use provider-specific billing schemas throughout the product | **Map cost and usage to FOCUS 1.4-compatible records and dimensions** | A normalized model supports multi-cloud reconciliation and internal cost attribution. | None |
| `CAP-13-D11` | Elastic work queues | A. Separate interactive, batch, model, parser and maintenance queues with budgets and fairness<br>B. Run all jobs in one autoscaled queue | **Separate interactive, batch, model, parser and maintenance queues with budgets and fairness** | Queue classes protect latency and prevent large tenants from monopolizing capacity. | None |
| `CAP-13-D12` | Model routing | A. Route by data class, residency, tenant policy, quality, cost and availability with deterministic fallback<br>B. Use the cheapest available model globally | **Route by data class, residency, tenant policy, quality, cost and availability with deterministic fallback** | Research confidentiality and reproducibility constrain model selection. | None |
| `CAP-13-D13` | Cost controls | A. Apply budgets, reservations, quotas, anomaly detection and circuit breakers before work starts<br>B. Report unexpected cost after execution | **Apply budgets, reservations, quotas, anomaly detection and circuit breakers before work starts** | Pre-execution controls are necessary for sustainable autonomous workloads. | None |
| `CAP-13-D14` | Encryption | A. Use envelope encryption with KMS-managed tenant/region keys and dedicated-key options<br>B. Use one application-wide encryption key | **Use envelope encryption with KMS-managed tenant/region keys and dedicated-key options** | Key scoping enables tenant separation, rotation and dedicated guarantees. | None |
| `CAP-13-D15` | Residency/deletion | A. Bind projects to a region, version retention policy and prove deletion across primary, backup and derivative stores<br>B. Treat region as a UI preference | **Bind projects to a region, version retention policy and prove deletion across primary, backup and derivative stores** | Residency and deletion claims must be technically enforced and auditable. | None |
| `CAP-13-D16` | Service reliability | A. Publish SLOs, error budgets, canary releases and automated rollback<br>B. Use uptime dashboards without release/error-budget policy | **Publish SLOs, error budgets, canary releases and automated rollback** | Reliability objectives must govern change velocity and incident response. | None |
| `CAP-13-D17` | Supply chain | A. Require signed images, SBOM and SLSA build provenance at deployment admission<br>B. Scan mutable latest images after deployment | **Require signed images, SBOM and SLSA build provenance at deployment admission** | Cloud scale increases the impact of compromised build artifacts. | None |
| `CAP-13-D18` | Launch gate | A. Require tenant-isolation, recovery, cost, security and complete desktop-cloud workflow evidence<br>B. Launch after infrastructure and billing are connected | **Require tenant-isolation, recovery, cost, security and complete desktop-cloud workflow evidence** | SaaS readiness is an end-to-end product and governance claim. | None |

Every decision is resolved by the documented best-in-class recommendation: `selected_option` equals `recommendation`, status is `accepted`, and `decision_completion` is `complete`. Reviewers may override a selection before capability approval, but every non-recommended selection requires explicit rationale. Approval remains the one authorization gate for the capability and all slice plans.

## 5. Cross-slice architecture contract

A content-minimizing global control plane governs organizations and routing; regional data planes host tenant research state. Kubernetes, GitOps and infrastructure-as-code are cloud-only deployment choices with shared, isolated and dedicated tiers.

Cross-slice invariants:

- Canonical scholarly records, evidence, accepted human decisions, rights state and provenance remain authoritative. Indexes, projections, caches, generated recommendations and operational dashboards are replaceable derivatives.
- Local, institutional and cloud profiles use the same domain identifiers, status semantics, evidence/provenance contracts and workflow meanings; infrastructure adapters may differ.
- Every long operation has stable identity, inputs/manifests, progress, cancellation, retry/checkpoint/restart and evidence records.
- Unknown, unavailable, denied, not reported, inferred, disputed, stale and failed remain distinct states.
- Provider, platform, database, cluster and UI framework objects do not escape their adapters into portable domain contracts.
- CAP-16–CAP-19 consume stable study/evidence/manuscript interfaces rather than internal storage tables or deployment SDK types.

## 6. Experience and workflow contract

The desktop remains the primary researcher UI. Region, tier, service status, quotas and cost-impacting actions are visible without exposing cloud internals. New SaaS administration or billing pages require reference-first design approval.

Approved reference exposure: No new researcher-facing page is pre-approved for this capability; any user-facing administrative surface requires a governed reference update before implementation.

Researcher-facing behavior must preserve the selected project objective, numbered primary stages, previous/next actions, expected output, supporting-tool relationship, inspect–contest–adjudicate interaction and visible provenance. Intentional UI change follows reference first: update the style guide, workflow/page contracts and HTML mockups; run validators; obtain explicit approval and a new reference ID; then implement. A defect restoration to the approved reference does not need a new design decision.

## 7. Security, privacy, rights and research-integrity decisions

Mandatory tenant context, workload identity, default-deny networking, scoped encryption keys, residency/deletion evidence, signed supply chain and continuous isolation tests define the cloud boundary.

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

After one-time approval, `taskctl capability start CAP-13` selects the first dependency-ready slice and continues through the capability. The agent does not ask again about settled options. Each task produces machine-linked evidence; each slice receives independent integration review; the campaign immediately advances when the next slice is ready. If a classified blocker occurs, the agent preserves work, records the exact affected decision/assumption and provides the static review URL rather than creating an unstructured chat approval.

## 10. Plan and approval checklist

- [ ] Every slice has exactly one structurally valid plan using the governed template.
- [ ] All listed decisions have a selected option, rationale and accepted status.
- [ ] Required ADRs and design-reference changes are accepted.
- [ ] Dependencies, credentials, source/model licenses, hardware and fixtures are available or have approved deterministic substitutes.
- [ ] Capability and slice plans are approved by the same reviewer at the same immutable commit.
- [ ] `python tools/planctl.py ready CAP-13 --require-approved` passes.
- [ ] Static review site matches plan hashes and provides the approved decision record.

## 11. Research and technical basis

| Key | Source | Publisher | Planning use |
|---|---|---|---|
| `NIST_ZERO_TRUST` | [Zero Trust Architecture SP 800-207](https://csrc.nist.gov/pubs/sp/800/207/final) | NIST | Identity- and policy-centric institutional access. |
| `CLOUDEVENTS` | [CloudEvents Specification](https://cloudevents.io/) | CNCF | Portable event envelopes and metering events. |
| `OTEL` | [OpenTelemetry Specification](https://opentelemetry.io/docs/specs/otel/) | OpenTelemetry | Portable traces, metrics and logs. |
| `K8S_MULTI` | [Kubernetes Multi-tenancy](https://kubernetes.io/docs/concepts/security/multi-tenancy/) | Kubernetes | Namespace, network, quota and isolation patterns. |
| `K8S_NETPOL` | [Kubernetes Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/) | Kubernetes | Default-deny tenant network isolation. |
| `K8S_QUOTA` | [Kubernetes Resource Quotas](https://kubernetes.io/docs/concepts/policy/resource-quotas/) | Kubernetes | Tenant fairness and capacity governance. |
| `SLSA` | [SLSA Specification 1.2](https://slsa.dev/spec/v1.2/) | OpenSSF / Linux Foundation | Build provenance and supply-chain assurance. |
| `OIDC` | [OpenID Connect Core 1.0 incorporating errata set 2](https://openid.net/specs/openid-connect-core-1_0.html) | OpenID Foundation | Institutional and cloud identity federation. |
| `FOCUS` | [FinOps Open Cost and Usage Specification 1.4](https://focus.finops.org/focus-specification/) | FinOps Foundation | Normalized cloud usage and cost records. |
| `SPIFFE` | [SPIFFE Specifications](https://spiffe.io/docs/latest/spiffe-about/overview/) | CNCF | Workload identity and service authentication. |
| `NIST_AI_SSDF` | [Secure Software Development Practices for Generative AI and Dual-Use Foundation Models SP 800-218A](https://csrc.nist.gov/pubs/sp/800/218/a/final) | NIST | AI-specific secure development practices. |
| `NIST_SSDF` | [Secure Software Development Framework SP 800-218](https://csrc.nist.gov/pubs/sp/800/218/final) | NIST | Secure development and release controls. |

Official documentation and standards define platform behavior; primary scholarly sources and reporting standards define research-method requirements. Versions, licenses, provider contracts and current target support must be rechecked at capability approval and pinned in accepted ADRs/manifests. A cited source supports a recommendation but does not replace project-specific benchmarks, threat analysis, institutional policy or expert methods review.

## 12. Approval record

| Field | Value |
|---|---|
| Decision completion | Complete — resolved by best-in-class recommendations |
| Packet approval | Pending |
| Approved by | — |
| Approved at | — |
| Approved commit | — |
| Decision feedback | Export from `planning/review-site/CAP-13/index.html` and apply with `planctl`; feedback alone does not approve execution. |
