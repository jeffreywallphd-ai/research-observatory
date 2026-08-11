---
id: ADR-0007
title: Package the local Core API as a versioned PyInstaller onedir sidecar
status: Accepted
date: 2026-08-11
deciders:
  - CAP-01 repository-owner capability and slice-plan approval at b0e318137b2aa3ccf34f6a21a587419991d24b03
linked_tasks:
  - CAP-01.S03.T02
decision_scope: Windows x64 Core API sidecar build format, identity, inventory, and verification boundary.
affected_paths:
  - services/core-api/
  - packages/contracts/core-api/
  - tools/core_sidecar_build.py
  - tests/packaging/
  - packaging/build-inputs.json
  - verification-profiles.json
  - quality-scope.json
  - pyproject.toml
  - uv.lock
  - security-exceptions.json
  - .gitignore
supersedes: []
superseded_by: null
---

# ADR-0007: Package the local Core API as a versioned PyInstaller onedir sidecar

## Context

The Windows desktop needs to start the local Core API without requiring a
system Python installation. The approved CAP-01.S03 plan selects a packaged
Python sidecar, a Tauri target-triple identity, exact contents inventory, and
missing-dependency denial. It explicitly defers installer signing and full
clean-VM release qualification to CAP-01.S05. The package must remain local,
must not contain UI-reference assets or research data, and must not introduce a
hosted service.

## Candidates

1. **PyInstaller `onedir`.** Transparent file inventory, conventional Tauri
   sidecar executable, faster startup than archive extraction, and direct
   missing-file testing at the cost of a directory-shaped artifact.
2. **PyInstaller `onefile`.** Convenient single file, but extracts at startup,
   obscures the runtime inventory, and adds antivirus and startup variability.
3. **Require system Python or an embeddable-Python bootstrap.** Reduces the
   frozen bundle abstraction but adds machine-level runtime discovery and a
   second dependency assembly mechanism.

## Decision

Use unmodified PyInstaller 6.21.0 in its `onedir`, console, no-UPX mode under
the pinned Python 3.14.6 development environment. Name the executable
`research-observatory-core-x86_64-pc-windows-msvc.exe` so it can be consumed as
a Tauri external binary in the next task. Place dependencies in the fixed
`research-observatory-core-runtime` directory. Exclude build/test tooling
(`mypy`, `setuptools`, `pip`, `pytest`, and `yaml`) from the shipped runtime.

Commit the build contract and artifact-manifest schema, but never the generated
binary. Each build must emit an exact sorted inventory containing path, byte
count, and SHA-256 for every regular file; redirects and unsupported filesystem
entries fail closed. The executable must run its configuration check with no
Python location on `PATH`, and removal or mutation of an inventoried file must
be detected.

PyInstaller's official license grants a special exception for bundling and
distributing generated executables. This repository does not modify or
redistribute PyInstaller itself; it records the builder and version as build
provenance. The exact build-environment findings are independently reviewed in
the time-bounded `CAP-01.S03.T02` security exceptions; those exceptions do not
apply to a future builder/version or to any runtime dependency.

## Consequences

The desktop can consume a deterministic, versioned Windows x64 package without
a system Python dependency. The onedir contents remain auditable and packaging
regressions are caught in the service profile. The artifact is larger and has
many files; the installer must preserve the complete directory atomically.

This record does not activate process supervision, installer signing, remote
network access, university/cloud deployment, or other platforms. Rollback is a
reversion to the preceding component version and its exact artifact inventory.
Python, PyInstaller, or format changes require a new or superseding ADR and
security/license requalification.

## Verification

- `python -m unittest tests.packaging.test_core_sidecar_package`
- `python tools/verify.py --profile service`
- `python tools/verify.py --profile desktop`
- scoped dependency, vulnerability, and license scan of the frozen environment
- exact artifact-manifest schema validation and missing-file denial

## Task links

- `CAP-01.S03.T02`
- `CAP-01.S03.T03`
