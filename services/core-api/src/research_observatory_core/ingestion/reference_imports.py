"""Bounded reference parsers over caller-authorized binary streams.

Records are provisional until the iterator reaches verified EOF. No filesystem,
network, logging, execution, rights grant, or canonical persistence lives here.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

PARSER_VERSION = "local-reference-imports/1.0.0"
NORMALIZATION_VERSION = "local-reference-candidates/1.0.0"
FORMATS = frozenset({"ris", "bibtex", "csl-json", "doi-list", "csv"})
_BYTES = tuple(bytes([value]) for value in range(256))
_SPACE = b" \t\r\n"
_RIS_TAG = re.compile(r"^([A-Z0-9]{2})  - ?(.*)$")
_BIB_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_:.+/-]*")
_BIB_ATOM = re.compile(r'[^\s,#{}()"]+')
_DOI_WRAPPER = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
_DOI = re.compile(r"10\.[0-9]{4,}/[^\s\x00-\x1f\x7f]+\Z")


class BinarySource(Protocol):
    def read(self, size: int = -1) -> bytes: ...


class ImportProblem(RuntimeError):
    """Content-free terminal failure; already yielded records remain provisional."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ImportSource:
    filename: str
    sha256: str
    encoding: str = "utf-8"

    def __post_init__(self) -> None:
        if (
            not isinstance(self.filename, str)
            or not self.filename.strip()
            or len(self.filename) > 255
            or any(char in self.filename for char in "/\\:")
            or any(ord(char) < 32 or ord(char) == 127 for char in self.filename)
            or self.filename in {".", ".."}
        ):
            raise ValueError("source-name-must-be-a-basename")
        if not isinstance(self.sha256, str) or re.fullmatch(r"[0-9a-f]{64}", self.sha256) is None:
            raise ValueError("invalid-source-digest")
        if self.encoding not in {"utf-8", "cp1252"}:
            raise ValueError("unsupported-encoding")


@dataclass(frozen=True, slots=True)
class ImportLimits:
    max_source_bytes: int = 256 * 1024 * 1024
    max_record_bytes: int = 1024 * 1024
    max_field_bytes: int = 64 * 1024
    max_records: int = 200000
    max_fields: int = 256
    max_depth: int = 64
    max_macros: int = 256
    max_seconds: float = 120.0

    def __post_init__(self) -> None:
        caps = {
            "max_source_bytes": 2 * 1024 * 1024 * 1024,
            "max_record_bytes": 16 * 1024 * 1024,
            "max_field_bytes": 64 * 1024,
            "max_records": 10000000,
            "max_fields": 4096,
            "max_depth": 128,
            "max_macros": 1024,
        }
        if any(type(getattr(self, key)) is not int or not 0 < getattr(self, key) <= cap for key, cap in caps.items()):
            raise ValueError("invalid-import-limit")
        if isinstance(self.max_seconds, bool) or not 0 < self.max_seconds <= 3600:
            raise ValueError("invalid-import-deadline")


@dataclass(frozen=True, slots=True)
class RawField:
    name: str
    raw_value: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FieldCandidate:
    name: str
    value: str
    source_field_index: int


