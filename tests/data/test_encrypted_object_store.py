from __future__ import annotations

import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from typing import BinaryIO, cast
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
SERVICE_SRC = REPO / "services" / "core-api" / "src"
sys.path.insert(0, str(SERVICE_SRC))

from research_observatory_core import object_store as object_store_module  # noqa: E402
from research_observatory_core.object_store import create_local_object_store  # noqa: E402
from research_observatory_core.ports.object_store import (  # noqa: E402
    ObjectCorrupt,
    ObjectKeyUnavailable,
    ObjectPutCommand,
    ObjectStoreProblem,
)
from research_observatory_core.ports.object_store_keys import (  # noqa: E402
    ObjectMasterKey,
)
from research_observatory_core.storage import development_plaintext_database_fixture, initialize_database  # noqa: E402

PROJECT_ID = "01890f6e-6a40-4cc5-98b7-7f3f36b60210"
CREATED_AT = "2026-08-18T12:00:00.000Z"


class MemoryKeyProvider:
    def __init__(self, keys: dict[str, bytes], active: str) -> None:
        self.keys = dict(keys)
        self.active = active

    def active_object_master_key(self) -> ObjectMasterKey:
        return ObjectMasterKey(self.active, self.keys[self.active])

    def object_master_key(self, key_version: str) -> ObjectMasterKey | None:
        key = self.keys.get(key_version)
        return None if key is None else ObjectMasterKey(key_version, key)


class InterruptedSource(io.RawIOBase):
    def __init__(self) -> None:
        self.calls = 0

    def read(self, _size: int = -1) -> bytes:
        self.calls += 1
        if self.calls == 1:
            return b"plaintext-that-must-never-be-staged"
        raise OSError("injected source interruption")


def command(*, profile: str = "project-encrypted-v1") -> ObjectPutCommand:
    return ObjectPutCommand(
        media_type="application/pdf",
        rights_status="allowed",
        protection_profile=profile,
        retention_class="project-lifetime",
        creation_source="test-fixture",
        created_at=CREATED_AT,
    )


class EncryptedObjectStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_profile = development_plaintext_database_fixture()
        self.database_profile.__enter__()
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-encrypted-object-store-")
        self.project = Path(self.temporary.name).resolve() / "project"
        for relative in ("state", "objects", ".tmp"):
            (self.project / relative).mkdir(parents=True, mode=0o700)
        initialize_database(
            self.project / "state" / "project.sqlite3",
            project_id=PROJECT_ID,
            project_created_at=CREATED_AT,
        )
        self.v1 = bytes.fromhex("11" * 32)
        self.v2 = bytes.fromhex("22" * 32)

    def tearDown(self) -> None:
        try:
            self.temporary.cleanup()
        finally:
            self.database_profile.__exit__(None, None, None)

    def object_file(self) -> Path:
        files = tuple(path for path in (self.project / "objects").rglob("*") if path.is_file())
        self.assertEqual(1, len(files))
        return files[0]

    def test_encrypted_put_persists_no_plaintext_and_restart_streams_exact_bytes(self) -> None:
        plaintext = (b"private-research-observation\n" * 100_000) + b"final"
        store = create_local_object_store(
            self.project,
            PROJECT_ID,
            key_provider=MemoryKeyProvider({"object-key-v1": self.v1}, "object-key-v1"),
        )

        stored = store.put(io.BytesIO(plaintext), command())

        physical = self.object_file().read_bytes()
        self.assertNotIn(b"private-research-observation", physical)
        self.assertNotEqual(plaintext, physical)
        self.assertEqual("secretstream-xchacha20poly1305-v1", stored.envelope_version)
        self.assertEqual("object-key-v1", stored.key_version)
        self.assertGreater(stored.ciphertext_byte_length, stored.byte_length)
        restarted = create_local_object_store(
            self.project,
            PROJECT_ID,
            key_provider=MemoryKeyProvider({"object-key-v1": self.v1}, "object-key-v1"),
        )
        with restarted.open(stored.object_sha256, purpose="document-analysis") as stream:
            self.assertEqual(plaintext, stream.read())
        self.assertEqual(hashlib.sha256(plaintext).hexdigest(), stored.object_sha256)

    def test_encrypted_staging_contains_no_plaintext_and_interruption_cleans_partial_envelope(self) -> None:
        plaintext = b"never-persist-this-plaintext" * 10_000
        store = create_local_object_store(
            self.project,
            PROJECT_ID,
            key_provider=MemoryKeyProvider({"object-key-v1": self.v1}, "object-key-v1"),
        )
        original_publish = object_store_module._publish
        inspected = False

        def inspect_encrypted_staging(staging: Path, destination: Path) -> bool:
            nonlocal inspected
            inspected = True
            staged = staging.read_bytes()
            self.assertNotIn(b"never-persist-this-plaintext", staged)
            self.assertNotEqual(plaintext, staged)
            return original_publish(staging, destination)

        with patch.object(object_store_module, "_publish", inspect_encrypted_staging):
            store.put(io.BytesIO(plaintext), command())
        self.assertTrue(inspected)
        self.assertEqual((), tuple((self.project / ".tmp").rglob("*.partial")))

        with self.assertRaises(ObjectStoreProblem) as raised:
            store.put(cast(BinaryIO, InterruptedSource()), command())
        self.assertIsNone(raised.exception.__cause__)
        self.assertIsNone(raised.exception.__context__)
        self.assertEqual((), tuple((self.project / ".tmp").rglob("*.partial")))

    def test_empty_encrypted_object_is_authenticated_and_streams_as_empty(self) -> None:
        store = create_local_object_store(
            self.project,
            PROJECT_ID,
            key_provider=MemoryKeyProvider({"object-key-v1": self.v1}, "object-key-v1"),
        )
        stored = store.put(io.BytesIO(b""), command())

        self.assertEqual(hashlib.sha256(b"").hexdigest(), stored.object_sha256)
        self.assertEqual(0, stored.byte_length)
        self.assertGreater(stored.ciphertext_byte_length, 0)
        with store.open(stored.object_sha256, purpose="document-analysis") as stream:
            self.assertEqual(b"", stream.read(1))

    def test_ciphertext_tamper_is_quarantined_before_plaintext_is_returned(self) -> None:
        store = create_local_object_store(
            self.project,
            PROJECT_ID,
            key_provider=MemoryKeyProvider({"object-key-v1": self.v1}, "object-key-v1"),
        )
        stored = store.put(io.BytesIO(b"authenticated plaintext" * 100), command())
        path = self.object_file()
        payload = bytearray(path.read_bytes())
        payload[-1] ^= 0x80
        path.write_bytes(payload)

        with self.assertRaises(ObjectCorrupt):
            store.open(stored.object_sha256, purpose="document-analysis")
        self.assertEqual("quarantined", store.metadata(stored.object_sha256).storage_state)

    def test_missing_key_is_bounded_and_does_not_misclassify_ciphertext_as_corrupt(self) -> None:
        store = create_local_object_store(
            self.project,
            PROJECT_ID,
            key_provider=MemoryKeyProvider({"object-key-v1": self.v1}, "object-key-v1"),
        )
        stored = store.put(io.BytesIO(b"key loss must be explicit"), command())
        unavailable = create_local_object_store(
            self.project,
            PROJECT_ID,
            key_provider=MemoryKeyProvider({"object-key-v2": self.v2}, "object-key-v2"),
        )

        with self.assertRaises(ObjectKeyUnavailable) as raised:
            unavailable.open(stored.object_sha256, purpose="document-analysis")
        self.assertIsNone(raised.exception.__cause__)
        self.assertIsNone(raised.exception.__context__)
        self.assertEqual("available", unavailable.metadata(stored.object_sha256).storage_state)

    def test_key_rotation_keeps_old_objects_readable_and_stamps_new_version(self) -> None:
        first_store = create_local_object_store(
            self.project,
            PROJECT_ID,
            key_provider=MemoryKeyProvider({"object-key-v1": self.v1}, "object-key-v1"),
        )
        first = first_store.put(io.BytesIO(b"old key object"), command())
        rotated = create_local_object_store(
            self.project,
            PROJECT_ID,
            key_provider=MemoryKeyProvider(
                {"object-key-v1": self.v1, "object-key-v2": self.v2},
                "object-key-v2",
            ),
        )
        second = rotated.put(io.BytesIO(b"new key object"), command())

        self.assertEqual("object-key-v1", first.key_version)
        self.assertEqual("object-key-v2", second.key_version)
        with rotated.open(first.object_sha256, purpose="document-analysis") as stream:
            self.assertEqual(b"old key object", stream.read())

    def test_plaintext_fixture_mode_is_explicit_and_test_only(self) -> None:
        with self.assertRaises(ObjectKeyUnavailable):
            create_local_object_store(self.project, PROJECT_ID)
        fixture = create_local_object_store(self.project, PROJECT_ID, allow_plaintext_fixture=True)
        stored = fixture.put(io.BytesIO(b"visible fixture bytes"), command(profile="plaintext-fixture-v1"))

        self.assertEqual("plaintext-fixture-v1", stored.envelope_version)
        self.assertIsNone(stored.key_version)
        self.assertEqual(b"visible fixture bytes", self.object_file().read_bytes())


if __name__ == "__main__":
    unittest.main()
