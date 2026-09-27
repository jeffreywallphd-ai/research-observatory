"""Oracle accounting catches transitive error and never drops blocking misses."""

import unittest

from tests.reconciliation.duplicate_benchmark import metrics


class CandidateMetricTests(unittest.TestCase):
    def test_false_bridge_counts_pair_and_cluster_errors_separately(self):
        keys = frozenset({"acm:a", "dblp:a", "acm:b", "dblp:b", "dblp:c"})
        gold = frozenset({("acm:a", "dblp:a"), ("acm:b", "dblp:b")})
        predicted = frozenset({("acm:a", "dblp:a"), ("acm:a", "dblp:b"), ("acm:b", "dblp:b")})
        report = metrics(keys, predicted, gold)
        self.assertEqual((2, 3, 2), (report["truePositives"], report["returnedPairs"], report["goldPairs"]))
        self.assertEqual(2 / 3, report["precision"])
        self.assertEqual(1, report["recall"])
        self.assertEqual((1, 0), (report["overmergedComponents"], report["fragmentedComponents"]))
        self.assertEqual([("acm:a", "dblp:b")], report["falsePositivePairs"])
        self.assertEqual([("acm:a", "dblp:b"), ("acm:b", "dblp:a")], report["transitiveFalsePositivePairs"])

    def test_unretrieved_pairs_remain_in_recall_denominator(self):
        report = metrics(frozenset({"acm:a", "dblp:a"}), frozenset(), frozenset({("acm:a", "dblp:a")}))
        self.assertEqual((0, 0, 1), (report["precision"], report["recall"], report["fragmentedComponents"]))
        self.assertEqual([("acm:a", "dblp:a")], report["falseNegativePairs"])

    def test_unknown_reversed_and_same_source_pairs_cannot_enter_metrics(self):
        keys = frozenset({"acm:a", "dblp:a", "dblp:b"})
        for pair in (("acm:b", "dblp:a"), ("dblp:a", "acm:a"), ("dblp:a", "dblp:b")):
            with self.subTest(pair=pair), self.assertRaises(ValueError):
                metrics(keys, frozenset({pair}), frozenset())


if __name__ == "__main__":
    unittest.main()
