# Software supply-chain security

The `security-local` profile and CI `security` job enforce one repository policy
for committed secrets, source misconfiguration, vulnerable dependencies, and
dependency licenses. The implementation uses Trivy 0.73.0 from the official Aqua
Security release. `security-toolchain.json` pins each supported desktop archive
by SHA-256; `tools/install_trivy.py` downloads into ignored checkout-local state,
verifies the archive before extraction, rejects unsafe or ambiguous executable
members, and verifies the installed version.

## Scan and report boundary

`tools/security_check.py` performs these scans:

- `secret` and `misconfig` against repository source, including Markdown;
- `vuln` and `license` against repository lockfiles and manifests; and
- `vuln` and `license` against installed `.venv` and `node_modules` environments
  when present.

Trivy's raw JSON exists only under ignored `.local/tmp/` for the duration of the
scan and is deleted in a `finally` block. Raw secret matches must never be
committed or uploaded. The retained JSON is a normalized report that preserves
finding identity, severity, package, target, and policy disposition but never
copies a secret match. CI retains only this normalized report for fourteen days.

## Release policy

`security-policy.json` is the machine-readable policy. Secrets always block.
`HIGH` and `CRITICAL` vulnerabilities or misconfigurations block. `MEDIUM`
findings are reported for review. Licenses must match an allowed SPDX identifier
or allowed Trivy category; explicitly denied identifiers and denied, restricted,
forbidden, reciprocal, or unknown categories block. The small explicit allowances for
MPL-2.0 and PSF-2.0 cover the current locked development environment and do not
authorize unreviewed additions to that list.

An exception in `security-exceptions.json` must:

- match the complete normalized finding key exactly, with no wildcard;
- have `status: approved`, a reviewer, rationale, and tracking ticket;
- specify ISO `reviewedAt` and `expiresAt` dates no more than 30 days apart; and
- be current and match an active blocking finding.

Expired, future-dated, overlong, duplicate, malformed, or unused exceptions fail
the gate. Removing the underlying finding therefore also requires removing its
exception.

## Local operation

```powershell
.venv\Scripts\python.exe tools/install_trivy.py --repo .
.venv\Scripts\python.exe tools/security_check.py --repo . --report artifacts/tmp/security-local.json
.venv\Scripts\python.exe tools/verify.py --profile security-local
```

The first installation and the first vulnerability scan require network access
to the pinned release and Trivy databases. Later runs use ignored local caches.
`tools/install_trivy.py --offline` verifies and reuses an already installed or
cached scanner without attempting a download.

Primary scanner sources:

- https://github.com/aquasecurity/trivy/releases/tag/v0.73.0
- https://trivy.dev/docs/latest/target/filesystem/
- https://trivy.dev/docs/latest/guide/scanner/secret/
- https://trivy.dev/docs/latest/scanner/license/
