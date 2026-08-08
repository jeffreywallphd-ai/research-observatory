---
plan_schema_version: '1.1'
document_type: capability-decision-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-14
title: Cross-platform desktop qualification and release
status: proposed
execution_mode: long-running-capability-campaign
decision_completion: complete
open_blocking_decisions: []
slice_ids:
- CAP-14.S01
- CAP-14.S02
- CAP-14.S03
- CAP-14.S04
- CAP-14.S05
- CAP-14.S06
decisions:
- id: CAP-14-D01
  title: Codebase strategy
  candidates:
  - Use one shared desktop/core codebase with narrow platform adapter ports and no feature forks
  - Maintain independent Windows, macOS and Linux implementations
  recommendation: Use one shared desktop/core codebase with narrow platform adapter ports and no feature forks
  recommendation_basis: Shared semantics and tests are essential for project portability and maintainability.
  selected_option: Use one shared desktop/core codebase with narrow platform adapter ports and no feature forks
  status: accepted
  required_adr: ADR-DESKTOP-PLATFORM-PORTS
- id: CAP-14-D02
  title: Qualification matrix
  candidates:
  - Qualify Windows x64, Apple Silicon macOS, Linux x86_64 and Linux ARM64 as explicit targets
  - Claim generic cross-platform support from framework compatibility
  recommendation: Qualify Windows x64, Apple Silicon macOS, Linux x86_64 and Linux ARM64 as explicit targets
  recommendation_basis: Native dependencies, sidecars, credential stores and installers require target-specific evidence.
  selected_option: Qualify Windows x64, Apple Silicon macOS, Linux x86_64 and Linux ARM64 as explicit targets
  status: accepted
  required_adr: null
- id: CAP-14-D03
  title: macOS distribution
  candidates:
  - Use Developer ID signing, hardened runtime, notarization and stapled DMG/PKG artifacts
  - Distribute an unsigned application bundle
  recommendation: Use Developer ID signing, hardened runtime, notarization and stapled DMG/PKG artifacts
  recommendation_basis: Gatekeeper-compatible distribution is required for a production macOS release.
  selected_option: Use Developer ID signing, hardened runtime, notarization and stapled DMG/PKG artifacts
  status: accepted
  required_adr: ADR-MACOS-PACKAGING
- id: CAP-14-D04
  title: Linux packaging
  candidates:
  - Provide AppImage plus Debian package baseline, with signed/checksummed metadata
  - Choose one distribution-specific package and call Linux complete
  recommendation: Provide AppImage plus Debian package baseline, with signed/checksummed metadata
  recommendation_basis: The baseline balances portability and managed Ubuntu/Debian lab deployment.
  selected_option: Provide AppImage plus Debian package baseline, with signed/checksummed metadata
  status: accepted
  required_adr: ADR-LINUX-PACKAGING
- id: CAP-14-D05
  title: Credential storage
  candidates:
  - Use Credential Manager, Keychain and Secret Service through one secrets port
  - Store credentials in project configuration files
  recommendation: Use Credential Manager, Keychain and Secret Service through one secrets port
  recommendation_basis: Each OS provides protected credential facilities with different APIs.
  selected_option: Use Credential Manager, Keychain and Secret Service through one secrets port
  status: accepted
  required_adr: null
- id: CAP-14-D06
  title: Filesystem layout
  candidates:
  - Use platform-native data/config/cache directories and architecture-neutral project-relative paths
  - Reuse Windows paths and separators on every OS
  recommendation: Use platform-native data/config/cache directories and architecture-neutral project-relative paths
  recommendation_basis: Correct platform directories avoid permissions, cleanup and portability defects.
  selected_option: Use platform-native data/config/cache directories and architecture-neutral project-relative paths
  status: accepted
  required_adr: null
- id: CAP-14-D07
  title: Sidecar packaging
  candidates:
  - Build and sign target-triple-specific Rust/Python/native sidecars from pinned manifests
  - Download executable dependencies at first launch
  recommendation: Build and sign target-triple-specific Rust/Python/native sidecars from pinned manifests
  recommendation_basis: Offline operation and supply-chain control require known local artifacts.
  selected_option: Build and sign target-triple-specific Rust/Python/native sidecars from pinned manifests
  status: accepted
  required_adr: null
