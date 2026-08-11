"""Deterministic OpenAPI contract generation."""

from __future__ import annotations

import json

from .app import create_app


def canonical_openapi_bytes() -> bytes:
    return (json.dumps(create_app().openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
