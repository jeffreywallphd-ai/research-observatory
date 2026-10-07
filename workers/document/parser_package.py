"""Pinned package observations; no ambient source, model or config selection."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path

CONFIGURATION = {
    "schemaVersion": "1.0",
    "parser": "docling-slim",
    "version": "2.126.0",
    "doclingParseVersion": "7.16.0",
    "doclingModelsVersion": "4.0.2",
    "layoutRevision": "8f39ad3c0b4c58e9c2d2c84a38465abf757272d8",
    "tableRevision": "fc0f2d45e2218ea24bce5045f58a389aed16dc23",
    "tableMode": "accurate",
    "cellMatching": True,
    "ocr": False,
    "enrichment": False,
    "remoteServices": False,
    "externalPlugins": False,
    "torchCompile": False,
    "cpuThreads": 4,
    "inputBytes": 134217728,
    "pages": 500,
    "pagePixels": 40000000,
    "outputBytes": 67108864,
    "privateMemoryMiB": 4096,
    "wallSeconds": 900,
}
VERSIONS = {
    "docling-slim": "2.126.0",
    "docling-core": "2.97.1",
    "docling-parse": "7.16.0",
    "docling-ibm-models": "4.0.2",
    "torch": "2.14.0+cpu",
    "torchvision": "0.29.0+cpu",
    "transformers": "5.17.0",
    "pypdfium2": "5.13.0",
}
CONFIGURATION_SHA256 = "4a64b8632596984722fe9276d3929906110f6f7fb826e41841bff21067d8afc7"
ASSETS_SHA256 = "79b5f725c6732daa2da9b1569dfecd3d8ac064ada487cef44bc4ccb840e9eec3"


class ParserPackageError(ValueError):
    def __init__(self) -> None:
        super().__init__("parser-assets-unavailable")


def package_observations(root: Path, *, check_installed_versions: bool = False) -> tuple[str, str]:
    """Caller authenticates/seals the package first; this verifies selected policy.

    Model-file bytes are authenticated by the signed inventory before launch.
    Do not authenticate a substituted inventory or turn these hashes into grants.
    """
    observed = None
    try:
        config = (root / "parser-config.json").read_bytes()
        assets = (root / "parser-assets.json").read_bytes()
        if len(config) > 8192 or len(assets) > 65536:
            raise ValueError
        if (hashlib.sha256(config).hexdigest(), hashlib.sha256(assets).hexdigest()) != (
            CONFIGURATION_SHA256,
            ASSETS_SHA256,
        ):
            raise ValueError
        if json.loads(config) != CONFIGURATION:
            raise ValueError
        manifest = json.loads(assets)
        if set(manifest) != {"schemaVersion", "documentType", "files"} or (
            manifest["schemaVersion"] != "1.0"
            or manifest["documentType"] != "pinned-document-parser-assets"
            or type(manifest["files"]) is not list
            or len(manifest["files"]) != 7
        ):
            raise ValueError
        if check_installed_versions and any(
            importlib.metadata.version(name) != value for name, value in VERSIONS.items()
        ):
            raise ValueError
        observed = hashlib.sha256(config).hexdigest(), hashlib.sha256(assets).hexdigest()
    except Exception:
        pass
    if observed is None:
        raise ParserPackageError()
    return observed