- id: CAP-14-D08
  title: Python runtime
  candidates:
  - Bundle a reproducible target-specific Python runtime and wheel set
  - Depend on the user’s system Python
  recommendation: Bundle a reproducible target-specific Python runtime and wheel set
  recommendation_basis: Scientific dependencies and ABI compatibility cannot be delegated to arbitrary environments.
  selected_option: Bundle a reproducible target-specific Python runtime and wheel set
  status: accepted
  required_adr: null
- id: CAP-14-D09
  title: AI portability
  candidates:
  - Use CPU as the semantic baseline; expose ONNX Runtime/llama.cpp backends and optional acceleration ports
  - Implement platform-specific model behavior with no common fallback
  recommendation: Use CPU as the semantic baseline; expose ONNX Runtime/llama.cpp backends and optional acceleration ports
  recommendation_basis: Acceleration must improve performance without changing accepted outputs or project semantics.
  selected_option: Use CPU as the semantic baseline; expose ONNX Runtime/llama.cpp backends and optional acceleration ports
  status: accepted
  required_adr: null
- id: CAP-14-D10
  title: DGX Spark support
  candidates:
  - Treat DGX Spark as Linux ARM64 with native builds, CUDA qualification, unified-memory limits and CPU fallback
  - Create a separate DGX Spark product fork or use x86 emulation
  recommendation: Treat DGX Spark as Linux ARM64 with native builds, CUDA qualification, unified-memory limits and CPU fallback
  recommendation_basis: NVIDIA documents the device as an ARM64 Ubuntu-based Grace Blackwell system.
  selected_option: Treat DGX Spark as Linux ARM64 with native builds, CUDA qualification, unified-memory limits and CPU fallback
  status: accepted
  required_adr: ADR-DGX-SPARK-RUNTIME
- id: CAP-14-D11
  title: Parser/vector portability
  candidates:
  - Pin target-specific artifacts, qualify equivalent behavior and declare a supported fallback
  - Silently omit features when a native dependency is unavailable
  recommendation: Pin target-specific artifacts, qualify equivalent behavior and declare a supported fallback
  recommendation_basis: Users must know when performance changes without losing functional semantics.
  selected_option: Pin target-specific artifacts, qualify equivalent behavior and declare a supported fallback
  status: accepted
  required_adr: null
- id: CAP-14-D12
  title: Project interchange
  candidates:
  - Keep canonical project structures architecture-neutral; treat indexes and model caches as rebuildable derivatives
  - Serialize native paths, accelerator state and index binaries as canonical
  recommendation: Keep canonical project structures architecture-neutral; treat indexes and model caches as rebuildable derivatives
  recommendation_basis: Projects must move among OS targets without lossy conversion.
  selected_option: Keep canonical project structures architecture-neutral; treat indexes and model caches as rebuildable derivatives
  status: accepted
  required_adr: null
- id: CAP-14-D13
  title: Portable package
  candidates:
  - Use checksummed BagIt payloads plus RO-Crate metadata and PROV links for transfers
  - Zip the project directory without a manifest
  recommendation: Use checksummed BagIt payloads plus RO-Crate metadata and PROV links for transfers
  recommendation_basis: Portable packaging should detect corruption and preserve research context.
  selected_option: Use checksummed BagIt payloads plus RO-Crate metadata and PROV links for transfers
  status: accepted
  required_adr: null
- id: CAP-14-D14
  title: Path safety
  candidates:
  - Detect case collisions, invalid names, symlinks, permissions and length limits before transfer
  - Let the destination filesystem resolve conflicts
  recommendation: Detect case collisions, invalid names, symlinks, permissions and length limits before transfer
  recommendation_basis: Cross-platform filename rules can otherwise overwrite or hide project objects.
  selected_option: Detect case collisions, invalid names, symlinks, permissions and length limits before transfer
  status: accepted
  required_adr: null
