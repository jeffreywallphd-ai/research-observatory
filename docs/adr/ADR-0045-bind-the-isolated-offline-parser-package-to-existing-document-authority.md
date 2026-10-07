---
id: ADR-0045
title: Bind the isolated offline parser package to existing document authority
status: Proposed
date: 2026-10-07
deciders: []
linked_tasks:
  - CAP-05.S02.T03
decision_scope: Documentary mapping of the separate pinned CPU parser package, native import compatibility derivatives and protected transport to accepted ADR-0028/0029; no new scope, capability, framework or release authority.
affected_paths:
  - workers/**
  - tools/document_parser_runtime_build.py
  - tools/parser_socket_build.py
  - tools/parser_pe_variant.py
  - tools/parser_python_variant.py
  - tools/parser_native_build.py
  - services/core-api/src/research_observatory_core/document_parser_runtime.py
  - services/core-api/src/research_observatory_core/document_attachment_repository.py
  - services/core-api/src/research_observatory_core/object_store.py
  - services/core-api/src/research_observatory_core/parsing/**
  - services/core-api/src/research_observatory_core/ports/*parsing.py
  - services/core-api/src/research_observatory_core/ports/pdf_*.py
  - packages/contracts/documents/**
  - docs/architecture/document-parsing.md
supersedes: []
superseded_by: null
---

# ADR-0045: Bind the isolated offline parser package to existing document authority

## Context

CAP-05.S02.T03 implements the approved isolated offline Docling outcome. The
qualified connector package supplies the Windows principal boundary, not a
qualified PDF runtime. Native source adapters and version-1 staged IR remain
the predecessor contracts. The larger read-only model package needs its own
finite admission envelope and actual qualification under the same LPAC token.

The selected CPU dependencies have native and Python import-time assumptions
that fail under zero-capability LPAC. Engineering diagnostics retained those
failures: eager Winsock startup, embedded DLL-manifest activation denial,
undrained stderr backpressure, and eager `_overlapped` socket discovery. These
are product packaging/startup defects, not grounds to give a parser network,
profile-write or ordinary-user authority. Diagnostic builds are explicitly
nonqualifying; a successful build or text import does not prove PDF conversion.

This Proposed record traces implementation details within the unchanged
accepted decisions. It neither amends the frozen Wave packet nor grants
authority while the runtime, integration and performance proofs remain open.

## Candidates

1. Increase the connector profile and ship the parser in Core. This conflates
   distinct admission boundaries and does not provide the approved dedicated
   worker; do not select it.
2. Package the pinned parser separately with explicit signed inventory,
   selected assets and bounded parser-only native compatibility derivatives.
   This preserves the approved boundary and requires real native proof.
3. Permit plaintext scratch, ordinary-user execution or a different parser.
   These change accepted security or product authority and require an explicit
   successor decision; they are not automatic recovery paths.

## Decision

Use the second implementation route. Parent code chooses the closed
`ro-parser-cpu-1` profile; a worker-supplied profile or public key cannot select
authority. The parser inventory binds every image, library, model, configuration,
dependency lock, derivative receipt and notice. Its bounded 2 GiB/8,192-file/
2 MiB inventory envelope covers the measured selected CPU tree. The connector's
256 MiB/256-file/64 KiB inventory envelope and binary-frame limit remain intact.

The parent records the full authenticated inventory digest as the existing
descriptor's `parser-runtime` asset. This binds native admission and transport
derivatives in addition to model/configuration hashes; worker echoes cannot
supply that identity. Native and degraded descriptors carry it too.

The worker receives only bounded source/control chunks over private inherited
pipes. Parent and worker independently check source length and digest. Parser
output is limited to 64 MiB and transported in at most 1 MiB chunks, with strict
nonce/sequence/length/digest validation. A worker echo confers no producer,
source, workflow-attempt or encrypted-staging authority. Current protected
source rights/session and durable attempt fencing remain Core responsibilities.
Cancellation, failure and denied delivery cannot publish canonical structure.

Native import compatibility is limited to this parser package. Exact CPython
3.14.6 source/patch hashes admit two isolated extension builds: `_socket`
retains its real types/C API while omitting eager Winsock startup; `_overlapped`
retains `_socket` import and native operations while discovering all four
network extension pointers only when an operation requests them. Discovery
must succeed before allocation, pending-operation state or a pointer call.
The qualified ordinary GIL/single-interpreter build is required; this is not
an admission of free-threaded or concurrent-subinterpreter pointer mutation.
The original source tree, Core and connector runtime are not rebuilt by these
extensions. Native LPAC denial, not missing Winsock initialization, establishes
network isolation.

`workers/document/parser-manifests.json` is the closed relative-path/name/
language/digest inventory for resource-only DLL variants. Admit only an empty
assembly, a strict inert asInvoker tree, or the exact previously qualified
CPython manifest on its named standard-library files. Reject unknown assembly
dependencies, elevation, activation content, aliases or language variants.
Preserve original manifest bytes and source/final digests in signed receipts.
Verify non-resource sections and loader directories, all remaining resources,
disjoint raw/mapped section ranges and complete resource-byte accounting.
One exact measured `uv.dll` linker-padding hash is explicitly accounted for;
unknown nonzero anonymous resource bytes fail. Executable manifests and process
capabilities are not changed. Application-derived DLLs are re-signed and the
complete inventory is verified before execution.

Library stderr is a private sink: drain with constant memory and no retained
content, reject more than 1 MiB through a fixed failure code, and keep cancellation
and owned-job termination live. Product diagnostics never retain a third-party
exception string. Separate hash-guarded synthetic engineering images may capture
bounded stderr in ignored local artifacts; they cannot qualify product behavior.

## Consequences

Existing IR/request/result versions and historical native source fixtures remain
unchanged. Accepted ADR-0029 still governs selected Docling/models, disabled
OCR/enrichment/egress, quality uncertainty, page geometry, fallback eligibility,
resource/cancellation limits and cold/warm targets. No parser replacement,
canonical acceptance, new plaintext cache, database migration or automation
framework work is introduced here.

Geometry may be labeled points only after source scale, boxes and rotation are
established. In particular, PDFium's canvas dimensions do not establish
`UserUnit`; unsupported geometry remains explicitly unavailable, not silently
assumed to be unit one. A render must be admitted before allocating its bounded
pixel surface. Scans and uncertain structure retain separate quality warnings.

Rollback disables the failed adapter and preserves encrypted originals, raw
attempts, staged artifacts and previously accepted heads. Retry creates a new
attempt under current rights/session/fence authority. It cannot lower isolation
or erase an adverse result. Installed packaging, protected raw delivery, full
Docling conversion, page/render geometry and measured resource/performance
qualification remain implementation obligations, not claims supplied by this ADR.

## Verification

Selected focused checks cover profile/path/substitution and chunk framing,
native nested ACL success/failure restoration, stderr backpressure/overflow,
exact source/patch/build identity and manifest/resource rejection. Actual signed
LPAC proofs must cover the complete Torch/Docling path, no-write/direct-network
denial, the four deferred network operations, non-network overlapped behavior,
owned cancellation/death/cleanup, offline assets, hostile PDF/resource cases,
protected encrypted raw delivery and historical IR compatibility.

Qualify the committed product image with complete immutable input closure,
declared corpus labels and hardware, raw cold/warm samples and resource peaks.
Do not reuse synthetic diagnostic timings as benchmarks. Independent expanded
task review and integrated S02 review remain required. Fresh full Wave checks,
independent Wave review and the separate human release gate remain W2 obligations.

## Task links

- `CAP-05.S02.T03`
