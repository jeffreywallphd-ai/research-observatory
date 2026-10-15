"""Two immutable trusted execution profiles, separate from scientific identity.

Missing/version1 settings always use legacy120. Only new private settings select
protected900; neither an input hash nor a public caller can select a duration.
"""

import hashlib
import json
from dataclasses import asdict
from typing import Literal

from .reference_imports import ImportLimits

type ParserProfile = Literal["legacy-preview-120s-v1", "protected-preview-900s-v1"]
LEGACY_PROFILE: Literal["legacy-preview-120s-v1"] = "legacy-preview-120s-v1"
PROTECTED_PROFILE: Literal["protected-preview-900s-v1"] = "protected-preview-900s-v1"
LEGACY_LIMITS_HASH = "sha256:3c90557e7cd47abf3454450b22673a9de3b250cde501372b515e1c50c03b524f"
PROTECTED_LIMITS_HASH = "sha256:eee2a0c5d0b4c8a2ea8b13d393819f4807aa51f2b4ad95cc78168654dd122495"


def profile_limits(profile: ParserProfile) -> ImportLimits:
    if profile not in (LEGACY_PROFILE, PROTECTED_PROFILE):
        raise ValueError("protected-import-profile-unknown")
    return ImportLimits(
        max_source_bytes=268435456,
        max_record_bytes=1048576,
        max_field_bytes=65536,
        max_records=200000,
        max_fields=256,
        max_depth=64,
        max_macros=256,
        max_seconds=120.0 if profile == LEGACY_PROFILE else 900.0,
    )


def profile_limits_hash(profile: ParserProfile) -> str:
    limits = profile_limits(profile)
    raw = json.dumps(asdict(limits), sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    observed = "sha256:" + hashlib.sha256(raw.encode("ascii")).hexdigest()
    expected = LEGACY_LIMITS_HASH if profile == LEGACY_PROFILE else PROTECTED_LIMITS_HASH
    if observed != expected:
        raise ValueError("protected-import-profile-hash-mismatch")
    return expected


def known_limits_hash(value: str) -> bool:
    return value in (LEGACY_LIMITS_HASH, PROTECTED_LIMITS_HASH)
