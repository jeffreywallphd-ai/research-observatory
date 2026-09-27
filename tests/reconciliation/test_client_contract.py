"""Generated client consumes actual repository values, including review digests."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.reconciliation.decisions import AliasPlan, ReviewCommand, ReviewPlan, SourcePartition

from tests.reconciliation import test_batch_publication as fixtures


class ReconciliationClientContractTests(unittest.TestCase):
    def test_generated_client_checks_actual_candidates_inspection_and_reversible_review(self):
        fixture = fixtures.BatchPublicationTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        output = fixture.publish()
        repository, source = fixture.f.repository, fixture.f
        candidates = repository.inspect_candidates(output.revision_id, after=0, limit=25, resolve=source.resolve)
        inspection = repository.inspect(candidates.items[0].left, resolve=source.resolve)
        assert inspection.canonical_work is not None
        context = repository.review_context((inspection.canonical_work.work_id,), resolve=source.resolve)
        members = context.works[0].assertion_revision_ids
        plan = ReviewPlan(
            action="split",
            works=context.works,
            unassigned_assertion_revision_ids=(),
            partitions=(
                SourcePartition(
                    group="retained", existing_work_id=context.works[0].work_id, assertion_revision_ids=members[:1]
                ),
                SourcePartition(group="separate", existing_work_id=None, assertion_revision_ids=members[1:]),
            ),
            aliases=(),
            conflict_disposition="retain-all",
            evidence_sha256=context.evidence_sha256,
            rationale="Synthetic researcher decision preserves café and supplementary Unicode: 🧪.",
        )
        preview = repository.preview_review(plan, actor=source.actor, resolve=source.resolve)
        command = ReviewCommand(command_id=new_uuid_v7(), plan=plan, expected_preview_sha256=preview.preview_sha256)
        outcome = repository.review(command, actor=source.actor, resolve=source.resolve)
        values = dict(
            candidates=candidates,
            inspection=inspection,
            context=context,
            plan=plan,
            preview=preview,
            command=command,
            outcome=outcome,
        )
        merged_context = repository.review_context(
            tuple(work.work_id for work in outcome.work_states), resolve=source.resolve
        )
        survivor, retired = merged_context.works
        merged_plan = ReviewPlan(
            action="merge",
            works=merged_context.works,
            unassigned_assertion_revision_ids=(),
            partitions=(
                SourcePartition(
                    group="combined",
                    existing_work_id=survivor.work_id,
                    assertion_revision_ids=tuple(
                        sorted(member for work in merged_context.works for member in work.assertion_revision_ids)
                    ),
                ),
            ),
            aliases=(AliasPlan(work_id=retired.work_id, revision_id=retired.revision_id, target_group="combined"),),
            conflict_disposition="retain-all",
            evidence_sha256=merged_context.evidence_sha256,
            rationale="Synthetic reversible merge with an explicit surviving identity.",
        )
        merged_preview = repository.preview_review(merged_plan, actor=source.actor, resolve=source.resolve)
        merged_command = ReviewCommand(
            command_id=new_uuid_v7(), plan=merged_plan, expected_preview_sha256=merged_preview.preview_sha256
        )
        values.update(
            mergedCommand=merged_command,
            mergedOutcome=repository.review(merged_command, actor=source.actor, resolve=source.resolve),
        )
        repo = Path(__file__).resolve().parents[2]
        bundled_node = repo / ".local/toolchains/node-v24.19.0-win-x64/node.exe"
        node = str(bundled_node) if bundled_node.exists() else shutil.which("node") or "node"
        with tempfile.TemporaryDirectory(prefix="reconciliation-client-", dir=repo / "artifacts/tmp") as directory:
            path = Path(directory) / "synthetic-values.json"
            path.write_text(
                json.dumps({key: value.model_dump(mode="json", by_alias=True) for key, value in values.items()}),
                encoding="utf-8",
            )
            result = subprocess.run(
                [node, str(repo / "tests/reconciliation/verify-client.mjs"), str(path)],
                cwd=repo,
                capture_output=True,
                text=True,
                timeout=30,
                env={**os.environ, "NODE_NO_WARNINGS": "1"},
            )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("Actual reconciliation client contracts: PASS", result.stdout)
