"""Portable report arithmetic and frozen drill identity at the pure boundary."""

from __future__ import annotations

import hashlib
import unittest
from collections import Counter

from pydantic import ValidationError
from research_observatory_core.corpus_report_model import (
    MAX_ROOTS_PER_MEMBER,
    CorpusReportAccumulator,
    CorpusReportDrillPage,
    CorpusReportFilter,
    CorpusReportMember,
    CorpusReportProblem,
    ReportField,
    ReportMembership,
    ReportPath,
    ReportRoute,
    ReportState,
    SourceOverlap,
    report_member_matches_filter,
)
from research_observatory_core.corpus_source_projection import _pair_counts

PROJECT = "01945c82-9340-4000-8000-000000000001"


def identity(number: int) -> str:
    return f"0199c100-0000-7000-8000-{number:012x}"


def member(
    number: int,
    *,
    sources: tuple[tuple[str | None, ReportRoute, int], ...],
    year: tuple[ReportState, str | None] = ("unknown", None),
    membership: ReportMembership = "candidate",
) -> CorpusReportMember:
    fields = tuple(
        ReportField(
            dimension=dimension,
            state=year[0] if dimension == "year" else "unknown",
            value=year[1] if dimension == "year" else None,
            witness_revision_id=identity(400 + number) if dimension == "year" and year[0] == "known" else None,
        )
        for dimension in ("identifier", "year", "venue", "language", "discipline", "oa", "full-text")
    )
    return CorpusReportMember(
        snapshot_id=identity(1),
        project_id=PROJECT,
        item_id=identity(10 + number),
        item_revision_id=identity(100 + number),
        work_id=identity(200 + number),
        work_revision_id=identity(300 + number),
        membership=membership,
        duplicate_of_item_id=None,
        display_label=f"Study {number}",
        paths=tuple(
            ReportPath(
                path_id=identity(path_id),
                source_revision_id=identity(1000 + path_id),
                context_revision_id=identity(2000 + path_id),
                source_key=source_key,
                route=route,
                metadata_assertion_status=(
                    "retained" if route in {"import-member", "connector-record"} else "no-external-assertion"
                ),
                report_inspect_status=("allowed" if route in {"import-member", "connector-record"} else "unassessed"),
                rights_policy_revision_id=(
                    identity(3000 + path_id) if route in {"import-member", "connector-record"} else None
                ),
                rights_expires_at=None,
                source_copy_availability="unknown",
            )
            for source_key, route, path_id in sources
        ),
        fields=fields,
    )


