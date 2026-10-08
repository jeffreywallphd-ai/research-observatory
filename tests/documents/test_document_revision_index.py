"""Bounded writer traversal of the already validated canonical hierarchy."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api/src"))

from research_observatory_core.document_revision_repository import LocalDocumentRevisionRepository  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402


class DocumentRevisionIndexTests(unittest.TestCase):
    def test_large_valid_chain_and_flat_hierarchy_have_bounded_parent_reads_and_exact_order(self):
        # Counting an authority-bearing access avoids wall-clock assertions or
        # a hardware-dependent benchmark. The fixture is the validated index
        # boundary, not proof of untrusted IR validation or SQL publication.
        for topology in ("chain", "flat"):
            with self.subTest(topology=topology):
                count = 4096
                reads = [0]

                class Node:
                    def __init__(self, index, previous, observations):
                        self.node_id, self.order = new_uuid_v7(), index
                        self.kind, self.parent = "paragraph", previous
                        self.observations = observations

                    @property
                    def parent_id(self):
                        self.observations[0] += 1
                        return self.parent

                nodes, identities = [], []
                for index in range(count):
                    parent = nodes[-1].node_id if nodes and topology == "chain" else None
                    node = Node(index, parent, reads)
                    nodes.append(node)
                    identities.append(SimpleNamespace(role="node", canonical_id=node.node_id, staged_id=str(index)))
                accepted = SimpleNamespace(
                    revision_id=new_uuid_v7(),
                    element_identities=identities,
                    structure=SimpleNamespace(nodes=nodes, text_projections=(), references=(), citations=()),
                )
                repository = object.__new__(LocalDocumentRevisionRepository)
                repository.project = new_uuid_v7()
                rows = repository._element_rows(accepted)
                self.assertEqual(count, len(rows))
                self.assertEqual([node.node_id for node in nodes], [row[0] for row in rows])
                self.assertEqual(list(range(count)), [row[5] for row in rows])
                self.assertEqual([node.parent for node in nodes], [row[6] for row in rows])
                self.assertLessEqual(reads[0], 3 * count)


if __name__ == "__main__":
    unittest.main(verbosity=2)
