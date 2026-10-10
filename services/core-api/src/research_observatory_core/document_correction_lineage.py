"""Bounded, detached lineage derived from authenticated correction replay.

This internal value is never deserialized from a client or used as authority.
Adapters authenticate each immutable base/patch before advancing it. Native and
Docling consumers still authenticate the literal original machine structure.
"""

from __future__ import annotations

from dataclasses import dataclass

from .document_corrections import (
    MAX_CORRECTION_ITEMS,
    CorrectionInheritance,
    CorrectionLabel,
    CorrectionNodeOrigin,
    HumanReferenceMatch,
    apply_correction,
)
from .document_revisions import AcceptedDocumentRevision, DocumentRevisionProblem, canonicalize_structure
from .parsing.contracts import CodepointRange
from .parsing.normalization import normalize_text


@dataclass(frozen=True, slots=True)
class CorrectionSourceLineage:
    machine_revision: AcceptedDocumentRevision
    revision: AcceptedDocumentRevision
    origins: tuple[CorrectionNodeOrigin, ...]
    inheritance: CorrectionInheritance
    generation: int
    excluded_origins: tuple[CorrectionNodeOrigin, ...] = ()

    @classmethod
    def machine(cls, accepted):
        accepted = AcceptedDocumentRevision.model_validate(accepted)
        if len(accepted.structure.nodes) > MAX_CORRECTION_ITEMS:
            raise DocumentRevisionProblem("document-correction-lineage-limit")
        return cls(
            accepted,
            accepted,
            tuple(
                CorrectionNodeOrigin(
                    result_node_id=n.node_id,
                    source_node_id=n.node_id,
                    result_range=n.text.normalized_range if n.text else None,
                    source_range=n.text.normalized_range if n.text else None,
                )
                for n in accepted.structure.nodes
            ),
            CorrectionInheritance(
                base_revision_id=accepted.revision_id,
                expected_structure_sha256=accepted.structure_sha256,
                labels=(),
                excluded_node_ids=(),
                reference_matches=(),
            ),
            0,
        )

    def validate(self, accepted):
        if (accepted.revision_id, accepted.structure_sha256, accepted.structure) != (
            self.revision.revision_id,
            self.revision.structure_sha256,
            self.revision.structure,
        ) or (accepted.result, accepted.structure.binding, accepted.structure.raw_artifacts) != (
            self.machine_revision.result,
            self.machine_revision.structure.binding,
            self.machine_revision.structure.raw_artifacts,
        ):
            raise DocumentRevisionProblem("document-correction-lineage-invalid")
        return self

    def preview(self, base, patch, *, cancelled=lambda: False):
        self.validate(base)
        result = apply_correction(base, patch, inherited=self.inheritance, cancelled=cancelled)
        structure, mapping = canonicalize_structure(result.ir)
        return structure, mapping, result

    def advance(self, accepted, result):
        if self.generation >= 32 or accepted.previous_revision_id != self.revision.revision_id:
            raise DocumentRevisionProblem("document-correction-lineage-limit")
        ids = iter(m.canonical_id for m in accepted.element_identities)
        structure, mapping = canonicalize_structure(result.ir, identity_factory=lambda: next(ids))
        if (accepted.structure, accepted.element_identities, accepted.result) != (
            structure,
            mapping,
            self.revision.result,
        ):
            raise DocumentRevisionProblem("document-correction-lineage-invalid")
        keys = {m.staged_id: m.canonical_id for m in mapping if m.role == "node"}
        references = {m.staged_id: m.canonical_id for m in mapping if m.role == "reference"}
        prior: dict[str, list[CorrectionNodeOrigin]] = {}
        for item in self.origins:
            prior.setdefault(item.result_node_id, []).append(item)
        origins: list[CorrectionNodeOrigin] = []
        for item in result.origins:
            for old in prior.get(item.source_node_id, ()):
                if len(origins) >= MAX_CORRECTION_ITEMS:
                    raise DocumentRevisionProblem("document-correction-lineage-limit")
                if item.result_range is None:
                    if item.source_range is not None or old.result_range is not None or old.source_range is not None:
                        raise DocumentRevisionProblem("document-correction-lineage-invalid")
                    origins.append(
                        CorrectionNodeOrigin(
                            result_node_id=keys[item.result_node_id],
                            source_node_id=old.source_node_id,
                            result_range=None,
                            source_range=None,
                        )
                    )
                    continue
                if old.result_range is None or old.source_range is None or item.source_range is None:
                    raise DocumentRevisionProblem("document-correction-lineage-invalid")
                if item.source_range.start == item.source_range.end == old.result_range.start == old.result_range.end:
                    origins.append(
                        CorrectionNodeOrigin(
                            result_node_id=keys[item.result_node_id],
                            source_node_id=old.source_node_id,
                            result_range=item.result_range,
                            source_range=old.source_range,
                        )
                    )
                    continue
                low, high = (
                    max(item.source_range.start, old.result_range.start),
                    min(item.source_range.end, old.result_range.end),
                )
                if low < high:
                    current_delta = item.result_range.start - item.source_range.start
                    source_delta = old.source_range.start - old.result_range.start
                    origins.append(
                        CorrectionNodeOrigin(
                            result_node_id=keys[item.result_node_id],
                            source_node_id=old.source_node_id,
                            result_range=CodepointRange(start=low + current_delta, end=high + current_delta),
                            source_range=CodepointRange(start=low + source_delta, end=high + source_delta),
                        )
                    )
        by_node: dict[str, list[CorrectionNodeOrigin]] = {}
        for item in origins:
            by_node.setdefault(item.result_node_id, []).append(item)
        for node in accepted.structure.nodes:
            values = by_node.get(node.node_id, [])
            if not values:
                raise DocumentRevisionProblem("document-correction-lineage-invalid")
            if node.text is not None:
                # Every retained codepoint has exactly one source interval.
                ranges = sorted(
                    (v.result_range.start, v.result_range.end) for v in values if v.result_range is not None
                )
                at = node.text.normalized_range.start
                for low, high in ranges:
                    if low != at:
                        raise DocumentRevisionProblem("document-correction-lineage-invalid")
                    at = high
                if at != node.text.normalized_range.end:
                    raise DocumentRevisionProblem("document-correction-lineage-invalid")
        inherited = CorrectionInheritance(
            base_revision_id=accepted.revision_id,
            expected_structure_sha256=accepted.structure_sha256,
            labels=tuple(CorrectionLabel(node_id=keys[label.node_id], label=label.label) for label in result.labels),
            excluded_node_ids=result.excluded_node_ids,
            reference_matches=tuple(
                HumanReferenceMatch(
                    reference_id=references[m.reference_id],
                    work_id=m.work_id,
                    work_revision_id=m.work_revision_id,
                    basis="human-accepted",
                )
                for m in result.reference_matches
            ),
        )
        excluded = list(self.excluded_origins)
        newly_excluded = set(result.excluded_node_ids) - set(self.inheritance.excluded_node_ids)
        for node_id in newly_excluded:
            excluded.extend(prior.get(node_id, ()))
        if len(excluded) > MAX_CORRECTION_ITEMS:
            raise DocumentRevisionProblem("document-correction-lineage-limit")
        return type(self)(
            self.machine_revision, accepted, tuple(origins), inherited, self.generation + 1, tuple(excluded)
        )

    def excluded_native_intervals(self, native, *, checkpoint=lambda: None):
        nodes = {n.node_id: n for n in self.machine_revision.structure.nodes}
        projections = {p.projection_id: p for p in self.machine_revision.structure.text_projections}
        intervals: list[tuple[int, int]] = []
        for item in self.excluded_origins:
            checkpoint()
            if item.source_range is None:
                continue
            node = nodes[item.source_node_id]
            if node.text is None:
                raise DocumentRevisionProblem("document-correction-lineage-invalid")
            mapping = normalize_text(
                projections[node.text.projection_id].raw_text, cancelled=lambda: bool(checkpoint())
            )
            origin = native.elements[node.order].text_start
            intervals.extend(
                (origin + a, origin + b)
                for a, b in mapping.raw_ranges_for(item.source_range.start, item.source_range.end)
            )
        return tuple(intervals)

    def excludes_span(self, node_id, span, *, checkpoint=lambda: None):
        """Without a native coordinate receipt, deny ambiguous ancestor overlap.

        A removed descendant must not be quoted through a retained ancestor.
        Distinct unaffected blocks and exact non-overlapping same-node ranges
        remain available. No string-search offset inference is used.
        """
        if span is None or not self.excluded_origins:
            return False
        nodes = {n.node_id: n for n in self.machine_revision.structure.nodes}
        for item in self.origins:
            checkpoint()
            if item.result_node_id != node_id or item.result_range is None:
                continue
            if item.source_range is None:
                raise DocumentRevisionProblem("document-correction-lineage-invalid")
            low = max(item.result_range.start, span.normalized_range.start)
            high = min(item.result_range.end, span.normalized_range.end)
            if low >= high:
                continue
            delta = item.source_range.start - item.result_range.start
            for excluded in self.excluded_origins:
                checkpoint()
                if excluded.source_range is None:
                    continue
                if item.source_node_id == excluded.source_node_id:
                    if low + delta < excluded.source_range.end and high + delta > excluded.source_range.start:
                        return True
                else:
                    ancestor = nodes[excluded.source_node_id].parent_id
                    while ancestor is not None:
                        checkpoint()
                        if ancestor == item.source_node_id:
                            return True
                        ancestor = nodes[ancestor].parent_id
        return False

    def native_index(self, node_id):
        identities = {o.source_node_id for o in self.origins if o.result_node_id == node_id}
        if len(identities) != 1:
            return None
        identity = next(iter(identities))
        return next((n.order for n in self.machine_revision.structure.nodes if n.node_id == identity), None)

    def retained_nodes(self, source_id):
        return tuple(dict.fromkeys(o.result_node_id for o in self.origins if o.source_node_id == source_id))

    def source_intervals(self, node_id, span, native, *, checkpoint=lambda: None):
        checkpoint()
        node = next((n for n in self.revision.structure.nodes if n.node_id == node_id), None)
        if (
            node is None
            or node.text is None
            or span.projection_id != node.text.projection_id
            or not (
                node.text.normalized_range.start
                <= span.normalized_range.start
                <= span.normalized_range.end
                <= node.text.normalized_range.end
            )
        ):
            raise DocumentRevisionProblem("document-correction-lineage-invalid")
        nodes = {n.node_id: n for n in self.machine_revision.structure.nodes}
        projections = {p.projection_id: p for p in self.machine_revision.structure.text_projections}
        intervals: list[tuple[int, int]] = []
        for item in self.origins:
            checkpoint()
            if item.result_node_id != node_id or item.result_range is None or item.source_range is None:
                continue
            low, high = (
                max(span.normalized_range.start, item.result_range.start),
                min(span.normalized_range.end, item.result_range.end),
            )
            if low >= high:
                continue
            source_node = nodes[item.source_node_id]
            if source_node.text is None:
                raise DocumentRevisionProblem("document-correction-lineage-invalid")
            source = projections[source_node.text.projection_id]
            delta = item.source_range.start - item.result_range.start
            origin = native.elements[source_node.order].text_start
            intervals.extend(
                (origin + a, origin + b)
                for a, b in normalize_text(source.raw_text, cancelled=lambda: bool(checkpoint())).raw_ranges_for(
                    low + delta, high + delta
                )
            )
        return tuple(intervals)

    def current_range(self, node_id, absolute_ranges, native, *, checkpoint=lambda: None):
        """Map an exact original interval to one contiguous current range.

        Cross-normalization or removed/split context stays unavailable.
        """
        nodes = {n.node_id: n for n in self.machine_revision.structure.nodes}
        projections = {p.projection_id: p for p in self.machine_revision.structure.text_projections}
        found = []
        for item in self.origins:
            checkpoint()
            if item.result_node_id != node_id or item.result_range is None or item.source_range is None:
                continue
            node = nodes[item.source_node_id]
            if node.text is None:
                raise DocumentRevisionProblem("document-correction-lineage-invalid")
            projection = projections[node.text.projection_id]
            mapping = normalize_text(projection.raw_text, cancelled=lambda: bool(checkpoint()))
            origin = native.elements[node.order].text_start
            for low, high in absolute_ranges:
                hits = []
                for i in range(item.source_range.start, item.source_range.end):
                    if i % 256 == 0:
                        checkpoint()
                    if any(a + origin < high and b + origin > low for a, b in mapping.raw_ranges_for(i, i + 1)):
                        hits.append(i)
                if not hits:
                    continue
                a, b = min(hits), max(hits) + 1
                if tuple(mapping.raw_ranges_for(a, b)) != ((low - origin, high - origin),):
                    return None
                delta = item.result_range.start - item.source_range.start
                found.append((a + delta, b + delta))
        if not found:
            return None
        found.sort()
        at = found[0][0]
        start = at
        for a, b in found:
            if a != at:
                return None
            at = b
        return CodepointRange(start=start, end=at)
