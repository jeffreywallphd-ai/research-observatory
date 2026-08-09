# Software supply-chain security

The `security-local` profile and CI `security` job enforce one repository policy
for committed secrets, source misconfiguration, vulnerable dependencies, and
dependency licenses. The implementation uses Trivy 0.73.0 from the official Aqua
Security release. `security-toolchain.json` pins each supported desktop archive
and its extracted executable by SHA-256; `tools/install_trivy.py` downloads into
ignored checkout-local state, verifies the archive before extraction, rejects
unsafe or ambiguous executable members, verifies every reused executable before
running it, and then verifies the installed version.

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
If raw-report deletion fails, the scan fails; scanner stdout/stderr is withheld
from retained errors because it may itself contain secret material.

Every invocation supplies generated empty Trivy configuration and ignore files
from the private scan directory and removes every inherited `TRIVY_*` environment
variable. A committed `trivy.yaml`, `.trivyignore`, or ambient Trivy setting
therefore cannot suppress a finding outside `security-exceptions.json`.

## Release policy

`security-policy.json` is the machine-readable policy. Secrets always block.
`HIGH` and `CRITICAL` vulnerabilities or misconfigurations block. `MEDIUM`
findings are reported for review. Licenses must match an allowed SPDX identifier
or allowed Trivy category; explicitly denied identifiers and denied, restricted,
forbidden, reciprocal, or unknown categories block. The small explicit allowances for
MPL-2.0 and PSF-2.0 cover the current locked development environment and do not
authorize unreviewed additions to that list. A conjunction such as
`MIT AND PSF-2.0` is allowed only when every component is individually present
in the allowlist. Disjunctions, license exceptions, malformed expressions, and
any conjunction containing an unlisted or denied component continue to fail
closed unless the complete identifier is reviewed and explicitly allowed.

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

CI runs both the live scanner and the controlled security boundary suite. The
workflow contract fails if either command is removed.

Primary scanner sources:

- https://github.com/aquasecurity/trivy/releases/tag/v0.73.0
- https://trivy.dev/docs/latest/target/filesystem/
- https://trivy.dev/docs/latest/guide/scanner/secret/
- https://trivy.dev/docs/latest/scanner/license/
