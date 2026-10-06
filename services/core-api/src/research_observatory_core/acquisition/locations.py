"""Project exact source observations without interpreting licenses as permission."""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..connectors.contracts import ConnectorRecord
from ..ports.acquisition import AcquisitionProblem
from .transport import validated_url


@dataclass(frozen=True, slots=True)
class RetainedLocation:
    key: str
    url: str
    license: str | None
    version: str | None


def retained_locations(record: ConnectorRecord) -> tuple[RetainedLocation, ...]:
    fields = {}
    for field in record.fields:
        if field.name in fields or field.namespace != record.provider_id:
            raise AcquisitionProblem("acquisition-source-invalid")
        fields[field.name] = json.loads(field.value) if field.encoding == "json" else field.value
    candidates: list[tuple[str, object, tuple[str, ...]]] = []
    if record.provider_id == "openalex":
        primary = fields.get("primary_location")
        if isinstance(primary, dict) and primary.get("is_oa") is True:
            candidates.append(("primary_location", primary, ("pdf_url", "landing_page_url")))
        locations = fields.get("locations", [])
        if not isinstance(locations, list) or len(locations) > 100:
            raise AcquisitionProblem("acquisition-source-invalid")
        candidates.extend(
            (f"locations:{index}", value, ("pdf_url", "landing_page_url"))
            for index, value in enumerate(locations)
            if isinstance(value, dict) and value.get("is_oa") is True
        )
    elif record.provider_id == "unpaywall":
        locations = fields.get("oa_locations", [])
        if not isinstance(locations, list) or len(locations) > 100:
            raise AcquisitionProblem("acquisition-source-invalid")
        candidates.extend(
            (f"oa_locations:{index}", value, ("url_for_pdf", "url", "url_for_landing_page"))
            for index, value in enumerate(locations)
        )
    elif record.provider_id == "semantic-scholar" and fields.get("isOpenAccess") is True:
        candidates.append(("openAccessPdf", fields.get("openAccessPdf"), ("url",)))
    result = []
    for key, value, names in candidates:
        if not isinstance(value, dict):
            raise AcquisitionProblem("acquisition-source-invalid")
        license_value, version = value.get("license"), value.get("version")
        if (license_value is not None and (not isinstance(license_value, str) or len(license_value) > 4096)) or (
            version is not None and (not isinstance(version, str) or len(version) > 256)
        ):
            raise AcquisitionProblem("acquisition-source-invalid")
        for name in names:
            url = value.get(name)
            if url is None:
                continue
            # Unsafe source observations remain in the retained metadata, but
            # cannot be selected as an acquisition destination.
            try:
                validated_url(url)
            except AcquisitionProblem:
                continue
            result.append(RetainedLocation(f"{key}:{name}", url, license_value, version))
    return tuple(result)
