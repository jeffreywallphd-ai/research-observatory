"""Actual pinned PDF worker; synthetic bytes, no Native/Core/tier qualification."""

import hashlib
import os
import time
import unittest
import zlib
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
ORIGIN = "http://tauri.localhost/"


def authored_pdf(*, active=False, huge_page=False, compressed_bomb=False):
    content = b"BT /F1 16 Tf 50 700 Td (Synthetic inert page) Tj ET"
    if compressed_bomb:
        compressor = zlib.compressobj()
        pieces = [compressor.compress(b" " * (1024 * 1024)) for _ in range(160)]
        content = b"".join(pieces) + compressor.flush()
    catalog = b"<< /Type /Catalog /Pages 2 0 R"
    if active:
        catalog += b" /OpenAction 6 0 R /Names << /JavaScript << /Names [(Synthetic) 6 0 R] >> >>"
    objects = [
        catalog + b" >>",
        b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 "
        + (b"9000 9000" if huge_page else b"612 792")
        + b"] /Resources << /Font << /F1 3 0 R >> >> /Contents 5 0 R"
        + (b" /Annots [7 0 R 8 0 R]" if active else b"")
        + b" >>",
        b"<< /Length "
        + str(len(content)).encode()
        + (b" /Filter /FlateDecode" if compressed_bomb else b"")
        + b" >>\nstream\n"
        + content
        + b"\nendstream",
    ]
    if active:
        objects.extend([
            b"<< /Type /Action /S /JavaScript /JS (globalThis.viewerDocumentExecuted=true) >>",
            b"<< /Type /Annot /Subtype /Link /Rect [0 0 100 100] "
            b"/A << /S /URI /URI (https://untrusted.invalid/active-source) >> >>",
            b"<< /Type /Annot /Subtype /Widget /Rect [0 0 100 100] "
            b"/AA << /E << /S /Launch /F (untrusted.exe) >> >> >>",
        ])
    payload, offsets = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"), [0]
    for number, value in enumerate(objects, 1):
        offsets.append(len(payload))
        payload.extend(f"{number} 0 obj\n".encode() + value + b"\nendobj\n")
    xref = len(payload)
    payload.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        payload.extend(f"{offset:010d} 00000 n \n".encode())
    payload.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(payload)


class ViewerDecoderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = Path(os.environ["RO_VIEWER_DECODER_FIXTURE"]).resolve()
        if not cls.directory.is_relative_to((REPO / "artifacts/tmp").resolve()):
            raise RuntimeError("decoder-fixture-output-not-owned")
        cls.runtime = sync_playwright().start()
        cls.browser = cls.runtime.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.runtime.stop()

    def probe(self, content):
        context = self.browser.new_context()
        self.addCleanup(context.close)
        requests, errors = [], []

        def route(request):
            url = request.request.url
            requests.append(url)
            if not url.startswith(ORIGIN):
                request.abort()
                return
            name = url.removeprefix(ORIGIN)
            if name == "index.html":
                request.fulfill(
                    status=200,
                    content_type="text/html",
                    body='<!doctype html><html><head><meta http-equiv="Content-Security-Policy" '
                    "content=\"default-src 'self'; script-src 'self'; worker-src 'self'; "
                    "connect-src 'self'\"></head><body><canvas width=\"0\" height=\"0\"></canvas>"
                    '<script type="module" src="/decoder.js"></script></body></html>',
                )
                return
            path = (self.directory / name).resolve()
            if not path.is_relative_to(self.directory) or not path.is_file():
                request.abort()
                return
            request.fulfill(
                status=200,
                content_type="text/javascript" if path.suffix == ".js" else "application/octet-stream",
                body=path.read_bytes(),
            )

        context.route("**/*", route)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.expose_function("readFixture", lambda start, end: list(content[start:end]))
        page.add_init_script(f"window.fixtureLength={len(content)}")
        page.goto(ORIGIN + "index.html")
        deadline, result = time.monotonic() + 30, None
        while time.monotonic() < deadline:
            result = page.evaluate("() => window.decoderResult ?? null")
            if result is not None and "heldAfterClose" in result:
                break
            time.sleep(0.05)
        self.assertIsNotNone(result, "actual decoder did not settle")
        self.assertIn("heldAfterClose", result, "decoder did not finish drain/cleanup")
        self.assertEqual(0, result["heldAfterClose"])
        self.assertEqual([0, 0], result["canvasAfterClose"])
        self.assertFalse(page.evaluate("() => globalThis.viewerDocumentExecuted === true"))
        self.assertFalse(page.locator("a, iframe, form, object, embed").count())
        self.assertFalse([url for url in requests if not url.startswith(ORIGIN)])
        self.assertFalse(errors)
        result["fixtureSHA256"] = hashlib.sha256(content).hexdigest()
        result["localRequestCount"] = len(requests)
        print(result, flush=True)
        return result

    def test_active_actions_links_and_widgets_remain_inert_with_actual_worker(self):
        result = self.probe(authored_pdf(active=True))
        self.assertEqual("rendered", result["outcome"])
        self.assertEqual(1, result["pages"])
        self.assertEqual(1, result["textMatch"])

    def test_missing_page_tree_is_denied_and_fresh_source_recovers(self):
        result = self.probe(b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n")
        self.assertEqual("denied", result["outcome"])
        self.assertEqual("rendered", self.probe(authored_pdf())["outcome"])

    def test_oversized_page_surface_is_denied_before_canvas_allocation(self):
        result = self.probe(authored_pdf(huge_page=True))
        self.assertEqual("denied", result["outcome"])
        self.assertEqual("viewer-resource-limit", result["code"])

    def test_compressed_content_expansion_hits_worker_quota_then_recovers(self):
        result = self.probe(authored_pdf(compressed_bomb=True))
        self.assertEqual("denied", result["outcome"])
        self.assertEqual("rendered", self.probe(authored_pdf())["outcome"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
