"""Inert native extraction inside the document worker; no paths, I/O or Core imports.

The raw receipt reports source bytes and decoded text separately. It supplies no
producer, attempt or storage authority. Runtime isolation is the launcher's job.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from collections.abc import Callable
from html.parser import HTMLParser
from typing import Any
from xml.parsers import expat

MAX_SOURCE_BYTES = 128 * 1_048_576
MAX_OUTPUT_BYTES = 64 * 1_048_576
MAX_DEPTH = 256
MAX_ELEMENTS = 1_000_000


class NativeParseError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _check(cancelled: Callable[[], bool]) -> None:
    stopped = True
    try:
        observation = cancelled()
        stopped = type(observation) is not bool or observation
    except Exception:
        pass
    if stopped:
        raise NativeParseError("cancelled")


def _qualified(name: str) -> str:
    return "{" + name if "}" in name else name


class _Receipt:
    def __init__(self, data: bytes, format: str, cancelled: Callable[[], bool]) -> None:
        self.data = data
        self.format = format
        self.cancelled = cancelled
        self.elements: list[dict[str, Any]] = []
        self.stack: list[int] = []
        self.runs: list[dict[str, int]] = []
        self.fragments: list[str] = []
        self.text_length = 0
        self.text_bytes = 0

    def start(self, name: str, attrs: list[tuple[str, str]], start: int, content: int) -> None:
        _check(self.cancelled)
        if len(self.stack) >= MAX_DEPTH or len(self.elements) >= MAX_ELEMENTS:
            raise NativeParseError("unsafe-content")
        self.elements.append(
            dict(
                index=len(self.elements),
                parentIndex=self.stack[-1] if self.stack else None,
                name=name,
                attributes=[dict(name=k, value=v) for k, v in attrs],
                byteStart=start,
                byteEnd=content,
                contentByteStart=content,
                contentByteEnd=content,
                textStart=self.text_length,
                textEnd=self.text_length,
                closeKind="empty",
            )
        )
        self.stack.append(len(self.elements) - 1)

    def end(self, content_end: int, byte_end: int, kind: str) -> None:
        _check(self.cancelled)
        if not self.stack:
            raise NativeParseError("malformed-content")
        node = self.elements[self.stack.pop()]
        node.update(contentByteEnd=content_end, byteEnd=byte_end, textEnd=self.text_length, closeKind=kind)

    def text(self, value: str, start: int, end: int) -> None:
        _check(self.cancelled)
        if not self.stack:
            if value.strip():
                raise NativeParseError("malformed-content")
            return
        if not value:
            return
        self.text_bytes += len(value.encode("utf-8"))
        if self.text_bytes > MAX_OUTPUT_BYTES:
            raise NativeParseError("oversize")
        self.runs.append(
            dict(
                ownerIndex=self.stack[-1],
                byteStart=start,
                byteEnd=end,
                textStart=self.text_length,
                textEnd=self.text_length + len(value),
            )
        )
        self.fragments.append(value)
        self.text_length += len(value)

    def wire(self) -> bytes:
        if self.stack or not self.elements:
            raise NativeParseError("malformed-content")
        value = dict(
            schemaVersion="1.0",
            format=self.format,
            sourceSha256=hashlib.sha256(self.data).hexdigest(),
            sourceByteLength=len(self.data),
            text="".join(self.fragments),
            elements=self.elements,
            textRuns=self.runs,
        )
        fragments: list[bytes] = []
        size = 0
        for fragment in json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(",", ":")).iterencode(value):
            _check(self.cancelled)
            encoded = fragment.encode("utf-8")
            size += len(encoded)
            if size > MAX_OUTPUT_BYTES:
                raise NativeParseError("oversize")
            fragments.append(encoded)
        return b"".join(fragments)


def _codec(data: bytes) -> str:
    if data.startswith(b"\xff\xfe"):
        return "utf-16-le"
    if data.startswith(b"\xfe\xff"):
        return "utf-16-be"
    declaration = re.match(rb"<\?xml\s[^?]*encoding\s*=\s*['\"]([^'\"]+)['\"]", data[:1024])
    name = declaration.group(1).lower() if declaration else b"utf-8"
    supported = {b"utf-8": "utf-8", b"us-ascii": "ascii", b"ascii": "ascii", b"iso-8859-1": "iso-8859-1"}
    if name not in supported:
        raise NativeParseError("unsupported-format")
    return supported[name]


def _xml_entities(value: str) -> str:
    predefined = {"amp": "&", "lt": "<", "gt": ">", "apos": "'", "quot": '"'}

    def expand(match: re.Match[str]) -> str:
        name = match.group(1)
        if name.startswith("#x"):
            return chr(int(name[2:], 16))
        if name.startswith("#"):
            return chr(int(name[1:]))
        return predefined[name]

    return re.sub(r"&([^;]+);", expand, value)


def _xml(receipt: _Receipt) -> None:
    data = receipt.data
    codec = _codec(data)
    unit = 2 if codec.startswith("utf-16") else 1
    parser = expat.ParserCreate(namespace_separator="}")
    pending: tuple[int, str, bool] | None = None
    cdata = False
    empty: list[bool] = []

    def tag_end(start: int) -> int:
        quote = 0
        for position in range(start, len(data), unit):
            # Only markup ASCII units matter; decoding a lone UTF-8 byte or
            # UTF-16 surrogate would reject valid non-ASCII attribute values.
            char = (
                int.from_bytes(data[position : position + 2], "little" if codec.endswith("le") else "big")
                if unit == 2
                else data[position]
            )
            if quote:
                if char == quote:
                    quote = 0
            elif char in {34, 39}:
                quote = char
            elif char == 62:
                return position + unit
        raise NativeParseError("malformed-content")

    def flush(end: int) -> None:
        nonlocal pending
        if pending is None:
            return
        start, observed, literal = pending
        lexical = data[start:end].decode(codec)
        raw = lexical if literal else _xml_entities(lexical)
        folded = lexical.replace("\r\n", "\n").replace("\r", "\n")
        expected = folded if literal else _xml_entities(folded)
        if expected != observed:
            raise NativeParseError("malformed-content")
        receipt.text(raw, start, end)
        pending = None

    def start(name: str, attrs: dict[str, str]) -> None:
        offset = parser.CurrentByteIndex
        flush(offset)
        end = tag_end(offset)
        lexical = data[offset:end].decode(codec)
        receipt.start(_qualified(name), [(_qualified(k), v) for k, v in attrs.items()], offset, end)
        empty.append(lexical.rstrip().endswith("/>"))

    def end(_name: str) -> None:
        offset = parser.CurrentByteIndex
        flush(offset)
        if empty.pop():
            position = receipt.elements[receipt.stack[-1]]["contentByteStart"]
            receipt.end(position, position, "empty")
        else:
            receipt.end(offset, tag_end(offset), "explicit")

    def text(value: str) -> None:
        nonlocal pending
        flush(parser.CurrentByteIndex)
        pending = (parser.CurrentByteIndex, value, cdata)

    def cdata_start() -> None:
        nonlocal cdata
        flush(parser.CurrentByteIndex)
        cdata = True

    def cdata_end() -> None:
        nonlocal cdata
        flush(parser.CurrentByteIndex)
        cdata = False

    def unsafe(*_args: object) -> None:
        raise NativeParseError("unsafe-content")

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = text
    parser.StartCdataSectionHandler = cdata_start
    parser.EndCdataSectionHandler = cdata_end
    parser.CommentHandler = lambda _value: flush(parser.CurrentByteIndex)
    parser.StartDoctypeDeclHandler = unsafe
    parser.EntityDeclHandler = unsafe
    parser.ExternalEntityRefHandler = lambda *_args: 0
    parser.ProcessingInstructionHandler = unsafe
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    for position in range(0, len(data), 65_536):
        _check(receipt.cancelled)
        parser.Parse(data[position : position + 65_536], False)
    parser.Parse(b"", True)
    flush(len(data))


class _HTML(HTMLParser):
    ACTIVE = frozenset(
        [
            "script",
            "style",
            "iframe",
            "frame",
            "frameset",
            "object",
            "embed",
            "form",
            "input",
            "button",
            "base",
            "link",
            "meta",
            "svg",
            "canvas",
        ]
    )
    FETCH = frozenset(["src", "srcset", "data", "poster", "action", "formaction"])
    VOID = frozenset(["area", "br", "col", "hr", "img", "source", "track", "wbr"])
    BLOCK = frozenset(
        [
            "address",
            "article",
            "aside",
            "blockquote",
            "div",
            "dl",
            "fieldset",
            "footer",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "header",
            "hr",
            "menu",
            "nav",
            "ol",
            "p",
            "pre",
            "section",
            "table",
            "ul",
        ]
    )

    def __init__(self, receipt: _Receipt) -> None:
        super().__init__(convert_charrefs=False, scripting=False)
        self.receipt = receipt
        self.decoded = receipt.data.decode("utf-8-sig")
        if "\x00" in self.decoded:
            raise NativeParseError("malformed-content")
        self.lines = [0] + [m.end() for m in re.finditer("\n", self.decoded)]
        self.last_char = 0
        self.last_byte = 3 if receipt.data.startswith(b"\xef\xbb\xbf") else 0
        self.tags: list[str] = []
        self.namespaces: list[dict[str, str]] = []

    def position(self) -> tuple[int, int]:
        line, column = self.getpos()
        char = self.lines[line - 1] + column
        if char < self.last_char:
            raise NativeParseError("malformed-content")
        self.last_byte += len(self.decoded[self.last_char : char].encode("utf-8"))
        self.last_char = char
        return char, self.last_byte

    def close_element(self, start: int, end: int, kind: str) -> None:
        self.receipt.end(start, end, kind)
        self.tags.pop()
        self.namespaces.pop()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        _char, start = self.position()
        if tag in self.ACTIVE:
            raise NativeParseError("unsafe-content")
        for name, value in attrs:
            normalized = re.sub(r"[\x00-\x20]", "", value or "").casefold()
            if (
                name.startswith("on")
                or name == "style"
                or name in self.FETCH
                or (
                    name in {"href", "xlink:href"}
                    and normalized.startswith(("javascript:", "data:", "file:", "vbscript:"))
                )
            ):
                raise NativeParseError("unsafe-content")
        optional = {
            "li": {"li"},
            "dt": {"dt", "dd"},
            "dd": {"dt", "dd"},
            "tr": {"tr", "td", "th"},
            "td": {"td", "th"},
            "th": {"td", "th"},
            "tbody": {"tbody", "thead", "tfoot", "tr", "td", "th"},
        }
        while self.tags and (self.tags[-1] in optional.get(tag, set()) or (self.tags[-1] == "p" and tag in self.BLOCK)):
            self.close_element(start, start, "implicit")
        scope = dict(self.namespaces[-1]) if self.namespaces else {}
        for name, value in attrs:
            if name == "xmlns":
                scope[""] = value or ""
            elif name.startswith("xmlns:"):
                scope[name[6:]] = value or ""
        prefix, _, local = tag.rpartition(":")
        uri = scope.get(prefix, "" if not prefix else "urn:unbound-prefix:" + prefix)
        qualified = "{" + uri + "}" + local if uri else tag
        lexical = self.get_starttag_text()
        assert lexical is not None
        content = start + len(lexical.encode("utf-8"))
        self.receipt.start(qualified, [(k, v or "") for k, v in attrs], start, content)
        self.tags.append(tag)
        self.namespaces.append(scope)
        if tag in self.VOID:
            self.close_element(content, content, "empty")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            content = self.receipt.elements[self.receipt.stack[-1]]["contentByteStart"]
            self.close_element(content, content, "empty")

    def handle_endtag(self, tag: str) -> None:
        char, start = self.position()
        if tag not in self.tags:
            raise NativeParseError("malformed-content")
        while self.tags[-1] != tag:
            if self.tags[-1] not in {"li", "p", "dt", "dd", "td", "th", "tr", "tbody", "thead", "tfoot"}:
                raise NativeParseError("malformed-content")
            self.close_element(start, start, "implicit")
        end_char = self.decoded.find(">", char)
        if end_char < 0:
            raise NativeParseError("malformed-content")
        self.close_element(start, start + len(self.decoded[char : end_char + 1].encode("utf-8")), "explicit")

    def handle_data(self, data: str) -> None:
        _char, start = self.position()
        self.receipt.text(data, start, start + len(data.encode("utf-8")))

    def reference(self) -> None:
        char, start = self.position()
        match = re.match(r"&(?:#[xX][0-9a-fA-F]+|#[0-9]+|[A-Za-z][A-Za-z0-9]*);?", self.decoded[char:])
        if match is None:
            raise NativeParseError("malformed-content")
        lexical = match.group()
        self.receipt.text(html.unescape(lexical), start, start + len(lexical.encode("utf-8")))

    def handle_entityref(self, _name: str) -> None:
        self.reference()

    def handle_charref(self, _name: str) -> None:
        self.reference()

    def handle_decl(self, decl: str) -> None:
        if decl.strip().casefold() != "doctype html":
            raise NativeParseError("unsafe-content")

    def unknown_decl(self, _data: str) -> None:
        raise NativeParseError("unsafe-content")

    def handle_pi(self, _data: str) -> None:
        raise NativeParseError("unsafe-content")


def parse_native_structure(data: bytes, *, format: str, cancelled: Callable[[], bool]) -> bytes:
    """Return one bounded receipt or a content-free failure, never partial output."""
    _check(cancelled)
    if type(data) is not bytes or not data or format not in {"jats", "tei", "xml", "html"}:
        raise NativeParseError("unsupported-format")
    if len(data) > MAX_SOURCE_BYTES:
        raise NativeParseError("oversize")
    failure = "malformed-content"
    wire = None
    try:
        receipt = _Receipt(data, format, cancelled)
        if format == "html":
            parser = _HTML(receipt)
            for position in range(0, len(parser.decoded), 65_536):
                _check(cancelled)
                parser.feed(parser.decoded[position : position + 65_536])
            parser.close()
            if not receipt.elements or receipt.elements[0]["name"] not in {
                "html",
                "{http://www.w3.org/1999/xhtml}html",
            }:
                raise NativeParseError("malformed-content")
        else:
            _xml(receipt)
            root = receipt.elements[0]["name"] if receipt.elements else ""
            if (format == "jats" and root not in {"article", "{http://jats.nlm.nih.gov}article"}) or (
                format == "tei" and root not in {"TEI", "{http://www.tei-c.org/ns/1.0}TEI"}
            ):
                raise NativeParseError("format-mismatch")
        wire = receipt.wire()
    except NativeParseError as problem:
        failure = problem.code
    except ValueError, KeyError, UnicodeError, RecursionError, expat.ExpatError:
        pass
    if wire is None:
        raise NativeParseError(failure)
    return wire
