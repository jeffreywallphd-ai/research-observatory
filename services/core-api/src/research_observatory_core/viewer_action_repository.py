"""Reader-local rights review and output preparation over the existing rights writer.

No destination, process or OS effect is authorized here. Only the exact otherwise
allowed local-export decision is handed to the private Native action boundary.
"""

import hashlib
import json
from datetime import UTC
from typing import Literal

from . import rights_repository as rights_storage
from .document_attachment_repository import LocalDocumentAttachmentService
from .document_revisions import DocumentRevisionProblem
from .document_viewer_allocations import ViewerOutlineReads, viewer_core_allowance, viewer_revision_reads
from .domain_contracts import is_uuid_v7, new_uuid_v7
from .ports.viewer_actions import (
    ViewerActionPayload,
    ViewerActionRequest,
    ViewerAnnotationOutput,
    ViewerOriginalHandoff,
    ViewerPolicyDecision,
    ViewerQuotationOutput,
    ViewerRightsReviewReceipt,
    ViewerUseDecision,
)
from .rights_policy import RightsPermission, RightsPolicyRevision, RightsRequest, RightsUse

_REVIEWABLE = {"rights-policy-missing", "rights-assertion-missing", "rights-assertion-unknown"}
_MIB = 1024 * 1024


def _sha(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def viewer_authority_sha256(actor):
    return _sha((actor.actor_id, actor.actor_type, actor.intent_revision_id, actor.intent_sha256, actor.policy_sha256))


def viewer_action_uses(action):
    request = ViewerActionRequest.model_fields["action"].annotation
    from pydantic import TypeAdapter

    action = TypeAdapter(request).validate_python(action)
    uses = [RightsUse(action="inspect", purpose="document-analysis", destination_kind="local-project")]
    if action != "open-external-original":
        uses.append(RightsUse(action="derive", purpose="document-analysis", destination_kind="local-project"))
    if action in {"copy-quotation", "print-quotation", "export-quotation"}:
        uses.append(RightsUse(action="quote", purpose="viewer-quotation", destination_kind="local-project"))
    uses.append(RightsUse(action="export", purpose="viewer-" + action, destination_kind="local-export"))
    return tuple(uses)


def _source_ready(decision):
    return decision.code == "allow" or (
        decision.use.destination_kind == "local-export"
        and decision.code == "require-confirmation"
        and decision.reason_code == "rights-further-authority-required"
    )


class ViewerActionRepository:
    def __init__(self, viewer):
        self.viewer, self.revisions = viewer, viewer.revisions
        self.attachments = LocalDocumentAttachmentService(
            self.revisions.database, self.revisions.project, self.revisions.objects
        )
        self.rights = self.attachments._rights

    def _subject(self, connection, metadata, actor):
        self.rights._authority(connection, actor)
        candidate = self.attachments._candidate(connection, metadata.source.candidate_id)
        source = metadata.source
        if (
            candidate.project_id,
            candidate.source_assertion_revision_id,
            candidate.work_id,
            candidate.work_revision_id,
            candidate.version_id,
            candidate.version_revision_id,
            candidate.object_sha256,
            candidate.byte_length,
            candidate.format,
        ) != (
            source.project_id,
            source.source_assertion_revision_id,
            source.work_id,
            source.work_revision_id,
            source.version_id,
            source.version_revision_id,
            source.object_sha256,
            source.byte_length,
            source.format,
        ):
            raise DocumentRevisionProblem("viewer-source-changed")
        subject = candidate.rights_subject
        self.rights._retained_source(connection, subject)
        self.rights._validate_subject_copy(connection, subject)
        return subject

    def _policy_budget(self, connection, metadata, subject, *, command_id=None, publishing=False):
        # Admit before the existing loader deserializes a complete policy. The
        # conservative multiplier covers old/new values and serialization; the
        # frame allowance remains reserved even though this step reads no source.
        row = connection.execute(
            "SELECT LENGTH(CAST(policy_json AS BLOB)) FROM rights_policy_revisions "
            "WHERE project_id=? AND subject_sha256=? ORDER BY revision_number DESC LIMIT 1",
            (self.revisions.project, rights_storage._digest(subject.model_dump(mode="json", by_alias=True))),
        ).fetchone()
        sizes = [int(row[0])] if row else [0]
        if command_id is not None:
            replay = connection.execute(
                "SELECT LENGTH(CAST(policy_json AS BLOB)) FROM rights_policy_revisions "
                "WHERE project_id=? AND command_id=?",
                (self.revisions.project, command_id),
            ).fetchone()
            if replay:
                sizes.append(int(replay[0]))
        charge = max(sizes) * 256 + (8192 * 256 if publishing else 2 * _MIB)
        if max(sizes) > 65536 or charge > viewer_core_allowance(metadata.source.byte_length) - 24 * _MIB:
            raise DocumentRevisionProblem("viewer-resource-limit")

    def _decisions(self, connection, metadata, action, actor):
        subject = self._subject(connection, metadata, actor)
        self._policy_budget(connection, metadata, subject)
        return subject, tuple(
            self.rights.evaluate_with_connection(
                connection, RightsRequest(actor_id=actor.actor_id, subject=subject, use=use), actor=actor
            )
            for use in viewer_action_uses(action)
        )

    def policy(self, selector, *, action, anchor_id=None, direct_transfer=False):
        selection = ViewerActionRequest(selector=selector, action=action, anchor_id=anchor_id)

        def read():
            metadata = self.viewer.describe(selection.selector)
            actor = self.revisions.actor()
            with self.rights._transaction(write=True) as (connection, _):
                subject, decisions = self._decisions(connection, metadata, action, actor)
                blocked = [d for d in decisions if not _source_ready(d)]
                reviewable = bool(blocked) and all(
                    d.code == "unknown" and d.reason_code in _REVIEWABLE for d in blocked
                )
                missing_selection = action != "open-external-original" and (
                    anchor_id is None or selection.selector.normalized_revision_id is None
                )
                state: Literal["ready", "review-required", "denied", "unavailable"]
                if direct_transfer is True:
                    state, reason, reviewable = "denied", "viewer-direct-transfer-disabled", False
                    self.rights._write_use_event(
                        connection,
                        subject=subject,
                        use=decisions[-1].use,
                        policy_revision_id=decisions[-1].policy_revision_id,
                        authority_kind=decisions[-1].authority_kind,
                        source_assertion_sha256=decisions[-1].source_assertion_sha256,
                        code="deny",
                        reason_code=reason,
                        event_kind="denied-attempt",
                        occurred_at=decisions[-1].evaluated_at,
                        actor=actor,
                    )
                elif blocked:
                    first = next((d for d in blocked if d.code == "deny"), blocked[0])
                    state = "denied" if first.code == "deny" else "review-required" if reviewable else "unavailable"
                    reason = first.reason_code
                elif missing_selection:
                    state, reason = "unavailable", "viewer-selection-required"
                    self.rights._write_use_event(
                        connection,
                        subject=subject,
                        use=decisions[-1].use,
                        policy_revision_id=decisions[-1].policy_revision_id,
                        authority_kind=decisions[-1].authority_kind,
                        source_assertion_sha256=decisions[-1].source_assertion_sha256,
                        code="deny",
                        reason_code=reason,
                        event_kind="denied-attempt",
                        occurred_at=decisions[-1].evaluated_at,
                        actor=actor,
                    )
                else:
                    state, reason = "ready", "viewer-native-destination-required"
                result = ViewerPolicyDecision(
                    metadata=metadata,
                    action=action,
                    anchor_id=anchor_id,
                    policy_revision_id=decisions[-1].policy_revision_id,
                    state=state,
                    reason_code=reason,
                    can_review=reviewable,
                    requirements=tuple(
                        ViewerUseDecision(use=d.use, code=d.code, reason_code=d.reason_code) for d in decisions
                    ),
                )
            if self.viewer.describe(selection.selector) != metadata or viewer_authority_sha256(
                self.revisions.actor()
            ) != viewer_authority_sha256(actor):
                raise DocumentRevisionProblem("viewer-authority-changed")
            return result

        return self.revisions._bounded(read)

    def review(self, selector, *, action, expected_policy_revision_id, command_id, confirmed):
        selection = ViewerActionRequest(selector=selector, action=action)
        if (
            confirmed is not True
            or not is_uuid_v7(command_id)
            or (expected_policy_revision_id is not None and not is_uuid_v7(expected_policy_revision_id))
        ):
            raise DocumentRevisionProblem("viewer-rights-confirmation-required")

        def publish():
            metadata = self.viewer.describe(selection.selector)
            actor = self.revisions.actor()
            fingerprint = _sha(
                {
                    "kind": "viewer-explicit-permitted-use-review-v1",
                    "metadata": metadata.model_dump(mode="json", by_alias=True),
                    "action": action,
                    "expectedPredecessor": expected_policy_revision_id,
                    "authority": viewer_authority_sha256(actor),
                    "confirmed": True,
                }
            )
            # Connector retention may acquire its own protected object owner.
            # Resolve it before the canonical writer, then revalidate the exact
            # retained source under the writer that publishes the policy.
            with self.rights._transaction(write=False) as (connection, _aggregates):
                retained_subject = self._subject(connection, metadata, actor)
            connector = self.rights._resolve_connector_record(retained_subject)
            outcome = None
            with self.rights._transaction(write=True) as (connection, aggregates):
                subject = self._subject(connection, metadata, actor)
                if subject != retained_subject:
                    raise DocumentRevisionProblem("viewer-source-changed")
                self._policy_budget(connection, metadata, subject, command_id=command_id, publishing=True)
                self.rights._actor(actor, command_id=command_id, command_sha256=fingerprint)
                row = connection.execute(
                    "SELECT revision_id,command_sha256,actor_id FROM rights_policy_revisions "
                    "WHERE project_id=? AND command_id=?",
                    (self.revisions.project, command_id),
                ).fetchone()
                if row:
                    if row[1] != fingerprint or row[2] != actor.actor_id:
                        raise DocumentRevisionProblem("viewer-rights-command-conflict")
                    stored = self.rights._load_revision(connection, str(row[0]))
                    if stored.subject != subject or stored.predecessor_revision_id != expected_policy_revision_id:
                        raise DocumentRevisionProblem("viewer-rights-command-conflict")
                    policy = self.rights._replay(connection, stored, command_id, fingerprint, actor)
                    if policy is None:
                        raise DocumentRevisionProblem("viewer-rights-command-conflict")
                    self.rights._validate_policy_evidence(
                        policy, actor, self.rights._retained_source(connection, subject)
                    )
                    outcome = policy
                else:
                    current = self.rights.current_with_connection(connection, subject)
                    if (current.revision_id if current else None) != expected_policy_revision_id:
                        raise DocumentRevisionProblem("viewer-rights-predecessor-stale")
                    _, decisions = self._decisions(connection, metadata, action, actor)
                    missing = tuple(d for d in decisions if not _source_ready(d))
                    if missing and all(d.code == "unknown" and d.reason_code in _REVIEWABLE for d in missing):
                        # Preserve all unrelated exact assertions. Remove only
                        # matching unknown assertions explicitly reviewed here.
                        reviewed_uses = tuple(d.use for d in missing)
                        preserved = (
                            tuple(
                                p
                                for p in current.permissions
                                if not (
                                    p.use in reviewed_uses
                                    and p.value == "unknown"
                                    and p.grantee_actor_id in (None, actor.actor_id)
                                )
                            )
                            if current
                            else ()
                        )
                        clock = rights_storage._utcnow()
                        if clock.tzinfo is None or clock.utcoffset() is None:
                            raise DocumentRevisionProblem("viewer-rights-clock-unavailable")
                        now = clock.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
                        added = tuple(
                            RightsPermission(
                                assertion_id=new_uuid_v7(),
                                subject=subject,
                                use=use,
                                value="permitted",
                                basis="researcher-confirmed",
                                confidence="confirmed",
                                asserted_by_actor_id=actor.actor_id,
                                grantee_actor_id=actor.actor_id,
                                evidence_revision_ids=(subject.source_assertion_revision_id,),
                                license_observation_revision_id=None,
                                entitlement_revision_id=None,
                                recorded_at=now,
                                expires_at=None,
                            )
                            for use in reviewed_uses
                        )
                        policy = RightsPolicyRevision(
                            revision_id=new_uuid_v7(),
                            predecessor_revision_id=expected_policy_revision_id,
                            subject=subject,
                            source_observation=current.source_observation if current else None,
                            permissions=(*preserved, *added),
                        )
                        outcome = self.rights._publish_with_connection(
                            connection, aggregates, policy, command_id, fingerprint, actor, connector
                        )
                    # Return normally on denied consent so its evaluated-use
                    # audit commits. Raising inside would roll it back.
            if outcome is None:
                raise DocumentRevisionProblem("viewer-rights-review-unavailable")
            if self.viewer.describe(selection.selector) != metadata or viewer_authority_sha256(
                self.revisions.actor()
            ) != viewer_authority_sha256(actor):
                raise DocumentRevisionProblem("viewer-authority-changed")
            return ViewerRightsReviewReceipt(metadata=metadata, action=action, policy_revision_id=outcome.revision_id)

        return self.revisions._bounded(publish)

    def payload(self, selector, *, action, anchor_id, expected_policy_revision_id, expected_authority_sha256=None):
        selection = ViewerActionRequest(selector=selector, action=action, anchor_id=anchor_id)

        def read():
            before = self.policy(selection.selector, action=action, anchor_id=anchor_id)
            actor = self.revisions.actor()
            principal = viewer_authority_sha256(actor)
            if (
                before.state != "ready"
                or before.policy_revision_id != expected_policy_revision_id
                or (expected_authority_sha256 is not None and principal != expected_authority_sha256)
            ):
                raise DocumentRevisionProblem("viewer-action-denied")
            content = {
                "schemaVersion": "1.0",
                "action": action,
                "source": before.metadata.source.model_dump(mode="json", by_alias=True),
                "normalizedRevisionId": before.metadata.normalized_revision_id,
                "policyRevisionId": before.policy_revision_id,
                "scholarlyVerification": "unverified",
                "policyBasis": [item.model_dump(mode="json", by_alias=True) for item in before.requirements],
            }
            anchor_revision = None
            if action in {"copy-quotation", "print-quotation", "export-quotation"}:
                resolved = self.viewer.resolve_anchor(
                    selection.selector, anchor_id=anchor_id, _retained_allowance=2 * _MIB
                )
                target = resolved.target
                if target is None or target.quote is None or resolved.source != before.metadata.source:
                    raise DocumentRevisionProblem("viewer-quotation-unavailable")
                anchor_revision = resolved.anchor_revision_id
                content.update(
                    {
                        "text": target.quote.exact,
                        "anchorId": resolved.anchor_id,
                        "anchorRevisionId": anchor_revision,
                        "textPosition": target.text_position.model_dump(mode="json", by_alias=True),
                        "citationMetadata": resolved.metadata.model_dump(mode="json", by_alias=True),
                    }
                )
            elif action == "export-annotation":
                bounded = viewer_revision_reads(self.revisions, before.metadata.source.byte_length)
                bounded.objects.remaining -= 2 * _MIB
                record = ViewerOutlineReads(bounded).read(anchor_id)
                target = record.target
                if (
                    target.source != before.metadata.source
                    or target.revision_id != selection.selector.normalized_revision_id
                ):
                    raise DocumentRevisionProblem("viewer-source-changed")
                anchor_revision = record.anchor_revision_id
                content.update(
                    {
                        "anchorId": record.anchor_id,
                        "anchorRevisionId": anchor_revision,
                        "nodeId": target.node_id,
                        "nodeKind": target.node_kind,
                        "textPosition": target.text_position.model_dump(mode="json", by_alias=True)
                        if target.text_position
                        else None,
                        "pageRegion": target.page_region.model_dump(mode="json", by_alias=True)
                        if target.page_region
                        else None,
                        "confidence": target.confidence.model_dump(mode="json", by_alias=True),
                        "coordinatesState": target.coordinates_state,
                    }
                )
            after = self.policy(selection.selector, action=action, anchor_id=anchor_id)
            if after != before or viewer_authority_sha256(self.revisions.actor()) != principal:
                raise DocumentRevisionProblem("viewer-authority-changed")
            output_type = (
                ViewerOriginalHandoff
                if action == "open-external-original"
                else (ViewerAnnotationOutput if action == "export-annotation" else ViewerQuotationOutput)
            )
            output = output_type.model_validate(content)
            text = json.dumps(
                output.model_dump(mode="json", by_alias=True), ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            if len(text.encode("utf-8")) > 65536:
                raise DocumentRevisionProblem("viewer-resource-limit")
            return ViewerActionPayload(
                metadata=before.metadata,
                action=action,
                anchor_id=anchor_id,
                anchor_revision_id=anchor_revision,
                policy_revision_id=before.policy_revision_id,
                authority_sha256=principal,
                content_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                content_utf8=text,
            )

        return self.revisions._bounded(read)
