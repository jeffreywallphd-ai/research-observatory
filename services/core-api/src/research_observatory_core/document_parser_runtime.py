"""Fixed installed Windows parser adapter; no project-supplied executable or key."""

from __future__ import annotations

import hashlib
import os
import sys
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass

from .parsing.contracts import ParserAsset, ParserDescriptor
from .parsing.docling import DOCLING_MEDIA_TYPE
from .parsing.requests import ParseRequest
from .ports.docling_parsing import AuthenticatedDoclingDelivery
from .ports.native_parsing import AuthenticatedNativeDelivery
from .ports.parsing import ParseProblem, RawParserStagerPort, ReadOnlyDocumentSource
from .ports.pdf_inspection import AuthenticatedInspectionDelivery
from .ports.pdf_pages import AuthenticatedPageDelivery


@dataclass(frozen=True, slots=True)
class InstalledParser:
    runtime: object
    descriptor: ParserDescriptor


class InstalledDocumentParserRuntime:
    def load(self) -> InstalledParser:
        loaded = None
        if os.name == "nt" and getattr(sys, "frozen", False) is True:
            try:
                from workers.document.parser_package import package_observations
                from workers.windows.runtime_inventory import PARSER_IMAGE_DIRECTORY, load_installed_parser_runtime

                runtime = load_installed_parser_runtime()
                config, assets = package_observations(runtime.package / PARSER_IMAGE_DIRECTORY / "_internal")
                descriptor = ParserDescriptor(
                    parser_id="ro-docling-cpu",
                    version="2.126.0",
                    kind="docling-cpu",
                    input_formats=("pdf", "docx"),
                    configuration_version="docling-cpu-1",
                    configuration_sha256=config,
                    assets=(
                        ParserAsset(component="docling-assets", version="4.0.2", sha256=assets),
                        ParserAsset(
                            component="parser-runtime",
                            version="ro-parser-cpu-1",
                            sha256=hashlib.sha256(runtime.inventory_bytes).hexdigest(),
                        ),
                    ),
                )
                loaded = InstalledParser(runtime, descriptor)
            except Exception:
                pass
        if loaded is None:
            raise ParseProblem("parser-runtime-unavailable")
        return loaded

    def load_inspection(self) -> InstalledParser:
        base = self.load()
        return InstalledParser(
            base.runtime,
            ParserDescriptor(
                parser_id="ro-page-text-fallback",
                version="1.0.0",
                kind="degraded-inspection",
                input_formats=("pdf",),
                configuration_version="pdf-inspection-1",
                configuration_sha256=base.descriptor.configuration_sha256,
                assets=tuple(asset for asset in base.descriptor.assets if asset.component == "parser-runtime"),
            ),
        )

    def load_text(self) -> InstalledParser:
        base = self.load()
        return InstalledParser(
            base.runtime,
            ParserDescriptor(
                parser_id="ro-native-text",
                version="1.0.0",
                kind="native",
                input_formats=("plain-text",),
                configuration_version="native-text-1",
                configuration_sha256=base.descriptor.configuration_sha256,
                assets=tuple(asset for asset in base.descriptor.assets if asset.component == "parser-runtime"),
            ),
        )

    def load_native(self) -> InstalledParser:
        base = self.load()
        return InstalledParser(
            base.runtime,
            ParserDescriptor(
                parser_id="ro-native-structured",
                version="1.0.0",
                kind="native",
                input_formats=("jats", "tei", "xml", "html"),
                configuration_version="native-1",
                configuration_sha256=base.descriptor.configuration_sha256,
                assets=tuple(asset for asset in base.descriptor.assets if asset.component == "parser-runtime"),
            ),
        )

    def run(
        self,
        installed: InstalledParser,
        request: ParseRequest,
        source: ReadOnlyDocumentSource,
        *,
        cancelled: Callable[[], bool],
        page_index: int | None = None,
    ) -> bytes:
        output = None
        failure = "parser-runtime-unavailable"
        if os.name == "nt" and getattr(sys, "frozen", False) is True:
            with suppress(Exception):
                output, failure = _run_installed(installed, request, source, cancelled=cancelled, page_index=page_index)
        if output is None:
            raise ParseProblem(failure)
        return output


