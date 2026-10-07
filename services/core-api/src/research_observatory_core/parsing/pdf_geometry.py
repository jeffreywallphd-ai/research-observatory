"""Pure geometry shared by isolated parsing and parent validation; no I/O."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal, cast


class PdfGeometryError(ValueError):
    """Content-free geometry/admission error."""


def _numbers(value: object, length: int) -> tuple[float, ...]:
    if not isinstance(value, (tuple, list)) or len(value) != length:
        raise PdfGeometryError("parser-geometry-invalid")
    if any(type(number) not in (float, int) or not math.isfinite(number) for number in value):
        raise PdfGeometryError("parser-geometry-invalid")
    return tuple(float(number) for number in value)


def _rotate(x: float, y: float, rotation: int) -> tuple[float, float]:
    return ((x, y), (y, -x), (-x, -y), (-y, x))[rotation // 90]


@dataclass(frozen=True)
class PdfPageGeometry:
    media_box: tuple[float, float, float, float]
    crop_box: tuple[float, float, float, float]
    rotation: Literal[0, 90, 180, 270]
    user_unit: float
    image_pixels: int

    @classmethod
    def from_native(cls, value: dict[str, Any]) -> PdfPageGeometry:
        if set(value) != {"mediaBox", "cropBox", "rotation", "userUnit", "imagePixels"}:
            raise PdfGeometryError("parser-geometry-invalid")
        media = _numbers(value["mediaBox"], 4)
        crop = _numbers(value["cropBox"], 4)
        unit = _numbers([value["userUnit"]], 1)[0]
        rotation = value["rotation"]
        pixels = value["imagePixels"]
        if (
            type(rotation) is not int
            or rotation not in (0, 90, 180, 270)
            or not 0 < unit <= 75000
            or type(pixels) is not int
            or not 0 <= pixels <= 40000000
            or media[0] >= media[2]
            or media[1] >= media[3]
            or crop[0] >= crop[2]
            or crop[1] >= crop[3]
            or crop[0] < media[0]
            or crop[1] < media[1]
            or crop[2] > media[2]
            or crop[3] > media[3]
        ):
            raise PdfGeometryError("parser-geometry-invalid")
        return cls(
            (media[0], media[1], media[2], media[3]),
            (crop[0], crop[1], crop[2], crop[3]),
            cast(Literal[0, 90, 180, 270], rotation),
            unit,
            pixels,
        )

    @property
    def width_points(self) -> float:
        return (self.media_box[2] - self.media_box[0]) * self.user_unit

    @property
    def height_points(self) -> float:
        return (self.media_box[3] - self.media_box[1]) * self.user_unit

    @property
    def display_size(self) -> tuple[float, float]:
        width, height = self.crop_box[2] - self.crop_box[0], self.crop_box[3] - self.crop_box[1]
        return (height, width) if self.rotation in (90, 270) else (width, height)

    def admit_render(self, scale: float = 1.0) -> tuple[int, int]:
        if type(scale) not in (int, float) or not math.isfinite(scale) or scale <= 0:
            raise PdfGeometryError("parser-render-scale-invalid")
        # The selected PDFium backend first renders at 1.5 times the scale.
        width, height = self.display_size
        width, height = math.ceil(width * scale * 1.5), math.ceil(height * scale * 1.5)
        if width * height + self.image_pixels > 40000000:
            raise PdfGeometryError("parser-page-pixel-limit")
        return width, height

    def region(self, value: dict[str, Any], displayed_size: tuple[float, float]) -> tuple[float, float, float, float]:
        """Both item provenance and table cells are crop-relative display boxes."""
        if set(value) != {"l", "t", "r", "b", "coord_origin"}:
            raise PdfGeometryError("parser-geometry-invalid")
        actual = _numbers(displayed_size, 2)
        expected = self.display_size
        if any(not math.isclose(a, e, rel_tol=1e-6, abs_tol=1e-4) for a, e in zip(actual, expected, strict=True)):
            raise PdfGeometryError("parser-geometry-frame-mismatch")
        left, top, right, bottom = _numbers([value[key] for key in ("l", "t", "r", "b")], 4)
        if value["coord_origin"] == "TOPLEFT":
            top, bottom = actual[1] - top, actual[1] - bottom
        elif value["coord_origin"] != "BOTTOMLEFT":
            raise PdfGeometryError("parser-geometry-origin-invalid")
        if right < left or top < bottom:
            raise PdfGeometryError("parser-geometry-invalid")
        # Rotation translation cancels when the transformed crop lower-left
        # is expressed in the same native frame, including nonzero/negative media.
        crop_corners = [
            _rotate(x, y, self.rotation)
            for x in (self.crop_box[0], self.crop_box[2])
            for y in (self.crop_box[1], self.crop_box[3])
        ]
        crop_left = min(x for x, _ in crop_corners)
        crop_bottom = min(y for _, y in crop_corners)
        corners = []
        for x in (left, right):
            for y in (bottom, top):
                px, py = _rotate(x + crop_left, y + crop_bottom, (360 - self.rotation) % 360)
                corners.append(((px - self.media_box[0]) * self.user_unit, (self.media_box[3] - py) * self.user_unit))
        return (
            min(x for x, _ in corners),
            min(y for _, y in corners),
            max(x for x, _ in corners),
            max(y for _, y in corners),
        )
