"""Synthetic, hostile-input checks for the isolated document classifier."""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import unittest
import zipfile
import zlib
from pathlib import Path
from typing import BinaryIO, cast
from unittest.mock import patch

CORE_SOURCE = Path(__file__).resolve().parents[2] / "services" / "core-api" / "src"
sys.path.insert(0, str(CORE_SOURCE))

from workers.document.inspection import (  # noqa: E402
    MAX_DOCUMENT_BYTES,
    DocumentInspectionError,
    classify_document,
)
from workers.windows import connector_launcher, document_launcher, recovery_guardian  # noqa: E402
from workers.windows.document_launcher import inspect_document  # noqa: E402
from workers.windows.plugin_worker import WorkerProtocolError, run_worker  # noqa: E402
from workers.windows.protocol import encode_frame, read_binary_frame, read_frame, write_binary_frame  # noqa: E402
from workers.windows.runtime_inventory import APPLICATION_INVENTORY_PUBLIC_KEY, SignedWorkerRuntime  # noqa: E402


def _pdf(*, encrypted: bool = False) -> bytes:
    prefix = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    offset = len(prefix)
    trailer = b"<< /Size 2 /Root 1 0 R"
    if encrypted:
        trailer += b" /Encrypt 2 0 R"
    return (
        prefix
        + b"xref\n0 2\n0000000000 65535 f \n0000000009 00000 n \ntrailer\n"
        + trailer
        + b" >>\nstartxref\n"
        + str(offset).encode("ascii")
        + b"\n%%EOF\n"
    )


def _pdf_with_compressed_xref_action() -> bytes:
    # Exact 210-byte pre-fix adverse: a forged xref stream with invalid xref
    # entries and a Flate-hidden active catalog.
    prefix = b"%PDF-1.7\n"
    payload = zlib.compress(b"<< /Type /Catalog /OpenAction << /S /JavaScript /JS (app.alert(1)) >> >>")
    xref = (
        b"1 0 obj\n<< /Type /XRef /Root 2 0 R /Size 2 /W [1 2 1] /Filter /FlateDecode >>\nstream\n"
        + payload
        + b"\nendstream\nendobj\n"
    )
    return prefix + xref + b"startxref\n" + str(len(prefix)).encode("ascii") + b"\n%%EOF\n"


def _pdf_with_compressed_object_stream() -> bytes:
    prefix = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    payload = zlib.compress(b"3 0 << /OpenAction << /S /JavaScript /JS (app.alert(1)) >> >>")
    object_offset = len(prefix)
    object_stream = (
        b"2 0 obj\n<< /Type /ObjStm /N 1 /First 4 /Filter /FlateDecode /Length "
        + str(len(payload)).encode("ascii")
        + b" >>\nstream\n"
        + payload
        + b"\nendstream\nendobj\n"
    )
    xref_offset = len(prefix) + len(object_stream)
    xref = (
        b"xref\n0 3\n0000000000 65535 f \n0000000009 00000 n \n"
        + f"{object_offset:010d}".encode("ascii")
        + b" 00000 n \ntrailer\n<< /Size 3 /Root 1 0 R >>\n"
    )
    return prefix + object_stream + xref + b"startxref\n" + str(xref_offset).encode("ascii") + b"\n%%EOF\n"


