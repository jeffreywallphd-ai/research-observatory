"""Core validation of staged output; no canonical repository or write port."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import NoReturn, cast

from pydantic import TypeAdapter

from ..ports.corpus import CorpusActor
from ..ports.parsing import AuthenticatedParseDelivery, DocumentParserPort, ParseProblem, ProtectedParseSourcePort
from .contracts import ParserDescriptor, RawParserArtifact
from .normalization import MAX_IR_BYTES
from .requests import FailureCode, ParseCancelled, ParseFailure, ParseRequest, ParseResult, ParseSuccess

_RESULT: TypeAdapter[ParseResult] = TypeAdapter(ParseResult)
_FAILURE_CODES = frozenset(
    {
        "parser-failed",
        "parser-timeout",
        "parser-memory-limit",
        "parser-assets-unavailable",
        "parser-runtime-unavailable",
        "parse-output-invalid",
        "parse-producer-mismatch",
        "parse-source-denied",
        "parse-delivery-denied",
    }
)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("parse-wire-duplicate-field")
        result[key] = value
    return result


def _nonfinite(_value: str) -> NoReturn:
    raise ValueError("parse-wire-nonfinite")


def decode_delivery(request: ParseRequest, delivery: AuthenticatedParseDelivery) -> ParseResult:
    bad_request = False
    try:
        request = ParseRequest.model_validate(request)
    except ValueError:
        bad_request = True
    if bad_request:
        raise ParseProblem("parse-request-invalid")
    bad_producer = False
    receipts: tuple[RawParserArtifact, ...] = ()
    try:
        producer = ParserDescriptor.model_validate(delivery.producer)
        receipts = tuple(RawParserArtifact.model_validate(item) for item in delivery.artifact_receipts)
        bad_producer = (
            producer != request.binding.producer
            or delivery.job_id != request.binding.attempt.job_id
            or delivery.attempt_id != request.binding.attempt.attempt_id
            or len({item.stage_id for item in receipts}) != len(receipts)
        )
    except ValueError, TypeError, AttributeError:
        bad_producer = True
    if bad_producer:
        raise ParseProblem("parse-producer-mismatch")
    if type(delivery.wire) is not bytes or len(delivery.wire) > MAX_IR_BYTES:
        raise ParseProblem("parse-output-invalid")
    result = None
    try:
        value = json.loads(
            delivery.wire.decode("utf-8", errors="strict"), object_pairs_hook=_unique_object, parse_constant=_nonfinite
        )
        result = _RESULT.validate_python(value)
        if result.binding != request.binding:
            result = None
        elif isinstance(result, ParseSuccess):
            expected_disposition = "inspection-only" if request.selection.outcome == "inspection-only" else "staged"
            if result.ir.disposition != expected_disposition or {
                item.stage_id: item for item in result.ir.raw_artifacts
            } != {item.stage_id: item for item in receipts}:
                result = None
        elif receipts:
            result = None
    except ValueError, TypeError, RecursionError, UnicodeError:
        result = None
    # Raise outside the handler: a private ValidationError input or decoder
    # exception must not survive as __context__, even with suppressed display.
    if result is None:
        raise ParseProblem("parse-output-invalid")
    return result


def stage_parse(
    request: ParseRequest,
    parser: DocumentParserPort,
    sources: ProtectedParseSourcePort,
    *,
    actor: CorpusActor,
    cancelled: Callable[[], bool],
) -> ParseResult:
    invalid = False
    try:
        request = ParseRequest.model_validate(request)
    except ValueError:
        invalid = True
    if invalid:
        raise ParseProblem("parse-request-invalid")

    def cancellation() -> ParseCancelled:
        return ParseCancelled(schema_version="1.0", kind="cancelled", binding=request.binding, code="cancelled")

    stopped = False

    def is_cancelled() -> bool:
        nonlocal stopped
        if not stopped:
            try:
                observation = cancelled()
                stopped = type(observation) is not bool or observation
            except Exception:
                stopped = True
        return stopped

    if is_cancelled():
        return cancellation()
    result: ParseResult | None = None
    failure: FailureCode = "parser-failed"
    try:
        with sources.read_source(request.binding.source, actor=actor, cancelled=is_cancelled) as stream:
            if is_cancelled():
                return cancellation()
            delivery = parser.parse(request, stream, cancelled=is_cancelled)
        if is_cancelled():
            return cancellation()
        result = decode_delivery(request, delivery)
    except ParseProblem as problem:
        failure = cast(FailureCode, problem.code) if problem.code in _FAILURE_CODES else "parser-failed"
    except Exception:
        failure = "parser-failed"
    if is_cancelled():
        return cancellation()
    if result is None:
        return ParseFailure(schema_version="1.0", kind="failure", binding=request.binding, code=failure)
    if isinstance(result, ParseSuccess):
        success = result
        delivered = None
        try:

            def publish() -> ParseResult:
                return cancellation() if is_cancelled() else success

            delivered = sources.deliver(request.binding.source, actor=actor, action=publish)
        except Exception:
            pass
        if delivered is None:
            return ParseFailure(
                schema_version="1.0", kind="failure", binding=request.binding, code="parse-delivery-denied"
            )
        return delivered
    return result
