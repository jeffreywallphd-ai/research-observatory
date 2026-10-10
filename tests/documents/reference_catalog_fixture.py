"""Actual imported members; declared SourceAssertion resolver for focused tests."""

from contextlib import closing

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ports.reconciliation import ReconciliationActor
from research_observatory_core.reconciliation.contracts import ScholarlyField, SourceAddress
from research_observatory_core.reconciliation.exact import IdentifierAssertion
from research_observatory_core.reconciliation_repository import SqliteReconciliationRepository
from research_observatory_core.storage import open_canonical_database


def import_works(corpus, count, *, duplicate=False):
    service_fixture = corpus._fixture.fixture.fixture.fixture.fixture
    # The encrypted document fixture replaced the disposable database after
    # its import worker was bound. Recompose its actual storage admission for
    # the new file identity while preserving the current Native session.
    service_fixture.service._action(
        service_fixture.root,
        lambda binding: setattr(
            binding, "adapters", service_fixture.service._adapters(binding.path, binding.project_id)
        ),
    )
    rows = "title,doi\n" + "".join(
        f"Synthetic reference {i},10.99999/synthetic-{'a' if duplicate else 'extra-' + str(i)}\n" for i in range(count)
    )
    corpus._fixture.prepare_another(raw=rows.encode())
    output = corpus._fixture.publish()
    fixture = corpus._fixture.fixture
    sources = {corpus.address: corpus.source}
    members = fixture.repository.manifest_members(output.revision_id, after=0, limit=100)
    for member in members:
        if not member.decision.included:
            continue
        address = SourceAddress(
            kind="import-member",
            context_id=fixture.inputs.preview.preview_id,
            revision_id=output.revision_id,
            ordinal=member.ordinal,
            record_key=member.record_key,
        )
        with closing(open_canonical_database(corpus.database, expected_project_id=corpus.project)) as connection:
            raw = connection.execute(
                (
                    "SELECT raw_sha256 FROM import_manifest_members WHERE project_id=? AND "
                    "manifest_revision_id=? AND ordinal=?"
                ),
                (corpus.project, output.revision_id, member.ordinal),
            ).fetchone()[0]
        doi = "10.99999/synthetic-a" if duplicate else "10.99999/synthetic-extra-" + str(member.ordinal)
        sources[address] = corpus.source.model_copy(
            update={
                "address": address,
                "source_revision_id": member.source_record_revision_id,
                "source_sha256": raw,
                "identifiers": (IdentifierAssertion(scheme="doi", observed=doi),),
                "fields": tuple(
                    ScholarlyField(
                        name=name, observed=value, origin="observed", source_selector=f"synthetic-field-{index}"
                    )
                    for index, (name, value) in enumerate(
                        (
                            ("doi", doi),
                            ("title", "Synthetic reference alpha"),
                            ("author", "Synthetic One"),
                            ("author", "Synthetic Two"),
                        )
                    )
                ),
            }
        )

    def resolver(address):
        return sources[address]

    results = [
        SqliteReconciliationRepository(corpus.database, corpus.project).reconcile(
            address,
            command_id=new_uuid_v7(),
            actor=ReconciliationActor(new_uuid_v7(), "a" * 32, corpus.actor.occurred_at, "b" * 64, "c" * 64),
            resolve=resolver,
        )
        for address in sources
        if address != corpus.address
    ]
    return resolver, results
