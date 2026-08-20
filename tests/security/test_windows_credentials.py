from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
SERVICE_SRC = REPO / "services" / "core-api" / "src"
sys.path.insert(0, str(SERVICE_SRC))

from research_observatory_core.logging import build_log_record  # noqa: E402
from research_observatory_core.main import _parser  # noqa: E402
from research_observatory_core.object_store import create_local_object_store  # noqa: E402
from research_observatory_core.ports.credential_store import (  # noqa: E402
    SecretAccessContext,
    SecretAccessDenied,
    SecretConflict,
    SecretCorrupt,
    SecretKind,
    SecretPurpose,
    SecretReference,
    SecretUnavailable,
)
from research_observatory_core.ports.object_store import ObjectPutCommand  # noqa: E402
from research_observatory_core.storage import initialize_database  # noqa: E402
from research_observatory_core.windows_credentials import (  # noqa: E402
    WindowsCredentialStore,
    WindowsObjectMasterKeyProvider,
)

PROJECT_ID = "01890f6e-6a40-4cc5-98b7-7f3f36b60210"
CREATED_AT = "2026-08-20T12:00:00.000Z"


def reference() -> SecretReference:
    return SecretReference(
        profile_id="local-default",
        kind=SecretKind.PROVIDER_KEY,
        subject_id="provider-example",
        name="primary-api-key",
    )


def context() -> SecretAccessContext:
    return SecretAccessContext(
        calling_capability="CAP-12.S01",
        purpose=SecretPurpose.PROVIDER_AUTHENTICATION,
        audit_context="a" * 32,
    )