class CorpusReportModelTests(unittest.TestCase):
    def test_oversized_source_root_write_omits_quadratic_pairs_and_report_denies_limit(self) -> None:
        keys = tuple("import:" + identity(5000 + index) for index in range(1000))
        bounded = Counter({key: 1 for key in keys[:MAX_ROOTS_PER_MEMBER]})
        self.assertEqual(496, len(_pair_counts(bounded)))
        self.assertEqual({}, _pair_counts(Counter({key: 1 for key in keys[: MAX_ROOTS_PER_MEMBER + 1]})))
        self.assertEqual(496, len(_pair_counts(bounded)))
        self.assertEqual({}, _pair_counts(Counter({key: 1 for key in keys})))
        report = CorpusReportAccumulator(snapshot_id=identity(1), project_id=PROJECT)
        oversized = member(
            1,
            sources=tuple(
                (key, "import-member", 500 + index) for index, key in enumerate(keys[: MAX_ROOTS_PER_MEMBER + 1])
            ),
        )
        with self.assertRaisesRegex(CorpusReportProblem, "corpus-report-limit"):
            report.add(oversized)
        self.assertEqual(0, report.member_count)

    def test_plausible_tampered_pair_cannot_bind_to_exact_member_stream(self) -> None:
        report = CorpusReportAccumulator(snapshot_id=identity(1), project_id=PROJECT, projected_source_overlaps=True)
        report.add(
            member(
                1,
                sources=(
                    ("connector:openalex", "connector-record", 501),
                    ("import:" + identity(51), "import-member", 502),
                ),
            )
        )
        sources = (("connector:openalex", 1, 1), ("import:" + identity(51), 1, 1))
        with self.assertRaisesRegex(CorpusReportProblem, "corpus-report-projection-integrity-invalid"):
            report.bind_source_projection(sources, (("connector:openalex", "import:" + identity(51), 1, 2),))
        report.bind_source_projection(sources, (("connector:openalex", "import:" + identity(51), 1, 1),))

    def test_distinct_item_denominator_source_route_overlap_and_missingness(self) -> None:
        report = CorpusReportAccumulator(snapshot_id=identity(1), project_id=PROJECT)
        report.add(
            member(
                1,
                sources=(
                    ("import:" + identity(51), "import-member", 501),
                    ("import:" + identity(51), "import-member", 502),
                    ("connector:openalex", "connector-record", 503),
                ),
                year=("known", "2024"),
            )
        )
        report.add(
            member(
                2,
                sources=(("import:" + identity(51), "import-member", 504),),
                year=("not-reported", None),
                membership="included",
            )
        )
        summary = report.finalize(
            intent_revision_id=identity(2),
            protocol_revision_id=identity(3),
            created_at="2026-10-01T12:00:00.000Z",
        )

        self.assertEqual(summary.member_count, 2)
        self.assertEqual(summary.discovery_path_count, 4)
        self.assertEqual(summary.unattributed_discovery_path_count, 0)
        self.assertEqual(
            [(part.source_key, part.item_count, part.discovery_path_count) for part in summary.source_contributions],
            [("connector:openalex", 1, 1), ("import:" + identity(51), 2, 3)],
        )
        self.assertEqual(
            [
                (part.left_source_key, part.right_source_key, part.item_count, part.discovery_path_pair_count)
                for part in summary.source_overlaps
            ],
            [("connector:openalex", "import:" + identity(51), 1, 2)],
        )
        self.assertEqual(
            [
                (part.route, part.item_count, part.discovery_path_count)
                for part in summary.route_contributions
                if part.item_count
            ],
            [("import-member", 2, 3), ("connector-record", 1, 1)],
        )
        self.assertEqual(
            [
                (part.left_route, part.right_route, part.item_count, part.discovery_path_pair_count)
                for part in summary.route_overlaps
            ],
            [("connector-record", "import-member", 1, 2)],
        )
        year = next(item for item in summary.coverage if item.dimension == "year")
        self.assertEqual((year.known, year.not_reported, year.unknown, year.unavailable), (1, 1, 0, 0))
        self.assertEqual(sum(item.item_count for item in summary.membership_counts), 2)
        self.assertEqual(summary.members_sha256.__len__(), 64)

    def test_unattributed_route_does_not_invent_source_and_empty_report_is_exact(self) -> None:
        empty = CorpusReportAccumulator(snapshot_id=identity(1), project_id=PROJECT).finalize(
            intent_revision_id=identity(2),
            protocol_revision_id=identity(3),
            created_at="2026-10-01T12:00:00.000Z",
        )
        self.assertEqual(empty.member_count, 0)
        self.assertEqual(empty.members_sha256, hashlib.sha256(b"").hexdigest())
        self.assertEqual(empty.source_contributions, ())
        self.assertEqual(empty.unattributed_item_count, 0)

        report = CorpusReportAccumulator(snapshot_id=identity(1), project_id=PROJECT)
        report.add(member(1, sources=((None, "citation", 501),)))
        summary = report.finalize(
            intent_revision_id=identity(2),
            protocol_revision_id=identity(3),
            created_at="2026-10-01T12:00:00.000Z",
        )
        self.assertEqual(summary.source_contributions, ())
        self.assertEqual(summary.unattributed_item_count, 1)
        self.assertEqual(summary.discovery_path_count, 1)
        self.assertEqual(summary.unattributed_discovery_path_count, 1)
        self.assertEqual(next(part.item_count for part in summary.route_contributions if part.route == "citation"), 1)

        mixed = member(
            2,
            sources=(
                ("connector:openalex", "connector-record", 502),
                (None, "citation", 503),
            ),
        )
        self.assertTrue(report_member_matches_filter(mixed, CorpusReportFilter(kind="unattributed")))
        self.assertTrue(
            report_member_matches_filter(mixed, CorpusReportFilter(kind="source", source_key="connector:openalex"))
        )
        report.add(mixed)
        summary = report.finalize(
            intent_revision_id=identity(2),
            protocol_revision_id=identity(3),
            created_at="2026-10-01T12:00:00.000Z",
        )
        self.assertEqual(summary.unattributed_item_count, 2)
        self.assertEqual(summary.discovery_path_count, 3)
        self.assertEqual(summary.unattributed_discovery_path_count, 2)
        self.assertEqual(summary.source_contributions[0].item_count, 1)
        self.assertEqual(summary.source_contributions[0].discovery_path_count, 1)

    def test_invalid_witness_duplicate_member_and_order_leave_accumulator_unchanged(self) -> None:
        with self.assertRaises(ValidationError):
            ReportField(dimension="oa", state="known", value="yes", witness_revision_id=None)
        with self.assertRaises(ValidationError):
            ReportField(dimension="oa", state="known", value="available", witness_revision_id=identity(4))
        with self.assertRaises(ValidationError):
            member(1, sources=(("assertion:" + identity(5), "citation", 501),))
        with self.assertRaises(ValidationError):
            member(1, sources=(("connector:openalex", "import-member", 501),))
        with self.assertRaises(ValidationError):
            ReportPath(
                path_id=identity(501),
                source_revision_id=identity(1501),
                context_revision_id=identity(2501),
                source_key="connector:openalex",
                route="connector-record",
                metadata_assertion_status="retained",
                report_inspect_status="allowed",
                rights_policy_revision_id=None,
                rights_expires_at=None,
                source_copy_availability="unknown",
            )
        with self.assertRaises(ValidationError):
            ReportPath(
                path_id=identity(501),
                source_revision_id=identity(1501),
                context_revision_id=identity(2501),
                source_key=None,
                route="citation",
                metadata_assertion_status="no-external-assertion",
                report_inspect_status="unassessed",
                rights_policy_revision_id=identity(3501),
                rights_expires_at=None,
                source_copy_availability="unknown",
            )

        report = CorpusReportAccumulator(snapshot_id=identity(1), project_id=PROJECT)
        first = member(1, sources=(("connector:openalex", "connector-record", 501),))
        report.add(first)
        with self.assertRaisesRegex(ValueError, "corpus-report-member-order-invalid"):
            report.add(first)
        with self.assertRaisesRegex(ValueError, "corpus-report-member-order-invalid"):
            report.add(member(0, sources=(("connector:openalex", "connector-record", 502),)))
        self.assertEqual(report.member_count, 1)

    def test_filter_discriminants_and_value_distribution_overflow(self) -> None:
        self.assertEqual(CorpusReportFilter(kind="all").kind, "all")
        self.assertEqual(CorpusReportFilter(kind="membership", membership="included").membership, "included")
        self.assertEqual(CorpusReportFilter(kind="duplicate-linked").kind, "duplicate-linked")
        self.assertEqual(CorpusReportFilter(kind="unattributed").kind, "unattributed")
        self.assertEqual(
            CorpusReportFilter(kind="coverage", dimension="year", state="known", value="2024").value,
            "2024",
        )
        with self.assertRaises(ValidationError):
            CorpusReportFilter(kind="all", source_key="connector:openalex")
        with self.assertRaises(ValidationError):
            CorpusReportFilter(kind="membership")
        with self.assertRaises(ValidationError):
            CorpusReportFilter(kind="coverage", dimension="oa", state="unknown", value="yes")
        first = member(1, sources=(("connector:openalex", "connector-record", 501),))
        with self.assertRaises(ValidationError):
            CorpusReportDrillPage(
                snapshot_id=identity(1),
                project_id=PROJECT,
                filter=CorpusReportFilter(kind="source", source_key="connector:crossref"),
                members=(first,),
                next_cursor=None,
                total=1,
            )

        report = CorpusReportAccumulator(snapshot_id=identity(1), project_id=PROJECT, max_distribution_buckets=1)
        report.add(member(1, sources=(("connector:openalex", "connector-record", 501),), year=("known", "2023")))
        report.add(member(2, sources=(("connector:openalex", "connector-record", 502),), year=("known", "2024")))
        summary = report.finalize(
            intent_revision_id=identity(2),
            protocol_revision_id=identity(3),
            created_at="2026-10-01T12:00:00.000Z",
        )
        years = next(item for item in summary.value_distributions if item.dimension == "year")
        self.assertEqual([(item.value, item.item_count) for item in years.buckets], [("2023", 1)])
        self.assertEqual(years.other_known_count, 1)
        self.assertTrue(years.truncated)

    def test_path_pair_count_stays_within_safe_bounded_integer(self) -> None:
        with self.assertRaises(ValidationError):
            SourceOverlap(
                left_source_key="connector:openalex",
                right_source_key="import:" + identity(51),
                item_count=1,
                discovery_path_pair_count=49_950_000_001,
            )


if __name__ == "__main__":
    unittest.main()