- id: CAP-14-D15
  title: Accessibility parity
  candidates:
  - Repeat keyboard, screen-reader, scaling and contrast qualification on each OS
  - Assume Windows accessibility results transfer unchanged
  recommendation: Repeat keyboard, screen-reader, scaling and contrast qualification on each OS
  recommendation_basis: Assistive technology and webview/platform behavior differ by OS.
  selected_option: Repeat keyboard, screen-reader, scaling and contrast qualification on each OS
  status: accepted
  required_adr: null
- id: CAP-14-D16
  title: Update channels
  candidates:
  - Sign and qualify target-specific update artifacts while sharing one release manifest model
  - Use one binary updater payload on all platforms
  recommendation: Sign and qualify target-specific update artifacts while sharing one release manifest model
  recommendation_basis: Packaging and trust chains differ even when release semantics are common.
  selected_option: Sign and qualify target-specific update artifacts while sharing one release manifest model
  status: accepted
  required_adr: null
- id: CAP-14-D17
  title: Semantic equivalence
  candidates:
  - Compare canonical records, evidence, graphs, workflows and exported hashes across OS fixtures
  - Treat successful application launch as cross-platform completion
  recommendation: Compare canonical records, evidence, graphs, workflows and exported hashes across OS fixtures
  recommendation_basis: The core promise is scholarly equivalence, not merely executable portability.
  selected_option: Compare canonical records, evidence, graphs, workflows and exported hashes across OS fixtures
  status: accepted
  required_adr: null
- id: CAP-14-D18
  title: G6 authority
  candidates:
  - Approve each platform independently and publish exact supported versions/limitations
  - Use Windows G5 approval as automatic approval for other platforms
  recommendation: Approve each platform independently and publish exact supported versions/limitations
  recommendation_basis: Cross-platform release claims require platform-specific production evidence.
  selected_option: Approve each platform independently and publish exact supported versions/limitations
  status: accepted
  required_adr: null
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-14 — Capability decision and execution plan

> **Capability approval gate — proposed, recommendations resolved.** The planning agent has researched the credible alternatives and preselected the documented best-in-class recommendation for every material decision. Those choices are complete decisions. Reviewers may confirm the defaults or override a choice with explicit rationale; one approval then authorizes this packet and all contained slice plans at an immutable commit. No separate decision-selection stop is required.

<div class="visual-flow"><span>Review all slices</span><b>→</b><span>Confirm or override resolved defaults</span><b>→</b><span>Approve once</span><b>→</b><span>Run long capability campaign</span><b>→</b><span>Production readiness review</span></div>

## 0. Control and authority

| Field | Value |
|---|---|
| Capability | `CAP-14` — Cross-platform desktop qualification and release |
| Baseline / supplemental release | 1.3 / 1.3.4 |
| Status | PROPOSED — recommendations resolved; capability approval pending |
| Execution mode | Long-running capability campaign |
| Slice count | 6 |
| Decision count | 18 |
| Review page | planning/review-site/CAP-14/index.html |

Authority order is Vision → accepted ADRs → Systems Design → authoritative backlog → approved capability packet → approved slice plans → approved UI reference for user-facing changes → automation rules and code/tests. The backlog remains authoritative for IDs, dependencies and status. This packet owns the architectural and product selections needed to execute the capability without repeated approval stops.

## 1. Capability outcome and production-ready exit

**Objective.** Extend the production Windows local edition to Apple Silicon macOS and Ubuntu-compatible Linux x86_64/ARM64 while preserving one codebase, one project format, and equivalent security and scholarly behavior.

One shared Tauri/core codebase uses narrow platform adapters for packaging, credentials, paths, process control and acceleration. Canonical projects are architecture-neutral; target-specific binaries, indexes and caches are replaceable derivatives.

The capability is not complete merely because its atomic tasks are checked off. Production readiness requires the following capability exits:

- Supported macOS and Linux packages install, upgrade, recover, back up, and run offline without Docker or a server.
- The same project opens across Windows, macOS, and Linux with identical evidence, provenance, workflows, and outputs.
- Platform secrets, signing/update trust, paths, sidecars, parsers, vector adapters, and model backends pass platform-specific security and reliability tests.
- Linux ARM64, including an NVIDIA DGX Spark-class lab profile where available, completes representative GPU/model and end-to-end qualification.

The independent capability reviewer must trace each exit to immutable task, slice and end-to-end evidence; verify failure, denial, cancellation, restart, migration, security, accessibility and relevant platform behavior; and confirm that no concealed TODO or deferred production blocker remains.

## 2. Slice map and end-to-end dependency logic

| Slice | Title | Outcome | Wave | Priority | Depends on |
|---|---|---|---|---|---|
| `CAP-14.S01` | Platform abstraction and build matrix | One codebase builds and reports its capabilities consistently across qualified desktop operating systems. | W6 | P0 | CAP-11.S06.T03 |
| `CAP-14.S02` | Apple Silicon macOS product qualification | The local product is production-ready on supported Apple Silicon macOS versions. | W6 | P0 | CAP-14.S01.T03 |
| `CAP-14.S03` | Linux x86_64 and ARM64 product qualification | The local product is production-ready on approved Ubuntu-compatible Linux workstation profiles. | W6 | P0 | CAP-14.S01.T03 |
| `CAP-14.S04` | Cross-platform scientific and AI runtime | Hardware acceleration is optional, governed, observable, and portable across supported desktop platforms. | W6 | P0 | CAP-14.S01.T03, CAP-07.S02.T03 |
| `CAP-14.S05` | Cross-platform project compatibility and recovery | Projects and analytical results remain portable and semantically identical across qualified desktop operating systems. | W6 | P0 | CAP-14.S02.T03, CAP-14.S03.T03 |
| `CAP-14.S06` | Cross-platform desktop release gate | The complete local edition is release-qualified on Windows, macOS, and Linux. | W6 | P0 | CAP-14.S05.T03 |

Slices execute in backlog dependency order. A later slice may introduce an adapter or test fixture for an earlier contract, but it may not redefine an approved cross-slice decision. Each slice concludes with integration and independent review, after which the same campaign proceeds directly to the next ready slice. The capability pauses only for demonstrated infeasibility, a missing external prerequisite, unavailable required hardware, a genuinely new consequential human decision, a higher-authority conflict, or an approved design-reference gate.

## 3. Decision-making protocol

Before approval, the planning agent must verify every candidate against the Vision, architecture, other capability contracts, current official standards, primary research where appropriate, existing code and representative environments. Reviewers may accept the recommendation, select another listed option, or request a revised candidate set. Each accepted selection must include rationale and any ADR/reference requirement. Once approved, routine implementation, debugging, testing and slice transitions do not reopen the decision.

A decision may be reopened only when implementation evidence demonstrates infeasibility or material new evidence changes the risk/architecture boundary. The agent must document the failed assumption, strongest feasible alternatives, migration effect and recommendation on the static review page, obtain focused approval, and resume the same campaign.

## 4. Decision register

