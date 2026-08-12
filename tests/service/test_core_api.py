from __future__ import annotations

import http.client
import json
import os
import socket
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]
SERVICE_SRC = REPO / "services" / "core-api" / "src"
sys.path.insert(0, str(SERVICE_SRC))

from research_observatory_core.app import create_app  # noqa: E402
from research_observatory_core.authentication import capability_token_digest, parse_startup_authentication  # noqa: E402
from research_observatory_core.config import CoreSettings  # noqa: E402
from research_observatory_core.contract import canonical_openapi_bytes  # noqa: E402
from research_observatory_core.logging import build_log_record  # noqa: E402
from research_observatory_core.main import supervision_handshake  # noqa: E402
from research_observatory_core.models import OperationState  # noqa: E402
from research_observatory_core.modules import ModuleDefinition, ModuleRegistry  # noqa: E402
from research_observatory_core.operations import OperationRecord, OperationRegistry  # noqa: E402

TOKEN = "0123456789abcdef" * 4
OTHER_TOKEN = "fedcba9876543210" * 4
AUTHORITY = "127.0.0.1:49152"
AUTH_HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def authenticated_app(operations: OperationRegistry | None = None) -> FastAPI:
    return create_app(
        settings=CoreSettings(),
        capability_digest=capability_token_digest(TOKEN),
        expected_authority=AUTHORITY,
        operations=operations,
    )


def authenticated_client(app: FastAPI | None = None) -> TestClient:
    return TestClient(
        app or authenticated_app(),
        base_url=f"http://{AUTHORITY}",
        headers=AUTH_HEADERS,
        client=("127.0.0.1", 50000),
    )


