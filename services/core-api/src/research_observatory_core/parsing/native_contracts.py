"""Native raw receipt shape and independently checked source/text relationships."""

from bisect import bisect_right
from typing import Literal, Self

from pydantic import Field, model_validator

from .contracts import Count, Digest, IRValue, Text

NATIVE_MEDIA_TYPE = "application/vnd.research-observatory.native-structure+json"


class NativeAttribute(IRValue):
    name: Text = Field(min_length=1)
    value: Text


class NativeElement(IRValue):
    index: Count
    parent_index: Count | None
    name: Text = Field(min_length=1)
    attributes: tuple[NativeAttribute, ...]
    byte_start: Count
    byte_end: Count
    content_byte_start: Count
    content_byte_end: Count
    text_start: Count
    text_end: Count
    close_kind: Literal["empty", "explicit", "implicit"]


class NativeTextRun(IRValue):
    owner_index: Count
    byte_start: Count
    byte_end: Count
    text_start: Count
    text_end: Count


class NativeStructure(IRValue):
    schema_version: Literal["1.0"]
    format: Literal["jats", "tei", "xml", "html"]
    source_sha256: Digest
    source_byte_length: Count = Field(le=128 * 1_048_576)
    text: Text = Field(repr=False)
    elements: tuple[NativeElement, ...] = Field(min_length=1, max_length=1_000_000)
    text_runs: tuple[NativeTextRun, ...] = Field(repr=False)

    @model_validator(mode="after")
    def source_relationships(self) -> Self:
        root = self.elements[0].name
        if (
            (self.format == "jats" and root not in {"article", "{http://jats.nlm.nih.gov}article"})
            or (self.format == "tei" and root not in {"TEI", "{http://www.tei-c.org/ns/1.0}TEI"})
            or (self.format == "html" and root not in {"html", "{http://www.w3.org/1999/xhtml}html"})
        ):
            raise ValueError("native-format-root-mismatch")
        stack: list[NativeElement] = []
        previous_start = -1
        roots = 0
        for index, element in enumerate(self.elements):
            if not (
                element.index == index
                and previous_start
                < element.byte_start
                < element.content_byte_start
                <= element.content_byte_end
                <= element.byte_end
                <= self.source_byte_length
                and 0 <= element.text_start <= element.text_end <= len(self.text)
            ):
                raise ValueError("native-element-boundary-invalid")
            if element.close_kind == "empty" and not (
                element.content_byte_start == element.content_byte_end == element.byte_end
                and element.text_start == element.text_end
            ):
                raise ValueError("native-empty-element-invalid")
            if element.close_kind == "implicit" and (
                self.format != "html" or element.content_byte_end != element.byte_end
            ):
                raise ValueError("native-implicit-element-invalid")
            if element.close_kind == "explicit" and element.content_byte_end >= element.byte_end:
                raise ValueError("native-explicit-end-markup-missing")
            while stack and element.byte_start >= stack[-1].content_byte_end:
                if element.byte_start < stack.pop().byte_end:
                    raise ValueError("native-markup-overlap")
            parent = stack[-1] if stack else None
            if element.parent_index != (parent.index if parent else None) or (
                parent is not None
                and (element.byte_start < parent.content_byte_start or element.byte_end > parent.content_byte_end)
            ):
                raise ValueError("native-nearest-parent-invalid")
            roots += parent is None
            stack.append(element)
            if len(stack) > 256:
                raise ValueError("native-depth-invalid")
            previous_start = element.byte_start
        if roots != 1:
            raise ValueError("native-root-invalid")
        stack = []
        position = 0
        text_end = 0
        byte_end = 0
        for run in self.text_runs:
            while position < len(self.elements) and self.elements[position].byte_start <= run.byte_start:
                element = self.elements[position]
                while stack and element.byte_start >= stack[-1].content_byte_end:
                    stack.pop()
                stack.append(element)
                position += 1
            while stack and run.byte_start >= stack[-1].content_byte_end:
                if run.byte_start < stack.pop().byte_end:
                    raise ValueError("native-text-markup-overlap")
            if not stack or not (
                run.owner_index == stack[-1].index
                and stack[-1].content_byte_start <= run.byte_start < run.byte_end <= stack[-1].content_byte_end
                and byte_end <= run.byte_start
                and run.text_start == text_end < run.text_end <= len(self.text)
                and (position == len(self.elements) or self.elements[position].byte_start >= run.byte_end)
            ):
                raise ValueError("native-text-origin-invalid")
            byte_end, text_end = run.byte_end, run.text_end
        if text_end != len(self.text):
            raise ValueError("native-text-coverage-invalid")
        ends = [run.byte_end for run in self.text_runs]
        starts = [run.byte_start for run in self.text_runs]
        offsets = [0] + [run.text_end for run in self.text_runs]
        for element in self.elements:
            left = bisect_right(ends, element.content_byte_start)
            right = bisect_right(ends, element.content_byte_end)
            if (
                element.text_start != offsets[left]
                or element.text_end != offsets[right]
                or (left < len(starts) and starts[left] < element.content_byte_start)
                or (right < len(starts) and starts[right] < element.content_byte_end)
            ):
                raise ValueError("native-element-text-rebinding")
        return self
