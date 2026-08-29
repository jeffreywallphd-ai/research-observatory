"""Supervised Core entrypoint for the native intent vertical integration check."""

from __future__ import annotations

import argparse
from pathlib import Path

from research_observatory_core.config import CoreSettings
from research_observatory_core.main import run_supervised


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-vault-root", type=Path, required=True)
    parser.add_argument("--supervised", action="store_true")
    arguments = parser.parse_args()
    if not arguments.supervised:
        parser.error("the integration sidecar requires supervised mode")
    return run_supervised(
        CoreSettings(),
        profile_vault_root=arguments.profile_vault_root.resolve(strict=True),
    )


if __name__ == "__main__":
    raise SystemExit(main())
