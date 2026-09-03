"""Supervised Core entrypoint for the native intent vertical integration check."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_observatory_core.config import CoreSettings
from research_observatory_core.main import run_supervised
from research_observatory_core.storage import configure_protected_database_provider, open_canonical_database
from research_observatory_core.windows_credentials import create_windows_database_key_provider


def inspect_project(profile_vault_root: Path, project_root: Path, project_id: str) -> int:
    """Report bounded persistence facts without exposing project or actor content."""

    configure_protected_database_provider(create_windows_database_key_provider(profile_vault_root))
    with open_canonical_database(
        project_root / "state" / "project.sqlite3",
        expected_project_id=project_id,
    ) as connection:
        revision_records = connection.execute(
            "SELECT COUNT(*) FROM settings WHERE setting_key='research-intent.revision'"
        ).fetchone()[0]
        event_rows = connection.execute(
            "SELECT event_type, COUNT(*), "
            "SUM(CASE WHEN actor_id IS NOT NULL AND actor_id <> '' THEN 1 ELSE 0 END) "
            "FROM provenance_events "
            "WHERE event_type IN ("
            "'intent.draft.saved','intent.accepted','intent.policy.evaluated','workflow.profile.activated'"
            ") "
            "GROUP BY event_type ORDER BY event_type"
        ).fetchall()
    events = {
        event_type: {"count": count, "actorBound": actor_bound == count}
        for event_type, count, actor_bound in event_rows
    }
    print(json.dumps({"revisionRecords": revision_records, "provenanceEvents": events}, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-vault-root", type=Path, required=True)
    parser.add_argument("--supervised", action="store_true")
    parser.add_argument("--inspect-project-root", type=Path)
    parser.add_argument("--project-id")
    arguments = parser.parse_args()
    profile_vault_root = arguments.profile_vault_root.resolve(strict=True)
    if arguments.inspect_project_root is not None or arguments.project_id is not None:
        if arguments.supervised or arguments.inspect_project_root is None or arguments.project_id is None:
            parser.error("inspection requires project root and project ID without supervised mode")
        return inspect_project(
            profile_vault_root,
            arguments.inspect_project_root.resolve(strict=True),
            arguments.project_id,
        )
    if not arguments.supervised:
        parser.error("the integration sidecar requires supervised or inspection mode")
    return run_supervised(
        CoreSettings(),
        profile_vault_root=profile_vault_root,
    )


if __name__ == "__main__":
    raise SystemExit(main())