class CoreApiTests(unittest.TestCase):
    def test_uvicorn_starts_on_an_os_assigned_loopback_port(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        assigned_host, assigned_port = listener.getsockname()
        configuration = uvicorn.Config(
            create_app(
                settings=CoreSettings(),
                capability_digest=capability_token_digest(TOKEN),
                expected_authority=f"{assigned_host}:{assigned_port}",
            ),
            host=assigned_host,
            port=assigned_port,
            log_config=None,
            access_log=False,
            proxy_headers=False,
        )
        server = uvicorn.Server(configuration)
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(server.started)
            self.assertTrue(server.servers)
            socket_name = server.servers[0].sockets[0].getsockname()
            self.assertEqual(socket_name[0], "127.0.0.1")
            self.assertGreater(socket_name[1], 0)
            connection = http.client.HTTPConnection("127.0.0.1", socket_name[1], timeout=5)
            try:
                connection.request(
                    "GET",
                    "/readyz",
                    headers={"Authorization": f"Bearer {TOKEN}", "Host": f"{assigned_host}:{assigned_port}"},
                )
                response = connection.getresponse()
                payload = json.loads(response.read())
                self.assertEqual(response.status, 200)
                self.assertTrue(payload["ready"])
            finally:
                connection.close()
        finally:
            server.should_exit = True
            thread.join(timeout=10)
        self.assertFalse(thread.is_alive())

    def test_lifespan_exposes_typed_runtime_endpoints_and_openapi(self) -> None:
        app = authenticated_app()
        self.assertNotIn(TOKEN, repr(app.user_middleware))
        authentication = next(item for item in app.user_middleware if "digest" in item.kwargs)
        self.assertNotIn("token", authentication.kwargs)
        self.assertEqual(authentication.kwargs["digest"], capability_token_digest(TOKEN))
        with authenticated_client(app) as client:
            health = client.get("/healthz")
            readiness = client.get("/readyz")
            version = client.get("/runtime/version")
            configuration = client.get("/runtime/configuration")
            modules = client.get("/runtime/modules")
            capabilities = client.get("/runtime/capabilities")
            openapi = client.get("/openapi.json")
        self.assertNotIn(TOKEN, repr(app.user_middleware))
        self.assertNotIn(TOKEN, repr(app.middleware_stack))

        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["state"], "ready")
        self.assertEqual(readiness.status_code, 200)
        self.assertTrue(readiness.json()["ready"])
        self.assertEqual(version.json()["version"], "0.1.0")
        self.assertEqual(version.json()["apiVersion"], "1.0.0")
        self.assertEqual(version.json()["minimumClientApiVersion"], "1.0.0")
        self.assertEqual(version.json()["maximumClientApiVersionExclusive"], "2.0.0")
        self.assertEqual(
            configuration.json(),
            {"schemaVersion": "1.0", "profile": "local", "bindHost": "loopback", "bindPort": "ephemeral"},
        )
        self.assertEqual([module["moduleId"] for module in modules.json()["modules"]], ["operations", "runtime"])
        self.assertEqual(
            capabilities.json()["capabilities"],
            ["operations.cancel", "operations.events", "operations.read", "runtime.contract", "runtime.status"],
        )
        self.assertEqual(openapi.status_code, 200)
        self.assertEqual(openapi.json()["info"]["version"], "0.1.0")
        self.assertNotIn("0.0.0.0", json.dumps(openapi.json()))

    def test_startup_rejects_non_loopback_local_configuration(self) -> None:
        fixture = json.loads(
            (REPO / "tests" / "service" / "fixtures" / "invalid-non-loopback.json").read_text(encoding="utf-8")
        )
        with self.assertRaises(ValidationError):
            CoreSettings.model_validate(fixture)

        environment = {
            "RO_CORE_PROFILE": "local",
            "RO_CORE_BIND_HOST": "0.0.0.0",
            "RO_CORE_BIND_PORT": "0",
            "RO_CORE_LOG_LEVEL": "INFO",
        }
        with patch.dict(os.environ, environment, clear=False):
            app = create_app()
            with self.assertRaises(ValidationError), authenticated_client(app):
                pass

    def test_module_registry_rejects_duplicate_identity(self) -> None:
        module = ModuleDefinition(module_id="runtime", capabilities=("runtime.status",))
        with self.assertRaisesRegex(ValueError, "duplicate module id"):
            ModuleRegistry((module, module))

    def test_structured_logging_redacts_sensitive_fields(self) -> None:
        record = build_log_record(
            "runtime.started",
            level="INFO",
            fields={"moduleId": "runtime", "token": "RO-TOKEN-HUNTER2-ABC123", "researchContent": "private"},
        )
        self.assertEqual(record["moduleId"], "runtime")
        self.assertEqual(record["token"], "[REDACTED]")
        self.assertEqual(record["researchContent"], "[REDACTED]")
        self.assertNotIn("HUNTER2", json.dumps(record))
        hostile_value = build_log_record(
            "runtime.failed", level="ERROR", fields={"reasonCode": "RO-TOKEN-HUNTER2-ABC123"}
        )
        self.assertEqual(hostile_value["reasonCode"], "[REDACTED]")

    def test_runtime_contract_accepts_served_health_and_readiness_and_denies_drift(self) -> None:
        schema = json.loads(
            (REPO / "packages" / "contracts" / "core-api" / "core-runtime.schema.json").read_text(encoding="utf-8")
        )
        validator = Draft202012Validator(schema)
        with authenticated_client() as client:
            health = client.get("/healthz").json()
            readiness = client.get("/readyz").json()
        self.assertEqual(list(validator.iter_errors(health)), [])
        self.assertEqual(list(validator.iter_errors(readiness)), [])

        invalid_state = {**health, "state": "probably-ready"}
        extra_field = {**readiness, "invented": True}
        self.assertNotEqual(list(validator.iter_errors(invalid_state)), [])
        self.assertNotEqual(list(validator.iter_errors(extra_field)), [])

    def test_generated_openapi_and_component_version_are_current(self) -> None:
        committed = REPO / "packages" / "contracts" / "core-api" / "openapi.json"
        self.assertEqual(committed.read_bytes(), canonical_openapi_bytes())
        component = json.loads((REPO / "services" / "core-api" / "component-manifest.json").read_text(encoding="utf-8"))
        product = json.loads((REPO / "packaging" / "product-version.json").read_text(encoding="utf-8"))
        self.assertEqual(component["version"], product["version"])
        self.assertEqual(component["version"], "0.1.0")
        generated = subprocess.run(
            [sys.executable, "tools/core_api_contract.py", "--repo", ".", "--check"],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(generated.returncode, 0, generated.stdout + generated.stderr)

    def test_operation_contract_pages_cancels_and_replays_sse_with_trace_safe_problems(self) -> None:
        registry = OperationRegistry()
        first = OperationRecord(
            operation_id="op-first",
            kind="runtime.fixture",
            trace_id="1" * 32,
        )
        first.transition(OperationState.RUNNING, 25)
        second = OperationRecord(
            operation_id="op-second",
            kind="runtime.fixture",
            trace_id="2" * 32,
        )
        second.transition(OperationState.SUCCEEDED, 100)
        registry.add_fixture(first)
        registry.add_fixture(second)

        with authenticated_client(authenticated_app(registry)) as client:
            page = client.get("/runtime/operations", params={"limit": 1})
            self.assertEqual(page.status_code, 200)
            self.assertEqual([item["operationId"] for item in page.json()["items"]], ["op-first"])
            self.assertEqual(page.json()["nextCursor"], "op-first")
            second_page = client.get("/runtime/operations", params={"limit": 1, "after": "op-first"})
            self.assertEqual([item["operationId"] for item in second_page.json()["items"]], ["op-second"])
            self.assertIsNone(second_page.json()["nextCursor"])

            events = client.get("/runtime/operations/op-first/events", params={"afterSequence": 0})
            self.assertEqual(events.status_code, 200)
            self.assertEqual(events.headers["content-type"].split(";", 1)[0], "text/event-stream")
            self.assertIn("id: 1\nevent: operation-progress\ndata: ", events.text)
            self.assertIn('"operationId":"op-first"', events.text)

            status_before_cancel = client.get("/runtime/operations/op-first")
            self.assertEqual(status_before_cancel.headers["etag"], '"op-first-1"')
            command_key = "3" * 32
            cancelled = client.post(
                "/runtime/operations/op-first/cancel",
                headers={"If-Match": status_before_cancel.headers["etag"], "Idempotency-Key": command_key},
            )
            self.assertEqual(cancelled.status_code, 200)
            self.assertEqual(cancelled.json()["state"], "cancelled")
            self.assertTrue(cancelled.json()["cancellationRequested"])
            self.assertEqual(cancelled.headers["etag"], '"op-first-2"')
            repeated = client.post(
                "/runtime/operations/op-first/cancel",
                headers={"If-Match": status_before_cancel.headers["etag"], "Idempotency-Key": command_key},
            )
            self.assertEqual(repeated.status_code, 200)
            self.assertEqual(repeated.json()["sequence"], 2)
            changed_fingerprint = client.post(
                "/runtime/operations/op-first/cancel",
                headers={"If-Match": '"op-first-999"', "Idempotency-Key": command_key},
            )
            self.assertEqual(changed_fingerprint.status_code, 409)
            self.assertEqual(changed_fingerprint.json()["code"], "RO-CORE-IDEMPOTENCY-CONFLICT")
            replay = client.get("/runtime/operations/op-first/events", params={"afterSequence": 1})
            self.assertIn("id: 2", replay.text)
            self.assertIn('"state":"cancelled"', replay.text)

            missing_precondition = client.post("/runtime/operations/op-first/cancel")
            self.assertEqual(missing_precondition.status_code, 428)
            self.assertEqual(missing_precondition.json()["code"], "RO-CORE-PRECONDITION-REQUIRED")
            stale = client.post(
                "/runtime/operations/op-first/cancel",
                headers={"If-Match": '"op-first-1"', "Idempotency-Key": "4" * 32},
            )
            self.assertEqual(stale.status_code, 412)
            self.assertEqual(stale.json()["code"], "RO-CORE-REVISION-CONFLICT")

            terminal_status = client.get("/runtime/operations/op-second")
            terminal = client.post(
                "/runtime/operations/op-second/cancel",
                headers={"If-Match": terminal_status.headers["etag"], "Idempotency-Key": "5" * 32},
            )
            self.assertEqual(terminal.status_code, 409)
            problem = terminal.json()
            self.assertEqual(problem["code"], "RO-CORE-OPERATION-TERMINAL")
            self.assertEqual(problem["traceId"], terminal.headers["x-trace-id"])
            self.assertNotIn("Traceback", json.dumps(problem))

            reused_identity = client.post(
                "/runtime/operations/op-second/cancel",
                headers={"If-Match": terminal_status.headers["etag"], "Idempotency-Key": command_key},
            )
            self.assertEqual(reused_identity.status_code, 409)
            self.assertEqual(reused_identity.json()["code"], "RO-CORE-IDEMPOTENCY-CONFLICT")

            missing = client.get("/runtime/operations/op-missing")
            self.assertEqual(missing.status_code, 404)
            self.assertEqual(missing.json()["code"], "RO-CORE-OPERATION-NOT-FOUND")
            self.assertEqual(missing.json()["traceId"], missing.headers["x-trace-id"])

            invalid_cursor = client.get("/runtime/operations", params={"after": "op-missing"})
            self.assertEqual(invalid_cursor.status_code, 422)
            self.assertEqual(invalid_cursor.json()["code"], "RO-CORE-CURSOR-INVALID")

            unknown_route = client.get("/runtime/private-database")
            self.assertEqual(unknown_route.status_code, 404)
            self.assertEqual(unknown_route.json()["code"], "RO-CORE-ROUTE-NOT-FOUND")
            self.assertEqual(unknown_route.json()["traceId"], unknown_route.headers["x-trace-id"])

            wrong_method = client.post("/runtime/version")
            self.assertEqual(wrong_method.status_code, 405)
            self.assertEqual(wrong_method.json()["code"], "RO-CORE-METHOD-DENIED")

    def test_operation_event_retention_is_bounded_and_requires_status_reconciliation_after_a_gap(self) -> None:
        registry = OperationRegistry()
        record = OperationRecord(operation_id="op-bounded", kind="runtime.fixture", trace_id="6" * 32)
        for progress in range(260):
            record.transition(OperationState.RUNNING, progress % 101)
        registry.add_fixture(record)
        self.assertEqual(len(record.events), 256)

        with authenticated_client(authenticated_app(registry)) as client:
            gap = client.get("/runtime/operations/op-bounded/events", params={"afterSequence": 0})
            self.assertEqual(gap.status_code, 409)
            self.assertEqual(gap.json()["code"], "RO-CORE-EVENT-REPLAY-GAP")
            resumed = client.get("/runtime/operations/op-bounded/events", params={"afterSequence": 4})
            self.assertEqual(resumed.status_code, 200)
            self.assertIn("id: 5", resumed.text)
            self.assertIn("id: 260", resumed.text)

    def test_trace_boundary_preserves_canonical_ids_and_denies_hostile_shapes(self) -> None:
        trace = "a" * 32
        with authenticated_client() as client:
            accepted = client.get("/runtime/version", headers={"X-Trace-Id": trace})
            self.assertEqual(accepted.status_code, 200)
            self.assertEqual(accepted.headers["x-trace-id"], trace)

            invalid = client.get("/runtime/version", headers={"X-Trace-Id": "../../secret"})
            self.assertEqual(invalid.status_code, 400)
            self.assertEqual(invalid.headers["content-type"], "application/problem+json")
            self.assertEqual(invalid.json()["code"], "RO-CORE-TRACE-INVALID")
            self.assertEqual(invalid.json()["traceId"], invalid.headers["x-trace-id"])
            self.assertNotIn("secret", invalid.text)

    def test_isolated_process_check_has_no_socket_and_redacts_configuration_errors(self) -> None:
        environment = os.environ.copy()
        for key in tuple(environment):
            if key.casefold().startswith("ro_core_") or key.casefold() == "pythonpath":
                environment.pop(key)
        environment["PYTHONPATH"] = str(SERVICE_SRC)
        valid = subprocess.run(
            [sys.executable, "-m", "research_observatory_core.main", "--check"],
            cwd=REPO,
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(valid.returncode, 0, valid.stderr)
        self.assertEqual(json.loads(valid.stdout)["status"], "configuration-valid")
        self.assertNotIn("http", valid.stdout)

        environment["RO_CORE_BIND_HOST"] = "https://token@example.invalid"
        invalid = subprocess.run(
            [sys.executable, "-m", "research_observatory_core.main", "--check"],
            cwd=REPO,
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(invalid.returncode, 2)
        self.assertEqual(json.loads(invalid.stderr)["status"], "configuration-error")
        self.assertNotIn("token@example", invalid.stderr)

    def test_supervised_process_emits_strict_handshake_and_stops_from_control_pipe(self) -> None:
        schema = json.loads(
            (REPO / "packages" / "contracts" / "core-api" / "runtime-handshake.schema.json").read_text(encoding="utf-8")
        )
        environment = os.environ.copy()
        for key in tuple(environment):
            if key.casefold().startswith("ro_core_") or key.casefold() == "pythonpath":
                environment.pop(key)
        environment["PYTHONPATH"] = str(SERVICE_SRC)
        process = subprocess.Popen(
            [sys.executable, "-m", "research_observatory_core.main", "--supervised"],
            cwd=REPO,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            assert process.stdin is not None
            process.stdin.write(f"auth {TOKEN}\n".encode("ascii"))
            process.stdin.flush()
            assert process.stdout is not None
            line = process.stdout.readline()
            handshake = json.loads(line)
            self.assertEqual(list(Draft202012Validator(schema).iter_errors(handshake)), [])
            # The uv-managed development interpreter may be a launcher process
            # on Windows. The packaged executable is bound to its direct PID by
            # the native supervisor integration check.
            self.assertGreater(handshake["pid"], 0)
            connection = http.client.HTTPConnection(handshake["host"], handshake["port"], timeout=5)
            deadline = time.monotonic() + 10
            response = None
            while time.monotonic() < deadline:
                try:
                    connection.request(
                        "GET",
                        "/readyz",
                        headers={
                            "Authorization": f"Bearer {TOKEN}",
                            "Host": f"{handshake['host']}:{handshake['port']}",
                        },
                    )
                    response = connection.getresponse()
                    if response.status == 200:
                        break
                    response.read()
                except OSError:
                    time.sleep(0.05)
                    connection.close()
                    connection = http.client.HTTPConnection(handshake["host"], handshake["port"], timeout=5)
            self.assertIsNotNone(response)
            assert response is not None
            self.assertEqual(response.status, 200)
            self.assertTrue(json.loads(response.read())["ready"])
            connection.close()

            denied = http.client.HTTPConnection(handshake["host"], handshake["port"], timeout=5)
            denied.request(
                "GET",
                "/readyz",
                headers={
                    "Authorization": f"Bearer {OTHER_TOKEN}",
                    "Host": f"{handshake['host']}:{handshake['port']}",
                },
            )
            denied_response = denied.getresponse()
            self.assertEqual(denied_response.status, 401)
            self.assertEqual(json.loads(denied_response.read())["code"], "RO-CORE-AUTH-REQUIRED")
            denied.close()

            process.stdin.write(b"shutdown\n")
            process.stdin.flush()
            self.assertEqual(process.wait(timeout=10), 0)
            assert process.stderr is not None
            stderr = process.stderr.read()
            self.assertNotIn(TOKEN.encode("ascii"), stderr)
            self.assertNotIn(OTHER_TOKEN.encode("ascii"), stderr)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()

        fabricated = supervision_handshake(host="127.0.0.1", port=49152)
        fabricated["pid"] = 0
        fabricated["host"] = "localhost"
        fabricated["nonce"] = "RO-TOKEN-HUNTER2"
        self.assertGreaterEqual(len(list(Draft202012Validator(schema).iter_errors(fabricated))), 3)

    def test_local_transport_denies_missing_stale_remote_and_origin_requests(self) -> None:
        with authenticated_client() as client:
            accepted = client.get("/readyz")
            missing = client.get("/readyz", headers={"Authorization": ""})
            wrong = client.get("/readyz", headers={"Authorization": f"Bearer {OTHER_TOKEN}"})
            noncanonical = client.get("/readyz", headers={"Authorization": f"Bearer {TOKEN.upper()}"})
            duplicate = client.get(
                "/readyz",
                headers=[
                    ("Authorization", f"Bearer {TOKEN}"),
                    ("Authorization", f"Bearer {OTHER_TOKEN}"),
                ],
            )
            origin = client.get("/readyz", headers={**AUTH_HEADERS, "Origin": "tauri://localhost"})
            wrong_host = client.get("/readyz", headers={**AUTH_HEADERS, "Host": "localhost:49152"})
        self.assertEqual(accepted.status_code, 200)
        for response in (missing, wrong, noncanonical, duplicate):
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json(), {"code": "RO-CORE-AUTH-REQUIRED", "status": 401})
            self.assertEqual(response.headers["www-authenticate"], "Bearer")
        self.assertEqual(origin.status_code, 403)
        self.assertEqual(origin.json()["code"], "RO-CORE-ORIGIN-DENIED")
        self.assertEqual(wrong_host.status_code, 403)
        self.assertEqual(wrong_host.json()["code"], "RO-CORE-TRANSPORT-DENIED")

        with TestClient(
            authenticated_app(),
            base_url=f"http://{AUTHORITY}",
            headers=AUTH_HEADERS,
            client=("192.0.2.25", 50000),
        ) as remote:
            denied = remote.get("/readyz")
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["code"], "RO-CORE-TRANSPORT-DENIED")

    def test_token_rotates_between_launches_and_startup_record_is_strict(self) -> None:
        first = authenticated_app()
        second = create_app(
            settings=CoreSettings(),
            capability_digest=capability_token_digest(OTHER_TOKEN),
            expected_authority=AUTHORITY,
        )
        with authenticated_client(first) as first_client:
            self.assertEqual(first_client.get("/readyz").status_code, 200)
        with authenticated_client(second) as second_client:
            self.assertEqual(second_client.get("/readyz").status_code, 401)
            self.assertEqual(
                second_client.get("/readyz", headers={"Authorization": f"Bearer {OTHER_TOKEN}"}).status_code,
                200,
            )

        record = bytearray(f"auth {TOKEN}\n".encode("ascii"))
        self.assertEqual(capability_token_digest(TOKEN), parse_startup_authentication(record))
        self.assertEqual(record, bytearray(len(record)))
        for invalid in (
            b"",
            b"auth short\n",
            f"AUTH {TOKEN}\n".encode("ascii"),
            f"auth {TOKEN.upper()}\n".encode("ascii"),
            f"auth {TOKEN}\r\n".encode("ascii"),
        ):
            record = bytearray(invalid)
            with self.subTest(invalid=invalid[:10]), self.assertRaises(ValueError):
                parse_startup_authentication(record)
            self.assertEqual(record, bytearray(len(record)))

    def test_supervised_process_rejects_malformed_startup_authentication_without_echoing_it(self) -> None:
        environment = os.environ.copy()
        for key in tuple(environment):
            if key.casefold().startswith("ro_core_") or key.casefold() == "pythonpath":
                environment.pop(key)
        environment["PYTHONPATH"] = str(SERVICE_SRC)
        exposed_value = TOKEN.upper()
        rejected = subprocess.run(
            [sys.executable, "-m", "research_observatory_core.main", "--supervised"],
            cwd=REPO,
            env=environment,
            input=f"auth {exposed_value}\n".encode("ascii"),
            capture_output=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertEqual(json.loads(rejected.stderr)["status"], "startup-authentication-error")
        self.assertEqual(rejected.stdout, b"")
        self.assertNotIn(exposed_value.encode("ascii"), rejected.stderr)


if __name__ == "__main__":
    unittest.main()