def _docx(*, extra: dict[str, bytes] | None = None) -> bytes:
    members = {
        "[Content_Types].xml": (
            b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            b'<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-'
            b'officedocument.wordprocessingml.document.main+xml"/></Types>'
        ),
        "_rels/.rels": (
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
            b'2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'
        ),
        "word/document.xml": (
            b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            b"<w:body><w:p><w:r><w:t>Synthetic text</w:t></w:r></w:p></w:body></w:document>"
        ),
    }
    members.update(extra or {})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class FormatInspectionTests(unittest.TestCase):
    def test_classic_xref_entry_must_resolve_to_an_object(self) -> None:
        original = _pdf()
        data = original.replace(b"1 0 obj", b"1 0 xxx", 1)
        self.assertNotEqual(original, data)
        self.assertEqual(len(original), len(data))
        with self.assertRaises(DocumentInspectionError) as caught:
            classify_document(data, extension=".pdf", declared_media_type="application/pdf")
        self.assertEqual("unsupported-format", caught.exception.code)

    def test_classic_xref_root_must_resolve_to_a_catalog(self) -> None:
        original = _pdf()
        data = original.replace(b"/Catalog", b"/Invalid", 1)
        self.assertNotEqual(original, data)
        self.assertEqual(len(original), len(data))
        with self.assertRaises(DocumentInspectionError) as caught:
            classify_document(data, extension=".pdf", declared_media_type="application/pdf")
        self.assertEqual("unsupported-format", caught.exception.code)

    def test_classic_xref_rejects_oversized_root_number_with_typed_error(self) -> None:
        data = _pdf().replace(b"/Root 1 0 R", b"/Root " + b"9" * 5000 + b" 0 R", 1)
        with self.assertRaises(DocumentInspectionError) as caught:
            classify_document(data, extension=".pdf", declared_media_type="application/pdf")
        self.assertEqual("malformed-content", caught.exception.code)

    def test_compressed_xref_stream_cannot_hide_active_pdf_content(self) -> None:
        data = _pdf_with_compressed_xref_action()
        self.assertEqual(210, len(data))
        self.assertEqual(
            "0d972181be3706d31c7762c848b107aa5670e0dddb3072d5e7db5c7ed1388e9c",
            hashlib.sha256(data).hexdigest(),
        )
        self.assertNotIn(b"/OpenAction", data)
        self.assertNotIn(b"/JavaScript", data)
        with self.assertRaises(DocumentInspectionError) as caught:
            classify_document(data, extension=".pdf", declared_media_type="application/pdf")
        self.assertEqual("unsupported-format", caught.exception.code)

    def test_classic_xref_does_not_admit_uninspected_object_stream(self) -> None:
        data = _pdf_with_compressed_object_stream()
        self.assertNotIn(b"/OpenAction", data)
        with self.assertRaises(DocumentInspectionError) as caught:
            classify_document(data, extension=".pdf", declared_media_type="application/pdf")
        self.assertEqual("unsupported-format", caught.exception.code)

    def test_hybrid_xref_stream_reference_is_unsupported(self) -> None:
        for marker in (b"/XRefStm", b"/XRef#53tm"):
            with self.subTest(marker=marker):
                data = _pdf().replace(b"/Root", marker + b" 9 /Root")
                with self.assertRaises(DocumentInspectionError) as caught:
                    classify_document(data, extension=".pdf", declared_media_type="application/pdf")
                self.assertEqual("unsupported-format", caught.exception.code)

    def test_supported_signatures_and_structure(self) -> None:
        cases = [
            (_pdf(), ".pdf", "application/pdf", "pdf"),
            (b'<article xmlns="http://jats.nlm.nih.gov"><body/></article>', ".xml", "application/xml", "jats"),
            (b'<TEI xmlns="http://www.tei-c.org/ns/1.0"><text/></TEI>', ".tei", "application/xml", "tei"),
            (b"<record><title>Synthetic</title></record>", ".xml", "application/xml", "xml"),
            (b"<!doctype html><html><body>Synthetic</body></html>", ".html", "text/html", "html"),
            (b"<html><body><br/>Synthetic<hr/></body></html>", ".html", "text/html", "html"),
            (_docx(), ".docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx"),
            (b"Synthetic text\nSecond line\n", ".txt", "text/plain", "txt"),
        ]
        for data, extension, media_type, expected_format in cases:
            with self.subTest(expected_format=expected_format):
                outcome = classify_document(data, extension=extension, declared_media_type=media_type)
                self.assertEqual(outcome.format, expected_format)
                self.assertEqual(outcome.size_bytes, len(data))
                self.assertEqual(outcome.sha256, hashlib.sha256(data).hexdigest())

    def test_filename_and_media_type_cannot_override_content(self) -> None:
        with self.assertRaises(DocumentInspectionError) as caught:
            classify_document(_pdf(), extension=".docx", declared_media_type="application/pdf")
        self.assertEqual(caught.exception.code, "format-mismatch")
        with self.assertRaises(DocumentInspectionError) as caught:
            classify_document(_pdf(), extension=".pdf", declared_media_type="text/plain")
        self.assertEqual(caught.exception.code, "format-mismatch")

    def test_password_protected_pdf_and_docx_are_rejected(self) -> None:
        with self.assertRaises(DocumentInspectionError) as caught:
            classify_document(_pdf(encrypted=True), extension=".pdf")
        self.assertEqual(caught.exception.code, "password-protected")

        protected = bytearray(_docx())
        local = protected.find(b"PK\x03\x04")
        central = protected.find(b"PK\x01\x02")
        self.assertGreaterEqual(local, 0)
        self.assertGreaterEqual(central, 0)
        protected[local + 6 : local + 8] = (1).to_bytes(2, "little")
        protected[central + 8 : central + 10] = (1).to_bytes(2, "little")
        with self.assertRaises(DocumentInspectionError) as caught:
            classify_document(bytes(protected), extension=".docx")
        self.assertEqual(caught.exception.code, "password-protected")

    def test_active_html_xml_and_docx_are_rejected(self) -> None:
        cases = [
            (b"<html><body><script>alert(1)</script></body></html>", ".html"),
            (b'<html><body><a href="javascript:alert(1)">a</a></body></html>', ".html"),
            (b'<!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]><a>&x;</a>', ".xml"),
            (_pdf().replace(b"/Root", b"/Open#41ction /Root"), ".pdf"),
            (_docx(extra={"word/vbaProject.bin": b"macro"}), ".docx"),
            (
                _docx(
                    extra={
                        "word/_rels/document.xml.rels": (
                            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                            b'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/'
                            b'2006/relationships/hyperlink" Target="https://example.org" TargetMode="External"/>'
                            b"</Relationships>"
                        )
                    }
                ),
                ".docx",
            ),
        ]
        for data, extension in cases:
            with self.subTest(extension=extension, digest=hashlib.sha256(data).hexdigest()):
                with self.assertRaises(DocumentInspectionError) as caught:
                    classify_document(data, extension=extension)
                self.assertEqual(caught.exception.code, "unsafe-content")

    def test_malformed_and_unsupported_inputs_are_distinct(self) -> None:
        cases = [
            (b"%PDF-1.4\ntruncated", ".pdf", "malformed-content"),
            (b"%PDF-1.7\nxref/Root\nstartxref\n9\n%%EOF", ".pdf", "malformed-content"),
            (_pdf().replace(b"startxref\n", b"startxref\n" + b"9" * 5000), ".pdf", "malformed-content"),
            (b"<record>", ".xml", "malformed-content"),
            (b"PK\x03\x04truncated", ".docx", "malformed-content"),
            (_docx() + b"appended executable", ".docx", "malformed-content"),
            (
                _docx(extra={"word/document.xml": b"<not-a-word-document/>"}),
                ".docx",
                "malformed-content",
            ),
            (
                _docx(extra={"[Content_Types].xml": b"<Types>wordprocessingml.document.main+xml</Types>"}),
                ".docx",
                "malformed-content",
            ),
            (
                _docx(extra={"_rels/.rels": b"<Relationships>officeDocument word/document.xml</Relationships>"}),
                ".docx",
                "malformed-content",
            ),
            (b"\x89PNG\r\n\x1a\n", ".png", "unsupported-format"),
            (b"line\x00with-null", ".txt", "unsupported-format"),
            (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 504, ".docx", "unsupported-format"),
        ]
        for data, extension, expected in cases:
            with self.subTest(extension=extension):
                with self.assertRaises(DocumentInspectionError) as caught:
                    classify_document(data, extension=extension)
                self.assertEqual(caught.exception.code, expected)

    def test_size_cap_is_exact_and_checked_before_parsing(self) -> None:
        self.assertEqual(MAX_DOCUMENT_BYTES, 128 * 1_048_576)
        with (
            patch("workers.document.inspection.MAX_DOCUMENT_BYTES", 16),
            self.assertRaises(DocumentInspectionError) as caught,
        ):
            classify_document(b"not-a-document-at-all", extension=".txt")
        self.assertEqual(caught.exception.code, "oversize")

    def test_parent_denies_when_signed_worker_is_not_installed(self) -> None:
        source = io.BytesIO(b"Synthetic text")
        with patch.object(sys, "frozen", False, create=True), self.assertRaises(DocumentInspectionError) as caught:
            inspect_document(source, filename="synthetic.txt", declared_media_type="text/plain")
        self.assertEqual(caught.exception.code, "worker-unavailable")
        self.assertEqual(source.tell(), 0)


