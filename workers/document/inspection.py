"""Bounded, non-rendering format inspection inside the signed LPAC worker.

This module must only be invoked by the isolated worker on untrusted bytes. It
does not resolve paths, fetch resources, extract archives to disk or interpret
document text as instructions. A positive verdict is intake suitability, not a
claim that downstream parsing will succeed.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from html.parser import HTMLParser
from xml.parsers import expat

MAX_DOCUMENT_BYTES = 128 * 1_048_576
_MAX_XML_PART_BYTES = 64 * 1_048_576
_MAX_ARCHIVE_ENTRIES = 4096
_MAX_XML_DEPTH = 256
_MAX_XML_ELEMENTS = 1_000_000
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_MIME: dict[str, frozenset[str]] = {
    "pdf": frozenset({"application/pdf"}),
    "jats": frozenset({"application/xml", "text/xml", "application/jats+xml"}),
    "tei": frozenset({"application/xml", "text/xml", "application/tei+xml"}),
    "xml": frozenset({"application/xml", "text/xml"}),
    "html": frozenset({"text/html"}),
    "docx": frozenset({_DOCX_MIME}),
    "txt": frozenset({"text/plain"}),
}
_EXTENSIONS: dict[str, frozenset[str]] = {
    "pdf": frozenset({".pdf"}),
    "jats": frozenset({".xml", ".nxml", ".jats"}),
    "tei": frozenset({".xml", ".tei"}),
    "xml": frozenset({".xml"}),
    "html": frozenset({".html", ".htm"}),
    "docx": frozenset({".docx"}),
    "txt": frozenset({".txt", ".text"}),
}
_MEDIA_TYPE = {
    "pdf": "application/pdf",
    "jats": "application/xml",
    "tei": "application/xml",
    "xml": "application/xml",
    "html": "text/html",
    "docx": _DOCX_MIME,
    "txt": "text/plain",
}
_PDF_NAME = re.compile(rb"/([A-Za-z0-9#]{1,64})")
_PDF_ACTIVE = frozenset({"JavaScript", "JS", "OpenAction", "AA", "Launch", "EmbeddedFile", "RichMedia", "XFA"})
_PDF_XREF_SUBSECTION = re.compile(rb"([0-9]{1,9})[ \t]+([1-9][0-9]{0,8})[ \t]*(?:\r\n|\r|\n)")
_PDF_XREF_ENTRY = re.compile(rb"([0-9]{10})[ \t]+([0-9]{5})[ \t]+([nf])[ \t]*(?:\r\n|\r|\n)")
_PDF_OBJECT_HEADER = re.compile(rb"([0-9]{1,9})[ \t]+([0-9]{1,5})[ \t]+obj\b")
_PDF_TRAILER = re.compile(rb"trailer[ \t]*(?:\r\n|\r|\n)")


class DocumentInspectionError(ValueError):
    """Typed, content-free rejection from the document intake worker."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class DocumentInspection:
    format: str
    media_type: str
    size_bytes: int
    sha256: str


def _xml_root(
    data: bytes,
    *,
    reject_external_relationship: bool = False,
    on_start: Callable[[str, dict[str, str]], None] | None = None,
) -> str:
    parser = expat.ParserCreate(namespace_separator="}")
    root: str | None = None
    depth = 0
    count = 0

    def start(name: str, attrs: dict[str, str]) -> None:
        nonlocal root, depth, count
        count += 1
        depth += 1
        if count > _MAX_XML_ELEMENTS or depth > _MAX_XML_DEPTH:
            raise DocumentInspectionError("unsafe-content")
        if root is None:
            root = name
        if reject_external_relationship:
            for key, value in attrs.items():
                if key.rpartition("}")[2].casefold() == "targetmode" and value.casefold() == "external":
                    raise DocumentInspectionError("unsafe-content")
        if on_start is not None:
            on_start(name, attrs)

    def end(_name: str) -> None:
        nonlocal depth
        depth -= 1

    def unsafe(*_args: object) -> None:
        raise DocumentInspectionError("unsafe-content")

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.StartDoctypeDeclHandler = unsafe
    parser.EntityDeclHandler = unsafe
    parser.ExternalEntityRefHandler = lambda *_args: 0
    parser.ProcessingInstructionHandler = unsafe
    try:
        for offset in range(0, len(data), 1_048_576):
            parser.Parse(data[offset : offset + 1_048_576], False)
        parser.Parse(b"", True)
    except DocumentInspectionError:
        raise
    except expat.ExpatError:
        raise DocumentInspectionError("malformed-content") from None
    if root is None or depth != 0:
        raise DocumentInspectionError("malformed-content")
    return root


