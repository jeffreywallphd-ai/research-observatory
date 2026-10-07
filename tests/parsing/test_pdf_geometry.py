from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[2] / "services/core-api/src")]

from workers.document.pdf_geometry import PdfGeometryError, PdfPageGeometry  # noqa: E402


class PdfGeometryTests(unittest.TestCase):
    def test_original_crop_scale_and_each_rotation_both_origins(self) -> None:
        # Original source rectangle [30,40,70,90], media [-20,-30,592,762],
        # crop [10,20,550,730], UserUnit 2. Expected top-left physical points.
        expected = (100.0, 1344.0, 180.0, 1444.0)
        cases = {
            0: (20, 70, 60, 20),
            90: (20, 520, 70, 480),
            180: (480, 690, 520, 640),
            270: (640, 60, 690, 20),
        }
        for rotation, (left, top, right, bottom) in cases.items():
            page = PdfPageGeometry.from_native(
                {
                    "mediaBox": [-20, -30, 592, 762],
                    "cropBox": [10, 20, 550, 730],
                    "rotation": rotation,
                    "userUnit": 2,
                    "imagePixels": 0,
                }
            )
            self.assertEqual((page.width_points, page.height_points), (1224.0, 1584.0))
            for origin in ("BOTTOMLEFT", "TOPLEFT"):
                with self.subTest(rotation=rotation, origin=origin):
                    h = page.display_size[1]
                    bbox = {
                        "l": left,
                        "t": top if origin == "BOTTOMLEFT" else h - top,
                        "r": right,
                        "b": bottom if origin == "BOTTOMLEFT" else h - bottom,
                        "coord_origin": origin,
                    }
                    self.assertEqual(page.region(bbox, page.display_size), expected)

    def test_unknown_frame_and_extra_fields_cannot_acquire_precise_coordinates(self) -> None:
        page = PdfPageGeometry.from_native(
            {"mediaBox": [0, 0, 612, 792], "cropBox": [0, 0, 612, 792], "rotation": 0, "userUnit": 1, "imagePixels": 0}
        )
        bbox = {"l": 20, "t": 50, "r": 40, "b": 30, "coord_origin": "BOTTOMLEFT"}
        with self.assertRaisesRegex(PdfGeometryError, "frame-mismatch"):
            page.region(bbox, (792, 612))
        with self.assertRaises(PdfGeometryError):
            page.region(dict(bbox, extra=True), page.display_size)
        for invalid in (float("nan"), float("inf"), True):
            with self.subTest(invalid=invalid), self.assertRaises(PdfGeometryError):
                page.region(dict(bbox, l=invalid), page.display_size)

    def test_admit_actual_supersampled_canvas_and_retained_images(self) -> None:
        page = PdfPageGeometry.from_native(
            {
                "mediaBox": [0, 0, 5000, 5000],
                "cropBox": [0, 0, 5000, 5000],
                "rotation": 0,
                "userUnit": 1,
                "imagePixels": 0,
            }
        )
        with self.assertRaisesRegex(PdfGeometryError, "pixel-limit"):
            page.admit_render()
        self.assertEqual(page.admit_render(0.5), (3750, 3750))


if __name__ == "__main__":
    unittest.main()