| ID | Decision | Candidates | Recommendation | Basis | ADR |
|---|---|---|---|---|---|
| `CAP-14-D01` | Codebase strategy | A. Use one shared desktop/core codebase with narrow platform adapter ports and no feature forks<br>B. Maintain independent Windows, macOS and Linux implementations | **Use one shared desktop/core codebase with narrow platform adapter ports and no feature forks** | Shared semantics and tests are essential for project portability and maintainability. | ADR-DESKTOP-PLATFORM-PORTS |
| `CAP-14-D02` | Qualification matrix | A. Qualify Windows x64, Apple Silicon macOS, Linux x86_64 and Linux ARM64 as explicit targets<br>B. Claim generic cross-platform support from framework compatibility | **Qualify Windows x64, Apple Silicon macOS, Linux x86_64 and Linux ARM64 as explicit targets** | Native dependencies, sidecars, credential stores and installers require target-specific evidence. | None |
| `CAP-14-D03` | macOS distribution | A. Use Developer ID signing, hardened runtime, notarization and stapled DMG/PKG artifacts<br>B. Distribute an unsigned application bundle | **Use Developer ID signing, hardened runtime, notarization and stapled DMG/PKG artifacts** | Gatekeeper-compatible distribution is required for a production macOS release. | ADR-MACOS-PACKAGING |
| `CAP-14-D04` | Linux packaging | A. Provide AppImage plus Debian package baseline, with signed/checksummed metadata<br>B. Choose one distribution-specific package and call Linux complete | **Provide AppImage plus Debian package baseline, with signed/checksummed metadata** | The baseline balances portability and managed Ubuntu/Debian lab deployment. | ADR-LINUX-PACKAGING |
| `CAP-14-D05` | Credential storage | A. Use Credential Manager, Keychain and Secret Service through one secrets port<br>B. Store credentials in project configuration files | **Use Credential Manager, Keychain and Secret Service through one secrets port** | Each OS provides protected credential facilities with different APIs. | None |
| `CAP-14-D06` | Filesystem layout | A. Use platform-native data/config/cache directories and architecture-neutral project-relative paths<br>B. Reuse Windows paths and separators on every OS | **Use platform-native data/config/cache directories and architecture-neutral project-relative paths** | Correct platform directories avoid permissions, cleanup and portability defects. | None |
| `CAP-14-D07` | Sidecar packaging | A. Build and sign target-triple-specific Rust/Python/native sidecars from pinned manifests<br>B. Download executable dependencies at first launch | **Build and sign target-triple-specific Rust/Python/native sidecars from pinned manifests** | Offline operation and supply-chain control require known local artifacts. | None |
| `CAP-14-D08` | Python runtime | A. Bundle a reproducible target-specific Python runtime and wheel set<br>B. Depend on the user’s system Python | **Bundle a reproducible target-specific Python runtime and wheel set** | Scientific dependencies and ABI compatibility cannot be delegated to arbitrary environments. | None |
| `CAP-14-D09` | AI portability | A. Use CPU as the semantic baseline; expose ONNX Runtime/llama.cpp backends and optional acceleration ports<br>B. Implement platform-specific model behavior with no common fallback | **Use CPU as the semantic baseline; expose ONNX Runtime/llama.cpp backends and optional acceleration ports** | Acceleration must improve performance without changing accepted outputs or project semantics. | None |
| `CAP-14-D10` | DGX Spark support | A. Treat DGX Spark as Linux ARM64 with native builds, CUDA qualification, unified-memory limits and CPU fallback<br>B. Create a separate DGX Spark product fork or use x86 emulation | **Treat DGX Spark as Linux ARM64 with native builds, CUDA qualification, unified-memory limits and CPU fallback** | NVIDIA documents the device as an ARM64 Ubuntu-based Grace Blackwell system. | ADR-DGX-SPARK-RUNTIME |
| `CAP-14-D11` | Parser/vector portability | A. Pin target-specific artifacts, qualify equivalent behavior and declare a supported fallback<br>B. Silently omit features when a native dependency is unavailable | **Pin target-specific artifacts, qualify equivalent behavior and declare a supported fallback** | Users must know when performance changes without losing functional semantics. | None |
| `CAP-14-D12` | Project interchange | A. Keep canonical project structures architecture-neutral; treat indexes and model caches as rebuildable derivatives<br>B. Serialize native paths, accelerator state and index binaries as canonical | **Keep canonical project structures architecture-neutral; treat indexes and model caches as rebuildable derivatives** | Projects must move among OS targets without lossy conversion. | None |
| `CAP-14-D13` | Portable package | A. Use checksummed BagIt payloads plus RO-Crate metadata and PROV links for transfers<br>B. Zip the project directory without a manifest | **Use checksummed BagIt payloads plus RO-Crate metadata and PROV links for transfers** | Portable packaging should detect corruption and preserve research context. | None |
| `CAP-14-D14` | Path safety | A. Detect case collisions, invalid names, symlinks, permissions and length limits before transfer<br>B. Let the destination filesystem resolve conflicts | **Detect case collisions, invalid names, symlinks, permissions and length limits before transfer** | Cross-platform filename rules can otherwise overwrite or hide project objects. | None |
| `CAP-14-D15` | Accessibility parity | A. Repeat keyboard, screen-reader, scaling and contrast qualification on each OS<br>B. Assume Windows accessibility results transfer unchanged | **Repeat keyboard, screen-reader, scaling and contrast qualification on each OS** | Assistive technology and webview/platform behavior differ by OS. | None |
| `CAP-14-D16` | Update channels | A. Sign and qualify target-specific update artifacts while sharing one release manifest model<br>B. Use one binary updater payload on all platforms | **Sign and qualify target-specific update artifacts while sharing one release manifest model** | Packaging and trust chains differ even when release semantics are common. | None |
| `CAP-14-D17` | Semantic equivalence | A. Compare canonical records, evidence, graphs, workflows and exported hashes across OS fixtures<br>B. Treat successful application launch as cross-platform completion | **Compare canonical records, evidence, graphs, workflows and exported hashes across OS fixtures** | The core promise is scholarly equivalence, not merely executable portability. | None |
| `CAP-14-D18` | G6 authority | A. Approve each platform independently and publish exact supported versions/limitations<br>B. Use Windows G5 approval as automatic approval for other platforms | **Approve each platform independently and publish exact supported versions/limitations** | Cross-platform release claims require platform-specific production evidence. | None |