class DocumentWorkerProtocolTests(unittest.TestCase):
    _NONCE = "a" * 32

    def _request(
        self,
        data: bytes,
        *,
        tampered_digest: bool = False,
        extension: str = ".txt",
        declared_media_type: str = "text/plain",
    ) -> io.BytesIO:
        stream = io.BytesIO()
        stream.write(
            encode_frame(
                {
                    "protocolVersion": "1.0",
                    "jobNonce": self._NONCE,
                    "sequence": 0,
                    "operation": "inspect-document",
                    "extension": extension,
                    "declaredMediaType": declared_media_type,
                }
            )
        )
        for offset in range(0, len(data), 3):
            write_binary_frame(stream, data[offset : offset + 3])
        write_binary_frame(stream, b"")
        stream.write(
            encode_frame(
                {
                    "protocolVersion": "1.0",
                    "jobNonce": self._NONCE,
                    "sequence": 1,
                    "operation": "inspect-end",
                    "inputLength": len(data),
                    "inputSha256": "0" * 64 if tampered_digest else hashlib.sha256(data).hexdigest(),
                }
            )
        )
        stream.seek(0)
        return stream

    def test_streamed_request_is_bound_to_digest_and_returns_typed_verdict(self) -> None:
        data = b"Synthetic text\n"
        output = io.BytesIO()
        run_worker(self._request(data), output, asset_root=Path("unused-for-built-in-inspection"))
        output.seek(0)
        result = read_frame(output, expected_nonce=self._NONCE, expected_sequence=2)
        self.assertEqual(result["operation"], "invoke-result")
        verdict = json.loads(read_binary_frame(output))
        self.assertEqual(
            verdict,
            {
                "status": "accepted",
                "format": "txt",
                "mediaType": "text/plain",
                "sizeBytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            },
        )

    def test_streamed_request_rejects_tampered_digest(self) -> None:
        with self.assertRaisesRegex(WorkerProtocolError, "worker-input-hash-mismatch"):
            run_worker(self._request(b"Synthetic text", tampered_digest=True), io.BytesIO(), asset_root=Path("unused"))

    def test_worker_returns_typed_denial_for_compressed_pdf_xref_action(self) -> None:
        output = io.BytesIO()
        run_worker(
            self._request(_pdf_with_compressed_xref_action(), extension=".pdf", declared_media_type="application/pdf"),
            output,
            asset_root=Path("unused"),
        )
        output.seek(0)
        result = read_frame(output, expected_nonce=self._NONCE, expected_sequence=2)
        self.assertEqual("invoke-result", result["operation"])
        self.assertEqual(
            {"status": "rejected", "code": "unsupported-format"},
            json.loads(read_binary_frame(output)),
        )

    def test_streamed_request_checks_cumulative_cap(self) -> None:
        with (
            patch("workers.windows.plugin_worker.MAX_DOCUMENT_BYTES", 16),
            self.assertRaisesRegex(WorkerProtocolError, "worker-document-oversize"),
        ):
            run_worker(self._request(b"Synthetic text beyond limit"), io.BytesIO(), asset_root=Path("unused"))

    def test_parent_rejects_malformed_worker_verdict(self) -> None:
        for value in (
            b'{"status":"rejected","code":[]}',
            b'{"status":"accepted","format":[],"mediaType":"text/plain","sizeBytes":1,"sha256":"0"}',
            b'{"status":"accepted","format":"pdf","mediaType":"text/plain","sizeBytes":1,"sha256":"0"}',
        ):
            with self.subTest(value=value), self.assertRaises(DocumentInspectionError) as caught:
                document_launcher._decode_verdict(value)
            self.assertEqual(caught.exception.code, "worker-unavailable")

    @unittest.skipUnless(os.name == "nt", "Windows x64 signed LPAC qualification")
    def test_signed_lpac_worker_inspects_stream_over_ten_mib(self) -> None:
        build_value = os.environ.get("RO_W2_SIGNED_WORKER_BUILD")
        sidecar_value = os.environ.get("RO_W2_CORE_SIDECAR_GUARDIAN")
        if not build_value:
            self.skipTest("signed local worker is required")
        build = Path(build_value).resolve(strict=True)
        sidecar = Path(sidecar_value).resolve(strict=True) if sidecar_value else None
        runtime = SignedWorkerRuntime(
            build / "package",
            (build / "inventory.json").read_bytes(),
            (build / "inventory.sig").read_bytes(),
            APPLICATION_INVENTORY_PUBLIC_KEY,
        )
        content = b"Synthetic paper text\n" * 620_000
        self.assertGreater(len(content), 10 * 1_048_576)

        class BoundedSource(io.BytesIO):
            reads: list[int]

            def __init__(self, value: bytes) -> None:
                super().__init__(value)
                self.reads = []

            def read(self, size: int | None = -1) -> bytes:
                if size is None:
                    raise AssertionError("document source read was unbounded")
                self.reads.append(size)
                return super().read(size)

        source = BoundedSource(content)
        observed: list[dict[str, object]] = []
        original_run = connector_launcher._run_signed_worker

        def observe(*args: object, **kwargs: object) -> connector_launcher.WorkerResult:
            try:
                result = original_run(*args, **kwargs)  # type: ignore[arg-type]
            except Exception as exc:
                raise AssertionError(f"signed worker boundary failed: {type(exc).__name__}: {exc}") from exc
            observed.append(result.token)
            return result

        guardian_command = [str(sidecar), "--plugin-acl-guardian"] if sidecar else recovery_guardian._guardian_command()
        with (
            patch.object(document_launcher, "load_installed_worker_runtime", return_value=runtime),
            patch.object(recovery_guardian, "_guardian_command", return_value=guardian_command),
            patch.object(connector_launcher, "_run_signed_worker", side_effect=observe),
        ):
            verdict = inspect_document(source, filename="synthetic.txt", declared_media_type="text/plain")
        self.assertEqual(verdict.format, "txt")
        self.assertEqual(verdict.size_bytes, len(content))
        self.assertEqual(verdict.sha256, hashlib.sha256(content).hexdigest())
        self.assertEqual(source.tell(), len(content))
        self.assertTrue(source.reads)
        self.assertTrue(all(size == 1_048_576 for size in source.reads))
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0]["appContainer"], True)
        self.assertEqual(observed[0]["lessPrivileged"], True)
        self.assertEqual(observed[0]["capabilityCount"], 0)

    @unittest.skipUnless(os.name == "nt", "Windows x64 signed LPAC qualification")
    def test_signed_lpac_worker_format_password_and_size_probes(self) -> None:
        build_value = os.environ.get("RO_W2_SIGNED_WORKER_BUILD")
        sidecar_value = os.environ.get("RO_W2_CORE_SIDECAR_GUARDIAN")
        if not build_value:
            self.skipTest("signed local worker is required")
        build = Path(build_value).resolve(strict=True)
        runtime = SignedWorkerRuntime(
            build / "package",
            (build / "inventory.json").read_bytes(),
            (build / "inventory.sig").read_bytes(),
            APPLICATION_INVENTORY_PUBLIC_KEY,
        )
        guardian_command = (
            [str(Path(sidecar_value).resolve(strict=True)), "--plugin-acl-guardian"]
            if sidecar_value
            else recovery_guardian._guardian_command()
        )

        class BoundedOversizeSource:
            remaining = MAX_DOCUMENT_BYTES + 1

            def read(self, size: int = -1) -> bytes:
                if not 0 < size <= 1_048_576:
                    raise AssertionError("document source read was unbounded")
                count = min(size, self.remaining)
                self.remaining -= count
                return b"x" * count

        cases = [
            (_pdf(), "synthetic.pdf", "application/pdf", "pdf"),
            (b'<article xmlns="http://jats.nlm.nih.gov"><body/></article>', "synthetic.xml", "application/xml", "jats"),
            (b'<TEI xmlns="http://www.tei-c.org/ns/1.0"><text/></TEI>', "synthetic.tei", "application/xml", "tei"),
            (b"<record><title>Synthetic</title></record>", "synthetic.xml", "application/xml", "xml"),
            (b"<html><body><br/>Synthetic</body></html>", "synthetic.html", "text/html", "html"),
            (
                _docx(),
                "synthetic.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "docx",
            ),
        ]
        with (
            patch.object(document_launcher, "load_installed_worker_runtime", return_value=runtime),
            patch.object(recovery_guardian, "_guardian_command", return_value=guardian_command),
        ):
            for data, name, mime, expected in cases:
                with self.subTest(format=expected):
                    verdict = inspect_document(io.BytesIO(data), filename=name, declared_media_type=mime)
                    self.assertEqual(verdict.format, expected)
                    self.assertEqual(verdict.sha256, hashlib.sha256(data).hexdigest())
            with self.assertRaises(DocumentInspectionError) as protected:
                inspect_document(io.BytesIO(_pdf(encrypted=True)), filename="protected.pdf")
            self.assertEqual(protected.exception.code, "password-protected")
            with self.assertRaises(DocumentInspectionError) as oversized:
                inspect_document(
                    cast(BinaryIO, BoundedOversizeSource()),
                    filename="oversized.txt",
                    declared_media_type="text/plain",
                )
            self.assertEqual(oversized.exception.code, "oversize")


if __name__ == "__main__":
    unittest.main()
