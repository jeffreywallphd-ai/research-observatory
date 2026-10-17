"""Authenticate a typed lexical run's complete bounded-fan-in source lineage."""

import hashlib
import json

from .lexical_index_repository import IndexServiceProblem
from .repositories import _projection_content_sha256
from .search.run_values import SearchInputManifest, SearchRunContent, content_sha256


def _payload_binding(db, project, revision, digest, input_digest, request):
    expected = {
        "search.lexical-node-payload": "sha256:" + digest,
        "search.lexical-input-snapshot": "sha256:" + input_digest,
        "search.current-intent": request.intent.content_hash,
        "search.current-privacy": "sha256:" + request.policy_sha256,
    }
    observed = dict(
        db.execute(
            "SELECT configuration_id,fingerprint FROM material_dependencies "
            "WHERE project_id=? AND output_revision_id=? AND dependency_kind='parameter-set'",
            (project, revision),
        )
    )
    if observed != expected:
        raise IndexServiceProblem("search node parameter provenance is invalid")


def _source_edges(db, aggregates, project, revision, source_ids):
    rows = tuple(
        db.execute(
            "SELECT dependency_revision_id,fingerprint FROM material_dependencies "
            "WHERE project_id=? AND output_revision_id=? AND dependency_kind='source-revision' "
            "AND relation_type='direct' ORDER BY dependency_revision_id",
            (project, revision),
        )
    )
    if tuple(row[0] for row in rows) != source_ids:
        raise IndexServiceProblem("search node source provenance is invalid")
    for source_id, fingerprint in rows:
        source = aggregates.get_revision(source_id)
        if source.project_id != project or _projection_content_sha256(source) != fingerprint:
            raise IndexServiceProblem("search source identity is invalid")


def validate_run_lineage(db, aggregates, revision_id: str, content: SearchRunContent) -> None:
    """No source text is decoded. Every manifest/node is an immutable subtype.

    Exact source edges and parameter hashes authenticate each bounded node;
    depth and duplicate/cycle rejection bind the complete sorted leaf inventory
    to the accepted input identity, independently of mutable search derivatives.
    """
    project = content.project_id
    _payload_binding(db, project, revision_id, content_sha256(content), content.inputs.input_sha256, content.request)
    _source_edges(db, aggregates, project, revision_id, content.source_roots)
    pending: list[tuple[str, int | None, int]] = [(root, None, 0) for root in content.source_roots]
    visited: set[str] = set()
    leaves: set[str] = set()
    root_levels: set[int] = set()
    while pending:
        identity, expected_level, depth = pending.pop()
        if identity in visited or depth > 32:
            raise IndexServiceProblem("search input lineage is invalid")
        visited.add(identity)
        row = db.execute(
            "SELECT manifest_json,payload_sha256,job_id FROM search_input_manifests "
            "WHERE project_id=? AND revision_id=?",
            (project, identity),
        ).fetchone()
        if row is None:
            source = aggregates.get_revision(identity)
            if (
                expected_level not in (None, -1)
                or source.project_id != project
                or source.aggregate_kind not in ("corpus-item", "record", "document")
            ):
                raise IndexServiceProblem("search input leaf is invalid")
            leaves.add(identity)
            if depth == 0:
                root_levels.add(-1)
            continue
        manifest = SearchInputManifest.model_validate_json(row[0])
        if (
            content_sha256(manifest) != row[1]
            or manifest.job_id != content.job_id
            or row[2] != content.job_id
            or manifest.project_id != project
            or manifest.input_sha256 != content.inputs.input_sha256
            or (expected_level is not None and manifest.level != expected_level)
        ):
            raise IndexServiceProblem("search input manifest binding is invalid")
        if depth == 0:
            root_levels.add(manifest.level)
        _payload_binding(db, project, identity, row[1], manifest.input_sha256, content.request)
        _source_edges(db, aggregates, project, identity, manifest.source_revision_ids)
        pending.extend((child, manifest.level - 1, depth + 1) for child in manifest.source_revision_ids)
    digest = hashlib.sha256(
        json.dumps(tuple(sorted(leaves)), sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()
    ).hexdigest()
    if len(root_levels) > 1 or digest != content.inputs.source_set_sha256:
        raise IndexServiceProblem("search complete source inventory is invalid")
