"""Owned crash producer with synthetic data and fixture keys delivered by stdin."""

import json
import os
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core.derivative_keys import VaultDerivativeKeyProvider  # noqa: E402
from research_observatory_core.lexical_index_store import ProtectedLexicalStore  # noqa: E402
from research_observatory_core.ports.credential_store import SecretKind, SecretRecord, SecretReference  # noqa: E402
from research_observatory_core.ports.derivative_keys import DerivativeKeyScope, DerivativePurpose  # noqa: E402

from tests.database_key_fixtures import InMemoryDatabaseKeyProvider  # noqa: E402
from tests.search.test_derivative_keys import MemoryVault  # noqa: E402
from tests.search.test_protected_lexical_store import row  # noqa: E402

payload = json.loads(sys.stdin.buffer.read(32769))
scope = DerivativeKeyScope(**dict(payload["scope"], purpose=DerivativePurpose(payload["scope"]["purpose"])))
canonical = InMemoryDatabaseKeyProvider()
canonical._active[scope.project_id] = (scope.canonical_key_version, bytes(payload["canonicalMaterial"]))
vault = MemoryVault()
for value in payload["records"]:
    reference = SecretReference(**dict(value["reference"], kind=SecretKind(value["reference"]["kind"])))
    vault.values[reference] = (SecretRecord(value["version"], reference.kind), bytes(value["material"]))
keys = VaultDerivativeKeyProvider(vault, profile_id="fixture", database_keys=canonical)
project = Path(payload["root"])
assert project.resolve().is_relative_to(Path(os.environ["TMPDIR"]).resolve())
store = ProtectedLexicalStore(project, scope, keys)
store.apply((replace(row(), title="synthetic crash replacement"),), (), expected_checkpoint=1, checkpoint=2)
# Deliberately bypass Python/SQLCipher/guard finalizers. Parent owns this child
# and verifies exact exit, encrypted populated WAL and recovered results.
os._exit(73)
