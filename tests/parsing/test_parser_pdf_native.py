"""Real selected native parser checks, enabled only with an explicit built image."""

from __future__ import annotations

import importlib.util
import os
import struct
import unittest
import zlib
from io import BytesIO
from pathlib import Path

from tests.parsing.pdf_fixtures import pdf_objects, scholarly_pdf


@unittest.skipUnless(os.environ.get("RO_PARSER_NATIVE_TEST"), "explicit native build required")
class NativePageAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Upstream native resource discovery imports this package through the
        # Python C API. Run these checks in the isolated parser environment;
        # a bare Core environment is not a selected native runtime.
        if importlib.util.find_spec("docling_parse") is None:
            raise RuntimeError("native-test-requires-isolated-docling-resource-package")
        path = Path(os.environ["RO_PARSER_NATIVE_TEST"])
        spec = importlib.util.spec_from_file_location("pdf_parsers", path)
        if spec is None or spec.loader is None:
            raise RuntimeError("native-test-input-invalid")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.module = module

    def admission(self, data: bytes) -> dict:
        parser = self.module.pdf_parser("fatal")
        self.assertTrue(parser.load_document_from_bytesio("synthetic", BytesIO(data), None, False))
        try:
            return parser.page_admission("synthetic", 0)
        finally:
            parser.unload_document("synthetic")

    def test_original_boxes_rotation_and_indirect_scale(self) -> None:
        data = pdf_objects(
            [
                b"<< /Type /Catalog /Pages 2 0 R >>",
                b"<< /Type /Pages /Count 1 /Kids [3 0 R] /MediaBox [-20 -30 592 762] /Rotate 90 >>",
                b"<< /Type /Page /Parent 2 0 R /CropBox [10 20 550 730] /UserUnit 4 0 R /Resources << >> >>",
                b"2",
            ]
        )
        self.assertEqual(
            self.admission(data),
            {
                "mediaBox": [-20.0, -30.0, 592.0, 762.0],
                "cropBox": [10.0, 20.0, 550.0, 730.0],
                "rotation": 90,
                "userUnit": 2.0,
                "imagePixels": 0,
            },
        )

    def test_absence_defaults_and_invalid_values_deny(self) -> None:
        self.assertEqual(self.admission(scholarly_pdf())["userUnit"], 1.0)
        for value in (b"0", b"-2", b"75001", b"(2)", b"null"):
            with self.subTest(value=value), self.assertRaisesRegex(RuntimeError, "parser-page-scale-invalid"):
                self.admission(
                    pdf_objects(
                        [
                            b"<< /Type /Catalog /Pages 2 0 R >>",
                            b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
                            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /UserUnit "
                            + value
                            + b" /Resources << >> >>",
                        ]
                    )
                )

    def test_image_and_crossed_mask_dimensions_deny_before_decode(self) -> None:
        for width, height, mask in ((10000, 10000, None), (4000000000, 2, None), (10000, 2, (2, 10000))):
            with self.subTest(width=width, height=height, mask=mask):
                objects = [
                    b"<< /Type /Catalog /Pages 2 0 R >>",
                    b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
                    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                    b"/Resources << /XObject << /Im 4 0 R >> >> >>",
                    (
                        f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} "
                        "/BitsPerComponent 8 /ColorSpace /DeviceGray "
                    ).encode()
                    + (b"/SMask 5 0 R " if mask else b"")
                    + b"/Length 0 >>\nstream\n\nendstream",
                ]
                if mask:
                    objects.append(
                        (
                            f"<< /Type /XObject /Subtype /Image /Width {mask[0]} /Height {mask[1]} "
                            "/BitsPerComponent 8 /ColorSpace /DeviceGray /Length 0 >>\nstream\n\nendstream"
                        ).encode()
                    )
                with self.assertRaisesRegex(RuntimeError, "parser-page-pixel-limit"):
                    self.admission(pdf_objects(objects))

    def test_inline_image_limit_and_jpeg_dictionary_substitution(self) -> None:
        for content, expected in (
            (b"BI /W 10000 /H 10000 /BPC 8 /CS /G ID x EI", "parser-page-pixel-limit"),
            (
                b"BI /W 2 /H 2 /BPC 8 /CS /RGB /F /DCT ID "
                + b"\xff\xd8\xff\xc0\x00\x11\x08\x27\x10\x27\x10\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00\xff\xd9 EI",
                "parser-page-pixel-limit",
            ),
        ):
            objects = [
                b"<< /Type /Catalog /Pages 2 0 R >>",
                b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << >> /Contents 4 0 R >>",
                b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
            ]
            with self.subTest(expected=expected), self.assertRaisesRegex(RuntimeError, expected):
                self.admission(pdf_objects(objects))

    def test_valid_small_inline_image_is_admitted(self) -> None:
        content = b"BI /W 2 /H 2 /BPC 8 /CS /G ID abcd EI"
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << >> /Contents 4 0 R >>",
            b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        ]
        self.assertEqual(self.admission(pdf_objects(objects))["imagePixels"], 4)

    def test_resource_names_and_glyph_appearances_cannot_bypass_admission(self) -> None:
        huge = b"<< /Type /XObject /Subtype /Image /Width 10000 /Height 10000 /Length 0 >>\nstream\n\nendstream"
        inline = b"BI /W 10000 /H 10000 /BPC 8 /CS /G ID x EI"
        stream = b"<< /Length " + str(len(inline)).encode() + b" >>\nstream\n" + inline + b"\nendstream"
        for page, obj in (
            (b"/Resources << /XObject << /P 4 0 R >> >>", huge),
            (b"/Resources << /XObject << /Parent 4 0 R >> >>", huge),
            (b"/Resources << /Font << /F << /Type /Font /Subtype /Type3 /CharProcs << /P 4 0 R >> >> >> >>", stream),
            (b"/Resources << >> /Annots [ << /Type /Annot /Subtype /Widget /P 3 0 R /AP << /N 4 0 R >> >> ]", stream),
        ):
            with self.subTest(page=page), self.assertRaisesRegex(RuntimeError, "parser-page-pixel-limit"):
                self.admission(
                    pdf_objects(
                        [
                            b"<< /Type /Catalog /Pages 2 0 R >>",
                            b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
                            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] " + page + b" >>",
                            obj,
                        ]
                    )
                )

    def test_predictor_parameters_deny_before_native_row_allocation(self) -> None:
        for params, code in (
            (b"/Predictor 15 /Columns 1 /Colors 400000000 /BitsPerComponent 8", "parser-resource-limit"),
            (b"/Predictor 15 /Columns 1000000000 /Colors 1 /BitsPerComponent 8", "parser-image-header-mismatch"),
        ):
            encoded = zlib.compress(b"\x00\x00")
            image = (
                b"<< /Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceGray "
                b"/BitsPerComponent 8 /Filter /FlateDecode /DecodeParms << "
                + params
                + b" >> /Length "
                + str(len(encoded)).encode()
                + b" >>\nstream\n"
                + encoded
                + b"\nendstream"
            )
            with self.subTest(params=params), self.assertRaisesRegex(RuntimeError, code):
                self.admission(
                    pdf_objects(
                        [
                            b"<< /Type /Catalog /Pages 2 0 R >>",
                            b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
                            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                            b"/Resources << /XObject << /Im 4 0 R >> >> >>",
                            image,
                        ]
                    )
                )

    def test_jpx_tile_component_fanout_is_rejected_before_codec(self) -> None:
        # Extent is one pixel but origin/tile geometry would allocate billions
        # of tile records during OpenJPEG header parsing.
        siz = (
            struct.pack(">HHIIIIIIIIH", 41, 0, 4000000000, 4000000000, 3999999999, 3999999999, 1, 1, 0, 0, 1)
            + b"\x07\x01\x01"
        )
        encoded = b"\xff\x4f\xff\x51" + siz
        image = (
            b"<< /Type /XObject /Subtype /Image /Width 1 /Height 1 /Filter /JPXDecode /Length "
            + str(len(encoded)).encode()
            + b" >>\nstream\n"
            + encoded
            + b"\nendstream"
        )
        with self.assertRaisesRegex(RuntimeError, "parser-image-header-invalid|parser-resource-limit"):
            self.admission(
                pdf_objects(
                    [
                        b"<< /Type /Catalog /Pages 2 0 R >>",
                        b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
                        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                        b"/Resources << /XObject << /Im 4 0 R >> >> >>",
                        image,
                    ]
                )
            )

    def test_jbig2_is_explicitly_unsupported_before_either_decoder(self) -> None:
        for subtype in (b"/Subtype /Image /Width 1 /Height 1", b""):
            image = b"<< " + subtype + b" /Filter /JBIG2Decode /Length 1 >>\nstream\nx\nendstream"
            with self.subTest(subtype=subtype), self.assertRaisesRegex(RuntimeError, "parser-image-codec-unverified"):
                self.admission(
                    pdf_objects(
                        [
                            b"<< /Type /Catalog /Pages 2 0 R >>",
                            b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
                            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                            b"/Resources << /XObject << /P 4 0 R >> >> >>",
                            image,
                        ]
                    )
                )

    def test_missing_original_media_box_is_never_reported_as_letter(self) -> None:
        parser = self.module.pdf_parser("fatal")
        value = pdf_objects(
            [
                b"<< /Type /Catalog /Pages 2 0 R >>",
                b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
                b"<< /Type /Page /Parent 2 0 R /Resources << >> >>",
            ]
        )
        self.assertFalse(parser.load_document_from_bytesio("synthetic", BytesIO(value), None, False))

    def test_decoder_uses_original_inherited_rotation_and_crop_on_square_page(self) -> None:
        parser = self.module.pdf_parser("fatal")
        value = pdf_objects(
            [
                b"<< /Type /Catalog /Pages 2 0 R >>",
                b"<< /Type /Pages /Count 1 /Kids [3 0 R] /MediaBox [0 0 600 600] "
                b"/CropBox [20 30 550 560] /Rotate 90 >>",
                b"<< /Type /Page /Parent 2 0 R /Resources << >> >>",
            ]
        )
        self.assertTrue(parser.load_document_from_bytesio("synthetic", BytesIO(value), None, False))
        try:
            admission = parser.page_admission("synthetic", 0)
            self.assertEqual(admission["rotation"], 90)
            page = parser.get_page_decoder("synthetic", 0, self.module.DecodePageConfig())
            geometry = page.get_page_dimension()
            # Clockwise 90 degrees plus the native MediaBox translation (600).
            self.assertEqual(geometry.get_crop_bbox(), [30.0, 50.0, 560.0, 580.0])
            self.assertEqual(geometry.get_media_bbox(), [0.0, 0.0, 600.0, 600.0])
        finally:
            parser.unload_document("synthetic")


if __name__ == "__main__":
    unittest.main()
