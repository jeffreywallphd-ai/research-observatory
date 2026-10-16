"""Real current-user DPAPI + guarded SQLCipher FTS; no Native-session claim."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core.derivative_keys import VaultDerivativeKeyProvider  # noqa: E402
from research_observatory_core.lexical_index_store import LexicalStoreProblem, ProtectedLexicalStore  # noqa: E402
from research_observatory_core.ports.credential_store import SecretAuditEvent, SecretPurpose  # noqa: E402
from research_observatory_core.ports.derivative_keys import (  # noqa: E402
    DerivativeKeyProblem,
    DerivativeKeyScope,
    DerivativePurpose,
)
from research_observatory_core.search import parse_query  # noqa: E402
from research_observatory_core.storage import StorageProblem, open_canonical_database  # noqa: E402
from research_observatory_core.windows_credentials import (  # noqa: E402
    WindowsCredentialStore,
    WindowsDatabaseKeyProvider,
)

from tests.search.test_derivative_keys import GENERATION, PROJECT  # noqa: E402
from tests.search.test_protected_lexical_store import PRIVATE, row  # noqa: E402


@unittest.skipUnless(os.name == "nt", "W3 Windows current-user DPAPI boundary")
class WindowsDerivativeIndexTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-index-dpapi-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.project = self.root / "synthetic-project"
        (self.project / "indexes").mkdir(parents=True)
        self.events: list[SecretAuditEvent] = []
        self.vault = WindowsCredentialStore(self.root / "vault", audit_sink=self.events.append)
        self.canonical = WindowsDatabaseKeyProvider(self.vault, profile_id="fixture")
        with self.canonical.active_key(PROJECT, create=True) as key:
            self.version = key.version
        self.scope = DerivativeKeyScope(PROJECT, GENERATION, DerivativePurpose.LEXICAL, self.version, "a" * 64)
        self.keys = VaultDerivativeKeyProvider(self.vault, profile_id="fixture", database_keys=self.canonical)

    def test_dpapi_restart_real_fts_ciphertext_and_legacy_path_denial(self):
        with ProtectedLexicalStore(self.project, self.scope, self.keys, create=True) as store:
            store.apply((row(),), (), expected_checkpoint=0, checkpoint=1)
            store.integrity_check()
            self.assertEqual((PROJECT,), store.match(parse_query("title:cafe"), (row().entry_id,), (PROJECT,)))
        reopened_vault = WindowsCredentialStore(self.root / "vault", audit_sink=self.events.append)
        reopened_canonical = WindowsDatabaseKeyProvider(reopened_vault, profile_id="fixture")
        reopened_keys = VaultDerivativeKeyProvider(
            reopened_vault, profile_id="fixture", database_keys=reopened_canonical
        )
        with ProtectedLexicalStore(self.project, self.scope, reopened_keys) as store:
            self.assertEqual(1, store.checkpoint)
            self.assertEqual((PROJECT,), store.match(parse_query("title:cafe"), (row().entry_id,), (PROJECT,)))
        self.assertTrue(any(event.purpose is SecretPurpose.DERIVATIVE_INDEX_ENCRYPTION for event in self.events))
        for file in self.root.rglob("*"):
            if file.is_file():
                self.assertNotIn(PRIVATE.encode(), file.read_bytes())
        database = self.project / "indexes" / ("lexical-" + GENERATION + ".sqlite3")
        self.assertNotEqual(b"SQLite format 3\0", database.read_bytes()[:16])
        with self.assertRaises(StorageProblem):
            open_canonical_database(database, expected_project_id=PROJECT)
        # The project DB port itself is not a derivative key authority.
        with self.assertRaises(LexicalStoreProblem):
            ProtectedLexicalStore(self.project, self.scope, cast(Any, reopened_canonical))

    def test_actual_vault_project_key_rotation_invalidates_live_index_lease(self):
        lease = self.keys.lease(self.scope, create=True)
        self.addCleanup(lease.close)
        with self.canonical.staged_rekey(PROJECT, "1" * 32, create=True):
            pass
        self.canonical.activate_rekey(PROJECT, "1" * 32, expected_active_version=self.version)
        with self.assertRaises(DerivativeKeyProblem):
            lease.use(self.scope, bytes)
        with self.assertRaises(DerivativeKeyProblem):
            self.keys.lease(self.scope, create=False)


if __name__ == "__main__":
    unittest.main()
