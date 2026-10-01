# CAP-04.S05.T02 task-start acceptance closure

Claim base: `6e9df6409c0cdcae12464dc47d2a809f6c39d2e3`; claim state committed at `e19f6f28f7fbc2c3fd6421935591a590884240bb`.

Authority: approved CAP-04.S05 §9.2, ADR-0028 and ADR-0027, the T01 signed manifest and authorization contract, and approved UI reference `RO-UI-ACADEMIC-MINIMAL-1.7`. This task owns the restricted Windows worker, brokered access, durable exact project permission, local publisher trust, quotas, timeouts, redacted audit, and failure/recovery proof. It does not authorize arbitrary plugin URLs, plaintext scratch, or a same-user child fallback.

| Material outcome or invariant | Planned proof |
|---|---|
| Exact signed package, active trusted publisher and explicit project grant authorize one supported invocation; package/hash/version/publisher/permission or project substitution denies. | Grant/trust state tests plus one committed, real-worker happy path. |
| Untrusted connector cannot read another project, vault, environment secrets, or write ordinary/AppContainer temporary locations; direct loopback and public egress deny. | Packaged adversarial worker under queried Windows AppContainer identity, explicit LPAC launch attributes, zero capabilities, and synthetic sentinels. |
| Worker sees no project path, database/key handle, reusable secret, arbitrary URL, or unrestricted RPC. Control frames bind protocol, nonce, sequence, operation and job; oversized/duplicate/wrong-job frames deny. | Private inherited-handle and framed-IPC tests, including malformed input and output. |
| Network and credential use stay in Core; signed route, concrete scientific parameters, current grant, project intent/privacy/rights, resolved address and redirect are rechecked. | Broker tests for permitted metadata, private/mixed/rebound DNS, route and policy changes, secret redaction, response bounds and denial audit. |
| A timeout, cancellation, crash, quota, child attempt or parent death cannot commit partial success or retain authority after restart. | Real Job Object/worker failure probes and durable audit/staging recovery tests. |
| Source Manager separates local publisher trust and exact project permission, with safe cancellation, renewal, disable/quarantine and focus/context return. | Approved 1.7 reference mapping and focused UI/API/native checks when that path is implemented. |

The first decisive proof is the packaged LPAC/no-plaintext-write vertical. Mocked process tests and manifest inspection do not close it. Focused tests are selected first; full `service` and `security-local` profiles remain slice/Wave qualification unless the implementation changes shared infrastructure or a failure cannot be localized. If LPAC or mandatory no-write behavior is demonstrated infeasible, fail closed and use the ADR decision route rather than relaxing the approved boundary.
