"""Portable, immutable corpus-report facts and distinct-item arithmetic.

This module calculates over Core-authorized observations. It does not discover
sources, infer unavailable metadata, grant rights, or read persistence. The
protected repository must resolve each witness before constructing a member.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime
from itertools import combinations
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .ingestion.import_drafts import Digest, DraftValue, Identity, ProjectIdentity

type ReportRoute = Literal["import-member", "connector-record", "citation", "recommendation", "manual"]
type ReportDimension = Literal["identifier", "year", "venue", "language", "discipline", "oa", "full-text"]
type ReportState = Literal["known", "not-reported", "unknown", "unavailable"]
type ReportMembership = Literal["candidate", "included", "excluded", "withdrawn"]
type ReportFilterKind = Literal[
    "all",
    "membership",
    "duplicate-linked",
    "unattributed",
    "source",
    "route",
    "source-overlap",
    "route-overlap",
    "coverage",
]

RULE_VERSION: Literal["corpus-report/1.0.0"] = "corpus-report/1.0.0"
DIMENSIONS: tuple[ReportDimension, ...] = ("identifier", "year", "venue", "language", "discipline", "oa", "full-text")
ROUTES: tuple[ReportRoute, ...] = ("import-member", "connector-record", "citation", "recommendation", "manual")
MEMBERSHIPS: tuple[ReportMembership, ...] = ("candidate", "included", "excluded", "withdrawn")
VALUE_DIMENSIONS: tuple[ReportDimension, ...] = ("year", "venue", "language", "discipline", "oa", "full-text")
MAX_MEMBERS = 100_000
MAX_SOURCE_ROOTS = 512
MAX_ROOTS_PER_MEMBER = 32
MAX_SOURCE_OVERLAP_PAIRS = 20_000
MAX_DISTRIBUTION_BUCKETS = 50
MAX_DISCOVERY_PATHS = MAX_MEMBERS * 1_000
MAX_DISCOVERY_PATH_PAIRS = MAX_MEMBERS * (1_000 * 999 // 2)

type SourceKey = Annotated[
    str,
    Field(
        max_length=90,
        pattern=r"^(?:import:[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}|connector:[a-z][a-z0-9-]{0,63})$",
    ),
]
type Count = Annotated[int, Field(strict=True, ge=0, le=MAX_MEMBERS)]
type DiscoveryPathCount = Annotated[int, Field(strict=True, ge=0, le=MAX_DISCOVERY_PATHS)]
type DiscoveryPathPairCount = Annotated[int, Field(strict=True, ge=0, le=MAX_DISCOVERY_PATH_PAIRS)]


class CorpusReportProblem(ValueError):
    """Content-free report failure for Core to map to a bounded API error."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _canonical_utc_milliseconds(value: str) -> bool:
    try:
        instant = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return instant.isoformat(timespec="milliseconds").replace("+00:00", "Z") == value