@dataclass(frozen=True, slots=True)
class ImportRecord:
    source: ImportSource
    format_name: str
    ordinal: int
    byte_start: int
    byte_end: int
    line_start: int
    line_end: int
    raw_sha256: str
    raw_bytes: bytes | None
    kind: str
    status: str
    fields: tuple[RawField, ...]
    candidates: tuple[FieldCandidate, ...]
    warnings: tuple[str, ...]

    @property
    def record_key(self) -> str:
        identity = [
            "import-record-key/1",
            self.ordinal,
            self.byte_start,
            self.byte_end,
            self.line_start,
            self.line_end,
            self.raw_sha256,
        ]
        return hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode("ascii")).hexdigest()

    def to_document(self) -> dict[str, Any]:
        return {
            "schemaVersion": "1.0",
            "parserVersion": PARSER_VERSION,
            "source": {
                "filename": self.source.filename,
                "sha256": self.source.sha256,
                "encoding": self.source.encoding,
            },
            "format": self.format_name,
            "ordinal": self.ordinal,
            "recordKey": self.record_key,
            "location": {
                "byteStart": self.byte_start,
                "byteEnd": self.byte_end,
                "lineStart": self.line_start,
                "lineEnd": self.line_end,
            },
            "rawSha256": self.raw_sha256,
            "rawBase64": base64.b64encode(self.raw_bytes).decode("ascii") if self.raw_bytes is not None else None,
            "kind": self.kind,
            "status": self.status,
            "fields": [
                {"name": item.name, "rawValue": item.raw_value, "warnings": list(item.warnings)} for item in self.fields
            ],
            "candidates": [
                {
                    "name": item.name,
                    "value": item.value,
                    "sourceFieldIndex": item.source_field_index,
                    "normalizationVersion": NORMALIZATION_VERSION,
                    "confidence": {"kind": "unknown"},
                }
                for item in self.candidates
            ],
            "warnings": list(self.warnings),
            "mappingDecision": None,
        }


class _Cursor:
    def __init__(self, owner: ImportSession):
        self.owner = owner
        self.buffer = b""
        self.index = 0
        self.offset = 0
        self.line = 1
        self.previous_cr = False
        self.digest = hashlib.sha256()
        self.received = 0
        self.eof = False

    def prefix(self, size: int = 1) -> bytes:
        while len(self.buffer) - self.index < size and not self.eof:
            self.owner._checkpoint()
            try:
                chunk = self.owner.stream.read(8192)
            except OSError, RuntimeError, ValueError:
                raise ImportProblem("source-unavailable") from None
            if not isinstance(chunk, bytes) or len(chunk) > 8192:
                raise ImportProblem("invalid-source-stream")
            if not chunk:
                self.eof = True
                break
            self.received += len(chunk)
            if self.received > self.owner.limits.max_source_bytes:
                raise ImportProblem("source-limit")
            self.digest.update(chunk)
            self.buffer = self.buffer[self.index :] + chunk
            self.index = 0
        return self.buffer[self.index : self.index + size]

    def peek(self) -> int | None:
        prefix = self.prefix()
        return prefix[0] if prefix else None

    def take(self, frame: _Frame | None = None) -> int:
        value = self.peek()
        if value is None:
            raise ImportProblem("unexpected-eof")
        if frame is not None:
            frame.add(value, self.line - int(value == 10 and self.previous_cr))
        self.index += 1
        self.offset += 1
        if value == 13 or (value == 10 and not self.previous_cr):
            self.line += 1
        self.previous_cr = value == 13
        if self.offset % 2048 == 0:
            self.owner._checkpoint()
        return value

    def whitespace(self) -> None:
        while (value := self.peek()) is not None and value in _SPACE:
            self.take()


@dataclass(slots=True)
class _Frame:
    start: int
    line: int
    limit: int
    buffer: bytearray = field(default_factory=bytearray)
    digest: Any = field(default_factory=hashlib.sha256)
    size: int = 0
    end_line: int = 1
    warnings: set[str] = field(default_factory=set)

    def add(self, value: int, line: int) -> None:
        self.digest.update(_BYTES[value])
        self.size += 1
        self.end_line = line
        if self.size <= self.limit:
            self.buffer.append(value)
        else:
            self.warnings.add("record-limit")


def _line(cursor: _Cursor, frame: _Frame) -> None:
    while cursor.peek() is not None:
        value = cursor.take(frame)
        if value in (10, 13):
            if value == 13 and cursor.peek() == 10:
                cursor.take(frame)
            break


def _doi(value: str) -> str | None:
    value = _DOI_WRAPPER.sub("", value.strip()).casefold()
    return value if _DOI.fullmatch(value) else None