class _SafeHTML(HTMLParser):
    _ACTIVE = frozenset(
        {
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
        }
    )
    _FETCH = frozenset({"src", "srcset", "data", "poster", "action", "formaction"})
    _VOID = frozenset({"area", "br", "col", "hr", "img", "source", "track", "wbr"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.elements = 0
        self.html_seen = False
        self.html_closed = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements += 1
        if tag not in self._VOID:
            self.depth += 1
        if self.elements > _MAX_XML_ELEMENTS or self.depth > _MAX_XML_DEPTH:
            raise DocumentInspectionError("unsafe-content")
        if tag == "html":
            self.html_seen = True
        if tag in self._ACTIVE:
            raise DocumentInspectionError("unsafe-content")
        for name, value in attrs:
            normalized = (value or "").strip().casefold()
            if name.startswith("on") or name == "style" or name in self._FETCH:
                raise DocumentInspectionError("unsafe-content")
            if name in {"href", "xlink:href"} and normalized.startswith(("javascript:", "data:", "file:", "vbscript:")):
                raise DocumentInspectionError("unsafe-content")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self._VOID:
            self.depth -= 1

    def handle_endtag(self, tag: str) -> None:
        self.depth -= 1
        if self.depth < 0:
            raise DocumentInspectionError("malformed-content")
        if tag == "html":
            self.html_closed = True

    def handle_decl(self, decl: str) -> None:
        if decl.strip().casefold() != "doctype html":
            raise DocumentInspectionError("unsafe-content")


def _inspect_html(data: bytes) -> None:
    try:
        decoded = data.decode("utf-8-sig")
    except UnicodeError:
        raise DocumentInspectionError("malformed-content") from None
    if "\x00" in decoded:
        raise DocumentInspectionError("malformed-content")
    parser = _SafeHTML()
    try:
        for offset in range(0, len(decoded), 1_048_576):
            parser.feed(decoded[offset : offset + 1_048_576])
        parser.close()
    except DocumentInspectionError:
        raise
    except ValueError:
        raise DocumentInspectionError("malformed-content") from None
    if not parser.html_seen or not parser.html_closed:
        raise DocumentInspectionError("malformed-content")


def _inspect_pdf(data: bytes) -> None:
    if re.match(rb"\A%PDF-[12]\.[0-9]\r?\n", data) is None:
        raise DocumentInspectionError("malformed-content")
    eof = data.rfind(b"%%EOF")
    if eof < 0 or len(data) - eof > 2048 or data[eof + 5 :].strip():
        raise DocumentInspectionError("malformed-content")
    marker = data.rfind(b"startxref", 0, eof)
    if marker < 0:
        raise DocumentInspectionError("malformed-content")
    match = re.match(rb"startxref\s+([0-9]+)\s*\Z", data[marker:eof])
    if match is None or len(match.group(1)) > 9:
        raise DocumentInspectionError("malformed-content")
    offset = int(match.group(1))
    if offset >= marker:
        raise DocumentInspectionError("malformed-content")
    preceding = data[offset:marker]
    if preceding.startswith(b"xref"):
        _inspect_pdf_classic_xref(data, offset, preceding)
    else:
        # Xref streams can hide object dictionaries behind stream filters and
        # require full entry, length, filter and object-reference validation.
        # This bounded intake parser only validates classic xref tables.
        if re.match(rb"[0-9]+\s+[0-9]+\s+obj\b", preceding[:64]) is None:
            raise DocumentInspectionError("malformed-content")
        raise DocumentInspectionError("unsupported-format")
    names = _pdf_names(data)
    if names & {"ObjStm", "XRefStm"}:
        raise DocumentInspectionError("unsupported-format")
    if "Encrypt" in _pdf_names(preceding):
        raise DocumentInspectionError("password-protected")
    if names & _PDF_ACTIVE:
        raise DocumentInspectionError("unsafe-content")


def _inspect_pdf_catalog(data: bytes) -> None:
    # Only the direct, uncomplicated catalog signature is admitted here. A
    # fuller PDF object grammar belongs to the later isolated parsing stage.
    if (
        len(data) > 1_048_576
        or re.match(rb"\s*<<\s*/Type\s+/Catalog(?=[\s/<>()\[\]])", data) is None
        or re.search(rb">>\s*\Z", data) is None
        or len(re.findall(rb"/Type\b", data)) != 1
        or b"#" in data
    ):
        raise DocumentInspectionError("unsupported-format")


def _inspect_pdf_classic_xref(data: bytes, xref_offset: int, preceding: bytes) -> None:
    opener = re.match(rb"xref[ \t]*(?:\r\n|\r|\n)", preceding)
    if opener is None:
        raise DocumentInspectionError("malformed-content")
    trailer_marker = _PDF_TRAILER.search(preceding, opener.end())
    if trailer_marker is None:
        raise DocumentInspectionError("malformed-content")
    trailer = preceding[trailer_marker.end() :]
    if len(trailer) > 65_536:
        raise DocumentInspectionError("unsupported-format")
    dictionary = re.fullmatch(rb"\s*<<(.*?)>>\s*", trailer, flags=re.DOTALL)
    if dictionary is None:
        raise DocumentInspectionError("malformed-content")
    trailer_body = dictionary.group(1)
    if b"<<" in trailer_body or b">>" in trailer_body or b"(" in trailer_body:
        raise DocumentInspectionError("unsupported-format")
    root = re.search(rb"/Root\s+([0-9]{1,9})\s+([0-9]{1,5})\s+R\b", trailer_body)
    if root is None or len(re.findall(rb"/Root\b", trailer_body)) != 1:
        raise DocumentInspectionError("malformed-content")
    root_number, root_generation = int(root.group(1)), int(root.group(2))
    position = opener.end()
    previous_end = -1
    root_body_start: int | None = None
    while position < trailer_marker.start():
        subsection = _PDF_XREF_SUBSECTION.match(preceding, position)
        if subsection is None:
            raise DocumentInspectionError("malformed-content")
        first, count = (int(group) for group in subsection.groups())
        position = subsection.end()
        if first <= previous_end or first + count > 1_000_000_000 or count > (trailer_marker.start() - position) // 18:
            raise DocumentInspectionError("malformed-content")
        previous_end = first + count - 1
        for object_number in range(first, first + count):
            entry = _PDF_XREF_ENTRY.match(preceding, position)
            if entry is None:
                raise DocumentInspectionError("malformed-content")
            position = entry.end()
            if entry.group(3) != b"n":
                continue
            object_offset, generation = int(entry.group(1)), int(entry.group(2))
            header = _PDF_OBJECT_HEADER.match(data, object_offset)
            if (
                object_offset >= xref_offset
                or header is None
                or int(header.group(1)) != object_number
                or int(header.group(2)) != generation
            ):
                raise DocumentInspectionError("unsupported-format")
            if object_number == root_number and generation == root_generation:
                root_body_start = header.end()
    if position != trailer_marker.start():
        raise DocumentInspectionError("malformed-content")
    if root_body_start is None:
        raise DocumentInspectionError("unsupported-format")
    end = data.find(b"endobj", root_body_start, xref_offset)
    if end < 0 or end - root_body_start > 1_048_576:
        raise DocumentInspectionError("unsupported-format")
    _inspect_pdf_catalog(data[root_body_start:end])


def _pdf_names(data: bytes) -> set[str]:
    names: set[str] = set()
    for match in _PDF_NAME.finditer(data):
        encoded = match.group(1)
        decoded = re.sub(rb"#([0-9A-Fa-f]{2})", lambda token: bytes.fromhex(token.group(1).decode("ascii")), encoded)
        try:
            names.add(decoded.decode("ascii"))
        except UnicodeError:
            continue
    return names


def _inspect_docx(data: bytes) -> None:
    eocd = data.rfind(b"PK\x05\x06")
    if (
        eocd < 0
        or eocd + 22 > len(data)
        or eocd + 22 + int.from_bytes(data[eocd + 20 : eocd + 22], "little") != len(data)
    ):
        raise DocumentInspectionError("malformed-content")
    try:
        content_types_ns = "http://schemas.openxmlformats.org/package/2006/content-types"
        relationships_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
        word_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        roots: dict[str, str] = {}
        found_content_type = False
        found_office_document = False
        found_body = False

        def note_element(part: str, name: str, attrs: dict[str, str]) -> None:
            nonlocal found_content_type, found_office_document, found_body
            if part == "[Content_Types].xml" and name == f"{content_types_ns}}}Override":
                found_content_type |= (
                    attrs.get("PartName") == "/word/document.xml"
                    and attrs.get("ContentType") == _DOCX_MIME + ".main+xml"
                )
            elif part == "_rels/.rels" and name == f"{relationships_ns}}}Relationship":
                found_office_document |= (
                    attrs.get("Type")
                    == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
                    and attrs.get("Target") == "word/document.xml"
                )
            elif part == "word/document.xml" and name == f"{word_ns}}}body":
                found_body = True

        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if not 0 < len(entries) <= _MAX_ARCHIVE_ENTRIES:
                raise DocumentInspectionError("unsafe-content")
            seen: set[str] = set()
            names: set[str] = set()
            total = 0
            for info in entries:
                name = info.filename
                parts = name.rstrip("/").split("/")
                folded = name.casefold()
                if (
                    not name
                    or name.startswith("/")
                    or "\\" in name
                    or ":" in name
                    or any(part in {"", ".", ".."} for part in parts)
                    or folded in seen
                    or info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                    or (info.external_attr >> 16) & 0o170000 == 0o120000
                ):
                    raise DocumentInspectionError("unsafe-content")
                seen.add(folded)
                names.add(name)
                if info.flag_bits & 1:
                    raise DocumentInspectionError("password-protected")
                if any(
                    part.casefold() in {"vbaproject.bin", "activex", "embeddings", "oleobject.bin"} for part in parts
                ):
                    raise DocumentInspectionError("unsafe-content")
                total += info.file_size
                if total > MAX_DOCUMENT_BYTES or info.file_size > MAX_DOCUMENT_BYTES:
                    raise DocumentInspectionError("unsafe-content")
                if info.file_size > 1_048_576 and info.file_size > max(1, info.compress_size) * 100:
                    raise DocumentInspectionError("unsafe-content")
            if not {"[Content_Types].xml", "_rels/.rels", "word/document.xml"} <= names:
                raise DocumentInspectionError("malformed-content")
            for info in entries:
                if info.is_dir():
                    continue
                is_xml = info.filename.casefold().endswith((".xml", ".rels")) or info.filename == "[Content_Types].xml"
                if is_xml and info.file_size > _MAX_XML_PART_BYTES:
                    raise DocumentInspectionError("unsafe-content")
                chunks: list[bytes] = []
                count = 0
                with archive.open(info) as part:
                    while chunk := part.read(1_048_576):
                        count += len(chunk)
                        if count > info.file_size:
                            raise DocumentInspectionError("malformed-content")
                        if is_xml:
                            chunks.append(chunk)
                if count != info.file_size:
                    raise DocumentInspectionError("malformed-content")
                if is_xml:
                    raw = b"".join(chunks)
                    root = _xml_root(
                        raw,
                        reject_external_relationship=info.filename.casefold().endswith(".rels"),
                        on_start=partial(note_element, info.filename),
                    )
                    if info.filename in {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}:
                        roots[info.filename] = root
            if (
                roots.get("[Content_Types].xml") != f"{content_types_ns}}}Types"
                or roots.get("_rels/.rels") != f"{relationships_ns}}}Relationships"
                or roots.get("word/document.xml") != f"{word_ns}}}document"
                or not (found_content_type and found_office_document and found_body)
            ):
                raise DocumentInspectionError("malformed-content")
    except DocumentInspectionError:
        raise
    except OSError, EOFError, RuntimeError, ValueError, zipfile.BadZipFile, zipfile.LargeZipFile:
        raise DocumentInspectionError("malformed-content") from None


def _inspect_text(data: bytes) -> None:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeError:
        raise DocumentInspectionError("unsupported-format") from None
    if not text.strip() or any(ord(char) < 32 and char not in "\t\n\r\f" for char in text):
        raise DocumentInspectionError("unsupported-format")


def classify_document(
    data: bytes, *, extension: str = "", declared_media_type: str | None = None
) -> DocumentInspection:
    """Classify bounded bytes after they have entered the zero-capability worker."""

    if not isinstance(data, bytes) or not data or not isinstance(extension, str):
        raise DocumentInspectionError("unsupported-format")
    if len(data) > MAX_DOCUMENT_BYTES:
        raise DocumentInspectionError("oversize")
    hint = extension.casefold()
    mime = declared_media_type.split(";", 1)[0].strip().casefold() if declared_media_type else None
    stripped = data.lstrip(b"\xef\xbb\xbf\x09\x0a\x0d\x20")
    if data.startswith(b"%PDF-"):
        kind = "pdf"
        _inspect_pdf(data)
    elif data.startswith(b"PK\x03\x04"):
        kind = "docx"
        _inspect_docx(data)
    elif re.match(rb"(?is)\A(?:<!doctype\s+html\b|<html\b)", stripped):
        kind = "html"
        _inspect_html(data)
    elif stripped.startswith(b"<"):
        root = _xml_root(data)
        namespace, _, local = root.rpartition("}")
        if local.casefold() == "article" and ("jats" in namespace.casefold() or not namespace):
            kind = "jats"
        elif local == "TEI" and (namespace == "http://www.tei-c.org/ns/1.0" or not namespace):
            kind = "tei"
        else:
            kind = "xml"
    else:
        _inspect_text(data)
        kind = "txt"
    if hint and hint not in _EXTENSIONS[kind]:
        known_extension = any(hint in values for values in _EXTENSIONS.values())
        raise DocumentInspectionError("format-mismatch" if known_extension else "unsupported-format")
    if mime and mime not in _MIME[kind]:
        raise DocumentInspectionError("format-mismatch")
    if kind == "txt" and not (hint or mime):
        raise DocumentInspectionError("unsupported-format")
    return DocumentInspection(kind, _MEDIA_TYPE[kind], len(data), hashlib.sha256(data).hexdigest())
