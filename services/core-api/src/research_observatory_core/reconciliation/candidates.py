"""Bounded, deterministic duplicate retrieval; scores propose human review only.

This pure module neither mints identities nor mutates canonical membership. Feature
preparation is reusable only for the exact immutable record revision/fingerprint;
authorization and project-local cache ownership remain with the caller.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from itertools import combinations
from typing import Literal

from .contracts import ReconciliationProblem
from .exact import IdentifierAssertion, exact_keys
from .identifiers import NORMALIZER_VERSION

ALGORITHM = "scholarly-duplicate-ranking/1.0.0"
FEATURE_VERSION = "scholarly-duplicate-features/1.0.0"
FIELD_NAMES = ("title", "authors", "year", "venue", "pages", "abstract")
_WEIGHTS = {
    "title": 7000,
    "authors": 1500,
    "year": 800,
    "venue": 400,
    "pages": 200,
    "abstract": 100,
    "identifiers": 2000,
}
_WORDS = re.compile(r"[^\W_]+", re.UNICODE)


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class CandidateConfig:
    minimum_score: int = 8200
    max_records: int = 10000
    max_comparisons: int = 250000
    max_candidates: int = 20000
    max_posting: int = 200
    rare_title_tokens: int = 4

    def __post_init__(self) -> None:
        for name, maximum, minimum in (
            ("minimum_score", 10000, 0),
            ("max_records", 10000, 1),
            ("max_comparisons", 250000, 1),
            ("max_candidates", 20000, 1),
            ("max_posting", 200, 2),
            ("rare_title_tokens", 8, 1),
        ):
            value = getattr(self, name)
            if type(value) is not int or not minimum <= value <= maximum:
                raise ReconciliationProblem("duplicate-configuration-invalid")

    @property
    def fingerprint(self) -> str:
        return _hash([ALGORITHM, FEATURE_VERSION, NORMALIZER_VERSION, _WEIGHTS, asdict(self)])


DEFAULT_CONFIG = CandidateConfig()


@dataclass(frozen=True, slots=True)
class CandidateRecord:
    key: str
    revision: str
    fields: tuple[tuple[str, tuple[str, ...]], ...] = field(repr=False)
    identifiers: tuple[IdentifierAssertion, ...] = field(default=(), repr=False)


@dataclass(frozen=True, slots=True)
class PreparedValue:
    text: str = field(repr=False)
    tokens: frozenset[str] = field(repr=False)


@dataclass(frozen=True, slots=True)
class PreparedRecord:
    key: str
    revision: str
    fingerprint: str
    fields: tuple[tuple[str, tuple[PreparedValue, ...]], ...] = field(repr=False)
    identifiers: frozenset[tuple[str, str]] = field(repr=False)


@dataclass(frozen=True, slots=True)
class FeatureComparison:
    name: str
    state: Literal["available", "not-reported", "disputed"]
    score: int | None
    weight: int
    conflict: bool


@dataclass(frozen=True, slots=True)
class CandidatePair:
    left: str
    right: str
    left_revision: str
    right_revision: str
    left_fingerprint: str
    right_fingerprint: str
    score: int
    features: tuple[FeatureComparison, ...]
    flags: tuple[str, ...]
    configuration_fingerprint: str
    algorithm: str = ALGORITHM
    feature_version: str = FEATURE_VERSION
    identifier_normalizer: str = NORMALIZER_VERSION
    disposition: Literal["human-review-required"] = "human-review-required"


@dataclass(frozen=True, slots=True)
class CandidateRetrieval:
    pairs: tuple[CandidatePair, ...]
    compared_pairs: int
    record_count: int
    configuration_fingerprint: str


def _prepare(value: str, name: str) -> PreparedValue:
    if not isinstance(value, str) or not 1 <= len(value) <= 65536:
        raise ReconciliationProblem("duplicate-feature-limit")
    normalized = "".join(
        char for char in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(char)
    )
    words = tuple(_WORDS.findall(normalized))
    if len(words) > 4096:
        raise ReconciliationProblem("duplicate-feature-limit")
    if name == "authors":
        # Initials and order are weak matching evidence, not person identity.
        words = tuple(word for word in words if len(word) > 1)
    text = " ".join(words)
    if name == "title" and len(text) > 4096:
        raise ReconciliationProblem("duplicate-feature-limit")
    return PreparedValue(text, frozenset(words))


def prepare_record(record: CandidateRecord) -> PreparedRecord:
    if (
        not isinstance(record, CandidateRecord)
        or any(not isinstance(value, str) or not 1 <= len(value) <= 512 for value in (record.key, record.revision))
        or not isinstance(record.fields, tuple)
        or len(record.fields) > len(FIELD_NAMES)
        or not isinstance(record.identifiers, tuple)
        or len(record.identifiers) > 32768
    ):
        raise ReconciliationProblem("duplicate-record-invalid")
    fields: dict[str, tuple[PreparedValue, ...]] = {}
    source_bytes = 0
    for name, values in record.fields:
        if name not in FIELD_NAMES or name in fields or not isinstance(values, tuple) or len(values) > 256:
            raise ReconciliationProblem("duplicate-record-invalid")
        prepared = set()
        for value in values:
            item = _prepare(value, name)
            source_bytes += len(value.encode())
            if source_bytes > 1024 * 1024:
                raise ReconciliationProblem("duplicate-feature-limit")
            if item.text:
                prepared.add(item)
        fields[name] = tuple(sorted(prepared, key=lambda item: item.text))
    identifiers = tuple(IdentifierAssertion.model_validate(item) for item in record.identifiers)
    source_bytes += sum(len(item.observed.encode()) for item in identifiers)
    if source_bytes > 1024 * 1024:
        raise ReconciliationProblem("duplicate-feature-limit")
    return PreparedRecord(
        record.key,
        record.revision,
        candidate_record_fingerprint(record),
        tuple(sorted(fields.items())),
        exact_keys(identifiers),
    )


def candidate_record_fingerprint(record: CandidateRecord) -> str:
    """Bind prepared features to the exact immutable, already validated input."""
    return _hash(
        [
            FEATURE_VERSION,
            NORMALIZER_VERSION,
            record.key,
            record.revision,
            record.fields,
            [
                IdentifierAssertion.model_validate(item).model_dump(mode="json", by_alias=True)
                for item in record.identifiers
            ],
        ]
    )


def _dice(left: frozenset[str], right: frozenset[str]) -> int:
    return 20000 * len(left & right) // (len(left) + len(right)) if left and right else 0


def _similarity(name: str, left: PreparedValue, right: PreparedValue) -> int:
    if left.text == right.text:
        return 10000
    if name == "year":
        if re.fullmatch(r"[0-9]{4}", left.text) and re.fullmatch(r"[0-9]{4}", right.text):
            return 5000 if abs(int(left.text) - int(right.text)) == 1 else 0
        return 0
    score = _dice(left.tokens, right.tokens)
    if name == "title":
        matcher = SequenceMatcher(None, left.text, right.text, autojunk=False)
        characters = (
            20000 * sum(block.size for block in matcher.get_matching_blocks()) // (len(left.text) + len(right.text))
        )
        score = max(score, characters)
    return score


def compare_records(
    left: PreparedRecord, right: PreparedRecord, *, config: CandidateConfig = DEFAULT_CONFIG
) -> CandidatePair:
    if left.key == right.key:
        raise ReconciliationProblem("duplicate-record-identity-conflict")
    if left.key > right.key:
        left, right = right, left
    lfields, rfields = dict(left.fields), dict(right.fields)
    features = []
    flags: set[str] = set()
    for name in FIELD_NAMES:
        lvalues, rvalues = lfields.get(name, ()), rfields.get(name, ())
        if len(lvalues) * len(rvalues) > 4096:
            raise ReconciliationProblem("duplicate-feature-comparison-limit")
        disputed = len(lvalues) > 1 or len(rvalues) > 1
        score = max((_similarity(name, a, b) for a in lvalues for b in rvalues), default=None)
        state: Literal["available", "not-reported", "disputed"] = (
            "disputed" if disputed else "available" if score is not None else "not-reported"
        )
        conflict = disputed or (score is not None and score < 10000)
        features.append(FeatureComparison(name, state, score, _WEIGHTS[name], conflict))
        if disputed:
            flags.add("competing-source-fields")
        if name == "year" and score == 0:
            flags.add("year-disagreement")
    lschemes = {scheme for scheme, _ in left.identifiers}
    rschemes = {scheme for scheme, _ in right.identifiers}
    conflicts = any(
        {v for s, v in left.identifiers if s == scheme} != {v for s, v in right.identifiers if s == scheme}
        for scheme in lschemes & rschemes
    )
    if conflicts:
        flags.add("conflicting-identifiers")
    identifier_score = 10000 if left.identifiers & right.identifiers else 0 if lschemes & rschemes else None
    features.append(
        FeatureComparison(
            "identifiers",
            "disputed" if conflicts else "available" if identifier_score is not None else "not-reported",
            identifier_score,
            _WEIGHTS["identifiers"],
            conflicts,
        )
    )
    denominator = sum(item.weight for item in features if item.score is not None)
    score = (
        sum(item.score * item.weight for item in features if item.score is not None) // denominator
        if denominator
        else 0
    )
    return CandidatePair(
        left.key,
        right.key,
        left.revision,
        right.revision,
        left.fingerprint,
        right.fingerprint,
        score,
        tuple(features),
        tuple(sorted(flags)),
        config.fingerprint,
    )


def generate_candidates(
    records: tuple[CandidateRecord, ...],
    *,
    config: CandidateConfig = DEFAULT_CONFIG,
    checkpoint: Callable[[], None] | None = None,
) -> CandidateRetrieval:
    """Prepare immutable inputs, then use the same retrieval path as the local cache."""
    if len(records) > config.max_records:
        raise ReconciliationProblem("duplicate-record-limit")
    prepared = []
    for record in records:
        if checkpoint is not None:
            checkpoint()
        prepared.append(prepare_record(record))
    return generate_prepared_candidates(tuple(prepared), config=config, checkpoint=checkpoint)


def generate_prepared_candidates(
    records: tuple[PreparedRecord, ...],
    *,
    config: CandidateConfig = DEFAULT_CONFIG,
    checkpoint: Callable[[], None] | None = None,
) -> CandidateRetrieval:
    """Inverted title/identifier blocking with a fail-closed comparison budget.

    Common individual words do not form blocks. Exact full titles/identifiers
    remain blocks; an oversized exact group requires a smaller explicit batch.
    No labels, source ID patterns, or benchmark mappings influence retrieval.
    """
    if len(records) > config.max_records:
        raise ReconciliationProblem("duplicate-record-limit")
    for record in records:
        _validate_prepared_record(record)
    prepared = tuple(sorted(records, key=lambda item: item.key))
    if len({item.key for item in prepared}) != len(prepared):
        raise ReconciliationProblem("duplicate-record-identity-conflict")
    postings: dict[tuple[str, str], set[int]] = defaultdict(set)
    tokens: list[frozenset[str]] = []
    for index, record in enumerate(prepared):
        if checkpoint is not None:
            checkpoint()
        title_values = dict(record.fields).get("title", ())
        words = frozenset(word for value in title_values for word in value.tokens if len(word) > 1)
        tokens.append(words)
        for word in words:
            postings[("token", word)].add(index)
        for value in title_values:
            postings[("title", value.text)].add(index)
        for scheme, identifier_value in record.identifiers:
            postings[("identifier", scheme + ":" + identifier_value)].add(index)
    pair_keys: set[tuple[int, int]] = set()

    def add(indices: set[int], anchor: int | None = None) -> None:
        if len(indices) > config.max_posting:
            raise ReconciliationProblem("duplicate-block-limit")
        selected = (
            combinations(sorted(indices), 2)
            if anchor is None
            else ((min(anchor, other), max(anchor, other)) for other in indices if other != anchor)
        )
        for pair in selected:
            pair_keys.add(pair)
            if len(pair_keys) > config.max_comparisons:
                raise ReconciliationProblem("duplicate-comparison-limit")

    for (kind, _), indices in postings.items():
        if kind != "token":
            add(indices)
    for index, words in enumerate(tokens):
        rare = sorted(
            (word for word in words if len(postings[("token", word)]) <= config.max_posting),
            key=lambda word: (len(postings[("token", word)]), word),
        )[: config.rare_title_tokens]
        for word in rare:
            add(postings[("token", word)], index)
    pairs = []
    for left, right in sorted(pair_keys):
        if checkpoint is not None:
            checkpoint()
        candidate = compare_records(prepared[left], prepared[right], config=config)
        if candidate.score >= config.minimum_score:
            pairs.append(candidate)
            if len(pairs) > config.max_candidates:
                raise ReconciliationProblem("duplicate-candidate-limit")
    return CandidateRetrieval(
        tuple(sorted(pairs, key=lambda item: (-item.score, item.left, item.right))),
        len(pair_keys),
        len(prepared),
        config.fingerprint,
    )


def _validate_prepared_record(record: PreparedRecord) -> None:
    if (
        not isinstance(record, PreparedRecord)
        or any(not isinstance(value, str) or not 1 <= len(value) <= 512 for value in (record.key, record.revision))
        or re.fullmatch(r"[0-9a-f]{64}", record.fingerprint) is None
        or not isinstance(record.fields, tuple)
        or len(record.fields) > len(FIELD_NAMES)
        or not isinstance(record.identifiers, frozenset)
        or len(record.identifiers) > 32768
    ):
        raise ReconciliationProblem("duplicate-prepared-record-invalid")
    seen = set()
    for name, values in record.fields:
        if name not in FIELD_NAMES or name in seen or not isinstance(values, tuple) or len(values) > 256:
            raise ReconciliationProblem("duplicate-prepared-record-invalid")
        seen.add(name)
        for value in values:
            if (
                not isinstance(value, PreparedValue)
                or not isinstance(value.text, str)
                or not 1 <= len(value.text) <= (4096 if name == "title" else 524288)
                or not isinstance(value.tokens, frozenset)
                or len(value.tokens) > 4096
                or value.tokens != frozenset(value.text.split())
            ):
                raise ReconciliationProblem("duplicate-prepared-record-invalid")
    if any(
        not isinstance(item, tuple)
        or len(item) != 2
        or any(not isinstance(part, str) or not 1 <= len(part) <= 65536 for part in item)
        for item in record.identifiers
    ):
        raise ReconciliationProblem("duplicate-prepared-record-invalid")