def _run_installed(installed, request, source, *, cancelled, page_index=None):
    from workers.windows.lpac_launcher import LPACError
    from workers.windows.parsing_launcher import parse_document
    from workers.windows.runtime_inventory import SignedWorkerRuntime

    request = ParseRequest.model_validate(request)
    if not isinstance(installed.runtime, SignedWorkerRuntime) or request.binding.producer != installed.descriptor:
        raise ValueError
    operation = (
        "render-pdf-page"
        if page_index is not None
        else "inspect-pdf"
        if installed.descriptor.kind == "degraded-inspection"
        else "parse-document"
    )
    try:
        result = parse_document(
            installed.runtime,
            source,
            format="txt" if request.binding.source.format == "plain-text" else request.binding.source.format,
            length=request.binding.source.byte_length,
            sha256=request.binding.source.object_sha256,
            cancelled=cancelled,
            operation=operation,
            page_index=page_index,
        )
        return result.output, "parser-runtime-unavailable"
    except LPACError as problem:
        return None, {
            "lpac-worker-timeout": "parser-timeout",
            "lpac-worker-memory-limit": "parser-memory-limit",
            "lpac-parser-failed": "parser-failed",
            "lpac-parser-memory-limit": "parser-memory-limit",
            "lpac-parser-input-invalid": "parser-input-invalid",
            "lpac-parser-input-unsupported": "parser-input-unsupported",
            "lpac-parser-resource-limit": "parser-resource-limit",
            "lpac-parser-assets-unavailable": "parser-assets-unavailable",
        }.get(str(problem), "parser-runtime-unavailable")


class _InstalledWorker:
    """Trusted Core composition supplies protected, attempt-fenced staging.

    The worker receives no staging callback/repository. Receipts are constructed
    only after its authenticated output has been retained in encrypted storage.
    """

    def __init__(
        self,
        runtime: InstalledDocumentParserRuntime,
        installed: InstalledParser,
        stage_raw: RawParserStagerPort,
    ) -> None:
        self._runtime, self._installed, self._stage = runtime, installed, stage_raw


class InstalledDoclingWorker(_InstalledWorker):
    def parse_source(
        self, request: ParseRequest, source: ReadOnlyDocumentSource, *, cancelled: Callable[[], bool]
    ) -> AuthenticatedDoclingDelivery:
        self._stage.validate_request(request)
        raw = self._runtime.run(self._installed, request, source, cancelled=cancelled)
        if cancelled():
            raise ParseProblem("parser-failed")
        receipt = self._stage(request, raw, media_type=DOCLING_MEDIA_TYPE, cancelled=cancelled)
        return AuthenticatedDoclingDelivery(
            raw, self._installed.descriptor, request.binding.attempt.job_id, request.binding.attempt.attempt_id, receipt
        )


class InstalledNativeWorker(_InstalledWorker):
    def parse_source(self, request, source, *, cancelled) -> AuthenticatedNativeDelivery:
        from .parsing.native_contracts import NATIVE_MEDIA_TYPE

        self._stage.validate_request(request)
        raw = self._runtime.run(self._installed, request, source, cancelled=cancelled)
        if cancelled():
            raise ParseProblem("parser-failed")
        receipt = self._stage(request, raw, media_type=NATIVE_MEDIA_TYPE, cancelled=cancelled)
        return AuthenticatedNativeDelivery(
            raw, self._installed.descriptor, request.binding.attempt.job_id, request.binding.attempt.attempt_id, receipt
        )


class InstalledInspectionWorker(_InstalledWorker):
    def parse_source(self, request, source, *, cancelled) -> AuthenticatedInspectionDelivery:
        from .parsing.inspection import INSPECTION_MEDIA_TYPE

        self._stage.validate_request(request)
        raw = self._runtime.run(self._installed, request, source, cancelled=cancelled)
        if cancelled():
            raise ParseProblem("parser-failed")
        receipt = self._stage(request, raw, media_type=INSPECTION_MEDIA_TYPE, cancelled=cancelled)
        return AuthenticatedInspectionDelivery(
            raw, self._installed.descriptor, request.binding.attempt.job_id, request.binding.attempt.attempt_id, receipt
        )


