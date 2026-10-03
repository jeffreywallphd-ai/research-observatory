"""Static conformance and trusted synthetic sample mapping tests."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from nacl.signing import SigningKey

REPO = Path(__file__).resolve().parents[2]
SAMPLE = REPO / "docs" / "developer" / "sample_repository"
CHECKER = REPO / "tools" / "connector_conformance.py"
CASES = (
    SAMPLE / "fixtures" / "repository-metadata.case.json",
    SAMPLE / "fixtures" / "search-page-1.case.json",
    SAMPLE / "fixtures" / "search-page-2.case.json",
)


def check(manifest: Path, *cases: Path) -> tuple[int, dict]:
    result = subprocess.run(
        [
            sys.executable,
            str(CHECKER),
            "--manifest",
            str(manifest),
            *(part for case in cases for part in ("--case", str(case))),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    return result.returncode, json.loads(result.stdout)


def check_package(package: Path, key: Path, *cases: Path) -> tuple[int, dict]:
    result = subprocess.run(
        [
            sys.executable,
            str(CHECKER),
            "--package",
            str(package),
            "--publisher-key-id",
            "sample-repository-publisher",
            "--publisher-key-file",
            str(key),
            *(part for case in cases for part in ("--case", str(case))),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    return result.returncode, json.loads(result.stdout)


class SampleConnectorConformanceTests(unittest.TestCase):
    def test_package_only_inspection_is_incomplete_behavior_conformance(self) -> None:
        status, report = check(SAMPLE / "manifest.json")
        self.assertEqual(1, status)
        self.assertEqual("incomplete", report["result"])
        self.assertEqual(0, report["caseCount"])
        self.assertIn(
            {"code": "CASE_OPERATION_COVERAGE_MISSING", "pointer": "/manifest/operations/0"}, report["violations"]
        )
        self.assertIn(
            {"code": "CASE_OPERATION_COVERAGE_MISSING", "pointer": "/manifest/operations/1"}, report["violations"]
        )
        self.assertIn(
            {"code": "SEARCH_CONTINUATION_COVERAGE_MISSING", "pointer": "/manifest/operations/1"},
            report["violations"],
        )

    def test_every_declared_operation_requires_a_case(self) -> None:
        status, report = check(SAMPLE / "manifest.json", CASES[0])
        self.assertEqual(1, status)
        self.assertEqual("fail", report["result"])
        self.assertIn(
            {"code": "CASE_OPERATION_COVERAGE_MISSING", "pointer": "/manifest/operations/1"}, report["violations"]
        )

    def test_search_requires_a_linked_continuation_case(self) -> None:
        status, report = check(SAMPLE / "manifest.json", CASES[0], CASES[1])
        self.assertEqual(1, status)
        self.assertIn(
            {"code": "SEARCH_CONTINUATION_COVERAGE_MISSING", "pointer": "/manifest/operations/1"},
            report["violations"],
        )
        with tempfile.TemporaryDirectory() as temporary:
            changed = Path(temporary) / "unlinked.json"
            case = json.loads(CASES[2].read_text(encoding="utf-8"))
            case["input"].pop("previousInvocationId")
            case["input"].pop("cursor")
            case["brokerCall"].pop("cursor")
            changed.write_text(json.dumps(case), encoding="utf-8")
            status, report = check(SAMPLE / "manifest.json", CASES[0], CASES[1], changed)
        self.assertEqual(1, status)
        self.assertIn(
            {"code": "SEARCH_CONTINUATION_COVERAGE_MISSING", "pointer": "/manifest/operations/1"},
            report["violations"],
        )

    def test_sample_manifest_and_three_cases_are_conformant(self) -> None:
        status, report = check(SAMPLE / "manifest.json", *CASES)
        self.assertEqual(0, status, report)
        self.assertEqual("pass", report["result"])
        self.assertEqual([], report["violations"])
        self.assertEqual(3, report["caseCount"])

    def test_sample_connector_maps_broker_observations_without_claiming_core_authority(self) -> None:
        sys.path.insert(0, str(SAMPLE))
        try:
            from plugin.connector import invoke  # type: ignore[import-not-found]

            for case_path in CASES:
                with self.subTest(case=case_path.name):
                    case = json.loads(case_path.read_text(encoding="utf-8"))
                    calls: list[dict] = []

                    def broker(
                        call: dict, *, _calls: list[dict] = calls, _response: dict = case["brokerResponse"]
                    ) -> bytes:
                        _calls.append(call)
                        return json.dumps(_response, separators=(",", ":")).encode("utf-8")

                    output = json.loads(
                        invoke(
                            json.dumps(case["input"], separators=(",", ":")).encode("utf-8"),
                            broker,
                            case["operation"],
                            context={"invocationId": case["invocationId"]},
                        )
                    )
                    self.assertEqual([case["brokerCall"]], calls)
                    self.assertEqual(case["output"], output)
                    self.assertNotIn("projectId", output)
                    self.assertNotIn("rightsStatus", output)
                    self.assertNotIn("sourceId", output)
                    self.assertNotIn("retrievedAt", output)
        finally:
            sys.path.remove(str(SAMPLE))
            sys.modules.pop("plugin", None)
            sys.modules.pop("plugin.connector", None)

    def test_sample_search_without_optional_page_size_does_not_invent_a_broker_parameter(self) -> None:
        sys.path.insert(0, str(SAMPLE))
        try:
            from plugin.connector import invoke

            case = json.loads(CASES[1].read_text(encoding="utf-8"))
            case["input"].pop("pageSize")
            case["brokerCall"].pop("pageSize")
            calls: list[dict] = []

            def broker(call: dict) -> bytes:
                calls.append(call)
                return json.dumps(case["brokerResponse"]).encode("utf-8")

            output = invoke(
                json.dumps(case["input"]).encode("utf-8"),
                broker,
                "search",
                context={"invocationId": case["invocationId"]},
            )
            self.assertEqual([case["brokerCall"]], calls)
            self.assertEqual(case["output"], json.loads(output))
        finally:
            sys.path.remove(str(SAMPLE))
            sys.modules.pop("plugin", None)
            sys.modules.pop("plugin.connector", None)

    def test_sample_rejects_provider_extra_fields_without_echoing_them(self) -> None:
        sys.path.insert(0, str(SAMPLE))
        try:
            from plugin.connector import invoke

            case = json.loads(CASES[1].read_text(encoding="utf-8"))
            case["brokerResponse"]["records"][0]["privateToken"] = "PRIVATE-DO-NOT-ECHO"

            def broker(_call: dict) -> bytes:
                return json.dumps(case["brokerResponse"]).encode("utf-8")

            with self.assertRaisesRegex(ValueError, "sample-contract-invalid") as denied:
                invoke(
                    json.dumps(case["input"]).encode("utf-8"),
                    broker,
                    "search",
                    context={"invocationId": case["invocationId"]},
                )
            self.assertNotIn("PRIVATE-DO-NOT-ECHO", str(denied.exception))
        finally:
            sys.path.remove(str(SAMPLE))
            sys.modules.pop("plugin", None)
            sys.modules.pop("plugin.connector", None)

    def test_unknown_field_has_stable_pointer_without_echoing_private_value(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            changed = Path(temporary) / "case.json"
            case = json.loads(CASES[1].read_text(encoding="utf-8"))
            case["output"]["projectId"] = "PRIVATE-DO-NOT-ECHO"
            changed.write_text(json.dumps(case), encoding="utf-8")
            status, report = check(SAMPLE / "manifest.json", changed)
        self.assertEqual(1, status)
        self.assertIn({"code": "PAGE_UNKNOWN_FIELD", "pointer": "/output/projectId", "case": 1}, report["violations"])
        self.assertNotIn("PRIVATE-DO-NOT-ECHO", json.dumps(report))

    def test_scientific_input_rejects_unknown_field_even_when_broker_call_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            changed = Path(temporary) / "case.json"
            case = json.loads(CASES[1].read_text(encoding="utf-8"))
            case["input"]["unexpectedParameter"] = "synthetic"
            case["brokerCall"]["unexpectedParameter"] = "synthetic"
            changed.write_text(json.dumps(case), encoding="utf-8")
            status, report = check(SAMPLE / "manifest.json", changed)
        self.assertEqual(1, status)
        self.assertIn({"code": "SCIENTIFIC_REQUEST_INVALID", "pointer": "/input", "case": 1}, report["violations"])

    def test_scientific_input_rejects_explicit_null_optional_parameter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            changed = Path(temporary) / "case.json"
            case = json.loads(CASES[1].read_text(encoding="utf-8"))
            case["input"]["pageSize"] = None
            case["brokerCall"]["pageSize"] = None
            changed.write_text(json.dumps(case), encoding="utf-8")
            status, report = check(SAMPLE / "manifest.json", changed)
        self.assertEqual(1, status)
        self.assertIn({"code": "SCIENTIFIC_REQUEST_INVALID", "pointer": "/input", "case": 1}, report["violations"])

    def test_worker_output_must_match_published_camel_case_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            changed = Path(temporary) / "case.json"
            case = json.loads(CASES[1].read_text(encoding="utf-8"))
            record = case["output"]["records"][0]
            record["raw_identifier"] = record.pop("rawIdentifier")
            changed.write_text(json.dumps(case), encoding="utf-8")
            status, report = check(SAMPLE / "manifest.json", changed)
        self.assertEqual(1, status)
        self.assertIn({"code": "PAGE_SCHEMA_INVALID", "pointer": "/output/records/0", "case": 1}, report["violations"])

    def test_unknown_field_names_are_not_diagnostic_content(self) -> None:
        secret = "SYNTHETIC_PRIVATE_FIELD_NAME_DO_NOT_ECHO"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = json.loads(CASES[1].read_text(encoding="utf-8"))
            case[secret] = "synthetic"
            root_case = root / "root-case.json"
            root_case.write_text(json.dumps(case), encoding="utf-8")
            _, root_report = check(SAMPLE / "manifest.json", root_case)

            case.pop(secret)
            case["brokerCall"][secret] = "synthetic"
            case["output"]["records"][0][secret] = "synthetic"
            nested_case = root / "nested-case.json"
            nested_case.write_text(json.dumps(case), encoding="utf-8")
            _, nested_report = check(SAMPLE / "manifest.json", nested_case)

            draft = root / "sample"
            shutil.copytree(SAMPLE, draft)
            manifest_path = draft / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest[secret] = "synthetic"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            _, manifest_report = check(manifest_path)
        self.assertNotIn(secret, json.dumps(root_report))
        self.assertNotIn(secret, json.dumps(nested_report))
        self.assertNotIn(secret, json.dumps(manifest_report))
        self.assertIn({"code": "CASE_UNKNOWN_FIELD", "pointer": "/case", "case": 1}, root_report["violations"])
        self.assertIn(
            {"code": "BROKER_CALL_UNKNOWN_FIELD", "pointer": "/brokerCall", "case": 1}, nested_report["violations"]
        )
        self.assertIn(
            {"code": "PAGE_UNKNOWN_FIELD", "pointer": "/output/records/0", "case": 1}, nested_report["violations"]
        )
        self.assertIn({"code": "MANIFEST_UNKNOWN_FIELD", "pointer": "/manifest"}, manifest_report["violations"])

    def test_reported_license_requires_a_value_without_claiming_usage_rights(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            changed = Path(temporary) / "case.json"
            case = json.loads(CASES[2].read_text(encoding="utf-8"))
            case["output"]["records"][0]["terms"]["license"]["value"] = None
            changed.write_text(json.dumps(case), encoding="utf-8")
            status, report = check(SAMPLE / "manifest.json", changed)
        self.assertEqual(1, status)
        self.assertIn(
            {"code": "PAGE_INVARIANT_INVALID", "pointer": "/output/records/0/terms/license", "case": 1},
            report["violations"],
        )

    def test_cursor_must_match_broker_observation_and_advance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            changed = Path(temporary) / "case.json"
            case = json.loads(CASES[1].read_text(encoding="utf-8"))
            case["output"]["nextCursor"] = "forged-page"
            changed.write_text(json.dumps(case), encoding="utf-8")
            status, report = check(SAMPLE / "manifest.json", changed)
            self.assertEqual(1, status)
            self.assertIn(
                {"code": "PAGE_CURSOR_UNOBSERVED", "pointer": "/output/nextCursor", "case": 1}, report["violations"]
            )

            case = json.loads(CASES[2].read_text(encoding="utf-8"))
            case["output"]["nextCursor"] = case["input"]["cursor"]
            case["output"]["continuation"] = "next-page"
            changed.write_text(json.dumps(case), encoding="utf-8")
            status, report = check(SAMPLE / "manifest.json", changed)
            self.assertEqual(1, status)
            self.assertIn(
                {"code": "PAGE_CURSOR_NOT_ADVANCING", "pointer": "/output/nextCursor", "case": 1}, report["violations"]
            )

    def test_broker_observed_cursor_cannot_be_silently_reported_as_exhausted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            changed = Path(temporary) / "case.json"
            case = json.loads(CASES[1].read_text(encoding="utf-8"))
            case["output"]["continuation"] = "exhausted"
            case["output"].pop("nextCursor")
            changed.write_text(json.dumps(case), encoding="utf-8")
            status, report = check(SAMPLE / "manifest.json", changed)
        self.assertEqual(1, status)
        self.assertIn({"code": "PAGE_CURSOR_OMITTED", "pointer": "/output/nextCursor", "case": 1}, report["violations"])

    def test_next_page_requires_matching_committed_case_predecessor(self) -> None:
        status, report = check(SAMPLE / "manifest.json", CASES[2])
        self.assertEqual(1, status)
        self.assertIn(
            {"code": "PAGE_PREDECESSOR_MISSING", "pointer": "/input/previousInvocationId", "case": 1},
            report["violations"],
        )
        with tempfile.TemporaryDirectory() as temporary:
            changed = Path(temporary) / "case.json"
            case = json.loads(CASES[2].read_text(encoding="utf-8"))
            case["input"]["query"] = "changed research query"
            case["brokerCall"]["query"] = "changed research query"
            changed.write_text(json.dumps(case), encoding="utf-8")
            status, report = check(SAMPLE / "manifest.json", CASES[1], changed)
        self.assertEqual(1, status)
        self.assertIn(
            {"code": "PAGE_PREDECESSOR_QUERY_MISMATCH", "pointer": "/input/query", "case": 2}, report["violations"]
        )

    def test_manifest_hash_check_does_not_execute_candidate_code(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            draft = Path(temporary) / "sample"
            shutil.copytree(SAMPLE, draft)
            entry = draft / "plugin" / "connector.py"
            entry.write_text("raise RuntimeError('PRIVATE-DO-NOT-ECHO')\n", encoding="utf-8")
            manifest_path = draft / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"][0]["sha256"] = "sha256:" + hashlib.sha256(entry.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            status, report = check(manifest_path, *(draft / "fixtures" / case.name for case in CASES))
        self.assertEqual(0, status, report)
        self.assertNotIn("PRIVATE-DO-NOT-ECHO", json.dumps(report))

    def test_manifest_file_hash_mismatch_has_exact_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            draft = Path(temporary) / "sample"
            shutil.copytree(SAMPLE, draft)
            manifest_path = draft / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"][0]["sha256"] = "sha256:" + "0" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            status, report = check(manifest_path)
        self.assertEqual(1, status)
        self.assertIn(
            {"code": "PACKAGE_FILE_HASH_MISMATCH", "pointer": "/manifest/files/0/sha256"}, report["violations"]
        )

    def test_signed_archive_requires_explicit_external_public_key_and_exact_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            key = SigningKey(b"\x19" * 32)
            public_key = root / "publisher.pub"
            public_key.write_bytes(bytes(key.verify_key))
            raw = (SAMPLE / "manifest.json").read_bytes()
            entry = (SAMPLE / "plugin" / "connector.py").read_bytes()

            def package(path: Path, *, changed: bool = False) -> None:
                with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr("manifest.json", raw)
                    archive.writestr("manifest.sig", key.sign(raw).signature)
                    archive.writestr("plugin/connector.py", entry + b"# tampered\n" if changed else entry)

            signed = root / "sample.zip"
            package(signed)
            status, report = check_package(signed, public_key)
            self.assertEqual(1, status)
            self.assertEqual("incomplete", report["result"])
            status, report = check_package(signed, public_key, *CASES)
            self.assertEqual(0, status, report)

            tampered = root / "tampered.zip"
            package(tampered, changed=True)
            status, report = check_package(tampered, public_key)
            self.assertEqual(1, status)
            self.assertIn({"code": "PACKAGE_ARCHIVE_INVALID", "pointer": "/package"}, report["violations"])

            bad_signature = root / "bad-signature.zip"
            with zipfile.ZipFile(bad_signature, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", raw)
                archive.writestr("manifest.sig", b"\0" * 64)
                archive.writestr("plugin/connector.py", entry)
            status, report = check_package(bad_signature, public_key)
        self.assertEqual(1, status)
        self.assertIn({"code": "PACKAGE_SIGNATURE_INVALID", "pointer": "/package/manifest.sig"}, report["violations"])


if __name__ == "__main__":
    unittest.main()
