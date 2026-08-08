# Research and standards source catalog

This catalog supports the slice and capability plans. Sources are primary research papers, standards or official technical documentation. A source supports a design decision; it does not replace project-specific benchmark, license, privacy, rights or human approval.

| Key | Source | Publisher | Planning use |
|---|---|---|---|
| `ANTHROPIC_TOOL_USE` | [Tool Use with Claude](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview) | Anthropic | Provider tool-schema and structured-input/output adapter. |
| `ASREVIEW` | [ASReview Documentation](https://asreview.readthedocs.io/en/latest/) | ASReview LAB | Transparent active-learning-assisted screening patterns. |
| `ASREVIEW_PAPER` | [An Open Source Machine Learning Framework for Efficient and Transparent Systematic Reviews](https://doi.org/10.1038/s42256-020-00287-7) | Nature Machine Intelligence | Evidence for active-learning screening with human decisions. |
| `BAGIT` | [RFC 8493 - The BagIt File Packaging Format](https://www.rfc-editor.org/rfc/rfc8493.html) | RFC Editor | Checksum-validated payload transfer and archival package layout. |
| `CROSSREF` | [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) | Crossref | DOI metadata, updates, licenses and cursor-based retrieval. |
| `CSL` | [Citation Style Language 1.0.2 Specification](https://docs.citationstyles.org/en/v1.0.2/specification.html) | Citation Style Language | Portable citation and bibliography formatting. |
| `CYTOSCAPE_JS` | [Cytoscape.js Documentation](https://js.cytoscape.org/) | Cytoscape.js | Interactive graph visualization, selectors, layouts, serialization and graph interaction. |
| `GAPMAP` | [GAPMAP: Mapping Scientific Knowledge Gaps in Biomedical Literature Using Large Language Models](https://arxiv.org/abs/2510.25055) | arXiv | Explicit and implicit gap inference with human validation. |
| `GEMINI_STRUCTURED` | [Structured Outputs](https://ai.google.dev/gemini-api/docs/structured-output) | Google | Provider-native schema-constrained output adapter. |
| `HERMENEUTIC` | [A Hermeneutic Approach for Conducting Literature Reviews and Literature Searches](https://doi.org/10.17705/1CAIS.03412) | Communications of the Association for Information Systems | Iterative search-reading-interpretation cycles and evolving understanding. |
| `HF_CACHE` | [Hugging Face Hub Cache Management](https://huggingface.co/docs/huggingface_hub/guides/manage-cache) | Hugging Face | Content-addressed model cache, revisions, cleanup and offline behavior. |
| `JSON_SCHEMA` | [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) | JSON Schema | Canonical structured-output and schema-pack validation. |
| `LLAMA_CPP` | [llama.cpp](https://github.com/ggml-org/llama.cpp) | ggml-org | Cross-platform local generative inference, embeddings, reranking, grammar constraints and OpenAI-compatible service. |
| `NOVELTY_CHECKER` | [Literature-Grounded Novelty Assessment of Scientific Ideas](https://aclanthology.org/2025.sdp-1.9/) | ACL Anthology | Broad retrieval, embedding filtering, facet-based reranking and literature-grounded novelty reasoning. |
| `ONNX_RUNTIME` | [ONNX Runtime Execution Providers](https://onnxruntime.ai/docs/execution-providers/) | Microsoft | Portable CPU/CUDA/DirectML/CoreML inference for embedding, reranking and classification models. |
| `OPENAI_STRUCTURED` | [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) | OpenAI | Provider-native schema-constrained output adapter. |
| `OPENALEX` | [OpenAlex API Documentation](https://docs.openalex.org/) | OpenAlex | Scholarly metadata, citations, cursor paging and source monitoring. |
| `OPEN_SCHOLAR` | [Synthesizing Scientific Literature with Retrieval-Augmented Language Models](https://doi.org/10.1038/s41586-025-10072-4) | Nature | Domain retrieval, reranking, iterative feedback, citation-aware synthesis and evaluation. |
| `OTEL_GENAI` | [OpenTelemetry Generative AI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) | OpenTelemetry | Portable redacted telemetry for model requests, responses, usage and agents. |
| `PAPERQA2` | [Language Agents Achieve Superhuman Synthesis of Scientific Knowledge](https://arxiv.org/abs/2409.13740) | arXiv | Agentic literature search, synthesis, LitQA2 evaluation and contradiction discovery. |
| `PRISMA_2020` | [PRISMA 2020 Statement](https://doi.org/10.1136/bmj.n71) | BMJ | Systematic-review flow and reporting outputs. |
| `PRISMA_S` | [PRISMA-S: An Extension to the PRISMA Statement for Reporting Literature Searches](https://doi.org/10.1186/s13643-020-01542-z) | Systematic Reviews | Search-strategy and information-source reporting. |
| `PROBLEMATIZATION` | [Generating Research Questions Through Problematization](https://doi.org/10.5465/amr.2009.0188) | Academy of Management Review | Assumption-challenging research-question methodology. |
| `PROV_O` | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) | W3C | Interoperable provenance entities, activities, agents and derivations. |
| `QDRANT_FILTER` | [Qdrant Filtering](https://qdrant.tech/documentation/concepts/filtering/) | Qdrant | Metadata-filtered vector retrieval. |
| `QDRANT_SNAPSHOT` | [Qdrant Snapshots](https://qdrant.tech/documentation/concepts/snapshots/) | Qdrant | Vector index backup, recovery and portability constraints. |
| `RESEARCH_AGENT` | [ResearchAgent: Iterative Research Idea Generation over Scientific Literature](https://aclanthology.org/2025.naacl-long.342/) | ACL Anthology | Graph-grounded idea generation and multi-agent review. |
| `ROAD_TV` | [ROAD-tv: Research Opportunity Discovery via Topological Data Analysis and Adversarial Multi-LLM Validation](https://doi.org/10.1016/j.procs.2026.01.036) | Procedia Computer Science | Structural gap detection, ontology validation and adversarial multi-model evidence checking. |
| `RO_CRATE` | [RO-Crate 1.3 Specification](https://www.researchobject.org/ro-crate/specification.html) | Research Object Crate Community | JSON-LD research package metadata and research-object interchange. |
| `RRF` | [Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods](https://doi.org/10.1145/1571941.1572114) | ACM SIGIR | Deterministic rank-level lexical/semantic fusion without score calibration assumptions. |
| `RUSTWORKX` | [rustworkx Documentation](https://www.rustworkx.org/dev/) | Qiskit | Cross-platform high-performance in-memory graph projections and algorithms. |
| `SAFETENSORS` | [Safetensors Documentation](https://huggingface.co/docs/safetensors/index) | Hugging Face | Safer tensor serialization and model artifact inspection. |
| `SBERT_RERANK` | [Retrieve & Re-Rank - Sentence Transformers](https://www.sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html) | Sentence Transformers | Bi-encoder candidate retrieval followed by cross-encoder reranking. |
| `SCIFACT` | [Fact or Fiction: Verifying Scientific Claims](https://aclanthology.org/2020.emnlp-main.609/) | ACL Anthology | Scientific claim/evidence verification benchmark and rationale retrieval. |
| `SEMANTIC_SCHOLAR` | [Semantic Scholar Academic Graph API](https://www.semanticscholar.org/product/api) | Allen Institute for AI | Citation graph, recommendations and paper metadata. |
| `SPECTER2` | [SciRepEval: A Multi-Format Benchmark for Scientific Document Representations](https://aclanthology.org/2023.emnlp-main.338/) | ACL Anthology | Scientific document embedding baseline and task-specific adapters. |
| `SPECTER2_MODEL` | [AllenAI SPECTER2 Model Card](https://huggingface.co/allenai/specter2) | Allen Institute for AI | Model files, adapters, licensing, dimensions and integration notes. |
| `SQLITE_FTS5` | [SQLite FTS5 Extension](https://www.sqlite.org/fts5.html) | SQLite | Local fielded lexical indexing, BM25 ranking, snippets, rebuild and integrity checks. |
| `UUIDV7` | [RFC 9562 - Universally Unique IDentifiers](https://www.rfc-editor.org/rfc/rfc9562.html) | RFC Editor | Stable sortable UUIDv7 identifiers. |
| `WCAG22` | [Web Content Accessibility Guidelines 2.2](https://www.w3.org/TR/WCAG22/) | W3C | AA accessibility target. |
| `WEB_ANNOTATION` | [Web Annotation Data Model](https://www.w3.org/TR/annotation-model/) | W3C | Multi-selector source anchors and revision-aware annotations. |

## Supplemental release 1.3.4 sources for CAP-16 through CAP-19

| Key | Source | Publisher | Planning use |
|---|---|---|---|
| `APA_JARS_QUAL` | [Journal Article Reporting Standards for Qualitative, Primary Qualitative Meta-Analytic, and Mixed Methods Research](https://doi.org/10.1037/amp0000151) | American Psychological Association | Qualitative and mixed-method design/reporting completeness. |
| `APA_JARS_QUANT` | [Journal Article Reporting Standards for Quantitative Research](https://doi.org/10.1037/amp0000191) | American Psychological Association | Quantitative design and reporting completeness. |
| `APPIMAGE` | [AppImage Documentation](https://docs.appimage.org/) | AppImage | Portable Linux desktop packaging. |
| `APPLE_KEYCHAIN` | [Keychain Services](https://developer.apple.com/documentation/security/keychain_services) | Apple | macOS protected credential storage. |
| `APPLE_NOTARY` | [Notarizing macOS software before distribution](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution) | Apple | Developer ID signing, hardened runtime and notarization. |
| `ARIA_APG` | [ARIA Authoring Practices Guide](https://www.w3.org/WAI/ARIA/apg/) | W3C | Accessible widget and interaction patterns. |
| `CLOUDEVENTS` | [CloudEvents Specification](https://cloudevents.io/) | CNCF | Portable event envelopes and metering events. |
| `COMMON_RULE` | [Federal Policy for the Protection of Human Subjects](https://www.hhs.gov/ohrp/regulations-and-policy/regulations/common-rule/index.html) | HHS OHRP | Human-subject research review and consent requirements. |
| `DGX_PORTING` | [DGX Spark Porting Guide](https://docs.nvidia.com/dgx/dgx-spark-porting-guide/overview.html) | NVIDIA | ARM64 and unified-memory porting constraints. |
| `DGX_SPARK` | [DGX Spark System Overview](https://docs.nvidia.com/dgx/dgx-spark/system-overview.html) | NVIDIA | ARM64 Grace Blackwell target and DGX OS environment. |
| `EQUATOR` | [EQUATOR Reporting Guidelines Library](https://www.equator-network.org/reporting-guidelines/) | EQUATOR Network | Study-type-specific reporting guidance. |
| `FAIR` | [FAIR Guiding Principles](https://www.go-fair.org/fair-principles/) | GO FAIR | Findable, accessible, interoperable and reusable research assets. |
| `FOCUS` | [FinOps Open Cost and Usage Specification 1.4](https://focus.finops.org/focus-specification/) | FinOps Foundation | Normalized cloud usage and cost records. |
| `INTUNE` | [Add, assign, and monitor a Win32 app in Microsoft Intune](https://learn.microsoft.com/en-us/intune/intune-service/apps/apps-win32-add) | Microsoft | Institutional Windows application deployment. |
| `K8S_MULTI` | [Kubernetes Multi-tenancy](https://kubernetes.io/docs/concepts/security/multi-tenancy/) | Kubernetes | Namespace, network, quota and isolation patterns. |
| `K8S_NETPOL` | [Kubernetes Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/) | Kubernetes | Default-deny tenant network isolation. |
| `K8S_QUOTA` | [Kubernetes Resource Quotas](https://kubernetes.io/docs/concepts/policy/resource-quotas/) | Kubernetes | Tenant fairness and capacity governance. |
| `NIST_AI_SSDF` | [Secure Software Development Practices for Generative AI and Dual-Use Foundation Models SP 800-218A](https://csrc.nist.gov/pubs/sp/800/218/a/final) | NIST | AI-specific secure development practices. |
| `NIST_SSDF` | [Secure Software Development Framework SP 800-218](https://csrc.nist.gov/pubs/sp/800/218/final) | NIST | Secure development and release controls. |
| `NIST_ZERO_TRUST` | [Zero Trust Architecture SP 800-207](https://csrc.nist.gov/pubs/sp/800/207/final) | NIST | Identity- and policy-centric institutional access. |
| `OIDC` | [OpenID Connect Core 1.0 incorporating errata set 2](https://openid.net/specs/openid-connect-core-1_0.html) | OpenID Foundation | Institutional and cloud identity federation. |
| `OSF_REG` | [OSF Registrations and Preregistrations](https://help.osf.io/article/330-welcome-to-registrations) | Center for Open Science | Time-stamped, read-only registrations and embargoes. |
| `OTEL` | [OpenTelemetry Specification](https://opentelemetry.io/docs/specs/otel/) | OpenTelemetry | Portable traces, metrics and logs. |
| `PKCE` | [RFC 7636: Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636) | IETF | Native-app authorization-code protection. |
| `POSTGRES_RLS` | [PostgreSQL Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) | PostgreSQL | Default-deny row-level data isolation. |
| `SCIM` | [RFC 7644: SCIM Protocol](https://www.rfc-editor.org/rfc/rfc7644) | IETF | Provisioning and lifecycle interoperability. |
| `SECRET_SERVICE` | [Secret Service API Specification](https://specifications.freedesktop.org/secret-service-spec/latest/) | freedesktop.org | Linux protected secret storage. |
| `SIGNTOOL` | [How to sign an app package using SignTool](https://learn.microsoft.com/en-us/windows/win32/appxpkg/how-to-sign-a-package-using-signtool) | Microsoft | Windows package signing. |
| `SLSA` | [SLSA Specification 1.2](https://slsa.dev/spec/v1.2/) | OpenSSF / Linux Foundation | Build provenance and supply-chain assurance. |
| `SPDX` | [SPDX Specification 3.0](https://spdx.github.io/spdx-spec/v3.0/) | Linux Foundation | Software bill of materials representation. |
| `SPIFFE` | [SPIFFE Specifications](https://spiffe.io/docs/latest/spiffe-about/overview/) | CNCF | Workload identity and service authentication. |
| `SQLITE_BACKUP` | [SQLite Online Backup API](https://www.sqlite.org/backup.html) | SQLite | Consistent local backups. |
| `SQLITE_INTEGRITY` | [SQLite PRAGMA integrity_check](https://www.sqlite.org/pragma.html#pragma_integrity_check) | SQLite | Project health and corruption detection. |
| `TAURI_DISTRIBUTION` | [Tauri 2 Distribution](https://v2.tauri.app/distribute/) | Tauri | Desktop packaging, signing and installer targets. |
| `TAURI_UPDATER` | [Tauri Updater Plugin](https://v2.tauri.app/plugin/updater/) | Tauri | Signed update manifests, channels and updater behavior. |
| `TEMPORAL` | [Temporal Documentation](https://docs.temporal.io/) | Temporal | Durable hosted workflow execution. |
| `TOP` | [Transparency and Openness Promotion Guidelines](https://www.cos.io/initiatives/top-guidelines) | Center for Open Science | Transparency, preregistration and openness policies. |
| `XDG` | [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/latest/) | freedesktop.org | Linux configuration, data and cache locations. |

## Supplemental release 1.3.4 sources for CAP-16 through CAP-19

| Key | Source | Publisher | Planning use |
|---|---|---|---|
| `CREDIT` | [ANSI/NISO Z39.104-2022 CRediT Contributor Roles Taxonomy](https://www.niso.org/publications/z39104-2022-credit) | NISO | Structured contributor-role capture and transparent authorship metadata. |
| `DATACITE47` | [DataCite Metadata Schema 4.7](https://schema.datacite.org/meta/kernel-4/) | DataCite | Persistent-identifier-ready metadata for research artifacts and related resources. |
| `FRICTIONLESS_TABLE` | [Frictionless Table Schema](https://specs.frictionlessdata.io/table-schema/) | Frictionless Data | Portable JSON-declared schemas for CSV/tabular result exchange, validation and missing values. |
| `ICMJE_AI` | [ICMJE Use of Artificial Intelligence in Publishing](https://www.icmje.org/recommendations/browse/artificial-intelligence/) | ICMJE | Human accountability, confidentiality and transparent disclosure for AI-assisted publication work. |
| `ICMJE_AI_AUTHORS` | [ICMJE Use of AI by Authors](https://www.icmje.org/recommendations/browse/artificial-intelligence/ai-use-by-authors.html) | ICMJE | Human authorship responsibility, disclosure and source/plagiarism controls. |
| `ICMJE_AI_REVIEWERS` | [ICMJE Use of AI by Reviewers](https://www.icmje.org/recommendations/browse/artificial-intelligence/ai-use-by-reviewers.html) | ICMJE | Confidentiality, permission, validation and disclosure for AI-assisted review. |
| `JATS14` | [JATS Article Authoring Tag Set 1.4](https://jats.nlm.nih.gov/articleauthoring/1.4/) | NLM / NISO | Current article-authoring XML interoperability, validation schemas and versioned scholarly structure. |
| `JATS14_PUB` | [JATS Journal Publishing Tag Set 1.4](https://jats.nlm.nih.gov/publishing/1.4/) | NLM / NISO | Publishing-oriented article interchange and validation. |
| `MECA201` | [NISO RP-30-2023, Manuscript Exchange Common Approach (MECA) Version 2.0.1](https://www.niso.org/publications/rp-30-2023-meca) | NISO | Portable package interchange for manuscripts, submission metadata, related files and optional peer-review data. |
| `NISO_PEER_REVIEW` | [ANSI/NISO Z39.106-2023 Standard Terminology for Peer Review](https://www.niso.org/publications/z39106-2023-peerreview) | NISO | Consistent reviewer roles, identity transparency and peer-review process terminology. |
| `OPENREVIEW_META` | [OpenReview Meta Review Stage](https://docs.openreview.net/reference/stages/meta-review-stage) | OpenReview | Editorial synthesis as a distinct stage from independent reviews. |
| `OPENREVIEW_REBUTTAL` | [OpenReview Rebuttal Stage](https://docs.openreview.net/reference/stages/rebuttal-stage) | OpenReview | Explicit response/rebuttal stage linked to prior reviews. |
| `OPENREVIEW_REVIEW` | [OpenReview Review Stage](https://docs.openreview.net/reference/stages/review-stage) | OpenReview | Structured independent review rounds and configurable review forms. |
| `PANDOC_JATS` | [Pandoc JATS Support](https://pandoc.org/jats.html) | Pandoc | Replaceable conversion to and from JATS through a tested export adapter. |
| `PROSEMIRROR` | [ProseMirror Guide](https://prosemirror.net/docs/guide/) | ProseMirror | Schema-driven editor state, transactions, plugins and stable structured-document behavior. |
| `QUARTO_CITATIONS` | [Quarto Citations](https://quarto.org/docs/authoring/footnotes-and-citations) | Quarto | Pandoc/CSL citation processing and bibliography inputs. |
| `QUARTO_EXTENSIONS` | [Quarto Custom Formats](https://quarto.org/docs/extensions/formats.html) | Quarto | Versioned venue/output overlays without hard-coding publisher layouts into the domain model. |
| `QUARTO_FORMATS` | [Quarto Formats](https://quarto.org/docs/reference/formats/) | Quarto | Portable HTML, PDF, Word, Markdown, JATS and other publication exports. |
| `QUARTO_MANUSCRIPTS` | [Quarto Manuscripts](https://quarto.org/docs/manuscripts/) | Quarto | Multi-format scholarly manuscript projects with executable research artifacts. |
| `QUARTO_XREF` | [Quarto Cross References](https://quarto.org/docs/authoring/cross-references) | Quarto | Stable figure, table, equation, section and listing references in generated artifacts. |
| `YJS_OFFLINE` | [Yjs Offline Editing](https://docs.yjs.dev/getting-started/allowing-offline-editing) | Yjs | Optional collaboration adapter and offline synchronization, not canonical local manuscript state. |

## Selection rule

For technical implementation, prefer official documentation and open standards. For scientific mechanisms, prefer the original peer-reviewed paper or clearly labeled preprint. Recheck licenses, versions, provider contracts and current platform support before capability approval. Record the exact version/date in the accepted ADR or benchmark manifest.