Every decision is resolved by the documented best-in-class recommendation: `selected_option` equals `recommendation`, status is `accepted`, and `decision_completion` is `complete`. Reviewers may override a selection before capability approval, but every non-recommended selection requires explicit rationale. Approval remains the one authorization gate for the capability and all slice plans.

## 5. Cross-slice architecture contract

One shared Tauri/core codebase uses narrow platform adapters for packaging, credentials, paths, process control and acceleration. Canonical projects are architecture-neutral; target-specific binaries, indexes and caches are replaceable derivatives.

Cross-slice invariants:

- Canonical scholarly records, evidence, accepted human decisions, rights state and provenance remain authoritative. Indexes, projections, caches, generated recommendations and operational dashboards are replaceable derivatives.
- Local, institutional and cloud profiles use the same domain identifiers, status semantics, evidence/provenance contracts and workflow meanings; infrastructure adapters may differ.
- Every long operation has stable identity, inputs/manifests, progress, cancellation, retry/checkpoint/restart and evidence records.
- Unknown, unavailable, denied, not reported, inferred, disputed, stale and failed remain distinct states.
- Provider, platform, database, cluster and UI framework objects do not escape their adapters into portable domain contracts.
- CAP-16–CAP-19 consume stable study/evidence/manuscript interfaces rather than internal storage tables or deployment SDK types.

## 6. Experience and workflow contract

Academic Minimal layout and objective-specific workflows remain consistent while native menus, permissions, packaging, shortcuts, screen readers and diagnostics follow each operating system.

Approved reference exposure: `help-onboarding.html`, `model-center.html`, `new-project.html`, `project-settings.html`, `prototype-index.html`, `style-guide.html`

Researcher-facing behavior must preserve the selected project objective, numbered primary stages, previous/next actions, expected output, supporting-tool relationship, inspect–contest–adjudicate interaction and visible provenance. Intentional UI change follows reference first: update the style guide, workflow/page contracts and HTML mockups; run validators; obtain explicit approval and a new reference ID; then implement. A defect restoration to the approved reference does not need a new design decision.

## 7. Security, privacy, rights and research-integrity decisions

Each target receives native signing/notarization or package verification, protected credential storage, pinned sidecars/runtimes and platform-specific security/recovery qualification.

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

After one-time approval, `taskctl capability start CAP-14` selects the first dependency-ready slice and continues through the capability. The agent does not ask again about settled options. Each task produces machine-linked evidence; each slice receives independent integration review; the campaign immediately advances when the next slice is ready. If a classified blocker occurs, the agent preserves work, records the exact affected decision/assumption and provides the static review URL rather than creating an unstructured chat approval.