class ReportPath(DraftValue):
    """One exact retained discovery edge, plus a source root if attested."""

    path_id: Identity
    source_revision_id: Identity
    context_revision_id: Identity
    source_key: SourceKey | None
    route: ReportRoute
    metadata_assertion_status: Literal["retained", "no-external-assertion"]
    report_inspect_status: Literal["allowed", "unassessed"]
    rights_policy_revision_id: Identity | None
    rights_expires_at: (
        Annotated[str, Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$")] | None
    )
    source_copy_availability: Literal["unknown"]

    @model_validator(mode="after")
    def root_matches_direct_route(self) -> Self:
        if self.route == "import-member" and (self.source_key is None or not self.source_key.startswith("import:")):
            raise ValueError("corpus-report-source-root-invalid")
        if self.route == "connector-record" and (
            self.source_key is None or not self.source_key.startswith("connector:")
        ):
            raise ValueError("corpus-report-source-root-invalid")
        retained = self.metadata_assertion_status == "retained"
        if retained != (self.report_inspect_status == "allowed") or retained != (
            self.rights_policy_revision_id is not None
        ):
            raise ValueError("corpus-report-path-rights-invalid")
        if not retained and self.rights_expires_at is not None:
            raise ValueError("corpus-report-path-rights-invalid")
        if self.rights_expires_at is not None and not _canonical_utc_milliseconds(self.rights_expires_at):
            raise ValueError("corpus-report-path-rights-time-invalid")
        return self


class ReportField(DraftValue):
    """A report classification, never a permission or an inferred value."""

    dimension: ReportDimension
    state: ReportState
    value: Annotated[str, Field(min_length=1, max_length=512)] | None
    witness_revision_id: Identity | None

    @model_validator(mode="after")
    def known_has_exact_witness(self) -> Self:
        if self.state == "known":
            if self.value is None or self.witness_revision_id is None:
                raise ValueError("corpus-report-known-witness-required")
            if self.dimension in {"oa", "full-text"} and self.value not in {"yes", "no"}:
                raise ValueError("corpus-report-status-value-invalid")
        elif self.value is not None:
            raise ValueError("corpus-report-missing-value-invalid")
        return self


class CorpusReportMember(DraftValue):
    """One counted current canonical item revision frozen into a snapshot."""

    schema_version: Literal["1.0"] = "1.0"
    contract_version: Literal["1.0.0"] = "1.0.0"
    document_type: Literal["research-observatory-corpus-report-member"] = "research-observatory-corpus-report-member"
    snapshot_id: Identity
    project_id: ProjectIdentity
    item_id: Identity
    item_revision_id: Identity
    work_id: Identity
    work_revision_id: Identity
    membership: ReportMembership
    duplicate_of_item_id: Identity | None
    display_label: Annotated[str, Field(min_length=1, max_length=512)] | None
    paths: Annotated[tuple[ReportPath, ...], Field(min_length=1, max_length=1000)]
    fields: Annotated[tuple[ReportField, ...], Field(min_length=7, max_length=7)]

    @model_validator(mode="after")
    def exact_member_shape(self) -> Self:
        if self.item_id in {self.item_revision_id, self.work_id} or self.duplicate_of_item_id == self.item_id:
            raise ValueError("corpus-report-member-identity-invalid")
        path_ids = tuple(path.path_id for path in self.paths)
        if path_ids != tuple(sorted(set(path_ids))):
            raise ValueError("corpus-report-path-order-invalid")
        if tuple(field.dimension for field in self.fields) != DIMENSIONS:
            raise ValueError("corpus-report-field-set-invalid")
        return self


class SourceContribution(DraftValue):
    source_key: SourceKey
    item_count: Count
    discovery_path_count: DiscoveryPathCount


class SourceOverlap(DraftValue):
    left_source_key: SourceKey
    right_source_key: SourceKey
    item_count: Count
    discovery_path_pair_count: DiscoveryPathPairCount

    @model_validator(mode="after")
    def ordered_pair(self) -> Self:
        if self.left_source_key >= self.right_source_key:
            raise ValueError("corpus-report-source-pair-invalid")
        return self


class RouteContribution(DraftValue):
    route: ReportRoute
    item_count: Count
    discovery_path_count: DiscoveryPathCount


class RouteOverlap(DraftValue):
    left_route: ReportRoute
    right_route: ReportRoute
    item_count: Count
    discovery_path_pair_count: DiscoveryPathPairCount

    @model_validator(mode="after")
    def ordered_pair(self) -> Self:
        if self.left_route >= self.right_route:
            raise ValueError("corpus-report-route-pair-invalid")
        return self


class MembershipCount(DraftValue):
    membership: ReportMembership
    item_count: Count


class CoverageSummary(DraftValue):
    dimension: ReportDimension
    known: Count
    not_reported: Count
    unknown: Count
    unavailable: Count


class ValueBucket(DraftValue):
    value: Annotated[str, Field(min_length=1, max_length=512)]
    item_count: Count


class ValueDistribution(DraftValue):
    dimension: ReportDimension
    buckets: Annotated[tuple[ValueBucket, ...], Field(max_length=MAX_DISTRIBUTION_BUCKETS)]
    other_known_count: Count
    truncated: bool

    @model_validator(mode="after")
    def honest_overflow(self) -> Self:
        if self.dimension not in VALUE_DIMENSIONS or self.truncated != (self.other_known_count > 0):
            raise ValueError("corpus-report-distribution-invalid")
        if len({bucket.value for bucket in self.buckets}) != len(self.buckets):
            raise ValueError("corpus-report-distribution-invalid")
        if any(bucket.item_count == 0 for bucket in self.buckets):
            raise ValueError("corpus-report-distribution-invalid")
        if tuple((bucket.value, bucket.item_count) for bucket in self.buckets) != tuple(
            sorted(((bucket.value, bucket.item_count) for bucket in self.buckets), key=lambda pair: (-pair[1], pair[0]))
        ):
            raise ValueError("corpus-report-distribution-invalid")
        return self


class CorpusReportSnapshot(DraftValue):
    """Immutable summary of one bounded, exact canonical member set."""

    schema_version: Literal["1.0"] = "1.0"
    contract_version: Literal["1.0.0"] = "1.0.0"
    document_type: Literal["research-observatory-corpus-report-snapshot"] = (
        "research-observatory-corpus-report-snapshot"
    )
    snapshot_id: Identity
    project_id: ProjectIdentity
    intent_revision_id: Identity
    protocol_revision_id: Identity
    rule_version: Literal["corpus-report/1.0.0"] = RULE_VERSION
    created_at: Annotated[str, Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$")]
    member_count: Count
    discovery_path_count: DiscoveryPathCount
    members_sha256: Digest
    membership_counts: Annotated[tuple[MembershipCount, ...], Field(min_length=4, max_length=4)]
    duplicate_linked_item_count: Count
    unattributed_item_count: Count
    unattributed_discovery_path_count: DiscoveryPathCount
    source_contributions: Annotated[tuple[SourceContribution, ...], Field(max_length=MAX_SOURCE_ROOTS)]
    source_overlaps: Annotated[tuple[SourceOverlap, ...], Field(max_length=MAX_SOURCE_OVERLAP_PAIRS)]
    route_contributions: Annotated[tuple[RouteContribution, ...], Field(min_length=5, max_length=5)]
    route_overlaps: Annotated[tuple[RouteOverlap, ...], Field(max_length=10)]
    coverage: Annotated[tuple[CoverageSummary, ...], Field(min_length=7, max_length=7)]
    value_distributions: Annotated[tuple[ValueDistribution, ...], Field(min_length=6, max_length=6)]

    @model_validator(mode="after")
    def coherent_summary(self) -> Self:
        if not _canonical_utc_milliseconds(self.created_at):
            raise ValueError("corpus-report-time-invalid")
        if tuple(item.membership for item in self.membership_counts) != MEMBERSHIPS:
            raise ValueError("corpus-report-membership-set-invalid")
        if sum(item.item_count for item in self.membership_counts) != self.member_count:
            raise ValueError("corpus-report-member-count-invalid")
        if (
            self.duplicate_linked_item_count > self.member_count
            or self.unattributed_item_count > self.member_count
            or self.discovery_path_count < self.member_count
            or self.unattributed_discovery_path_count > self.discovery_path_count
            or self.unattributed_discovery_path_count < self.unattributed_item_count
        ):
            raise ValueError("corpus-report-member-count-invalid")
        if tuple(item.route for item in self.route_contributions) != ROUTES:
            raise ValueError("corpus-report-route-set-invalid")
        if tuple(item.dimension for item in self.coverage) != DIMENSIONS:
            raise ValueError("corpus-report-coverage-set-invalid")
        if tuple(item.dimension for item in self.value_distributions) != VALUE_DIMENSIONS:
            raise ValueError("corpus-report-distribution-set-invalid")
        for coverage_item in self.coverage:
            if (
                coverage_item.known + coverage_item.not_reported + coverage_item.unknown + coverage_item.unavailable
                != self.member_count
            ):
                raise ValueError("corpus-report-coverage-count-invalid")
        for distribution in self.value_distributions:
            known = next(entry.known for entry in self.coverage if entry.dimension == distribution.dimension)
            if sum(bucket.item_count for bucket in distribution.buckets) + distribution.other_known_count != known:
                raise ValueError("corpus-report-distribution-count-invalid")
        if tuple(item.source_key for item in self.source_contributions) != tuple(
            sorted({item.source_key for item in self.source_contributions})
        ):
            raise ValueError("corpus-report-source-order-invalid")
        sources = {item.source_key: item.item_count for item in self.source_contributions}
        routes = {item.route: item.item_count for item in self.route_contributions}
        if any(count > self.member_count for count in (*sources.values(), *routes.values())):
            raise ValueError("corpus-report-contribution-count-invalid")
        if (
            sum(item.discovery_path_count for item in self.source_contributions)
            + self.unattributed_discovery_path_count
            != self.discovery_path_count
            or sum(item.discovery_path_count for item in self.route_contributions) != self.discovery_path_count
            or any(
                item.discovery_path_count < item.item_count or item.discovery_path_count > self.discovery_path_count
                for item in self.source_contributions
            )
            or any(
                item.discovery_path_count < item.item_count or item.discovery_path_count > self.discovery_path_count
                for item in self.route_contributions
            )
        ):
            raise ValueError("corpus-report-discovery-path-count-invalid")
        source_pairs = tuple((item.left_source_key, item.right_source_key) for item in self.source_overlaps)
        route_pairs = tuple((item.left_route, item.right_route) for item in self.route_overlaps)
        if source_pairs != tuple(sorted(set(source_pairs))) or route_pairs != tuple(sorted(set(route_pairs))):
            raise ValueError("corpus-report-overlap-order-invalid")
        if any(
            item.item_count == 0
            or item.item_count > min(sources.get(item.left_source_key, 0), sources.get(item.right_source_key, 0))
            or item.discovery_path_pair_count < item.item_count
            for item in self.source_overlaps
        ) or any(
            item.item_count == 0
            or item.item_count > min(routes[item.left_route], routes[item.right_route])
            or item.discovery_path_pair_count < item.item_count
            for item in self.route_overlaps
        ):
            raise ValueError("corpus-report-overlap-count-invalid")
        return self


class CorpusReportFilter(DraftValue):
    """One exact drill predicate; absent dimensions cannot broaden a selector."""

    kind: ReportFilterKind
    membership: ReportMembership | None = None
    source_key: SourceKey | None = None
    left_source_key: SourceKey | None = None
    right_source_key: SourceKey | None = None
    route: ReportRoute | None = None
    left_route: ReportRoute | None = None
    right_route: ReportRoute | None = None
    dimension: ReportDimension | None = None
    state: ReportState | None = None
    value: Annotated[str, Field(min_length=1, max_length=512)] | None = None

    @model_validator(mode="after")
    def exact_selector(self) -> Self:
        present = {
            name
            for name in (
                "membership",
                "source_key",
                "left_source_key",
                "right_source_key",
                "route",
                "left_route",
                "right_route",
                "dimension",
                "state",
                "value",
            )
            if getattr(self, name) is not None
        }
        required = {
            "all": set(),
            "membership": {"membership"},
            "duplicate-linked": set(),
            "unattributed": set(),
            "source": {"source_key"},
            "route": {"route"},
            "source-overlap": {"left_source_key", "right_source_key"},
            "route-overlap": {"left_route", "right_route"},
            "coverage": {"dimension", "state"},
        }[self.kind]
        allowed = required | ({"value"} if self.kind == "coverage" and self.state == "known" else set())
        if not required.issubset(present) or not present.issubset(allowed):
            raise ValueError("corpus-report-filter-invalid")
        if self.kind == "source-overlap" and self.left_source_key >= self.right_source_key:  # type: ignore[operator]
            raise ValueError("corpus-report-filter-invalid")
        if self.kind == "route-overlap" and self.left_route >= self.right_route:  # type: ignore[operator]
            raise ValueError("corpus-report-filter-invalid")
        return self


class CorpusReportDrillPage(DraftValue):
    schema_version: Literal["1.0"] = "1.0"
    contract_version: Literal["1.0.0"] = "1.0.0"
    document_type: Literal["research-observatory-corpus-report-drill-page"] = (
        "research-observatory-corpus-report-drill-page"
    )
    snapshot_id: Identity
    project_id: ProjectIdentity
    filter: CorpusReportFilter
    members: Annotated[tuple[CorpusReportMember, ...], Field(max_length=100)]
    next_cursor: Annotated[str, Field(min_length=1, max_length=512)] | None
    total: Count

    @model_validator(mode="after")
    def bounded_consistent_page(self) -> Self:
        if any(
            (member.snapshot_id, member.project_id) != (self.snapshot_id, self.project_id) for member in self.members
        ):
            raise ValueError("corpus-report-page-scope-invalid")
        item_ids = tuple(member.item_id for member in self.members)
        if item_ids != tuple(sorted(set(item_ids))) or len(self.members) > self.total:
            raise ValueError("corpus-report-page-order-invalid")
        if self.next_cursor is not None and not self.members:
            raise ValueError("corpus-report-page-cursor-invalid")
        if any(not report_member_matches_filter(member, self.filter) for member in self.members):
            raise ValueError("corpus-report-page-filter-invalid")
        return self


def report_member_matches_filter(member: CorpusReportMember, selected: CorpusReportFilter) -> bool:
    """Pure drill predicate; the protected reader still enforces snapshot authority."""

    if selected.kind == "all":
        return True
    if selected.kind == "membership":
        return member.membership == selected.membership
    if selected.kind == "duplicate-linked":
        return member.duplicate_of_item_id is not None
    if selected.kind == "unattributed":
        return any(path.source_key is None for path in member.paths)
    sources = {path.source_key for path in member.paths if path.source_key is not None}
    routes = {path.route for path in member.paths}
    if selected.kind == "source":
        return selected.source_key in sources
    if selected.kind == "route":
        return selected.route in routes
    if selected.kind == "source-overlap":
        return selected.left_source_key in sources and selected.right_source_key in sources
    if selected.kind == "route-overlap":
        return selected.left_route in routes and selected.right_route in routes
    field = next(field for field in member.fields if field.dimension == selected.dimension)
    return field.state == selected.state and (selected.value is None or field.value == selected.value)


def _member_bytes(member: CorpusReportMember) -> bytes:
    document = member.model_dump(mode="json", by_alias=True)
    return (
        json.dumps(document, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    )


class CorpusReportAccumulator:
    """Stream sorted members without retaining research records in memory."""

    def __init__(
        self,
        *,
        snapshot_id: str,
        project_id: str,
        max_distribution_buckets: int = MAX_DISTRIBUTION_BUCKETS,
    ) -> None:
        if not 1 <= max_distribution_buckets <= MAX_DISTRIBUTION_BUCKETS:
            raise CorpusReportProblem("corpus-report-limit")
        self.snapshot_id = snapshot_id
        self.project_id = project_id
        self._max_distribution_buckets = max_distribution_buckets
        self._last_item_id: str | None = None
        self._member_count = 0
        self._discovery_path_count = 0
        self._members_hash = hashlib.sha256()
        self._memberships: Counter[str] = Counter()
        self._duplicate_count = 0
        self._unattributed_count = 0
        self._unattributed_discovery_path_count = 0
        self._sources: Counter[str] = Counter()
        self._source_paths: Counter[str] = Counter()
        self._source_pairs: Counter[tuple[str, str]] = Counter()
        self._source_pair_paths: Counter[tuple[str, str]] = Counter()
        self._routes: Counter[ReportRoute] = Counter()
        self._route_paths: Counter[ReportRoute] = Counter()
        self._route_pairs: Counter[tuple[ReportRoute, ReportRoute]] = Counter()
        self._route_pair_paths: Counter[tuple[ReportRoute, ReportRoute]] = Counter()
        self._coverage: dict[str, Counter[str]] = {dimension: Counter() for dimension in DIMENSIONS}
        self._values: dict[str, Counter[str]] = {dimension: Counter() for dimension in VALUE_DIMENSIONS}

    @property
    def member_count(self) -> int:
        return self._member_count

    def add(self, member: CorpusReportMember) -> None:
        member = CorpusReportMember.model_validate(member)
        if (member.snapshot_id, member.project_id) != (self.snapshot_id, self.project_id):
            raise CorpusReportProblem("corpus-report-scope-invalid")
        if self._last_item_id is not None and member.item_id <= self._last_item_id:
            raise CorpusReportProblem("corpus-report-member-order-invalid")
        if self._member_count >= MAX_MEMBERS:
            raise CorpusReportProblem("corpus-report-limit")
        source_path_counts: Counter[str] = Counter(
            path.source_key for path in member.paths if path.source_key is not None
        )
        route_path_counts: Counter[ReportRoute] = Counter(path.route for path in member.paths)
        sources = tuple(sorted(source_path_counts))
        routes = tuple(sorted(route_path_counts))
        new_source_roots = sum(source not in self._sources for source in sources)
        if len(sources) > MAX_ROOTS_PER_MEMBER or len(self._sources) + new_source_roots > MAX_SOURCE_ROOTS:
            raise CorpusReportProblem("corpus-report-limit")
        pairs = tuple(combinations(sources, 2))
        new_source_pairs = sum(pair not in self._source_pairs for pair in pairs)
        if len(self._source_pairs) + new_source_pairs > MAX_SOURCE_OVERLAP_PAIRS:
            raise CorpusReportProblem("corpus-report-limit")
        # All limit and identity checks precede changes to the running summary.
        self._members_hash.update(_member_bytes(member))
        self._last_item_id = member.item_id
        self._member_count += 1
        self._discovery_path_count += len(member.paths)
        self._memberships[member.membership] += 1
        self._duplicate_count += member.duplicate_of_item_id is not None
        self._unattributed_count += any(path.source_key is None for path in member.paths)
        self._unattributed_discovery_path_count += sum(path.source_key is None for path in member.paths)
        self._sources.update(sources)
        self._source_paths.update(source_path_counts)
        self._source_pairs.update(pairs)
        self._source_pair_paths.update(
            {pair: source_path_counts[pair[0]] * source_path_counts[pair[1]] for pair in pairs}
        )
        self._routes.update(routes)
        self._route_paths.update(route_path_counts)
        route_pairs = tuple(combinations(routes, 2))
        self._route_pairs.update(route_pairs)
        self._route_pair_paths.update(
            {pair: route_path_counts[pair[0]] * route_path_counts[pair[1]] for pair in route_pairs}
        )
        for field in member.fields:
            self._coverage[field.dimension][field.state] += 1
            if field.dimension in self._values and field.state == "known":
                assert field.value is not None
                self._values[field.dimension][field.value] += 1

    def finalize(
        self,
        *,
        intent_revision_id: str,
        protocol_revision_id: str,
        created_at: str,
    ) -> CorpusReportSnapshot:
        distributions: list[ValueDistribution] = []
        for dimension in VALUE_DIMENSIONS:
            all_values = sorted(self._values[dimension].items(), key=lambda item: (-item[1], item[0]))
            kept = all_values[: self._max_distribution_buckets]
            other = sum(count for _, count in all_values[self._max_distribution_buckets :])
            distributions.append(
                ValueDistribution(
                    dimension=dimension,
                    buckets=tuple(ValueBucket(value=value, item_count=count) for value, count in kept),
                    other_known_count=other,
                    truncated=other > 0,
                )
            )
        return CorpusReportSnapshot(
            snapshot_id=self.snapshot_id,
            project_id=self.project_id,
            intent_revision_id=intent_revision_id,
            protocol_revision_id=protocol_revision_id,
            created_at=created_at,
            member_count=self._member_count,
            discovery_path_count=self._discovery_path_count,
            members_sha256=self._members_hash.hexdigest(),
            membership_counts=tuple(
                MembershipCount(membership=membership, item_count=self._memberships[membership])
                for membership in MEMBERSHIPS
            ),
            duplicate_linked_item_count=self._duplicate_count,
            unattributed_item_count=self._unattributed_count,
            unattributed_discovery_path_count=self._unattributed_discovery_path_count,
            source_contributions=tuple(
                SourceContribution(source_key=source, item_count=count, discovery_path_count=self._source_paths[source])
                for source, count in sorted(self._sources.items())
            ),
            source_overlaps=tuple(
                SourceOverlap(
                    left_source_key=left,
                    right_source_key=right,
                    item_count=count,
                    discovery_path_pair_count=self._source_pair_paths[(left, right)],
                )
                for (left, right), count in sorted(self._source_pairs.items())
            ),
            route_contributions=tuple(
                RouteContribution(
                    route=route,
                    item_count=self._routes[route],
                    discovery_path_count=self._route_paths[route],
                )
                for route in ROUTES
            ),
            route_overlaps=tuple(
                RouteOverlap(
                    left_route=left,
                    right_route=right,
                    item_count=count,
                    discovery_path_pair_count=self._route_pair_paths[(left, right)],
                )
                for (left, right), count in sorted(self._route_pairs.items())
            ),
            coverage=tuple(
                CoverageSummary(
                    dimension=dimension,
                    known=self._coverage[dimension]["known"],
                    not_reported=self._coverage[dimension]["not-reported"],
                    unknown=self._coverage[dimension]["unknown"],
                    unavailable=self._coverage[dimension]["unavailable"],
                )
                for dimension in DIMENSIONS
            ),
            value_distributions=tuple(distributions),
        )


def report_member_sha256(member: CorpusReportMember) -> str:
    """Bind one persisted member row to the same canonical stream encoding."""

    return hashlib.sha256(_member_bytes(CorpusReportMember.model_validate(member))).hexdigest()
