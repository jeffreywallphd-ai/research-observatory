#!/usr/bin/env python3
"""Create an indexed Proposed ADR linked to governed tasks."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

import yaml

from adr_check import ADR_ID, task_ids


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if not slug:
        raise ValueError("title must contain letters or numbers")
    return slug


def create_adr(
    repo: Path,
    adr_id: str,
    title: str,
    linked_tasks: list[str],
    affected_paths: list[str],
) -> Path:
    if not ADR_ID.fullmatch(adr_id):
        raise ValueError("ADR id must use ADR-NNNN")
    backlog = yaml.safe_load((repo / "planning" / "backlog.yaml").read_text(encoding="utf-8"))
    unknown = sorted(set(linked_tasks) - task_ids(backlog))
    if not linked_tasks or unknown:
        raise ValueError(f"ADR must link existing tasks; unknown={unknown}")
    if not affected_paths:
        raise ValueError("ADR must name at least one affected path or pattern")

    index_path = repo / "docs" / "adr" / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if any(record["id"] == adr_id for record in index["records"]):
        raise FileExistsError(f"{adr_id} already exists")
    relative = f"docs/adr/{adr_id}-{slugify(title)}.md"
    output = repo / relative
    if output.exists():
        raise FileExistsError(relative)

    task_lines = "\n".join(f"  - {task}" for task in linked_tasks)
    affected_lines = "\n".join(f"  - {path}" for path in affected_paths)
    task_links = "\n".join(f"- `{task}`" for task in linked_tasks)
    body = f"""---
id: {adr_id}
title: {title}
status: Proposed
date: {date.today().isoformat()}
deciders: []
linked_tasks:
{task_lines}
decision_scope: TODO - state exactly what this record governs.
affected_paths:
{affected_lines}
supersedes: []
superseded_by: null
---

# {adr_id}: {title}

## Context

TODO - problem, forces, authority, constraints, and evidence.

## Candidates

TODO - at least two credible candidates and tradeoffs.

## Decision

TODO - selected choice and rationale.

## Consequences

TODO - positive/negative consequences, profiles, compatibility, security, migration, and rollback.

## Verification

TODO - named checks and evidence.

## Task links

{task_links}
"""
    output.write_text(body, encoding="utf-8", newline="\n")
    index["records"].append(
        {
            "id": adr_id,
            "path": relative,
            "title": title,
            "status": "Proposed",
            "linkedTasks": linked_tasks,
        }
    )
    index["records"].sort(key=lambda record: record["id"])
    index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8", newline="\n")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--task", action="append", required=True)
    parser.add_argument("--affected", action="append", required=True)
    args = parser.parse_args()
    try:
        output = create_adr(
            Path(args.repo).resolve(), args.id, args.title, args.task, args.affected
        )
    except (OSError, ValueError, FileExistsError, KeyError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