@unittest.skipUnless(os.name == "nt", "Windows DPAPI credential-store boundary")
class WindowsCredentialStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-windows-credentials-")
        self.root = Path(self.temporary.name).resolve()
        self.vault = self.root / "profile-vault"
        self.events: list[object] = []

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_user_scoped_round_trip_is_opaque_redacted_and_zeroes_the_lease(self) -> None:
        secret = b"provider-secret-that-must-not-leak"
        store = WindowsCredentialStore(self.vault, audit_sink=self.events.append)

        first = store.put(reference(), secret, context())
        with WindowsCredentialStore(self.vault, audit_sink=self.events.append).lease(reference(), context()) as lease:
            observed = lease.use(bytes)
        self.assertEqual(secret, observed)
        with self.assertRaises(SecretUnavailable):
            lease.use(bytes)

        vault_files = tuple(path for path in self.vault.rglob("*") if path.is_file())
        self.assertEqual(3, len(vault_files))
        self.assertTrue(any(path.suffix == ".sealed" for path in vault_files))
        for path in vault_files:
            payload = path.read_bytes()
            self.assertNotIn(secret, payload)
            self.assertNotIn(b"provider-example", payload)
            self.assertNotIn(b"primary-api-key", payload)
            self.assertNotIn("provider-example", path.name)
            self.assertNotIn("primary-api-key", path.name)

        self.assertEqual(2, len(self.events))
        for event in self.events:
            projection = repr(event)
            self.assertNotIn(secret.decode("ascii"), projection)
            self.assertNotIn("provider-example", projection)
            self.assertNotIn("primary-api-key", projection)
            self.assertRegex(event.reference_token, "^[0-9a-f]{32}$")  # type: ignore[attr-defined]
        self.assertRegex(first.version, "^[0-9a-f]{32}$")

    def test_corruption_and_os_unprotect_failure_retain_recoverable_ciphertext(self) -> None:
        secret = b"recoverable-secret-material"
        store = WindowsCredentialStore(self.vault, audit_sink=self.events.append)
        store.put(reference(), secret, context())
        record = next(self.vault.rglob("*.sealed"))
        original_record = record.read_bytes()
        tampered = bytearray(original_record)
        tampered[-1] ^= 0x80
        record.write_bytes(tampered)

        with self.assertRaises(SecretCorrupt):
            store.lease(reference(), context())
        self.assertEqual(bytes(tampered), record.read_bytes())
        record.write_bytes(original_record)
        with store.lease(reference(), context()) as lease:
            self.assertEqual(secret, lease.use(bytes))

        protected_root = self.vault / ".profile-vault-root-v1.dpapi"
        original_root = protected_root.read_bytes()
        protected_root.write_bytes(original_root[:-1] + bytes((original_root[-1] ^ 0x40,)))
        with self.assertRaises(SecretUnavailable):
            WindowsCredentialStore(self.vault, audit_sink=self.events.append).lease(reference(), context())
        self.assertTrue(record.is_file())
        protected_root.write_bytes(original_root)
        with WindowsCredentialStore(self.vault, audit_sink=self.events.append).lease(reference(), context()) as lease:
            self.assertEqual(secret, lease.use(bytes))

    def test_compare_and_swap_and_audit_failure_fail_closed(self) -> None:
        store = WindowsCredentialStore(self.vault, audit_sink=self.events.append)
        first = store.put(reference(), b"first-secret", context())
        with self.assertRaises(SecretConflict):
            store.put(reference(), b"unconditional-overwrite", context())
        with self.assertRaises(SecretConflict):
            store.put(reference(), b"stale-overwrite", context(), expected_version="b" * 32)
        second = store.put(reference(), b"second-secret", context(), expected_version=first.version)
        self.assertNotEqual(first.version, second.version)
        with store.lease(reference(), context()) as lease:
            self.assertEqual(b"second-secret", lease.use(bytes))

        denied = WindowsCredentialStore(
            self.vault,
            audit_sink=lambda _event: (_ for _ in ()).throw(RuntimeError("audit unavailable")),
        )
        with self.assertRaises(SecretAccessDenied):
            denied.lease(reference(), context())
        with self.assertRaises(SecretAccessDenied):
            denied.put(
                SecretReference("local-default", SecretKind.CONNECTOR_TOKEN, "connector-example", "oauth"),
                b"must-not-be-stored",
                context(),
            )
        self.assertEqual(1, len(tuple(self.vault.rglob("*.sealed"))))

    def test_default_audit_retains_only_the_bounded_attributed_projection(self) -> None:
        secret = b"audit-projection-secret-that-must-not-leak"
        captured = io.StringIO()
        store = WindowsCredentialStore(self.vault)
        with redirect_stderr(captured):
            store.put(reference(), secret, context())
            with store.lease(reference(), context()) as lease:
                self.assertEqual(secret, lease.use(bytes))

        records = [json.loads(line) for line in captured.getvalue().splitlines()]
        self.assertEqual(2, len(records))
        self.assertEqual(["put", "lease"], [record["operation"] for record in records])
        for record in records:
            self.assertEqual(
                {
                    "auditContext",
                    "callingCapability",
                    "event",
                    "level",
                    "operation",
                    "outcome",
                    "purpose",
                    "reasonCode",
                    "referenceToken",
                    "timestamp",
                },
                set(record),
            )
            self.assertEqual("security.credential-access", record["event"])
            self.assertEqual("authorized", record["outcome"])
            self.assertEqual("CAP-12.S01", record["callingCapability"])
            self.assertEqual("provider-authentication", record["purpose"])
            self.assertEqual("a" * 32, record["auditContext"])
            self.assertRegex(record["referenceToken"], "^[0-9a-f]{32}$")
            projection = json.dumps(record, sort_keys=True)
            self.assertNotIn(secret.decode("ascii"), projection)
            self.assertNotIn("provider-example", projection)
            self.assertNotIn("primary-api-key", projection)

        for unsafe_purpose in (
            "local-default",
            "provider-example",
            "primary-api-key",
            "canonical-looking-secret",
        ):
            with self.subTest(unsafe_purpose=unsafe_purpose):
                with self.assertRaises(ValueError):
                    SecretAccessContext(
                        calling_capability="CAP-12.S01",
                        purpose=unsafe_purpose,  # type: ignore[arg-type]
                        audit_context="b" * 32,
                    )
                structured_record = build_log_record(
                    "security.credential-access",
                    level="INFO",
                    fields={"purpose": unsafe_purpose},
                )
                self.assertEqual("[REDACTED]", structured_record["purpose"])

    def test_invalid_and_unavailable_vault_authorities_are_bounded_for_put_and_lease(self) -> None:
        for operation in ("put", "lease"):
            with self.subTest(authority="root-file", operation=operation):
                vault = self.root / f"root-file-{operation}"
                payload = b"existing-root-authority"
                vault.write_bytes(payload)
                store = WindowsCredentialStore(vault, audit_sink=self.events.append)
                with self.assertRaises(SecretAccessDenied):
                    if operation == "put":
                        store.put(reference(), b"must-not-be-stored", context())
                    else:
                        store.lease(reference(), context())
                self.assertEqual(payload, vault.read_bytes())

            with self.subTest(authority="records-file", operation=operation):
                vault = self.root / f"records-file-{operation}"
                vault.mkdir()
                records = vault / "records"
                payload = b"existing-record-authority"
                records.write_bytes(payload)
                store = WindowsCredentialStore(vault, audit_sink=self.events.append)
                with self.assertRaises(SecretAccessDenied):
                    if operation == "put":
                        store.put(reference(), b"must-not-be-stored", context())
                    else:
                        store.lease(reference(), context())
                self.assertEqual(payload, records.read_bytes())

        store = WindowsCredentialStore(self.vault, audit_sink=self.events.append)
        store.put(reference(), b"ciphertext-must-remain", context())
        before = {path.relative_to(self.vault): path.read_bytes() for path in self.vault.rglob("*") if path.is_file()}
        for operation in ("put", "lease"):
            with (
                self.subTest(authority="unavailable", operation=operation),
                patch(
                    "research_observatory_core.windows_credentials.Path.mkdir",
                    side_effect=PermissionError("simulated unavailable authority"),
                ),
                self.assertRaises(SecretUnavailable),
            ):
                if operation == "put":
                    store.put(
                        SecretReference(
                            "local-default",
                            SecretKind.CONNECTOR_TOKEN,
                            "connector-unavailable",
                            "oauth",
                        ),
                        b"must-not-be-stored",
                        context(),
                    )
                else:
                    store.lease(reference(), context())
        after = {path.relative_to(self.vault): path.read_bytes() for path in self.vault.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_concurrent_processes_converge_on_one_object_key_record(self) -> None:
        code = (
            "from pathlib import Path;"
            "from research_observatory_core.windows_credentials import "
            "WindowsCredentialStore,WindowsObjectMasterKeyProvider;"
            "provider=WindowsObjectMasterKeyProvider(WindowsCredentialStore(Path(__import__('sys').argv[1])),"
            "profile_id='local-default');"
            "print(provider.active_object_master_key().key_version)"
        )
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(SERVICE_SRC)
        processes = [
            subprocess.Popen(
                [sys.executable, "-c", code, str(self.vault)],
                cwd=REPO,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _ in range(2)
        ]
        outputs = [process.communicate(timeout=20) for process in processes]
        for process, (stdout, stderr) in zip(processes, outputs, strict=True):
            self.assertEqual(0, process.returncode, stderr)
            self.assertEqual("object-key-v1", stdout.strip())
            self.assertNotIn("Traceback", stderr)
        self.assertEqual(1, len(tuple(self.vault.rglob("*.sealed"))))

    def test_object_key_provider_survives_restart_without_leaking_into_project_state_or_exports(self) -> None:
        project = self.root / "project"
        for relative in ("state", "objects", "exports", ".tmp"):
            (project / relative).mkdir(parents=True)
        initialize_database(
            project / "state" / "project.sqlite3",
            project_id=PROJECT_ID,
            project_created_at=CREATED_AT,
        )
        provider = WindowsObjectMasterKeyProvider(
            WindowsCredentialStore(self.vault, audit_sink=self.events.append),
            profile_id="local-default",
        )
        first_key = provider.active_object_master_key()
        plaintext = b"private object protected by the profile vault" * 100
        store = create_local_object_store(project, PROJECT_ID, key_provider=provider)
        stored = store.put(
            io.BytesIO(plaintext),
            ObjectPutCommand(
                media_type="application/pdf",
                rights_status="allowed",
                protection_profile="project-encrypted-v1",
                retention_class="project-lifetime",
                creation_source="test-fixture",
                created_at=CREATED_AT,
            ),
        )

        restarted_provider = WindowsObjectMasterKeyProvider(
            WindowsCredentialStore(self.vault, audit_sink=self.events.append),
            profile_id="local-default",
        )
        self.assertEqual(first_key, restarted_provider.active_object_master_key())
        restarted = create_local_object_store(project, PROJECT_ID, key_provider=restarted_provider)
        with restarted.open(stored.object_sha256, purpose="document-analysis") as stream:
            self.assertEqual(plaintext, stream.read())
        for path in project.rglob("*"):
            if path.is_file():
                self.assertNotIn(first_key.key_bytes, path.read_bytes())
        self.assertEqual((), tuple((project / "exports").iterdir()))
        support_schema = json.loads(
            (REPO / "packages" / "contracts" / "support-bundle" / "support-bundle.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("credentials-and-tokens", support_schema["properties"]["exclusions"]["const"])
        process_options = {option for action in _parser()._actions for option in action.option_strings}
        self.assertEqual({"-h", "--help", "--check", "--version", "--supervised"}, process_options)

    def test_redirected_vault_authority_is_denied_without_touching_the_target(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        redirected = self.root / "redirected-vault"
        try:
            redirected.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("directory symlinks are unavailable to the current Windows token")
        store = WindowsCredentialStore(redirected, audit_sink=self.events.append)
        with self.assertRaises(SecretAccessDenied):
            store.put(reference(), b"must-not-cross-the-redirect", context())
        self.assertEqual((), tuple(outside.iterdir()))


if __name__ == "__main__":
    unittest.main()
