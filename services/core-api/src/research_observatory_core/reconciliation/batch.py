"""Portable authority for one bounded inventory snapshot and duplicate run."""

from dataclasses import asdict
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ..ingestion.import_drafts import Digest, DraftValue, Identity, ProjectIdentity
from ..ingestion.preview_workflow import Fingerprint, PreviewIntentContext, ResumeEpoch, fingerprint
from ..ports.workflow_executor import WorkflowAcceptedBoundary, WorkflowAcceptedSnapshot
from .candidates import ALGORITHM, DEFAULT_CONFIG, FEATURE_VERSION
from .identifiers import NORMALIZER_VERSION

SOURCE_ACTIVITIES = ("local-import-commit", "scholarly-connector-page")
BATCH_ACTIVITY = "scholarly-reconciliation-batch"
# Counts include excluded rows and authorization closure. Exhaustion is a failed
# bounded run, never a claim that the remaining project inventory is empty.
MAX_INVENTORY_JOBS = 10000
MAX_SCANNED_ROWS = 250000
MAX_AUTHORIZED_SOURCES = 20000
MAX_AUTHORIZED_BYTES = 64 * 1024 * 1024
MAX_CANDIDATE_BYTES = 64 * 1024 * 1024


class InventoryBoundary(DraftValue):
    segment_key: Literal["rfc8785.sha256.v1", "rfc8785.sha256.v2"]
    sequence: Annotated[int, Field(strict=True, ge=1, le=9007199254740991)]
    checkpoint_id: Identity
    chain_sha256: Fingerprint


class InventorySnapshot(DraftValue):
    project_id: ProjectIdentity
    activity_types: tuple[Literal["local-import-commit", "scholarly-connector-page"], ...]
    boundaries: Annotated[tuple[InventoryBoundary, ...], Field(max_length=2)]

    @model_validator(mode="after")
    def exact_scope(self) -> Self:
        if self.activity_types != SOURCE_ACTIVITIES or tuple(item.segment_key for item in self.boundaries) != tuple(
            sorted({item.segment_key for item in self.boundaries})
        ):
            raise ValueError("reconciliation-inventory-scope-invalid")
        return self

    @classmethod
    def from_queue(cls, value: WorkflowAcceptedSnapshot) -> Self:
        return cls.model_validate(asdict(value))

    def queue_snapshot(self) -> WorkflowAcceptedSnapshot:
        return WorkflowAcceptedSnapshot(
            self.project_id,
            self.activity_types,
            tuple(
                WorkflowAcceptedBoundary(item.segment_key, item.sequence, item.checkpoint_id, item.chain_sha256)
                for item in self.boundaries
            ),
        )


class BatchInput(DraftValue):
    schema_version: Literal["1.0"] = "1.0"
    request_id: Identity
    project_id: ProjectIdentity
    actor_id: Identity
    intent: PreviewIntentContext
    policy_sha256: Fingerprint
    session_epoch: ResumeEpoch = Field(repr=False)
    inventory: InventorySnapshot
    algorithm: Literal["scholarly-duplicate-ranking/1.0.0"] = "scholarly-duplicate-ranking/1.0.0"
    feature_version: Literal["scholarly-duplicate-features/1.0.0"] = "scholarly-duplicate-features/1.0.0"
    identifier_normalizer: str = NORMALIZER_VERSION
    scoring_sha256: Digest = DEFAULT_CONFIG.fingerprint

    @model_validator(mode="after")
    def exact_authority(self) -> Self:
        if (
            self.project_id != self.intent.project_id
            or self.project_id != self.inventory.project_id
            or self.intent.status != "accepted"
            or self.identifier_normalizer != NORMALIZER_VERSION
            or self.scoring_sha256 != DEFAULT_CONFIG.fingerprint
            or self.algorithm != ALGORITHM
            or self.feature_version != FEATURE_VERSION
        ):
            raise ValueError("reconciliation-batch-authority-invalid")
        return self

    @property
    def configuration_id(self) -> str:
        return f"reconciliation-batch.{self.request_id}.{self.session_epoch}"

    @property
    def configuration_version(self) -> str:
        return "1.0.0"

    @property
    def configuration_hash(self) -> str:
        return fingerprint(self.model_dump(mode="json", by_alias=True))

    @property
    def idempotency_key(self) -> str:
        return fingerprint([BATCH_ACTIVITY, self.project_id, self.request_id])

    def policy_reference(self) -> dict[str, str]:
        return {
            "policyId": "scholarly-reconciliation-policy",
            "policyVersion": "1.0.0",
            "policyHash": self.policy_sha256,
        }