class InstalledTextWorker(_InstalledWorker):
    def parse_source(self, request, source, *, cancelled) -> AuthenticatedNativeDelivery:
        from .parsing.text import TEXT_MEDIA_TYPE

        self._stage.validate_request(request)
        raw = self._runtime.run(self._installed, request, source, cancelled=cancelled)
        if cancelled():
            raise ParseProblem("parser-failed")
        receipt = self._stage(request, raw, media_type=TEXT_MEDIA_TYPE, cancelled=cancelled)
        return AuthenticatedNativeDelivery(
            raw, self._installed.descriptor, request.binding.attempt.job_id, request.binding.attempt.attempt_id, receipt
        )


class InstalledPageWorker(_InstalledWorker):
    def render_page(self, request, source, page_index, *, cancelled) -> AuthenticatedPageDelivery:
        from .parsing.pages import decode_png_page

        if type(page_index) is not int or not 0 <= page_index < 500 or request.binding.source.format != "pdf":
            raise ParseProblem("parse-request-invalid")
        self._stage.validate_request(request)
        raw = self._runtime.run(self._installed, request, source, cancelled=cancelled, page_index=page_index)
        valid = False
        try:
            decode_png_page(raw, page_index)
            valid = not cancelled()
        except Exception:
            pass
        if not valid:
            raise ParseProblem("parse-output-invalid")
        receipt = self._stage(request, raw, media_type="image/png", cancelled=cancelled, page_index=page_index)
        return AuthenticatedPageDelivery(
            raw,
            self._installed.descriptor,
            request.binding.attempt.job_id,
            request.binding.attempt.attempt_id,
            page_index,
            receipt,
        )


class InstalledParserPipeline:
    """Trusted Core composition for one admitted, leased workflow attempt.

    It returns staged values only. Human acceptance and canonical publication
    belong to the document revision service. Fallback requires an independently
    admitted new attempt and its recorded selection; this class never starts it.
    """

    def __init__(self, *, stage_raw: RawParserStagerPort, sources, runtime=None) -> None:
        self._runtime = runtime or InstalledDocumentParserRuntime()
        self._stage, self._sources = stage_raw, sources

    def _selection(self, request):
        from .parsing.docling import DoclingDocumentParser
        from .parsing.inspection import PdfInspectionAdapter
        from .parsing.native import NativeStructuredParser
        from .parsing.text import BoundedTextParser

        choices = {
            "docling-cpu": (self._runtime.load, InstalledDoclingWorker, DoclingDocumentParser),
            "native": (self._runtime.load_native, InstalledNativeWorker, NativeStructuredParser),
            "degraded-inspection": (self._runtime.load_inspection, InstalledInspectionWorker, PdfInspectionAdapter),
        }
        selected = None
        try:
            request = ParseRequest.model_validate(request)
            load, worker, adapter = (
                (self._runtime.load_text, InstalledTextWorker, BoundedTextParser)
                if request.binding.producer.parser_id == "ro-native-text"
                else choices[request.binding.producer.kind]
            )
            installed = load()
            if installed.descriptor == request.binding.producer:
                selected = installed, worker, adapter
        except Exception:
            pass
        if selected is None:
            raise ParseProblem("parse-producer-mismatch")
        return selected

    def _parser(self, request):
        installed, worker, adapter = self._selection(request)
        return adapter(worker(self._runtime, installed, self._stage))

    def stage(self, request, *, actor, cancelled):
        from .parsing.pipeline import stage_parse

        return stage_parse(request, self._parser(request), self._sources, actor=actor, cancelled=cancelled)

    def render(self, request, page_index, *, actor, cancelled):
        from .parsing.pages import render_page

        installed, _, _ = self._selection(request)
        return render_page(
            request,
            page_index,
            InstalledPageWorker(self._runtime, installed, self._stage),
            self._sources,
            actor=actor,
            cancelled=cancelled,
        )