## 10. Plan and approval checklist

- [ ] Every slice has exactly one structurally valid plan using the governed template.
- [ ] All listed decisions have a selected option, rationale and accepted status.
- [ ] Required ADRs and design-reference changes are accepted.
- [ ] Dependencies, credentials, source/model licenses, hardware and fixtures are available or have approved deterministic substitutes.
- [ ] Capability and slice plans are approved by the same reviewer at the same immutable commit.
- [ ] `python tools/planctl.py ready CAP-14 --require-approved` passes.
- [ ] Static review site matches plan hashes and provides the approved decision record.

## 11. Research and technical basis

| Key | Source | Publisher | Planning use |
|---|---|---|---|
| `TAURI_DISTRIBUTION` | [Tauri 2 Distribution](https://v2.tauri.app/distribute/) | Tauri | Desktop packaging, signing and installer targets. |
| `SLSA` | [SLSA Specification 1.2](https://slsa.dev/spec/v1.2/) | OpenSSF / Linux Foundation | Build provenance and supply-chain assurance. |
| `SPDX` | [SPDX Specification 3.0](https://spdx.github.io/spdx-spec/v3.0/) | Linux Foundation | Software bill of materials representation. |
| `APPLE_NOTARY` | [Notarizing macOS software before distribution](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution) | Apple | Developer ID signing, hardened runtime and notarization. |
| `APPLE_KEYCHAIN` | [Keychain Services](https://developer.apple.com/documentation/security/keychain_services) | Apple | macOS protected credential storage. |
| `WCAG22` | [Web Content Accessibility Guidelines 2.2](https://www.w3.org/TR/WCAG22/) | W3C | Accessibility conformance and testable success criteria. |
| `APPIMAGE` | [AppImage Documentation](https://docs.appimage.org/) | AppImage | Portable Linux desktop packaging. |
| `SECRET_SERVICE` | [Secret Service API Specification](https://specifications.freedesktop.org/secret-service-spec/latest/) | freedesktop.org | Linux protected secret storage. |
| `XDG` | [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/latest/) | freedesktop.org | Linux configuration, data and cache locations. |
| `ONNX_RUNTIME` | [ONNX Runtime Execution Providers](https://onnxruntime.ai/docs/execution-providers/) | Microsoft | Portable CPU, CUDA and platform acceleration. |
| `LLAMA_CPP` | [llama.cpp](https://github.com/ggml-org/llama.cpp) | ggml-org | Cross-platform local inference and hardware backends. |
| `DGX_SPARK` | [DGX Spark System Overview](https://docs.nvidia.com/dgx/dgx-spark/system-overview.html) | NVIDIA | ARM64 Grace Blackwell target and DGX OS environment. |
| `DGX_PORTING` | [DGX Spark Porting Guide](https://docs.nvidia.com/dgx/dgx-spark-porting-guide/overview.html) | NVIDIA | ARM64 and unified-memory porting constraints. |
| `BAGIT` | [RFC 8493: The BagIt File Packaging Format](https://www.rfc-editor.org/rfc/rfc8493.html) | IETF | Checksum-validated research package transfer. |
| `RO_CRATE` | [RO-Crate 1.3 Specification](https://www.researchobject.org/ro-crate/specification.html) | RO-Crate Community | Research-object metadata and portability. |
| `PROV_O` | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) | W3C | Interoperable research provenance. |

Official documentation and standards define platform behavior; primary scholarly sources and reporting standards define research-method requirements. Versions, licenses, provider contracts and current target support must be rechecked at capability approval and pinned in accepted ADRs/manifests. A cited source supports a recommendation but does not replace project-specific benchmarks, threat analysis, institutional policy or expert methods review.

## 12. Approval record

| Field | Value |
|---|---|
| Decision completion | Complete — resolved by best-in-class recommendations |
| Packet approval | Pending |
| Approved by | — |
| Approved at | — |
| Approved commit | — |
| Decision feedback | Export from `planning/review-site/CAP-14/index.html` and apply with `planctl`; feedback alone does not approve execution. |
