# CAP-04.S05.T03 task-start acceptance closure

Claim base: `2283e37e43cb56f8330b060b4c7d4b4f0f19489b`. Taskctl claimed the next dependency-eligible W2 task after `CAP-04.S05.T02` completed and `CAP-05.S01.T01` was blocked at its documented approval boundary.

Authority: approved CAP-04.S05 §9.3, accepted ADR-0028 and ADR-0027, the T01 manifest/authorization contract, and the T02 LPAC/Core broker and publication boundary. This task supplies a public-metadata repository example and third-party conformance path; it does not authorize private repository access, arbitrary network destinations, a weaker sandbox, or a new desktop experience.

| Material outcome or invariant | Planned proof |
|---|---|
| A third-party developer can build and validate a connector using the published manifest, worker request/result shape, sample, and documented commands. Existing three-argument plugins remain compatible. | A signed synthetic sample executes through the real worker/Core path; focused old/new worker API and documentation/contract checks. |
| Each page is broker-observed and Core-authorized; a plugin cannot forge a cursor, skip consent, replay a cursor in another project/package/query, or publish a partial error as success. | Red-first two-page, changed-query/project/package, uncommitted predecessor, cursor mismatch, broker-error, and cancellation tests; one real-principal worker path where relevant. |
| A published assertion preserves source provenance and rights limits without accepting worker-selected project, source identity, rights, or retrieval time. | Exact output contract tests, publication/reopen evidence, rights/provenance assertions, and malformed/forged output denials. |
| A failed, timed-out, or restarted invocation has an explainable result and cannot change previously committed pages or hide a failure. | Repository restart/replay and staged-output/failure tests with stable identities and denial audit. |
| Conformance failures identify the exact rule and JSON location without leaking request, response, credential, or private research content. | Positive sample and negative fixture CLI tests checking stable codes/pointers and redacted output. |

Select affected worker, broker, dispatch, result, repository, contract, and conformance checks first. Run broader service/foundation profiles at slice integration or sooner if a shared-runtime failure cannot be localized. Bind qualification to the exact committed candidate and preserve every adverse result. Independent review must cover the public/cross-process and security boundaries before task completion.
