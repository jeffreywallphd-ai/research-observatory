"""Versioned local SQLite profile, schema, connection, and integrity boundary."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
import stat
import threading
from collections.abc import Callable
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import UUID

import sqlcipher3.dbapi2 as sqlcipher  # type: ignore[import-untyped]

from research_observatory_core.migrations.versions.v0002_schema_history import (
    SCHEMA_MIGRATIONS_DDL,
    SCHEMA_MIGRATIONS_TRIGGERS,
)
from research_observatory_core.migrations.versions.v0003_object_envelopes import (
    OBJECT_ENVELOPE_COLUMNS,
    OBJECT_ENVELOPE_TRIGGERS,
)
from research_observatory_core.migrations.versions.v0004_object_envelope_upgrades import (
    OBJECT_ENVELOPE_UPGRADES_DDL,
)
from research_observatory_core.migrations.versions.v0005_object_creation_source import (
    OBJECT_CREATION_SOURCE_COLUMN,
    SCHEMA_METADATA_V5_DDL,
)
from research_observatory_core.ports.database_keys import (
    DatabaseKeyConflict,
    DatabaseKeyLease,
    DatabaseKeyProblem,
    DatabaseKeyProvider,
    validate_database_key_identity,
)

APPLICATION_ID = 0x524F4253  # ASCII "ROBS"
DATABASE_PROFILE = "sqlite-wal-v1"
DATABASE_SCHEMA_VERSION = 25
DOCUMENT_INTAKE_PREDECESSOR_DATABASE_SCHEMA_VERSION = 24
ACQUISITION_PREDECESSOR_DATABASE_SCHEMA_VERSION = 23
ATTACHMENT_OPERATION_PREDECESSOR_DATABASE_SCHEMA_VERSION = 22
DOCUMENT_ATTACHMENT_PREDECESSOR_DATABASE_SCHEMA_VERSION = 21
PLUGIN_GRANT_PREDECESSOR_DATABASE_SCHEMA_VERSION = 20
CORPUS_REPORT_DATABASE_SCHEMA_VERSION = 19
RIGHTS_DATABASE_SCHEMA_VERSION = 18
CORPUS_DATABASE_SCHEMA_VERSION = 17
WORK_VERSION_DATABASE_SCHEMA_VERSION = 16
RECONCILIATION_REVIEW_DATABASE_SCHEMA_VERSION = 15
RECONCILIATION_DATABASE_SCHEMA_VERSION = 14
IMPORT_COMMIT_DATABASE_SCHEMA_VERSION = 13
IMPORT_SUMMARY_DATABASE_SCHEMA_VERSION = 12
IMPORT_PREVIEW_DATABASE_SCHEMA_VERSION = 11
DEPENDENCY_IMPACT_DATABASE_SCHEMA_VERSION = 10
MATERIAL_DEPENDENCY_DATABASE_SCHEMA_VERSION = 9
WORKFLOW_EXECUTOR_DATABASE_SCHEMA_VERSION = 8
PROVENANCE_LEDGER_DATABASE_SCHEMA_VERSION = 7
ACTOR_IDENTITY_DATABASE_SCHEMA_VERSION = 6
OBJECT_CREATION_SOURCE_DATABASE_SCHEMA_VERSION = 5
OBJECT_ENVELOPE_UPGRADE_DATABASE_SCHEMA_VERSION = 4
OBJECT_ENVELOPE_DATABASE_SCHEMA_VERSION = 3
PREVIOUS_DATABASE_SCHEMA_VERSION = 2
OLDEST_DATABASE_SCHEMA_VERSION = 1
BUSY_TIMEOUT_MILLISECONDS = 5_000
WAL_AUTOCHECKPOINT_PAGES = 1_000
MAX_SAFE_INTEGER = 9_007_199_254_740_991
MINIMUM_SQLITE_VERSION = (3, 37, 0)
SQLCIPHER_PROFILE = "sqlcipher-4.12-community-wal-v1"
DEVELOPMENT_PLAINTEXT_PROFILE = "development-plaintext-fixture"
_SQLCIPHER_HEADER = b"SQLite format 3\x00"
_DATABASE_ERRORS = (sqlite3.Error, sqlcipher.Error)

IMPORT_PREVIEW_TABLES = (
    "import_previews",
    "import_source_chunks",
    "import_source_seals",
    "import_parse_attempts",
    "import_parse_records",
    "import_parse_completions",
    "import_draft_revisions",
    "import_record_decisions",
    "import_preview_events",
)
IMPORT_SUMMARY_TABLES = (
    "import_summary_attempts",
    "import_summary_rows",
    "import_summary_groups",
    "import_summary_completions",
)
IMPORT_COMMIT_TABLES = (
    "import_commit_preparations",
    "import_commit_rows",
    "import_source_records",
    "import_manifests",
    "import_manifest_members",
    "import_manifest_seals",
)
RECONCILIATION_TABLES = (
    "reconciliation_assertions",
    "reconciliation_work_revisions",
    "reconciliation_identifier_links",
    "reconciliation_commands",
)
RECONCILIATION_REVIEW_TABLES = (
    "reconciliation_work_states",
    "reconciliation_work_members",
    "reconciliation_work_seals",
    "reconciliation_review_decisions",
    "reconciliation_feature_cache",
    "reconciliation_candidate_sets",
    "reconciliation_candidate_pairs",
    "reconciliation_exact_impacts",
    "reconciliation_impact_continuations",
    "reconciliation_impact_seals",
)
WORK_VERSION_TABLES = (
    "reconciliation_versions",
    "reconciliation_version_sources",
    "reconciliation_version_relations",
    "reconciliation_relation_evidence",
    "reconciliation_version_preferences",
    "reconciliation_version_decisions",
    "reconciliation_version_impacts",
)
CORPUS_REPORT_TABLES = (
    "corpus_report_snapshots",
    "corpus_report_members",
    "corpus_report_paths",
    "corpus_report_sources",
)
CORPUS_SOURCE_PROJECTION_TABLES = (
    "corpus_source_item_heads",
    "corpus_source_totals",
    "corpus_source_overlap_totals",
)
PLUGIN_GRANT_TABLES = ("plugin_grant_events",)
DOCUMENT_ATTACHMENT_TABLES = (
    "document_attachment_candidates",
    "document_attachment_cancellations",
    "document_attachment_assertions",
)
ATTACHMENT_OPERATION_TABLES = ("document_attachment_operations",)
ACQUISITION_TABLES = (
    "acquisition_locations",
    "acquisition_attempts",
    "acquisition_attempt_results",
    "document_acquisition_sources",
)
DOCUMENT_INTAKE_TABLES = (
    "document_intake_jobs",
    "document_intake_results",
    "document_attachment_recoveries",
    "document_access_needs",
)

EXPECTED_TABLES = (
    "schema_metadata",
    "schema_migrations",
    "projects",
    "object_records",
    "object_envelope_upgrades",
    "aggregate_identities",
    "aggregate_revisions",
    "scholarly_records",
    "documents",
    "workflows",
    "workflow_definitions",
    "workflow_authority_snapshots",
    "workflow_queue_jobs",
    "workflow_job_attempts",
    "workflow_attempt_artifacts",
    "workflow_history_events",
    "workflow_checkpoints",
    "workflow_committed_outputs",
    "material_dependency_outputs",
    "material_dependencies",
    "material_dependency_diagnostics",
    "dependency_impact_runs",
    "dependency_impact_decisions",
    "dependency_impact_items",
    "dependency_stale_causes",
    "dependency_impact_audit_events",
    "evidence",
    "ontologies",
    "decisions",
    "provenance_events",
    "provenance_ledger_events",
    "provenance_ledger_entities",
    "provenance_ledger_relations",
    "provenance_ledger_checkpoints",
    "provenance_legacy_bridges",
    "settings",
    "outbox_events",
    *IMPORT_PREVIEW_TABLES,
    *IMPORT_SUMMARY_TABLES,
    *IMPORT_COMMIT_TABLES,
    *RECONCILIATION_TABLES,
    *RECONCILIATION_REVIEW_TABLES,
    *WORK_VERSION_TABLES,
    "corpus_items",
    "corpus_item_states",
    "corpus_discovery_paths",
    "corpus_item_discovery_paths",
    "corpus_decisions",
    "corpus_decision_evidence",
    "corpus_commands",
    "rights_policy_subjects",
    "rights_policy_revisions",
    "rights_policy_rechecks",
    "rights_policy_recheck_scopes",
    "rights_policy_recheck_completions",
    "rights_policy_generic_rechecks",
    "rights_legacy_output_rechecks",
    "rights_use_decisions",
    *CORPUS_REPORT_TABLES,
    *CORPUS_SOURCE_PROJECTION_TABLES,
    *PLUGIN_GRANT_TABLES,
    *DOCUMENT_ATTACHMENT_TABLES,
    *ATTACHMENT_OPERATION_TABLES,
    *ACQUISITION_TABLES,
    *DOCUMENT_INTAKE_TABLES,
)
IMMUTABLE_ROW_TABLES = (
    "schema_metadata",
    "schema_migrations",
    "projects",
    "aggregate_identities",
    "aggregate_revisions",
    "scholarly_records",
    "documents",
    "workflows",
    "workflow_definitions",
    "workflow_authority_snapshots",
    "workflow_history_events",
    "workflow_checkpoints",
    "workflow_committed_outputs",
    "material_dependency_outputs",
    "material_dependencies",
    "material_dependency_diagnostics",
    "dependency_impact_runs",
    "dependency_impact_decisions",
    "dependency_impact_items",
    "dependency_stale_causes",
    "dependency_impact_audit_events",
    "evidence",
    "ontologies",
    "decisions",
    "provenance_events",
    "provenance_ledger_events",
    "provenance_ledger_entities",
    "provenance_ledger_relations",
    "provenance_ledger_checkpoints",
    "provenance_legacy_bridges",
    "settings",
    *IMPORT_PREVIEW_TABLES,
    *IMPORT_SUMMARY_TABLES,
    *IMPORT_COMMIT_TABLES,
    *RECONCILIATION_TABLES,
    *RECONCILIATION_REVIEW_TABLES,
    *WORK_VERSION_TABLES,
    "corpus_items",
    "corpus_item_states",
    "corpus_discovery_paths",
    "corpus_item_discovery_paths",
    "corpus_decisions",
    "corpus_decision_evidence",
    "corpus_commands",
    "rights_policy_subjects",
    "rights_policy_revisions",
    "rights_policy_rechecks",
    "rights_policy_recheck_scopes",
    "rights_policy_recheck_completions",
    "rights_policy_generic_rechecks",
    "rights_legacy_output_rechecks",
    "rights_use_decisions",
    *CORPUS_REPORT_TABLES,
    *PLUGIN_GRANT_TABLES,
    *DOCUMENT_ATTACHMENT_TABLES,
    *ATTACHMENT_OPERATION_TABLES,
    *ACQUISITION_TABLES,
    *DOCUMENT_INTAKE_TABLES,
)
MUTABLE_STATE_TABLES = (
    "object_records",
    "object_envelope_upgrades",
    "outbox_events",
    "workflow_queue_jobs",
    "workflow_job_attempts",
    "workflow_attempt_artifacts",
    *CORPUS_SOURCE_PROJECTION_TABLES,
)
EXPECTED_TRIGGERS = tuple(
    sorted(
        [f"{table}_no_{operation}" for table in IMMUTABLE_ROW_TABLES for operation in ("delete", "update")]
        + [
            "document_intake_job_binding",
            "document_attachment_recovery_binding",
            "object_records_envelope_insert",
            "object_records_envelope_update",
            "provenance_events_bridge_legacy_after_insert",
            "workflow_queue_jobs_identity_immutable",
            "workflow_job_attempts_identity_immutable",
            "workflow_attempt_artifacts_identity_immutable",
            "workflow_attempt_artifacts_disposition_transition",
            "workflow_checkpoint_artifact_authority",
            "import_chunk_membership",
            "import_seal_membership",
            "import_attempt_binding",
            "import_record_membership",
            "import_completion_membership",
            "import_summary_attempt_binding",
            "import_summary_row_membership",
            "import_summary_group_membership",
            "import_summary_completion_membership",
            "import_commit_preparation_binding",
            "import_commit_row_membership",
            "import_source_record_binding",
            "import_manifest_binding",
            "import_manifest_member_binding",
            "import_manifest_seal_binding",
            "reconciliation_work_binding",
            "reconciliation_candidate_pair_binding",
            "reconciliation_state_binding",
            "reconciliation_membership_binding",
            "reconciliation_seal_binding",
            "reconciliation_legacy_history_closed",
            "reconciliation_exact_impact_binding",
            "reconciliation_impact_continuation_binding",
            "reconciliation_version_binding",
            "reconciliation_version_source_binding",
            "reconciliation_relation_binding",
            "reconciliation_relation_evidence_binding",
            "reconciliation_preference_binding",
            "reconciliation_version_impact_binding",
            "reconciliation_version_work_exclusion",
            "reconciliation_version_import_exclusion",
            "reconciliation_version_assertion_exclusion",
            "reconciliation_version_decision_binding",
            "corpus_item_state_work_binding",
            "corpus_discovery_path_predecessor_binding",
            "corpus_decision_chain_binding",
            "corpus_command_result_binding",
            "rights_policy_revision_binding",
            "rights_policy_recheck_binding",
            "rights_policy_recheck_scope_binding",
            "rights_policy_recheck_completion_binding",
            "rights_policy_generic_recheck_binding",
            "rights_legacy_output_recheck_binding",
            "rights_use_decision_binding",
            "document_acquisition_source_binding",
            "corpus_report_snapshot_seal_binding",
            "corpus_report_member_binding",
            "corpus_report_path_binding",
            "corpus_report_source_binding",
            "plugin_grant_revision_binding",
            "plugin_grant_event_binding",
            "document_attachment_assertion_binding",
        ]
    )
)
EXPECTED_INDEXES = (
    "aggregate_revisions_project_kind",
    "outbox_events_dispatch",
    "provenance_events_project_time",
    "provenance_ledger_project_time",
    "provenance_ledger_project_type",
    "provenance_ledger_project_subject",
    "provenance_ledger_project_correlation",
    "provenance_ledger_entity_input",
    "provenance_ledger_entity_output",
    "provenance_ledger_relation_entity",
    "provenance_ledger_relation_related_entity",
    "workflow_queue_dispatch",
    "workflow_queue_lease_expiry",
    "workflow_history_run_sequence",
    "workflow_checkpoint_attempt_sequence",
    "workflow_artifact_job_disposition",
    "material_dependency_by_revision",
    "material_dependency_by_configuration",
    "material_dependency_diagnostic_output",
    "dependency_impact_run_change",
    "dependency_impact_decision_run",
    "dependency_impact_item_sequence",
    "dependency_stale_output",
    "dependency_impact_audit_sequence",
    "import_chunk_object",
    "import_decision_record",
    "import_summary_draft",
    "import_summary_raw",
    "import_summary_doi",
    "import_manifest_source",
    "import_manifest_raw",
    "import_manifest_doi",
    "import_manifest_source_record",
    "reconciliation_identifier_lookup",
    "reconciliation_work_sources",
    "reconciliation_current_membership",
    "reconciliation_state_predecessor",
    "reconciliation_alias_target",
    "dependency_impact_project_identity",
    "reconciliation_version_source_lookup",
    "reconciliation_version_relation_target",
    "reconciliation_version_relation_source",
    "reconciliation_version_preference_work",
    "corpus_item_states_current",
    "corpus_discovery_paths_item",
    "corpus_decisions_item",
    "rights_policy_revisions_current",
    "rights_policy_rechecks_output",
    "rights_policy_generic_rechecks_output",
    "rights_legacy_output_rechecks_project",
    "corpus_report_member_item",
    "corpus_report_path_source",
    "corpus_report_source_policy",
    "corpus_item_states_membership",
    "corpus_decisions_reason",
    "rights_use_decisions_action",
    "corpus_discovery_paths_source",
    "corpus_discovery_paths_search_run",
    "corpus_report_snapshots_project_time",
    "plugin_grant_events_current",
    "document_attachment_candidates_work",
    "document_attachment_candidates_object",
    "document_attachment_assertions_version",
    "document_attachment_operations_candidate",
)
V1_SCHEMA_SHA256 = "61e5693187250e240f9b6cae573e3b89752ae9b135c6c739d14ff3dfbf6dfdc9"
V1_PROFILE_SHA256 = "fcd3ee269f5d80ce4b554ffc4578d0d16cd941b4afecea19f8860197a77bd1c0"
PREVIOUS_SCHEMA_SHA256 = "afd48fbe857de4172215e9cb61a0f6137e73edec685dcc116bedbb66eb519dda"
PREVIOUS_PROFILE_SHA256 = "29454c72d0b357c2ece14a8991db57bfb87414d7ade85d1a2e8048a648a17cc2"
OBJECT_ENVELOPE_SCHEMA_SHA256 = "246ad968bb1931732c827d0739882c0d59ce91a06c7075867c503c0ef52fd356"
OBJECT_ENVELOPE_PROFILE_SHA256 = "78f1ea999a50641758b0b618af33dc18739d6d6c99644d97823af959583ac2d9"
OBJECT_ENVELOPE_UPGRADE_SCHEMA_SHA256 = "0b957b48a4280c0dd3c3f9ec518ac44b5fff9354e828572cd2af8aa95e496ff6"
OBJECT_ENVELOPE_UPGRADE_PROFILE_SHA256 = "12cd2d187b6abf8e3cc597288c103277f1079e77b2cd206ad2821730181dbffb"
OBJECT_CREATION_SOURCE_SCHEMA_SHA256 = "4d505b3f925e9df09b137cae61b56125878aa84fd0d6cb353e5d415a0602e2fd"
OBJECT_CREATION_SOURCE_PROFILE_SHA256 = "949f2d60ebe020ad8e8e049ac9d58307213d7aa7008025e5b340e543064ffaa7"
ACTOR_IDENTITY_SCHEMA_SHA256 = "11856aa1b328924596692f08acce368ffbb8798441353fe6a76036329460a7d4"
ACTOR_IDENTITY_PROFILE_SHA256 = "ab8e57caf36e9219a99085648850cd07e2b286feb5e4834ecadf204f76aa771f"
PROVENANCE_LEDGER_SCHEMA_SHA256 = "49329a82e7ade17d57f09a33e650d81e1b3b1d67dc6e4e3b4c8a79d24b6f7475"
WORKFLOW_EXECUTOR_SCHEMA_SHA256 = "1f5d94ac9a17732c72405fdda945df75d1558c444eaf7b6a5dcf286a50443b04"
MATERIAL_DEPENDENCY_SCHEMA_SHA256 = "a1f8087eda44532e269d19adfc6ee90591e00ca7a69be0ddab0db7c84744d2cc"
DEPENDENCY_IMPACT_SCHEMA_SHA256 = "49459b9ca8e54d27ad45abf16615946107a8d73e1ba8e211f1c45bc8fa230187"
IMPORT_PREVIEW_SCHEMA_SHA256 = "33f607dea1a2b20e0d1b451cafdbcaa5d1bb58e1b91499525adad40bc5a8f5c0"
IMPORT_SUMMARY_SCHEMA_SHA256 = "42a9886d0b9d132071cebe3170d12b46a048148f9c69dcf624178d4f281840fa"
IMPORT_COMMIT_SCHEMA_SHA256 = "13e54503130f8e40036beed26659c5bda2787928c56444987619366e4310b064"
RECONCILIATION_SCHEMA_SHA256 = "4b8b87b1024b855fa1eee932b41b9d4a8d8492823b17968eb3d17eda24b5ccb2"
RECONCILIATION_REVIEW_SCHEMA_SHA256 = "6361c684264358e94c19c90bd67f6f2d47eda21c107d1012a3f86b5cf2faf949"
WORK_VERSION_SCHEMA_SHA256 = "faa1dcd5823f086986ea3a86a8cc85369edd826f2a0c1d724f923bdff9f293f5"
CORPUS_SCHEMA_SHA256 = "bb068798493011b7b2300c076e9f129443fe15939aabdf16dc62af33ac6a7945"
RIGHTS_SCHEMA_SHA256 = "a9812a5fad0394652a070b3fd8466961eb3e88a928965d56e89d57008b89b503"
CORPUS_REPORT_SCHEMA_SHA256 = "829684b8a5274b6666400c2719ea9302384a8bdd01024b8f952b49a834ae52ba"
PLUGIN_GRANT_PREDECESSOR_SCHEMA_SHA256 = "c6bdef5f65d5f688747a1effed96f3cd79556e37891946e1985841bce4ae1cd6"
DOCUMENT_ATTACHMENT_PREDECESSOR_SCHEMA_SHA256 = "c0aa9be9916fbe517f1ae94a86aeac13f19a92ec366b1a4d4d816bff614da034"
ATTACHMENT_OPERATION_PREDECESSOR_SCHEMA_SHA256 = "32dc9a2b87efdd8b69b92271b8b1841e40da07bbc86e9943f59dbe5784f2617e"
ACQUISITION_PREDECESSOR_SCHEMA_SHA256 = "0d5eb89a3975aa1d95fa4d190ce8debfee2ae43d390669ce8b3acb5f10a1a41e"
DOCUMENT_INTAKE_PREDECESSOR_SCHEMA_SHA256 = "8078a6f7132200e6cf9e729f116c7b8ad6cd7c2bcf61d56f337e594dc7552a97"
EXPECTED_SCHEMA_SHA256 = "5c2090bb9586117f8f0e521efcb74ab10bd64a855fdcdc943035385cd1742951"

_PROFILE_DOCUMENT: dict[str, Any] = {
    "schemaVersion": "1.0",
    "documentType": "research-observatory-sqlite-profile",
    "profileId": DATABASE_PROFILE,
    "databaseSchemaVersion": DATABASE_SCHEMA_VERSION,
    "applicationId": APPLICATION_ID,
    "schemaFingerprintSha256": EXPECTED_SCHEMA_SHA256,
    "minimumSqliteVersion": "3.37.0",
    "identifierStorage": {
        "project": "uuid4-bridge-or-uuid7-lowercase-text",
        "aggregate": "uuid7-lowercase-text",
        "revision": "uuid7-lowercase-text",
        "event": "uuid7-lowercase-text",
        "actor": "canonical-id-or-uuid7-lowercase-text",
        "setting": "uuid7-lowercase-text",
    },
    "timestampStorage": "utc-rfc3339-millisecond-text",
    "canonicalColumnTypes": ["INTEGER", "REAL", "TEXT"],
    "derivedBinaryStorage": "digest-reference-only",
    "objectCreationSources": [
        "local-import",
        "connector-acquisition",
        "local-derivation",
        "test-fixture",
        "legacy-unreported",
    ],
    "immutableRowTables": list(IMMUTABLE_ROW_TABLES),
    "mutableStateTables": list(MUTABLE_STATE_TABLES),
    "connectionProfile": {
        "foreignKeys": True,
        "journalMode": "wal",
        "synchronous": "full",
        "busyTimeoutMilliseconds": BUSY_TIMEOUT_MILLISECONDS,
        "trustedSchema": False,
        "defensive": True,
        "doubleQuotedStringLiterals": False,
        "loadableExtensions": False,
        "recursiveTriggers": True,
        "walAutocheckpointPages": WAL_AUTOCHECKPOINT_PAGES,
        "lockingMode": "normal",
        "schemaChanges": "dedicated-backed-up-migration-connection-only",
    },
    "checkpointPolicy": {
        "automaticMode": "passive",
        "automaticPages": WAL_AUTOCHECKPOINT_PAGES,
        "manualAuthority": "migration-backup-and-maintenance-only",
    },
    "integrityChecks": ["quick_check", "foreign_key_check", "strict_table_inventory"],
    "canonicalTables": list(EXPECTED_TABLES),
}
_PROFILE_SHA256 = hashlib.sha256(
    json.dumps(_PROFILE_DOCUMENT, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()
PROVENANCE_LEDGER_PROFILE_SHA256 = "aa59d6f2858f41b7732c91947566fffaf5cd146e1143277deccf2707ceb751e0"
WORKFLOW_EXECUTOR_PROFILE_SHA256 = "c55bb71d5c9553de5d104ae591fee39e06407b479f9f3583b8f1ce42db8ecba7"
MATERIAL_DEPENDENCY_PROFILE_SHA256 = "4761d833e7d8a25e969e79ea9c740f501ae2a4c119b03f38ffb5d06bd1e46e76"
DEPENDENCY_IMPACT_PROFILE_SHA256 = "0641cf38a63226c98c9df55093f4c696687b14a2baddfb17f7986aa85efad8fb"
IMPORT_PREVIEW_PROFILE_SHA256 = "c751146ae0301c14716e8fa1f0c29b9929a1dd4caa9a3b9fd6d98595a7888c91"
IMPORT_SUMMARY_PROFILE_SHA256 = "9d6ac8532068f3271c42140525a6c106208f92ca6f8362c36eee4e25b02d863f"
IMPORT_COMMIT_PROFILE_SHA256 = "9ef28bc5d42188c63b50f31eb714c69d040a685311c1dcc5aaf1e89faec42e0b"
RECONCILIATION_PROFILE_SHA256 = "49ee17767e8a0652a381925181f3a6e38722b9635f15f704c22b648f0e981a89"
RECONCILIATION_REVIEW_PROFILE_SHA256 = "1db7b16d30ea6c1b629ba935c68a542129855391ab69246f62696623d067cd37"
WORK_VERSION_PROFILE_SHA256 = "2cf19511744a6536b5da695027768893bd54946460f57172dd790050bdafda72"
CORPUS_PROFILE_SHA256 = "3b79e6e6c2fa5055041b6977a318d0fe335b88f8106b72c2d099131fc31a9fc3"
RIGHTS_PROFILE_SHA256 = "4617f88a662f50b6286f399158ca4477e2cad34bad68033be99149cbdfb4ed30"
CORPUS_REPORT_PROFILE_SHA256 = "e22cb614472013b6ed3fac45c9778e7fb9c987018d20f416911a2f805db4a50f"
PLUGIN_GRANT_PREDECESSOR_PROFILE_SHA256 = "1e5b92e8e82cc64a191b4e3d5c1935d1931c4c3639678c26860fc317e1e11515"
DOCUMENT_ATTACHMENT_PREDECESSOR_PROFILE_SHA256 = "74ed7818d261958b0039aef90c00b42ed5f97b3558cc61818fcca93a862a9822"
ATTACHMENT_OPERATION_PREDECESSOR_PROFILE_SHA256 = "67361cdaa6b082a552f89a40c5a83036526da3a1230c8f6d3bef4cb57cc43997"
ACQUISITION_PREDECESSOR_PROFILE_SHA256 = "bc4f7aa4029ed660329b407362c017a42de2966f1d18bbbcbe7c75f1afa837f5"
DOCUMENT_INTAKE_PREDECESSOR_PROFILE_SHA256 = "b8f925467533ee5810343ce3a83a0035b8bf5e1f1989d421279994e0f73b9e1e"
EXPECTED_PROFILE_SHA256 = "50c8583b7958c4e035690fdcf305c8d968b3a4c26a21f18e8744436eabf45721"
if _PROFILE_SHA256 != EXPECTED_PROFILE_SHA256:
    raise RuntimeError("compiled SQLite profile differs from its reviewed fingerprint")

_UTC_INPUT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$")


class StorageProblem(RuntimeError):
    """Bounded local storage failure without project content or path disclosure."""


class _GuardedConnection(sqlite3.Connection):
    """Internal SQLite handle retaining file and directory identity guards."""

    _guard_handles: list[int]
    _guard_descriptor: int | None

    def close(self) -> None:
        try:
            super().close()
        finally:
            descriptor = getattr(self, "_guard_descriptor", None)
            if descriptor is not None:
                self._guard_descriptor = None
                os.close(descriptor)
            handles = getattr(self, "_guard_handles", [])
            self._guard_handles = []
            _close_windows_handles(handles)


class _GuardedSqlCipherConnection(sqlcipher.Connection):
    """Internal SQLCipher handle retaining file and directory identity guards."""

    _guard_handles: list[int]
    _guard_descriptor: int | None

    def close(self) -> None:
        try:
            super().close()
        finally:
            descriptor = getattr(self, "_guard_descriptor", None)
            if descriptor is not None:
                self._guard_descriptor = None
                os.close(descriptor)
            handles = getattr(self, "_guard_handles", [])
            self._guard_handles = []
            _close_windows_handles(handles)


@dataclass(frozen=True, slots=True)
class _DatabaseProtectionConfiguration:
    profile: str
    provider: DatabaseKeyProvider | None


_DATABASE_PROTECTION_LOCK = threading.RLock()
_DATABASE_PROTECTION = _DatabaseProtectionConfiguration(profile="unconfigured", provider=None)


def configure_protected_database_provider(provider: DatabaseKeyProvider) -> None:
    """Install the process composition's mandatory protected-database key authority."""

    if not isinstance(provider, DatabaseKeyProvider):
        raise ValueError("database key provider is invalid")
    global _DATABASE_PROTECTION
    with _DATABASE_PROTECTION_LOCK:
        if _CAPABILITY_REGISTRY.has_open_connections():
            raise StorageProblem("database protection cannot change while a database is open")
        _DATABASE_PROTECTION = _DatabaseProtectionConfiguration(profile=SQLCIPHER_PROFILE, provider=provider)


@contextmanager
def development_plaintext_database_fixture() -> Any:
    """Explicitly scope legacy schema tests to the sole allowed plaintext profile."""

    global _DATABASE_PROTECTION
    with _DATABASE_PROTECTION_LOCK:
        if _CAPABILITY_REGISTRY.has_open_connections():
            raise StorageProblem("database protection cannot change while a database is open")
        previous = _DATABASE_PROTECTION
        _DATABASE_PROTECTION = _DatabaseProtectionConfiguration(
            profile=DEVELOPMENT_PLAINTEXT_PROFILE,
            provider=None,
        )
    try:
        yield
    finally:
        with _DATABASE_PROTECTION_LOCK:
            if _CAPABILITY_REGISTRY.has_open_connections():
                raise StorageProblem("development plaintext fixture leaked an open database")
            _DATABASE_PROTECTION = previous


def database_protection_profile() -> str:
    with _DATABASE_PROTECTION_LOCK:
        return _DATABASE_PROTECTION.profile


@dataclass(frozen=True, slots=True)
class _CursorEntry:
    connection_token: str
    cursor: Any


class _CapabilityRegistry:
    """Module-owned raw SQLite authority, never returned to ordinary callers."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._connections: dict[str, Any] = {}
        self._cursors: dict[str, _CursorEntry] = {}

    def _token(self) -> str:
        while True:
            token = secrets.token_hex(32)
            if token not in self._connections and token not in self._cursors:
                return token

    def register_connection(self, connection: Any) -> str:
        with self._lock:
            token = self._token()
            self._connections[token] = connection
            return token

    def connection(self, token: str | None) -> Any:
        if token is None:
            raise sqlite3.ProgrammingError("canonical connection is closed")
        with self._lock:
            connection = self._connections.get(token)
        if connection is None:
            raise sqlite3.ProgrammingError("canonical connection is closed")
        return connection

    def close_connection(self, token: str | None) -> None:
        if token is None:
            return
        with self._lock:
            connection = self._connections.pop(token, None)
            cursors = [cursor_token for cursor_token, entry in self._cursors.items() if entry.connection_token == token]
            entries = [self._cursors.pop(cursor_token) for cursor_token in cursors]
        for entry in entries:
            with suppress(*_DATABASE_ERRORS):
                entry.cursor.close()
        if connection is not None:
            connection.close()

    def register_cursor(self, connection_token: str, cursor: Any) -> str:
        with self._lock:
            if connection_token not in self._connections:
                cursor.close()
                raise sqlite3.ProgrammingError("canonical connection is closed")
            token = self._token()
            self._cursors[token] = _CursorEntry(connection_token=connection_token, cursor=cursor)
            return token

    def cursor(self, token: str | None) -> Any:
        if token is None:
            raise sqlite3.ProgrammingError("canonical cursor is closed")
        with self._lock:
            entry = self._cursors.get(token)
        if entry is None:
            raise sqlite3.ProgrammingError("canonical cursor is closed")
        return entry.cursor

    def close_cursor(self, token: str | None) -> None:
        if token is None:
            return
        with self._lock:
            entry = self._cursors.pop(token, None)
        if entry is not None:
            with suppress(*_DATABASE_ERRORS):
                entry.cursor.close()

    def has_open_connections(self) -> bool:
        with self._lock:
            return bool(self._connections)


_CAPABILITY_REGISTRY = _CapabilityRegistry()


class CanonicalCursor:
    """Restricted result cursor carrying only an opaque registry token and metadata."""

    __slots__ = ("__description", "__lastrowid", "__rowcount", "__token")

    def __init__(
        self,
        token: str | None,
        *,
        description: tuple[Any, ...] | None,
        lastrowid: int | None,
        rowcount: int,
    ) -> None:
        self.__token = token
        self.__description = description
        self.__lastrowid = lastrowid
        self.__rowcount = rowcount

    def __iter__(self) -> CanonicalCursor:
        return self

    def __next__(self) -> Any:
        try:
            return next(_CAPABILITY_REGISTRY.cursor(self.__token))
        except StopIteration:
            self.close()
            raise
        except sqlcipher.Error as error:
            raise sqlite3.DatabaseError("protected database operation failed") from error

    def fetchone(self) -> Any:
        try:
            row = _CAPABILITY_REGISTRY.cursor(self.__token).fetchone()
        except sqlcipher.Error as error:
            raise sqlite3.DatabaseError("protected database operation failed") from error
        if row is None:
            self.close()
        return row

    def fetchmany(self, size: int | None = None) -> list[Any]:
        cursor = _CAPABILITY_REGISTRY.cursor(self.__token)
        try:
            rows = cursor.fetchmany() if size is None else cursor.fetchmany(size)
        except sqlcipher.Error as error:
            raise sqlite3.DatabaseError("protected database operation failed") from error
        if not rows:
            self.close()
        return rows

    def fetchall(self) -> list[Any]:
        try:
            try:
                return _CAPABILITY_REGISTRY.cursor(self.__token).fetchall()
            except sqlcipher.Error as error:
                raise sqlite3.DatabaseError("protected database operation failed") from error
        finally:
            self.close()

    def close(self) -> None:
        token = self.__token
        self.__token = None
        _CAPABILITY_REGISTRY.close_cursor(token)

    @property
    def description(self) -> tuple[Any, ...] | None:
        return self.__description

    @property
    def lastrowid(self) -> int | None:
        return self.__lastrowid

    @property
    def rowcount(self) -> int:
        return self.__rowcount

    def __del__(self) -> None:
        with suppress(Exception):
            self.close()


def _restricted_cursor(connection_token: str, cursor: Any) -> CanonicalCursor:
    description = cursor.description
    lastrowid = cursor.lastrowid
    rowcount = cursor.rowcount
    token: str | None = None
    if description is None:
        cursor.close()
    else:
        token = _CAPABILITY_REGISTRY.register_cursor(connection_token, cursor)
    return CanonicalCursor(token, description=description, lastrowid=lastrowid, rowcount=rowcount)


class CanonicalConnection:
    """Restricted ordinary database capability carrying only an opaque registry token."""

    __slots__ = ("__token",)

    def __init__(self, token: str) -> None:
        self.__token: str | None = token

    def execute(self, sql: str, parameters: Any = ()) -> CanonicalCursor:
        token = self.__token
        if token is None:
            raise sqlite3.ProgrammingError("canonical connection is closed")
        connection = _CAPABILITY_REGISTRY.connection(token)
        try:
            return _restricted_cursor(token, connection.execute(sql, parameters))
        except sqlcipher.Error as error:
            raise sqlite3.DatabaseError("protected database operation failed") from error

    def executemany(self, sql: str, parameters: Any) -> CanonicalCursor:
        token = self.__token
        if token is None:
            raise sqlite3.ProgrammingError("canonical connection is closed")
        connection = _CAPABILITY_REGISTRY.connection(token)
        try:
            return _restricted_cursor(token, connection.executemany(sql, parameters))
        except sqlcipher.Error as error:
            raise sqlite3.DatabaseError("protected database operation failed") from error

    def commit(self) -> None:
        try:
            _CAPABILITY_REGISTRY.connection(self.__token).commit()
        except sqlcipher.Error as error:
            raise sqlite3.DatabaseError("protected database operation failed") from error

    def rollback(self) -> None:
        try:
            _CAPABILITY_REGISTRY.connection(self.__token).rollback()
        except sqlcipher.Error as error:
            raise sqlite3.DatabaseError("protected database operation failed") from error

    @contextmanager
    def interrupt_when(self, requested: Callable[[], bool]):
        """Scoped stop-only hook; never expose the raw handle or alter its policy.

        The hook is removed before callers unwind/rollback. SQLite may itself
        roll back an interrupted writer; ordinary transaction checks cover both.
        """
        connection = _CAPABILITY_REGISTRY.connection(self.__token)
        connection.set_progress_handler(lambda: int(requested()), 1000)
        try:
            yield
        finally:
            connection.set_progress_handler(None, 0)

    @property
    def in_transaction(self) -> bool:
        return _CAPABILITY_REGISTRY.connection(self.__token).in_transaction

    def close(self) -> None:
        token = self.__token
        self.__token = None
        _CAPABILITY_REGISTRY.close_connection(token)

    def __enter__(self) -> CanonicalConnection:
        _CAPABILITY_REGISTRY.connection(self.__token)
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()

    def __del__(self) -> None:
        with suppress(Exception):
            self.close()


@dataclass(frozen=True, slots=True)
class DatabaseIntegrityReport:
    ok: bool
    profile_id: str | None
    schema_version: int | None
    application_id: int | None
    journal_mode: str | None
    foreign_keys: bool | None
    strict_tables: tuple[str, ...]
    quick_check: tuple[str, ...]
    foreign_key_violations: tuple[tuple[Any, ...], ...]
    protection_profile: str
    cipher_version: str | None
    cipher_integrity: tuple[str, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DatabaseRekeyReport:
    operation_id: str
    outcome: str
    previous_key_version: str
    active_key_version: str
    backup_sha256: str


@dataclass(frozen=True, slots=True)
class DatabaseProtectionMigrationReport:
    operation_id: str
    outcome: str
    plaintext_source_sha256: str
    protected_database_sha256: str
    plaintext_cleanup: str


@dataclass(frozen=True, slots=True)
class ProtectedDatabaseBackupReport:
    protection_profile: str
    database_sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class ProtectedDatabaseRestoreReport:
    operation_id: str
    outcome: str
    restored_database_sha256: str
    displaced_database_sha256: str


def storage_profile_document() -> dict[str, Any]:
    """Return a detached JSON-compatible copy of the portable profile."""

    return json.loads(json.dumps(_PROFILE_DOCUMENT, ensure_ascii=True))


def _uuid_check(column: str, version: str) -> str:
    return (
        f"length({column}) = 36 AND {column} = lower({column}) "
        f"AND substr({column}, 9, 1) = '-' AND substr({column}, 14, 1) = '-' "
        f"AND substr({column}, 19, 1) = '-' AND substr({column}, 24, 1) = '-' "
        f"AND length(replace({column}, '-', '')) = 32 "
        f"AND {column} NOT GLOB '*[^0-9a-f-]*' "
        f"AND substr({column}, 15, 1) = '{version}' "
        f"AND substr({column}, 20, 1) IN ('8', '9', 'a', 'b')"
    )


def _project_uuid_check(column: str) -> str:
    common = (
        f"length({column}) = 36 AND {column} = lower({column}) "
        f"AND substr({column}, 9, 1) = '-' AND substr({column}, 14, 1) = '-' "
        f"AND substr({column}, 19, 1) = '-' AND substr({column}, 24, 1) = '-' "
        f"AND length(replace({column}, '-', '')) = 32 "
        f"AND {column} NOT GLOB '*[^0-9a-f-]*' "
        f"AND substr({column}, 20, 1) IN ('8', '9', 'a', 'b')"
    )
    return (
        f"{common} AND ((project_id_scheme = 'uuid4-bridge' AND substr({column}, 15, 1) = '4') "
        f"OR (project_id_scheme = 'uuid7' AND substr({column}, 15, 1) = '7'))"
    )


def _timestamp_check(column: str) -> str:
    return (
        f"length({column}) = 24 AND {column} GLOB "
        "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T"
        "[0-9][0-9]:[0-9][0-9]:[0-9][0-9]."
        "[0-9][0-9][0-9]Z' "
        f"AND CAST(substr({column}, 1, 4) AS INTEGER) BETWEEN 1 AND 9999 "
        f"AND CAST(substr({column}, 12, 2) AS INTEGER) BETWEEN 0 AND 23 "
        f"AND strftime('%Y-%m-%dT%H:%M:%fZ', {column}) IS NOT NULL "
        f"AND strftime('%Y-%m-%dT%H:%M:%fZ', {column}) = {column}"
    )


def _sha256_check(column: str) -> str:
    return f"length({column}) = 64 AND {column} = lower({column}) AND {column} NOT GLOB '*[^0-9a-f]*'"


def _identifier_check(column: str, maximum: int = 120) -> str:
    return (
        f"length({column}) BETWEEN 1 AND {maximum} AND {column} = lower({column}) "
        f"AND substr({column}, 1, 1) GLOB '[a-z]' "
        f"AND {column} NOT GLOB '*[^a-z0-9.-]*' "
        f"AND {column} NOT GLOB '*..*' AND {column} NOT GLOB '*--*' "
        f"AND substr({column}, -1, 1) GLOB '[a-z0-9]'"
    )


def _subtype_table(name: str, kind: str) -> str:
    return f"""
        CREATE TABLE {name} (
            revision_id TEXT PRIMARY KEY,
            aggregate_kind TEXT NOT NULL DEFAULT '{kind}' CHECK (aggregate_kind = '{kind}'),
            FOREIGN KEY (revision_id, aggregate_kind)
                REFERENCES aggregate_revisions (revision_id, aggregate_kind)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """


def _immutable_triggers(table: str, message: str) -> tuple[str, str]:
    return (
        f"""
            CREATE TRIGGER {table}_no_update
            BEFORE UPDATE ON {table}
            BEGIN
                SELECT RAISE(ABORT, '{message}');
            END
        """,
        f"""
            CREATE TRIGGER {table}_no_delete
            BEFORE DELETE ON {table}
            BEGIN
                SELECT RAISE(ABORT, '{message}');
            END
        """,
    )


_V1_IMMUTABLE_ROW_POLICIES = (
    ("schema_metadata", "schema metadata is immutable outside a reviewed migration"),
    ("projects", "project identity is immutable"),
    ("aggregate_identities", "aggregate identities are immutable"),
    ("aggregate_revisions", "aggregate revisions are immutable"),
    ("scholarly_records", "scholarly record revisions are immutable"),
    ("documents", "document revisions are immutable"),
    ("workflows", "workflow revisions are immutable"),
    ("evidence", "evidence revisions are immutable"),
    ("ontologies", "ontology revisions are immutable"),
    ("decisions", "decision revisions are immutable"),
    ("provenance_events", "provenance events are append-only"),
    ("settings", "settings history is append-only"),
)

_IMMUTABLE_ROW_POLICIES = (
    *_V1_IMMUTABLE_ROW_POLICIES,
    ("schema_migrations", "schema migration history is append-only"),
)


_V1_DDL_STATEMENTS = (
    f"""
        CREATE TABLE schema_metadata (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            schema_version INTEGER NOT NULL CHECK (schema_version = {OLDEST_DATABASE_SCHEMA_VERSION}),
            database_profile TEXT NOT NULL CHECK (database_profile = '{DATABASE_PROFILE}'),
            application_id INTEGER NOT NULL CHECK (application_id = {APPLICATION_ID}),
            profile_sha256 TEXT NOT NULL CHECK ({_sha256_check("profile_sha256")}),
            schema_sha256 TEXT NOT NULL CHECK ({_sha256_check("schema_sha256")}),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")})
        ) STRICT
    """,
    f"""
        CREATE TABLE projects (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            project_id TEXT NOT NULL UNIQUE,
            project_id_scheme TEXT NOT NULL CHECK (project_id_scheme IN ('uuid4-bridge', 'uuid7')),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            CHECK ({_project_uuid_check("project_id")}),
            UNIQUE (project_id, project_id_scheme)
        ) STRICT
    """,
    f"""
        CREATE TABLE aggregate_identities (
            aggregate_id TEXT PRIMARY KEY CHECK ({_uuid_check("aggregate_id", "7")}),
            project_id TEXT NOT NULL,
            aggregate_kind TEXT NOT NULL CHECK (aggregate_kind IN (
                'record', 'document', 'workflow', 'evidence', 'ontology', 'decision'
            )),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (aggregate_id, project_id, aggregate_kind)
        ) STRICT
    """,
    f"""
        CREATE TABLE aggregate_revisions (
            revision_id TEXT PRIMARY KEY CHECK ({_uuid_check("revision_id", "7")}),
            aggregate_id TEXT NOT NULL CHECK ({_uuid_check("aggregate_id", "7")}),
            aggregate_kind TEXT NOT NULL CHECK (aggregate_kind IN (
                'record', 'document', 'workflow', 'evidence', 'ontology', 'decision'
            )),
            project_id TEXT NOT NULL,
            revision INTEGER NOT NULL CHECK (revision BETWEEN 0 AND {MAX_SAFE_INTEGER}),
            contract_version TEXT NOT NULL CHECK (contract_version = '1.0.0'),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            modified_at TEXT NOT NULL CHECK ({_timestamp_check("modified_at")}),
            display_label_observed TEXT NOT NULL CHECK (length(display_label_observed) BETWEEN 1 AND 4096),
            display_label_normalized TEXT CHECK (length(display_label_normalized) BETWEEN 1 AND 4096),
            knowledge_status TEXT NOT NULL CHECK (knowledge_status IN (
                'observed', 'extracted', 'inferred', 'verified', 'disputed', 'adjudicated',
                'stale', 'unknown', 'not-reported', 'not-applicable', 'ambiguous', 'unavailable'
            )),
            rights_status TEXT NOT NULL CHECK (rights_status IN ('allowed', 'denied', 'unknown', 'not-applicable')),
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (aggregate_id, project_id, aggregate_kind)
                REFERENCES aggregate_identities (aggregate_id, project_id, aggregate_kind)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CHECK (revision_id <> aggregate_id),
            CHECK (modified_at >= created_at),
            UNIQUE (aggregate_id, revision),
            UNIQUE (revision_id, aggregate_kind),
            UNIQUE (revision_id, project_id),
            UNIQUE (revision_id, aggregate_kind, project_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE object_records (
            object_sha256 TEXT PRIMARY KEY CHECK ({_sha256_check("object_sha256")}),
            project_id TEXT NOT NULL,
            byte_length INTEGER NOT NULL CHECK (byte_length BETWEEN 0 AND {MAX_SAFE_INTEGER}),
            media_type TEXT NOT NULL CHECK (
                length(media_type) BETWEEN 3 AND 200
                AND media_type = lower(media_type)
                AND instr(media_type, '/') BETWEEN 2 AND length(media_type) - 1
                AND media_type NOT GLOB '*[^a-z0-9!#$&^_.+/-]*'
            ),
            rights_status TEXT NOT NULL CHECK (rights_status IN ('allowed', 'denied', 'unknown', 'not-applicable')),
            protection_profile TEXT NOT NULL CHECK ({_identifier_check("protection_profile", 120)}),
            retention_class TEXT NOT NULL CHECK (
                retention_class IN ('project-lifetime', 'derived-rebuildable', 'export-retained')
            ),
            storage_state TEXT NOT NULL CHECK (
                storage_state IN ('pending', 'available', 'quarantined', 'deleted')
            ),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            verified_at TEXT CHECK (verified_at IS NULL OR ({_timestamp_check("verified_at")})),
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            CHECK (verified_at IS NULL OR verified_at >= created_at),
            UNIQUE (object_sha256, project_id)
        ) STRICT
    """,
    _subtype_table("scholarly_records", "record"),
    """
        CREATE TABLE documents (
            revision_id TEXT PRIMARY KEY,
            aggregate_kind TEXT NOT NULL DEFAULT 'document' CHECK (aggregate_kind = 'document'),
            project_id TEXT NOT NULL,
            object_sha256 TEXT,
            FOREIGN KEY (revision_id, aggregate_kind, project_id)
                REFERENCES aggregate_revisions (revision_id, aggregate_kind, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (object_sha256, project_id) REFERENCES object_records (object_sha256, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    _subtype_table("workflows", "workflow"),
    _subtype_table("evidence", "evidence"),
    _subtype_table("ontologies", "ontology"),
    _subtype_table("decisions", "decision"),
    f"""
        CREATE TABLE provenance_events (
            event_id TEXT PRIMARY KEY CHECK ({_uuid_check("event_id", "7")}),
            project_id TEXT NOT NULL,
            revision_id TEXT,
            event_type TEXT NOT NULL CHECK ({_identifier_check("event_type")}),
            occurred_at TEXT NOT NULL CHECK ({_timestamp_check("occurred_at")}),
            trace_id TEXT NOT NULL CHECK (
                length(trace_id) = 32 AND trace_id = lower(trace_id) AND trace_id NOT GLOB '*[^0-9a-f]*'
            ),
            actor_type TEXT NOT NULL CHECK (actor_type IN ('human', 'system', 'worker', 'model')),
            actor_id TEXT CHECK ({_identifier_check("actor_id", 200)}),
            record_sha256 TEXT NOT NULL CHECK ({_sha256_check("record_sha256")}),
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (revision_id, project_id) REFERENCES aggregate_revisions (revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    f"""
        CREATE TABLE settings (
            setting_id TEXT PRIMARY KEY CHECK ({_uuid_check("setting_id", "7")}),
            project_id TEXT NOT NULL,
            setting_key TEXT NOT NULL CHECK ({_identifier_check("setting_key", 160)}),
            revision INTEGER NOT NULL CHECK (revision BETWEEN 0 AND {MAX_SAFE_INTEGER}),
            value_type TEXT NOT NULL CHECK (value_type IN ('text', 'integer', 'real', 'boolean')),
            text_value TEXT,
            integer_value INTEGER,
            real_value REAL,
            boolean_value INTEGER CHECK (boolean_value IN (0, 1)),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            modified_at TEXT NOT NULL CHECK ({_timestamp_check("modified_at")}),
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            CHECK (modified_at >= created_at),
            CHECK (integer_value IS NULL OR integer_value BETWEEN -{MAX_SAFE_INTEGER} AND {MAX_SAFE_INTEGER}),
            CHECK (
                real_value IS NULL
                OR real_value BETWEEN -1.7976931348623157e308 AND 1.7976931348623157e308
            ),
            CHECK (text_value IS NULL OR length(text_value) <= 65536),
            CHECK (
                (value_type = 'text' AND text_value IS NOT NULL AND integer_value IS NULL
                    AND real_value IS NULL AND boolean_value IS NULL)
                OR (value_type = 'integer' AND text_value IS NULL AND integer_value IS NOT NULL
                    AND real_value IS NULL AND boolean_value IS NULL)
                OR (value_type = 'real' AND text_value IS NULL AND integer_value IS NULL
                    AND real_value IS NOT NULL AND boolean_value IS NULL)
                OR (value_type = 'boolean' AND text_value IS NULL AND integer_value IS NULL
                    AND real_value IS NULL AND boolean_value IS NOT NULL)
            ),
            UNIQUE (project_id, setting_key, revision)
        ) STRICT
    """,
    f"""
        CREATE TABLE outbox_events (
            outbox_id TEXT PRIMARY KEY CHECK ({_uuid_check("outbox_id", "7")}),
            project_id TEXT NOT NULL,
            revision_id TEXT,
            event_type TEXT NOT NULL CHECK ({_identifier_check("event_type")}),
            occurred_at TEXT NOT NULL CHECK ({_timestamp_check("occurred_at")}),
            available_at TEXT NOT NULL CHECK ({_timestamp_check("available_at")}),
            state TEXT NOT NULL CHECK (state IN ('pending', 'publishing', 'published', 'failed')),
            attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count BETWEEN 0 AND 1000),
            published_at TEXT CHECK (published_at IS NULL OR ({_timestamp_check("published_at")})),
            idempotency_key TEXT NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 200),
            record_sha256 TEXT NOT NULL CHECK ({_sha256_check("record_sha256")}),
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (revision_id, project_id) REFERENCES aggregate_revisions (revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CHECK (available_at >= occurred_at),
            CHECK (
                (state = 'published' AND published_at IS NOT NULL)
                OR (state <> 'published' AND published_at IS NULL)
            ),
            UNIQUE (project_id, idempotency_key)
        ) STRICT
    """,
    *(statement for table, message in _V1_IMMUTABLE_ROW_POLICIES for statement in _immutable_triggers(table, message)),
    "CREATE INDEX aggregate_revisions_project_kind ON aggregate_revisions (project_id, aggregate_kind, revision)",
    "CREATE INDEX provenance_events_project_time ON provenance_events (project_id, occurred_at, event_id)",
    "CREATE INDEX outbox_events_dispatch ON outbox_events (state, available_at, outbox_id)",
)

_PROVENANCE_EVENTS_V5_DDL = next(
    statement for statement in _V1_DDL_STATEMENTS if "CREATE TABLE provenance_events" in statement
)
PROVENANCE_EVENTS_V6_DDL = _PROVENANCE_EVENTS_V5_DDL.replace(
    f"actor_id TEXT CHECK ({_identifier_check('actor_id', 200)}),",
    f"actor_id TEXT CHECK (({_identifier_check('actor_id', 200)}) OR ({_uuid_check('actor_id', '7')})),",
)
if PROVENANCE_EVENTS_V6_DDL == _PROVENANCE_EVENTS_V5_DDL:
    raise RuntimeError("compiled provenance actor migration differs from its source authority")
SCHEMA_METADATA_V6_DDL = SCHEMA_METADATA_V5_DDL.replace(
    "schema_version INTEGER NOT NULL CHECK (schema_version = 5)",
    "schema_version INTEGER NOT NULL CHECK (schema_version = 6)",
)
SCHEMA_METADATA_V7_DDL = SCHEMA_METADATA_V6_DDL.replace(
    "schema_version INTEGER NOT NULL CHECK (schema_version = 6)",
    "schema_version INTEGER NOT NULL CHECK (schema_version = 7)",
)
SCHEMA_METADATA_V8_DDL = SCHEMA_METADATA_V7_DDL.replace(
    "schema_version INTEGER NOT NULL CHECK (schema_version = 7)",
    "schema_version INTEGER NOT NULL CHECK (schema_version = 8)",
)
SCHEMA_METADATA_V9_DDL = SCHEMA_METADATA_V8_DDL.replace(
    "schema_version INTEGER NOT NULL CHECK (schema_version = 8)",
    "schema_version INTEGER NOT NULL CHECK (schema_version = 9)",
)
SCHEMA_METADATA_V10_DDL = SCHEMA_METADATA_V9_DDL.replace(
    "schema_version INTEGER NOT NULL CHECK (schema_version = 9)",
    "schema_version INTEGER NOT NULL CHECK (schema_version = 10)",
)

SCHEMA_METADATA_V11_DDL = SCHEMA_METADATA_V10_DDL.replace(
    "schema_version INTEGER NOT NULL CHECK (schema_version = 10)",
    "schema_version INTEGER NOT NULL CHECK (schema_version = 11)",
)
SCHEMA_METADATA_V12_DDL = SCHEMA_METADATA_V11_DDL.replace(
    "schema_version INTEGER NOT NULL CHECK (schema_version = 11)",
    "schema_version INTEGER NOT NULL CHECK (schema_version = 12)",
)

SCHEMA_METADATA_V13_DDL = SCHEMA_METADATA_V12_DDL.replace(
    "schema_version INTEGER NOT NULL CHECK (schema_version = 12)",
    "schema_version INTEGER NOT NULL CHECK (schema_version = 13)",
)

PROVENANCE_LEDGER_DDL = (
    f"""
        CREATE TABLE provenance_ledger_events (
            event_id TEXT PRIMARY KEY CHECK ({_uuid_check("event_id", "7")}),
            project_id TEXT NOT NULL,
            segment_key TEXT NOT NULL CHECK ({_identifier_check("segment_key", 120)}),
            sequence INTEGER NOT NULL CHECK (sequence BETWEEN 1 AND {MAX_SAFE_INTEGER}),
            subject TEXT NOT NULL CHECK (length(subject) BETWEEN 50 AND 300),
            event_type TEXT NOT NULL CHECK (length(event_type) BETWEEN 1 AND 160),
            occurred_at TEXT NOT NULL CHECK ({_timestamp_check("occurred_at")}),
            correlation_id TEXT NOT NULL CHECK ({_uuid_check("correlation_id", "7")}),
            causation_id TEXT CHECK (causation_id IS NULL OR ({_uuid_check("causation_id", "7")})),
            activity_id TEXT NOT NULL CHECK ({_uuid_check("activity_id", "7")}),
            activity_type TEXT NOT NULL CHECK ({_identifier_check("activity_type", 128)}),
            activity_status TEXT NOT NULL CHECK (activity_status IN ('succeeded', 'failed', 'cancelled', 'denied')),
            agent_id TEXT NOT NULL CHECK ({_uuid_check("agent_id", "7")}),
            sensitivity TEXT NOT NULL CHECK (
                sensitivity IN (
                    'public-metadata', 'licensed-metadata', 'open-full-text',
                    'licensed-full-text', 'private-research', 'restricted'
                )
            ),
            retention_class TEXT NOT NULL CHECK (
                retention_class IN ('project-lifetime', 'legal-hold', 'policy-bound', 'time-bounded', 'tombstone-only')
            ),
            record_json TEXT NOT NULL CHECK (length(record_json) BETWEEN 2 AND 1048576),
            record_sha256 TEXT NOT NULL CHECK (
                length(record_sha256) = 71 AND substr(record_sha256, 1, 7) = 'sha256:'
                AND substr(record_sha256, 8) = lower(substr(record_sha256, 8))
                AND substr(record_sha256, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            idempotency_sha256 TEXT NOT NULL CHECK ({_sha256_check("idempotency_sha256")}),
            previous_chain_sha256 TEXT CHECK (
                previous_chain_sha256 IS NULL OR (
                    length(previous_chain_sha256) = 71 AND substr(previous_chain_sha256, 1, 7) = 'sha256:'
                    AND substr(previous_chain_sha256, 8) = lower(substr(previous_chain_sha256, 8))
                    AND substr(previous_chain_sha256, 8) NOT GLOB '*[^0-9a-f]*'
                )
            ),
            chain_sha256 TEXT NOT NULL CHECK (
                length(chain_sha256) = 71 AND substr(chain_sha256, 1, 7) = 'sha256:'
                AND substr(chain_sha256, 8) = lower(substr(chain_sha256, 8))
                AND substr(chain_sha256, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (project_id, segment_key, sequence),
            UNIQUE (project_id, event_id),
            UNIQUE (project_id, record_sha256)
        ) STRICT
    """,
    f"""
        CREATE TABLE provenance_ledger_entities (
            event_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            direction TEXT NOT NULL CHECK (direction IN ('input', 'output')),
            entity_id TEXT NOT NULL CHECK ({_uuid_check("entity_id", "7")}),
            revision_id TEXT NOT NULL CHECK ({_uuid_check("revision_id", "7")}),
            entity_kind TEXT NOT NULL CHECK ({_identifier_check("entity_kind", 128)}),
            content_hash TEXT NOT NULL CHECK (
                length(content_hash) = 71 AND substr(content_hash, 1, 7) = 'sha256:'
                AND substr(content_hash, 8) = lower(substr(content_hash, 8))
                AND substr(content_hash, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            sensitivity TEXT NOT NULL CHECK (
                sensitivity IN (
                    'public-metadata', 'licensed-metadata', 'open-full-text',
                    'licensed-full-text', 'private-research', 'restricted'
                )
            ),
            retention_class TEXT NOT NULL CHECK (
                retention_class IN ('project-lifetime', 'legal-hold', 'policy-bound', 'time-bounded', 'tombstone-only')
            ),
            PRIMARY KEY (event_id, direction, revision_id),
            FOREIGN KEY (event_id, project_id) REFERENCES provenance_ledger_events (event_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (revision_id, project_id) REFERENCES aggregate_revisions (revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    f"""
        CREATE TABLE provenance_ledger_relations (
            event_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            relation_id TEXT NOT NULL CHECK ({_uuid_check("relation_id", "7")}),
            relation_type TEXT NOT NULL CHECK (
                relation_type IN (
                    'used', 'wasGeneratedBy', 'wasAssociatedWith', 'wasDerivedFrom',
                    'wasInvalidatedBy', 'wasAttributedTo'
                )
            ),
            entity_id TEXT CHECK (entity_id IS NULL OR ({_uuid_check("entity_id", "7")})),
            entity_revision_id TEXT CHECK (
                entity_revision_id IS NULL OR ({_uuid_check("entity_revision_id", "7")})
            ),
            related_entity_id TEXT CHECK (related_entity_id IS NULL OR ({_uuid_check("related_entity_id", "7")})),
            related_revision_id TEXT CHECK (
                related_revision_id IS NULL OR ({_uuid_check("related_revision_id", "7")})
            ),
            activity_id TEXT CHECK (activity_id IS NULL OR ({_uuid_check("activity_id", "7")})),
            agent_id TEXT CHECK (agent_id IS NULL OR ({_uuid_check("agent_id", "7")})),
            occurred_at TEXT NOT NULL CHECK ({_timestamp_check("occurred_at")}),
            PRIMARY KEY (event_id, relation_id),
            FOREIGN KEY (event_id, project_id) REFERENCES provenance_ledger_events (event_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CHECK ((entity_id IS NULL) = (entity_revision_id IS NULL)),
            CHECK ((related_entity_id IS NULL) = (related_revision_id IS NULL))
        ) STRICT
    """,
    f"""
        CREATE TABLE provenance_ledger_checkpoints (
            checkpoint_id TEXT PRIMARY KEY CHECK ({_uuid_check("checkpoint_id", "7")}),
            event_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            segment_key TEXT NOT NULL CHECK ({_identifier_check("segment_key", 120)}),
            sequence INTEGER NOT NULL CHECK (sequence BETWEEN 1 AND {MAX_SAFE_INTEGER}),
            chain_sha256 TEXT NOT NULL CHECK (
                length(chain_sha256) = 71 AND substr(chain_sha256, 1, 7) = 'sha256:'
                AND substr(chain_sha256, 8) = lower(substr(chain_sha256, 8))
                AND substr(chain_sha256, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            FOREIGN KEY (event_id, project_id) REFERENCES provenance_ledger_events (event_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (project_id, segment_key, sequence)
        ) STRICT
    """,
    f"""
        CREATE TABLE provenance_legacy_bridges (
            event_id TEXT PRIMARY KEY CHECK ({_uuid_check("event_id", "7")}),
            project_id TEXT NOT NULL,
            revision_id TEXT,
            event_type TEXT NOT NULL CHECK ({_identifier_check("event_type")}),
            occurred_at TEXT NOT NULL CHECK ({_timestamp_check("occurred_at")}),
            trace_id TEXT NOT NULL CHECK (
                length(trace_id) = 32 AND trace_id = lower(trace_id) AND trace_id NOT GLOB '*[^0-9a-f]*'
            ),
            actor_type TEXT NOT NULL CHECK (actor_type IN ('human', 'system', 'worker', 'model')),
            actor_id TEXT,
            source_record_sha256 TEXT NOT NULL CHECK ({_sha256_check("source_record_sha256")}),
            bridge_state TEXT NOT NULL CHECK (bridge_state = 'legacy-narrow'),
            FOREIGN KEY (event_id) REFERENCES provenance_events (event_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (revision_id, project_id) REFERENCES aggregate_revisions (revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    *(
        statement
        for table, message in (
            ("provenance_ledger_events", "provenance ledger events are append-only"),
            ("provenance_ledger_entities", "provenance ledger entities are append-only"),
            ("provenance_ledger_relations", "provenance ledger relations are append-only"),
            ("provenance_ledger_checkpoints", "provenance ledger checkpoints are append-only"),
            ("provenance_legacy_bridges", "provenance legacy bridges are append-only"),
        )
        for statement in _immutable_triggers(table, message)
    ),
    "CREATE INDEX provenance_ledger_project_time ON provenance_ledger_events (project_id, occurred_at, event_id)",
    "CREATE INDEX provenance_ledger_project_type ON provenance_ledger_events (project_id, event_type, occurred_at)",
    "CREATE INDEX provenance_ledger_project_subject ON provenance_ledger_events (project_id, subject, occurred_at)",
    "CREATE INDEX provenance_ledger_project_correlation ON provenance_ledger_events "
    "(project_id, correlation_id, occurred_at)",
    "CREATE INDEX provenance_ledger_entity_input ON provenance_ledger_entities "
    "(project_id, revision_id, direction, event_id)",
    "CREATE INDEX provenance_ledger_entity_output ON provenance_ledger_entities "
    "(project_id, entity_id, direction, revision_id)",
    "CREATE INDEX provenance_ledger_relation_entity ON provenance_ledger_relations "
    "(project_id, entity_revision_id, relation_type)",
    "CREATE INDEX provenance_ledger_relation_related_entity ON provenance_ledger_relations "
    "(project_id, related_revision_id, relation_type)",
    """
        CREATE TRIGGER provenance_events_bridge_legacy_after_insert
        AFTER INSERT ON provenance_events
        WHEN NOT EXISTS (
            SELECT 1 FROM provenance_ledger_events
             WHERE project_id=NEW.project_id AND event_id=NEW.event_id
        )
        BEGIN
            INSERT INTO provenance_legacy_bridges (
                event_id, project_id, revision_id, event_type, occurred_at,
                trace_id, actor_type, actor_id, source_record_sha256, bridge_state
            ) VALUES (
                NEW.event_id, NEW.project_id, NEW.revision_id, NEW.event_type,
                NEW.occurred_at, NEW.trace_id, NEW.actor_type, NEW.actor_id,
                NEW.record_sha256, 'legacy-narrow'
            );
        END
    """,
)

WORKFLOW_EXECUTOR_DDL = (
    f"""
        CREATE TABLE workflow_definitions (
            definition_revision_id TEXT PRIMARY KEY CHECK ({_uuid_check("definition_revision_id", "7")}),
            project_id TEXT NOT NULL,
            workflow_definition_id TEXT NOT NULL CHECK ({_uuid_check("workflow_definition_id", "7")}),
            definition_version TEXT NOT NULL CHECK (length(definition_version) BETWEEN 5 AND 64),
            contract_version TEXT NOT NULL CHECK (contract_version = '1.0.0'),
            content_hash TEXT NOT NULL CHECK (
                length(content_hash) = 71 AND substr(content_hash, 1, 7) = 'sha256:'
                AND substr(content_hash, 8) = lower(substr(content_hash, 8))
                AND substr(content_hash, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            definition_json TEXT NOT NULL CHECK (length(definition_json) BETWEEN 2 AND 1048576),
            record_sha256 TEXT NOT NULL CHECK (
                length(record_sha256) = 71 AND substr(record_sha256, 1, 7) = 'sha256:'
                AND substr(record_sha256, 8) = lower(substr(record_sha256, 8))
                AND substr(record_sha256, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (project_id, workflow_definition_id, definition_revision_id),
            UNIQUE (project_id, record_sha256)
        ) STRICT
    """,
    f"""
        CREATE TABLE workflow_authority_snapshots (
            snapshot_id TEXT NOT NULL CHECK ({_uuid_check("snapshot_id", "7")}),
            snapshot_revision INTEGER NOT NULL CHECK (snapshot_revision BETWEEN 1 AND {MAX_SAFE_INTEGER}),
            project_id TEXT NOT NULL,
            workflow_run_id TEXT NOT NULL CHECK ({_uuid_check("workflow_run_id", "7")}),
            definition_revision_id TEXT NOT NULL CHECK ({_uuid_check("definition_revision_id", "7")}),
            state TEXT NOT NULL CHECK (state IN (
                'accepted', 'running', 'waiting-human', 'paused', 'cancelling',
                'succeeded', 'failed', 'cancelled'
            )),
            history_sequence INTEGER NOT NULL CHECK (history_sequence BETWEEN 1 AND {MAX_SAFE_INTEGER}),
            snapshot_json TEXT NOT NULL CHECK (length(snapshot_json) BETWEEN 2 AND 16777216),
            record_sha256 TEXT NOT NULL CHECK (
                length(record_sha256) = 71 AND substr(record_sha256, 1, 7) = 'sha256:'
                AND substr(record_sha256, 8) = lower(substr(record_sha256, 8))
                AND substr(record_sha256, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            updated_at TEXT NOT NULL CHECK ({_timestamp_check("updated_at")}),
            PRIMARY KEY (snapshot_id, snapshot_revision),
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (definition_revision_id) REFERENCES workflow_definitions (definition_revision_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (project_id, workflow_run_id, snapshot_revision),
            UNIQUE (snapshot_id, snapshot_revision, project_id, workflow_run_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE workflow_queue_jobs (
            job_id TEXT PRIMARY KEY CHECK ({_uuid_check("job_id", "7")}),
            project_id TEXT NOT NULL,
            workflow_run_id TEXT NOT NULL CHECK ({_uuid_check("workflow_run_id", "7")}),
            snapshot_id TEXT NOT NULL CHECK ({_uuid_check("snapshot_id", "7")}),
            snapshot_revision INTEGER NOT NULL CHECK (snapshot_revision BETWEEN 1 AND {MAX_SAFE_INTEGER}),
            step_run_id TEXT NOT NULL CHECK ({_uuid_check("step_run_id", "7")}),
            activity_type TEXT NOT NULL CHECK ({_identifier_check("activity_type", 96)}),
            concurrency_class TEXT NOT NULL CHECK (
                concurrency_class IN ('interactive', 'document', 'ai', 'maintenance')
            ),
            progress_unit TEXT NOT NULL CHECK ({_identifier_check("progress_unit", 96)}),
            progress_total_kind TEXT NOT NULL CHECK (
                progress_total_kind IN ('known', 'unknown', 'not-applicable')
            ),
            progress_total_units INTEGER CHECK (
                progress_total_units IS NULL OR progress_total_units BETWEEN 0 AND {MAX_SAFE_INTEGER}
            ),
            checkpoint_mode TEXT NOT NULL CHECK (checkpoint_mode IN ('forbidden', 'optional', 'required')),
            partial_artifact_disposition TEXT NOT NULL CHECK (
                partial_artifact_disposition IN ('retained-incomplete', 'quarantined', 'discarded')
            ),
            state TEXT NOT NULL CHECK (state IN (
                'runnable', 'claimed', 'running', 'retry-scheduled', 'cancelling',
                'cancelled', 'failed', 'succeeded'
            )),
            priority INTEGER NOT NULL CHECK (priority BETWEEN -1000 AND 1000),
            available_at TEXT NOT NULL CHECK ({_timestamp_check("available_at")}),
            max_attempts INTEGER NOT NULL CHECK (max_attempts BETWEEN 1 AND 32),
            attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count BETWEEN 0 AND 32),
            initial_backoff_ms INTEGER NOT NULL CHECK (initial_backoff_ms BETWEEN 0 AND 86400000),
            maximum_backoff_ms INTEGER NOT NULL CHECK (maximum_backoff_ms BETWEEN 0 AND 604800000),
            multiplier_basis_points INTEGER NOT NULL CHECK (multiplier_basis_points BETWEEN 10000 AND 100000),
            deterministic_jitter INTEGER NOT NULL CHECK (deterministic_jitter IN (0, 1)),
            retryable_error_codes_json TEXT NOT NULL CHECK (length(retryable_error_codes_json) BETWEEN 2 AND 16384),
            non_retryable_error_codes_json TEXT NOT NULL CHECK (
                length(non_retryable_error_codes_json) BETWEEN 2 AND 16384
            ),
            idempotency_key TEXT NOT NULL CHECK (
                length(idempotency_key) = 71 AND substr(idempotency_key, 1, 7) = 'sha256:'
                AND substr(idempotency_key, 8) = lower(substr(idempotency_key, 8))
                AND substr(idempotency_key, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            command_fingerprint TEXT NOT NULL CHECK (
                length(command_fingerprint) = 71 AND substr(command_fingerprint, 1, 7) = 'sha256:'
                AND substr(command_fingerprint, 8) = lower(substr(command_fingerprint, 8))
                AND substr(command_fingerprint, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            current_attempt_id TEXT CHECK (current_attempt_id IS NULL OR ({_uuid_check("current_attempt_id", "7")})),
            lease_generation INTEGER NOT NULL DEFAULT 0 CHECK (
                lease_generation BETWEEN 0 AND {MAX_SAFE_INTEGER}
            ),
            lease_owner TEXT CHECK (lease_owner IS NULL OR ({_uuid_check("lease_owner", "7")})),
            lease_token_sha256 TEXT CHECK (lease_token_sha256 IS NULL OR ({_sha256_check("lease_token_sha256")})),
            lease_expires_at TEXT CHECK (lease_expires_at IS NULL OR ({_timestamp_check("lease_expires_at")})),
            heartbeat_at TEXT CHECK (heartbeat_at IS NULL OR ({_timestamp_check("heartbeat_at")})),
            cancellation_requested_at TEXT CHECK (
                cancellation_requested_at IS NULL OR ({_timestamp_check("cancellation_requested_at")})
            ),
            cancellation_reason_code TEXT CHECK (
                cancellation_reason_code IS NULL OR ({_identifier_check("cancellation_reason_code", 96)})
            ),
            interruption_kind TEXT CHECK (
                interruption_kind IS NULL OR interruption_kind IN (
                    'ordinary-restart', 'user-cancel', 'security-lock', 'policy', 'dependency'
                )
            ),
            diagnostic_code TEXT CHECK (diagnostic_code IS NULL OR ({_identifier_check("diagnostic_code", 96)})),
            committed_output_sha256 TEXT CHECK (
                committed_output_sha256 IS NULL OR (
                    length(committed_output_sha256) = 71 AND substr(committed_output_sha256, 1, 7) = 'sha256:'
                    AND substr(committed_output_sha256, 8) = lower(substr(committed_output_sha256, 8))
                    AND substr(committed_output_sha256, 8) NOT GLOB '*[^0-9a-f]*'
                )
            ),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            updated_at TEXT NOT NULL CHECK ({_timestamp_check("updated_at")}),
            FOREIGN KEY (snapshot_id, snapshot_revision, project_id, workflow_run_id)
                REFERENCES workflow_authority_snapshots (snapshot_id, snapshot_revision, project_id, workflow_run_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (project_id, idempotency_key),
            CHECK (attempt_count <= max_attempts),
            CHECK ((progress_total_kind = 'known') = (progress_total_units IS NOT NULL)),
            CHECK (
                (state IN ('claimed', 'running', 'cancelling') AND current_attempt_id IS NOT NULL
                    AND lease_owner IS NOT NULL AND lease_token_sha256 IS NOT NULL AND lease_expires_at IS NOT NULL)
                OR (state NOT IN ('claimed', 'running', 'cancelling')
                    AND lease_owner IS NULL AND lease_token_sha256 IS NULL AND lease_expires_at IS NULL)
            ),
            CHECK ((state = 'succeeded') = (committed_output_sha256 IS NOT NULL))
        ) STRICT
    """,
    f"""
        CREATE TABLE workflow_job_attempts (
            attempt_id TEXT PRIMARY KEY CHECK ({_uuid_check("attempt_id", "7")}),
            project_id TEXT NOT NULL,
            job_id TEXT NOT NULL CHECK ({_uuid_check("job_id", "7")}),
            attempt_number INTEGER NOT NULL CHECK (attempt_number BETWEEN 1 AND 32),
            state TEXT NOT NULL CHECK (state IN (
                'claimed', 'running', 'succeeded', 'failed', 'cancelled', 'abandoned'
            )),
            worker_id TEXT NOT NULL CHECK ({_uuid_check("worker_id", "7")}),
            lease_generation INTEGER NOT NULL CHECK (lease_generation BETWEEN 1 AND {MAX_SAFE_INTEGER}),
            lease_token_sha256 TEXT NOT NULL CHECK ({_sha256_check("lease_token_sha256")}),
            lease_expires_at TEXT NOT NULL CHECK ({_timestamp_check("lease_expires_at")}),
            heartbeat_at TEXT NOT NULL CHECK ({_timestamp_check("heartbeat_at")}),
            progress_json TEXT,
            started_at TEXT CHECK (started_at IS NULL OR ({_timestamp_check("started_at")})),
            ended_at TEXT CHECK (ended_at IS NULL OR ({_timestamp_check("ended_at")})),
            diagnostic_code TEXT CHECK (diagnostic_code IS NULL OR ({_identifier_check("diagnostic_code", 96)})),
            FOREIGN KEY (job_id) REFERENCES workflow_queue_jobs (job_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (job_id, attempt_number),
            UNIQUE (job_id, lease_generation),
            CHECK ((state IN ('succeeded', 'failed', 'cancelled', 'abandoned')) = (ended_at IS NOT NULL))
        ) STRICT
    """,
    f"""
        CREATE TABLE workflow_attempt_artifacts (
            attempt_id TEXT NOT NULL CHECK ({_uuid_check("attempt_id", "7")}),
            project_id TEXT NOT NULL,
            job_id TEXT NOT NULL CHECK ({_uuid_check("job_id", "7")}),
            artifact_id TEXT NOT NULL CHECK ({_uuid_check("artifact_id", "7")}),
            revision_id TEXT NOT NULL CHECK ({_uuid_check("revision_id", "7")}),
            role TEXT NOT NULL CHECK (role IN ('output', 'checkpoint', 'diagnostic')),
            disposition TEXT NOT NULL CHECK (
                disposition IN ('committed', 'retained-incomplete', 'quarantined', 'discarded')
            ),
            content_hash TEXT NOT NULL CHECK (
                length(content_hash) = 71 AND substr(content_hash, 1, 7) = 'sha256:'
                AND substr(content_hash, 8) = lower(substr(content_hash, 8))
                AND substr(content_hash, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            media_type TEXT NOT NULL CHECK (length(media_type) BETWEEN 3 AND 100),
            provenance_entity_id TEXT CHECK (
                provenance_entity_id IS NULL OR ({_uuid_check("provenance_entity_id", "7")})
            ),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            updated_at TEXT NOT NULL CHECK ({_timestamp_check("updated_at")}),
            PRIMARY KEY (attempt_id, artifact_id),
            FOREIGN KEY (attempt_id) REFERENCES workflow_job_attempts (attempt_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (job_id) REFERENCES workflow_queue_jobs (job_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (revision_id, project_id) REFERENCES aggregate_revisions (revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (attempt_id, revision_id),
            CHECK (provenance_entity_id IS NULL OR provenance_entity_id = artifact_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE workflow_history_events (
            event_id TEXT PRIMARY KEY CHECK ({_uuid_check("event_id", "7")}),
            project_id TEXT NOT NULL,
            workflow_run_id TEXT NOT NULL CHECK ({_uuid_check("workflow_run_id", "7")}),
            job_id TEXT CHECK (job_id IS NULL OR ({_uuid_check("job_id", "7")})),
            attempt_id TEXT CHECK (attempt_id IS NULL OR ({_uuid_check("attempt_id", "7")})),
            sequence INTEGER NOT NULL CHECK (sequence BETWEEN 1 AND {MAX_SAFE_INTEGER}),
            entity_type TEXT NOT NULL CHECK (
                entity_type IN ('workflow-run', 'workflow-step', 'job', 'job-attempt', 'human-task')
            ),
            entity_id TEXT NOT NULL CHECK ({_uuid_check("entity_id", "7")}),
            from_state TEXT,
            to_state TEXT NOT NULL CHECK ({_identifier_check("to_state", 96)}),
            occurred_at TEXT NOT NULL CHECK ({_timestamp_check("occurred_at")}),
            actor_json TEXT NOT NULL CHECK (length(actor_json) BETWEEN 2 AND 4096),
            reason_code TEXT NOT NULL CHECK ({_identifier_check("reason_code", 96)}),
            event_json TEXT NOT NULL CHECK (length(event_json) BETWEEN 2 AND 65536),
            record_sha256 TEXT NOT NULL CHECK (
                length(record_sha256) = 71 AND substr(record_sha256, 1, 7) = 'sha256:'
                AND substr(record_sha256, 8) = lower(substr(record_sha256, 8))
                AND substr(record_sha256, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (job_id) REFERENCES workflow_queue_jobs (job_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (attempt_id) REFERENCES workflow_job_attempts (attempt_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (project_id, workflow_run_id, sequence)
        ) STRICT
    """,
    f"""
        CREATE TABLE workflow_checkpoints (
            checkpoint_id TEXT PRIMARY KEY CHECK ({_uuid_check("checkpoint_id", "7")}),
            project_id TEXT NOT NULL,
            job_id TEXT NOT NULL CHECK ({_uuid_check("job_id", "7")}),
            attempt_id TEXT NOT NULL CHECK ({_uuid_check("attempt_id", "7")}),
            checkpoint_sequence INTEGER NOT NULL CHECK (
                checkpoint_sequence BETWEEN 1 AND {MAX_SAFE_INTEGER}
            ),
            history_sequence INTEGER NOT NULL CHECK (history_sequence BETWEEN 1 AND {MAX_SAFE_INTEGER}),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            state_hash TEXT NOT NULL CHECK (
                length(state_hash) = 71 AND substr(state_hash, 1, 7) = 'sha256:'
                AND substr(state_hash, 8) = lower(substr(state_hash, 8))
                AND substr(state_hash, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            payload_artifact_id TEXT NOT NULL CHECK ({_uuid_check("payload_artifact_id", "7")}),
            FOREIGN KEY (job_id) REFERENCES workflow_queue_jobs (job_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (attempt_id) REFERENCES workflow_job_attempts (attempt_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (attempt_id, payload_artifact_id)
                REFERENCES workflow_attempt_artifacts (attempt_id, artifact_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (attempt_id, checkpoint_sequence)
        ) STRICT
    """,
    f"""
        CREATE TABLE workflow_committed_outputs (
            job_id TEXT PRIMARY KEY CHECK ({_uuid_check("job_id", "7")}),
            project_id TEXT NOT NULL,
            attempt_id TEXT NOT NULL CHECK ({_uuid_check("attempt_id", "7")}),
            idempotency_key TEXT NOT NULL,
            command_fingerprint TEXT NOT NULL,
            output_manifest_json TEXT NOT NULL CHECK (length(output_manifest_json) BETWEEN 2 AND 1048576),
            output_record_sha256 TEXT NOT NULL CHECK (
                length(output_record_sha256) = 71 AND substr(output_record_sha256, 1, 7) = 'sha256:'
                AND substr(output_record_sha256, 8) = lower(substr(output_record_sha256, 8))
                AND substr(output_record_sha256, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            committed_at TEXT NOT NULL CHECK ({_timestamp_check("committed_at")}),
            provenance_event_id TEXT NOT NULL CHECK ({_uuid_check("provenance_event_id", "7")}),
            outbox_id TEXT NOT NULL CHECK ({_uuid_check("outbox_id", "7")}),
            FOREIGN KEY (job_id) REFERENCES workflow_queue_jobs (job_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (attempt_id) REFERENCES workflow_job_attempts (attempt_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (provenance_event_id) REFERENCES provenance_events (event_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (outbox_id) REFERENCES outbox_events (outbox_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (project_id, idempotency_key)
        ) STRICT
    """,
    *(
        statement
        for table, message in (
            ("workflow_definitions", "workflow definitions are immutable"),
            ("workflow_authority_snapshots", "workflow authority snapshots are immutable"),
            ("workflow_history_events", "workflow history is append-only"),
            ("workflow_checkpoints", "workflow checkpoints are append-only"),
            ("workflow_committed_outputs", "workflow committed outputs are immutable"),
        )
        for statement in _immutable_triggers(table, message)
    ),
    """
        CREATE TRIGGER workflow_queue_jobs_identity_immutable
        BEFORE UPDATE ON workflow_queue_jobs
        WHEN NEW.job_id <> OLD.job_id OR NEW.project_id <> OLD.project_id
          OR NEW.workflow_run_id <> OLD.workflow_run_id OR NEW.snapshot_id <> OLD.snapshot_id
          OR NEW.snapshot_revision <> OLD.snapshot_revision OR NEW.step_run_id <> OLD.step_run_id
          OR NEW.activity_type <> OLD.activity_type OR NEW.concurrency_class <> OLD.concurrency_class
          OR NEW.progress_unit <> OLD.progress_unit OR NEW.progress_total_kind <> OLD.progress_total_kind
          OR NEW.progress_total_units IS NOT OLD.progress_total_units OR NEW.checkpoint_mode <> OLD.checkpoint_mode
          OR NEW.partial_artifact_disposition <> OLD.partial_artifact_disposition
          OR NEW.idempotency_key <> OLD.idempotency_key OR NEW.command_fingerprint <> OLD.command_fingerprint
          OR NEW.max_attempts <> OLD.max_attempts
        BEGIN
            SELECT RAISE(ABORT, 'workflow queue authority is immutable');
        END
    """,
    """
        CREATE TRIGGER workflow_attempt_artifacts_identity_immutable
        BEFORE UPDATE ON workflow_attempt_artifacts
        WHEN NEW.attempt_id <> OLD.attempt_id OR NEW.project_id <> OLD.project_id
          OR NEW.job_id <> OLD.job_id OR NEW.artifact_id <> OLD.artifact_id
          OR NEW.revision_id <> OLD.revision_id OR NEW.role <> OLD.role
          OR NEW.content_hash <> OLD.content_hash OR NEW.media_type <> OLD.media_type
          OR NEW.provenance_entity_id IS NOT OLD.provenance_entity_id OR NEW.created_at <> OLD.created_at
        BEGIN
            SELECT RAISE(ABORT, 'workflow artifact authority is immutable');
        END
    """,
    """
        CREATE TRIGGER workflow_attempt_artifacts_disposition_transition
        BEFORE UPDATE OF disposition ON workflow_attempt_artifacts
        WHEN NEW.disposition <> OLD.disposition
         AND NOT (
            OLD.disposition='retained-incomplete'
            AND NEW.disposition IN ('committed', 'quarantined', 'discarded')
         )
        BEGIN
            SELECT RAISE(ABORT, 'workflow artifact disposition transition is invalid');
        END
    """,
    """
        CREATE TRIGGER workflow_checkpoint_artifact_authority
        BEFORE INSERT ON workflow_checkpoints
        WHEN NOT EXISTS (
            SELECT 1 FROM workflow_attempt_artifacts AS artifact
             WHERE artifact.project_id=NEW.project_id AND artifact.job_id=NEW.job_id
               AND artifact.attempt_id=NEW.attempt_id
               AND artifact.artifact_id=NEW.payload_artifact_id
               AND artifact.role='checkpoint' AND artifact.disposition='committed'
               AND artifact.content_hash=NEW.state_hash
        )
        BEGIN
            SELECT RAISE(ABORT, 'workflow checkpoint artifact authority differs');
        END
    """,
    """
        CREATE TRIGGER workflow_job_attempts_identity_immutable
        BEFORE UPDATE ON workflow_job_attempts
        WHEN NEW.attempt_id <> OLD.attempt_id OR NEW.project_id <> OLD.project_id
          OR NEW.job_id <> OLD.job_id OR NEW.attempt_number <> OLD.attempt_number
          OR NEW.worker_id <> OLD.worker_id OR NEW.lease_generation <> OLD.lease_generation
          OR NEW.lease_token_sha256 <> OLD.lease_token_sha256
        BEGIN
            SELECT RAISE(ABORT, 'workflow attempt authority is immutable');
        END
    """,
    "CREATE INDEX workflow_queue_dispatch ON workflow_queue_jobs "
    "(state, concurrency_class, available_at, priority DESC, job_id)",
    "CREATE INDEX workflow_queue_lease_expiry ON workflow_queue_jobs (state, lease_expires_at, job_id)",
    "CREATE INDEX workflow_history_run_sequence ON workflow_history_events (project_id, workflow_run_id, sequence)",
    "CREATE INDEX workflow_checkpoint_attempt_sequence ON workflow_checkpoints (attempt_id, checkpoint_sequence)",
    "CREATE INDEX workflow_artifact_job_disposition ON workflow_attempt_artifacts "
    "(job_id, disposition, role, artifact_id)",
)

MATERIAL_DEPENDENCY_DDL = (
    f"""
        CREATE TABLE material_dependency_outputs (
            output_revision_id TEXT PRIMARY KEY CHECK ({_uuid_check("output_revision_id", "7")}),
            project_id TEXT NOT NULL,
            coverage TEXT NOT NULL CHECK (coverage IN ('not-applicable', 'complete', 'legacy-unreported')),
            registration_event_id TEXT CHECK (
                registration_event_id IS NULL OR ({_uuid_check("registration_event_id", "7")})
            ),
            registered_at TEXT CHECK (registered_at IS NULL OR ({_timestamp_check("registered_at")})),
            FOREIGN KEY (output_revision_id, project_id) REFERENCES aggregate_revisions (revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (registration_event_id) REFERENCES provenance_events (event_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (output_revision_id, project_id),
            CHECK (
                (coverage = 'legacy-unreported' AND registration_event_id IS NULL AND registered_at IS NULL)
                OR (coverage IN ('not-applicable', 'complete')
                    AND registration_event_id IS NOT NULL AND registered_at IS NOT NULL)
            )
        ) STRICT
    """,
    f"""
        CREATE TABLE material_dependencies (
            dependency_id TEXT PRIMARY KEY CHECK ({_uuid_check("dependency_id", "7")}),
            project_id TEXT NOT NULL,
            output_revision_id TEXT NOT NULL CHECK ({_uuid_check("output_revision_id", "7")}),
            dependency_kind TEXT NOT NULL CHECK (dependency_kind IN (
                'source-revision', 'evidence-record', 'ontology-version', 'prompt-version',
                'model-version', 'parameter-set', 'schema-version', 'template-version',
                'code-version', 'human-decision'
            )),
            relation_type TEXT NOT NULL CHECK (relation_type IN ('direct', 'conditional', 'non-material')),
            dependency_revision_id TEXT CHECK (
                dependency_revision_id IS NULL OR ({_uuid_check("dependency_revision_id", "7")})
            ),
            configuration_id TEXT CHECK (
                configuration_id IS NULL OR ({_identifier_check("configuration_id", 128)})
            ),
            configuration_version TEXT CHECK (
                configuration_version IS NULL OR (
                    length(configuration_version) BETWEEN 5 AND 29
                    AND configuration_version GLOB '[0-9]*.[0-9]*.[0-9]*'
                    AND configuration_version NOT GLOB '*[^0-9.]*'
                )
            ),
            fingerprint TEXT NOT NULL CHECK (
                length(fingerprint) = 71 AND substr(fingerprint, 1, 7) = 'sha256:'
                AND substr(fingerprint, 8) = lower(substr(fingerprint, 8))
                AND substr(fingerprint, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            governing_policy_id TEXT NOT NULL CHECK ({_identifier_check("governing_policy_id", 128)}),
            governing_policy_version TEXT NOT NULL CHECK (
                length(governing_policy_version) BETWEEN 5 AND 29
                AND governing_policy_version GLOB '[0-9]*.[0-9]*.[0-9]*'
                AND governing_policy_version NOT GLOB '*[^0-9.]*'
            ),
            semantic_sha256 TEXT NOT NULL CHECK ({_sha256_check("semantic_sha256")}),
            registration_event_id TEXT NOT NULL CHECK ({_uuid_check("registration_event_id", "7")}),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            FOREIGN KEY (output_revision_id, project_id)
                REFERENCES material_dependency_outputs (output_revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (dependency_revision_id, project_id)
                REFERENCES aggregate_revisions (revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (registration_event_id) REFERENCES provenance_events (event_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (project_id, output_revision_id, semantic_sha256),
            CHECK (output_revision_id IS NOT dependency_revision_id),
            CHECK (
                (dependency_revision_id IS NOT NULL
                    AND configuration_id IS NULL AND configuration_version IS NULL
                    AND dependency_kind IN (
                        'source-revision', 'evidence-record', 'ontology-version', 'human-decision'
                    ))
                OR (dependency_revision_id IS NULL
                    AND configuration_id IS NOT NULL AND configuration_version IS NOT NULL
                    AND dependency_kind IN (
                        'prompt-version', 'model-version', 'parameter-set', 'schema-version',
                        'template-version', 'code-version'
                    ))
            )
        ) STRICT
    """,
    f"""
        CREATE TABLE material_dependency_diagnostics (
            diagnostic_id TEXT PRIMARY KEY CHECK ({_uuid_check("diagnostic_id", "7")}),
            project_id TEXT NOT NULL,
            output_revision_id TEXT NOT NULL CHECK ({_uuid_check("output_revision_id", "7")}),
            workflow_run_id TEXT NOT NULL CHECK ({_uuid_check("workflow_run_id", "7")}),
            job_id TEXT NOT NULL CHECK ({_uuid_check("job_id", "7")}),
            attempt_id TEXT NOT NULL CHECK ({_uuid_check("attempt_id", "7")}),
            diagnostic_code TEXT NOT NULL CHECK (diagnostic_code = 'dependency-registration-missing'),
            detected_at TEXT NOT NULL CHECK ({_timestamp_check("detected_at")}),
            FOREIGN KEY (output_revision_id, project_id) REFERENCES aggregate_revisions (revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (job_id) REFERENCES workflow_queue_jobs (job_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (attempt_id) REFERENCES workflow_job_attempts (attempt_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (project_id, job_id, attempt_id, output_revision_id, diagnostic_code)
        ) STRICT
    """,
    *(
        statement
        for table, message in (
            ("material_dependency_outputs", "material dependency coverage is immutable"),
            ("material_dependencies", "material dependencies are append-only"),
            ("material_dependency_diagnostics", "material dependency diagnostics are append-only"),
        )
        for statement in _immutable_triggers(table, message)
    ),
    "CREATE INDEX material_dependency_by_revision ON material_dependencies "
    "(project_id, dependency_revision_id, relation_type, output_revision_id)",
    "CREATE INDEX material_dependency_by_configuration ON material_dependencies "
    "(project_id, configuration_id, configuration_version, relation_type, output_revision_id)",
    "CREATE INDEX material_dependency_diagnostic_output ON material_dependency_diagnostics "
    "(project_id, output_revision_id, detected_at, diagnostic_id)",
)

DEPENDENCY_IMPACT_DDL = (
    f"""
        CREATE TABLE dependency_impact_runs (
            run_id TEXT PRIMARY KEY CHECK ({_uuid_check("run_id", "7")}),
            project_id TEXT NOT NULL,
            change_id TEXT NOT NULL CHECK ({_uuid_check("change_id", "7")}),
            idempotency_key TEXT NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 200),
            reason TEXT NOT NULL CHECK (reason IN (
                'SOURCE_VERSION', 'RIGHTS_POLICY', 'SCHEMA_VERSION',
                'MODEL_OR_PROMPT', 'ONTOLOGY_MAPPING', 'HUMAN_DECISION'
            )),
            dependency_kind TEXT NOT NULL CHECK (dependency_kind IN (
                'source-revision', 'evidence-record', 'ontology-version', 'prompt-version',
                'model-version', 'parameter-set', 'schema-version', 'template-version',
                'code-version', 'human-decision'
            )),
            previous_revision_id TEXT CHECK (
                previous_revision_id IS NULL OR ({_uuid_check("previous_revision_id", "7")})
            ),
            replacement_revision_id TEXT CHECK (
                replacement_revision_id IS NULL OR ({_uuid_check("replacement_revision_id", "7")})
            ),
            configuration_id TEXT CHECK (
                configuration_id IS NULL OR ({_identifier_check("configuration_id", 128)})
            ),
            previous_configuration_version TEXT,
            replacement_configuration_version TEXT,
            previous_fingerprint TEXT NOT NULL CHECK (
                length(previous_fingerprint) = 71 AND substr(previous_fingerprint, 1, 7) = 'sha256:'
                AND substr(previous_fingerprint, 8) = lower(substr(previous_fingerprint, 8))
                AND substr(previous_fingerprint, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            replacement_fingerprint TEXT CHECK (
                replacement_fingerprint IS NULL OR (
                    length(replacement_fingerprint) = 71
                    AND substr(replacement_fingerprint, 1, 7) = 'sha256:'
                    AND substr(replacement_fingerprint, 8) = lower(substr(replacement_fingerprint, 8))
                    AND substr(replacement_fingerprint, 8) NOT GLOB '*[^0-9a-f]*'
                )
            ),
            propagation_policy_id TEXT NOT NULL CHECK ({_identifier_check("propagation_policy_id", 128)}),
            propagation_policy_version TEXT NOT NULL CHECK (
                length(propagation_policy_version) BETWEEN 5 AND 29
                AND propagation_policy_version GLOB '[0-9]*.[0-9]*.[0-9]*'
                AND propagation_policy_version NOT GLOB '*[^0-9.]*'
            ),
            actor_id TEXT NOT NULL CHECK (
                ({_identifier_check("actor_id", 200)}) OR ({_uuid_check("actor_id", "7")})
            ),
            trace_id TEXT NOT NULL CHECK (
                length(trace_id) = 32 AND trace_id = lower(trace_id)
                AND trace_id NOT GLOB '*[^0-9a-f]*'
            ),
            occurred_at TEXT NOT NULL CHECK ({_timestamp_check("occurred_at")}),
            graph_sha256 TEXT NOT NULL CHECK (
                length(graph_sha256) = 71 AND substr(graph_sha256, 1, 7) = 'sha256:'
                AND substr(graph_sha256, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            preview_sha256 TEXT NOT NULL CHECK (
                length(preview_sha256) = 71 AND substr(preview_sha256, 1, 7) = 'sha256:'
                AND substr(preview_sha256, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            authority_sha256 TEXT NOT NULL CHECK (
                length(authority_sha256) = 71 AND substr(authority_sha256, 1, 7) = 'sha256:'
                AND substr(authority_sha256, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            batch_size INTEGER NOT NULL CHECK (batch_size BETWEEN 1 AND 1000),
            total_items INTEGER NOT NULL CHECK (total_items BETWEEN 0 AND {MAX_SAFE_INTEGER}),
            max_nodes INTEGER NOT NULL CHECK (max_nodes BETWEEN 1 AND 20000),
            max_edges INTEGER NOT NULL CHECK (max_edges BETWEEN 1 AND 100000),
            max_depth INTEGER NOT NULL CHECK (max_depth BETWEEN 1 AND 128),
            max_path_samples INTEGER NOT NULL CHECK (max_path_samples BETWEEN 2 AND 64),
            max_legacy_samples INTEGER NOT NULL CHECK (max_legacy_samples BETWEEN 1 AND 100),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (previous_revision_id, project_id)
                REFERENCES aggregate_revisions (revision_id, project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (replacement_revision_id, project_id)
                REFERENCES aggregate_revisions (revision_id, project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (project_id, change_id),
            UNIQUE (project_id, idempotency_key),
            CHECK (
                (previous_revision_id IS NOT NULL AND replacement_revision_id IS NOT NULL
                    AND previous_revision_id <> replacement_revision_id
                    AND configuration_id IS NULL
                    AND previous_configuration_version IS NULL
                    AND replacement_configuration_version IS NULL
                    AND dependency_kind IN (
                        'source-revision', 'evidence-record', 'ontology-version', 'human-decision'
                    ))
                OR (previous_revision_id IS NULL AND replacement_revision_id IS NULL
                    AND configuration_id IS NOT NULL
                    AND previous_configuration_version IS NOT NULL
                    AND replacement_configuration_version IS NOT NULL
                    AND previous_configuration_version <> replacement_configuration_version
                    AND dependency_kind IN (
                        'prompt-version', 'model-version', 'parameter-set', 'schema-version',
                        'template-version', 'code-version'
                    ))
            )
        ) STRICT
    """,
    f"""
        CREATE TABLE dependency_impact_decisions (
            run_id TEXT NOT NULL CHECK ({_uuid_check("run_id", "7")}),
            project_id TEXT NOT NULL,
            dependency_id TEXT NOT NULL CHECK ({_uuid_check("dependency_id", "7")}),
            decision_id TEXT NOT NULL CHECK ({_uuid_check("decision_id", "7")}),
            disposition TEXT NOT NULL CHECK (disposition IN ('propagate', 'ignore')),
            governing_policy_id TEXT NOT NULL CHECK ({_identifier_check("governing_policy_id", 128)}),
            governing_policy_version TEXT NOT NULL CHECK (
                length(governing_policy_version) BETWEEN 5 AND 29
                AND governing_policy_version GLOB '[0-9]*.[0-9]*.[0-9]*'
                AND governing_policy_version NOT GLOB '*[^0-9.]*'
            ),
            actor_id TEXT NOT NULL CHECK (
                ({_identifier_check("actor_id", 200)}) OR ({_uuid_check("actor_id", "7")})
            ),
            decided_at TEXT NOT NULL CHECK ({_timestamp_check("decided_at")}),
            FOREIGN KEY (run_id) REFERENCES dependency_impact_runs (run_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (dependency_id) REFERENCES material_dependencies (dependency_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (project_id) REFERENCES projects (project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            PRIMARY KEY (run_id, decision_id),
            UNIQUE (run_id, dependency_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE dependency_impact_items (
            item_id TEXT PRIMARY KEY CHECK ({_uuid_check("item_id", "7")}),
            run_id TEXT NOT NULL CHECK ({_uuid_check("run_id", "7")}),
            item_sequence INTEGER NOT NULL CHECK (item_sequence BETWEEN 1 AND {MAX_SAFE_INTEGER}),
            project_id TEXT NOT NULL,
            output_revision_id TEXT NOT NULL CHECK ({_uuid_check("output_revision_id", "7")}),
            output_kind TEXT NOT NULL CHECK (output_kind IN (
                'record', 'document', 'workflow', 'evidence', 'ontology', 'decision'
            )),
            disposition TEXT NOT NULL CHECK (disposition IN ('stale', 'unknown-impact')),
            depth INTEGER NOT NULL CHECK (depth BETWEEN 1 AND 128),
            relation_type TEXT NOT NULL CHECK (relation_type IN ('direct', 'conditional')),
            path_json TEXT NOT NULL CHECK (length(path_json) BETWEEN 40 AND 65536),
            path_sha256 TEXT NOT NULL CHECK (
                length(path_sha256) = 71 AND substr(path_sha256, 1, 7) = 'sha256:'
                AND substr(path_sha256, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            path_length INTEGER NOT NULL CHECK (path_length BETWEEN 1 AND 129),
            path_truncated INTEGER NOT NULL CHECK (path_truncated IN (0, 1)),
            cycle_group_id TEXT CHECK (
                cycle_group_id IS NULL OR (
                    length(cycle_group_id) = 71 AND substr(cycle_group_id, 1, 7) = 'sha256:'
                    AND substr(cycle_group_id, 8) NOT GLOB '*[^0-9a-f]*'
                )
            ),
            confidence TEXT NOT NULL CHECK (confidence IN ('confirmed', 'conditional', 'unknown')),
            review_required INTEGER NOT NULL CHECK (review_required IN (0, 1)),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            FOREIGN KEY (run_id) REFERENCES dependency_impact_runs (run_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (output_revision_id, project_id)
                REFERENCES aggregate_revisions (revision_id, project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (run_id, item_sequence),
            UNIQUE (run_id, output_revision_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE dependency_stale_causes (
            cause_id TEXT PRIMARY KEY CHECK ({_uuid_check("cause_id", "7")}),
            run_id TEXT NOT NULL CHECK ({_uuid_check("run_id", "7")}),
            item_sequence INTEGER NOT NULL CHECK (item_sequence BETWEEN 1 AND {MAX_SAFE_INTEGER}),
            project_id TEXT NOT NULL,
            change_id TEXT NOT NULL CHECK ({_uuid_check("change_id", "7")}),
            output_revision_id TEXT NOT NULL CHECK ({_uuid_check("output_revision_id", "7")}),
            disposition TEXT NOT NULL CHECK (disposition IN ('stale', 'unknown-impact')),
            reason TEXT NOT NULL CHECK (reason IN (
                'SOURCE_VERSION', 'RIGHTS_POLICY', 'SCHEMA_VERSION',
                'MODEL_OR_PROMPT', 'ONTOLOGY_MAPPING', 'HUMAN_DECISION'
            )),
            propagation_policy_id TEXT NOT NULL CHECK ({_identifier_check("propagation_policy_id", 128)}),
            propagation_policy_version TEXT NOT NULL CHECK (
                length(propagation_policy_version) BETWEEN 5 AND 29
                AND propagation_policy_version GLOB '[0-9]*.[0-9]*.[0-9]*'
                AND propagation_policy_version NOT GLOB '*[^0-9.]*'
            ),
            depth INTEGER NOT NULL CHECK (depth BETWEEN 1 AND 128),
            path_json TEXT NOT NULL CHECK (length(path_json) BETWEEN 40 AND 65536),
            path_sha256 TEXT NOT NULL CHECK (
                length(path_sha256) = 71 AND substr(path_sha256, 1, 7) = 'sha256:'
                AND substr(path_sha256, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            path_length INTEGER NOT NULL CHECK (path_length BETWEEN 1 AND 129),
            path_truncated INTEGER NOT NULL CHECK (path_truncated IN (0, 1)),
            cycle_group_id TEXT CHECK (
                cycle_group_id IS NULL OR (
                    length(cycle_group_id) = 71 AND substr(cycle_group_id, 1, 7) = 'sha256:'
                    AND substr(cycle_group_id, 8) NOT GLOB '*[^0-9a-f]*'
                )
            ),
            confidence TEXT NOT NULL CHECK (confidence IN ('confirmed', 'conditional', 'unknown')),
            review_required INTEGER NOT NULL CHECK (review_required IN (0, 1)),
            detected_at TEXT NOT NULL CHECK ({_timestamp_check("detected_at")}),
            resolution_state TEXT NOT NULL CHECK (resolution_state = 'open'),
            FOREIGN KEY (run_id, item_sequence)
                REFERENCES dependency_impact_items (run_id, item_sequence)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (output_revision_id, project_id)
                REFERENCES aggregate_revisions (revision_id, project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (run_id, item_sequence),
            UNIQUE (project_id, change_id, output_revision_id, propagation_policy_id, propagation_policy_version)
        ) STRICT
    """,
    f"""
        CREATE TABLE dependency_impact_audit_events (
            event_id TEXT PRIMARY KEY CHECK ({_uuid_check("event_id", "7")}),
            run_id TEXT NOT NULL CHECK ({_uuid_check("run_id", "7")}),
            project_id TEXT NOT NULL,
            sequence INTEGER NOT NULL CHECK (sequence BETWEEN 1 AND {MAX_SAFE_INTEGER}),
            event_type TEXT NOT NULL CHECK (
                event_type IN ('started', 'checkpoint', 'failed-attempt', 'completed', 'cancelled')
            ),
            processed_items INTEGER NOT NULL CHECK (processed_items BETWEEN 0 AND {MAX_SAFE_INTEGER}),
            stale_count INTEGER NOT NULL CHECK (stale_count BETWEEN 0 AND {MAX_SAFE_INTEGER}),
            unknown_count INTEGER NOT NULL CHECK (unknown_count BETWEEN 0 AND {MAX_SAFE_INTEGER}),
            checkpoint_sha256 TEXT NOT NULL CHECK (
                length(checkpoint_sha256) = 71 AND substr(checkpoint_sha256, 1, 7) = 'sha256:'
                AND substr(checkpoint_sha256, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            occurred_at TEXT NOT NULL CHECK ({_timestamp_check("occurred_at")}),
            FOREIGN KEY (run_id) REFERENCES dependency_impact_runs (run_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (run_id, sequence)
        ) STRICT
    """,
    *(
        statement
        for table, message in (
            ("dependency_impact_runs", "dependency impact runs are append-only"),
            ("dependency_impact_decisions", "dependency impact decisions are append-only"),
            ("dependency_impact_items", "dependency impact items are append-only"),
            ("dependency_stale_causes", "dependency stale causes are append-only"),
            ("dependency_impact_audit_events", "dependency impact audit events are append-only"),
        )
        for statement in _immutable_triggers(table, message)
    ),
    "CREATE INDEX dependency_impact_run_change ON dependency_impact_runs (project_id, change_id, run_id)",
    "CREATE INDEX dependency_impact_decision_run ON dependency_impact_decisions (project_id, run_id, dependency_id)",
    "CREATE INDEX dependency_impact_item_sequence ON dependency_impact_items (project_id, run_id, item_sequence)",
    "CREATE INDEX dependency_stale_output ON dependency_stale_causes "
    "(project_id, output_revision_id, resolution_state, detected_at, cause_id)",
    "CREATE INDEX dependency_impact_audit_sequence ON dependency_impact_audit_events (project_id, run_id, sequence)",
)

IMPORT_PREVIEW_DDL = (
    f"""
        CREATE TABLE import_previews (
            preview_id TEXT NOT NULL CHECK ({_uuid_check("preview_id", "7")}),
            project_id TEXT NOT NULL,
            source_name TEXT NOT NULL CHECK (length(source_name) BETWEEN 1 AND 255
                AND instr(source_name, '/') = 0 AND instr(source_name, char(92)) = 0
                AND instr(source_name, ':') = 0 AND source_name NOT IN ('.', '..')),
            format_name TEXT NOT NULL CHECK (format_name IN ('ris', 'bibtex', 'csl-json', 'doi-list', 'csv')),
            encoding TEXT NOT NULL CHECK (encoding IN ('utf-8', 'cp1252')),
            initial_rights_json TEXT NOT NULL CHECK (length(initial_rights_json) BETWEEN 2 AND 4096),
            actor_id TEXT NOT NULL CHECK ({_uuid_check("actor_id", "7")}),
            trace_id TEXT NOT NULL CHECK (length(trace_id) = 32 AND trace_id NOT GLOB '*[^0-9a-f]*'),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            PRIMARY KEY (preview_id, project_id),
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    """
        CREATE TABLE import_source_chunks (
            preview_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL CHECK (ordinal BETWEEN 1 AND 2048),
            object_sha256 TEXT NOT NULL,
            byte_length INTEGER NOT NULL CHECK (byte_length BETWEEN 1 AND 131072),
            PRIMARY KEY (preview_id, project_id, ordinal),
            FOREIGN KEY (preview_id, project_id) REFERENCES import_previews (preview_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (object_sha256, project_id) REFERENCES object_records (object_sha256, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    f"""
        CREATE TABLE import_source_seals (
            preview_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64
                AND source_sha256 NOT GLOB '*[^0-9a-f]*'),
            manifest_sha256 TEXT NOT NULL CHECK (length(manifest_sha256) = 64
                AND manifest_sha256 NOT GLOB '*[^0-9a-f]*'),
            byte_length INTEGER NOT NULL CHECK (byte_length BETWEEN 0 AND 268435456),
            chunk_count INTEGER NOT NULL CHECK (chunk_count BETWEEN 0 AND 2048),
            sealed_at TEXT NOT NULL CHECK ({_timestamp_check("sealed_at")}),
            PRIMARY KEY (preview_id, project_id),
            FOREIGN KEY (preview_id, project_id) REFERENCES import_previews (preview_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    f"""
        CREATE TABLE import_parse_attempts (
            preview_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            attempt_id TEXT NOT NULL CHECK ({_uuid_check("attempt_id", "7")}),
            job_id TEXT NOT NULL CHECK ({_uuid_check("job_id", "7")}),
            parser_version TEXT NOT NULL CHECK (parser_version = 'local-reference-imports/1.0.0'),
            started_at TEXT NOT NULL CHECK ({_timestamp_check("started_at")}),
            PRIMARY KEY (preview_id, project_id, attempt_id),
            UNIQUE (attempt_id),
            FOREIGN KEY (preview_id, project_id) REFERENCES import_source_seals (preview_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (job_id) REFERENCES workflow_queue_jobs (job_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (attempt_id) REFERENCES workflow_job_attempts (attempt_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    """
        CREATE TABLE import_parse_records (
            preview_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            attempt_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL CHECK (ordinal BETWEEN 1 AND 200000),
            record_key TEXT NOT NULL CHECK (length(record_key) = 64 AND record_key NOT GLOB '*[^0-9a-f]*'),
            record_json TEXT NOT NULL CHECK (length(record_json) BETWEEN 2 AND 8388608),
            PRIMARY KEY (preview_id, project_id, attempt_id, ordinal),
            UNIQUE (preview_id, project_id, attempt_id, ordinal, record_key),
            FOREIGN KEY (preview_id, project_id, attempt_id)
                REFERENCES import_parse_attempts (preview_id, project_id, attempt_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    f"""
        CREATE TABLE import_parse_completions (
            preview_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            attempt_id TEXT NOT NULL,
            receipt_revision_id TEXT NOT NULL CHECK ({_uuid_check("receipt_revision_id", "7")}),
            record_count INTEGER NOT NULL CHECK (record_count BETWEEN 0 AND 200000),
            source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64
                AND source_sha256 NOT GLOB '*[^0-9a-f]*'),
            completed_at TEXT NOT NULL CHECK ({_timestamp_check("completed_at")}),
            PRIMARY KEY (preview_id, project_id, attempt_id),
            UNIQUE (project_id, receipt_revision_id),
            FOREIGN KEY (receipt_revision_id, project_id)
                REFERENCES aggregate_revisions (revision_id, project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (preview_id, project_id, attempt_id)
                REFERENCES import_parse_attempts (preview_id, project_id, attempt_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    f"""
        CREATE TABLE import_draft_revisions (
            preview_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            revision INTEGER NOT NULL CHECK (revision BETWEEN 1 AND 2147483647),
            predecessor_revision INTEGER,
            attempt_id TEXT NOT NULL,
            mapping_json TEXT NOT NULL CHECK (length(mapping_json) BETWEEN 2 AND 1048576),
            rights_json TEXT NOT NULL CHECK (length(rights_json) BETWEEN 2 AND 4096),
            options_json TEXT NOT NULL CHECK (length(options_json) BETWEEN 2 AND 4096),
            undo_revision INTEGER CHECK (undo_revision IS NULL OR (undo_revision >= 1 AND undo_revision < revision)),
            actor_id TEXT NOT NULL CHECK ({_uuid_check("actor_id", "7")}),
            trace_id TEXT NOT NULL CHECK (length(trace_id) = 32 AND trace_id NOT GLOB '*[^0-9a-f]*'),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            PRIMARY KEY (preview_id, project_id, revision),
            UNIQUE (preview_id, project_id, revision, attempt_id),
            CHECK ((revision = 1 AND predecessor_revision IS NULL)
                OR (revision > 1 AND predecessor_revision IS NOT NULL AND predecessor_revision = revision - 1)),
            FOREIGN KEY (preview_id, project_id, predecessor_revision)
                REFERENCES import_draft_revisions (preview_id, project_id, revision)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (preview_id, project_id, undo_revision)
                REFERENCES import_draft_revisions (preview_id, project_id, revision)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (preview_id, project_id, attempt_id)
                REFERENCES import_parse_completions (preview_id, project_id, attempt_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    """
        CREATE TABLE import_record_decisions (
            preview_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            revision INTEGER NOT NULL,
            attempt_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            record_key TEXT NOT NULL,
            decision_json TEXT NOT NULL CHECK (length(decision_json) BETWEEN 2 AND 8388608),
            PRIMARY KEY (preview_id, project_id, revision, ordinal),
            FOREIGN KEY (preview_id, project_id, revision, attempt_id)
                REFERENCES import_draft_revisions (preview_id, project_id, revision, attempt_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (preview_id, project_id, attempt_id, ordinal, record_key)
                REFERENCES import_parse_records (preview_id, project_id, attempt_id, ordinal, record_key)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    f"""
        CREATE TABLE import_preview_events (
            preview_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            sequence INTEGER NOT NULL CHECK (sequence BETWEEN 1 AND 2147483647),
            event_type TEXT NOT NULL CHECK (event_type IN (
                'created', 'source-sealed', 'parse-started', 'parse-completed',
                'draft-revised', 'cancelled', 'failed', 'security-interrupted'
            )),
            actor_id TEXT NOT NULL CHECK ({_uuid_check("actor_id", "7")}),
            trace_id TEXT NOT NULL CHECK (length(trace_id) = 32 AND trace_id NOT GLOB '*[^0-9a-f]*'),
            occurred_at TEXT NOT NULL CHECK ({_timestamp_check("occurred_at")}),
            PRIMARY KEY (preview_id, project_id, sequence),
            FOREIGN KEY (preview_id, project_id) REFERENCES import_previews (preview_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    *(
        statement
        for table in IMPORT_PREVIEW_TABLES
        for statement in _immutable_triggers(table, "import preview history is append-only")
    ),
    """
        CREATE TRIGGER import_chunk_membership BEFORE INSERT ON import_source_chunks
        WHEN EXISTS (SELECT 1 FROM import_source_seals
                      WHERE preview_id=NEW.preview_id AND project_id=NEW.project_id)
          OR NEW.ordinal <> (SELECT COUNT(*) + 1 FROM import_source_chunks
                              WHERE preview_id=NEW.preview_id AND project_id=NEW.project_id)
          OR EXISTS (SELECT 1 FROM import_source_chunks
                      WHERE preview_id=NEW.preview_id AND project_id=NEW.project_id AND byte_length <> 131072)
          OR NOT EXISTS (SELECT 1 FROM object_records
                          WHERE project_id=NEW.project_id AND object_sha256=NEW.object_sha256
                            AND byte_length=NEW.byte_length AND storage_state='available'
                            AND protection_profile='project-encrypted-v1' AND retention_class='project-lifetime')
        BEGIN SELECT RAISE(ABORT, 'import chunk membership denied'); END
    """,
    """
        CREATE TRIGGER import_seal_membership BEFORE INSERT ON import_source_seals
        WHEN NEW.chunk_count <> (SELECT COUNT(*) FROM import_source_chunks
                                  WHERE preview_id=NEW.preview_id AND project_id=NEW.project_id)
          OR NEW.byte_length <> (SELECT COALESCE(SUM(byte_length), 0) FROM import_source_chunks
                                  WHERE preview_id=NEW.preview_id AND project_id=NEW.project_id)
        BEGIN SELECT RAISE(ABORT, 'import source seal denied'); END
    """,
    """
        CREATE TRIGGER import_attempt_binding BEFORE INSERT ON import_parse_attempts
        WHEN NOT EXISTS (
            SELECT 1 FROM workflow_job_attempts a JOIN workflow_queue_jobs j ON j.job_id=a.job_id
             WHERE a.attempt_id=NEW.attempt_id AND a.job_id=NEW.job_id
               AND a.project_id=NEW.project_id AND j.project_id=NEW.project_id
               AND j.current_attempt_id=a.attempt_id AND a.state='running' AND j.state='running'
               AND j.cancellation_requested_at IS NULL
        )
        BEGIN SELECT RAISE(ABORT, 'import attempt binding denied'); END
    """,
    """
        CREATE TRIGGER import_record_membership BEFORE INSERT ON import_parse_records
        WHEN EXISTS (SELECT 1 FROM import_parse_completions WHERE preview_id=NEW.preview_id
                      AND project_id=NEW.project_id AND attempt_id=NEW.attempt_id)
          OR NEW.ordinal <> (SELECT COALESCE(MAX(ordinal), 0) + 1 FROM import_parse_records
                              WHERE preview_id=NEW.preview_id AND project_id=NEW.project_id
                                AND attempt_id=NEW.attempt_id)
        BEGIN SELECT RAISE(ABORT, 'import record membership denied'); END
    """,
    """
        CREATE TRIGGER import_completion_membership BEFORE INSERT ON import_parse_completions
        WHEN NEW.record_count <> (SELECT COUNT(*) FROM import_parse_records
                                   WHERE preview_id=NEW.preview_id AND project_id=NEW.project_id
                                     AND attempt_id=NEW.attempt_id)
          OR NOT EXISTS (SELECT 1 FROM import_source_seals WHERE preview_id=NEW.preview_id
                          AND project_id=NEW.project_id AND source_sha256=NEW.source_sha256)
        BEGIN SELECT RAISE(ABORT, 'import completion membership denied'); END
    """,
    "CREATE INDEX import_chunk_object ON import_source_chunks (project_id, object_sha256)",
    "CREATE INDEX import_decision_record ON import_record_decisions (preview_id, project_id, ordinal, revision)",
)

IMPORT_SUMMARY_DDL = (
    f"""
        CREATE TABLE import_summary_attempts (
            preview_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            summary_attempt_id TEXT NOT NULL CHECK ({_uuid_check("summary_attempt_id", "7")}),
            job_id TEXT NOT NULL CHECK ({_uuid_check("job_id", "7")}),
            parse_attempt_id TEXT NOT NULL,
            draft_revision INTEGER NOT NULL CHECK (draft_revision BETWEEN 1 AND 2147483647),
            algorithm_version TEXT NOT NULL CHECK (algorithm_version='draft-summary/1'),
            started_at TEXT NOT NULL CHECK ({_timestamp_check("started_at")}),
            PRIMARY KEY (preview_id, project_id, summary_attempt_id),
            UNIQUE (summary_attempt_id),
            UNIQUE (preview_id, project_id, summary_attempt_id, parse_attempt_id),
            FOREIGN KEY (preview_id, project_id, draft_revision, parse_attempt_id)
                REFERENCES import_draft_revisions (preview_id, project_id, revision, attempt_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (job_id) REFERENCES workflow_queue_jobs (job_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (summary_attempt_id) REFERENCES workflow_job_attempts (attempt_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    """
        CREATE TABLE import_summary_rows (
            preview_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            summary_attempt_id TEXT NOT NULL,
            parse_attempt_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL CHECK (ordinal BETWEEN 1 AND 200000),
            record_key TEXT NOT NULL,
            record_kind TEXT NOT NULL CHECK (record_kind IN ('record', 'header', 'directive')),
            parse_status TEXT NOT NULL CHECK (parse_status IN ('parsed', 'malformed')),
            included INTEGER NOT NULL CHECK (included IN (0, 1)),
            warning_count INTEGER NOT NULL CHECK (warning_count BETWEEN 0 AND 64),
            coverage_mask INTEGER NOT NULL CHECK (coverage_mask BETWEEN 0 AND 31),
            raw_key TEXT CHECK (raw_key IS NULL OR (length(raw_key)=64 AND raw_key NOT GLOB '*[^0-9a-f]*')),
            doi_key TEXT CHECK (doi_key IS NULL OR (length(doi_key)=64 AND doi_key NOT GLOB '*[^0-9a-f]*')),
            PRIMARY KEY (preview_id, project_id, summary_attempt_id, ordinal),
            CHECK (included=0 OR (record_kind='record' AND parse_status='parsed')),
            CHECK ((included=0 AND raw_key IS NULL AND doi_key IS NULL AND coverage_mask=0)
                OR (included=1 AND raw_key IS NOT NULL)),
            CHECK ((coverage_mask & 2)=0 AND doi_key IS NULL OR (coverage_mask & 2)=2 AND doi_key IS NOT NULL),
            FOREIGN KEY (preview_id, project_id, summary_attempt_id, parse_attempt_id)
                REFERENCES import_summary_attempts (preview_id, project_id, summary_attempt_id, parse_attempt_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (preview_id, project_id, parse_attempt_id, ordinal, record_key)
                REFERENCES import_parse_records (preview_id, project_id, attempt_id, ordinal, record_key)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    """
        CREATE TABLE import_summary_groups (
            preview_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            summary_attempt_id TEXT NOT NULL,
            reason TEXT NOT NULL CHECK (reason IN ('raw', 'doi')),
            group_key TEXT NOT NULL CHECK (length(group_key)=64 AND group_key NOT GLOB '*[^0-9a-f]*'),
            member_count INTEGER NOT NULL CHECK (member_count BETWEEN 2 AND 200000),
            first_ordinal INTEGER NOT NULL CHECK (first_ordinal BETWEEN 1 AND 200000),
            PRIMARY KEY (preview_id, project_id, summary_attempt_id, reason, group_key),
            FOREIGN KEY (preview_id, project_id, summary_attempt_id, first_ordinal)
                REFERENCES import_summary_rows (preview_id, project_id, summary_attempt_id, ordinal)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    f"""
        CREATE TABLE import_summary_completions (
            preview_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            summary_attempt_id TEXT NOT NULL,
            receipt_revision_id TEXT NOT NULL CHECK ({_uuid_check("receipt_revision_id", "7")}),
            record_count INTEGER NOT NULL CHECK (record_count BETWEEN 0 AND 200000),
            result_sha256 TEXT NOT NULL CHECK (length(result_sha256)=64 AND result_sha256 NOT GLOB '*[^0-9a-f]*'),
            summary_json TEXT NOT NULL CHECK (length(summary_json) BETWEEN 2 AND 4096),
            completed_at TEXT NOT NULL CHECK ({_timestamp_check("completed_at")}),
            PRIMARY KEY (preview_id, project_id, summary_attempt_id),
            UNIQUE (project_id, receipt_revision_id),
            FOREIGN KEY (preview_id, project_id, summary_attempt_id)
                REFERENCES import_summary_attempts (preview_id, project_id, summary_attempt_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (receipt_revision_id, project_id)
                REFERENCES aggregate_revisions (revision_id, project_id) ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    *(
        statement
        for table in IMPORT_SUMMARY_TABLES
        for statement in _immutable_triggers(table, "import summary history is append-only")
    ),
    """
        CREATE TRIGGER import_summary_attempt_binding BEFORE INSERT ON import_summary_attempts
        WHEN NOT EXISTS (
            SELECT 1 FROM workflow_job_attempts a JOIN workflow_queue_jobs j ON j.job_id=a.job_id
             WHERE a.attempt_id=NEW.summary_attempt_id AND a.job_id=NEW.job_id
               AND a.project_id=NEW.project_id AND j.project_id=NEW.project_id
               AND j.current_attempt_id=a.attempt_id AND a.state='running' AND j.state='running'
               AND j.cancellation_requested_at IS NULL
        )
        BEGIN SELECT RAISE(ABORT, 'import summary attempt binding denied'); END
    """,
    """
        CREATE TRIGGER import_summary_row_membership BEFORE INSERT ON import_summary_rows
        WHEN EXISTS (SELECT 1 FROM import_summary_completions WHERE preview_id=NEW.preview_id
                      AND project_id=NEW.project_id AND summary_attempt_id=NEW.summary_attempt_id)
          OR NEW.ordinal <> (SELECT COALESCE(MAX(ordinal), 0) + 1 FROM import_summary_rows
                              WHERE preview_id=NEW.preview_id AND project_id=NEW.project_id
                                AND summary_attempt_id=NEW.summary_attempt_id)
        BEGIN SELECT RAISE(ABORT, 'import summary row membership denied'); END
    """,
    """
        CREATE TRIGGER import_summary_group_membership BEFORE INSERT ON import_summary_groups
        WHEN EXISTS (SELECT 1 FROM import_summary_completions WHERE preview_id=NEW.preview_id
                      AND project_id=NEW.project_id AND summary_attempt_id=NEW.summary_attempt_id)
        BEGIN SELECT RAISE(ABORT, 'import summary already complete'); END
    """,
    """
        CREATE TRIGGER import_summary_completion_membership BEFORE INSERT ON import_summary_completions
        WHEN NEW.record_count <> (SELECT COUNT(*) FROM import_summary_rows WHERE preview_id=NEW.preview_id
                      AND project_id=NEW.project_id AND summary_attempt_id=NEW.summary_attempt_id)
          OR NOT EXISTS (
            SELECT 1 FROM import_summary_attempts a JOIN import_parse_completions c
                ON c.preview_id=a.preview_id AND c.project_id=a.project_id AND c.attempt_id=a.parse_attempt_id
             WHERE a.preview_id=NEW.preview_id AND a.project_id=NEW.project_id
               AND a.summary_attempt_id=NEW.summary_attempt_id AND c.record_count=NEW.record_count
          )
        BEGIN SELECT RAISE(ABORT, 'import summary completion membership denied'); END
    """,
    "CREATE INDEX import_summary_draft ON import_summary_attempts (preview_id, project_id, draft_revision)",
    "CREATE INDEX import_summary_raw ON import_summary_rows "
    "(preview_id, project_id, summary_attempt_id, raw_key, ordinal)",
    "CREATE INDEX import_summary_doi ON import_summary_rows "
    "(preview_id, project_id, summary_attempt_id, doi_key, ordinal)",
)

IMPORT_COMMIT_DDL = (
    f"""
        CREATE TABLE import_commit_preparations (
            project_id TEXT NOT NULL,
            attempt_id TEXT PRIMARY KEY CHECK ({_uuid_check("attempt_id", "7")}),
            job_id TEXT NOT NULL,
            preview_id TEXT NOT NULL,
            draft_revision INTEGER NOT NULL CHECK (draft_revision BETWEEN 1 AND 2147483647),
            parse_attempt_id TEXT NOT NULL,
            previous_manifest_revision_id TEXT,
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            UNIQUE (attempt_id, project_id, preview_id, parse_attempt_id),
            FOREIGN KEY (preview_id, project_id, draft_revision, parse_attempt_id)
                REFERENCES import_draft_revisions (preview_id, project_id, revision, attempt_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (job_id) REFERENCES workflow_queue_jobs (job_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (attempt_id) REFERENCES workflow_job_attempts (attempt_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (previous_manifest_revision_id, project_id)
                REFERENCES import_manifests (revision_id, project_id) ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    """
        CREATE TABLE import_commit_rows (
            attempt_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            preview_id TEXT NOT NULL,
            parse_attempt_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL CHECK (ordinal BETWEEN 1 AND 200000),
            record_key TEXT NOT NULL,
            included INTEGER NOT NULL CHECK (included IN (0, 1)),
            decision_json TEXT NOT NULL CHECK (length(decision_json) BETWEEN 2 AND 16777216),
            warnings_json TEXT NOT NULL CHECK (length(warnings_json) BETWEEN 2 AND 8192),
            raw_sha256 TEXT NOT NULL CHECK (length(raw_sha256)=64 AND raw_sha256 NOT GLOB '*[^0-9a-f]*'),
            doi_key TEXT CHECK (doi_key IS NULL OR (length(doi_key)=64 AND doi_key NOT GLOB '*[^0-9a-f]*')),
            PRIMARY KEY (attempt_id, project_id, ordinal),
            FOREIGN KEY (attempt_id, project_id, preview_id, parse_attempt_id)
                REFERENCES import_commit_preparations (attempt_id, project_id, preview_id, parse_attempt_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (preview_id, project_id, parse_attempt_id, ordinal, record_key)
                REFERENCES import_parse_records (preview_id, project_id, attempt_id, ordinal, record_key)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    f"""
        CREATE TABLE import_source_records (
            project_id TEXT NOT NULL,
            source_sha256 TEXT NOT NULL CHECK (length(source_sha256)=64 AND source_sha256 NOT GLOB '*[^0-9a-f]*'),
            record_key TEXT NOT NULL,
            aggregate_id TEXT NOT NULL CHECK ({_uuid_check("aggregate_id", "7")}),
            revision_id TEXT NOT NULL CHECK ({_uuid_check("revision_id", "7")}),
            preview_id TEXT NOT NULL,
            parse_attempt_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL CHECK (ordinal BETWEEN 1 AND 200000),
            PRIMARY KEY (project_id, source_sha256, record_key),
            UNIQUE (revision_id, project_id),
            UNIQUE (aggregate_id, project_id),
            FOREIGN KEY (revision_id, project_id) REFERENCES aggregate_revisions (revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (preview_id, project_id, parse_attempt_id, ordinal, record_key)
                REFERENCES import_parse_records (preview_id, project_id, attempt_id, ordinal, record_key)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    f"""
        CREATE TABLE import_manifests (
            project_id TEXT NOT NULL,
            revision_id TEXT NOT NULL CHECK ({_uuid_check("revision_id", "7")}),
            aggregate_id TEXT NOT NULL CHECK ({_uuid_check("aggregate_id", "7")}),
            attempt_id TEXT NOT NULL,
            preview_id TEXT NOT NULL,
            parse_attempt_id TEXT NOT NULL,
            source_sha256 TEXT NOT NULL CHECK (length(source_sha256)=64 AND source_sha256 NOT GLOB '*[^0-9a-f]*'),
            identity_sha256 TEXT NOT NULL CHECK (length(identity_sha256)=64 AND identity_sha256 NOT GLOB '*[^0-9a-f]*'),
            draft_sha256 TEXT NOT NULL CHECK (length(draft_sha256)=64 AND draft_sha256 NOT GLOB '*[^0-9a-f]*'),
            record_count INTEGER NOT NULL CHECK (record_count BETWEEN 0 AND 200000),
            selected_count INTEGER NOT NULL CHECK (selected_count BETWEEN 0 AND record_count),
            created_count INTEGER NOT NULL CHECK (created_count BETWEEN 0 AND selected_count),
            reused_count INTEGER NOT NULL CHECK (reused_count=selected_count-created_count),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            PRIMARY KEY (revision_id, project_id),
            UNIQUE (project_id, identity_sha256),
            UNIQUE (attempt_id),
            UNIQUE (revision_id, project_id, preview_id, parse_attempt_id),
            FOREIGN KEY (revision_id, project_id) REFERENCES aggregate_revisions (revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (attempt_id, project_id, preview_id, parse_attempt_id)
                REFERENCES import_commit_preparations (attempt_id, project_id, preview_id, parse_attempt_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    """
        CREATE TABLE import_manifest_members (
            manifest_revision_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            preview_id TEXT NOT NULL,
            parse_attempt_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL CHECK (ordinal BETWEEN 1 AND 200000),
            record_key TEXT NOT NULL,
            source_record_revision_id TEXT,
            included INTEGER NOT NULL CHECK (included IN (0, 1)),
            decision_json TEXT NOT NULL CHECK (length(decision_json) BETWEEN 2 AND 16777216),
            warnings_json TEXT NOT NULL CHECK (length(warnings_json) BETWEEN 2 AND 8192),
            raw_sha256 TEXT NOT NULL CHECK (length(raw_sha256)=64 AND raw_sha256 NOT GLOB '*[^0-9a-f]*'),
            doi_key TEXT CHECK (doi_key IS NULL OR (length(doi_key)=64 AND doi_key NOT GLOB '*[^0-9a-f]*')),
            comparison TEXT NOT NULL
                CHECK (comparison IN ('not-compared', 'added', 'unchanged', 'updated', 'ambiguous')),
            previous_record_revision_id TEXT,
            PRIMARY KEY (manifest_revision_id, project_id, ordinal),
            CHECK ((included=0 AND source_record_revision_id IS NULL) OR
                   (included=1 AND source_record_revision_id IS NOT NULL)),
            CHECK ((comparison IN ('unchanged', 'updated') AND previous_record_revision_id IS NOT NULL) OR
                   (comparison NOT IN ('unchanged', 'updated') AND previous_record_revision_id IS NULL)),
            FOREIGN KEY (manifest_revision_id, project_id, preview_id, parse_attempt_id)
                REFERENCES import_manifests (revision_id, project_id, preview_id, parse_attempt_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (preview_id, project_id, parse_attempt_id, ordinal, record_key)
                REFERENCES import_parse_records (preview_id, project_id, attempt_id, ordinal, record_key)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (source_record_revision_id, project_id)
                REFERENCES import_source_records (revision_id, project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (previous_record_revision_id, project_id)
                REFERENCES import_source_records (revision_id, project_id) ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    f"""
        CREATE TABLE import_manifest_seals (
            manifest_revision_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            members_sha256 TEXT NOT NULL CHECK (length(members_sha256)=64 AND members_sha256 NOT GLOB '*[^0-9a-f]*'),
            sealed_at TEXT NOT NULL CHECK ({_timestamp_check("sealed_at")}),
            PRIMARY KEY (manifest_revision_id, project_id),
            FOREIGN KEY (manifest_revision_id, project_id) REFERENCES import_manifests (revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    *(
        statement
        for table in IMPORT_COMMIT_TABLES
        for statement in _immutable_triggers(table, "import commit history is append-only")
    ),
    """
        CREATE TRIGGER import_commit_preparation_binding BEFORE INSERT ON import_commit_preparations
        WHEN NOT EXISTS (
            SELECT 1 FROM workflow_job_attempts a JOIN workflow_queue_jobs j ON j.job_id=a.job_id
             WHERE a.attempt_id=NEW.attempt_id AND a.job_id=NEW.job_id AND a.project_id=NEW.project_id
               AND j.project_id=NEW.project_id AND j.current_attempt_id=a.attempt_id
               AND a.state='running' AND j.state='running' AND j.cancellation_requested_at IS NULL
               AND j.activity_type='local-import-commit'
        ) OR (NEW.previous_manifest_revision_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM import_manifest_seals s WHERE s.project_id=NEW.project_id
              AND s.manifest_revision_id=NEW.previous_manifest_revision_id
        ))
        BEGIN SELECT RAISE(ABORT, 'import commit attempt binding denied'); END
    """,
    """
        CREATE TRIGGER import_commit_row_membership BEFORE INSERT ON import_commit_rows
        WHEN EXISTS (SELECT 1 FROM import_manifests WHERE attempt_id=NEW.attempt_id)
          OR NEW.ordinal <> (SELECT COALESCE(MAX(ordinal), 0)+1 FROM import_commit_rows
                               WHERE attempt_id=NEW.attempt_id AND project_id=NEW.project_id)
        BEGIN SELECT RAISE(ABORT, 'import commit row membership denied'); END
    """,
    """
        CREATE TRIGGER import_source_record_binding BEFORE INSERT ON import_source_records
        WHEN NOT EXISTS (
            SELECT 1 FROM aggregate_revisions r JOIN import_parse_completions c ON c.project_id=r.project_id
             WHERE r.revision_id=NEW.revision_id AND r.project_id=NEW.project_id
               AND r.aggregate_id=NEW.aggregate_id AND r.aggregate_kind='record' AND r.revision=0
               AND c.preview_id=NEW.preview_id AND c.attempt_id=NEW.parse_attempt_id
               AND c.source_sha256=NEW.source_sha256
        )
        BEGIN SELECT RAISE(ABORT, 'import source record binding denied'); END
    """,
    """
        CREATE TRIGGER import_manifest_binding BEFORE INSERT ON import_manifests
        WHEN NOT EXISTS (
            SELECT 1 FROM aggregate_revisions r JOIN import_commit_preparations p ON p.project_id=r.project_id
              JOIN import_parse_completions c ON c.preview_id=p.preview_id AND c.project_id=p.project_id
                AND c.attempt_id=p.parse_attempt_id
             WHERE r.revision_id=NEW.revision_id AND r.project_id=NEW.project_id
               AND r.aggregate_id=NEW.aggregate_id AND r.aggregate_kind='workflow'
               AND p.attempt_id=NEW.attempt_id AND c.source_sha256=NEW.source_sha256
               AND c.record_count=NEW.record_count
        ) OR NEW.record_count <> (SELECT COUNT(*) FROM import_commit_rows WHERE attempt_id=NEW.attempt_id)
        BEGIN SELECT RAISE(ABORT, 'import manifest binding denied'); END
    """,
    """
        CREATE TRIGGER import_manifest_member_binding BEFORE INSERT ON import_manifest_members
        WHEN EXISTS (SELECT 1 FROM import_manifest_seals WHERE manifest_revision_id=NEW.manifest_revision_id
                       AND project_id=NEW.project_id)
          OR NOT EXISTS (
              SELECT 1 FROM import_manifests m JOIN import_commit_rows r
                ON r.attempt_id=m.attempt_id AND r.project_id=m.project_id
               WHERE m.revision_id=NEW.manifest_revision_id AND m.project_id=NEW.project_id
                 AND r.ordinal=NEW.ordinal AND r.record_key=NEW.record_key AND r.included=NEW.included
                 AND r.decision_json=NEW.decision_json AND r.warnings_json=NEW.warnings_json
                 AND r.raw_sha256=NEW.raw_sha256 AND r.doi_key IS NEW.doi_key
          )
          OR (NEW.previous_record_revision_id IS NOT NULL AND NOT EXISTS (
              SELECT 1 FROM import_manifests m JOIN import_commit_preparations p
                ON p.attempt_id=m.attempt_id AND p.project_id=m.project_id
                JOIN import_manifest_members prior ON prior.manifest_revision_id=p.previous_manifest_revision_id
                  AND prior.project_id=p.project_id
               WHERE m.revision_id=NEW.manifest_revision_id AND m.project_id=NEW.project_id
                 AND prior.included=1 AND prior.source_record_revision_id=NEW.previous_record_revision_id
          ))
          OR NEW.ordinal <> (SELECT COALESCE(MAX(ordinal), 0)+1 FROM import_manifest_members
                               WHERE manifest_revision_id=NEW.manifest_revision_id AND project_id=NEW.project_id)
          OR (NEW.included=1 AND NOT EXISTS (
              SELECT 1 FROM import_source_records s JOIN import_manifests m ON m.project_id=s.project_id
               WHERE m.revision_id=NEW.manifest_revision_id AND m.project_id=NEW.project_id
                 AND s.revision_id=NEW.source_record_revision_id AND s.source_sha256=m.source_sha256
                 AND s.record_key=NEW.record_key
          ))
        BEGIN SELECT RAISE(ABORT, 'import manifest member binding denied'); END
    """,
    """
        CREATE TRIGGER import_manifest_seal_binding BEFORE INSERT ON import_manifest_seals
        WHEN NOT EXISTS (
            SELECT 1 FROM import_manifests m
              WHERE m.revision_id=NEW.manifest_revision_id AND m.project_id=NEW.project_id
              AND m.record_count=(SELECT COUNT(*) FROM import_manifest_members
                    WHERE manifest_revision_id=m.revision_id AND project_id=m.project_id)
              AND m.selected_count=(SELECT COALESCE(SUM(included),0) FROM import_manifest_members
                    WHERE manifest_revision_id=m.revision_id AND project_id=m.project_id)
        )
        BEGIN SELECT RAISE(ABORT, 'import manifest seal binding denied'); END
    """,
    "CREATE INDEX import_manifest_source ON import_manifests (project_id, source_sha256, created_at, revision_id)",
    "CREATE INDEX import_manifest_raw ON import_manifest_members "
    "(project_id, manifest_revision_id, raw_sha256, ordinal)",
    "CREATE INDEX import_manifest_doi ON import_manifest_members (project_id, manifest_revision_id, doi_key, ordinal)",
    "CREATE INDEX import_manifest_source_record ON import_manifest_members "
    "(project_id, manifest_revision_id, source_record_revision_id) WHERE included=1",
)

RECONCILIATION_DDL = (
    f"""
        CREATE TABLE reconciliation_assertions (
            revision_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            aggregate_kind TEXT NOT NULL DEFAULT 'record' CHECK (aggregate_kind = 'record'),
            source_revision_id TEXT NOT NULL,
            address_revision_id TEXT NOT NULL,
            address_sha256 TEXT NOT NULL CHECK ({_sha256_check("address_sha256")}),
            payload_sha256 TEXT NOT NULL CHECK ({_sha256_check("payload_sha256")}),
            assertion_json TEXT NOT NULL
                CHECK (json_valid(assertion_json) AND length(CAST(assertion_json AS BLOB)) <= 1048576
                    AND json_type(assertion_json) IS 'object'
                    AND json_extract(assertion_json, '$.schemaVersion') IS '1.0'
                    AND json_extract(assertion_json, '$.projectId') IS project_id
                    AND json_extract(assertion_json, '$.sourceRevisionId') IS source_revision_id
                    AND json_extract(assertion_json, '$.address.revisionId') IS address_revision_id),
            result_json TEXT NOT NULL CHECK (json_valid(result_json) AND length(CAST(result_json AS BLOB)) <= 65536),
            FOREIGN KEY (revision_id, aggregate_kind, project_id)
                REFERENCES aggregate_revisions (revision_id, aggregate_kind, project_id),
            FOREIGN KEY (source_revision_id, project_id) REFERENCES aggregate_revisions (revision_id, project_id),
            FOREIGN KEY (address_revision_id, project_id) REFERENCES aggregate_revisions (revision_id, project_id),
            UNIQUE (project_id, address_sha256),
            UNIQUE (revision_id, project_id)
        ) STRICT
    """,
    """
        CREATE TABLE reconciliation_work_revisions (
            revision_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            work_id TEXT NOT NULL,
            aggregate_kind TEXT NOT NULL DEFAULT 'record' CHECK (aggregate_kind = 'record'),
            assertion_revision_id TEXT NOT NULL UNIQUE,
            previous_revision_id TEXT,
            FOREIGN KEY (revision_id, aggregate_kind, project_id)
                REFERENCES aggregate_revisions (revision_id, aggregate_kind, project_id),
            FOREIGN KEY (work_id, project_id, aggregate_kind)
                REFERENCES aggregate_identities (aggregate_id, project_id, aggregate_kind),
            FOREIGN KEY (assertion_revision_id, project_id)
                REFERENCES reconciliation_assertions (revision_id, project_id),
            FOREIGN KEY (previous_revision_id, project_id, work_id)
                REFERENCES reconciliation_work_revisions (revision_id, project_id, work_id),
            UNIQUE (revision_id, project_id, work_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE reconciliation_identifier_links (
            assertion_revision_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            scheme TEXT NOT NULL CHECK ({_identifier_check("scheme", 64)}),
            key_sha256 TEXT NOT NULL CHECK ({_sha256_check("key_sha256")}),
            work_id TEXT,
            aggregate_kind TEXT NOT NULL DEFAULT 'record' CHECK (aggregate_kind = 'record'),
            FOREIGN KEY (assertion_revision_id, project_id)
                REFERENCES reconciliation_assertions (revision_id, project_id),
            FOREIGN KEY (work_id, project_id, aggregate_kind)
                REFERENCES aggregate_identities (aggregate_id, project_id, aggregate_kind),
            PRIMARY KEY (assertion_revision_id, scheme, key_sha256)
        ) STRICT
    """,
    f"""
        CREATE TABLE reconciliation_commands (
            command_id TEXT NOT NULL CHECK ({_uuid_check("command_id", "7")}),
            project_id TEXT NOT NULL,
            actor_id TEXT NOT NULL CHECK ({_uuid_check("actor_id", "7")}),
            command_sha256 TEXT NOT NULL CHECK ({_sha256_check("command_sha256")}),
            assertion_revision_id TEXT NOT NULL,
            FOREIGN KEY (assertion_revision_id, project_id)
                REFERENCES reconciliation_assertions (revision_id, project_id),
            PRIMARY KEY (project_id, command_id)
        ) STRICT
    """,
    *(
        statement
        for table in RECONCILIATION_TABLES
        for statement in _immutable_triggers(table, "scholarly reconciliation history is append-only")
    ),
    "CREATE INDEX reconciliation_identifier_lookup ON reconciliation_identifier_links (project_id, scheme, key_sha256)",
    "CREATE INDEX reconciliation_work_sources ON reconciliation_work_revisions (project_id, work_id)",
    """
        CREATE TRIGGER reconciliation_work_binding BEFORE INSERT ON reconciliation_work_revisions
        WHEN NOT EXISTS (
            SELECT 1 FROM aggregate_revisions r WHERE r.revision_id=NEW.revision_id
            AND r.project_id=NEW.project_id AND r.aggregate_id=NEW.work_id AND r.aggregate_kind='record'
            AND ((r.revision=0 AND NEW.previous_revision_id IS NULL) OR EXISTS (
                SELECT 1 FROM aggregate_revisions p WHERE p.revision_id=NEW.previous_revision_id
                AND p.aggregate_id=r.aggregate_id AND p.revision=r.revision-1
            ))
        )
        BEGIN SELECT RAISE(ABORT, 'scholarly work revision binding denied'); END
    """,
)

RECONCILIATION_REVIEW_DDL = (
    "CREATE UNIQUE INDEX dependency_impact_project_identity ON dependency_impact_runs (run_id, project_id)",
    f"""
        CREATE TABLE reconciliation_impact_seals (
            run_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            run_sha256 TEXT NOT NULL CHECK ({_sha256_check("run_sha256")}),
            FOREIGN KEY (run_id, project_id) REFERENCES dependency_impact_runs (run_id, project_id)
        ) STRICT
    """,
    """
        CREATE TABLE reconciliation_exact_impacts (
            run_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            command_id TEXT NOT NULL,
            FOREIGN KEY (run_id, project_id) REFERENCES dependency_impact_runs (run_id, project_id),
            FOREIGN KEY (project_id, command_id) REFERENCES reconciliation_commands (project_id, command_id),
            UNIQUE (project_id, command_id)
        ) STRICT
    """,
    """
        CREATE TABLE reconciliation_impact_continuations (
            root_run_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            sequence INTEGER NOT NULL CHECK (sequence BETWEEN 1 AND 128),
            previous_run_id TEXT NOT NULL UNIQUE,
            run_id TEXT PRIMARY KEY,
            previous_checkpoint_sha256 TEXT NOT NULL CHECK (
                length(previous_checkpoint_sha256)=71 AND substr(previous_checkpoint_sha256,1,7)='sha256:'
                AND substr(previous_checkpoint_sha256,8) NOT GLOB '*[^0-9a-f]*'),
            CHECK (run_id<>root_run_id AND run_id<>previous_run_id),
            FOREIGN KEY (root_run_id, project_id) REFERENCES dependency_impact_runs (run_id, project_id),
            FOREIGN KEY (previous_run_id, project_id) REFERENCES dependency_impact_runs (run_id, project_id),
            FOREIGN KEY (run_id, project_id) REFERENCES dependency_impact_runs (run_id, project_id),
            UNIQUE (root_run_id, sequence)
        ) STRICT
    """,
    """
        CREATE TABLE reconciliation_work_states (
            revision_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            work_id TEXT NOT NULL,
            aggregate_kind TEXT NOT NULL DEFAULT 'record' CHECK (aggregate_kind='record'),
            previous_revision_id TEXT,
            disposition TEXT NOT NULL CHECK (disposition IN ('active','alias')),
            alias_target TEXT,
            decision_revision_id TEXT,
            decision_kind TEXT NOT NULL DEFAULT 'decision' CHECK (decision_kind='decision'),
            CHECK ((disposition='active' AND alias_target IS NULL) OR
                   (disposition='alias' AND alias_target IS NOT NULL AND alias_target<>work_id
                    AND previous_revision_id IS NOT NULL AND decision_revision_id IS NOT NULL)),
            FOREIGN KEY (revision_id, aggregate_kind, project_id)
                REFERENCES aggregate_revisions (revision_id, aggregate_kind, project_id),
            FOREIGN KEY (work_id, project_id, aggregate_kind)
                REFERENCES aggregate_identities (aggregate_id, project_id, aggregate_kind),
            FOREIGN KEY (alias_target, project_id, aggregate_kind)
                REFERENCES aggregate_identities (aggregate_id, project_id, aggregate_kind),
            FOREIGN KEY (previous_revision_id, project_id, work_id)
                REFERENCES reconciliation_work_states (revision_id, project_id, work_id),
            FOREIGN KEY (decision_revision_id, decision_kind, project_id)
                REFERENCES aggregate_revisions (revision_id, aggregate_kind, project_id),
            UNIQUE (revision_id, project_id, work_id),
            UNIQUE (revision_id, project_id)
        ) STRICT
    """,
    """
        CREATE TABLE reconciliation_work_members (
            work_revision_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL CHECK (ordinal BETWEEN 1 AND 256),
            assertion_revision_id TEXT NOT NULL,
            FOREIGN KEY (work_revision_id, project_id)
                REFERENCES reconciliation_work_states (revision_id, project_id),
            FOREIGN KEY (assertion_revision_id, project_id)
                REFERENCES reconciliation_assertions (revision_id, project_id),
            PRIMARY KEY (work_revision_id, project_id, assertion_revision_id),
            UNIQUE (work_revision_id, project_id, ordinal)
        ) STRICT
    """,
    f"""
        CREATE TABLE reconciliation_work_seals (
            work_revision_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            member_count INTEGER NOT NULL CHECK (member_count BETWEEN 0 AND 256),
            state_sha256 TEXT NOT NULL CHECK ({_sha256_check("state_sha256")}),
            FOREIGN KEY (work_revision_id, project_id)
                REFERENCES reconciliation_work_states (revision_id, project_id),
            PRIMARY KEY (work_revision_id, project_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE reconciliation_review_decisions (
            revision_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            aggregate_kind TEXT NOT NULL DEFAULT 'decision' CHECK (aggregate_kind='decision'),
            command_id TEXT NOT NULL CHECK ({_uuid_check("command_id", "7")}),
            actor_id TEXT NOT NULL CHECK ({_uuid_check("actor_id", "7")}),
            command_sha256 TEXT NOT NULL CHECK ({_sha256_check("command_sha256")}),
            plan_sha256 TEXT NOT NULL CHECK ({_sha256_check("plan_sha256")}),
            intent_sha256 TEXT NOT NULL CHECK ({_sha256_check("intent_sha256")}),
            policy_sha256 TEXT NOT NULL CHECK ({_sha256_check("policy_sha256")}),
            plan_json TEXT NOT NULL CHECK (json_valid(plan_json)
                AND length(CAST(plan_json AS BLOB)) BETWEEN 2 AND 1048576
                AND json_type(plan_json) IS 'object'
                AND json_extract(plan_json,'$.schemaVersion') IS '1.0'
                AND json_extract(plan_json,'$.conflictDisposition') IS 'retain-all'),
            outcome_json TEXT NOT NULL CHECK (json_valid(outcome_json)
                AND length(CAST(outcome_json AS BLOB)) BETWEEN 2 AND 4194304
                AND json_type(outcome_json) IS 'object'
                AND json_extract(outcome_json,'$.schemaVersion') IS '1.0'
                AND json_extract(outcome_json,'$.decisionRevisionId') IS revision_id
                AND json_extract(outcome_json,'$.commandId') IS command_id
                AND json_extract(outcome_json,'$.planSha256') IS plan_sha256),
            FOREIGN KEY (revision_id, aggregate_kind, project_id)
                REFERENCES aggregate_revisions (revision_id, aggregate_kind, project_id),
            UNIQUE (project_id, command_id),
            UNIQUE (revision_id, project_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE reconciliation_feature_cache (
            project_id TEXT NOT NULL,
            assertion_revision_id TEXT NOT NULL,
            feature_version TEXT NOT NULL CHECK (length(feature_version) BETWEEN 1 AND 128),
            normalizer_version TEXT NOT NULL CHECK (length(normalizer_version) BETWEEN 1 AND 128),
            configuration_sha256 TEXT NOT NULL CHECK ({_sha256_check("configuration_sha256")}),
            input_sha256 TEXT NOT NULL CHECK ({_sha256_check("input_sha256")}),
            payload_sha256 TEXT NOT NULL CHECK ({_sha256_check("payload_sha256")}),
            feature_json TEXT NOT NULL CHECK (json_valid(feature_json)
                AND length(CAST(feature_json AS BLOB)) BETWEEN 2 AND 2097152
                AND json_type(feature_json) IS 'object'
                AND json_extract(feature_json,'$.schemaVersion') IS '1.0'
                AND json_extract(feature_json,'$.assertionRevisionId') IS assertion_revision_id
                AND json_extract(feature_json,'$.featureVersion') IS feature_version
                AND json_extract(feature_json,'$.identifierNormalizer') IS normalizer_version
                AND json_extract(feature_json,'$.configurationSha256') IS configuration_sha256
                AND json_extract(feature_json,'$.inputSha256') IS input_sha256
                AND json_extract(feature_json,'$.algorithm') IS 'scholarly-duplicate-ranking/1.0.0'
                AND json_type(feature_json,'$.sourceRevisionId') IS 'text'
                AND length(json_extract(feature_json,'$.sourceRevisionId')) = 36
                AND json_type(feature_json,'$.sourceSha256') IS 'text'
                AND length(json_extract(feature_json,'$.sourceSha256')) = 64
                AND json_type(feature_json,'$.fields') IS 'array'
                AND json_array_length(feature_json,'$.fields') BETWEEN 0 AND 6
                AND json_type(feature_json,'$.identifiers') IS 'array'
                AND json_array_length(feature_json,'$.identifiers') BETWEEN 0 AND 128
                AND json_remove(feature_json,'$.schemaVersion','$.algorithm','$.featureVersion',
                    '$.identifierNormalizer','$.configurationSha256','$.assertionRevisionId',
                    '$.sourceRevisionId','$.sourceSha256','$.inputSha256','$.fields','$.identifiers') = '{{}}'),
            FOREIGN KEY (assertion_revision_id, project_id)
                REFERENCES reconciliation_assertions (revision_id, project_id),
            PRIMARY KEY (project_id, assertion_revision_id, feature_version, normalizer_version, configuration_sha256)
        ) STRICT
    """,
    f"""
        CREATE TABLE reconciliation_candidate_sets (
            revision_id TEXT PRIMARY KEY NOT NULL CHECK ({_uuid_check("revision_id", "7")}),
            project_id TEXT NOT NULL,
            aggregate_kind TEXT NOT NULL DEFAULT 'workflow' CHECK (aggregate_kind='workflow'),
            request_id TEXT NOT NULL CHECK ({_uuid_check("request_id", "7")}),
            request_sha256 TEXT NOT NULL CHECK ({_sha256_check("request_sha256")}),
            payload_sha256 TEXT NOT NULL CHECK ({_sha256_check("payload_sha256")}),
            candidate_set_json TEXT NOT NULL CHECK (json_valid(candidate_set_json)
                AND length(CAST(candidate_set_json AS BLOB)) BETWEEN 2 AND 8388608
                AND json_type(candidate_set_json) IS 'object'
                AND json_extract(candidate_set_json,'$.schemaVersion') IS '1.0'
                AND json_extract(candidate_set_json,'$.projectId') IS project_id
                AND json_extract(candidate_set_json,'$.requestId') IS request_id
                AND json_extract(candidate_set_json,'$.requestSha256') IS request_sha256
                AND json_type(candidate_set_json,'$.members') IS 'array'
                AND json_array_length(candidate_set_json,'$.members') BETWEEN 0 AND 10000
                AND json_type(candidate_set_json,'$.pairSha256') IS 'array'
                AND json_array_length(candidate_set_json,'$.pairSha256') BETWEEN 0 AND 20000
                AND json_extract(candidate_set_json,'$.algorithm') IS 'scholarly-duplicate-ranking/1.0.0'
                AND json_extract(candidate_set_json,'$.featureVersion') IS 'scholarly-duplicate-features/1.0.0'
                AND json_extract(candidate_set_json,'$.identifierNormalizer') IS 'scholarly-identifiers/1.0.0'
                AND json_type(candidate_set_json,'$.configurationSha256') IS 'text'
                AND length(json_extract(candidate_set_json,'$.configurationSha256')) = 64
                AND json_type(candidate_set_json,'$.inventorySha256') IS 'text'
                AND length(json_extract(candidate_set_json,'$.inventorySha256')) = 64
                AND json_type(candidate_set_json,'$.comparedPairs') IS 'integer'
                AND json_extract(candidate_set_json,'$.comparedPairs') BETWEEN 0 AND 250000
                AND json_remove(candidate_set_json,'$.schemaVersion','$.projectId','$.requestId',
                    '$.requestSha256','$.inventorySha256','$.members','$.comparedPairs','$.pairSha256',
                    '$.algorithm','$.featureVersion','$.configurationSha256','$.identifierNormalizer') = '{{}}'),
            FOREIGN KEY (revision_id, aggregate_kind, project_id)
                REFERENCES aggregate_revisions (revision_id, aggregate_kind, project_id),
            UNIQUE (project_id, request_id),
            UNIQUE (revision_id, project_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE reconciliation_candidate_pairs (
            set_revision_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL CHECK (ordinal BETWEEN 0 AND 19999),
            payload_sha256 TEXT NOT NULL CHECK ({_sha256_check("payload_sha256")}),
            explanation_json TEXT NOT NULL CHECK (json_valid(explanation_json)
                AND length(CAST(explanation_json AS BLOB)) BETWEEN 2 AND 65536
                AND json_type(explanation_json) IS 'object'
                AND json_extract(explanation_json,'$.disposition') IS 'human-review-required'
                AND json_extract(explanation_json,'$.algorithm') IS 'scholarly-duplicate-ranking/1.0.0'
                AND json_extract(explanation_json,'$.featureVersion') IS 'scholarly-duplicate-features/1.0.0'
                AND json_extract(explanation_json,'$.identifierNormalizer') IS 'scholarly-identifiers/1.0.0'
                AND json_type(explanation_json,'$.score') IS 'integer'
                AND json_extract(explanation_json,'$.score') BETWEEN 0 AND 10000
                AND json_type(explanation_json,'$.features') IS 'array'
                AND json_array_length(explanation_json,'$.features') = 7
                AND json_type(explanation_json,'$.flags') IS 'array'
                AND json_array_length(explanation_json,'$.flags') BETWEEN 0 AND 3
                AND json_type(explanation_json,'$.left') IS 'text'
                AND json_type(explanation_json,'$.right') IS 'text'
                AND json_type(explanation_json,'$.leftRevision') IS 'text'
                AND json_type(explanation_json,'$.rightRevision') IS 'text'
                AND json_type(explanation_json,'$.leftFingerprint') IS 'text'
                AND json_type(explanation_json,'$.rightFingerprint') IS 'text'
                AND json_type(explanation_json,'$.configurationFingerprint') IS 'text'
                AND json_remove(explanation_json,'$.left','$.right','$.leftRevision','$.rightRevision',
                    '$.leftFingerprint','$.rightFingerprint','$.score','$.features','$.flags',
                    '$.configurationFingerprint','$.algorithm','$.featureVersion',
                    '$.identifierNormalizer','$.disposition') = '{{}}'),
            FOREIGN KEY (set_revision_id, project_id)
                REFERENCES reconciliation_candidate_sets (revision_id, project_id),
            PRIMARY KEY (set_revision_id, ordinal)
        ) STRICT
    """,
    """
        CREATE TRIGGER reconciliation_candidate_pair_binding BEFORE INSERT ON reconciliation_candidate_pairs
        WHEN NOT EXISTS (
            SELECT 1 FROM reconciliation_candidate_sets s
            WHERE s.revision_id=NEW.set_revision_id AND s.project_id=NEW.project_id
              AND json_extract(s.candidate_set_json,'$.pairSha256[' || NEW.ordinal || ']') IS NEW.payload_sha256
        )
        BEGIN SELECT RAISE(ABORT, 'scholarly candidate pair binding denied'); END
    """,
    *(
        statement
        for table in RECONCILIATION_REVIEW_TABLES
        for statement in _immutable_triggers(table, "scholarly review history is append-only")
    ),
    "CREATE INDEX reconciliation_current_membership ON reconciliation_work_members (project_id, assertion_revision_id)",
    "CREATE INDEX reconciliation_state_predecessor ON reconciliation_work_states (project_id, previous_revision_id)",
    "CREATE INDEX reconciliation_alias_target ON reconciliation_work_states (project_id, alias_target)",
    """
        CREATE TRIGGER reconciliation_state_binding BEFORE INSERT ON reconciliation_work_states
        WHEN NOT EXISTS (
            SELECT 1 FROM aggregate_revisions r WHERE r.revision_id=NEW.revision_id
              AND r.project_id=NEW.project_id AND r.aggregate_id=NEW.work_id AND r.aggregate_kind='record'
              AND ((r.revision=0 AND NEW.previous_revision_id IS NULL) OR EXISTS (
                SELECT 1 FROM aggregate_revisions p JOIN reconciliation_work_seals s
                  ON s.work_revision_id=p.revision_id AND s.project_id=p.project_id
                WHERE p.revision_id=NEW.previous_revision_id AND p.project_id=r.project_id
                  AND p.aggregate_id=r.aggregate_id AND p.revision=r.revision-1
              ))
        ) OR EXISTS (
            SELECT 1 FROM aggregate_revisions r JOIN reconciliation_assertions a ON a.revision_id=r.revision_id
            WHERE r.project_id=NEW.project_id AND r.aggregate_id=NEW.work_id
        ) OR EXISTS (
            SELECT 1 FROM import_source_records s WHERE s.project_id=NEW.project_id AND s.aggregate_id=NEW.work_id
        )
        BEGIN SELECT RAISE(ABORT, 'scholarly current work binding denied'); END
    """,
    """
        CREATE TRIGGER reconciliation_membership_binding BEFORE INSERT ON reconciliation_work_members
        WHEN EXISTS (SELECT 1 FROM reconciliation_work_seals s
            WHERE s.work_revision_id=NEW.work_revision_id AND s.project_id=NEW.project_id)
          OR NOT EXISTS (SELECT 1 FROM reconciliation_work_states s
            WHERE s.revision_id=NEW.work_revision_id AND s.project_id=NEW.project_id AND s.disposition='active')
          OR NEW.ordinal <> (SELECT COALESCE(MAX(ordinal),0)+1 FROM reconciliation_work_members
            WHERE work_revision_id=NEW.work_revision_id AND project_id=NEW.project_id)
          OR EXISTS (SELECT 1 FROM reconciliation_work_members WHERE work_revision_id=NEW.work_revision_id
            AND project_id=NEW.project_id AND assertion_revision_id>=NEW.assertion_revision_id)
        BEGIN SELECT RAISE(ABORT, 'scholarly current membership binding denied'); END
    """,
    """
        CREATE TRIGGER reconciliation_seal_binding BEFORE INSERT ON reconciliation_work_seals
        WHEN NEW.member_count <> (SELECT COUNT(*) FROM reconciliation_work_members
            WHERE work_revision_id=NEW.work_revision_id AND project_id=NEW.project_id)
          OR NOT EXISTS (SELECT 1 FROM reconciliation_work_states s WHERE s.revision_id=NEW.work_revision_id
            AND s.project_id=NEW.project_id
            AND ((s.disposition='active' AND NEW.member_count>0) OR (s.disposition='alias' AND NEW.member_count=0)))
        BEGIN SELECT RAISE(ABORT, 'scholarly current membership seal denied'); END
    """,
    """
        CREATE TRIGGER reconciliation_legacy_history_closed BEFORE INSERT ON reconciliation_work_revisions
        BEGIN SELECT RAISE(ABORT, 'use sealed scholarly work states'); END
    """,
    """
        CREATE TRIGGER reconciliation_exact_impact_binding BEFORE INSERT ON reconciliation_exact_impacts
        WHEN NOT EXISTS (
            SELECT 1 FROM reconciliation_commands c
            JOIN reconciliation_assertions a ON a.revision_id=c.assertion_revision_id AND a.project_id=c.project_id
            JOIN reconciliation_work_states s ON s.revision_id=json_extract(a.result_json,'$.workRevisionId')
                AND s.project_id=c.project_id
            JOIN reconciliation_work_members m ON m.work_revision_id=s.revision_id AND m.project_id=c.project_id
                AND m.assertion_revision_id=c.assertion_revision_id
            JOIN dependency_impact_runs r ON r.run_id=NEW.run_id AND r.project_id=c.project_id
            WHERE c.command_id=NEW.command_id AND c.project_id=NEW.project_id
                AND r.actor_id=c.actor_id AND r.reason='SOURCE_VERSION' AND r.dependency_kind='source-revision'
                AND r.previous_revision_id=s.previous_revision_id AND r.replacement_revision_id=s.revision_id
        )
        BEGIN SELECT RAISE(ABORT, 'scholarly exact impact owner denied'); END
    """,
    """
        CREATE TRIGGER reconciliation_impact_continuation_binding BEFORE INSERT ON reconciliation_impact_continuations
        WHEN NOT (
            (NEW.sequence=1 AND NEW.previous_run_id=NEW.root_run_id) OR EXISTS (
                SELECT 1 FROM reconciliation_impact_continuations p WHERE p.project_id=NEW.project_id
                    AND p.root_run_id=NEW.root_run_id AND p.run_id=NEW.previous_run_id AND p.sequence=NEW.sequence-1
            )
        ) OR NOT (
            EXISTS (SELECT 1 FROM reconciliation_exact_impacts x WHERE x.project_id=NEW.project_id
                AND x.run_id=NEW.root_run_id) OR EXISTS (
                SELECT 1 FROM reconciliation_review_decisions d,json_each(d.outcome_json,'$.dependencyRunIds') owned
                WHERE d.project_id=NEW.project_id AND owned.value=NEW.root_run_id
            )
        ) OR EXISTS (SELECT 1 FROM reconciliation_impact_continuations p
            WHERE p.previous_run_id=NEW.run_id OR p.root_run_id=NEW.run_id)
        OR NOT EXISTS (
            SELECT 1 FROM dependency_impact_audit_events a WHERE a.run_id=NEW.previous_run_id
                AND a.project_id=NEW.project_id AND a.checkpoint_sha256=NEW.previous_checkpoint_sha256
                AND a.event_type IN ('started','checkpoint','failed-attempt')
                AND a.sequence=(SELECT MAX(sequence) FROM dependency_impact_audit_events
                    WHERE run_id=a.run_id AND project_id=a.project_id)
        ) OR NOT EXISTS (
            SELECT 1 FROM dependency_impact_runs p JOIN dependency_impact_runs c ON c.project_id=p.project_id
            WHERE p.run_id=NEW.previous_run_id AND c.run_id=NEW.run_id AND p.project_id=NEW.project_id
                AND c.reason IS p.reason AND c.dependency_kind IS p.dependency_kind
                AND c.previous_revision_id IS p.previous_revision_id
                AND c.replacement_revision_id IS p.replacement_revision_id
                AND c.configuration_id IS p.configuration_id
                AND c.previous_configuration_version IS p.previous_configuration_version
                AND c.replacement_configuration_version IS p.replacement_configuration_version
                AND c.previous_fingerprint IS p.previous_fingerprint
                AND c.replacement_fingerprint IS p.replacement_fingerprint
                AND c.propagation_policy_id IS p.propagation_policy_id
                AND c.propagation_policy_version IS p.propagation_policy_version
                AND c.actor_id IS p.actor_id AND c.trace_id IS p.trace_id AND c.occurred_at IS p.occurred_at
                AND c.batch_size=p.batch_size AND c.max_nodes=p.max_nodes AND c.max_edges=p.max_edges
                AND c.max_depth=p.max_depth AND c.max_path_samples=p.max_path_samples
                AND c.max_legacy_samples=p.max_legacy_samples
                AND NOT EXISTS (SELECT 1 FROM dependency_impact_decisions d WHERE d.run_id IN (p.run_id,c.run_id))
        )
        BEGIN SELECT RAISE(ABORT, 'scholarly impact continuation authority denied'); END
    """,
)


def _version_date_check() -> str:
    return """(date_precision IN ('unknown','not-reported') AND date_value IS NULL)
        OR (date_precision='year' AND length(date_value)=4 AND date_value NOT GLOB '*[^0-9]*'
            AND CAST(date_value AS INTEGER) BETWEEN 1 AND 9999)
        OR (date_precision='month' AND length(date_value)=7 AND date_value GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'
            AND CAST(substr(date_value,1,4) AS INTEGER) BETWEEN 1 AND 9999
            AND CAST(substr(date_value,6,2) AS INTEGER) BETWEEN 1 AND 12)
        OR (date_precision='day' AND length(date_value)=10 AND date_value GLOB
            '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
            AND CAST(substr(date_value,1,4) AS INTEGER) BETWEEN 1 AND 9999
            AND date(date_value) IS date_value)"""


# Additive v16 authority. The v15 DDL above remains the exact historical target.
WORK_VERSION_DDL = (
    f"""
        CREATE TABLE reconciliation_versions (
            revision_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            version_id TEXT NOT NULL,
            aggregate_kind TEXT NOT NULL DEFAULT 'record' CHECK (aggregate_kind='record'),
            previous_revision_id TEXT,
            version_kind TEXT NOT NULL CHECK (version_kind IN ('preprint','accepted-manuscript','version-of-record',
                'erratum','correction','expression-of-concern','retraction','not-reported')),
            date_precision TEXT NOT NULL CHECK (date_precision IN ('unknown','not-reported','year','month','day')),
            date_value TEXT,
            decision_revision_id TEXT NOT NULL,
            decision_kind TEXT NOT NULL DEFAULT 'decision' CHECK (decision_kind='decision'),
            source_count INTEGER NOT NULL CHECK (source_count BETWEEN 1 AND 256),
            status_sha256 TEXT NOT NULL CHECK ({_sha256_check("status_sha256")}),
            content_sha256 TEXT NOT NULL CHECK ({_sha256_check("content_sha256")}),
            CHECK ((date_precision IN ('unknown','not-reported')) IS (date_value IS NULL)),
            CHECK ({_version_date_check()}),
            FOREIGN KEY (revision_id,aggregate_kind,project_id) REFERENCES aggregate_revisions (revision_id,
                aggregate_kind,project_id),
            FOREIGN KEY (version_id,project_id,aggregate_kind) REFERENCES aggregate_identities (aggregate_id,
                project_id,aggregate_kind),
            FOREIGN KEY (previous_revision_id,project_id,version_id) REFERENCES reconciliation_versions
                (revision_id,project_id,version_id),
            FOREIGN KEY (decision_revision_id,decision_kind,project_id) REFERENCES aggregate_revisions
                (revision_id,aggregate_kind,project_id),
            UNIQUE (revision_id,project_id,version_id),
            UNIQUE (revision_id,project_id)
        ) STRICT
    """,
    """
        CREATE TABLE reconciliation_version_sources (
            version_revision_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL CHECK (ordinal BETWEEN 1 AND 256),
            assertion_revision_id TEXT NOT NULL,
            FOREIGN KEY (version_revision_id,project_id) REFERENCES reconciliation_versions (revision_id,project_id),
            FOREIGN KEY (assertion_revision_id,project_id) REFERENCES reconciliation_assertions (revision_id,
                project_id),
            PRIMARY KEY (version_revision_id,project_id,ordinal),
            UNIQUE (version_revision_id,project_id,assertion_revision_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE reconciliation_version_relations (
            revision_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            relation_id TEXT NOT NULL,
            aggregate_kind TEXT NOT NULL DEFAULT 'record' CHECK (aggregate_kind='record'),
            decision_revision_id TEXT NOT NULL,
            decision_kind TEXT NOT NULL DEFAULT 'decision' CHECK (decision_kind='decision'),
            source_revision_id TEXT NOT NULL,
            target_revision_id TEXT NOT NULL CHECK (target_revision_id<>source_revision_id),
            relation_kind TEXT NOT NULL CHECK (relation_kind IN ('is-version-of','supersedes','erratum-for',
                'corrects','expresses-concern','retracts')),
            knowledge_status TEXT NOT NULL CHECK (knowledge_status IN ('adjudicated','disputed')),
            date_precision TEXT NOT NULL CHECK (date_precision IN ('unknown','not-reported','year','month','day')),
            date_value TEXT,
            evidence_count INTEGER NOT NULL CHECK (evidence_count BETWEEN 1 AND 32),
            content_sha256 TEXT NOT NULL CHECK ({_sha256_check("content_sha256")}),
            CHECK ((date_precision IN ('unknown','not-reported')) IS (date_value IS NULL)),
            CHECK ({_version_date_check()}),
            FOREIGN KEY (revision_id,aggregate_kind,project_id) REFERENCES aggregate_revisions (revision_id,
                aggregate_kind,project_id),
            FOREIGN KEY (relation_id,project_id,aggregate_kind) REFERENCES aggregate_identities (aggregate_id,
                project_id,aggregate_kind),
            FOREIGN KEY (decision_revision_id,decision_kind,project_id) REFERENCES aggregate_revisions
                (revision_id,aggregate_kind,project_id),
            FOREIGN KEY (source_revision_id,project_id) REFERENCES reconciliation_versions (revision_id,project_id),
            FOREIGN KEY (target_revision_id,project_id) REFERENCES reconciliation_versions (revision_id,project_id),
            UNIQUE (revision_id,project_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE reconciliation_relation_evidence (
            relation_revision_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL CHECK (ordinal BETWEEN 1 AND 32),
            assertion_revision_id TEXT NOT NULL,
            category TEXT NOT NULL CHECK (category IN ('field','identifier')),
            selector TEXT NOT NULL CHECK (length(selector) BETWEEN 1 AND 128),
            value_sha256 TEXT NOT NULL CHECK ({_sha256_check("value_sha256")}),
            FOREIGN KEY (relation_revision_id,project_id) REFERENCES reconciliation_version_relations
                (revision_id,project_id),
            FOREIGN KEY (assertion_revision_id,project_id) REFERENCES reconciliation_assertions (revision_id,
                project_id),
            PRIMARY KEY (relation_revision_id,project_id,ordinal),
            UNIQUE (relation_revision_id,project_id,assertion_revision_id,category,selector)
        ) STRICT
    """,
    f"""
        CREATE TABLE reconciliation_version_preferences (
            revision_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            preference_id TEXT NOT NULL,
            aggregate_kind TEXT NOT NULL DEFAULT 'decision' CHECK (aggregate_kind='decision'),
            previous_revision_id TEXT,
            decision_revision_id TEXT NOT NULL,
            work_revision_id TEXT NOT NULL,
            work_id TEXT NOT NULL,
            selected_revision_id TEXT NOT NULL,
            membership_sha256 TEXT NOT NULL CHECK ({_sha256_check("membership_sha256")}),
            status_sha256 TEXT NOT NULL CHECK ({_sha256_check("status_sha256")}),
            FOREIGN KEY (revision_id,aggregate_kind,project_id) REFERENCES aggregate_revisions (revision_id,
                aggregate_kind,project_id),
            FOREIGN KEY (preference_id,project_id,aggregate_kind) REFERENCES aggregate_identities
                (aggregate_id,project_id,aggregate_kind),
            FOREIGN KEY (previous_revision_id,project_id,preference_id) REFERENCES
                reconciliation_version_preferences (revision_id,project_id,preference_id),
            FOREIGN KEY (decision_revision_id,aggregate_kind,project_id) REFERENCES aggregate_revisions
                (revision_id,aggregate_kind,project_id),
            FOREIGN KEY (work_revision_id,project_id,work_id) REFERENCES reconciliation_work_states
                (revision_id,project_id,work_id),
            FOREIGN KEY (selected_revision_id,project_id) REFERENCES reconciliation_versions (revision_id,project_id),
            UNIQUE (revision_id,project_id,preference_id),
            UNIQUE (revision_id,project_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE reconciliation_version_decisions (
            revision_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            aggregate_kind TEXT NOT NULL DEFAULT 'decision' CHECK (aggregate_kind='decision'),
            command_id TEXT NOT NULL CHECK ({_uuid_check("command_id", "7")}),
            actor_id TEXT NOT NULL CHECK ({_uuid_check("actor_id", "7")}),
            command_sha256 TEXT NOT NULL CHECK ({_sha256_check("command_sha256")}),
            plan_sha256 TEXT NOT NULL CHECK ({_sha256_check("plan_sha256")}),
            intent_sha256 TEXT NOT NULL CHECK ({_sha256_check("intent_sha256")}),
            policy_sha256 TEXT NOT NULL CHECK ({_sha256_check("policy_sha256")}),
            plan_json TEXT NOT NULL CHECK (json_valid(plan_json)
                AND length(CAST(plan_json AS BLOB)) BETWEEN 2 AND 1048576 AND json_type(plan_json) IS 'object'
                AND json_extract(plan_json,'$.schemaVersion') IS '1.0'
                AND json_extract(plan_json,'$.action') IN ('register','revise','relate','prefer')
                AND json_type(plan_json,'$.action') IS 'text'
                AND json_type(plan_json,'$.workIds') IS 'array' AND json_array_length(plan_json,'$.workIds')
                    BETWEEN 1 AND 8
                AND json_type(plan_json,'$.contextSha256') IS 'text'
                AND json_type(plan_json,'$.rationale') IS 'text'
                AND json_remove(plan_json,'$.schemaVersion','$.action','$.workIds','$.contextSha256','$.rationale',
                    '$.definition','$.version','$.relation','$.previousPreferenceRevisionId')='{{}}'),
            outcome_json TEXT NOT NULL CHECK (json_valid(outcome_json)
                AND length(CAST(outcome_json AS BLOB)) BETWEEN 2 AND 4194304 AND json_type(outcome_json) IS 'object'
                AND json_extract(outcome_json,'$.decisionRevisionId') IS revision_id
                AND json_extract(outcome_json,'$.commandId') IS command_id
                AND json_extract(outcome_json,'$.planSha256') IS plan_sha256
                AND json_type(outcome_json,'$.versionRevisions') IS 'array'
                AND json_array_length(outcome_json,'$.versionRevisions') BETWEEN 0 AND 256
                AND json_type(outcome_json,'$.workStates') IS 'array'
                AND json_array_length(outcome_json,'$.workStates') BETWEEN 0 AND 8
                AND json_type(outcome_json,'$.dependencyRunIds') IS 'array'
                AND json_array_length(outcome_json,'$.dependencyRunIds') BETWEEN 0 AND 264
                AND json_remove(outcome_json,'$.commandId','$.decisionId','$.decisionRevisionId','$.planSha256',
                    '$.versionRevisions','$.relationRevisionId','$.preferenceRevisionId','$.workStates',
                        '$.dependencyRunIds')='{{}}'),
            FOREIGN KEY (revision_id,aggregate_kind,project_id) REFERENCES aggregate_revisions (revision_id,
                aggregate_kind,project_id),
            UNIQUE (project_id,command_id),
            UNIQUE (revision_id,project_id)
        ) STRICT
    """,
    """
        CREATE TABLE reconciliation_version_impacts (
            run_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            decision_revision_id TEXT NOT NULL,
            previous_revision_id TEXT NOT NULL,
            replacement_revision_id TEXT NOT NULL,
            FOREIGN KEY (run_id,project_id) REFERENCES dependency_impact_runs (run_id,project_id),
            FOREIGN KEY (decision_revision_id,project_id) REFERENCES reconciliation_version_decisions
                (revision_id,project_id),
            FOREIGN KEY (previous_revision_id,project_id) REFERENCES aggregate_revisions (revision_id,project_id),
            FOREIGN KEY (replacement_revision_id,project_id) REFERENCES aggregate_revisions (revision_id,project_id)
        ) STRICT
    """,
    *(
        statement
        for table in WORK_VERSION_TABLES
        for statement in _immutable_triggers(table, "scholarly version history is append-only")
    ),
    "CREATE INDEX reconciliation_version_source_lookup "
    "ON reconciliation_version_sources (project_id,assertion_revision_id)",
    "CREATE INDEX reconciliation_version_relation_target "
    "ON reconciliation_version_relations (project_id,target_revision_id)",
    "CREATE INDEX reconciliation_version_relation_source "
    "ON reconciliation_version_relations (project_id,source_revision_id)",
    "CREATE INDEX reconciliation_version_preference_work ON reconciliation_version_preferences (project_id,work_id)",
    *(
        f"""
        CREATE TRIGGER reconciliation_version_{name}_exclusion BEFORE INSERT ON {table}
        WHEN EXISTS (SELECT 1 FROM reconciliation_versions v WHERE v.project_id=NEW.project_id AND
            v.version_id={identity})
          OR EXISTS (SELECT 1 FROM reconciliation_version_relations r WHERE r.project_id=NEW.project_id AND
              r.relation_id={identity})
        BEGIN SELECT RAISE(ABORT, 'scholarly version subtype identity denied'); END
        """
        for name, table, identity in (
            ("work", "reconciliation_work_states", "NEW.work_id"),
            ("import", "import_source_records", "NEW.aggregate_id"),
            (
                "assertion",
                "reconciliation_assertions",
                "(SELECT aggregate_id FROM aggregate_revisions "
                "WHERE project_id=NEW.project_id AND revision_id=NEW.revision_id)",
            ),
        )
    ),
    """
        CREATE TRIGGER reconciliation_version_decision_binding BEFORE INSERT ON reconciliation_version_decisions
        WHEN NOT EXISTS (SELECT 1 FROM material_dependencies m WHERE m.project_id=NEW.project_id
            AND m.output_revision_id=NEW.revision_id AND m.configuration_id='scholarly.version-plan'
            AND m.fingerprint='sha256:' || NEW.plan_sha256)
          OR EXISTS (SELECT 1 FROM aggregate_revisions a JOIN reconciliation_version_preferences p ON
              p.preference_id=a.aggregate_id
            WHERE a.revision_id=NEW.revision_id AND a.project_id=NEW.project_id AND p.project_id=NEW.project_id)
          OR EXISTS (SELECT 1 FROM aggregate_revisions a JOIN aggregate_revisions b ON b.aggregate_id=a.aggregate_id
            JOIN reconciliation_review_decisions d ON d.revision_id=b.revision_id
            WHERE a.revision_id=NEW.revision_id AND a.project_id=NEW.project_id AND d.project_id=NEW.project_id)
        BEGIN SELECT RAISE(ABORT, 'scholarly version command identity denied'); END
    """,
    """
        CREATE TRIGGER reconciliation_version_binding BEFORE INSERT ON reconciliation_versions
        WHEN NOT EXISTS (SELECT 1 FROM material_dependencies m WHERE m.project_id=NEW.project_id
            AND m.output_revision_id=NEW.revision_id AND m.configuration_id='scholarly.version-content'
            AND m.fingerprint='sha256:' || NEW.content_sha256)
        OR EXISTS (SELECT 1 FROM reconciliation_work_states WHERE project_id=NEW.project_id AND work_id=NEW.version_id)
        OR EXISTS (SELECT 1 FROM reconciliation_assertions a JOIN aggregate_revisions r ON r.revision_id=a.revision_id
            WHERE r.project_id=NEW.project_id AND r.aggregate_id=NEW.version_id)
        OR EXISTS (SELECT 1 FROM import_source_records WHERE project_id=NEW.project_id AND aggregate_id=NEW.version_id)
        OR EXISTS (SELECT 1 FROM reconciliation_version_relations WHERE project_id=NEW.project_id AND
            relation_id=NEW.version_id)
        OR NOT EXISTS (SELECT 1 FROM aggregate_revisions r WHERE r.revision_id=NEW.revision_id
            AND r.project_id=NEW.project_id AND r.aggregate_id=NEW.version_id AND r.aggregate_kind='record'
            AND ((r.revision=0 AND NEW.previous_revision_id IS NULL) OR EXISTS (
                SELECT 1 FROM aggregate_revisions p JOIN reconciliation_versions v ON v.revision_id=p.revision_id
                WHERE p.revision_id=NEW.previous_revision_id AND p.project_id=r.project_id
                    AND p.aggregate_id=r.aggregate_id AND p.revision=r.revision-1)))
        BEGIN SELECT RAISE(ABORT,'scholarly version revision binding denied'); END
    """,
    """
        CREATE TRIGGER reconciliation_version_source_binding BEFORE INSERT ON reconciliation_version_sources
        WHEN NEW.ordinal<>(SELECT COUNT(*)+1 FROM reconciliation_version_sources WHERE
            version_revision_id=NEW.version_revision_id)
            OR NEW.ordinal>(SELECT source_count FROM reconciliation_versions WHERE revision_id=NEW.version_revision_id)
            OR EXISTS (SELECT 1 FROM reconciliation_version_sources WHERE version_revision_id=NEW.version_revision_id
                AND assertion_revision_id>=NEW.assertion_revision_id)
        BEGIN SELECT RAISE(ABORT,'scholarly version source binding denied'); END
    """,
    """
        CREATE TRIGGER reconciliation_relation_binding BEFORE INSERT ON reconciliation_version_relations
        WHEN NOT EXISTS (SELECT 1 FROM material_dependencies m WHERE m.project_id=NEW.project_id
            AND m.output_revision_id=NEW.revision_id AND m.configuration_id='scholarly.version-relation'
            AND m.fingerprint='sha256:' || NEW.content_sha256)
        OR EXISTS (SELECT 1 FROM reconciliation_work_states WHERE project_id=NEW.project_id AND work_id=NEW.relation_id)
        OR EXISTS (SELECT 1 FROM reconciliation_versions WHERE project_id=NEW.project_id AND version_id=NEW.relation_id)
        OR EXISTS (SELECT 1 FROM reconciliation_assertions a JOIN aggregate_revisions r ON r.revision_id=a.revision_id
            WHERE r.project_id=NEW.project_id AND r.aggregate_id=NEW.relation_id)
        OR EXISTS (SELECT 1 FROM import_source_records WHERE project_id=NEW.project_id AND aggregate_id=NEW.relation_id)
        OR NOT EXISTS (SELECT 1 FROM aggregate_revisions r WHERE r.revision_id=NEW.revision_id
            AND r.project_id=NEW.project_id AND r.aggregate_id=NEW.relation_id AND r.aggregate_kind='record'
                AND r.revision=0)
            OR EXISTS (SELECT 1 FROM reconciliation_versions s JOIN reconciliation_versions t ON
                s.version_id=t.version_id
                WHERE s.revision_id=NEW.source_revision_id AND t.revision_id=NEW.target_revision_id)
        BEGIN SELECT RAISE(ABORT,'scholarly version relation binding denied'); END
    """,
    """
        CREATE TRIGGER reconciliation_relation_evidence_binding BEFORE INSERT ON reconciliation_relation_evidence
        WHEN NEW.ordinal<>(SELECT COUNT(*)+1 FROM reconciliation_relation_evidence WHERE
            relation_revision_id=NEW.relation_revision_id)
            OR NEW.ordinal>(SELECT evidence_count FROM reconciliation_version_relations WHERE
                revision_id=NEW.relation_revision_id)
        BEGIN SELECT RAISE(ABORT,'scholarly version evidence binding denied'); END
    """,
    """
        CREATE TRIGGER reconciliation_preference_binding BEFORE INSERT ON reconciliation_version_preferences
        WHEN NOT EXISTS (SELECT 1 FROM material_dependencies m WHERE m.project_id=NEW.project_id
            AND m.output_revision_id=NEW.revision_id AND m.configuration_id='scholarly.version-preference')
        OR EXISTS (SELECT 1 FROM reconciliation_review_decisions d JOIN aggregate_revisions r ON
            r.revision_id=d.revision_id
            WHERE r.project_id=NEW.project_id AND r.aggregate_id=NEW.preference_id)
        OR EXISTS (SELECT 1 FROM reconciliation_version_decisions d JOIN aggregate_revisions r ON
            r.revision_id=d.revision_id
            WHERE r.project_id=NEW.project_id AND r.aggregate_id=NEW.preference_id)
        OR NOT EXISTS (SELECT 1 FROM aggregate_revisions r WHERE r.revision_id=NEW.revision_id
            AND r.project_id=NEW.project_id AND r.aggregate_id=NEW.preference_id AND r.aggregate_kind='decision'
            AND ((r.revision=0 AND NEW.previous_revision_id IS NULL) OR EXISTS (
                SELECT 1 FROM aggregate_revisions p JOIN reconciliation_version_preferences v ON
                    v.revision_id=p.revision_id
                WHERE p.revision_id=NEW.previous_revision_id AND p.project_id=r.project_id
                    AND v.work_id=NEW.work_id AND p.aggregate_id=r.aggregate_id AND p.revision=r.revision-1)))
        BEGIN SELECT RAISE(ABORT,'scholarly version preference binding denied'); END
    """,
    """
        CREATE TRIGGER reconciliation_version_impact_binding BEFORE INSERT ON reconciliation_version_impacts
        WHEN NOT EXISTS (SELECT 1 FROM dependency_impact_runs r JOIN reconciliation_version_decisions d ON
            d.project_id=r.project_id
            WHERE r.run_id=NEW.run_id AND r.project_id=NEW.project_id AND d.revision_id=NEW.decision_revision_id
                AND r.previous_revision_id=NEW.previous_revision_id AND
                    r.replacement_revision_id=NEW.replacement_revision_id
                AND r.reason='HUMAN_DECISION' AND r.actor_id=d.actor_id
                AND r.dependency_kind=(SELECT CASE aggregate_kind WHEN 'decision' THEN 'human-decision' ELSE
                    'source-revision' END
                    FROM aggregate_revisions WHERE revision_id=NEW.previous_revision_id AND project_id=NEW.project_id)
                AND EXISTS (SELECT 1 FROM json_each(d.outcome_json,'$.dependencyRunIds') WHERE value=NEW.run_id))
            OR EXISTS (SELECT 1 FROM reconciliation_exact_impacts WHERE run_id=NEW.run_id)
            OR EXISTS (SELECT 1 FROM reconciliation_review_decisions d,json_each(d.outcome_json,
                '$.dependencyRunIds') WHERE value=NEW.run_id)
        BEGIN SELECT RAISE(ABORT,'scholarly version impact binding denied'); END
    """,
    "DROP TRIGGER reconciliation_impact_continuation_binding",
    next(
        statement
        for statement in RECONCILIATION_REVIEW_DDL
        if "CREATE TRIGGER reconciliation_impact_continuation_binding" in statement
    ).replace(
        "EXISTS (SELECT 1 FROM reconciliation_exact_impacts x WHERE x.project_id=NEW.project_id",
        "EXISTS (SELECT 1 FROM reconciliation_version_impacts v "
        "WHERE v.project_id=NEW.project_id AND v.run_id=NEW.root_run_id) "
        "OR EXISTS (SELECT 1 FROM reconciliation_exact_impacts x WHERE x.project_id=NEW.project_id",
    ),
)


_V6_BASE_DDL_STATEMENTS = tuple(
    PROVENANCE_EVENTS_V6_DDL if "CREATE TABLE provenance_events" in statement else statement
    for statement in _V1_DDL_STATEMENTS[1:]
)

SCHEMA_METADATA_V14_DDL = SCHEMA_METADATA_V13_DDL.replace("schema_version = 13", "schema_version = 14")
SCHEMA_METADATA_V15_DDL = SCHEMA_METADATA_V14_DDL.replace("schema_version = 14", "schema_version = 15")

SCHEMA_METADATA_V16_DDL = SCHEMA_METADATA_V15_DDL.replace("schema_version = 15", "schema_version = 16")
SCHEMA_METADATA_V17_DDL = SCHEMA_METADATA_V16_DDL.replace("schema_version = 16", "schema_version = 17")
SCHEMA_METADATA_V18_DDL = SCHEMA_METADATA_V17_DDL.replace("schema_version = 17", "schema_version = 18")
SCHEMA_METADATA_V19_DDL = SCHEMA_METADATA_V18_DDL.replace("schema_version = 18", "schema_version = 19")
SCHEMA_METADATA_V20_DDL = SCHEMA_METADATA_V19_DDL.replace("schema_version = 19", "schema_version = 20")
SCHEMA_METADATA_V21_DDL = SCHEMA_METADATA_V20_DDL.replace("schema_version = 20", "schema_version = 21")
SCHEMA_METADATA_V22_DDL = SCHEMA_METADATA_V21_DDL.replace("schema_version = 21", "schema_version = 22")
SCHEMA_METADATA_V23_DDL = SCHEMA_METADATA_V22_DDL.replace("schema_version = 22", "schema_version = 23")
SCHEMA_METADATA_V24_DDL = SCHEMA_METADATA_V23_DDL.replace("schema_version = 23", "schema_version = 24")
SCHEMA_METADATA_V25_DDL = SCHEMA_METADATA_V24_DDL.replace("schema_version = 24", "schema_version = 25")

_V16_AGGREGATE_IDENTITY_DDL = next(
    statement for statement in _V1_DDL_STATEMENTS if "CREATE TABLE aggregate_identities" in statement
)
_V16_AGGREGATE_REVISION_DDL = next(
    statement for statement in _V1_DDL_STATEMENTS if "CREATE TABLE aggregate_revisions" in statement
)
_V17_KIND_LIST = "'record', 'document', 'workflow', 'evidence', 'ontology', 'decision', 'corpus-item'"
_V16_KIND_LIST = "'record', 'document', 'workflow', 'evidence', 'ontology', 'decision'"
AGGREGATE_IDENTITIES_V17_DDL = _V16_AGGREGATE_IDENTITY_DDL.replace(_V16_KIND_LIST, _V17_KIND_LIST)
AGGREGATE_REVISIONS_V17_DDL = _V16_AGGREGATE_REVISION_DDL.replace(_V16_KIND_LIST, _V17_KIND_LIST).replace(
    "contract_version TEXT NOT NULL CHECK (contract_version = '1.0.0')",
    "contract_version TEXT NOT NULL CHECK ((aggregate_kind = 'corpus-item' AND contract_version = '2.0.0') "
    "OR (aggregate_kind <> 'corpus-item' AND contract_version = '1.0.0'))",
)
if (
    AGGREGATE_IDENTITIES_V17_DDL == _V16_AGGREGATE_IDENTITY_DDL
    or AGGREGATE_REVISIONS_V17_DDL == _V16_AGGREGATE_REVISION_DDL
    or "contract_version = '2.0.0'" not in AGGREGATE_REVISIONS_V17_DDL
):
    raise RuntimeError("compiled v17 aggregate widening differs from the v16 authority")

_V16_DEPENDENCY_IMPACT_ITEMS_DDL = next(
    statement for statement in DEPENDENCY_IMPACT_DDL if "CREATE TABLE dependency_impact_items" in statement
)
DEPENDENCY_IMPACT_ITEMS_V17_DDL = _V16_DEPENDENCY_IMPACT_ITEMS_DDL.replace(_V16_KIND_LIST, _V17_KIND_LIST)
if DEPENDENCY_IMPACT_ITEMS_V17_DDL == _V16_DEPENDENCY_IMPACT_ITEMS_DDL:
    raise RuntimeError("compiled v17 impact-kind widening differs from the v16 authority")
_V17_DEPENDENCY_IMPACT_DDL = tuple(
    DEPENDENCY_IMPACT_ITEMS_V17_DDL if "CREATE TABLE dependency_impact_items" in statement else statement
    for statement in DEPENDENCY_IMPACT_DDL
)

CORPUS_DDL = (
    """
        CREATE TABLE corpus_items (
            revision_id TEXT PRIMARY KEY,
            aggregate_kind TEXT NOT NULL DEFAULT 'corpus-item' CHECK (aggregate_kind = 'corpus-item'),
            FOREIGN KEY (revision_id, aggregate_kind)
                REFERENCES aggregate_revisions (revision_id, aggregate_kind)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (revision_id) REFERENCES corpus_item_states (revision_id)
                DEFERRABLE INITIALLY DEFERRED
        ) STRICT
    """,
    f"""
        CREATE TABLE corpus_item_states (
            revision_id TEXT PRIMARY KEY CHECK ({_uuid_check("revision_id", "7")}),
            project_id TEXT NOT NULL,
            item_id TEXT NOT NULL CHECK ({_uuid_check("item_id", "7")}),
            item_kind TEXT NOT NULL DEFAULT 'corpus-item' CHECK (item_kind = 'corpus-item'),
            previous_revision_id TEXT CHECK (
                previous_revision_id IS NULL OR ({_uuid_check("previous_revision_id", "7")})
            ),
            work_id TEXT NOT NULL CHECK ({_uuid_check("work_id", "7")}),
            work_revision_id TEXT NOT NULL CHECK ({_uuid_check("work_revision_id", "7")}),
            work_kind TEXT NOT NULL DEFAULT 'record' CHECK (work_kind = 'record'),
            membership TEXT NOT NULL CHECK (membership IN ('candidate', 'included', 'excluded', 'withdrawn')),
            review TEXT NOT NULL CHECK (review IN ('none', 'pending')),
            duplicate_of_item_id TEXT CHECK (
                duplicate_of_item_id IS NULL OR ({_uuid_check("duplicate_of_item_id", "7")})
            ),
            availability TEXT NOT NULL CHECK (
                availability IN ('unknown', 'not-applicable', 'available', 'unavailable')
            ),
            primary_discovery_path_id TEXT NOT NULL CHECK ({_uuid_check("primary_discovery_path_id", "7")}),
            discovery_fingerprint TEXT NOT NULL CHECK ({_sha256_check("discovery_fingerprint")}),
            decision_revision_id TEXT CHECK (
                decision_revision_id IS NULL OR ({_uuid_check("decision_revision_id", "7")})
            ),
            FOREIGN KEY (revision_id) REFERENCES corpus_items (revision_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (revision_id, project_id) REFERENCES aggregate_revisions (revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (item_id, project_id, item_kind)
                REFERENCES aggregate_identities (aggregate_id, project_id, aggregate_kind)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (work_id, project_id, work_kind)
                REFERENCES aggregate_identities (aggregate_id, project_id, aggregate_kind)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (previous_revision_id, item_id, project_id)
                REFERENCES corpus_item_states (revision_id, item_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (revision_id, primary_discovery_path_id)
                REFERENCES corpus_item_discovery_paths (revision_id, path_id)
                DEFERRABLE INITIALLY DEFERRED,
            FOREIGN KEY (decision_revision_id) REFERENCES corpus_decisions (decision_id)
                DEFERRABLE INITIALLY DEFERRED,
            CHECK (item_id <> work_id AND revision_id <> item_id AND duplicate_of_item_id IS NOT item_id),
            CHECK ((previous_revision_id IS NULL AND membership = 'candidate' AND review = 'pending'
                AND duplicate_of_item_id IS NULL AND availability = 'unknown' AND decision_revision_id IS NULL)
                OR (previous_revision_id IS NOT NULL AND decision_revision_id IS NOT NULL)),
            UNIQUE (revision_id, item_id, project_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE corpus_discovery_paths (
            path_id TEXT PRIMARY KEY CHECK ({_uuid_check("path_id", "7")}),
            project_id TEXT NOT NULL,
            item_id TEXT NOT NULL CHECK ({_uuid_check("item_id", "7")}),
            item_kind TEXT NOT NULL DEFAULT 'corpus-item' CHECK (item_kind = 'corpus-item'),
            direction TEXT NOT NULL CHECK (direction = 'source-to-corpus-item'),
            occurred_at TEXT NOT NULL CHECK ({_timestamp_check("occurred_at")}),
            predecessor_item_revision_id TEXT CHECK (
                predecessor_item_revision_id IS NULL OR ({_uuid_check("predecessor_item_revision_id", "7")})
            ),
            kind TEXT NOT NULL CHECK (
                kind IN ('import-member', 'connector-record', 'citation', 'recommendation', 'manual')
            ),
            source_revision_id TEXT NOT NULL CHECK ({_uuid_check("source_revision_id", "7")}),
            context_id TEXT NOT NULL CHECK ({_uuid_check("context_id", "7")}),
            context_revision_id TEXT NOT NULL CHECK ({_uuid_check("context_revision_id", "7")}),
            ordinal INTEGER CHECK (ordinal BETWEEN 0 AND 200000),
            record_key_sha256 TEXT CHECK (record_key_sha256 IS NULL OR ({_sha256_check("record_key_sha256")})),
            query_revision_id TEXT CHECK (query_revision_id IS NULL OR ({_uuid_check("query_revision_id", "7")})),
            citing_work_revision_id TEXT CHECK (
                citing_work_revision_id IS NULL OR ({_uuid_check("citing_work_revision_id", "7")})
            ),
            recommendation_revision_id TEXT CHECK (
                recommendation_revision_id IS NULL OR ({_uuid_check("recommendation_revision_id", "7")})
            ),
            manual_decision_revision_id TEXT CHECK (
                manual_decision_revision_id IS NULL OR ({_uuid_check("manual_decision_revision_id", "7")})
            ),
            FOREIGN KEY (item_id, project_id, item_kind)
                REFERENCES aggregate_identities (aggregate_id, project_id, aggregate_kind)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (predecessor_item_revision_id, item_id, project_id)
                REFERENCES corpus_item_states (revision_id, item_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CHECK (path_id <> item_id AND path_id <> source_revision_id),
            CHECK (
                (kind = 'import-member' AND ordinal BETWEEN 1 AND 200000 AND record_key_sha256 IS NOT NULL
                    AND query_revision_id IS NULL AND citing_work_revision_id IS NULL
                    AND recommendation_revision_id IS NULL AND manual_decision_revision_id IS NULL)
                OR (kind = 'connector-record' AND ordinal BETWEEN 0 AND 999 AND record_key_sha256 IS NULL
                    AND query_revision_id IS NOT NULL AND citing_work_revision_id IS NULL
                    AND recommendation_revision_id IS NULL AND manual_decision_revision_id IS NULL)
                OR (kind = 'citation' AND ordinal IS NULL AND record_key_sha256 IS NULL
                    AND query_revision_id IS NULL AND citing_work_revision_id IS NOT NULL
                    AND recommendation_revision_id IS NULL AND manual_decision_revision_id IS NULL)
                OR (kind = 'recommendation' AND ordinal IS NULL AND record_key_sha256 IS NULL
                    AND query_revision_id IS NULL AND citing_work_revision_id IS NULL
                    AND recommendation_revision_id IS NOT NULL AND manual_decision_revision_id IS NULL)
                OR (kind = 'manual' AND ordinal IS NULL AND record_key_sha256 IS NULL
                    AND query_revision_id IS NULL AND citing_work_revision_id IS NULL
                    AND recommendation_revision_id IS NULL AND manual_decision_revision_id IS NOT NULL)
            ),
            UNIQUE (path_id, project_id, item_id)
        ) STRICT
    """,
    """
        CREATE TABLE corpus_item_discovery_paths (
            revision_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            item_id TEXT NOT NULL,
            path_id TEXT NOT NULL,
            FOREIGN KEY (revision_id, item_id, project_id)
                REFERENCES corpus_item_states (revision_id, item_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (path_id, project_id, item_id)
                REFERENCES corpus_discovery_paths (path_id, project_id, item_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            PRIMARY KEY (revision_id, path_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE corpus_decisions (
            decision_id TEXT PRIMARY KEY CHECK ({_uuid_check("decision_id", "7")}),
            project_id TEXT NOT NULL,
            item_id TEXT NOT NULL CHECK ({_uuid_check("item_id", "7")}),
            previous_revision_id TEXT NOT NULL CHECK ({_uuid_check("previous_revision_id", "7")}),
            next_revision_id TEXT NOT NULL CHECK ({_uuid_check("next_revision_id", "7")}),
            dimension TEXT NOT NULL CHECK (dimension IN
                ('membership', 'review', 'duplicate', 'availability', 'discovery', 'work-reference')),
            command TEXT NOT NULL CHECK (length(command) BETWEEN 1 AND 64),
            previous_value TEXT NOT NULL CHECK (length(previous_value) BETWEEN 1 AND 64),
            next_value TEXT NOT NULL CHECK (length(next_value) BETWEEN 1 AND 64),
            previous_decision_revision_id TEXT CHECK (previous_decision_revision_id IS NULL OR
                ({_uuid_check("previous_decision_revision_id", "7")})),
            supersedes_decision_revision_id TEXT CHECK (supersedes_decision_revision_id IS NULL OR
                ({_uuid_check("supersedes_decision_revision_id", "7")})),
            next_work_id TEXT CHECK (next_work_id IS NULL OR ({_uuid_check("next_work_id", "7")})),
            actor_id TEXT NOT NULL CHECK ({_uuid_check("actor_id", "7")}),
            reason_code TEXT NOT NULL CHECK (length(reason_code) BETWEEN 1 AND 64),
            protocol_revision_id TEXT NOT NULL CHECK ({_uuid_check("protocol_revision_id", "7")}),
            occurred_at TEXT NOT NULL CHECK ({_timestamp_check("occurred_at")}),
            FOREIGN KEY (previous_revision_id, item_id, project_id)
                REFERENCES corpus_item_states (revision_id, item_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (next_revision_id, item_id, project_id)
                REFERENCES corpus_item_states (revision_id, item_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CHECK (previous_revision_id <> next_revision_id AND previous_value <> next_value
                AND decision_id <> item_id AND decision_id <> previous_revision_id
                AND decision_id <> next_revision_id AND supersedes_decision_revision_id IS NOT decision_id
                AND previous_decision_revision_id IS NOT decision_id),
            CHECK ((dimension = 'work-reference' AND next_work_id IS NOT NULL)
                OR (dimension <> 'work-reference' AND next_work_id IS NULL)),
            UNIQUE (project_id, item_id, next_revision_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE corpus_decision_evidence (
            decision_id TEXT NOT NULL,
            evidence_revision_id TEXT NOT NULL CHECK ({_uuid_check("evidence_revision_id", "7")}),
            FOREIGN KEY (decision_id) REFERENCES corpus_decisions (decision_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            PRIMARY KEY (decision_id, evidence_revision_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE corpus_commands (
            project_id TEXT NOT NULL,
            command_id TEXT NOT NULL CHECK ({_uuid_check("command_id", "7")}),
            semantic_sha256 TEXT NOT NULL CHECK ({_sha256_check("semantic_sha256")}),
            result_item_id TEXT NOT NULL CHECK ({_uuid_check("result_item_id", "7")}),
            result_revision_id TEXT NOT NULL CHECK ({_uuid_check("result_revision_id", "7")}),
            result_path_id TEXT CHECK (result_path_id IS NULL OR ({_uuid_check("result_path_id", "7")})),
            result_decision_id TEXT CHECK (result_decision_id IS NULL OR ({_uuid_check("result_decision_id", "7")})),
            provenance_event_id TEXT CHECK (provenance_event_id IS NULL OR ({_uuid_check("provenance_event_id", "7")})),
            outbox_id TEXT CHECK (outbox_id IS NULL OR ({_uuid_check("outbox_id", "7")})),
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (result_revision_id, result_item_id, project_id)
                REFERENCES corpus_item_states (revision_id, item_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (result_path_id, project_id, result_item_id)
                REFERENCES corpus_discovery_paths (path_id, project_id, item_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (result_decision_id) REFERENCES corpus_decisions (decision_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (provenance_event_id) REFERENCES provenance_events (event_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (outbox_id) REFERENCES outbox_events (outbox_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CHECK (result_path_id IS NOT NULL OR result_decision_id IS NOT NULL),
            PRIMARY KEY (project_id, command_id)
        ) STRICT
    """,
    "CREATE INDEX corpus_item_states_current ON corpus_item_states (project_id, item_id, revision_id)",
    "CREATE INDEX corpus_discovery_paths_item ON corpus_discovery_paths (project_id, item_id, path_id)",
    "CREATE INDEX corpus_decisions_item ON corpus_decisions (project_id, item_id, next_revision_id)",
    *(
        statement
        for table in (
            "corpus_items",
            "corpus_item_states",
            "corpus_discovery_paths",
            "corpus_item_discovery_paths",
            "corpus_decisions",
            "corpus_decision_evidence",
            "corpus_commands",
        )
        for statement in _immutable_triggers(table, f"{table} history is append-only")
    ),
    """
        CREATE TRIGGER corpus_item_state_work_binding BEFORE INSERT ON corpus_item_states
        WHEN NOT EXISTS (
            SELECT 1 FROM aggregate_revisions
            WHERE revision_id = NEW.work_revision_id AND aggregate_id = NEW.work_id
              AND aggregate_kind = 'record' AND project_id = NEW.project_id
        ) OR NOT EXISTS (
            SELECT 1 FROM aggregate_revisions
            WHERE revision_id = NEW.revision_id AND aggregate_id = NEW.item_id
              AND aggregate_kind = 'corpus-item' AND project_id = NEW.project_id
        ) OR (NEW.duplicate_of_item_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM aggregate_identities
            WHERE aggregate_id = NEW.duplicate_of_item_id AND aggregate_kind = 'corpus-item'
              AND project_id = NEW.project_id
        ))
        BEGIN SELECT RAISE(ABORT, 'corpus item state binding denied'); END
    """,
    """
        CREATE TRIGGER corpus_discovery_path_predecessor_binding BEFORE INSERT ON corpus_discovery_paths
        WHEN (NEW.predecessor_item_revision_id IS NULL AND EXISTS (
            SELECT 1 FROM corpus_item_states
            WHERE item_id = NEW.item_id AND project_id = NEW.project_id
        )) OR (NEW.predecessor_item_revision_id IS NOT NULL AND NEW.predecessor_item_revision_id IS NOT (
            SELECT state.revision_id FROM corpus_item_states state
            JOIN aggregate_revisions revision ON revision.revision_id = state.revision_id
            WHERE state.item_id = NEW.item_id AND state.project_id = NEW.project_id
            ORDER BY revision.revision DESC LIMIT 1
        ))
        BEGIN SELECT RAISE(ABORT, 'corpus discovery predecessor binding denied'); END
    """,
    """
        CREATE TRIGGER corpus_decision_chain_binding BEFORE INSERT ON corpus_decisions
        WHEN NOT EXISTS (
            SELECT 1 FROM corpus_item_states prior JOIN corpus_item_states next
              ON next.item_id = prior.item_id AND next.project_id = prior.project_id
            WHERE prior.revision_id = NEW.previous_revision_id
              AND next.revision_id = NEW.next_revision_id
              AND prior.item_id = NEW.item_id AND prior.project_id = NEW.project_id
              AND next.previous_revision_id = prior.revision_id
              AND prior.decision_revision_id IS NEW.previous_decision_revision_id
              AND next.decision_revision_id = NEW.decision_id
              AND prior.membership <> 'withdrawn'
              AND (NEW.dimension <> 'work-reference' OR next.work_id = NEW.next_work_id)
              AND (NEW.dimension <> 'work-reference' OR prior.work_id = next.work_id)
              AND (NEW.dimension = 'membership' OR prior.membership = next.membership)
              AND (NEW.dimension = 'review' OR prior.review = next.review)
              AND (NEW.dimension = 'duplicate' OR prior.duplicate_of_item_id IS next.duplicate_of_item_id)
              AND (NEW.dimension = 'availability' OR prior.availability = next.availability)
              AND (NEW.dimension = 'work-reference'
                  OR (prior.work_id = next.work_id AND prior.work_revision_id = next.work_revision_id))
              AND (NEW.dimension = 'discovery'
                  OR (prior.discovery_fingerprint = next.discovery_fingerprint
                      AND prior.primary_discovery_path_id = next.primary_discovery_path_id))
              AND (
                (NEW.dimension = 'membership'
                    AND NEW.previous_value = prior.membership AND NEW.next_value = next.membership
                    AND NEW.command = CASE
                        WHEN prior.membership = 'candidate' AND next.membership = 'included' THEN 'include'
                        WHEN prior.membership = 'candidate' AND next.membership = 'excluded' THEN 'exclude'
                        WHEN prior.membership = 'candidate' AND next.membership = 'withdrawn' THEN 'withdraw'
                        WHEN prior.membership = 'included' AND next.membership = 'candidate' THEN 'reconsider'
                        WHEN prior.membership = 'included' AND next.membership = 'withdrawn' THEN 'withdraw'
                        WHEN prior.membership = 'excluded' AND next.membership = 'candidate' THEN 'reconsider'
                        WHEN prior.membership = 'excluded' AND next.membership = 'withdrawn' THEN 'withdraw'
                    END)
                OR (NEW.dimension = 'review'
                    AND NEW.previous_value = prior.review AND NEW.next_value = next.review
                    AND NEW.command = CASE WHEN next.review = 'pending' THEN 'queue-review'
                        ELSE 'resolve-review' END)
                OR (NEW.dimension = 'availability'
                    AND NEW.previous_value = prior.availability AND NEW.next_value = next.availability
                    AND NEW.command = 'mark-' || next.availability)
                OR (NEW.dimension = 'duplicate'
                    AND NEW.previous_value = COALESCE(prior.duplicate_of_item_id, 'none')
                    AND NEW.next_value = COALESCE(next.duplicate_of_item_id, 'none')
                    AND NEW.command = CASE WHEN next.duplicate_of_item_id IS NULL THEN 'clear-duplicate'
                        ELSE 'mark-duplicate' END)
                OR (NEW.dimension = 'work-reference'
                    AND NEW.previous_value = prior.work_revision_id
                    AND NEW.next_value = next.work_revision_id AND NEW.command = 'rebind-work')
                OR (NEW.dimension = 'discovery'
                    AND NEW.previous_value = prior.discovery_fingerprint
                    AND next.discovery_fingerprint <> prior.discovery_fingerprint
                    AND NEW.command = 'add-discovery'
                    AND EXISTS (SELECT 1 FROM corpus_item_discovery_paths added
                        WHERE added.revision_id = next.revision_id AND added.path_id = NEW.next_value)
                    AND NOT EXISTS (SELECT 1 FROM corpus_item_discovery_paths old_added
                        WHERE old_added.revision_id = prior.revision_id AND old_added.path_id = NEW.next_value))
              )
              AND NOT EXISTS (
                  SELECT 1 FROM corpus_item_discovery_paths old_path
                  WHERE old_path.revision_id = prior.revision_id
                    AND NOT EXISTS (
                        SELECT 1 FROM corpus_item_discovery_paths new_path
                        WHERE new_path.revision_id = next.revision_id AND new_path.path_id = old_path.path_id
                    )
              )
              AND (SELECT COUNT(*) FROM corpus_item_discovery_paths WHERE revision_id = next.revision_id)
                = (SELECT COUNT(*) FROM corpus_item_discovery_paths WHERE revision_id = prior.revision_id)
                  + CASE WHEN NEW.dimension = 'discovery' THEN 1 ELSE 0 END
        ) OR NEW.supersedes_decision_revision_id IS NOT (
            SELECT prior_decision.decision_id FROM corpus_decisions prior_decision
            JOIN aggregate_revisions prior_revision
              ON prior_revision.revision_id = prior_decision.next_revision_id
            JOIN aggregate_revisions next_revision ON next_revision.revision_id = NEW.next_revision_id
            WHERE prior_decision.project_id = NEW.project_id
              AND prior_decision.item_id = NEW.item_id
              AND prior_decision.dimension = NEW.dimension
              AND prior_revision.aggregate_id = NEW.item_id
              AND prior_revision.revision < next_revision.revision
            ORDER BY prior_revision.revision DESC LIMIT 1
        ) OR (NEW.dimension = 'work-reference' AND NOT EXISTS (
            SELECT 1 FROM aggregate_identities
            WHERE aggregate_id = NEW.next_work_id AND project_id = NEW.project_id
              AND aggregate_kind = 'record'
        ))
        BEGIN SELECT RAISE(ABORT, 'corpus decision chain binding denied'); END
    """,
    """
        CREATE TRIGGER corpus_command_result_binding BEFORE INSERT ON corpus_commands
        WHEN (NEW.result_decision_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM corpus_decisions
            WHERE decision_id = NEW.result_decision_id AND project_id = NEW.project_id
              AND item_id = NEW.result_item_id AND next_revision_id = NEW.result_revision_id
        )) OR (NEW.result_path_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM corpus_item_discovery_paths
            WHERE path_id = NEW.result_path_id AND project_id = NEW.project_id
              AND item_id = NEW.result_item_id AND revision_id = NEW.result_revision_id
        )) OR (NEW.provenance_event_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM provenance_events
            WHERE event_id = NEW.provenance_event_id AND project_id = NEW.project_id
        )) OR (NEW.outbox_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM outbox_events
            WHERE outbox_id = NEW.outbox_id AND project_id = NEW.project_id
        ))
        BEGIN SELECT RAISE(ABORT, 'corpus command result binding denied'); END
    """,
)

_V17_BASE_DDL_STATEMENTS = tuple(
    AGGREGATE_IDENTITIES_V17_DDL
    if "CREATE TABLE aggregate_identities" in statement
    else AGGREGATE_REVISIONS_V17_DDL
    if "CREATE TABLE aggregate_revisions" in statement
    else statement
    for statement in _V6_BASE_DDL_STATEMENTS
)

RIGHTS_POLICY_DDL = (
    f"""
        CREATE TABLE rights_policy_subjects (
            project_id TEXT NOT NULL,
            subject_sha256 TEXT NOT NULL CHECK ({_sha256_check("subject_sha256")}),
            policy_id TEXT NOT NULL CHECK ({_uuid_check("policy_id", "7")}),
            policy_kind TEXT NOT NULL DEFAULT 'decision' CHECK (policy_kind = 'decision'),
            subject_json TEXT NOT NULL CHECK (
                json_valid(subject_json) AND length(CAST(subject_json AS BLOB)) BETWEEN 2 AND 16384
                AND json_type(subject_json) = 'object'
                AND json_extract(subject_json, '$.projectId') IS project_id
                AND json_extract(subject_json, '$.sourceAssertionRevisionId') IS source_assertion_revision_id
                AND json_extract(subject_json, '$.copyId') IS copy_id
                AND json_extract(subject_json, '$.copyLocation') IS copy_location
                AND json_extract(subject_json, '$.resourceClass') IS resource_class
            ),
            source_assertion_revision_id TEXT NOT NULL CHECK ({_uuid_check("source_assertion_revision_id", "7")}),
            copy_id TEXT NOT NULL CHECK ({_uuid_check("copy_id", "7")}),
            copy_location TEXT NOT NULL CHECK ({_identifier_check("copy_location", 64)}),
            resource_class TEXT NOT NULL CHECK ({_identifier_check("resource_class", 64)}),
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (policy_id, project_id, policy_kind)
                REFERENCES aggregate_identities (aggregate_id, project_id, aggregate_kind)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (source_assertion_revision_id, project_id)
                REFERENCES reconciliation_assertions (revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            PRIMARY KEY (project_id, subject_sha256),
            UNIQUE (project_id, subject_sha256, policy_id),
            UNIQUE (project_id, policy_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE rights_policy_revisions (
            revision_id TEXT PRIMARY KEY CHECK ({_uuid_check("revision_id", "7")}),
            policy_id TEXT NOT NULL CHECK ({_uuid_check("policy_id", "7")}),
            project_id TEXT NOT NULL,
            aggregate_kind TEXT NOT NULL DEFAULT 'decision' CHECK (aggregate_kind = 'decision'),
            subject_sha256 TEXT NOT NULL CHECK ({_sha256_check("subject_sha256")}),
            predecessor_revision_id TEXT CHECK (
                predecessor_revision_id IS NULL OR ({_uuid_check("predecessor_revision_id", "7")})
            ),
            revision_number INTEGER NOT NULL CHECK (revision_number BETWEEN 0 AND {MAX_SAFE_INTEGER}),
            policy_json TEXT NOT NULL CHECK (
                json_valid(policy_json) AND length(CAST(policy_json AS BLOB)) BETWEEN 2 AND 262144
                AND json_type(policy_json) = 'object'
                AND json_extract(policy_json, '$.revisionId') IS revision_id
                AND json_extract(policy_json, '$.predecessorRevisionId') IS predecessor_revision_id
                AND json_extract(policy_json, '$.subject.projectId') IS project_id
            ),
            policy_sha256 TEXT NOT NULL CHECK ({_sha256_check("policy_sha256")}),
            command_id TEXT NOT NULL CHECK ({_uuid_check("command_id", "7")}),
            command_sha256 TEXT NOT NULL CHECK ({_sha256_check("command_sha256")}),
            actor_id TEXT NOT NULL CHECK ({_uuid_check("actor_id", "7")}),
            occurred_at TEXT NOT NULL CHECK ({_timestamp_check("occurred_at")}),
            FOREIGN KEY (revision_id, aggregate_kind, project_id)
                REFERENCES aggregate_revisions (revision_id, aggregate_kind, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (policy_id, project_id, aggregate_kind)
                REFERENCES aggregate_identities (aggregate_id, project_id, aggregate_kind)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (project_id, subject_sha256, policy_id)
                REFERENCES rights_policy_subjects (project_id, subject_sha256, policy_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (predecessor_revision_id, project_id, subject_sha256, policy_id)
                REFERENCES rights_policy_revisions (revision_id, project_id, subject_sha256, policy_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CHECK ((revision_number = 0 AND predecessor_revision_id IS NULL)
                OR (revision_number > 0 AND predecessor_revision_id IS NOT NULL)),
            CHECK (revision_id <> policy_id AND revision_id IS NOT predecessor_revision_id),
            UNIQUE (project_id, subject_sha256, revision_number),
            UNIQUE (project_id, command_id),
            UNIQUE (revision_id, project_id),
            UNIQUE (project_id, revision_id, subject_sha256),
            UNIQUE (revision_id, project_id, subject_sha256, policy_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE rights_policy_rechecks (
            recheck_id TEXT PRIMARY KEY CHECK ({_uuid_check("recheck_id", "7")}),
            project_id TEXT NOT NULL,
            rights_revision_id TEXT NOT NULL CHECK ({_uuid_check("rights_revision_id", "7")}),
            source_assertion_revision_id TEXT NOT NULL CHECK ({_uuid_check("source_assertion_revision_id", "7")}),
            item_id TEXT NOT NULL CHECK ({_uuid_check("item_id", "7")}),
            path_id TEXT NOT NULL CHECK ({_uuid_check("path_id", "7")}),
            output_revision_id TEXT NOT NULL CHECK ({_uuid_check("output_revision_id", "7")}),
            reason TEXT NOT NULL CHECK (reason = 'RIGHTS_POLICY'),
            disposition TEXT NOT NULL CHECK (disposition = 'requires-review'),
            occurred_at TEXT NOT NULL CHECK ({_timestamp_check("occurred_at")}),
            FOREIGN KEY (rights_revision_id, project_id)
                REFERENCES rights_policy_revisions (revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (source_assertion_revision_id, project_id)
                REFERENCES reconciliation_assertions (revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (path_id, project_id, item_id)
                REFERENCES corpus_discovery_paths (path_id, project_id, item_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (output_revision_id, item_id, project_id)
                REFERENCES corpus_item_states (revision_id, item_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (rights_revision_id, output_revision_id, path_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE rights_policy_recheck_scopes (
            rights_revision_id TEXT PRIMARY KEY CHECK ({_uuid_check("rights_revision_id", "7")}),
            project_id TEXT NOT NULL,
            subject_sha256 TEXT NOT NULL CHECK ({_sha256_check("subject_sha256")}),
            source_assertion_revision_id TEXT NOT NULL CHECK ({_uuid_check("source_assertion_revision_id", "7")}),
            exact_state TEXT NOT NULL CHECK (exact_state IN ('complete', 'pending')),
            generic_state TEXT NOT NULL CHECK (generic_state IN ('complete', 'pending')),
            disposition TEXT NOT NULL CHECK (disposition IN ('complete', 'pending')),
            pending_reason TEXT CHECK (pending_reason IN (
                'exact-limit', 'generic-limit', 'exact-and-generic-limit'
            )),
            reason TEXT NOT NULL CHECK (reason = 'RIGHTS_POLICY'),
            occurred_at TEXT NOT NULL CHECK ({_timestamp_check("occurred_at")}),
            CHECK (
                (exact_state = 'complete' AND generic_state = 'complete'
                    AND disposition = 'complete' AND pending_reason IS NULL)
                OR (exact_state = 'pending' AND generic_state = 'complete'
                    AND disposition = 'pending' AND pending_reason = 'exact-limit')
                OR (exact_state = 'complete' AND generic_state = 'pending'
                    AND disposition = 'pending' AND pending_reason = 'generic-limit')
                OR (exact_state = 'pending' AND generic_state = 'pending'
                    AND disposition = 'pending' AND pending_reason = 'exact-and-generic-limit')
            ),
            FOREIGN KEY (project_id, rights_revision_id, subject_sha256)
                REFERENCES rights_policy_revisions (project_id, revision_id, subject_sha256)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (project_id, subject_sha256)
                REFERENCES rights_policy_subjects (project_id, subject_sha256)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (source_assertion_revision_id, project_id)
                REFERENCES reconciliation_assertions (revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (rights_revision_id, project_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE rights_policy_recheck_completions (
            completion_id TEXT PRIMARY KEY CHECK ({_uuid_check("completion_id", "7")}),
            rights_revision_id TEXT NOT NULL CHECK ({_uuid_check("rights_revision_id", "7")}),
            project_id TEXT NOT NULL,
            dimension TEXT NOT NULL CHECK (dimension IN ('exact', 'generic')),
            actor_id TEXT NOT NULL CHECK ({_uuid_check("actor_id", "7")}),
            occurred_at TEXT NOT NULL CHECK ({_timestamp_check("occurred_at")}),
            FOREIGN KEY (rights_revision_id, project_id)
                REFERENCES rights_policy_recheck_scopes (rights_revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (rights_revision_id, dimension)
        ) STRICT
    """,
    f"""
        CREATE TABLE rights_policy_generic_rechecks (
            recheck_id TEXT PRIMARY KEY CHECK ({_uuid_check("recheck_id", "7")}),
            rights_revision_id TEXT NOT NULL CHECK ({_uuid_check("rights_revision_id", "7")}),
            project_id TEXT NOT NULL,
            previous_revision_id TEXT NOT NULL CHECK ({_uuid_check("previous_revision_id", "7")}),
            parent_revision_id TEXT NOT NULL CHECK ({_uuid_check("parent_revision_id", "7")}),
            output_revision_id TEXT NOT NULL CHECK ({_uuid_check("output_revision_id", "7")}),
            reason TEXT NOT NULL CHECK (reason = 'RIGHTS_POLICY'),
            disposition TEXT NOT NULL CHECK (disposition = 'requires-review'),
            occurred_at TEXT NOT NULL CHECK ({_timestamp_check("occurred_at")}),
            FOREIGN KEY (rights_revision_id, project_id)
                REFERENCES rights_policy_recheck_scopes (rights_revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (previous_revision_id, project_id)
                REFERENCES rights_policy_revisions (revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (parent_revision_id, project_id)
                REFERENCES aggregate_revisions (revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (output_revision_id, project_id)
                REFERENCES aggregate_revisions (revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (rights_revision_id, output_revision_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE rights_legacy_output_rechecks (
            project_id TEXT NOT NULL,
            item_id TEXT NOT NULL CHECK ({_uuid_check("item_id", "7")}),
            path_id TEXT NOT NULL CHECK ({_uuid_check("path_id", "7")}),
            output_revision_id TEXT NOT NULL CHECK ({_uuid_check("output_revision_id", "7")}),
            source_assertion_revision_id TEXT CHECK (
                source_assertion_revision_id IS NULL OR ({_uuid_check("source_assertion_revision_id", "7")})
            ),
            reason TEXT NOT NULL CHECK (reason = 'RIGHTS_POLICY'),
            disposition TEXT NOT NULL CHECK (disposition = 'requires-review'),
            detected_at TEXT NOT NULL CHECK ({_timestamp_check("detected_at")}),
            FOREIGN KEY (output_revision_id, item_id, project_id)
                REFERENCES corpus_item_states (revision_id, item_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (path_id, project_id, item_id)
                REFERENCES corpus_discovery_paths (path_id, project_id, item_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (output_revision_id, path_id)
                REFERENCES corpus_item_discovery_paths (revision_id, path_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (source_assertion_revision_id, project_id)
                REFERENCES reconciliation_assertions (revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            PRIMARY KEY (output_revision_id, path_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE rights_use_decisions (
            decision_id TEXT PRIMARY KEY CHECK ({_uuid_check("decision_id", "7")}),
            event_kind TEXT NOT NULL CHECK (event_kind IN (
                'evaluate', 'denied-attempt', 'legacy-import-bridge'
            )),
            project_id TEXT NOT NULL,
            subject_sha256 TEXT NOT NULL CHECK ({_sha256_check("subject_sha256")}),
            source_assertion_revision_id TEXT NOT NULL CHECK ({_uuid_check("source_assertion_revision_id", "7")}),
            source_assertion_sha256 TEXT NOT NULL CHECK ({_sha256_check("source_assertion_sha256")}),
            authority_kind TEXT NOT NULL CHECK (authority_kind IN (
                'policy', 'legacy-import-bridge', 'none'
            )),
            policy_revision_id TEXT CHECK (
                policy_revision_id IS NULL OR ({_uuid_check("policy_revision_id", "7")})
            ),
            policy_sha256 TEXT CHECK (policy_sha256 IS NULL OR ({_sha256_check("policy_sha256")})),
            actor_id TEXT NOT NULL CHECK ({_uuid_check("actor_id", "7")}),
            trace_id TEXT NOT NULL CHECK (
                length(trace_id) = 32 AND trace_id = lower(trace_id)
                AND trace_id NOT GLOB '*[^0-9a-f]*'
            ),
            use_action TEXT NOT NULL CHECK (use_action IN (
                'store', 'inspect', 'index', 'derive', 'model-use', 'quote', 'export', 'share'
            )),
            use_sha256 TEXT NOT NULL CHECK ({_sha256_check("use_sha256")}),
            decision_code TEXT NOT NULL CHECK (decision_code IN (
                'allow', 'deny', 'unknown', 'require-confirmation'
            )),
            reason_code TEXT NOT NULL CHECK (
                length(reason_code) BETWEEN 1 AND 64
                AND substr(reason_code, 1, 1) GLOB '[a-z]'
                AND reason_code NOT GLOB '*[^a-z0-9-]*'
            ),
            occurred_at TEXT NOT NULL CHECK ({_timestamp_check("occurred_at")}),
            CHECK ((authority_kind = 'policy' AND policy_revision_id IS NOT NULL
                AND policy_sha256 IS NOT NULL)
                OR (authority_kind IN ('legacy-import-bridge', 'none')
                    AND policy_revision_id IS NULL AND policy_sha256 IS NULL)),
            CHECK (decision_code <> 'allow' OR authority_kind IN ('policy', 'legacy-import-bridge')),
            CHECK (event_kind <> 'denied-attempt' OR decision_code <> 'allow'),
            CHECK ((event_kind = 'legacy-import-bridge') = (authority_kind = 'legacy-import-bridge')),
            CHECK (authority_kind <> 'legacy-import-bridge' OR (
                decision_code = 'allow'
                AND reason_code = 'rights-legacy-import-confirmed'
                AND use_action IN ('store', 'inspect', 'derive', 'index')
            )),
            FOREIGN KEY (project_id) REFERENCES projects (project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (source_assertion_revision_id, project_id)
                REFERENCES reconciliation_assertions (revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (policy_revision_id, project_id)
                REFERENCES rights_policy_revisions (revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    "CREATE INDEX rights_policy_revisions_current ON rights_policy_revisions "
    "(project_id, subject_sha256, revision_number DESC)",
    "CREATE INDEX rights_policy_rechecks_output ON rights_policy_rechecks (project_id, output_revision_id)",
    "CREATE INDEX rights_policy_generic_rechecks_output ON rights_policy_generic_rechecks "
    "(project_id, output_revision_id)",
    "CREATE INDEX rights_legacy_output_rechecks_project ON rights_legacy_output_rechecks "
    "(project_id, output_revision_id)",
    *(
        statement
        for table in (
            "rights_policy_subjects",
            "rights_policy_revisions",
            "rights_policy_rechecks",
            "rights_policy_recheck_scopes",
            "rights_policy_recheck_completions",
            "rights_policy_generic_rechecks",
            "rights_legacy_output_rechecks",
            "rights_use_decisions",
        )
        for statement in _immutable_triggers(table, f"{table} history is append-only")
    ),
    """
        CREATE TRIGGER rights_policy_revision_binding BEFORE INSERT ON rights_policy_revisions
        WHEN NOT EXISTS (
            SELECT 1 FROM aggregate_revisions AS r
            WHERE r.revision_id = NEW.revision_id AND r.aggregate_id = NEW.policy_id
              AND r.aggregate_kind = 'decision' AND r.project_id = NEW.project_id
              AND r.revision = NEW.revision_number AND r.rights_status = 'unknown'
        ) OR NOT EXISTS (
            SELECT 1 FROM rights_policy_subjects AS s
            JOIN reconciliation_assertions AS a ON a.revision_id = s.source_assertion_revision_id
              AND a.project_id = s.project_id
            WHERE s.project_id = NEW.project_id AND s.subject_sha256 = NEW.subject_sha256
              AND s.policy_id = NEW.policy_id
              AND json_extract(NEW.policy_json, '$.subject.sourceAssertionRevisionId') IS s.source_assertion_revision_id
              AND json_extract(NEW.policy_json, '$.subject.copyId') IS s.copy_id
              AND json_extract(NEW.policy_json, '$.subject.copyLocation') IS s.copy_location
              AND json_extract(NEW.policy_json, '$.subject.resourceClass') IS s.resource_class
              AND json_type(NEW.policy_json, '$.sourceObservation') = 'object'
              AND json_extract(NEW.policy_json, '$.sourceObservation.projectId') IS s.project_id
              AND json_extract(NEW.policy_json, '$.sourceObservation.sourceAssertionRevisionId') IS a.revision_id
              AND json_extract(NEW.policy_json, '$.sourceObservation.sourceRevisionId') IS a.source_revision_id
              AND json_extract(NEW.policy_json, '$.sourceObservation.sourceSha256')
                  IS json_extract(a.assertion_json, '$.sourceSha256')
              AND json_extract(NEW.policy_json, '$.sourceObservation.provider')
                  IS json_extract(a.assertion_json, '$.provider')
              AND json_extract(NEW.policy_json, '$.subject.address.kind')
                  IS json_extract(a.assertion_json, '$.address.kind')
              AND json_extract(NEW.policy_json, '$.subject.address.contextId')
                  IS json_extract(a.assertion_json, '$.address.contextId')
              AND json_extract(NEW.policy_json, '$.subject.address.revisionId')
                  IS json_extract(a.assertion_json, '$.address.revisionId')
              AND json_extract(NEW.policy_json, '$.subject.address.ordinal')
                  IS json_extract(a.assertion_json, '$.address.ordinal')
              AND json_extract(NEW.policy_json, '$.subject.address.recordKey')
                  IS json_extract(a.assertion_json, '$.address.recordKey')
              AND json_extract(NEW.policy_json, '$.sourceObservation.address.kind')
                  IS json_extract(a.assertion_json, '$.address.kind')
              AND json_extract(NEW.policy_json, '$.sourceObservation.address.contextId')
                  IS json_extract(a.assertion_json, '$.address.contextId')
              AND json_extract(NEW.policy_json, '$.sourceObservation.address.revisionId')
                  IS json_extract(a.assertion_json, '$.address.revisionId')
              AND json_extract(NEW.policy_json, '$.sourceObservation.address.ordinal')
                  IS json_extract(a.assertion_json, '$.address.ordinal')
              AND json_extract(NEW.policy_json, '$.sourceObservation.address.recordKey')
                  IS json_extract(a.assertion_json, '$.address.recordKey')
              AND json_extract(s.subject_json, '$.address.kind')
                  IS json_extract(a.assertion_json, '$.address.kind')
              AND json_extract(s.subject_json, '$.address.contextId')
                  IS json_extract(a.assertion_json, '$.address.contextId')
              AND json_extract(s.subject_json, '$.address.revisionId')
                  IS json_extract(a.assertion_json, '$.address.revisionId')
              AND json_extract(s.subject_json, '$.address.ordinal')
                  IS json_extract(a.assertion_json, '$.address.ordinal')
              AND json_extract(s.subject_json, '$.address.recordKey')
                  IS json_extract(a.assertion_json, '$.address.recordKey')
        ) OR (NEW.revision_number = 0 AND EXISTS (
            SELECT 1 FROM rights_policy_revisions AS prior
            WHERE prior.project_id = NEW.project_id AND prior.subject_sha256 = NEW.subject_sha256
        )) OR (NEW.revision_number > 0 AND NOT EXISTS (
            SELECT 1 FROM rights_policy_revisions AS prior
            WHERE prior.revision_id = NEW.predecessor_revision_id
              AND prior.project_id = NEW.project_id AND prior.subject_sha256 = NEW.subject_sha256
              AND prior.policy_id = NEW.policy_id AND prior.revision_number = NEW.revision_number - 1
              AND prior.revision_number = (
                  SELECT MAX(head.revision_number) FROM rights_policy_revisions AS head
                  WHERE head.project_id = NEW.project_id AND head.subject_sha256 = NEW.subject_sha256
              )
        ))
        BEGIN SELECT RAISE(ABORT, 'rights policy revision binding denied'); END
    """,
    """
        CREATE TRIGGER rights_policy_recheck_binding BEFORE INSERT ON rights_policy_rechecks
        WHEN NOT EXISTS (
            SELECT 1 FROM rights_policy_revisions AS r
            JOIN rights_policy_subjects AS s ON s.project_id = r.project_id
              AND s.subject_sha256 = r.subject_sha256 AND s.policy_id = r.policy_id
            JOIN reconciliation_assertions AS a ON a.revision_id = s.source_assertion_revision_id
              AND a.project_id = s.project_id
            JOIN corpus_discovery_paths AS path ON path.path_id = NEW.path_id
              AND path.project_id = NEW.project_id AND path.item_id = NEW.item_id
            JOIN corpus_item_discovery_paths AS membership
              ON membership.path_id = path.path_id
              AND membership.revision_id = NEW.output_revision_id
              AND membership.project_id = NEW.project_id AND membership.item_id = NEW.item_id
            WHERE r.revision_id = NEW.rights_revision_id AND r.project_id = NEW.project_id
              AND s.source_assertion_revision_id = NEW.source_assertion_revision_id
              AND (
                  (path.kind IN ('import-member', 'connector-record')
                      AND path.source_revision_id = a.source_revision_id
                      AND path.kind = json_extract(a.assertion_json, '$.address.kind')
                      AND path.context_id = json_extract(a.assertion_json, '$.address.contextId')
                      AND path.context_revision_id = json_extract(a.assertion_json, '$.address.revisionId')
                      AND path.ordinal IS json_extract(a.assertion_json, '$.address.ordinal')
                      AND path.record_key_sha256 IS json_extract(a.assertion_json, '$.address.recordKey'))
                  OR (path.kind = 'citation'
                      AND path.source_revision_id = a.revision_id
                      AND path.context_revision_id = path.citing_work_revision_id
                      AND EXISTS (
                          SELECT 1 FROM reconciliation_work_members AS cited_member
                          JOIN reconciliation_work_states AS cited_work
                            ON cited_work.revision_id = cited_member.work_revision_id
                            AND cited_work.project_id = cited_member.project_id
                          WHERE cited_member.assertion_revision_id = a.revision_id
                            AND cited_member.project_id = NEW.project_id
                            AND cited_member.work_revision_id = path.citing_work_revision_id
                            AND cited_work.work_id = path.context_id
                      ))
              )
        )
        BEGIN SELECT RAISE(ABORT, 'rights policy recheck binding denied'); END
    """,
    """
        CREATE TRIGGER rights_policy_recheck_scope_binding
        BEFORE INSERT ON rights_policy_recheck_scopes
        WHEN NOT EXISTS (
            SELECT 1 FROM rights_policy_revisions AS r
            JOIN rights_policy_subjects AS s ON s.project_id = r.project_id
              AND s.subject_sha256 = r.subject_sha256 AND s.policy_id = r.policy_id
            WHERE r.revision_id = NEW.rights_revision_id AND r.project_id = NEW.project_id
              AND r.subject_sha256 = NEW.subject_sha256
              AND s.source_assertion_revision_id = NEW.source_assertion_revision_id
              AND r.revision_number = (
                  SELECT MAX(head.revision_number) FROM rights_policy_revisions AS head
                  WHERE head.project_id = r.project_id AND head.subject_sha256 = r.subject_sha256
              )
        ) OR (NEW.exact_state = 'complete' AND EXISTS (
            SELECT 1 FROM reconciliation_assertions AS a
            JOIN corpus_discovery_paths AS path ON path.project_id = a.project_id
            JOIN corpus_item_discovery_paths AS membership ON membership.path_id = path.path_id
              AND membership.project_id = path.project_id AND membership.item_id = path.item_id
            WHERE a.revision_id = NEW.source_assertion_revision_id AND a.project_id = NEW.project_id
              AND (
                  (path.kind IN ('import-member', 'connector-record')
                      AND path.source_revision_id = a.source_revision_id
                      AND path.kind = json_extract(a.assertion_json, '$.address.kind')
                      AND path.context_id = json_extract(a.assertion_json, '$.address.contextId')
                      AND path.context_revision_id = json_extract(a.assertion_json, '$.address.revisionId')
                      AND path.ordinal IS json_extract(a.assertion_json, '$.address.ordinal')
                      AND path.record_key_sha256 IS json_extract(a.assertion_json, '$.address.recordKey'))
                  OR (path.kind = 'citation'
                      AND path.source_revision_id = a.revision_id
                      AND path.context_revision_id = path.citing_work_revision_id
                      AND EXISTS (
                          SELECT 1 FROM reconciliation_work_members AS cited_member
                          JOIN reconciliation_work_states AS cited_work
                            ON cited_work.revision_id = cited_member.work_revision_id
                            AND cited_work.project_id = cited_member.project_id
                          WHERE cited_member.assertion_revision_id = a.revision_id
                            AND cited_member.project_id = NEW.project_id
                            AND cited_member.work_revision_id = path.citing_work_revision_id
                            AND cited_work.work_id = path.context_id
                      ))
              )
              AND NOT EXISTS (
                  SELECT 1 FROM rights_policy_rechecks AS linked
                  WHERE linked.rights_revision_id = NEW.rights_revision_id
                    AND linked.project_id = NEW.project_id
                    AND linked.output_revision_id = membership.revision_id
                    AND linked.path_id = path.path_id
              )
        )) OR (NEW.generic_state = 'complete' AND EXISTS (
            SELECT 1 FROM rights_policy_revisions AS r
            WHERE r.revision_id = NEW.rights_revision_id AND r.project_id = NEW.project_id
              AND r.predecessor_revision_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM dependency_impact_runs AS run
                  JOIN dependency_impact_audit_events AS audit ON audit.run_id = run.run_id
                    AND audit.project_id = run.project_id
                  WHERE run.project_id = r.project_id
                    AND run.previous_revision_id = r.predecessor_revision_id
                    AND run.replacement_revision_id = r.revision_id
                    AND run.idempotency_key = 'rights-' || r.command_id
                    AND run.reason = 'RIGHTS_POLICY'
                    AND run.dependency_kind = 'human-decision'
                    AND audit.event_type = 'completed'
                    AND audit.processed_items = run.total_items
                    AND audit.sequence = (
                        SELECT MAX(last.sequence) FROM dependency_impact_audit_events AS last
                        WHERE last.run_id = run.run_id AND last.project_id = run.project_id
                    )
              )
        ))
        BEGIN SELECT RAISE(ABORT, 'rights policy recheck scope binding denied'); END
    """,
    """
        CREATE TRIGGER rights_legacy_output_recheck_binding
        BEFORE INSERT ON rights_legacy_output_rechecks
        WHEN NOT EXISTS (
            SELECT 1 FROM corpus_item_discovery_paths AS membership
            JOIN corpus_discovery_paths AS path ON path.path_id = membership.path_id
              AND path.project_id = membership.project_id AND path.item_id = membership.item_id
            WHERE membership.revision_id = NEW.output_revision_id
              AND membership.path_id = NEW.path_id
              AND membership.project_id = NEW.project_id
              AND membership.item_id = NEW.item_id
              AND path.direction = 'source-to-corpus-item'
        ) OR NEW.source_assertion_revision_id IS NOT (
            SELECT CASE WHEN COUNT(*) = 1 THEN MIN(a.revision_id) ELSE NULL END
            FROM corpus_discovery_paths AS path
            JOIN reconciliation_assertions AS a ON a.project_id = path.project_id
              AND (
                  (path.kind IN ('import-member', 'connector-record')
                    AND path.source_revision_id = a.source_revision_id
                    AND path.kind = json_extract(a.assertion_json, '$.address.kind')
                    AND path.context_id = json_extract(a.assertion_json, '$.address.contextId')
                    AND path.context_revision_id = json_extract(a.assertion_json, '$.address.revisionId')
                    AND path.ordinal IS json_extract(a.assertion_json, '$.address.ordinal')
                    AND path.record_key_sha256 IS json_extract(a.assertion_json, '$.address.recordKey'))
                  OR (path.kind = 'citation' AND path.source_revision_id = a.revision_id)
              )
            WHERE path.path_id = NEW.path_id AND path.project_id = NEW.project_id
              AND path.item_id = NEW.item_id
        )
        BEGIN SELECT RAISE(ABORT, 'legacy output recheck binding denied'); END
    """,
    """
        CREATE TRIGGER rights_policy_generic_recheck_binding
        BEFORE INSERT ON rights_policy_generic_rechecks
        WHEN NOT EXISTS (
            SELECT 1 FROM rights_policy_recheck_scopes AS scope
            JOIN rights_policy_revisions AS r ON r.revision_id = scope.rights_revision_id
              AND r.project_id = scope.project_id
            WHERE scope.rights_revision_id = NEW.rights_revision_id
              AND scope.project_id = NEW.project_id
              AND scope.generic_state = 'pending'
              AND r.predecessor_revision_id = NEW.previous_revision_id
              AND (NEW.parent_revision_id = r.predecessor_revision_id OR EXISTS (
                  SELECT 1 FROM rights_policy_generic_rechecks AS parent
                  WHERE parent.rights_revision_id = NEW.rights_revision_id
                    AND parent.project_id = NEW.project_id
                    AND parent.output_revision_id = NEW.parent_revision_id
              ))
              AND EXISTS (
                  SELECT 1 FROM material_dependencies AS d
                  WHERE d.project_id = NEW.project_id
                    AND d.dependency_revision_id = NEW.parent_revision_id
                    AND d.output_revision_id = NEW.output_revision_id
                    AND d.relation_type IN ('direct', 'conditional')
              )
        )
        BEGIN SELECT RAISE(ABORT, 'rights policy generic recheck binding denied'); END
    """,
    """
        CREATE TRIGGER rights_policy_recheck_completion_binding
        BEFORE INSERT ON rights_policy_recheck_completions
        WHEN NOT EXISTS (
            SELECT 1 FROM rights_policy_recheck_scopes AS scope
            WHERE scope.rights_revision_id = NEW.rights_revision_id
              AND scope.project_id = NEW.project_id
              AND ((NEW.dimension = 'exact' AND scope.exact_state = 'pending')
                OR (NEW.dimension = 'generic' AND scope.generic_state = 'pending'))
        ) OR (NEW.dimension = 'exact' AND EXISTS (
            SELECT 1 FROM rights_policy_recheck_scopes AS scope
            JOIN reconciliation_assertions AS a ON a.revision_id = scope.source_assertion_revision_id
              AND a.project_id = scope.project_id
            JOIN corpus_discovery_paths AS path ON path.project_id = a.project_id
            JOIN corpus_item_discovery_paths AS membership ON membership.path_id = path.path_id
              AND membership.project_id = path.project_id AND membership.item_id = path.item_id
            WHERE scope.rights_revision_id = NEW.rights_revision_id
              AND scope.project_id = NEW.project_id
              AND (
                  (path.kind IN ('import-member', 'connector-record')
                      AND path.source_revision_id = a.source_revision_id
                      AND path.kind = json_extract(a.assertion_json, '$.address.kind')
                      AND path.context_id = json_extract(a.assertion_json, '$.address.contextId')
                      AND path.context_revision_id = json_extract(a.assertion_json, '$.address.revisionId')
                      AND path.ordinal IS json_extract(a.assertion_json, '$.address.ordinal')
                      AND path.record_key_sha256 IS json_extract(a.assertion_json, '$.address.recordKey'))
                  OR (path.kind = 'citation'
                      AND path.source_revision_id = a.revision_id
                      AND path.context_revision_id = path.citing_work_revision_id
                      AND EXISTS (
                          SELECT 1 FROM reconciliation_work_members AS cited_member
                          JOIN reconciliation_work_states AS cited_work
                            ON cited_work.revision_id = cited_member.work_revision_id
                            AND cited_work.project_id = cited_member.project_id
                          WHERE cited_member.assertion_revision_id = a.revision_id
                            AND cited_member.project_id = NEW.project_id
                            AND cited_member.work_revision_id = path.citing_work_revision_id
                            AND cited_work.work_id = path.context_id
                      ))
              )
              AND NOT EXISTS (
                  SELECT 1 FROM rights_policy_rechecks AS linked
                  WHERE linked.rights_revision_id = NEW.rights_revision_id
                    AND linked.project_id = NEW.project_id
                    AND linked.output_revision_id = membership.revision_id
                    AND linked.path_id = path.path_id
              )
        )) OR (NEW.dimension = 'generic' AND NOT EXISTS (
            SELECT 1 FROM rights_policy_revisions AS r
            WHERE r.revision_id = NEW.rights_revision_id AND r.project_id = NEW.project_id
              AND r.predecessor_revision_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM (
                      SELECT predecessor_revision_id AS revision_id
                      FROM rights_policy_revisions
                      WHERE revision_id = NEW.rights_revision_id AND project_id = NEW.project_id
                      UNION
                      SELECT parent.output_revision_id FROM rights_policy_generic_rechecks AS parent
                      WHERE parent.rights_revision_id = NEW.rights_revision_id
                        AND parent.project_id = NEW.project_id
                  ) AS parents
                  CROSS JOIN material_dependencies AS d
                  WHERE d.project_id = r.project_id
                    AND d.dependency_revision_id = parents.revision_id
                    AND d.relation_type IN ('direct', 'conditional')
                    AND NOT EXISTS (
                        SELECT 1 FROM rights_policy_generic_rechecks AS linked
                        WHERE linked.rights_revision_id = NEW.rights_revision_id
                          AND linked.project_id = NEW.project_id
                          AND linked.previous_revision_id = r.predecessor_revision_id
                          AND linked.output_revision_id = d.output_revision_id
                    )
              )
        ))
        BEGIN SELECT RAISE(ABORT, 'rights policy recheck completion binding denied'); END
    """,
    """
        CREATE TRIGGER rights_use_decision_binding BEFORE INSERT ON rights_use_decisions
        WHEN NOT EXISTS (
            SELECT 1 FROM reconciliation_assertions AS a
            WHERE a.revision_id = NEW.source_assertion_revision_id AND a.project_id = NEW.project_id
              AND a.payload_sha256 = NEW.source_assertion_sha256
        ) OR (NEW.authority_kind = 'policy' AND NOT EXISTS (
            SELECT 1 FROM rights_policy_revisions AS r
            JOIN rights_policy_subjects AS s ON s.project_id = r.project_id
              AND s.subject_sha256 = r.subject_sha256 AND s.policy_id = r.policy_id
            WHERE r.revision_id = NEW.policy_revision_id AND r.project_id = NEW.project_id
              AND r.subject_sha256 = NEW.subject_sha256
              AND r.policy_sha256 = NEW.policy_sha256
              AND s.source_assertion_revision_id = NEW.source_assertion_revision_id
        )) OR (NEW.authority_kind = 'legacy-import-bridge' AND NOT EXISTS (
            SELECT 1 FROM reconciliation_assertions AS a
            WHERE a.revision_id = NEW.source_assertion_revision_id AND a.project_id = NEW.project_id
              AND json_extract(a.assertion_json, '$.address.kind') = 'import-member'
              AND json_extract(a.assertion_json, '$.provider') = 'local-import'
              AND json_extract(a.assertion_json, '$.rights."' || NEW.use_action || '".value') = 'permitted'
              AND json_extract(a.assertion_json, '$.rights."' || NEW.use_action || '".basis')
                  = 'researcher-confirmed'
        ))
        BEGIN SELECT RAISE(ABORT, 'rights use decision binding denied'); END
    """,
)


CORPUS_REPORT_DDL = (
    f"""
        CREATE TABLE corpus_report_snapshots (
            snapshot_id TEXT PRIMARY KEY CHECK ({_uuid_check("snapshot_id", "7")}),
            project_id TEXT NOT NULL,
            command_id TEXT NOT NULL CHECK ({_uuid_check("command_id", "7")}),
            command_sha256 TEXT NOT NULL CHECK ({_sha256_check("command_sha256")}),
            actor_id TEXT NOT NULL CHECK ({_uuid_check("actor_id", "7")}),
            trace_id TEXT NOT NULL CHECK (length(trace_id)=32 AND trace_id=lower(trace_id)
                AND trace_id NOT GLOB '*[^0-9a-f]*'),
            intent_revision_id TEXT NOT NULL CHECK ({_uuid_check("intent_revision_id", "7")}),
            intent_sha256 TEXT NOT NULL CHECK ({_sha256_check("intent_sha256")}),
            privacy_sha256 TEXT NOT NULL CHECK ({_sha256_check("privacy_sha256")}),
            protocol_revision_id TEXT NOT NULL CHECK ({_uuid_check("protocol_revision_id", "7")}),
            rule_version TEXT NOT NULL CHECK (rule_version='corpus-report/1.0.0'),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            member_count INTEGER NOT NULL CHECK (member_count BETWEEN 0 AND 100000),
            path_count INTEGER NOT NULL CHECK (path_count BETWEEN 0 AND 100000000),
            source_count INTEGER NOT NULL CHECK (source_count BETWEEN 0 AND 100000),
            members_sha256 TEXT NOT NULL CHECK ({_sha256_check("members_sha256")}),
            summary_json TEXT NOT NULL CHECK (json_valid(summary_json)
                AND length(CAST(summary_json AS BLOB)) BETWEEN 2 AND 8388608
                AND json_type(summary_json)='object'
                AND json_extract(summary_json,'$.snapshotId') IS snapshot_id
                AND json_extract(summary_json,'$.projectId') IS project_id
                AND json_extract(summary_json,'$.intentRevisionId') IS intent_revision_id
                AND json_extract(summary_json,'$.protocolRevisionId') IS protocol_revision_id
                AND json_extract(summary_json,'$.memberCount') IS member_count
                AND json_extract(summary_json,'$.discoveryPathCount') IS path_count
                AND json_extract(summary_json,'$.membersSha256') IS members_sha256),
            summary_sha256 TEXT NOT NULL CHECK ({_sha256_check("summary_sha256")}),
            provenance_event_id TEXT NOT NULL CHECK ({_uuid_check("provenance_event_id", "7")}),
            outbox_id TEXT NOT NULL CHECK ({_uuid_check("outbox_id", "7")}),
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (provenance_event_id) REFERENCES provenance_events (event_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (outbox_id) REFERENCES outbox_events (outbox_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (snapshot_id, project_id),
            UNIQUE (project_id, command_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE corpus_report_members (
            snapshot_id TEXT NOT NULL CHECK ({_uuid_check("snapshot_id", "7")}),
            project_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL CHECK (ordinal BETWEEN 1 AND 100000),
            item_id TEXT NOT NULL CHECK ({_uuid_check("item_id", "7")}),
            item_revision_id TEXT NOT NULL CHECK ({_uuid_check("item_revision_id", "7")}),
            work_id TEXT NOT NULL CHECK ({_uuid_check("work_id", "7")}),
            work_revision_id TEXT NOT NULL CHECK ({_uuid_check("work_revision_id", "7")}),
            member_json TEXT NOT NULL CHECK (json_valid(member_json)
                AND length(CAST(member_json AS BLOB)) BETWEEN 2 AND 262144
                AND json_type(member_json)='object'
                AND json_extract(member_json,'$.snapshotId') IS snapshot_id
                AND json_extract(member_json,'$.projectId') IS project_id
                AND json_extract(member_json,'$.itemId') IS item_id
                AND json_extract(member_json,'$.itemRevisionId') IS item_revision_id
                AND json_extract(member_json,'$.workId') IS work_id
                AND json_extract(member_json,'$.workRevisionId') IS work_revision_id
                AND json_array_length(member_json,'$.paths') BETWEEN 1 AND 1000
                AND json_array_length(member_json,'$.fields')=7),
            member_sha256 TEXT NOT NULL CHECK ({_sha256_check("member_sha256")}),
            FOREIGN KEY (snapshot_id, project_id)
                REFERENCES corpus_report_snapshots (snapshot_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            FOREIGN KEY (item_revision_id, item_id, project_id)
                REFERENCES corpus_item_states (revision_id, item_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (work_revision_id, project_id, work_id)
                REFERENCES reconciliation_work_states (revision_id, project_id, work_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            PRIMARY KEY (snapshot_id, ordinal),
            UNIQUE (snapshot_id, item_id),
            UNIQUE (snapshot_id, item_revision_id),
            UNIQUE (snapshot_id, project_id, item_id, item_revision_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE corpus_report_sources (
            snapshot_id TEXT NOT NULL CHECK ({_uuid_check("snapshot_id", "7")}),
            project_id TEXT NOT NULL,
            source_assertion_revision_id TEXT NOT NULL CHECK (
                {_uuid_check("source_assertion_revision_id", "7")}),
            source_assertion_sha256 TEXT NOT NULL CHECK ({_sha256_check("source_assertion_sha256")}),
            subject_sha256 TEXT NOT NULL CHECK ({_sha256_check("subject_sha256")}),
            policy_revision_id TEXT NOT NULL CHECK ({_uuid_check("policy_revision_id", "7")}),
            policy_sha256 TEXT NOT NULL CHECK ({_sha256_check("policy_sha256")}),
            expires_at TEXT CHECK (expires_at IS NULL OR ({_timestamp_check("expires_at")})),
            FOREIGN KEY (snapshot_id, project_id)
                REFERENCES corpus_report_snapshots (snapshot_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            FOREIGN KEY (source_assertion_revision_id, project_id)
                REFERENCES reconciliation_assertions (revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (project_id, policy_revision_id, subject_sha256)
                REFERENCES rights_policy_revisions (project_id, revision_id, subject_sha256)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            PRIMARY KEY (snapshot_id, source_assertion_revision_id),
            UNIQUE (snapshot_id, project_id, source_assertion_revision_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE corpus_report_paths (
            snapshot_id TEXT NOT NULL CHECK ({_uuid_check("snapshot_id", "7")}),
            project_id TEXT NOT NULL,
            item_id TEXT NOT NULL CHECK ({_uuid_check("item_id", "7")}),
            item_revision_id TEXT NOT NULL CHECK ({_uuid_check("item_revision_id", "7")}),
            path_id TEXT NOT NULL CHECK ({_uuid_check("path_id", "7")}),
            source_assertion_revision_id TEXT CHECK (source_assertion_revision_id IS NULL OR (
                {_uuid_check("source_assertion_revision_id", "7")})),
            source_revision_id TEXT NOT NULL CHECK ({_uuid_check("source_revision_id", "7")}),
            source_key TEXT CHECK (source_key IS NULL OR length(source_key) BETWEEN 1 AND 90),
            route TEXT NOT NULL CHECK (route IN (
                'import-member','connector-record','citation','recommendation','manual')),
            FOREIGN KEY (snapshot_id, project_id, item_id, item_revision_id)
                REFERENCES corpus_report_members (snapshot_id, project_id, item_id, item_revision_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (item_revision_id, path_id)
                REFERENCES corpus_item_discovery_paths (revision_id, path_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (snapshot_id, project_id, source_assertion_revision_id)
                REFERENCES corpus_report_sources (snapshot_id, project_id, source_assertion_revision_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            PRIMARY KEY (snapshot_id, item_revision_id, path_id)
        ) STRICT
    """,
    *(
        statement
        for table in CORPUS_REPORT_TABLES
        for statement in _immutable_triggers(table, "corpus report history is append-only")
    ),
    "CREATE INDEX corpus_report_member_item ON corpus_report_members (snapshot_id,item_id)",
    "CREATE INDEX corpus_report_path_source ON corpus_report_paths (snapshot_id,source_key,item_id)",
    "CREATE INDEX corpus_report_source_policy ON corpus_report_sources (project_id,subject_sha256,policy_revision_id)",
    """
        CREATE TRIGGER corpus_report_member_binding BEFORE INSERT ON corpus_report_members
        WHEN EXISTS (SELECT 1 FROM corpus_report_snapshots WHERE snapshot_id=NEW.snapshot_id)
            OR NOT EXISTS (SELECT 1 FROM aggregate_revisions r
                JOIN corpus_item_states s ON s.revision_id=r.revision_id AND s.project_id=r.project_id
                WHERE r.project_id=NEW.project_id AND r.aggregate_id=NEW.item_id
                  AND r.revision_id=NEW.item_revision_id AND r.aggregate_kind='corpus-item'
                  AND s.work_id=NEW.work_id AND s.work_revision_id=NEW.work_revision_id
                  AND s.membership=json_extract(NEW.member_json,'$.membership')
                  AND s.duplicate_of_item_id IS json_extract(NEW.member_json,'$.duplicateOfItemId')
                  AND r.revision=(SELECT MAX(x.revision) FROM aggregate_revisions x
                    WHERE x.project_id=r.project_id AND x.aggregate_id=r.aggregate_id))
        BEGIN SELECT RAISE(ABORT,'corpus report member binding denied'); END
    """,
    """
        CREATE TRIGGER corpus_report_source_binding BEFORE INSERT ON corpus_report_sources
        WHEN EXISTS (SELECT 1 FROM corpus_report_snapshots WHERE snapshot_id=NEW.snapshot_id)
            OR NOT EXISTS (SELECT 1 FROM reconciliation_assertions a
                JOIN rights_policy_revisions r ON r.revision_id=NEW.policy_revision_id
                    AND r.project_id=a.project_id AND r.subject_sha256=NEW.subject_sha256
                JOIN rights_policy_subjects s ON s.project_id=r.project_id
                    AND s.subject_sha256=r.subject_sha256
                WHERE a.project_id=NEW.project_id AND a.revision_id=NEW.source_assertion_revision_id
                    AND a.payload_sha256=NEW.source_assertion_sha256
                    AND r.policy_sha256=NEW.policy_sha256
                    AND s.source_assertion_revision_id=a.revision_id
                    AND s.copy_id=a.revision_id AND s.copy_location='local-source'
                    AND s.resource_class='metadata')
        BEGIN SELECT RAISE(ABORT,'corpus report source binding denied'); END
    """,
    """
        CREATE TRIGGER corpus_report_path_binding BEFORE INSERT ON corpus_report_paths
        WHEN EXISTS (SELECT 1 FROM corpus_report_snapshots WHERE snapshot_id=NEW.snapshot_id)
            OR NOT EXISTS (SELECT 1 FROM corpus_discovery_paths p
                JOIN corpus_item_discovery_paths m ON m.path_id=p.path_id
                    AND m.revision_id=NEW.item_revision_id
                LEFT JOIN reconciliation_assertions a ON a.revision_id=NEW.source_assertion_revision_id
                    AND a.project_id=p.project_id
                WHERE p.project_id=NEW.project_id AND p.item_id=NEW.item_id
                    AND p.path_id=NEW.path_id AND p.source_revision_id=NEW.source_revision_id
                    AND p.kind=NEW.route
                    AND ((p.kind IN ('import-member','connector-record')
                        AND a.source_revision_id=p.source_revision_id
                        AND json_extract(a.assertion_json,'$.address.kind')=p.kind
                        AND json_extract(a.assertion_json,'$.address.revisionId')=p.context_revision_id
                        AND json_extract(a.assertion_json,'$.address.contextId')=p.context_id
                        AND json_extract(a.assertion_json,'$.address.ordinal') IS p.ordinal
                        AND json_extract(a.assertion_json,'$.address.recordKey') IS p.record_key_sha256)
                        OR (p.kind='citation' AND a.revision_id=p.source_revision_id)
                        OR (p.kind IN ('recommendation','manual')
                            AND NEW.source_assertion_revision_id IS NULL AND NEW.source_key IS NULL)))
        BEGIN SELECT RAISE(ABORT,'corpus report path binding denied'); END
    """,
    """
        CREATE TRIGGER corpus_report_snapshot_seal_binding BEFORE INSERT ON corpus_report_snapshots
        WHEN NEW.member_count<>(SELECT COUNT(*) FROM corpus_report_members WHERE snapshot_id=NEW.snapshot_id)
            OR NEW.path_count<>(SELECT COUNT(*) FROM corpus_report_paths WHERE snapshot_id=NEW.snapshot_id)
            OR NEW.source_count<>(SELECT COUNT(*) FROM corpus_report_sources WHERE snapshot_id=NEW.snapshot_id)
            OR (NEW.member_count>0 AND NEW.member_count<>(SELECT MAX(ordinal) FROM corpus_report_members
                WHERE snapshot_id=NEW.snapshot_id))
            OR EXISTS (SELECT 1 FROM corpus_report_members m WHERE m.snapshot_id=NEW.snapshot_id
                AND json_array_length(m.member_json,'$.paths')<>
                    (SELECT COUNT(*) FROM corpus_report_paths p WHERE p.snapshot_id=m.snapshot_id
                        AND p.item_revision_id=m.item_revision_id))
            OR NOT EXISTS (SELECT 1 FROM provenance_events p JOIN outbox_events o
                ON o.outbox_id=NEW.outbox_id AND o.project_id=p.project_id
                WHERE p.event_id=NEW.provenance_event_id AND p.project_id=NEW.project_id
                    AND p.revision_id IS NULL AND o.revision_id IS NULL
                    AND p.event_type='corpus.report-created' AND o.event_type=p.event_type
                    AND p.record_sha256=NEW.summary_sha256 AND o.record_sha256=p.record_sha256
                    AND p.actor_id=NEW.actor_id AND p.trace_id=NEW.trace_id
                    AND o.idempotency_key='corpus-report-' || NEW.command_id)
        BEGIN SELECT RAISE(ABORT,'corpus report seal binding denied'); END
    """,
)


CORPUS_SOURCE_PROJECTION_DDL = (
    f"""
        CREATE TABLE corpus_source_item_heads (
            project_id TEXT NOT NULL,
            item_id TEXT NOT NULL CHECK ({_uuid_check("item_id", "7")}),
            revision_id TEXT NOT NULL CHECK ({_uuid_check("revision_id", "7")}),
            work_revision_id TEXT NOT NULL CHECK ({_uuid_check("work_revision_id", "7")}),
            included_in_report INTEGER NOT NULL CHECK (included_in_report IN (0,1)),
            source_counts_json TEXT NOT NULL CHECK (json_valid(source_counts_json)
                AND json_type(source_counts_json)='object'
                AND length(CAST(source_counts_json AS BLOB)) BETWEEN 2 AND 8388608),
            PRIMARY KEY (project_id,item_id),
            FOREIGN KEY (revision_id,item_id,project_id)
                REFERENCES corpus_item_states (revision_id,item_id,project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (work_revision_id,project_id)
                REFERENCES reconciliation_work_states (revision_id,project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    """
        CREATE TABLE corpus_source_totals (
            project_id TEXT NOT NULL,
            source_key TEXT NOT NULL CHECK (length(source_key) BETWEEN 1 AND 512),
            item_count INTEGER NOT NULL CHECK (item_count > 0),
            discovery_path_count INTEGER NOT NULL CHECK (discovery_path_count >= item_count),
            PRIMARY KEY (project_id,source_key),
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    """
        CREATE TABLE corpus_source_overlap_totals (
            project_id TEXT NOT NULL,
            left_source_key TEXT NOT NULL CHECK (length(left_source_key) BETWEEN 1 AND 512),
            right_source_key TEXT NOT NULL CHECK (length(right_source_key) BETWEEN 1 AND 512),
            item_count INTEGER NOT NULL CHECK (item_count > 0),
            discovery_path_pair_count INTEGER NOT NULL CHECK (discovery_path_pair_count >= item_count),
            PRIMARY KEY (project_id,left_source_key,right_source_key),
            CHECK (left_source_key < right_source_key),
            FOREIGN KEY (project_id,left_source_key) REFERENCES corpus_source_totals (project_id,source_key)
                ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
            FOREIGN KEY (project_id,right_source_key) REFERENCES corpus_source_totals (project_id,source_key)
                ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
        ) STRICT
    """,
    "CREATE INDEX corpus_item_states_membership ON corpus_item_states (project_id,membership,item_id,revision_id)",
    "CREATE INDEX corpus_decisions_reason ON corpus_decisions (project_id,reason_code,item_id,next_revision_id)",
    "CREATE INDEX rights_use_decisions_action ON rights_use_decisions (project_id,use_action,occurred_at,decision_id)",
    "CREATE INDEX corpus_discovery_paths_source ON corpus_discovery_paths "
    "(project_id,source_revision_id,item_id,path_id)",
    "CREATE INDEX corpus_discovery_paths_search_run ON corpus_discovery_paths "
    "(project_id,query_revision_id,item_id,path_id) WHERE query_revision_id IS NOT NULL",
    "CREATE INDEX corpus_report_snapshots_project_time ON corpus_report_snapshots (project_id,created_at,snapshot_id)",
)


PLUGIN_GRANT_DDL = (
    f"""
        CREATE TABLE plugin_grant_events (
            audit_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL UNIQUE CHECK ({_uuid_check("event_id", "7")}),
            project_id TEXT NOT NULL,
            plugin_id TEXT NOT NULL CHECK (
                length(plugin_id) BETWEEN 1 AND 121
                AND plugin_id = lower(plugin_id)
                AND substr(plugin_id,1,1) GLOB '[a-z]'
                AND plugin_id NOT GLOB '*[^a-z0-9.-]*'
            ),
            event_kind TEXT NOT NULL CHECK (event_kind IN ('enabled','revoked','denied')),
            reason_code TEXT NOT NULL CHECK (
                length(reason_code) BETWEEN 1 AND 64
                AND substr(reason_code,1,1) GLOB '[a-z]'
                AND reason_code NOT GLOB '*[^a-z0-9-]*'
            ),
            revision INTEGER CHECK (revision IS NULL OR revision BETWEEN 1 AND {MAX_SAFE_INTEGER}),
            predecessor_event_id TEXT,
            action_id TEXT CHECK (action_id IS NULL OR ({_uuid_check("action_id", "7")})),
            action_sha256 TEXT CHECK (action_sha256 IS NULL OR ({_sha256_check("action_sha256")})),
            publisher_key_id TEXT CHECK (publisher_key_id IS NULL OR length(publisher_key_id) BETWEEN 1 AND 128),
            package_sha256 TEXT CHECK (package_sha256 IS NULL OR (
                length(package_sha256)=71 AND substr(package_sha256,1,7)='sha256:'
                AND substr(package_sha256,8) NOT GLOB '*[^0-9a-f]*'
            )),
            manifest_sha256 TEXT CHECK (manifest_sha256 IS NULL OR (
                length(manifest_sha256)=71 AND substr(manifest_sha256,1,7)='sha256:'
                AND substr(manifest_sha256,8) NOT GLOB '*[^0-9a-f]*'
            )),
            trusted_key_sha256 TEXT CHECK (trusted_key_sha256 IS NULL OR (
                length(trusted_key_sha256)=71 AND substr(trusted_key_sha256,1,7)='sha256:'
                AND substr(trusted_key_sha256,8) NOT GLOB '*[^0-9a-f]*'
            )),
            trusted_key_revision INTEGER CHECK (
                trusted_key_revision IS NULL OR trusted_key_revision BETWEEN 1 AND {MAX_SAFE_INTEGER}
            ),
            review_json TEXT CHECK (review_json IS NULL OR (
                json_valid(review_json) AND json_type(review_json)='object'
                AND json_type(review_json,'$.operations')='array'
                AND json_type(review_json,'$.dataClasses')='array'
                AND json_type(review_json,'$.credentialScopes')='array'
                AND length(CAST(review_json AS BLOB)) BETWEEN 2 AND 16384
            )),
            grant_json TEXT CHECK (grant_json IS NULL OR (
                json_valid(grant_json) AND json_type(grant_json)='object'
                AND length(CAST(grant_json AS BLOB)) BETWEEN 2 AND 16384
            )),
            invocation_id TEXT CHECK (invocation_id IS NULL OR ({_uuid_check("invocation_id", "7")})),
            record_sha256 TEXT NOT NULL CHECK ({_sha256_check("record_sha256")}),
            provenance_event_id TEXT NOT NULL UNIQUE CHECK ({_uuid_check("provenance_event_id", "7")}),
            outbox_id TEXT UNIQUE CHECK (outbox_id IS NULL OR ({_uuid_check("outbox_id", "7")})),
            actor_id TEXT NOT NULL CHECK ({_uuid_check("actor_id", "7")}),
            trace_id TEXT NOT NULL CHECK (length(trace_id)=32 AND trace_id=lower(trace_id)
                AND trace_id NOT GLOB '*[^0-9a-f]*'),
            occurred_at TEXT NOT NULL CHECK ({_timestamp_check("occurred_at")}),
            CHECK (
                (event_kind='enabled' AND revision IS NOT NULL AND action_id IS NOT NULL
                    AND action_sha256 IS NOT NULL AND publisher_key_id IS NOT NULL
                    AND package_sha256 IS NOT NULL AND manifest_sha256 IS NOT NULL
                    AND trusted_key_sha256 IS NOT NULL AND trusted_key_revision IS NOT NULL
                    AND review_json IS NOT NULL AND grant_json IS NOT NULL
                    AND outbox_id IS NOT NULL AND invocation_id IS NULL)
                OR (event_kind='revoked' AND revision IS NOT NULL AND action_id IS NOT NULL
                    AND action_sha256 IS NOT NULL AND publisher_key_id IS NOT NULL
                    AND package_sha256 IS NOT NULL AND grant_json IS NULL
                    AND trusted_key_sha256 IS NULL AND trusted_key_revision IS NULL
                    AND review_json IS NULL
                    AND outbox_id IS NOT NULL AND invocation_id IS NULL)
                OR (event_kind='denied' AND revision IS NULL AND predecessor_event_id IS NULL
                    AND action_id IS NULL AND action_sha256 IS NULL AND grant_json IS NULL
                    AND trusted_key_sha256 IS NULL AND trusted_key_revision IS NULL
                    AND review_json IS NULL
                    AND outbox_id IS NULL)
            ),
            FOREIGN KEY (project_id) REFERENCES projects(project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (predecessor_event_id) REFERENCES plugin_grant_events(event_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (provenance_event_id) REFERENCES provenance_events(event_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (outbox_id) REFERENCES outbox_events(outbox_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (project_id,plugin_id,revision),
            UNIQUE (project_id,action_id)
        ) STRICT
    """,
    *_immutable_triggers("plugin_grant_events", "plugin grant and denial history is append-only"),
    "CREATE INDEX plugin_grant_events_current ON plugin_grant_events(project_id,plugin_id,revision DESC)",
    """
        CREATE TRIGGER plugin_grant_revision_binding BEFORE INSERT ON plugin_grant_events
        WHEN NEW.revision IS NOT NULL AND (
            (NEW.revision=1 AND (
                NEW.event_kind<>'enabled' OR NEW.predecessor_event_id IS NOT NULL
                OR EXISTS (SELECT 1 FROM plugin_grant_events prior
                    WHERE prior.project_id=NEW.project_id AND prior.plugin_id=NEW.plugin_id
                    AND prior.revision IS NOT NULL)
            )) OR (NEW.revision>1 AND NOT EXISTS (
                SELECT 1 FROM plugin_grant_events prior
                WHERE prior.project_id=NEW.project_id AND prior.plugin_id=NEW.plugin_id
                    AND prior.revision=NEW.revision-1
                    AND prior.event_id=NEW.predecessor_event_id
                    AND prior.publisher_key_id=NEW.publisher_key_id
                    AND (NEW.event_kind<>'revoked' OR prior.event_kind='enabled')
                    AND NOT EXISTS (SELECT 1 FROM plugin_grant_events later
                        WHERE later.project_id=NEW.project_id AND later.plugin_id=NEW.plugin_id
                        AND later.revision>=NEW.revision)
            ))
        ) BEGIN SELECT RAISE(ABORT,'plugin grant revision binding denied'); END
    """,
    """
        CREATE TRIGGER plugin_grant_event_binding BEFORE INSERT ON plugin_grant_events
        WHEN NOT EXISTS (
            SELECT 1 FROM provenance_events p WHERE p.event_id=NEW.provenance_event_id
                AND p.project_id=NEW.project_id AND p.revision_id IS NULL
                AND p.event_type='connector.plugin-' || NEW.event_kind
                AND p.record_sha256=NEW.record_sha256
                AND p.actor_id=NEW.actor_id
                AND p.actor_type IN ('human','system')
                AND (NEW.event_kind='denied' OR p.actor_type='human')
                AND p.trace_id=NEW.trace_id AND p.occurred_at=NEW.occurred_at
        ) OR (NEW.outbox_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM outbox_events o WHERE o.outbox_id=NEW.outbox_id
                AND o.project_id=NEW.project_id AND o.revision_id IS NULL
                AND o.event_type='connector.plugin-' || NEW.event_kind
                AND o.record_sha256=NEW.record_sha256
                AND o.idempotency_key='plugin-grant-' || NEW.action_id
        )) OR (NEW.event_kind='enabled' AND (
            json_extract(NEW.grant_json,'$.projectId') IS NOT NEW.project_id
            OR json_extract(NEW.grant_json,'$.pluginId') IS NOT NEW.plugin_id
            OR json_extract(NEW.grant_json,'$.revision') IS NOT NEW.revision
            OR json_extract(NEW.grant_json,'$.publisherKeyId') IS NOT NEW.publisher_key_id
            OR json_extract(NEW.grant_json,'$.packageSha256') IS NOT NEW.package_sha256
            OR json_extract(NEW.grant_json,'$.manifestSha256') IS NOT NEW.manifest_sha256
        ))
        BEGIN SELECT RAISE(ABORT,'plugin grant audit binding denied'); END
    """,
)


DOCUMENT_ATTACHMENT_DDL = (
    f"""
        CREATE TABLE document_attachment_candidates (
            candidate_id TEXT PRIMARY KEY CHECK ({_uuid_check("candidate_id", "7")}),
            project_id TEXT NOT NULL,
            source_assertion_revision_id TEXT NOT NULL CHECK ({_uuid_check("source_assertion_revision_id", "7")}),
            work_id TEXT NOT NULL CHECK ({_uuid_check("work_id", "7")}),
            work_revision_id TEXT NOT NULL CHECK ({_uuid_check("work_revision_id", "7")}),
            version_id TEXT NOT NULL CHECK ({_uuid_check("version_id", "7")}),
            version_revision_id TEXT NOT NULL CHECK ({_uuid_check("version_revision_id", "7")}),
            object_sha256 TEXT NOT NULL CHECK ({_sha256_check("object_sha256")}),
            byte_length INTEGER NOT NULL CHECK (byte_length BETWEEN 1 AND 134217728),
            format_name TEXT NOT NULL CHECK (format_name IN ('pdf','jats','tei','xml','html','docx','plain-text')),
            media_type TEXT NOT NULL CHECK (length(media_type) BETWEEN 3 AND 200),
            source_name TEXT NOT NULL CHECK (length(source_name) BETWEEN 1 AND 255),
            confirmation_required INTEGER NOT NULL CHECK (confirmation_required IN (0,1)),
            candidate_sha256 TEXT NOT NULL CHECK ({_sha256_check("candidate_sha256")}),
            actor_id TEXT NOT NULL CHECK ({_uuid_check("actor_id", "7")}),
            trace_id TEXT NOT NULL CHECK (length(trace_id)=32 AND trace_id=lower(trace_id)
                AND trace_id NOT GLOB '*[^0-9a-f]*'),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            FOREIGN KEY (project_id) REFERENCES projects(project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (source_assertion_revision_id,project_id) REFERENCES reconciliation_assertions
                (revision_id,project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (work_revision_id,project_id,work_id) REFERENCES reconciliation_work_states
                (revision_id,project_id,work_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (version_revision_id,project_id,version_id) REFERENCES reconciliation_versions
                (revision_id,project_id,version_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (object_sha256,project_id) REFERENCES object_records
                (object_sha256,project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (candidate_id,project_id),
            UNIQUE (candidate_id,project_id,source_assertion_revision_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE document_attachment_cancellations (
            candidate_id TEXT PRIMARY KEY CHECK ({_uuid_check("candidate_id", "7")}),
            project_id TEXT NOT NULL,
            actor_id TEXT NOT NULL CHECK ({_uuid_check("actor_id", "7")}),
            trace_id TEXT NOT NULL CHECK (length(trace_id)=32 AND trace_id=lower(trace_id)
                AND trace_id NOT GLOB '*[^0-9a-f]*'),
            cancelled_at TEXT NOT NULL CHECK ({_timestamp_check("cancelled_at")}),
            FOREIGN KEY (candidate_id,project_id) REFERENCES document_attachment_candidates
                (candidate_id,project_id) ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    f"""
        CREATE TABLE document_attachment_assertions (
            attachment_id TEXT PRIMARY KEY CHECK ({_uuid_check("attachment_id", "7")}),
            project_id TEXT NOT NULL,
            candidate_id TEXT NOT NULL UNIQUE CHECK ({_uuid_check("candidate_id", "7")}),
            source_assertion_revision_id TEXT NOT NULL CHECK ({_uuid_check("source_assertion_revision_id", "7")}),
            document_id TEXT NOT NULL CHECK ({_uuid_check("document_id", "7")}),
            document_revision_id TEXT NOT NULL UNIQUE CHECK ({_uuid_check("document_revision_id", "7")}),
            work_id TEXT NOT NULL CHECK ({_uuid_check("work_id", "7")}),
            work_revision_id TEXT NOT NULL CHECK ({_uuid_check("work_revision_id", "7")}),
            version_id TEXT NOT NULL CHECK ({_uuid_check("version_id", "7")}),
            version_revision_id TEXT NOT NULL CHECK ({_uuid_check("version_revision_id", "7")}),
            object_sha256 TEXT NOT NULL CHECK ({_sha256_check("object_sha256")}),
            subject_sha256 TEXT NOT NULL CHECK ({_sha256_check("subject_sha256")}),
            rights_policy_revision_id TEXT NOT NULL CHECK ({_uuid_check("rights_policy_revision_id", "7")}),
            confirmation_sha256 TEXT CHECK (confirmation_sha256 IS NULL OR ({_sha256_check("confirmation_sha256")})),
            command_id TEXT NOT NULL UNIQUE CHECK ({_uuid_check("command_id", "7")}),
            command_sha256 TEXT NOT NULL CHECK ({_sha256_check("command_sha256")}),
            provenance_event_id TEXT NOT NULL UNIQUE CHECK ({_uuid_check("provenance_event_id", "7")}),
            outbox_id TEXT NOT NULL UNIQUE CHECK ({_uuid_check("outbox_id", "7")}),
            actor_id TEXT NOT NULL CHECK ({_uuid_check("actor_id", "7")}),
            committed_at TEXT NOT NULL CHECK ({_timestamp_check("committed_at")}),
            FOREIGN KEY (candidate_id,project_id,source_assertion_revision_id)
                REFERENCES document_attachment_candidates(candidate_id,project_id,source_assertion_revision_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (document_revision_id,project_id) REFERENCES aggregate_revisions(revision_id,project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (work_revision_id,project_id,work_id) REFERENCES reconciliation_work_states
                (revision_id,project_id,work_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (version_revision_id,project_id,version_id) REFERENCES reconciliation_versions
                (revision_id,project_id,version_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (object_sha256,project_id) REFERENCES object_records(object_sha256,project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (rights_policy_revision_id,project_id,subject_sha256) REFERENCES rights_policy_revisions
                (revision_id,project_id,subject_sha256) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (provenance_event_id) REFERENCES provenance_events(event_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (outbox_id) REFERENCES outbox_events(outbox_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    *(
        statement
        for table in DOCUMENT_ATTACHMENT_TABLES
        for statement in _immutable_triggers(table, "document attachment history is append-only")
    ),
    "CREATE INDEX document_attachment_candidates_work ON document_attachment_candidates(project_id,work_id,version_id)",
    "CREATE INDEX document_attachment_candidates_object ON document_attachment_candidates(project_id,object_sha256)",
    "CREATE INDEX document_attachment_assertions_version "
    "ON document_attachment_assertions(project_id,version_revision_id)",
    """
        CREATE TRIGGER document_attachment_assertion_binding BEFORE INSERT ON document_attachment_assertions
        WHEN EXISTS (SELECT 1 FROM document_attachment_cancellations x WHERE x.candidate_id=NEW.candidate_id)
          OR NOT EXISTS (
              SELECT 1 FROM document_attachment_candidates c JOIN documents d
                ON d.revision_id=NEW.document_revision_id AND d.project_id=c.project_id
                JOIN aggregate_revisions r ON r.revision_id=d.revision_id AND r.project_id=d.project_id
              WHERE c.candidate_id=NEW.candidate_id AND c.project_id=NEW.project_id
                AND c.source_assertion_revision_id=NEW.source_assertion_revision_id
                AND c.work_id=NEW.work_id AND c.work_revision_id=NEW.work_revision_id
                AND c.version_id=NEW.version_id AND c.version_revision_id=NEW.version_revision_id
                AND c.object_sha256=NEW.object_sha256 AND d.object_sha256=c.object_sha256
                AND r.aggregate_id=NEW.document_id AND r.aggregate_kind='document'
                AND ((c.confirmation_required=0 AND NEW.confirmation_sha256 IS NULL)
                  OR (c.confirmation_required=1 AND NEW.confirmation_sha256=c.candidate_sha256))
          )
          OR NOT EXISTS (
              SELECT 1 FROM rights_policy_revisions p JOIN rights_policy_subjects s
                ON s.project_id=p.project_id AND s.subject_sha256=p.subject_sha256
              WHERE p.revision_id=NEW.rights_policy_revision_id AND p.project_id=NEW.project_id
                AND p.subject_sha256=NEW.subject_sha256 AND s.copy_id=NEW.candidate_id
                AND s.source_assertion_revision_id=NEW.source_assertion_revision_id
                AND s.copy_location='local-project-object' AND s.resource_class='full-text'
          )
          OR NOT EXISTS (
              SELECT 1 FROM provenance_events p JOIN outbox_events o
                ON o.project_id=p.project_id AND o.revision_id=p.revision_id
              WHERE p.event_id=NEW.provenance_event_id AND o.outbox_id=NEW.outbox_id
                AND p.project_id=NEW.project_id AND p.revision_id=NEW.document_revision_id
                AND p.actor_id=NEW.actor_id AND p.occurred_at=NEW.committed_at
                AND p.record_sha256=o.record_sha256
          )
        BEGIN SELECT RAISE(ABORT,'document attachment assertion binding denied'); END
    """,
)

ATTACHMENT_OPERATION_DDL = (
    f"""
        CREATE TABLE document_attachment_operations (
            operation_id TEXT PRIMARY KEY CHECK ({_uuid_check("operation_id", "7")}),
            project_id TEXT NOT NULL,
            candidate_id TEXT NOT NULL UNIQUE CHECK ({_uuid_check("candidate_id", "7")}),
            session_id TEXT NOT NULL CHECK (length(session_id)=32 AND session_id=lower(session_id)
                AND session_id NOT GLOB '*[^0-9a-f]*'),
            actor_id TEXT NOT NULL CHECK ({_uuid_check("actor_id", "7")}),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            FOREIGN KEY (candidate_id,project_id) REFERENCES document_attachment_candidates
                (candidate_id,project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (operation_id,project_id)
        ) STRICT
    """,
    *(
        statement
        for table in ATTACHMENT_OPERATION_TABLES
        for statement in _immutable_triggers(table, "document attachment operation history is append-only")
    ),
    "CREATE INDEX document_attachment_operations_candidate ON document_attachment_operations(project_id,candidate_id)",
)


ACQUISITION_DDL = (
    f"""
        CREATE TABLE acquisition_locations (
            location_id TEXT PRIMARY KEY CHECK ({_uuid_check("location_id", "7")}),
            project_id TEXT NOT NULL,
            source_assertion_revision_id TEXT NOT NULL,
            location_key TEXT NOT NULL CHECK (length(location_key) BETWEEN 1 AND 128),
            location_sha256 TEXT NOT NULL CHECK ({_sha256_check("location_sha256")}),
            location_json TEXT NOT NULL CHECK (json_valid(location_json)),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            FOREIGN KEY (source_assertion_revision_id,project_id) REFERENCES reconciliation_assertions
                (revision_id,project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (location_id,project_id),
            UNIQUE (project_id,source_assertion_revision_id,location_key)
        ) STRICT
    """,
    f"""
        CREATE TABLE acquisition_attempts (
            operation_id TEXT PRIMARY KEY CHECK ({_uuid_check("operation_id", "7")}),
            project_id TEXT NOT NULL,
            revision_id TEXT NOT NULL,
            location_id TEXT NOT NULL,
            actor_id TEXT NOT NULL CHECK ({_uuid_check("actor_id", "7")}),
            session_id TEXT NOT NULL CHECK (length(session_id)=32 AND session_id=lower(session_id)
                AND session_id NOT GLOB '*[^0-9a-f]*'),
            selection_json TEXT NOT NULL CHECK (json_valid(selection_json)),
            confirmation_sha256 TEXT NOT NULL CHECK ({_sha256_check("confirmation_sha256")}),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            FOREIGN KEY (revision_id,project_id) REFERENCES aggregate_revisions(revision_id,project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (location_id,project_id) REFERENCES acquisition_locations(location_id,project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (operation_id,project_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE acquisition_attempt_results (
            operation_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            revision_id TEXT NOT NULL,
            outcome TEXT NOT NULL CHECK (outcome IN ('candidate','failed','cancelled')),
            code TEXT NOT NULL CHECK ({_identifier_check("code", 64)}),
            candidate_id TEXT,
            FOREIGN KEY (operation_id,project_id) REFERENCES acquisition_attempts(operation_id,project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (revision_id,project_id) REFERENCES aggregate_revisions(revision_id,project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (candidate_id,project_id) REFERENCES document_attachment_candidates(candidate_id,project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CHECK ((outcome='candidate')=(candidate_id IS NOT NULL))
        ) STRICT
    """,
    f"""
        CREATE TABLE document_acquisition_sources (
            candidate_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            operation_id TEXT NOT NULL UNIQUE,
            location_id TEXT NOT NULL,
            provider_policy_revision_id TEXT NOT NULL,
            receipt_sha256 TEXT NOT NULL CHECK ({_sha256_check("receipt_sha256")}),
            receipt_json TEXT NOT NULL CHECK (json_valid(receipt_json)),
            FOREIGN KEY (candidate_id,project_id) REFERENCES document_attachment_candidates
                (candidate_id,project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (operation_id,project_id) REFERENCES acquisition_attempts
                (operation_id,project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (location_id,project_id) REFERENCES acquisition_locations
                (location_id,project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (provider_policy_revision_id,project_id) REFERENCES rights_policy_revisions
                (revision_id,project_id) ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    """
        CREATE TRIGGER document_acquisition_source_binding BEFORE INSERT ON document_acquisition_sources
        WHEN NOT EXISTS (SELECT 1 FROM document_attachment_candidates c
            JOIN document_attachment_operations o ON o.project_id=c.project_id AND o.candidate_id=c.candidate_id
            JOIN acquisition_attempts attempt ON attempt.project_id=o.project_id AND attempt.operation_id=o.operation_id
            JOIN acquisition_locations l ON l.project_id=c.project_id
                AND l.source_assertion_revision_id=c.source_assertion_revision_id
            JOIN rights_policy_revisions r ON r.project_id=l.project_id
            JOIN rights_policy_subjects s ON s.project_id=r.project_id AND s.subject_sha256=r.subject_sha256
            WHERE c.candidate_id=NEW.candidate_id AND c.project_id=NEW.project_id AND l.location_id=NEW.location_id
                AND attempt.location_id=l.location_id AND attempt.operation_id=NEW.operation_id
                AND attempt.actor_id=o.actor_id AND attempt.session_id=o.session_id
                AND attempt.confirmation_sha256=json_extract(NEW.receipt_json,'$.confirmationSha256')
                AND r.revision_id=NEW.provider_policy_revision_id AND s.copy_id=l.location_id
                AND s.copy_location='provider-hosted' AND s.resource_class='full-text'
                AND s.source_assertion_revision_id=c.source_assertion_revision_id
                AND json_extract(NEW.receipt_json,'$.locationId')=l.location_id
                AND json_extract(NEW.receipt_json,'$.locationSha256')=l.location_sha256
                AND json_extract(NEW.receipt_json,'$.providerPolicyRevisionId')=r.revision_id
                AND json_extract(NEW.receipt_json,'$.actualSha256')=c.object_sha256
                AND json_extract(NEW.receipt_json,'$.expandedBytes')=c.byte_length)
        BEGIN SELECT RAISE(ABORT,'acquisition source binding denied'); END
    """,
    *(
        statement
        for table in ACQUISITION_TABLES
        for statement in _immutable_triggers(table, "acquisition source history is append-only")
    ),
)


_ATTACHMENT_OPS = "document_attachment_operations"
DOCUMENT_INTAKE_DDL = (
    f"""
        CREATE TABLE document_intake_jobs (
            operation_id TEXT PRIMARY KEY CHECK ({_uuid_check("operation_id", "7")}),
            project_id TEXT NOT NULL,
            revision_id TEXT NOT NULL,
            job_id TEXT NOT NULL UNIQUE,
            kind TEXT NOT NULL CHECK (kind IN ('local-import','remote-download')),
            actor_id TEXT NOT NULL CHECK ({_uuid_check("actor_id", "7")}),
            session_id TEXT NOT NULL CHECK (length(session_id)=32 AND session_id=lower(session_id)
                AND session_id NOT GLOB '*[^0-9a-f]*'),
            selection_json TEXT NOT NULL CHECK (json_valid(selection_json)),
            input_sha256 TEXT NOT NULL CHECK ({_sha256_check("input_sha256")}),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            FOREIGN KEY (revision_id,project_id) REFERENCES aggregate_revisions(revision_id,project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (job_id) REFERENCES workflow_queue_jobs(job_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (operation_id,project_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE document_intake_results (
            operation_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            revision_id TEXT NOT NULL,
            outcome TEXT NOT NULL CHECK (outcome IN ('candidate','failed','cancelled')),
            code TEXT NOT NULL CHECK ({_identifier_check("code", 64)}),
            candidate_id TEXT,
            FOREIGN KEY (operation_id,project_id) REFERENCES document_intake_jobs(operation_id,project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (revision_id,project_id) REFERENCES aggregate_revisions(revision_id,project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (candidate_id,project_id) REFERENCES document_attachment_candidates(candidate_id,project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CHECK ((outcome='candidate')=(candidate_id IS NOT NULL))
        ) STRICT
    """,
    f"""
        CREATE TABLE document_attachment_recoveries (
            operation_id TEXT PRIMARY KEY CHECK ({_uuid_check("operation_id", "7")}),
            project_id TEXT NOT NULL,
            original_operation_id TEXT NOT NULL,
            candidate_id TEXT NOT NULL,
            revision_id TEXT NOT NULL,
            actor_id TEXT NOT NULL CHECK ({_uuid_check("actor_id", "7")}),
            session_id TEXT NOT NULL CHECK (length(session_id)=32 AND session_id=lower(session_id)
                AND session_id NOT GLOB '*[^0-9a-f]*'),
            basis_sha256 TEXT NOT NULL CHECK ({_sha256_check("basis_sha256")}),
            basis_json TEXT NOT NULL CHECK (json_valid(basis_json)),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            FOREIGN KEY (original_operation_id,project_id) REFERENCES {_ATTACHMENT_OPS}(operation_id,project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (candidate_id,project_id) REFERENCES document_attachment_candidates(candidate_id,project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (revision_id,project_id) REFERENCES aggregate_revisions(revision_id,project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (operation_id,project_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE document_access_needs (
            annotation_id TEXT PRIMARY KEY CHECK ({_uuid_check("annotation_id", "7")}),
            project_id TEXT NOT NULL,
            revision_id TEXT NOT NULL UNIQUE,
            location_id TEXT,
            selection_json TEXT NOT NULL CHECK (json_valid(selection_json)),
            kind TEXT NOT NULL CHECK (kind IN ('unknown','unavailable','rights-denied','entitlement-required')),
            channel TEXT NOT NULL CHECK (channel IN ('manual','institutional')),
            actor_id TEXT NOT NULL CHECK ({_uuid_check("actor_id", "7")}),
            command_sha256 TEXT NOT NULL CHECK ({_sha256_check("command_sha256")}),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            FOREIGN KEY (revision_id,project_id) REFERENCES aggregate_revisions(revision_id,project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (location_id,project_id) REFERENCES acquisition_locations(location_id,project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (annotation_id,project_id)
        ) STRICT
    """,
    """
        CREATE TRIGGER document_intake_job_binding BEFORE INSERT ON document_intake_jobs
        WHEN NOT EXISTS (SELECT 1 FROM workflow_queue_jobs j JOIN aggregate_revisions r
            ON r.project_id=j.project_id WHERE j.job_id=NEW.job_id AND j.project_id=NEW.project_id
                AND j.max_attempts=1 AND j.command_fingerprint='sha256:'||NEW.input_sha256
                AND j.activity_type=CASE NEW.kind WHEN 'remote-download' THEN 'document-intake-remote'
                    ELSE 'document-intake-local' END
                AND r.revision_id=NEW.revision_id AND r.aggregate_id=NEW.operation_id AND r.aggregate_kind='workflow')
        BEGIN SELECT RAISE(ABORT,'document intake job binding denied'); END
    """,
    """
        CREATE TRIGGER document_attachment_recovery_binding BEFORE INSERT ON document_attachment_recoveries
        WHEN NOT EXISTS (SELECT 1 FROM document_attachment_operations o JOIN document_attachment_candidates c
            ON c.project_id=o.project_id AND c.candidate_id=o.candidate_id
            JOIN aggregate_revisions r ON r.project_id=c.project_id
            WHERE o.project_id=NEW.project_id AND o.operation_id=NEW.original_operation_id
                AND o.candidate_id=NEW.candidate_id AND o.actor_id=NEW.actor_id AND c.actor_id=NEW.actor_id
                AND r.revision_id=NEW.revision_id AND r.aggregate_id=NEW.operation_id AND r.aggregate_kind='workflow'
                AND json_extract(NEW.basis_json,'$.candidateId')=c.candidate_id
                AND json_extract(NEW.basis_json,'$.candidateSha256')=c.candidate_sha256
                AND json_extract(NEW.basis_json,'$.objectSha256')=c.object_sha256
                AND json_extract(NEW.basis_json,'$.originalOperationId')=o.operation_id
                AND json_extract(NEW.basis_json,'$.sessionId')=NEW.session_id
                AND json_extract(NEW.basis_json,'$.actorId')=NEW.actor_id)
        BEGIN SELECT RAISE(ABORT,'document recovery binding denied'); END
    """,
    *(
        statement
        for table in DOCUMENT_INTAKE_TABLES
        for statement in _immutable_triggers(table, "document intake and recovery history is append-only")
    ),
)


_DDL_STATEMENTS = (
    SCHEMA_METADATA_V25_DDL,
    *_V17_BASE_DDL_STATEMENTS,
    SCHEMA_MIGRATIONS_DDL,
    *SCHEMA_MIGRATIONS_TRIGGERS,
    *OBJECT_ENVELOPE_COLUMNS,
    "UPDATE object_records SET ciphertext_byte_length=byte_length",
    *OBJECT_ENVELOPE_TRIGGERS,
    OBJECT_ENVELOPE_UPGRADES_DDL,
    OBJECT_CREATION_SOURCE_COLUMN,
    *PROVENANCE_LEDGER_DDL,
    *WORKFLOW_EXECUTOR_DDL,
    *MATERIAL_DEPENDENCY_DDL,
    *_V17_DEPENDENCY_IMPACT_DDL,
    *IMPORT_PREVIEW_DDL,
    *IMPORT_SUMMARY_DDL,
    *IMPORT_COMMIT_DDL,
    *RECONCILIATION_DDL,
    *RECONCILIATION_REVIEW_DDL,
    *WORK_VERSION_DDL,
    *CORPUS_DDL,
    *RIGHTS_POLICY_DDL,
    *CORPUS_REPORT_DDL,
    *CORPUS_SOURCE_PROJECTION_DDL,
    *PLUGIN_GRANT_DDL,
    *DOCUMENT_ATTACHMENT_DDL,
    *ATTACHMENT_OPERATION_DDL,
    *ACQUISITION_DDL,
    *DOCUMENT_INTAKE_DDL,
)


def _normalize_utc_millisecond(value: str) -> str:
    if not isinstance(value, str) or not _UTC_INPUT.fullmatch(value):
        raise StorageProblem("storage timestamp must be a canonical UTC instant")
    try:
        instant = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise StorageProblem("storage timestamp must be a real UTC instant") from error
    offset = instant.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise StorageProblem("storage timestamp must use UTC")
    return instant.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _project_identity(value: str) -> tuple[str, str]:
    if not isinstance(value, str) or value != value.lower():
        raise StorageProblem("project identity must be canonical")
    try:
        identity = UUID(value)
    except ValueError as error:
        raise StorageProblem("project identity must be canonical") from error
    if str(identity) != value or identity.variant != "specified in RFC 4122" or identity.version not in {4, 7}:
        raise StorageProblem("project identity must be an approved UUID bridge or UUIDv7")
    return value, "uuid4-bridge" if identity.version == 4 else "uuid7"


def _redirect(path: Path) -> bool:
    try:
        native = Path(_native_io_path(path))
        return native.is_symlink() or native.is_junction()
    except OSError as error:
        raise StorageProblem("database path identity cannot be inspected") from error


def _canonical_database_path(path: Path, *, must_exist: bool) -> Path:
    database = Path(path)
    raw = str(database)
    windows_value = raw.replace("/", "\\").casefold()
    if (
        not database.is_absolute()
        or database.name != "project.sqlite3"
        or "\x00" in raw
        or windows_value.startswith(("\\\\?\\", "\\\\.\\", "\\??\\", "\\device\\"))
    ):
        raise StorageProblem("database path must be the canonical project database location")
    parent = database.parent
    try:
        if _redirect(parent) or not parent.is_dir() or parent.resolve(strict=True) != parent:
            raise StorageProblem("database parent is unavailable or redirected")
        if must_exist:
            status = database.stat(follow_symlinks=False)
            if _redirect(database) or not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
                raise StorageProblem("database file is redirected, linked, or non-regular")
            if database.resolve(strict=True) != database:
                raise StorageProblem("database file is not canonical")
        elif database.exists() or _redirect(database):
            raise StorageProblem("database initialization will not replace an existing entry")
    except StorageProblem:
        raise
    except OSError as error:
        raise StorageProblem("database path identity cannot be verified") from error
    return database


def _native_io_path(path: Path) -> str:
    """Encode a logical path for native I/O; never grant or normalize authority.

    Callers retain their canonical-parent, redirect, link and held-identity
    checks. The private encoding is not accepted as a caller-supplied path and
    must never enter a project-relative manifest.
    """
    raw = str(path)
    if os.name != "nt":
        return raw
    if (
        not path.is_absolute()
        or "\x00" in raw
        or raw.casefold().startswith(("\\\\?\\", "\\\\.\\", "\\??\\", "\\device\\"))
        or any(part == ".." or part.endswith((" ", ".")) for part in path.parts[1:])
    ):
        raise StorageProblem("native database path is not canonical")
    return "\\\\?\\UNC\\" + raw[2:] if raw.startswith("\\\\") else "\\\\?\\" + raw


def _database_uri(database: Path, *, mode: str = "rw") -> str:
    if mode not in {"ro", "rw"}:
        raise StorageProblem("database open mode is invalid")
    if os.name == "nt":
        # Path.as_uri treats an extended path as a URI authority. Quote the
        # private native filename instead, retaining the locking Windows VFS.
        return "file:" + quote(_native_io_path(database), safe="/:") + "?mode=" + mode + "&vfs=win32-longpath"
    return database.as_uri() + "?mode=" + mode


def _open_windows_guards(parent: Path, database: Path) -> list[int]:
    if os.name != "nt":
        return []
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    file_read_attributes = 0x00000080
    file_share_read = 0x00000001
    file_share_write = 0x00000002
    open_existing = 3
    file_flag_open_reparse_point = 0x00200000
    file_flag_backup_semantics = 0x02000000
    invalid_handle = wintypes.HANDLE(-1).value
    handles: list[int] = []
    for item, flags in (
        (parent, file_flag_open_reparse_point | file_flag_backup_semantics),
        (database, file_flag_open_reparse_point),
    ):
        handle = create_file(
            _native_io_path(item),
            file_read_attributes,
            file_share_read | file_share_write,
            None,
            open_existing,
            flags,
            None,
        )
        if handle == invalid_handle:
            _close_windows_handles(handles)
            raise StorageProblem("database path could not be held against replacement")
        handles.append(handle)
    return handles


def _close_windows_handles(handles: list[int]) -> None:
    if os.name != "nt" or not handles:
        return
    import ctypes
    from ctypes import wintypes

    close_handle = ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    for handle in reversed(handles):
        close_handle(handle)


_SCHEMA_MUTATION_ACTIONS = frozenset(
    getattr(sqlite3, name)
    for name in (
        "SQLITE_ALTER_TABLE",
        "SQLITE_CREATE_INDEX",
        "SQLITE_CREATE_TABLE",
        "SQLITE_CREATE_TEMP_INDEX",
        "SQLITE_CREATE_TEMP_TABLE",
        "SQLITE_CREATE_TEMP_TRIGGER",
        "SQLITE_CREATE_TEMP_VIEW",
        "SQLITE_CREATE_TRIGGER",
        "SQLITE_CREATE_VIEW",
        "SQLITE_CREATE_VTABLE",
        "SQLITE_DROP_INDEX",
        "SQLITE_DROP_TABLE",
        "SQLITE_DROP_TEMP_INDEX",
        "SQLITE_DROP_TEMP_TABLE",
        "SQLITE_DROP_TEMP_TRIGGER",
        "SQLITE_DROP_TEMP_VIEW",
        "SQLITE_DROP_TRIGGER",
        "SQLITE_DROP_VIEW",
        "SQLITE_DROP_VTABLE",
        "SQLITE_REINDEX",
    )
)

_PROTECTED_WRITE_PRAGMAS = frozenset(
    {
        "application_id",
        "busy_timeout",
        "defer_foreign_keys",
        "foreign_keys",
        "ignore_check_constraints",
        "journal_mode",
        "legacy_alter_table",
        "locking_mode",
        "query_only",
        "recursive_triggers",
        "schema_version",
        "synchronous",
        "trusted_schema",
        "user_version",
        "wal_autocheckpoint",
        "writable_schema",
    }
)
_PROTECTED_COMMAND_PRAGMAS = frozenset({"incremental_vacuum", "optimize", "wal_checkpoint"})


def _initialization_authorizer(
    action: int,
    _arg1: str | None,
    _arg2: str | None,
    _database: str | None,
    _trigger: str | None,
) -> int:
    if action in {sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH}:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def _canonical_authorizer(
    action: int,
    arg1: str | None,
    arg2: str | None,
    database: str | None,
    trigger: str | None,
) -> int:
    if action in _SCHEMA_MUTATION_ACTIONS:
        return sqlite3.SQLITE_DENY
    if action in {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE} and arg1 == "schema_migrations":
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_PRAGMA and arg1 is not None:
        pragma = arg1.casefold()
        if pragma in _PROTECTED_COMMAND_PRAGMAS or (pragma in _PROTECTED_WRITE_PRAGMAS and arg2 is not None):
            return sqlite3.SQLITE_DENY
    return _initialization_authorizer(action, arg1, arg2, database, trigger)


def _configure_connection(connection: Any, *, initialize: bool, protected: bool = False) -> None:
    sqlite_version = sqlcipher.sqlite_version_info if protected else sqlite3.sqlite_version_info
    if sqlite_version < MINIMUM_SQLITE_VERSION:
        raise StorageProblem("installed SQLite is older than the STRICT storage profile")
    if protected:
        version = connection.execute("PRAGMA cipher_version").fetchone()
        status = connection.execute("PRAGMA cipher_status").fetchone()
        if version is None or not str(version[0]).startswith("4.12.") or status is None or str(status[0]) != "1":
            raise StorageProblem("protected database runtime is unavailable")
        connection.execute("PRAGMA cipher_plaintext_header_size=0")
        cipher_expected = {
            "cipher_page_size": "4096",
            "cipher_use_hmac": "1",
            "cipher_hmac_algorithm": "HMAC_SHA512",
            "cipher_kdf_algorithm": "PBKDF2_HMAC_SHA512",
        }
        for pragma, cipher_value in cipher_expected.items():
            row = connection.execute(f"PRAGMA {pragma}").fetchone()
            if row is None or row[0] != cipher_value:
                raise StorageProblem("protected database compatibility profile was not applied")
    else:
        connection.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_FKEY, True)
        connection.setconfig(sqlite3.SQLITE_DBCONFIG_DQS_DDL, False)
        connection.setconfig(sqlite3.SQLITE_DBCONFIG_DQS_DML, False)
        connection.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION, False)
        connection.setconfig(sqlite3.SQLITE_DBCONFIG_TRUSTED_SCHEMA, False)
        connection.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, True)
    connection.enable_load_extension(False)
    connection.set_authorizer(_initialization_authorizer)
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MILLISECONDS}")
    connection.execute("PRAGMA trusted_schema=OFF")
    connection.execute("PRAGMA recursive_triggers=ON")
    connection.execute("PRAGMA locking_mode=NORMAL")
    journal_statement = "PRAGMA journal_mode=WAL" if initialize else "PRAGMA journal_mode"
    journal_mode = str(connection.execute(journal_statement).fetchone()[0]).lower()
    if journal_mode != "wal":
        raise StorageProblem("canonical database could not enter WAL mode")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute(f"PRAGMA wal_autocheckpoint={WAL_AUTOCHECKPOINT_PAGES}")
    expected = {
        "foreign_keys": 1,
        "busy_timeout": BUSY_TIMEOUT_MILLISECONDS,
        "trusted_schema": 0,
        "recursive_triggers": 1,
        "synchronous": 2,
        "wal_autocheckpoint": WAL_AUTOCHECKPOINT_PAGES,
    }
    for pragma, value in expected.items():
        if connection.execute(f"PRAGMA {pragma}").fetchone()[0] != value:
            raise StorageProblem("canonical database connection profile was not applied")
    if not initialize:
        connection.set_authorizer(_canonical_authorizer)


def _database_protection_configuration() -> _DatabaseProtectionConfiguration:
    with _DATABASE_PROTECTION_LOCK:
        configuration = _DATABASE_PROTECTION
    if configuration.profile == "unconfigured":
        raise StorageProblem("protected database key authority is not configured")
    return configuration


def _key_sqlcipher_connection(connection: Any, material: memoryview) -> None:
    if len(material) != 32:
        raise StorageProblem("protected database key material is invalid")
    raw_hex = material.hex()
    try:
        connection.execute(f"PRAGMA key = \"x'{raw_hex}'\"")
        connection.execute("PRAGMA cipher_compatibility=4")
        connection.execute("PRAGMA cipher_plaintext_header_size=0")
    finally:
        raw_hex = ""


def _connect_held(
    database: Path,
    *,
    project_id: str | None,
    create_key: bool = False,
    check_same_thread: bool = True,
    key_lease: DatabaseKeyLease | None = None,
) -> Any:
    parent_before = os.stat(_native_io_path(database.parent), follow_symlinks=False)
    before = os.stat(_native_io_path(database), follow_symlinks=False)
    configuration = _database_protection_configuration()
    protected = configuration.profile == SQLCIPHER_PROFILE
    if protected and configuration.provider is None:
        raise StorageProblem("protected database key authority is unavailable")
    if protected and project_id is None:
        raise StorageProblem("protected database project identity is required")
    descriptor: int | None = None
    handles: list[int] = []
    connection: Any = None
    try:
        descriptor = os.open(_native_io_path(database), os.O_RDONLY | getattr(os, "O_BINARY", 0))
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino) or opened.st_nlink != 1:
            raise StorageProblem("database identity changed before open")
        header = os.read(descriptor, len(_SQLCIPHER_HEADER))
        os.lseek(descriptor, 0, os.SEEK_SET)
        if protected and not create_key and header == _SQLCIPHER_HEADER:
            raise StorageProblem("production profile rejected a plaintext project database")
        handles = _open_windows_guards(database.parent, database)
        parent_after = os.stat(_native_io_path(database.parent), follow_symlinks=False)
        if (parent_after.st_dev, parent_after.st_ino) != (parent_before.st_dev, parent_before.st_ino) or _redirect(
            database.parent
        ):
            raise StorageProblem("database parent identity changed during open")
        uri = _database_uri(database)
        if protected:
            assert configuration.provider is not None
            assert project_id is not None
            key = configuration.provider.active_key(project_id, create=create_key) if key_lease is None else key_lease
            try:
                connection = sqlcipher.connect(
                    uri,
                    uri=True,
                    isolation_level=None,
                    timeout=BUSY_TIMEOUT_MILLISECONDS / 1_000,
                    factory=_GuardedSqlCipherConnection,
                    check_same_thread=check_same_thread,
                )
                key.use(lambda material: _key_sqlcipher_connection(connection, material))
            finally:
                if key_lease is None:
                    key.close()
            connection.row_factory = sqlcipher.Row
        else:
            connection = sqlite3.connect(
                uri,
                uri=True,
                autocommit=True,
                timeout=BUSY_TIMEOUT_MILLISECONDS / 1_000,
                factory=_GuardedConnection,
                check_same_thread=check_same_thread,
            )
            connection.row_factory = sqlite3.Row
        after = os.stat(_native_io_path(database), follow_symlinks=False)
        if (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino) or after.st_nlink != 1 or _redirect(database):
            raise StorageProblem("database identity changed during open")
        connection._guard_descriptor = descriptor
        connection._guard_handles = handles
        descriptor = None
        handles = []
        return connection
    except (OSError, DatabaseKeyProblem, *_DATABASE_ERRORS) as error:
        raise StorageProblem("canonical database could not be opened") from error
    finally:
        if connection is not None and descriptor is not None:
            connection.close()
        if descriptor is not None:
            os.close(descriptor)
        _close_windows_handles(handles)


def _schema_profile_errors(
    connection: sqlite3.Connection | CanonicalConnection, expected_project_id: str | None
) -> list[str]:
    errors: list[str] = []
    if connection.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID:
        errors.append("application-id-mismatch")
    if connection.execute("PRAGMA user_version").fetchone()[0] != DATABASE_SCHEMA_VERSION:
        errors.append("schema-version-mismatch")
    try:
        metadata = connection.execute(
            """
            SELECT schema_version, database_profile, application_id, profile_sha256, schema_sha256
            FROM schema_metadata WHERE singleton=1
            """
        ).fetchone()
    except _DATABASE_ERRORS:
        metadata = None
    if metadata is None or tuple(metadata) != (
        DATABASE_SCHEMA_VERSION,
        DATABASE_PROFILE,
        APPLICATION_ID,
        _PROFILE_SHA256,
        EXPECTED_SCHEMA_SHA256,
    ):
        errors.append("schema-metadata-mismatch")
    if _schema_fingerprint(connection) != EXPECTED_SCHEMA_SHA256:
        errors.append("canonical-schema-fingerprint-mismatch")
    if expected_project_id is not None:
        project_rows = connection.execute("SELECT project_id FROM projects ORDER BY project_id").fetchall()
        if [str(row[0]) for row in project_rows] != [expected_project_id]:
            errors.append("project-identity-mismatch")
    return errors


def _open_canonical_database(
    path: Path,
    *,
    expected_project_id: str | None,
    check_same_thread: bool,
) -> CanonicalConnection:
    database = _canonical_database_path(Path(path), must_exist=True)
    configuration = _database_protection_configuration()
    if configuration.profile == SQLCIPHER_PROFILE and expected_project_id is None:
        raise StorageProblem("protected database project identity is required")
    if expected_project_id is not None:
        expected_project_id, _ = _project_identity(expected_project_id)
    connection = _connect_held(
        database,
        project_id=expected_project_id,
        check_same_thread=check_same_thread,
    )
    try:
        _configure_connection(
            connection,
            initialize=False,
            protected=configuration.profile == SQLCIPHER_PROFILE,
        )
        errors = _schema_profile_errors(connection, expected_project_id)
        if errors:
            raise StorageProblem("canonical database profile is incompatible")
        return CanonicalConnection(_CAPABILITY_REGISTRY.register_connection(connection))
    except (*_DATABASE_ERRORS, StorageProblem) as error:
        connection.close()
        if isinstance(error, StorageProblem):
            raise
        raise StorageProblem("canonical database profile could not be verified") from error


def open_canonical_database(path: Path, *, expected_project_id: str | None = None) -> CanonicalConnection:
    """Open an existing canonical database with every connection control applied."""

    return _open_canonical_database(
        path,
        expected_project_id=expected_project_id,
        check_same_thread=True,
    )


def _open_thread_transferable_canonical_database(
    path: Path,
    *,
    expected_project_id: str,
) -> CanonicalConnection:
    """Open a guarded connection whose authority may be closed by its stream consumer."""

    return _open_canonical_database(
        path,
        expected_project_id=expected_project_id,
        check_same_thread=False,
    )


def validate_canonical_database(path: Path, *, expected_project_id: str | None = None) -> None:
    """Validate and close a canonical database without returning connection authority."""

    connection = open_canonical_database(path, expected_project_id=expected_project_id)
    connection.close()


def _schema_fingerprint(connection: sqlite3.Connection | CanonicalConnection) -> str:
    rows = [
        {"type": str(row[0]), "name": str(row[1]), "table": str(row[2]), "sql": str(row[3])}
        for row in connection.execute(
            """
            SELECT type, name, tbl_name, sql
            FROM sqlite_schema
            WHERE name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """
        )
    ]
    payload = json.dumps(rows, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def database_integrity_report(
    connection: sqlite3.Connection | CanonicalConnection,
    *,
    expected_project_id: str | None = None,
) -> DatabaseIntegrityReport:
    """Run content-free integrity checks against an already configured connection."""

    errors: list[str] = []
    profile_id: str | None = None
    schema_version: int | None = None
    application_id: int | None = None
    journal_mode: str | None = None
    foreign_keys: bool | None = None
    strict_tables: tuple[str, ...] = ()
    quick_check: tuple[str, ...] = ()
    foreign_key_violations: tuple[tuple[Any, ...], ...] = ()
    protection = database_protection_profile()
    cipher_version: str | None = None
    cipher_integrity: tuple[str, ...] = ()
    try:
        errors.extend(_schema_profile_errors(connection, expected_project_id))
        application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
        schema_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower()
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        metadata = connection.execute("SELECT database_profile FROM schema_metadata WHERE singleton=1").fetchone()
        profile_id = str(metadata[0]) if metadata is not None else None
        strict_tables = tuple(
            sorted(
                str(row[1])
                for row in connection.execute("PRAGMA table_list")
                if row[2] == "table" and int(row[5]) == 1 and not str(row[1]).startswith("sqlite_")
            )
        )
        quick_check = tuple(str(row[0]) for row in connection.execute("PRAGMA quick_check"))
        foreign_key_violations = tuple(tuple(row) for row in connection.execute("PRAGMA foreign_key_check"))
        if protection == SQLCIPHER_PROFILE:
            version = connection.execute("PRAGMA cipher_version").fetchone()
            cipher_version = None if version is None else str(version[0])
            cipher_integrity = tuple(str(row[0]) for row in connection.execute("PRAGMA cipher_integrity_check"))
            if cipher_version is None or not cipher_version.startswith("4.12."):
                errors.append("cipher-version-mismatch")
            if cipher_integrity:
                errors.append("cipher-integrity-check-failed")
        if quick_check != ("ok",):
            errors.append("quick-check-failed")
        if foreign_key_violations:
            errors.append("foreign-key-check-failed")
        if journal_mode != "wal" or foreign_keys is not True:
            errors.append("connection-profile-mismatch")
    except _DATABASE_ERRORS:
        errors.append("integrity-check-unavailable")
    return DatabaseIntegrityReport(
        ok=not errors,
        profile_id=profile_id,
        schema_version=schema_version,
        application_id=application_id,
        journal_mode=journal_mode,
        foreign_keys=foreign_keys,
        strict_tables=strict_tables,
        quick_check=quick_check,
        foreign_key_violations=foreign_key_violations,
        protection_profile=protection,
        cipher_version=cipher_version,
        cipher_integrity=cipher_integrity,
        errors=tuple(dict.fromkeys(errors)),
    )


def initialize_database(
    path: Path,
    *,
    project_id: str,
    project_created_at: str,
) -> DatabaseIntegrityReport:
    """Atomically initialize the current schema without replacing any existing entry."""

    database = _canonical_database_path(Path(path), must_exist=False)
    project_id, project_id_scheme = _project_identity(project_id)
    created_at = _normalize_utc_millisecond(project_created_at)
    descriptor: int | None = None
    connection: Any = None
    created = False
    succeeded = False
    try:
        descriptor = os.open(
            database,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
        )
        created = True
        status = os.fstat(descriptor)
        path_status = database.stat(follow_symlinks=False)
        if (
            not stat.S_ISREG(status.st_mode)
            or status.st_nlink != 1
            or (status.st_dev, status.st_ino) != (path_status.st_dev, path_status.st_ino)
        ):
            raise StorageProblem("new database identity is not exclusive")
        configuration = _database_protection_configuration()
        connection = _connect_held(database, project_id=project_id, create_key=True)
        _configure_connection(
            connection,
            initialize=True,
            protected=configuration.profile == SQLCIPHER_PROFILE,
        )
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
            connection.execute(f"PRAGMA user_version={DATABASE_SCHEMA_VERSION}")
            for statement in _DDL_STATEMENTS:
                connection.execute(statement)
            schema_sha256 = _schema_fingerprint(connection)
            if schema_sha256 != EXPECTED_SCHEMA_SHA256:
                raise StorageProblem("compiled schema does not match its reviewed fingerprint")
            connection.execute(
                """
                INSERT INTO schema_metadata (
                    singleton, schema_version, database_profile, application_id,
                    profile_sha256, schema_sha256, created_at
                ) VALUES (1, ?, ?, ?, ?, ?, ?)
                """,
                (
                    DATABASE_SCHEMA_VERSION,
                    DATABASE_PROFILE,
                    APPLICATION_ID,
                    _PROFILE_SHA256,
                    schema_sha256,
                    created_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO projects (
                    singleton, project_id, project_id_scheme, created_at
                ) VALUES (1, ?, ?, ?)
                """,
                (project_id, project_id_scheme, created_at),
            )
            connection.set_authorizer(_canonical_authorizer)
            report = database_integrity_report(connection, expected_project_id=project_id)
            if not report.ok:
                raise StorageProblem("new database did not satisfy its integrity contract")
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        after = database.stat(follow_symlinks=False)
        opened = os.fstat(descriptor)
        if (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino) or after.st_nlink != 1:
            raise StorageProblem("new database identity changed during initialization")
        os.lseek(descriptor, 0, os.SEEK_SET)
        header = os.read(descriptor, len(_SQLCIPHER_HEADER))
        if configuration.profile == SQLCIPHER_PROFILE and header == _SQLCIPHER_HEADER:
            raise StorageProblem("protected database initialization produced plaintext")
        succeeded = True
        return report
    except (OSError, *_DATABASE_ERRORS) as error:
        raise StorageProblem("canonical database initialization failed") from error
    finally:
        if connection is not None:
            connection.close()
        if descriptor is not None:
            os.close(descriptor)
        if created and not succeeded:
            for candidate in (database, Path(str(database) + "-wal"), Path(str(database) + "-shm")):
                with suppress(OSError):
                    candidate.unlink(missing_ok=True)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, document: dict[str, Any]) -> None:
    payload = (json.dumps(document, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode()
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = None
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        with suppress(OSError):
            temporary.unlink(missing_ok=True)


def _create_exclusive_database_file(path: Path) -> None:
    if not path.is_absolute() or "\x00" in str(path):
        raise StorageProblem("protected database output path is invalid")
    parent = path.parent
    created = False
    valid = False
    descriptor: int | None = None
    try:
        if _redirect(parent) or not parent.is_dir() or parent.resolve(strict=True) != parent:
            raise StorageProblem("protected database output parent is unavailable or redirected")
        if path.exists() or _redirect(path):
            raise StorageProblem("protected database output already exists")
        descriptor = os.open(
            path,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
        )
        created = True
        opened = os.fstat(descriptor)
        visible = path.stat(follow_symlinks=False)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or visible.st_nlink != 1
            or (opened.st_dev, opened.st_ino) != (visible.st_dev, visible.st_ino)
        ):
            raise StorageProblem("protected database output identity is invalid")
        valid = True
    except StorageProblem:
        raise
    except OSError as error:
        raise StorageProblem("protected database output could not be created") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if created and not valid:
            with suppress(OSError):
                path.unlink(missing_ok=True)


def _remove_database_sidecars(path: Path) -> None:
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(path) + suffix)
        if sidecar.exists() and sidecar.stat(follow_symlinks=False).st_size:
            raise StorageProblem("protected database retained live sidecar state")
        sidecar.unlink(missing_ok=True)


def _verify_protected_database_file(
    path: Path,
    project_id: str,
    key: DatabaseKeyLease,
    *,
    checkpoint: bool = False,
) -> None:
    connection = _connect_held(path, project_id=project_id, key_lease=key)
    try:
        _configure_connection(connection, initialize=False, protected=True)
        if _schema_profile_errors(connection, project_id):
            raise StorageProblem("protected database backup profile is incompatible")
        if tuple(str(row[0]) for row in connection.execute("PRAGMA cipher_integrity_check")):
            raise StorageProblem("protected database backup failed cipher integrity")
        if tuple(str(row[0]) for row in connection.execute("PRAGMA quick_check")) != ("ok",):
            raise StorageProblem("protected database backup failed logical integrity")
        if tuple(connection.execute("PRAGMA foreign_key_check")):
            raise StorageProblem("protected database backup failed referential integrity")
        if checkpoint:
            connection.set_authorizer(_initialization_authorizer)
            result = tuple(int(value) for value in connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone())
            if result != (0, 0, 0):
                raise StorageProblem("protected database backup could not checkpoint")
    except (*_DATABASE_ERRORS,) as error:
        raise StorageProblem("protected database backup verification failed") from error
    finally:
        connection.close()
    _remove_database_sidecars(path)


def create_protected_database_backup(
    path: Path,
    destination: Path,
    *,
    project_id: str,
) -> ProtectedDatabaseBackupReport:
    """Create and verify one encrypted, self-contained SQLCipher database backup."""

    project_id, _ = _project_identity(project_id)
    database = _canonical_database_path(Path(path), must_exist=True)
    backup = Path(destination)
    if backup == database:
        raise StorageProblem("protected database backup cannot replace the canonical database")
    configuration = _database_protection_configuration()
    if configuration.profile != SQLCIPHER_PROFILE or configuration.provider is None:
        raise StorageProblem("protected database backup requires the production protection profile")
    _create_exclusive_database_file(backup)
    source: Any | None = None
    target: Any | None = None
    succeeded = False
    try:
        with configuration.provider.active_key(project_id, create=False) as key:
            source = _connect_held(database, project_id=project_id, key_lease=key)
            target = _connect_held(backup, project_id=project_id, key_lease=key)
            _configure_connection(source, initialize=False, protected=True)
            _configure_connection(target, initialize=True, protected=True)
            source.set_authorizer(_initialization_authorizer)
            checkpoint = tuple(int(value) for value in source.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone())
            if checkpoint[0] != 0 or checkpoint[1] != checkpoint[2]:
                raise StorageProblem("protected database source could not reach a backup checkpoint")
            source.backup(target, pages=256, sleep=0.01)
            target.set_authorizer(_initialization_authorizer)
            target_checkpoint = tuple(
                int(value) for value in target.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            )
            if target_checkpoint != (0, 0, 0):
                raise StorageProblem("protected database backup could not checkpoint")
            target.close()
            target = None
            source.close()
            source = None
            _verify_protected_database_file(backup, project_id, key)
        with backup.open("rb") as stream:
            if stream.read(len(_SQLCIPHER_HEADER)) == _SQLCIPHER_HEADER:
                raise StorageProblem("protected database backup unexpectedly contains plaintext")
        os.chmod(backup, 0o600)
        succeeded = True
        return ProtectedDatabaseBackupReport(
            protection_profile=SQLCIPHER_PROFILE,
            database_sha256=_file_sha256(backup),
            size_bytes=backup.stat(follow_symlinks=False).st_size,
        )
    except (*_DATABASE_ERRORS, OSError) as error:
        raise StorageProblem("protected database backup failed") from error
    finally:
        if target is not None:
            target.close()
        if source is not None:
            source.close()
        if not succeeded:
            for candidate in (backup, Path(str(backup) + "-wal"), Path(str(backup) + "-shm")):
                with suppress(OSError):
                    candidate.unlink(missing_ok=True)


def restore_protected_database_backup(
    backup_path: Path,
    path: Path,
    *,
    project_id: str,
    operation_id: str,
) -> ProtectedDatabaseRestoreReport:
    """Verify and atomically restore one protected database, rolling back on publication failure."""

    validate_database_key_identity(project_id, operation_id)
    database = _canonical_database_path(Path(path), must_exist=True)
    backup = Path(backup_path)
    try:
        backup_status = backup.stat(follow_symlinks=False)
        if (
            not backup.is_absolute()
            or _redirect(backup)
            or not stat.S_ISREG(backup_status.st_mode)
            or backup_status.st_nlink != 1
            or backup.resolve(strict=True) != backup
        ):
            raise StorageProblem("protected database backup authority is invalid")
    except StorageProblem:
        raise
    except OSError as error:
        raise StorageProblem("protected database backup authority is unavailable") from error
    configuration = _database_protection_configuration()
    if configuration.profile != SQLCIPHER_PROFILE or configuration.provider is None:
        raise StorageProblem("protected database restore requires the production protection profile")
    if _CAPABILITY_REGISTRY.has_open_connections():
        raise StorageProblem("protected database restore requires a quiescent Core database boundary")
    staging = database.parent.parent / ".tmp"
    if not staging.is_dir() or _redirect(staging) or staging.resolve(strict=True) != staging:
        raise StorageProblem("protected database restore staging authority is unavailable")
    candidate = staging / f"database-restore-{operation_id}.candidate.sqlite3"
    quarantine = staging / f"database-restore-{operation_id}.displaced.sqlite3"
    failed = staging / f"database-restore-{operation_id}.failed.sqlite3"
    if candidate.exists() or quarantine.exists() or failed.exists():
        raise StorageProblem("protected database restore artifacts already exist")
    with configuration.provider.active_key(project_id, create=False) as key:
        _verify_protected_database_file(backup, project_id, key)
        _verify_protected_database_file(database, project_id, key, checkpoint=True)
        before_sha256 = _file_sha256(database)
        _create_exclusive_database_file(candidate)
        try:
            shutil.copyfile(backup, candidate)
            with candidate.open("r+b") as stream:
                stream.flush()
                os.fsync(stream.fileno())
            _verify_protected_database_file(candidate, project_id, key)
            restored_sha256 = _file_sha256(candidate)
            os.replace(database, quarantine)
            try:
                os.replace(candidate, database)
                verified = _open_with_key_lease(database, project_id, key)
                verified.close()
            except BaseException:
                try:
                    if database.exists():
                        os.replace(database, failed)
                    os.replace(quarantine, database)
                except OSError as rollback_error:
                    raise StorageProblem("protected database restore requires manual recovery") from rollback_error
                with suppress(OSError):
                    failed.unlink(missing_ok=True)
                raise
            try:
                quarantine.unlink()
                outcome = "restored"
            except OSError:
                outcome = "restored-displaced-ciphertext-retained"
            return ProtectedDatabaseRestoreReport(
                operation_id=operation_id,
                outcome=outcome,
                restored_database_sha256=restored_sha256,
                displaced_database_sha256=before_sha256,
            )
        except (*_DATABASE_ERRORS, OSError) as error:
            raise StorageProblem("protected database restore failed") from error
        finally:
            with suppress(OSError):
                candidate.unlink(missing_ok=True)


def _rekey_paths(database: Path, operation_id: str) -> tuple[Path, Path, Path]:
    project = database.parent.parent
    staging = project / ".tmp"
    if not staging.is_dir() or _redirect(staging) or staging.resolve(strict=True) != staging:
        raise StorageProblem("database rekey staging authority is unavailable")
    manifest = staging / f"database-rekey-{operation_id}.json"
    backup = staging / f"database-rekey-{operation_id}.backup.sqlite3"
    quarantine = staging / f"database-rekey-{operation_id}.unrecoverable.sqlite3"
    return manifest, backup, quarantine


def _open_with_key_lease(database: Path, project_id: str, key: DatabaseKeyLease) -> Any:
    connection = _connect_held(database, project_id=project_id, key_lease=key)
    try:
        _configure_connection(connection, initialize=False, protected=True)
        if _schema_profile_errors(connection, project_id):
            raise StorageProblem("protected database profile is incompatible")
        return connection
    except BaseException:
        connection.close()
        raise


def rekey_protected_database(
    path: Path,
    *,
    project_id: str,
    operation_id: str,
    failure_hook: Callable[[str], None] | None = None,
) -> DatabaseRekeyReport:
    """Rekey one protected database with an encrypted rollback copy and resumable key activation."""

    validate_database_key_identity(project_id, operation_id)
    database = _canonical_database_path(Path(path), must_exist=True)
    configuration = _database_protection_configuration()
    if configuration.profile != SQLCIPHER_PROFILE or configuration.provider is None:
        raise StorageProblem("database rekey requires the protected production profile")
    manifest, backup, _quarantine = _rekey_paths(database, operation_id)
    if manifest.exists() or backup.exists():
        return recover_protected_database_rekey(database, project_id=project_id, operation_id=operation_id)

    provider = configuration.provider
    with provider.active_key(project_id, create=False) as active:
        previous_version = active.version
    with provider.staged_rekey(project_id, operation_id, create=True) as staged:
        staged_version = staged.version

    connection = _connect_held(database, project_id=project_id)
    backup_sha256 = ""
    try:
        _configure_connection(connection, initialize=False, protected=True)
        connection.set_authorizer(_initialization_authorizer)
        checkpoint = tuple(connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone())
        if checkpoint != (0, 0, 0):
            raise StorageProblem("protected database could not reach a rekey checkpoint")
        shutil.copyfile(database, backup)
        os.chmod(backup, 0o600)
        with backup.open("r+b") as stream:
            stream.flush()
            os.fsync(stream.fileno())
        backup_sha256 = _file_sha256(backup)
        document = {
            "schemaVersion": "1.0",
            "documentType": "research-observatory-database-rekey-recovery",
            "projectId": project_id,
            "operationId": operation_id,
            "database": "state/project.sqlite3",
            "backup": f".tmp/{backup.name}",
            "backupSha256": backup_sha256,
            "previousKeyVersion": previous_version,
            "stagedKeyVersion": staged_version,
            "state": "prepared",
        }
        _atomic_json(manifest, document)
        if failure_hook is not None:
            failure_hook("after-prepared")
        with provider.staged_rekey(project_id, operation_id, create=False) as staged:
            staged.use(lambda material: _rekey_sqlcipher_connection(connection, material))
        document["state"] = "database-rekeyed"
        _atomic_json(manifest, document)
        if failure_hook is not None:
            failure_hook("after-database-rekeyed")
    except BaseException:
        raise
    finally:
        connection.close()

    with provider.staged_rekey(project_id, operation_id, create=False) as staged:
        candidate = _open_with_key_lease(database, project_id, staged)
        try:
            if tuple(str(row[0]) for row in candidate.execute("PRAGMA cipher_integrity_check")):
                raise StorageProblem("protected database failed integrity after rekey")
        finally:
            candidate.close()
    active_version = provider.activate_rekey(
        project_id,
        operation_id,
        expected_active_version=previous_version,
    )
    document["state"] = "key-activated"
    document["activeKeyVersion"] = active_version
    _atomic_json(manifest, document)
    if failure_hook is not None:
        failure_hook("after-key-activated")
    verified = open_canonical_database(database, expected_project_id=project_id)
    verified.close()
    backup.unlink()
    manifest.unlink()
    return DatabaseRekeyReport(operation_id, "rekeyed", previous_version, active_version, backup_sha256)


def _rekey_sqlcipher_connection(connection: Any, material: memoryview) -> None:
    if len(material) != 32:
        raise StorageProblem("staged database key material is invalid")
    raw_hex = material.hex()
    try:
        connection.execute(f"PRAGMA rekey = \"x'{raw_hex}'\"")
    finally:
        raw_hex = ""


def recover_protected_database_rekey(
    path: Path,
    *,
    project_id: str,
    operation_id: str,
) -> DatabaseRekeyReport:
    """Resolve an interrupted rekey by proving the active key, staged key, or encrypted backup."""

    validate_database_key_identity(project_id, operation_id)
    database = _canonical_database_path(Path(path), must_exist=True)
    configuration = _database_protection_configuration()
    if configuration.profile != SQLCIPHER_PROFILE or configuration.provider is None:
        raise StorageProblem("database rekey recovery requires the protected production profile")
    manifest, backup, quarantine = _rekey_paths(database, operation_id)
    try:
        document = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise StorageProblem("database rekey recovery manifest is unavailable") from error
    if (
        not isinstance(document, dict)
        or document.get("projectId") != project_id
        or document.get("operationId") != operation_id
        or document.get("database") != "state/project.sqlite3"
        or document.get("backup") != f".tmp/{backup.name}"
        or not isinstance(document.get("backupSha256"), str)
        or not isinstance(document.get("previousKeyVersion"), str)
    ):
        raise StorageProblem("database rekey recovery manifest is invalid")
    backup_sha256 = str(document["backupSha256"])
    previous_version = str(document["previousKeyVersion"])
    provider = configuration.provider

    try:
        connection = open_canonical_database(database, expected_project_id=project_id)
    except StorageProblem:
        connection = None
    if connection is not None:
        connection.close()
        with provider.active_key(project_id, create=False) as active:
            active_version = active.version
        backup.unlink(missing_ok=True)
        manifest.unlink(missing_ok=True)
        return DatabaseRekeyReport(
            operation_id, "active-key-confirmed", previous_version, active_version, backup_sha256
        )

    staged_valid = False
    try:
        with provider.staged_rekey(project_id, operation_id, create=False) as staged:
            candidate = _open_with_key_lease(database, project_id, staged)
            candidate.close()
            staged_valid = True
    except DatabaseKeyProblem, StorageProblem:
        staged_valid = False
    if staged_valid:
        try:
            active_version = provider.activate_rekey(
                project_id,
                operation_id,
                expected_active_version=previous_version,
            )
        except DatabaseKeyConflict:
            with provider.active_key(project_id, create=False) as active:
                active_version = active.version
        verified = open_canonical_database(database, expected_project_id=project_id)
        verified.close()
        backup.unlink(missing_ok=True)
        manifest.unlink(missing_ok=True)
        return DatabaseRekeyReport(
            operation_id, "staged-key-activated", previous_version, active_version, backup_sha256
        )

    if not backup.is_file() or _file_sha256(backup) != backup_sha256:
        raise StorageProblem("database rekey recovery backup is invalid")
    if quarantine.exists():
        raise StorageProblem("database rekey recovery quarantine already exists")
    os.replace(database, quarantine)
    shutil.copyfile(backup, database)
    os.chmod(database, 0o600)
    restored = open_canonical_database(database, expected_project_id=project_id)
    restored.close()
    with provider.active_key(project_id, create=False) as active:
        active_version = active.version
    backup.unlink(missing_ok=True)
    manifest.unlink(missing_ok=True)
    return DatabaseRekeyReport(
        operation_id, "encrypted-backup-restored", previous_version, active_version, backup_sha256
    )


_PLAINTEXT_MIGRATION_APPROVAL = "approve-plaintext-to-protected-v1"


def _migration_paths(database: Path, operation_id: str) -> tuple[Path, Path, Path]:
    project = database.parent.parent
    staging = project / ".tmp"
    if not staging.is_dir() or _redirect(staging) or staging.resolve(strict=True) != staging:
        raise StorageProblem("database protection migration staging authority is unavailable")
    manifest = staging / f"database-protection-migration-{operation_id}.json"
    target = staging / f"database-protection-migration-{operation_id}.sqlcipher"
    rollback = staging / f"database-protection-migration-{operation_id}.plaintext-rollback"
    return manifest, target, rollback


def _verify_plaintext_source(database: Path, project_id: str) -> Any:
    with database.open("rb") as stream:
        if stream.read(len(_SQLCIPHER_HEADER)) != _SQLCIPHER_HEADER:
            raise StorageProblem("legacy database is not a plaintext SQLite source")
    source = sqlcipher.connect(
        database.as_uri() + "?mode=ro",
        uri=True,
        isolation_level=None,
        timeout=BUSY_TIMEOUT_MILLISECONDS / 1_000,
    )
    try:
        source.row_factory = sqlcipher.Row
        source.enable_load_extension(False)
        source.execute("PRAGMA trusted_schema=OFF")
        source.execute("PRAGMA foreign_keys=ON")
        if _schema_profile_errors(source, project_id):
            raise StorageProblem("legacy plaintext database profile is incompatible")
        report = tuple(str(row[0]) for row in source.execute("PRAGMA quick_check"))
        if report != ("ok",) or tuple(source.execute("PRAGMA foreign_key_check")):
            raise StorageProblem("legacy plaintext database failed integrity")
        return source
    except BaseException:
        source.close()
        raise


def _export_plaintext_to_protected(
    source: Any,
    target: Path,
    key: DatabaseKeyLease,
) -> None:
    if target.exists() or _redirect(target):
        raise StorageProblem("protected migration target already exists")

    def export(material: memoryview) -> None:
        if len(material) != 32:
            raise StorageProblem("protected database key material is invalid")
        key_literal = f"x'{material.hex()}'"
        attached = False
        try:
            source.execute("ATTACH DATABASE ? AS protected KEY ?", (str(target), key_literal))
            attached = True
            source.execute("SELECT sqlcipher_export('protected')").fetchone()
            source.execute(f"PRAGMA protected.application_id={APPLICATION_ID}")
            source.execute(f"PRAGMA protected.user_version={DATABASE_SCHEMA_VERSION}")
            source.execute("DETACH DATABASE protected")
            attached = False
        finally:
            key_literal = ""
            if attached:
                with suppress(sqlcipher.Error):
                    source.execute("DETACH DATABASE protected")

    key.use(export)


def _verify_protected_candidate(target: Path, project_id: str, key: DatabaseKeyLease) -> None:
    connection = _connect_held(target, project_id=project_id, key_lease=key)
    try:
        _configure_connection(connection, initialize=True, protected=True)
        errors = _schema_profile_errors(connection, project_id)
        if errors:
            raise StorageProblem(f"protected migration target profile is incompatible: {','.join(errors)}")
        if tuple(str(row[0]) for row in connection.execute("PRAGMA cipher_integrity_check")):
            raise StorageProblem("protected migration target failed cipher integrity")
        checkpoint = tuple(connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone())
        if checkpoint != (0, 0, 0):
            raise StorageProblem("protected migration target could not checkpoint")
    finally:
        connection.close()
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(target) + suffix)
        if sidecar.exists() and sidecar.stat().st_size:
            raise StorageProblem("protected migration target retained live sidecar state")
        sidecar.unlink(missing_ok=True)


def _cleanup_plaintext_rollback(path: Path) -> str:
    if not path.exists():
        return "not-present"
    try:
        os.chmod(path, 0o600)
        size = path.stat(follow_symlinks=False).st_size
        with path.open("r+b", buffering=0) as stream:
            block = b"\0" * (1024 * 1024)
            remaining = size
            while remaining:
                chunk = min(remaining, len(block))
                stream.write(block[:chunk])
                remaining -= chunk
            stream.flush()
            os.fsync(stream.fileno())
        path.unlink()
        return "best-effort-overwrite-and-unlink"
    except OSError:
        with suppress(OSError):
            os.chmod(path, 0o400)
        return "cleanup-pending-read-only"


def migrate_plaintext_database_to_protected(
    path: Path,
    *,
    project_id: str,
    operation_id: str,
    approval_token: str,
    failure_hook: Callable[[str], None] | None = None,
) -> DatabaseProtectionMigrationReport:
    """Copy a validated read-only legacy database into SQLCipher and atomically publish it."""

    validate_database_key_identity(project_id, operation_id)
    if approval_token != _PLAINTEXT_MIGRATION_APPROVAL:
        raise StorageProblem("plaintext database migration requires explicit approval")
    database = _canonical_database_path(Path(path), must_exist=True)
    configuration = _database_protection_configuration()
    if configuration.profile != SQLCIPHER_PROFILE or configuration.provider is None:
        raise StorageProblem("plaintext migration requires the protected production profile")
    manifest, target, rollback = _migration_paths(database, operation_id)
    if manifest.exists():
        return recover_plaintext_database_migration(database, project_id=project_id, operation_id=operation_id)
    if target.exists() or rollback.exists():
        raise StorageProblem("unbound database protection migration artifacts exist")

    source = _verify_plaintext_source(database, project_id)
    try:
        source_sha256 = _file_sha256(database)
        with configuration.provider.active_key(project_id, create=True) as key:
            _export_plaintext_to_protected(source, target, key)
            _verify_protected_candidate(target, project_id, key)
        target_sha256 = _file_sha256(target)
        document = {
            "schemaVersion": "1.0",
            "documentType": "research-observatory-database-protection-migration",
            "projectId": project_id,
            "operationId": operation_id,
            "source": "state/project.sqlite3",
            "target": f".tmp/{target.name}",
            "rollback": f".tmp/{rollback.name}",
            "plaintextSourceSha256": source_sha256,
            "protectedTargetSha256": target_sha256,
            "state": "prepared",
        }
        _atomic_json(manifest, document)
        if failure_hook is not None:
            failure_hook("after-prepared")
    finally:
        source.close()

    os.chmod(database, 0o400)
    os.replace(database, rollback)
    document["state"] = "source-staged"
    _atomic_json(manifest, document)
    if failure_hook is not None:
        failure_hook("after-source-staged")
    os.replace(target, database)
    document["state"] = "protected-published"
    _atomic_json(manifest, document)
    if failure_hook is not None:
        failure_hook("after-protected-published")
    verified = open_canonical_database(database, expected_project_id=project_id)
    verified.close()
    cleanup = _cleanup_plaintext_rollback(rollback)
    if cleanup.startswith("cleanup-pending"):
        document["state"] = cleanup
        _atomic_json(manifest, document)
    else:
        manifest.unlink()
    return DatabaseProtectionMigrationReport(operation_id, "protected", source_sha256, target_sha256, cleanup)


def recover_plaintext_database_migration(
    path: Path,
    *,
    project_id: str,
    operation_id: str,
) -> DatabaseProtectionMigrationReport:
    """Resume or safely roll back an interrupted plaintext-to-SQLCipher publication."""

    validate_database_key_identity(project_id, operation_id)
    database = Path(path)
    manifest, target, rollback = _migration_paths(database, operation_id)
    try:
        document = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise StorageProblem("database protection migration manifest is unavailable") from error
    if (
        not isinstance(document, dict)
        or document.get("projectId") != project_id
        or document.get("operationId") != operation_id
        or document.get("source") != "state/project.sqlite3"
        or document.get("target") != f".tmp/{target.name}"
        or document.get("rollback") != f".tmp/{rollback.name}"
        or not isinstance(document.get("plaintextSourceSha256"), str)
        or not isinstance(document.get("protectedTargetSha256"), str)
    ):
        raise StorageProblem("database protection migration manifest is invalid")
    source_sha256 = str(document["plaintextSourceSha256"])
    target_sha256 = str(document["protectedTargetSha256"])

    try:
        verified = open_canonical_database(database, expected_project_id=project_id)
    except OSError, StorageProblem:
        verified = None
    if verified is not None:
        verified.close()
        cleanup = _cleanup_plaintext_rollback(rollback)
        target.unlink(missing_ok=True)
        if cleanup.startswith("cleanup-pending"):
            document["state"] = cleanup
            _atomic_json(manifest, document)
        else:
            manifest.unlink(missing_ok=True)
        return DatabaseProtectionMigrationReport(
            operation_id, "protected-recovered", source_sha256, target_sha256, cleanup
        )

    configuration = _database_protection_configuration()
    if configuration.provider is None:
        raise StorageProblem("database protection migration key is unavailable")
    target_valid = target.is_file() and _file_sha256(target) == target_sha256
    if target_valid:
        try:
            with configuration.provider.active_key(project_id, create=False) as key:
                _verify_protected_candidate(target, project_id, key)
        except DatabaseKeyProblem, StorageProblem:
            target_valid = False
    if target_valid:
        if database.exists():
            with database.open("rb") as stream:
                header = stream.read(len(_SQLCIPHER_HEADER))
            if header != _SQLCIPHER_HEADER:
                raise StorageProblem("migration recovery found an unknown canonical database")
            if rollback.exists():
                raise StorageProblem("migration recovery found competing plaintext sources")
            os.chmod(database, 0o400)
            os.replace(database, rollback)
        if not rollback.is_file() or _file_sha256(rollback) != source_sha256:
            raise StorageProblem("migration recovery plaintext rollback is invalid")
        os.replace(target, database)
        verified = open_canonical_database(database, expected_project_id=project_id)
        verified.close()
        cleanup = _cleanup_plaintext_rollback(rollback)
        if cleanup.startswith("cleanup-pending"):
            document["state"] = cleanup
            _atomic_json(manifest, document)
        else:
            manifest.unlink(missing_ok=True)
        return DatabaseProtectionMigrationReport(
            operation_id, "protected-recovered", source_sha256, target_sha256, cleanup
        )

    target.unlink(missing_ok=True)
    if rollback.is_file() and _file_sha256(rollback) == source_sha256 and not database.exists():
        os.replace(rollback, database)
        os.chmod(database, 0o600)
    if not database.is_file() or _file_sha256(database) != source_sha256:
        raise StorageProblem("database protection migration cannot restore the plaintext source")
    manifest.unlink(missing_ok=True)
    return DatabaseProtectionMigrationReport(
        operation_id, "plaintext-restored", source_sha256, target_sha256, "retained"
    )