class ImportSession:
    """One-shot preview parse. Caller retains ownership of stream and rights.

    `complete` means verified traversal, not an error-free or committed import.
    A complete report can contain malformed records; consumers must display them.
    """

    def __init__(
        self,
        stream: BinarySource,
        source: ImportSource,
        format_name: str,
        *,
        limits: ImportLimits | None = None,
        cancelled: Callable[[], bool] | None = None,
        clock: Callable[[], float] = time.monotonic,
        delimiter: str = ",",
    ):
        if format_name not in FORMATS or delimiter not in {",", ";", "\t"}:
            raise ValueError("unsupported-import-format")
        if format_name == "csl-json" and source.encoding != "utf-8":
            raise ValueError("csl-json-requires-utf-8")
        self.stream, self.source, self.format_name = stream, source, format_name
        self.limits = limits or ImportLimits()
        self.cancelled = cancelled or (lambda: False)
        self.clock, self.delimiter = clock, delimiter
        self.complete = False
        self.failure_code: str | None = None
        self.record_count = 0
        self.error_count = 0
        self._started = False
        self._deadline = 0.0
        self._columns: list[str] | None = None
        self._macros: dict[str, str | None] = {}

    def _checkpoint(self) -> None:
        if self.cancelled():
            raise ImportProblem("cancelled")
        if self.clock() >= self._deadline:
            raise ImportProblem("timeout")

    def records(self) -> Iterator[ImportRecord]:
        if self._started:
            raise ImportProblem("session-already-consumed")
        self._started = True
        self._deadline = self.clock() + self.limits.max_seconds
        cursor = _Cursor(self)
        try:
            prefix = cursor.prefix(4)
            if prefix[:2] in {b"\xff\xfe", b"\xfe\xff"} or prefix == b"\x00\x00\xfe\xff":
                raise ImportProblem("unsupported-encoding")
            if prefix[:3] == b"\xef\xbb\xbf" and self.source.encoding == "utf-8":
                for _ in range(3):
                    cursor.take()
            for frame in self._frames(cursor):
                self._checkpoint()
                if self.record_count >= self.limits.max_records:
                    raise ImportProblem("record-count-limit")
                self.record_count += 1
                record = self._record(frame)
                self.error_count += int(record.status == "malformed")
                yield record
            self._checkpoint()
            if cursor.peek() is not None or cursor.digest.hexdigest() != self.source.sha256:
                raise ImportProblem("source-digest-mismatch")
            self.complete = True
        except ImportProblem as problem:
            self.failure_code = problem.code
            raise

    def _new_frame(self, cursor: _Cursor) -> _Frame:
        return _Frame(cursor.offset, cursor.line, self.limits.max_record_bytes)

    def _frames(self, cursor: _Cursor) -> Iterator[_Frame]:
        if self.format_name == "ris":
            yield from self._ris_frames(cursor)
        elif self.format_name == "csv":
            yield from self._csv_frames(cursor)
        elif self.format_name == "csl-json":
            yield from self._json_frames(cursor)
        elif self.format_name == "bibtex":
            yield from self._bib_frames(cursor)
        else:
            while cursor.peek() is not None:
                frame = self._new_frame(cursor)
                _line(cursor, frame)
                if frame.buffer.strip() or frame.warnings:
                    yield frame

    def _ris_frames(self, cursor: _Cursor) -> Iterator[_Frame]:
        frame: _Frame | None = None
        while cursor.peek() is not None:
            prefix = cursor.prefix(5)
            if prefix == b"TY  -" and frame is not None:
                frame.warnings.add("missing-ris-end")
                yield frame
                frame = None
            if frame is None:
                if cursor.peek() in (10, 13):
                    cursor.take()
                    continue
                frame = self._new_frame(cursor)
            _line(cursor, frame)
            if not frame.buffer.strip() and not frame.warnings:
                frame = None
                continue
            if prefix == b"ER  -":
                yield frame
                frame = None
        if frame is not None:
            frame.warnings.add("missing-ris-end")
            yield frame

    def _csv_frames(self, cursor: _Cursor) -> Iterator[_Frame]:
        while cursor.peek() is not None:
            frame = self._new_frame(cursor)
            quoted, at_start = False, True
            columns = 1
            while cursor.peek() is not None:
                value = cursor.take(frame)
                if value == 34 and (quoted or at_start):
                    if quoted and cursor.peek() == 34:
                        cursor.take(frame)
                    else:
                        quoted = not quoted
                    at_start = False
                elif not quoted and value in (10, 13):
                    if value == 13 and cursor.peek() == 10:
                        cursor.take(frame)
                    break
                elif not quoted:
                    at_start = value == ord(self.delimiter)
                    if at_start:
                        columns += 1
                        if columns > self.limits.max_fields:
                            frame.warnings.add("field-count-limit")
            if quoted:
                frame.warnings.add("unterminated-record")
            if frame.buffer.strip() or frame.warnings:
                yield frame

    def _json_frames(self, cursor: _Cursor) -> Iterator[_Frame]:
        cursor.whitespace()
        if cursor.peek() != 91:
            frame = self._new_frame(cursor)
            while cursor.peek() is not None:
                cursor.take(frame)
            frame.warnings.add("csl-array-required")
            yield frame
            return
        cursor.take()
        needs_value = False
        while True:
            cursor.whitespace()
            if cursor.peek() == 93 and not needs_value:
                cursor.take()
                break
            frame = self._new_frame(cursor)
            depth, quoted, escaped = 0, False, False
            while cursor.peek() is not None:
                value = cursor.peek()
                if not quoted and depth == 0 and value in (44, 93):
                    break
                value = cursor.take(frame)
                if quoted:
                    if escaped:
                        escaped = False
                    elif value == 92:
                        escaped = True
                    elif value == 34:
                        quoted = False
                elif value == 34:
                    quoted = True
                elif value in (91, 123):
                    depth += 1
                    if depth > self.limits.max_depth:
                        frame.warnings.add("nesting-limit")
                elif value in (93, 125):
                    depth -= 1
                    if depth < 0:
                        frame.warnings.add("invalid-json")
                        depth = 0
            if cursor.peek() is None:
                frame.warnings.add("unterminated-record")
                yield frame
                return
            if frame.size == 0:
                frame.warnings.add("missing-json-record")
            yield frame
            if cursor.take() == 93:
                break
            needs_value = True
        cursor.whitespace()
        if cursor.peek() is not None:
            frame = self._new_frame(cursor)
            while cursor.peek() is not None:
                cursor.take(frame)
            frame.warnings.add("trailing-json-content")
            yield frame

    def _bib_frames(self, cursor: _Cursor) -> Iterator[_Frame]:
        while True:
            cursor.whitespace()
            if cursor.peek() is None:
                return
            frame = self._new_frame(cursor)
            if cursor.peek() != 64:
                while cursor.peek() not in (None, 64):
                    cursor.take(frame)
                frame.warnings.add("bibtex-comment")
                yield frame
                continue
            cursor.take(frame)
            while (value := cursor.peek()) is not None and (chr(value).isascii() and chr(value).isalpha()):
                cursor.take(frame)
            while (value := cursor.peek()) is not None and value in _SPACE:
                cursor.take(frame)
            if cursor.peek() not in (123, 40):
                while cursor.peek() not in (None, 64):
                    cursor.take(frame)
                frame.warnings.add("invalid-bibtex")
                yield frame
                continue
            opening = cursor.take(frame)
            closing = 125 if opening == 123 else 41
            depth, quoted, escaped = 0, False, False
            comment = bytes(frame.buffer).lstrip().lower().startswith(b"@comment")
            closed = False
            while cursor.peek() is not None:
                value = cursor.take(frame)
                if escaped:
                    escaped = False
                    continue
                if value == 92:
                    escaped = True
                    continue
                if value == 34 and depth == 0 and not comment:
                    quoted = not quoted
                elif value == 123:
                    depth += 1
                    if depth > self.limits.max_depth:
                        frame.warnings.add("nesting-limit")
                elif value == closing and depth == 0 and not quoted:
                    closed = True
                    break
                elif value == 125 and depth > 0:
                    depth -= 1
            if not closed:
                frame.warnings.add("unterminated-record")
            yield frame

    def _record(self, frame: _Frame) -> ImportRecord:
        fields: list[RawField] = []
        candidates: list[FieldCandidate] = []
        warnings = set(frame.warnings)
        kind = "header" if self.format_name == "csv" and self.record_count == 1 else "record"
        status = "parsed"
        raw = bytes(frame.buffer) if frame.size <= frame.limit else None
        definitions: dict[str, str | None] = {}
        try:
            if warnings - {"bibtex-comment"}:
                raise ImportProblem("malformed-frame")
            text = bytes(frame.buffer).decode(self.source.encoding, errors="strict")
            if self.format_name == "ris":
                decoded = self._ris(text, warnings)
            elif self.format_name == "csv":
                kind, decoded = self._csv(text, warnings)
            elif self.format_name == "csl-json":
                decoded = self._csl(text, warnings)
            elif self.format_name == "bibtex":
                kind, decoded, definitions = self._bib(text, warnings)
            else:
                decoded = [(RawField("DOI", text.rstrip("\r\n")), text.strip())]
                if _doi(text) is None:
                    raise ImportProblem("invalid-doi")
            if len(decoded) > self.limits.max_fields:
                raise ImportProblem("field-count-limit")
            names: set[str] = set()
            for item, value in decoded:
                if any(
                    len(value.encode(self.source.encoding)) > self.limits.max_field_bytes
                    for value in (item.name, item.raw_value)
                ):
                    raise ImportProblem("field-limit")
                field_warnings = set(item.warnings)
                if item.name.casefold() in names:
                    field_warnings.add("duplicate-field")
                names.add(item.name.casefold())
                candidate = self._candidate(item.name, value, len(fields), field_warnings)
                fields.append(RawField(item.name, item.raw_value, tuple(sorted(field_warnings))))
                warnings.update(field_warnings)
                if candidate is not None and kind == "record":
                    candidates.append(candidate)
            self._macros.update(definitions)
        except UnicodeError:
            status = "malformed"
            warnings.add("invalid-encoding")
        except ValueError, csv.Error, RecursionError:
            status = "malformed"
            warnings.add("invalid-syntax")
        except ImportProblem as problem:
            if problem.code in {"cancelled", "timeout"}:
                raise
            status = "malformed"
            if problem.code != "malformed-frame":
                warnings.add(problem.code)
        if status == "malformed":
            candidates.clear()
        return ImportRecord(
            self.source,
            self.format_name,
            self.record_count,
            frame.start,
            frame.start + frame.size,
            frame.line,
            max(frame.line, frame.end_line),
            frame.digest.hexdigest(),
            raw,
            kind,
            status,
            tuple(fields),
            tuple(candidates),
            tuple(sorted(warnings)),
        )

    def _candidate(self, name: str, value: object, index: int, warnings: set[str]) -> FieldCandidate | None:
        key = name.casefold()
        aliases = {
            "ti": "title",
            "t1": "title",
            "do": "doi",
            "py": "year",
            "y1": "year",
            "au": "author",
            "a1": "author",
            "jo": "container",
            "jf": "container",
            "journal": "container",
            "container-title": "container",
        }
        key = aliases.get(key, key)
        if key not in {"title", "doi", "year", "author", "container"} or not isinstance(value, str):
            return None
        normalized = " ".join(value.split())
        if key == "doi":
            doi = _doi(value)
            if doi is None:
                warnings.add("invalid-doi")
                return None
            normalized = doi
        if any(ord(char) < 32 or ord(char) == 127 for char in normalized):
            warnings.add("control-character")
            return None
        if len(normalized.encode("utf-8")) > self.limits.max_field_bytes:
            warnings.add("candidate-limit")
            return None
        return FieldCandidate(key, normalized, index) if normalized else None

    def _ris(self, text: str, warnings: set[str]) -> list[tuple[RawField, object]]:
        parsed: list[tuple[RawField, object]] = []
        for line in text.splitlines():
            self._checkpoint()
            match = _RIS_TAG.match(line)
            if match:
                parsed.append((RawField(match[1], match[2]), match[2]))
                if len(parsed) > self.limits.max_fields:
                    raise ImportProblem("field-count-limit")
            elif line[:1].isspace() and parsed:
                old, _ = parsed[-1]
                value = old.raw_value + "\n" + line
                parsed[-1] = (RawField(old.name, value), value)
            elif line.strip():
                raise ImportProblem("invalid-ris-line")
        if not parsed or parsed[0][0].name != "TY" or parsed[-1][0].name != "ER":
            raise ImportProblem("invalid-ris-boundary")
        return parsed

    def _csv(self, text: str, warnings: set[str]) -> tuple[str, list[tuple[RawField, object]]]:
        rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=self.delimiter, strict=True))
        if len(rows) != 1:
            raise ImportProblem("invalid-csv-record")
        values = rows[0]

        def field(name: str, value: str) -> RawField:
            active = value.lstrip().startswith(("=", "+", "-", "@")) or (value and ord(value[0]) < 32)
            return RawField(name, value, ("formula-like-cell",) if active else ())

        if any(field("", value).warnings for value in values):
            warnings.add("formula-like-cell")
        if self.record_count == 1:
            if not values or len(values) > self.limits.max_fields or any(not value.strip() for value in values):
                raise ImportProblem("invalid-csv-header")
            if any(len(value.encode(self.source.encoding)) > self.limits.max_field_bytes for value in values):
                raise ImportProblem("field-limit")
            self._columns = values
            return "header", [(field(value, value), value) for value in values]
        if self._columns is None:
            raise ImportProblem("csv-header-unavailable")
        if len(values) != len(self._columns):
            raise ImportProblem("csv-column-count")
        return "record", [(field(name, value), value) for name, value in zip(self._columns, values, strict=True)]

    def _csl(self, text: str, warnings: set[str]) -> list[tuple[RawField, object]]:
        def reject_constant(_value: str) -> None:
            raise ValueError("invalid-json-constant")

        decoder = json.JSONDecoder(parse_constant=reject_constant)
        index = 0
        text = text.strip()
        if not text.startswith("{"):
            raise ImportProblem("csl-object-required")
        index = 1
        parsed: list[tuple[RawField, object]] = []
        while index < len(text):
            self._checkpoint()
            while index < len(text) and text[index].isspace():
                index += 1
            if index < len(text) and text[index] == "}":
                if text[index + 1 :].strip():
                    raise ValueError("trailing-object-content")
                return parsed
            name, index = decoder.raw_decode(text, index)
            if not isinstance(name, str):
                raise ValueError("invalid-field-name")
            while index < len(text) and text[index].isspace():
                index += 1
            if index >= len(text) or text[index] != ":":
                raise ValueError("missing-colon")
            index += 1
            while index < len(text) and text[index].isspace():
                index += 1
            start = index
            value, index = decoder.raw_decode(text, index)
            parsed.append((RawField(name, text[start:index]), value))
            if len(parsed) > self.limits.max_fields:
                raise ImportProblem("field-count-limit")
            while index < len(text) and text[index].isspace():
                index += 1
            if index < len(text) and text[index] == ",":
                index += 1
                if text[index:].lstrip().startswith("}"):
                    raise ValueError("trailing-comma")
            elif index >= len(text) or text[index] != "}":
                raise ValueError("invalid-object-delimiter")
        raise ValueError("unterminated-object")

    def _bib(self, text: str, warnings: set[str]) -> tuple[str, list[tuple[RawField, object]], dict[str, str | None]]:
        if "bibtex-comment" in warnings:
            return "directive", [(RawField("comment", text), None)], {}
        match = re.match(r"@([A-Za-z]+)\s*([({])", text)
        if match is None:
            raise ImportProblem("invalid-bibtex")
        entry_type = match[1].casefold()
        body = text[match.end() : -1]
        if entry_type in {"comment", "preamble"}:
            warnings.add("inert-bibtex-directive")
            return "directive", [(RawField(entry_type, body), None)], {}
        parsed: list[tuple[RawField, object]] = [(RawField("entry-type", match[1]), None)]
        if entry_type != "string":
            key, separator, body = body.partition(",")
            if not key.strip() or any(char.isspace() for char in key.strip()):
                raise ImportProblem("invalid-bibtex-key")
            parsed.append((RawField("citation-key", key.strip()), None))
            if not separator:
                warnings.add("empty-bibtex-entry")
        index = 0
        definitions: dict[str, str | None] = {}
        while index < len(body):
            self._checkpoint()
            while index < len(body) and (body[index].isspace() or body[index] == ","):
                index += 1
            if index == len(body):
                break
            name_match = _BIB_NAME.match(body, index)
            if name_match is None:
                raise ImportProblem("invalid-bibtex-field")
            name, index = name_match[0], name_match.end()
            while index < len(body) and body[index].isspace():
                index += 1
            if index == len(body) or body[index] != "=":
                raise ImportProblem("invalid-bibtex-assignment")
            index += 1
            start = index
            pieces: list[str] = []
            expanded_size = 0
            unresolved = False
            while True:
                self._checkpoint()
                piece: str | None = None
                while index < len(body) and body[index].isspace():
                    index += 1
                if index >= len(body):
                    raise ImportProblem("missing-bibtex-value")
                if body[index] in '{"':
                    opener = body[index]
                    index += 1
                    value_start, depth, escaped = index, 0, False
                    while index < len(body):
                        char = body[index]
                        if escaped:
                            escaped = False
                        elif char == "\\":
                            escaped = True
                        elif char == "{":
                            depth += 1
                        elif ((char == "}" and opener == "{") or (char == '"' and opener == '"')) and depth == 0:
                            break
                        elif char == "}" and depth:
                            depth -= 1
                        index += 1
                    if index == len(body):
                        raise ImportProblem("unterminated-bibtex-value")
                    piece = body[value_start:index]
                    index += 1
                else:
                    token = _BIB_ATOM.match(body, index)
                    if token is None:
                        raise ImportProblem("invalid-bibtex-value")
                    atom = token[0]
                    index += len(atom)
                    if atom.isascii() and atom.isdecimal():
                        piece = atom
                    else:
                        piece = definitions.get(atom.casefold(), self._macros.get(atom.casefold()))
                if piece is None:
                    unresolved = True
                    warnings.add("unresolved-bibtex-macro")
                else:
                    pieces.append(piece)
                    expanded_size += len(piece.encode(self.source.encoding))
                if expanded_size > self.limits.max_field_bytes:
                    raise ImportProblem("field-limit")
                while index < len(body) and body[index].isspace():
                    index += 1
                if index < len(body) and body[index] == "#":
                    index += 1
                    continue
                break
            value = None if unresolved else "".join(pieces)
            field_warnings = ("unresolved-bibtex-macro",) if unresolved else ()
            parsed.append((RawField(name, body[start:index], field_warnings), value))
            if len(parsed) > self.limits.max_fields:
                raise ImportProblem("field-count-limit")
            if entry_type == "string":
                definitions[name.casefold()] = value
            if index < len(body) and body[index] != ",":
                raise ImportProblem("invalid-bibtex-separator")
        if entry_type == "string":
            if len(parsed) == 1:
                raise ImportProblem("missing-bibtex-definition")
            if len(self._macros.keys() | definitions.keys()) > self.limits.max_macros:
                raise ImportProblem("macro-count-limit")
            return "directive", parsed, definitions
        return "record", parsed, {}
