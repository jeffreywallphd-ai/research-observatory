"""Fixed offline document parser entry; plaintext exists only in owned memory.

The application, not a document or plugin, supplies the immutable runtime and
model/config tree. Only bounded source/output chunks cross inherited pipes.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from contextlib import closing
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO

from workers.document.inspection import DocumentInspectionError, classify_document
from workers.windows.protocol import (
    MAX_DOCUMENT_CHUNK,
    FrameError,
    read_binary_frame,
    read_frame,
    write_binary_frame,
    write_frame,
)

MAX_SOURCE_BYTES = 128 * 1_048_576
MAX_OUTPUT_BYTES = 64 * 1_048_576
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class ParserWorkerError(ValueError):
    """Content-free parser failure."""


def _source(stream: BinaryIO, request: dict[str, Any]) -> bytes:
    operation = request.get("operation")
    fields = {"protocolVersion", "jobNonce", "sequence", "operation", "format", "inputLength", "inputSha256"}
    if operation == "render-pdf-page":
        fields.add("pageIndex")
    if (
        set(request) != fields
        or operation not in {"parse-document", "inspect-pdf", "render-pdf-page"}
        or (operation != "parse-document" and request.get("format") != "pdf")
        or (
            operation == "render-pdf-page"
            and (type(request.get("pageIndex")) is not int or not 0 <= request["pageIndex"] < 500)
        )
        or request["format"] not in {"pdf", "docx", "jats", "tei", "xml", "html", "txt"}
        or type(request["inputLength"]) is not int
        or not 0 < request["inputLength"] <= MAX_SOURCE_BYTES
        or not isinstance(request["inputSha256"], str)
        or _DIGEST.fullmatch(request["inputSha256"]) is None
    ):
        raise ParserWorkerError("parser-request-invalid")
    source = bytearray()
    digest = hashlib.sha256()
    while True:
        chunk = read_binary_frame(stream)
        if len(chunk) > MAX_DOCUMENT_CHUNK or len(source) + len(chunk) > request["inputLength"]:
            raise ParserWorkerError("parser-source-invalid")
        if not chunk:
            break
        source.extend(chunk)
        digest.update(chunk)
    end = read_frame(stream, expected_nonce=request["jobNonce"], expected_sequence=1)
    if (
        end != {"protocolVersion": "1.0", "jobNonce": request["jobNonce"], "sequence": 1, "operation": "parse-end"}
        or len(source) != request["inputLength"]
        or digest.hexdigest() != request["inputSha256"]
    ):
        raise ParserWorkerError("parser-source-invalid")
    return bytes(source)


def inspect_pdf(source: bytes, assets: Path) -> bytes:
    """A separate degraded attempt, using the same admitted isolated runtime."""
    classify_document(source, extension=".pdf", declared_media_type=None)
    _package(assets)
    geometries = _pdf_admission(source)
    import pypdfium2 as pdfium  # type: ignore[import-not-found]

    pages = []
    characters = 0
    with pdfium.PdfDocument(source) as document:
        if len(document) != len(geometries):
            raise ParserWorkerError("parser-input-invalid")
        for index in range(len(document)):
            with closing(document[index]) as page, closing(page.get_textpage()) as text_page:
                count = text_page.count_chars()
                if type(count) is not int or count < 0 or characters + count > 8 * 1_048_576:
                    raise ParserWorkerError("parser-resource-limit")
                characters += count
                text = text_page.get_text_range(index=0, count=count) if count else ""
                pages.append({"geometry": geometries[index], "text": text})
    raw = json.dumps(
        {
            "schemaVersion": "1.0",
            "documentType": "pdf-inspection-output",
            "inputSha256": hashlib.sha256(source).hexdigest(),
            "inputLength": len(source),
            "pages": pages,
        },
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(raw) > MAX_OUTPUT_BYTES:
        raise ParserWorkerError("parser-resource-limit")
    return raw


def render_pdf_page(source: bytes, page_index: int, assets: Path) -> bytes:
    """Decode only the requested page, after the shared hostile-PDF admission."""
    import math

    from workers.document.pdf_geometry import PdfPageGeometry

    classify_document(source, extension=".pdf", declared_media_type=None)
    _package(assets)
    geometries = _pdf_admission(source)
    if type(page_index) is not int or not 0 <= page_index < len(geometries):
        raise ParserWorkerError("parser-input-invalid")
    geometry = PdfPageGeometry.from_native(geometries[page_index])
    width, height = geometry.admit_render()
    import pypdfium2 as pdfium

    with pdfium.PdfDocument(source) as document, closing(document[page_index]) as page:
        if len(document) != len(geometries) or any(
            not math.isclose(actual, expected, rel_tol=1e-6, abs_tol=1e-4)
            for actual, expected in zip(page.get_size(), geometry.display_size, strict=True)
        ):
            raise ParserWorkerError("parser-input-unsupported")
        with closing(page.render(scale=1.5)) as bitmap:
            if (bitmap.width, bitmap.height) != (width, height):
                raise ParserWorkerError("parser-input-unsupported")
            with bitmap.to_pil() as image:
                from PIL.PngImagePlugin import PngInfo  # type: ignore[import-not-found]

                metadata = PngInfo()
                metadata.add_text(
                    "RO_SOURCE_GEOMETRY",
                    json.dumps(
                        {"schemaVersion": "1.0", "pageIndex": page_index, "geometry": geometries[page_index]},
                        ensure_ascii=True,
                        allow_nan=False,
                        separators=(",", ":"),
                    ),
                )
                output = BytesIO()
                image.save(output, format="PNG", pnginfo=metadata)
                raw = output.getvalue()
    if not 0 < len(raw) <= MAX_OUTPUT_BYTES:
        raise ParserWorkerError("parser-resource-limit")
    return raw


def _package(assets: Path) -> None:
    from workers.document.parser_package import ParserPackageError, package_observations

    try:
        package_observations(assets.parent, check_installed_versions=True)
    except ParserPackageError:
        raise ParserWorkerError("parser-assets-unavailable") from None


def parse_document(source: bytes, kind: str, assets: Path) -> bytes:
    if kind in {"jats", "tei", "xml", "html"}:
        from workers.document.native_parsing import parse_native_structure

        return parse_native_structure(source, format=kind, cancelled=lambda: False)
    classify_document(source, extension=f".{kind}", declared_media_type=None)
    if kind == "txt":
        try:
            return json.dumps(
                {
                    "schemaVersion": "1.0",
                    "documentType": "bounded-text-parser-output",
                    "text": source.decode("utf-8-sig"),
                },
                ensure_ascii=False,
            ).encode("utf-8")
        except UnicodeError:
            raise ParserWorkerError("malformed-content") from None
    # Set offline and no-compile behavior before importing any inference module.
    os.environ.update(
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        HF_HUB_DISABLE_TELEMETRY="1",
        TOKENIZERS_PARALLELISM="false",
        OMP_NUM_THREADS="4",
        MKL_NUM_THREADS="4",
        OPENBLAS_NUM_THREADS="4",
        NUMEXPR_NUM_THREADS="4",
        PYTHONDONTWRITEBYTECODE="1",
        TORCH_COMPILE_DISABLE="1",
        TORCHINDUCTOR_CACHE_DIR=str(assets.parent / "torch-disabled-cache"),
    )
    _builtin_mime_types()
    _package(assets)
    source_pages = _pdf_admission(source) if kind == "pdf" else []
    import torch  # type: ignore[import-not-found]
    from docling.backend.docling_parse_backend import DoclingParseDocumentBackend  # type: ignore[import-not-found]
    from docling.datamodel.accelerator_options import (  # type: ignore[import-not-found]
        AcceleratorDevice,
        AcceleratorOptions,
    )
    from docling.datamodel.base_models import DocumentStream, InputFormat  # type: ignore[import-not-found]
    from docling.datamodel.pipeline_options import (  # type: ignore[import-not-found]
        LayoutObjectDetectionOptions,
        PdfPipelineOptions,
        TableFormerMode,
        TableStructureOptions,
    )
    from docling.datamodel.settings import settings  # type: ignore[import-not-found]
    from docling.datamodel.stage_model_specs import ObjectDetectionModelSpec  # type: ignore[import-not-found]
    from docling.document_converter import DocumentConverter, PdfFormatOption  # type: ignore[import-not-found]

    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    settings.inference.compile_torch_models = False
    options = PdfPipelineOptions(
        artifacts_path=assets,
        enable_remote_services=False,
        allow_external_plugins=False,
        do_ocr=False,
        do_table_structure=True,
        do_code_enrichment=False,
        do_formula_enrichment=False,
        do_picture_classification=False,
        do_picture_description=False,
        generate_page_images=False,
        generate_picture_images=False,
        generate_table_images=False,
        images_scale=1.0,
        accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CPU, num_threads=4),
        table_structure_options=TableStructureOptions(mode=TableFormerMode.ACCURATE, do_cell_matching=True),
        layout_options=LayoutObjectDetectionOptions(
            model_spec=ObjectDetectionModelSpec(
                name="docling_layout_heron",
                repo_id="docling-project/docling-layout-heron",
                revision="8f39ad3c0b4c58e9c2d2c84a38465abf757272d8",
            )
        ),
    )

    class AdmittedPdfBackend(DoclingParseDocumentBackend):
        def load_page(self, page_no: int, create_words: bool = True, create_textlines: bool = True):
            from workers.document.pdf_geometry import PdfPageGeometry

            if type(page_no) is not int or not 0 <= page_no < len(source_pages):
                raise ParserWorkerError("parser-resource-limit")
            geometry = PdfPageGeometry.from_native(source_pages[page_no])
            page = super().load_page(page_no, create_words=create_words, create_textlines=create_textlines)
            original_render = page.get_page_image

            def bounded_render(scale=1.0, cropbox=None):
                geometry.admit_render(scale)
                return original_render(scale=scale, cropbox=cropbox)

            page.get_page_image = bounded_render
            return page

    converter = DocumentConverter(
        allowed_formats=[InputFormat.PDF, InputFormat.DOCX],
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options, backend=AdmittedPdfBackend)},
    )
    converted = converter.convert(
        DocumentStream(name=f"document.{kind}", stream=BytesIO(source)),
        max_num_pages=500,
        max_file_size=MAX_SOURCE_BYTES,
    )
    if converted.status.value not in {"success", "partial_success"}:
        raise ParserWorkerError("parser-failed")
    document = converted.document.export_to_dict()
    locations, geometry_warnings = _mapped_locations(document, source_pages)
    raw = json.dumps(
        {
            "schemaVersion": "2.0",
            "documentType": "docling-parser-output",
            "inputSha256": hashlib.sha256(source).hexdigest(),
            "inputLength": len(source),
            "format": kind,
            "status": converted.status.value,
            "document": document,
            "sourcePages": source_pages,
            "locations": locations,
            "geometryWarnings": geometry_warnings,
        },
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(raw) > MAX_OUTPUT_BYTES:
        raise ParserWorkerError("parser-output-oversize")
    return raw


def _pdf_admission(source: bytes) -> list[dict[str, Any]]:
    from docling_parse.pdf_parsers import pdf_parser  # type: ignore[import-not-found]

    from workers.document.pdf_geometry import PdfGeometryError, PdfPageGeometry

    parser = pdf_parser("fatal")
    if not parser.load_document_from_bytesio("ro-original", BytesIO(source), None, False):
        raise ParserWorkerError("parser-input-invalid")
    try:
        count = parser.number_of_pages("ro-original")
        if type(count) is not int or not 0 < count <= 500:
            raise ParserWorkerError("parser-resource-limit")
        pages = [parser.page_admission("ro-original", index) for index in range(count)]
        for page in pages:
            # TableFormer requests scale 2; the backend actually renders at 3.
            PdfPageGeometry.from_native(page).admit_render(2.0)
        return pages
    except RuntimeError as problem:
        # Only closed application-owned native codes cross the process boundary.
        # All other decoder exception messages stay private and are discarded.
        if str(problem) == "parser-image-codec-unverified":
            raise ParserWorkerError("parser-input-unsupported") from None
        if str(problem) in {"parser-page-pixel-limit", "parser-resource-limit"}:
            raise ParserWorkerError("parser-resource-limit") from None
        raise ParserWorkerError("parser-input-invalid") from None
    except PdfGeometryError:
        raise ParserWorkerError("parser-resource-limit") from None
    finally:
        parser.unload_document("ro-original")


def _mapped_locations(document: dict[str, Any], pages: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    from workers.document.pdf_geometry import PdfGeometryError, PdfPageGeometry

    locations = {}
    warnings = []
    for group in ("texts", "tables", "pictures", "key_value_items", "form_items"):
        for index, item in enumerate(document.get(group, [])):
            key = f"#/{group}/{index}"
            provenances = item.get("prov", [])
            if len(provenances) != 1:
                if provenances:
                    warnings.append(key)
                continue
            prov = provenances[0]
            page_no = prov.get("page_no")
            if type(page_no) is not int or not 0 < page_no <= len(pages):
                continue
            geometry = PdfPageGeometry.from_native(pages[page_no - 1])
            displayed = document["pages"][str(page_no)]["size"]
            size = (displayed["width"], displayed["height"])

            def mapped(bbox, *, geometry=geometry, size=size, page_no=page_no, key=key):
                try:
                    x0, y0, x1, y1 = geometry.region(bbox, size)
                    if x0 < 0 or y0 < 0 or x1 > geometry.width_points or y1 > geometry.height_points:
                        raise PdfGeometryError("parser-geometry-outside-page")
                    return {
                        "kind": "page-region",
                        "page_index": page_no - 1,
                        "x0": x0,
                        "y0": y0,
                        "x1": x1,
                        "y1": y1,
                        "unit": "points",
                        "origin": "top-left",
                        "frame": "unrotated-source-page",
                    }
                except PdfGeometryError:
                    warnings.append(key)
                    return {"kind": "unavailable", "reason": "unsupported-location"}

            locations[key] = mapped(prov["bbox"])
            if group == "tables":
                for cell_index, cell in enumerate(item["data"]["table_cells"]):
                    if cell.get("bbox") is not None:
                        locations[f"{key}/cell/{cell_index}"] = mapped(cell["bbox"])
    return locations, sorted(set(warnings))


def _builtin_mime_types() -> None:
    import mimetypes

    # The pinned Python MimeTypes constructor recursively initializes the
    # module unless inited is set. Initialize its built-in table explicitly;
    # no ambient registry or MIME file may influence this offline worker.
    # MIME guesses are not intake authority: classify_document already checked
    # the independently selected source format above.
    mimetypes.inited = True
    mimetypes._db = mimetypes.MimeTypes(filenames=())  # type: ignore[attr-defined]
    mimetypes.init(files=[])


def run(stdin: BinaryIO, stdout: BinaryIO, assets: Path) -> None:
    request = read_frame(stdin, expected_nonce=None, expected_sequence=0)
    source = _source(stdin, request)
    failure = None
    output = b""
    try:
        if request["operation"] == "inspect-pdf":
            output = inspect_pdf(source, assets)
        elif request["operation"] == "render-pdf-page":
            output = render_pdf_page(source, request["pageIndex"], assets)
        else:
            output = parse_document(source, request["format"], assets)
    except MemoryError:
        failure = "parser-memory-limit"
    except DocumentInspectionError:
        failure = "parser-input-invalid"
    except ParserWorkerError as problem:
        failure = (
            str(problem)
            if str(problem)
            in {
                "parser-assets-unavailable",
                "parser-resource-limit",
                "parser-input-invalid",
                "parser-input-unsupported",
            }
            else "parser-failed"
        )
    except Exception:
        failure = "parser-failed"
    if failure is not None:
        write_frame(
            stdout,
            {
                "protocolVersion": "1.0",
                "jobNonce": request["jobNonce"],
                "sequence": 2,
                "operation": "parse-failure",
                "code": failure,
            },
        )
        return
    if not 0 < len(output) <= MAX_OUTPUT_BYTES:
        raise ParserWorkerError("parser-output-oversize")
    write_frame(
        stdout,
        {
            "protocolVersion": "1.0",
            "jobNonce": request["jobNonce"],
            "sequence": 2,
            "operation": "parse-result",
            "outputLength": len(output),
            "outputSha256": hashlib.sha256(output).hexdigest(),
        },
    )
    for index in range(0, len(output), MAX_DOCUMENT_CHUNK):
        write_binary_frame(stdout, output[index : index + MAX_DOCUMENT_CHUNK])
    write_binary_frame(stdout, b"")


def main() -> int:
    try:
        root = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
        # Preserve the private protocol pipe before redirecting both Python and
        # CRT/native stdout to the bounded stderr sink. Third-party messages are
        # never interpreted as framing or retained by the product parent.
        descriptor = os.dup(sys.stdout.fileno())
        try:
            os.dup2(sys.stderr.fileno(), sys.stdout.fileno(), inheritable=False)
            if os.name == "nt":
                import ctypes
                import msvcrt
                from ctypes import wintypes

                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.SetStdHandle.argtypes = [wintypes.DWORD, wintypes.HANDLE]
                kernel.SetStdHandle.restype = wintypes.BOOL
                if not kernel.SetStdHandle(0xFFFFFFF5, msvcrt.get_osfhandle(sys.stderr.fileno())):
                    raise ParserWorkerError("parser-output-channel-unavailable")
            protocol = os.fdopen(descriptor, "wb", buffering=0)
        except BaseException:
            os.close(descriptor)
            raise
        with protocol:
            run(sys.stdin.buffer, protocol, root / "parser-assets")
        return 0
    except FrameError, ParserWorkerError, DocumentInspectionError:
        return 2
    except Exception:
        # Private source/parser exceptions never become telemetry or IPC text.
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
