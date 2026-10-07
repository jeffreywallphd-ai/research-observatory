"""Pure coordinate operations; no Core service or persistence enters the worker."""

from research_observatory_core.parsing.pdf_geometry import PdfGeometryError, PdfPageGeometry

__all__ = ["PdfGeometryError", "PdfPageGeometry"]
