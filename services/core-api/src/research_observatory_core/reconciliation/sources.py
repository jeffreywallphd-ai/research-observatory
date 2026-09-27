"""Pure projections from authenticated retained source records; no grants or I/O."""

import hashlib
import json

from ..connectors.contracts import ConnectorRecord
from ..ingestion.import_drafts import ImportRights
from ..ingestion.reference_imports import ImportRecord
from ..ports.import_commits import ImportManifestMember
from .contracts import ReconciliationProblem, ScholarlyField, SourceAddress, SourceAssertion
from .exact import IdentifierAssertion, SourceOrigin


def import_assertion(
    *, project_id: str, address: SourceAddress, record: ImportRecord, member: ImportManifestMember, rights: ImportRights
) -> SourceAssertion:
    if (
        address.ordinal != record.ordinal
        or address.record_key != record.record_key
        or member.record_key != record.record_key
        or member.source_record_revision_id is None
        or not member.decision.included
    ):
        raise ReconciliationProblem("reconciliation-import-source-invalid")
    identifiers: list[IdentifierAssertion] = []
    fields: list[ScholarlyField] = []
    corrections = {item.name for item in member.decision.fields if item.origin == "correction"}
    mapped_dois = {
        item.source_field_index for item in member.decision.fields if item.name == "doi" and item.origin != "correction"
    }
    for index, raw in enumerate(record.fields):
        name = raw.name.casefold()
        scheme = {
            "do": "doi",
            "doi": "doi",
            "pmid": "pmid",
            "arxiv": "arxiv",
            "isbn": "isbn",
            "orcid": "orcid",
            "url": "url",
        }.get(name)
        if index in mapped_dois:
            scheme = "doi"
        if scheme is None:
            continue
        identifiers.append(
            IdentifierAssertion(
                scheme=scheme,
                observed=raw.raw_value,
                role="person"
                if scheme == "orcid"
                else "container"
                if scheme == "isbn"
                else "location"
                if scheme == "url"
                else "subject",
                active_for_matching=scheme not in corrections,
                source_selector=f"fields.{index}",
                source_encoding="json-string"
                if record.format_name == "csl-json"
                else "bibtex-literal"
                if record.format_name == "bibtex"
                else "text",
            )
        )
    for index, item in enumerate(member.decision.fields):
        origin: SourceOrigin = "correction" if item.origin == "correction" else "observed"
        fields.append(
            ScholarlyField(
                name=item.name, observed=item.value, origin=origin, source_selector=f"decision.fields.{index}"
            )
        )
        if item.name == "doi" and item.origin == "correction":
            identifiers.append(
                IdentifierAssertion(
                    scheme="doi", observed=item.value, origin="correction", source_selector=f"decision.fields.{index}"
                )
            )
        if item.name == "title":
            identifiers.append(
                IdentifierAssertion(
                    scheme="title", observed=item.value, origin=origin, source_selector=f"decision.fields.{index}"
                )
            )
    return SourceAssertion(
        project_id=project_id,
        address=address,
        source_revision_id=member.source_record_revision_id,
        provider="local-import",
        identifiers=tuple(identifiers),
        fields=tuple(fields),
        rights=rights,
        source_sha256=record.raw_sha256,
    )


def connector_assertion(
    *, project_id: str, address: SourceAddress, record: ConnectorRecord, rights: ImportRights
) -> SourceAssertion:
    def identifier(scheme, value, selector):
        if not isinstance(value, str | int) or isinstance(value, bool):
            raise ReconciliationProblem("reconciliation-connector-identifier-invalid")
        return IdentifierAssertion(
            scheme="s2-paper" if scheme == "semantic-scholar" else scheme, observed=str(value), source_selector=selector
        )

    identifiers = [identifier(record.raw_identifier.scheme, record.raw_identifier.value, "raw-identifier")]
    fields: list[ScholarlyField] = []
    mapping = {
        "doi": "doi",
        "pmid": "pmid",
        "arxiv": "arxiv",
        "openalex": "openalex",
        "corpusid": "s2-corpus",
        "paperid": "s2-paper",
    }
    for index, item in enumerate(record.fields):
        if item.namespace != record.provider_id:
            raise ReconciliationProblem("reconciliation-provider-mismatch")
        try:
            value = json.loads(item.value) if item.encoding == "json" else item.value
        except ValueError:
            raise ReconciliationProblem("reconciliation-connector-field-invalid") from None
        name = item.name.casefold()
        if name in mapping and value is not None:
            identifiers.append(identifier(mapping[name], value, f"fields.{index}"))
        if name in {"ids", "externalids"} and isinstance(value, dict):
            for key, observed in value.items():
                scheme = mapping.get(key.casefold())
                if scheme is not None and observed is not None:
                    identifiers.append(identifier(scheme, observed, f"fields.{index}.{key}"))
        if name.startswith("candidate.") and value is not None:
            candidate = name.removeprefix("candidate.")
            if candidate in {"title", "authors", "year", "venue", "pages", "abstract"}:
                observed = (
                    value if isinstance(value, str) else json.dumps(value, ensure_ascii=True, separators=(",", ":"))
                )
                if observed:
                    fields.append(
                        ScholarlyField(
                            name=candidate, observed=observed, origin="observed", source_selector=f"fields.{index}"
                        )
                    )
                    if candidate == "title":
                        identifiers.append(
                            IdentifierAssertion(scheme="title", observed=observed, source_selector=f"fields.{index}")
                        )
    return SourceAssertion(
        project_id=project_id,
        address=address,
        source_revision_id=address.revision_id,
        provider=record.provider_id,
        identifiers=tuple(identifiers),
        fields=tuple(fields),
        rights=rights,
        source_sha256=hashlib.sha256(record.model_dump_json(by_alias=True).encode()).hexdigest(),
    )
