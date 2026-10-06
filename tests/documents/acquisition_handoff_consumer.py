"""Tiny downstream consumer of portable acquisition and protected-read ports."""

import hashlib

from research_observatory_core.ports.acquisition import AcquisitionRepositoryPort
from research_observatory_core.ports.corpus import CorpusActor
from research_observatory_core.ports.document_attachments import DocumentAttachment
from research_observatory_core.ports.object_store import ObjectStore


def consume_attached_source(
    repository: AcquisitionRepositoryPort,
    objects: ObjectStore,
    attachment: DocumentAttachment,
    actor: CorpusActor,
) -> bytes:
    source = repository.source_for_revision(attachment.document_revision_id, actor=actor)
    if source is None:
        raise ValueError("missing acquisition provenance")
    location, receipt = source
    if receipt.location_id != location.location_id or receipt.actual_sha256 != attachment.object_sha256:
        raise ValueError("mismatched acquisition provenance")
    with objects.open_document_attachment(
        attachment.attachment_id, attachment.document_revision_id, actor=actor
    ) as reader:
        body = reader.read()
    if hashlib.sha256(body).hexdigest() != receipt.actual_sha256 or len(body) != receipt.expanded_bytes:
        raise ValueError("mismatched original content")
    return body
