"""Serve a live, read-only planning projection without generating review pages.

The API is a working-tree display, never readiness, approval or qualification.
Only canonical planning sources and fixed browser assets are read. No command
execution, planning mutation, arbitrary file route or persisted result cache.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import math
import os
import re
import sys
import threading
import time
from datetime import date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(__file__).resolve().parent / "planning_review"
MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_ENTITIES = 5000
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
IDENTITY = re.compile(r"(?:W\d+(?:\.C\d+\.T\d+|\.A\d+)?|G\d+|CAP-\d+(?:\.S\d+(?:\.T\d+)?)?|ECR-\d{4}|GRR-\d{4})\Z")
PUBLIC_FIELDS = (
    "id",
    "title",
    "alias",
    "goal",
    "objective",
    "track",
    "wave",
    "status",
    "acceptance_criteria",
    "dependencies",
    "verification_profiles",
    "verification_commands",
    "deployment_profiles",
    "platform_targets",
    "updated_at",
    "outcome",
    "depends_on",
    "name",
    "criteria",
    "after_wave",
    "unlocks_waves",
)
DECISION_FIELDS = (
    "id",
    "title",
    "candidates",
    "recommendation",
    "recommendation_basis",
    "selected_option",
    "rationale",
    "status",
    "binding_waves",
    "required_adr",
)


class SourceChanged(ValueError):
    """The displayed inputs changed while collecting one response."""


def _json_value(value: Any, budget: list[int] | None = None, depth: int = 0) -> Any:
    if budget is None:
        budget = [10000, MAX_RESPONSE_BYTES]
    budget[0] -= 1
    if budget[0] < 0 or depth > 16:
        raise ValueError("Planning public value exceeds display traversal bound")
    if isinstance(value, str):
        budget[1] -= len(value.encode("utf-8"))
        if budget[1] < 0:
            raise ValueError("Planning public text exceeds display byte bound")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_value(item, budget, depth + 1) for item in value]
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("Planning public object keys must be strings")
        return {key: _json_value(item, budget, depth + 1) for key, item in value.items()}
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Planning public numbers must be finite")
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise ValueError("Unsupported planning value")


def _objects(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError("Expected a planning object list")
    return value


def _optional_object(record: dict[str, Any], field: str) -> dict[str, Any]:
    value = record.get(field)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("Planning nested record must be an object")
    return value


def _public(record: dict[str, Any], budget: list[int] | None = None) -> dict[str, Any]:
    if budget is None:
        budget = [10000, MAX_RESPONSE_BYTES]
    result = {key: _json_value(record[key], budget) for key in PUBLIC_FIELDS if key in record}
    for field in ("completion", "campaign", "lifecycle"):
        if record.get(field) is not None:
            result[field] = {"status": _json_value(_optional_object(record, field).get("status"), budget)}
    approval = _optional_object(record, "approval")
    if approval:
        result["approval"] = {
            key: _json_value(approval[key], budget)
            for key in ("status", "approved_commit", "approved_at", "capability_ids", "slice_ids", "decision_ids")
            if key in approval
        }
    return result


class Projection:
    """Read immutable captured bytes; reuse parsing only for byte-identical display inputs."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=True)
        self._lock = threading.Lock()
        self._last_backlog: bytes | None = None
        self._parsed: dict[str, Any] = {}

    def _read(self, relative: str) -> bytes:
        parts = relative.split("/")
        if not parts or any(part in {"", ".", ".."} for part in parts) or ":" in relative or "\\" in relative:
            raise ValueError("Unsafe planning source")
        current = self.root
        for part in parts:
            current /= part
            if current.is_symlink() or os.path.isjunction(current):
                raise ValueError("Linked planning source")
        current.resolve(strict=True).relative_to(self.root)
        limit = MAX_SOURCE_BYTES if relative == "planning/backlog.yaml" else min(MAX_SOURCE_BYTES, 1024 * 1024)
        if not current.is_file():
            raise ValueError("Planning source is not a regular file")
        with current.open("rb") as source:
            raw = source.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("Planning source exceeds display bound")
        return raw

    def _entities(self, backlog: dict[str, Any], budget: list[int]) -> list[dict[str, Any]]:
        entities: list[dict[str, Any]] = []

        def add(record: dict[str, Any], kind: str, route: str, **context: Any) -> dict[str, Any]:
            identity = record.get("id")
            if not isinstance(identity, str) or len(identity) > 128 or not IDENTITY.fullmatch(identity):
                raise ValueError("Invalid planning identity")
            if len(entities) >= MAX_ENTITIES:
                raise ValueError("Planning display inventory exceeds bound")
            item = {
                **_public(record, budget),
                "kind": kind,
                "route": route,
                **{key: _json_value(value, budget) for key, value in context.items()},
            }
            entities.append(item)
            return item

        for wave in _objects(backlog.get("waves", [])):
            add(wave, "wave", f"/waves/{wave['id']}.html")
            for correction in _objects(_optional_object(wave, "campaign").get("corrective_tasks", [])):
                add(correction, "correction", f"/corrections/{correction['id']}.html", wave=wave["id"])
        for capability in _objects(backlog.get("capabilities", [])):
            cid = capability["id"]
            add(capability, "capability", f"/{cid}/index.html")
            for slice_ in _objects(capability.get("slices", [])):
                sid = slice_["id"]
                add(slice_, "slice", f"/{cid}/{sid}.html", capability_id=cid)
                for task in _objects(slice_.get("tasks", [])):
                    add(
                        task,
                        "task",
                        f"/{cid}/{task['id']}.html",
                        capability_id=cid,
                        slice_id=sid,
                        wave=task.get("wave", slice_.get("wave")),
                    )
        for gate in _objects(backlog.get("release_gates", [])):
            add(gate, "gate", f"/gates/{gate['id']}.html", wave=gate.get("after_wave"))
        for amendment in _objects(backlog.get("wave_amendments", [])):
            change = amendment.get("change_request_id")
            if change is None:
                add(amendment, "amendment", f"/amendments/{amendment['id']}.html")
                continue
            if not isinstance(change, str) or not re.fullmatch(r"ECR-\d{4}", change):
                raise ValueError("Invalid amendment source identity")
            record = {**amendment, "id": change}
            add(record, "amendment", f"/enablers/{change}.html", amendment_id=amendment.get("id"))
        for hold in _objects(_optional_object(backlog, "control_plane").get("recovery_holds", [])):
            request = hold.get("recovery_request_id")
            if not isinstance(request, str) or not re.fullmatch(r"GRR-\d{4}", request):
                raise ValueError("Invalid recovery identity")
            add({**hold, "id": request}, "recovery", f"/recoveries/{request}.html")
        identities = [item["id"] for item in entities]
        if len(identities) > MAX_ENTITIES:
            raise ValueError("Planning display inventory exceeds bound")
        if len(identities) != len(set(identities)):
            raise ValueError("Duplicate planning identity")
        return entities

    def _plan_paths(self, item: dict[str, Any]) -> list[str]:
        identity = item["id"]
        if item["kind"] == "capability":
            paths = [f"planning/capability-plans/{identity}.md"]
        elif item["kind"] in {"slice", "task"}:
            sid = item.get("slice_id", identity)
            parent = f"planning/slice-plans/{item['capability_id']}"
            # Inspect the directory through the same confinement boundary before globbing.
            current = self.root
            for part in parent.split("/"):
                current /= part
                if current.is_symlink() or os.path.isjunction(current):
                    raise ValueError("Linked planning directory")
            paths = sorted(path.relative_to(self.root).as_posix() for path in current.glob(f"{sid}-*.md"))
            if len(paths) > 1:
                raise ValueError("Duplicate slice plan")
        else:
            return []
        if not paths or not (self.root / paths[0]).exists():
            return []
        return paths

    def _plan(
        self, item: dict[str, Any], inputs: dict[str, bytes], paths: list[str], budget: list[int]
    ) -> dict[str, Any] | None:
        if not paths:
            return None
        relative = paths[0]
        raw = self._read(relative)
        if sum(len(value) for value in inputs.values()) + len(raw) > 24 * 1024 * 1024:
            raise ValueError("Selected planning sources exceed display byte bound")
        inputs[relative] = raw
        text = raw.decode("utf-8").replace("\r\n", "\n")
        if not text.startswith("---\n") or "\n---\n" not in text[4:]:
            raise ValueError("Invalid plan frontmatter")
        metadata_text, body = text[4:].split("\n---\n", 1)
        metadata = yaml.safe_load(metadata_text)
        if not isinstance(metadata, dict):
            raise ValueError("Invalid plan metadata")
        expected = item.get("slice_id", item["id"])
        key = "capability_id" if item["kind"] == "capability" else "slice_id"
        if metadata.get(key) != expected:
            raise ValueError("Plan identity does not match current ledger")
        decisions = _objects(metadata.get("decisions", []))
        if len(decisions) > 500:
            raise ValueError("Decision display inventory exceeds bound")
        return {
            "path": relative,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "metadata": _public(metadata, budget),
            "markdown": _json_value(body, budget),
            "decisions": [
                {key: _json_value(decision[key], budget) for key in DECISION_FIELDS if key in decision}
                for decision in decisions
            ],
        }

    def read(self, selected: str | None = None) -> dict[str, Any]:
        started = time.monotonic()
        with self._lock:
            raw = self._read("planning/backlog.yaml")
            if raw != self._last_backlog:
                parsed = yaml.safe_load(raw)
                if not isinstance(parsed, dict):
                    raise ValueError("Invalid backlog")
                self._parsed = parsed
                self._last_backlog = raw
            inputs = {"planning/backlog.yaml": raw}
            budget = [100000, MAX_RESPONSE_BYTES]
            entities = self._entities(self._parsed, budget)
            selected_item = next((item for item in entities if item["id"] == selected), None)
            if selected is not None and selected_item is None:
                raise KeyError("Unknown planning identity")
            inspected = [selected_item] if selected_item else []
            inventory = {item["id"]: self._plan_paths(item) for item in inspected}
            plan = self._plan(selected_item, inputs, inventory[selected_item["id"]], budget) if selected_item else None
            plans = []
            if selected_item and selected_item["kind"] == "wave":
                related_slices = [item for item in entities if item["kind"] == "slice" and item.get("wave") == selected]
                capability_ids = {item["capability_id"] for item in related_slices}
                related_caps = [
                    item for item in entities if item["kind"] == "capability" and item["id"] in capability_ids
                ]
                if len(related_caps) + len(related_slices) > 128:
                    raise ValueError("Selected plan inventory exceeds display bound")
                for item in [*related_caps, *related_slices]:
                    inspected.append(item)
                    inventory[item["id"]] = self._plan_paths(item)
                    projected = self._plan(item, inputs, inventory[item["id"]], budget)
                    if projected:
                        plans.append(projected)
            # Reject changed sources rather than returning a previous successful projection.
            for relative, original in inputs.items():
                if self._read(relative) != original:
                    raise SourceChanged("Planning changed during projection; refresh")
            if any(self._plan_paths(item) != inventory[item["id"]] for item in inspected):
                raise SourceChanged("Selected plan inventory changed; refresh")
            sources = [
                {"path": path, "sha256": hashlib.sha256(value).hexdigest()} for path, value in sorted(inputs.items())
            ]
            fingerprint = hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()
            return {
                "schemaVersion": "1.0",
                "documentType": "live-planning-review",
                "authority": "Working-tree display only; approval, readiness and qualification are separate.",
                "sources": sources,
                "fingerprint": fingerprint,
                "entities": entities,
                "selected": selected_item,
                "plan": plan,
                "plans": plans,
                "projectionMilliseconds": round((time.monotonic() - started) * 1000, 3),
            }


