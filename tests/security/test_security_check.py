from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from security_check import evaluate, load_policy, normalize_reports, run_trivy, trivy_commands  # noqa: E402


def load_fixture(name: str) -> dict[str, object]:
    return json.loads((REPO / "tests" / "security" / "fixtures" / name).read_text(encoding="utf-8"))


def exception_for(key: str, *, reviewed_at: str = "2026-08-01", expires_at: str = "2026-08-20") -> dict[str, object]:
    return {
        "schemaVersion": "1.0",
        "documentType": "software-supply-chain-exceptions",
        "exceptions": [
            {
                "findingKey": key,
                "status": "approved",
                "reviewedBy": "controlled-test-reviewer",
                "reviewedAt": reviewed_at,
                "expiresAt": expires_at,
                "rationale": "Controlled exception policy fixture",
                "ticket": "TEST-SEC-001",
            }
        ],
    }


class SecurityPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_policy(REPO)
        self.findings, self.packages = normalize_reports([load_fixture("trivy-violations.json")])

    def test_normalization_removes_secret_values_and_is_stable(self) -> None:
        self.assertEqual(
            {"license", "misconfiguration", "secret", "vulnerability"}, {item["kind"] for item in self.findings}
        )
        secret = next(item for item in self.findings if item["kind"] == "secret")
        self.assertNotIn("Match", secret)
        self.assertNotIn("redacted-test-value", json.dumps(self.findings))
        self.assertIn("|line:1", secret["key"])
        self.assertEqual(sorted(item["key"] for item in self.findings), [item["key"] for item in self.findings])

    def test_known_violations_block_without_exceptions(self) -> None:
        exceptions = {
            "schemaVersion": "1.0",
            "documentType": "software-supply-chain-exceptions",
            "exceptions": [],
        }

        evaluated, errors, warnings = evaluate(self.findings, self.policy, exceptions, today=date(2026, 8, 8))

        self.assertEqual([], errors)
        self.assertEqual([], warnings)
        self.assertEqual(4, sum(item["disposition"] == "BLOCK" for item in evaluated))

    def test_exact_reviewed_exception_suppresses_only_its_current_finding(self) -> None:
        vulnerability = next(item for item in self.findings if item["kind"] == "vulnerability")

        evaluated, errors, _ = evaluate(
            self.findings,
            self.policy,
            exception_for(vulnerability["key"]),
            today=date(2026, 8, 8),
        )

        self.assertEqual([], errors)
        self.assertEqual(1, sum(item["disposition"] == "EXCEPTED" for item in evaluated))
        self.assertEqual(3, sum(item["disposition"] == "BLOCK" for item in evaluated))

    def test_expired_and_overlong_exceptions_fail_policy(self) -> None:
        key = self.findings[0]["key"]

        _, expired_errors, _ = evaluate(
            self.findings,
            self.policy,
            exception_for(key, reviewed_at="2026-07-01", expires_at="2026-08-07"),
            today=date(2026, 8, 8),
        )
        _, overlong_errors, _ = evaluate(
            self.findings,
            self.policy,
            exception_for(key, reviewed_at="2026-08-01", expires_at="2026-09-15"),
            today=date(2026, 8, 8),
        )

        self.assertTrue(any("expired" in error for error in expired_errors))
        self.assertTrue(any("30-day maximum" in error for error in overlong_errors))

    def test_suffixed_malformed_exception_dates_fail_policy(self) -> None:
        _, errors, _ = evaluate(
            self.findings,
            self.policy,
            exception_for(self.findings[0]["key"], reviewed_at="2026-08-01-not-iso", expires_at="2026-08-20-not-iso"),
            today=date(2026, 8, 8),
        )

        self.assertEqual(2, sum("must be an ISO date" in error for error in errors))

    def test_unused_exception_fails_closed(self) -> None:
        evaluated, errors, _ = evaluate(
            self.findings,
            self.policy,
            exception_for("vulnerability|CVE-2000-0000|missing.lock|missing"),
            today=date(2026, 8, 8),
        )

        self.assertEqual(4, sum(item["disposition"] == "BLOCK" for item in evaluated))
        self.assertTrue(any("does not match a current blocking finding" in error for error in errors))

    def test_clean_allowed_license_report_passes(self) -> None:
        findings, _ = normalize_reports([load_fixture("trivy-clean.json")])
        exceptions = {
            "schemaVersion": "1.0",
            "documentType": "software-supply-chain-exceptions",
            "exceptions": [],
        }

        evaluated, errors, warnings = evaluate(findings, self.policy, exceptions, today=date(2026, 8, 8))

        self.assertEqual([], errors)
        self.assertEqual([], warnings)
        self.assertEqual(["ALLOW"], [item["disposition"] for item in evaluated])

    def test_allowed_spdx_conjunction_requires_every_component_to_be_allowed(self) -> None:
        base = {
            "kind": "license",
            "severity": "UNKNOWN",
            "category": "unknown",
            "target": "Python",
            "package": "controlled-package",
            "title": "Controlled composite license fixture",
        }
        allowed = {
            **base,
            "key": "license|MIT AND PSF-2.0|Python|controlled-package",
            "id": "MIT AND PSF-2.0",
        }
        denied = {
            **base,
            "key": "license|MIT AND AGPL-3.0-only|Python|controlled-package",
            "id": "MIT AND AGPL-3.0-only",
        }
        invalid_expressions = [
            "MIT OR PSF-2.0",
            "MIT WITH LLVM-exception",
            "MIT && AGPL-3.0-only",
            "MIT AND PSF-2.0 OR AGPL-3.0-only",
        ]
        unlisted = {
            **base,
            "key": "license|MIT AND BlueOak-1.0.0|Python|controlled-package",
            "id": "MIT AND BlueOak-1.0.0",
            "category": "permissive",
        }
        exceptions = {
            "schemaVersion": "1.0",
            "documentType": "software-supply-chain-exceptions",
            "exceptions": [],
        }

        findings = [allowed, denied, unlisted]
        findings.extend(
            {
                **base,
                "key": f"license|{identifier}|Python|controlled-package",
                "id": identifier,
                "category": "permissive",
            }
            for identifier in invalid_expressions
        )
        evaluated, errors, _ = evaluate(findings, self.policy, exceptions, today=date(2026, 8, 8))

        self.assertEqual([], errors)
        self.assertEqual(
            ["ALLOW", "BLOCK", "BLOCK", "BLOCK", "BLOCK", "BLOCK", "BLOCK"], [item["disposition"] for item in evaluated]
        )
        self.assertIn("explicitly denied", evaluated[1]["policyReason"])
        self.assertIn("component that is not explicitly allowed", evaluated[2]["policyReason"])
        self.assertTrue(all("not an allowed SPDX conjunction" in item["policyReason"] for item in evaluated[3:]))

    def test_unlisted_reciprocal_license_blocks_while_explicit_mpl_allowance_remains_visible(self) -> None:
        reciprocal = {
            "key": "license|GPL-3.0-only|Python|controlled-package",
            "kind": "license",
            "id": "GPL-3.0-only",
            "severity": "MEDIUM",
            "category": "reciprocal",
            "target": "Python",
            "package": "controlled-package",
            "title": "Controlled reciprocal license fixture",
        }
        mpl = {
            **reciprocal,
            "key": "license|MPL-2.0|Python|controlled-package",
            "id": "MPL-2.0",
        }
        exceptions = {
            "schemaVersion": "1.0",
            "documentType": "software-supply-chain-exceptions",
            "exceptions": [],
        }

        evaluated, errors, warnings = evaluate([reciprocal, mpl], self.policy, exceptions, today=date(2026, 8, 8))

        self.assertEqual([], errors)
        self.assertEqual(["BLOCK", "WARN"], [item["disposition"] for item in evaluated])
        self.assertEqual([mpl["key"]], warnings)

    def test_retained_fixture_report_contains_only_normalized_secret_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "security.json"
            # The subprocess-level CLI behavior is exercised by the verification profile; this assertion
            # protects the retained-report boundary independently of Trivy availability.
            findings, _ = normalize_reports([load_fixture("trivy-violations.json")])
            output.write_text(json.dumps({"findings": findings}), encoding="utf-8")

            self.assertNotIn("redacted-test-value", output.read_text(encoding="utf-8"))

    def test_live_runner_deletes_raw_reports_after_normalization_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary)
            (checkout / ".local" / "tmp").mkdir(parents=True)
            for relative in ("security-policy.json", "security-toolchain.json", "trivy-secret.yaml"):
                (checkout / relative).write_bytes((REPO / relative).read_bytes())

            observed_environments: list[dict[str, str]] = []

            def controlled_runner(command: list[str], **options: object) -> subprocess.CompletedProcess[str]:
                environment = options["env"]
                self.assertIsInstance(environment, dict)
                observed_environments.append(environment)  # type: ignore[arg-type]
                output = Path(command[command.index("--output") + 1])
                output.write_text(json.dumps(load_fixture("trivy-clean.json")), encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            with (
                patch.dict(os.environ, {"TRIVY_IGNORE_UNFIXED": "true", "trivy_config": "ambient.yaml"}),
                patch("security_check.install", return_value=checkout / "trivy.exe"),
                patch("security_check.scanner_version", return_value="0.73.0"),
            ):
                reports, version = run_trivy(checkout, load_policy(checkout), runner=controlled_runner)

            self.assertEqual("0.73.0", version)
            self.assertEqual(2, len(reports))
            self.assertTrue(observed_environments)
            self.assertTrue(all(not key.upper().startswith("TRIVY_") for env in observed_environments for key in env))
            self.assertEqual([], list((checkout / ".local" / "tmp").iterdir()))

    def test_commands_override_committed_config_and_ignore_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary)
            scratch = checkout / ".local" / "tmp" / "scan"
            scratch.mkdir(parents=True)
            (checkout / "trivy.yaml").write_text("exit-code: 0\n", encoding="utf-8")
            (checkout / ".trivyignore").write_text("CVE-*\n", encoding="utf-8")

            commands = trivy_commands(checkout, checkout / "trivy.exe", self.policy, scratch)

            self.assertTrue(commands)
            for command, _ in commands:
                config = Path(command[command.index("--config") + 1])
                ignore = Path(command[command.index("--ignorefile") + 1])
                self.assertEqual(scratch / "trivy.yaml", config)
                self.assertEqual(scratch / ".trivyignore", ignore)
                self.assertNotEqual(checkout / "trivy.yaml", config)
                self.assertNotEqual(checkout / ".trivyignore", ignore)

    def test_scanner_failure_withholds_potential_secret_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary)
            (checkout / ".local" / "tmp").mkdir(parents=True)
            for relative in ("security-policy.json", "security-toolchain.json", "trivy-secret.yaml"):
                (checkout / relative).write_bytes((REPO / relative).read_bytes())

            def failing_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                return subprocess.CompletedProcess(command, 7, "potential-secret-value", "")

            with (
                patch("security_check.install", return_value=checkout / "trivy.exe"),
                patch("security_check.scanner_version", return_value="0.73.0"),
                self.assertRaisesRegex(RuntimeError, "output was withheld") as raised,
            ):
                run_trivy(checkout, load_policy(checkout), runner=failing_runner)

            self.assertNotIn("potential-secret-value", str(raised.exception))

    def test_raw_report_cleanup_failure_fails_the_scan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary)
            (checkout / ".local" / "tmp").mkdir(parents=True)
            for relative in ("security-policy.json", "security-toolchain.json", "trivy-secret.yaml"):
                (checkout / relative).write_bytes((REPO / relative).read_bytes())

            def controlled_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                output = Path(command[command.index("--output") + 1])
                output.write_text(json.dumps(load_fixture("trivy-clean.json")), encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            with (
                patch("security_check.install", return_value=checkout / "trivy.exe"),
                patch("security_check.scanner_version", return_value="0.73.0"),
                patch("security_check.shutil.rmtree", side_effect=OSError("controlled cleanup failure")),
                self.assertRaisesRegex(OSError, "controlled cleanup failure"),
            ):
                run_trivy(checkout, load_policy(checkout), runner=controlled_runner)


if __name__ == "__main__":
    unittest.main()
