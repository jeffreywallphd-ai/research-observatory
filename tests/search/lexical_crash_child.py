"""Owned crash producer with synthetic data and fixture keys delivered by stdin."""

import json
import os
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core import lexical_index_io, lexical_index_store, storage  # noqa: E402
from research_observatory_core.derivative_keys import VaultDerivativeKeyProvider  # noqa: E402
from research_observatory_core.lexical_catalog_repository import SqliteIndexCatalog  # noqa: E402
from research_observatory_core.lexical_index_store import ProtectedLexicalStore  # noqa: E402
from research_observatory_core.ports.corpus import CorpusActor  # noqa: E402
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
if "bootstrapPhase" in payload:
    storage.configure_protected_database_provider(canonical)
    catalog = SqliteIndexCatalog(
        project / "state/project.sqlite3",
        scope.project_id,
        keys,
        actor=lambda: CorpusActor(**payload["actor"]),
        guard=lambda action: action(),
    )
    lease = catalog.acquire(scope.generation_id)

    def interrupt(name):
        if name == payload["bootstrapPhase"]:
            os._exit(73)

    lexical_index_io._bootstrap_step = interrupt
    lexical_index_store._bootstrap_step = interrupt
    with ProtectedLexicalStore(
        project, scope, keys, create=True, _bootstrap=lambda identities: catalog.bind_bootstrap(lease, identities)
    ) as store:
        interrupt("empty-schema-initialized")
        catalog.acknowledge_initialization(lease, store.file_identities)
        interrupt("initialization-acknowledged")
    raise AssertionError("owned child did not reach its requested interruption")
store = ProtectedLexicalStore(project, scope, keys)
store.apply((replace(row(), title="synthetic crash replacement"),), (), expected_checkpoint=1, checkpoint=2)
# Deliberately bypass Python/SQLCipher/guard finalizers. Parent owns this child
# and verifies exact exit, encrypted populated WAL and recovered results.
os._exit(73)