def _asset_bytes(path: Path) -> bytes:
    path = path.absolute()
    if any(part.is_symlink() or os.path.isjunction(part) for part in [*path.parents, path]):
        raise ValueError("Linked review implementation or asset")
    if not path.is_file():
        raise ValueError("Review implementation/asset is not a regular file")
    with path.open("rb") as source:
        raw = source.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("Review implementation/asset exceeds byte bound")
    return raw


class ReviewServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 8

    def __init__(self, root: Path, port: int, assets: Path = ASSETS) -> None:
        self.projection = Projection(root)
        self.assets = assets
        self._slots = threading.BoundedSemaphore(4)
        self._pinned = {
            path: _asset_bytes(path)
            for path in [
                Path(__file__).absolute(),
                *(assets / name for name in ("index.html", "review.js", "review.css")),
            ]
        }
        super().__init__(("127.0.0.1", port), ReviewHandler)

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self._slots.acquire(blocking=False):
            try:
                request.sendall(b"HTTP/1.0 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


class ReviewHandler(BaseHTTPRequestHandler):
    server: ReviewServer

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, format: str, *args: Any) -> None:
        # Do not echo arbitrary request paths or imported text into logs.
        return

    def _send(self, status: HTTPStatus, body: bytes, content_type: str = "application/json; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
            "img-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
        )
        if status == HTTPStatus.METHOD_NOT_ALLOWED:
            self.send_header("Allow", "GET, HEAD")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _error(self, status: HTTPStatus, code: str) -> None:
        self._send(status, json.dumps({"error": code}).encode())

    def _trusted_request(self) -> bool:
        authority = f"127.0.0.1:{self.server.server_port}"
        return self.headers.get_all("Host") == [authority] and self.headers.get_all("Origin", []) in (
            [],
            [f"http://{authority}"],
        )

    def _handle(self) -> None:
        if not self._trusted_request():
            self._error(HTTPStatus.FORBIDDEN, "request.authority-denied")
            return
        try:
            if any(_asset_bytes(path) != pinned for path, pinned in self.server._pinned.items()):
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, "server.code-changed-restart-required")
                return
            parsed = urlsplit(self.path)
        except OSError, ValueError:
            self._error(HTTPStatus.SERVICE_UNAVAILABLE, "server.sources-unavailable")
            return
        if (
            parsed.scheme
            or parsed.netloc
            or parsed.query
            or parsed.fragment
            or "%" in parsed.path
            or "\\" in parsed.path
        ):
            self._error(HTTPStatus.NOT_FOUND, "route.not-found")
            return
        path = parsed.path
        fixed = {
            "/assets/live-review.js": ("review.js", "text/javascript; charset=utf-8"),
            "/assets/live-review.css": ("review.css", "text/css; charset=utf-8"),
        }
        selected = None
        is_api = path == "/api/review" or path.startswith("/api/review/")
        if is_api and path != "/api/review":
            selected = path.removeprefix("/api/review/")
            if not IDENTITY.fullmatch(selected):
                self._error(HTTPStatus.NOT_FOUND, "route.not-found")
                return
        try:
            if path in fixed:
                name, mime = fixed[path]
                self._send(HTTPStatus.OK, self.server._pinned[self.server.assets / name], mime)
                return
            if is_api:
                payload = self.server.projection.read(selected)
                body = bytearray()
                for chunk in json.JSONEncoder(ensure_ascii=False, allow_nan=False).iterencode(payload):
                    encoded = chunk.encode("utf-8")
                    if len(body) + len(encoded) > MAX_RESPONSE_BYTES:
                        raise ValueError("Planning response exceeds display bound")
                    body.extend(encoded)
                self._send(HTTPStatus.OK, bytes(body))
                return
            # Browser routes are resolved from current canonical identities, never filesystem paths.
            overview = self.server.projection.read()
            routes = {item["route"] for item in overview["entities"]}
            if path not in {"/", "/index.html", "/enablers/index.html", "/recoveries/index.html"} | routes:
                self._error(HTTPStatus.NOT_FOUND, "route.not-found")
                return
            self._send(
                HTTPStatus.OK, self.server._pinned[self.server.assets / "index.html"], "text/html; charset=utf-8"
            )
        except KeyError:
            self._error(HTTPStatus.NOT_FOUND, "route.not-found")
        except SourceChanged:
            self._error(HTTPStatus.SERVICE_UNAVAILABLE, "projection.source-changed-refresh")
        except OSError, ValueError, TypeError, RecursionError, yaml.YAMLError:
            self._error(HTTPStatus.SERVICE_UNAVAILABLE, "projection.unavailable-check-canonical-sources")

    def do_GET(self) -> None:
        self._handle()

    def do_HEAD(self) -> None:
        self._handle()

    def _deny_mutation(self) -> None:
        self._error(HTTPStatus.METHOD_NOT_ALLOWED, "method.read-only")

    do_POST = _deny_mutation
    do_PUT = _deny_mutation
    do_PATCH = _deny_mutation
    do_DELETE = _deny_mutation
    do_OPTIONS = _deny_mutation
    do_TRACE = _deny_mutation
    do_CONNECT = _deny_mutation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=57003)
    args = parser.parse_args()
    if args.host != "127.0.0.1" or not ipaddress.ip_address(args.host).is_loopback:
        parser.error("Review server binds only to numeric IPv4 loopback 127.0.0.1")
    try:
        server = ReviewServer(args.repo, args.port)
    except (OSError, ValueError) as error:
        print(f"Review server could not start: {error}", file=sys.stderr)
        return 2
    print(f"Live planning review: http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
