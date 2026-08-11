from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import uvicorn
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]
SERVICE_SRC = REPO / "services" / "core-api" / "src"
sys.path.insert(0, str(SERVICE_SRC))

from research_observatory_core.app import create_app  # noqa: E402
from research_observatory_core.config import CoreSettings  # noqa: E402
from research_observatory_core.contract import canonical_openapi_bytes  # noqa: E402
from research_observatory_core.logging import build_log_record  # noqa: E402
from research_observatory_core.modules import ModuleDefinition, ModuleRegistry  # noqa: E402


class CoreApiTests(unittest.TestCase):
    def test_uvicorn_starts_on_an_os_assigned_loopback_port(self) -> None:
        configuration = uvicorn.Config(
            create_app(settings=CoreSettings()),
            host="127.0.0.1",
            port=0,
            log_config=None,
            access_log=False,
        )
        server = uvicorn.Server(configuration)
        thread = threading.Thread(target=server.run, daemon=True)
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
                connection.request("GET", "/readyz")
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
        app = create_app(settings=CoreSettings())
        with TestClient(app) as client:
            health = client.get("/healthz")
            readiness = client.get("/readyz")
            version = client.get("/runtime/version")
            configuration = client.get("/runtime/configuration")
            modules = client.get("/runtime/modules")
            capabilities = client.get("/runtime/capabilities")
            openapi = client.get("/openapi.json")

        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["state"], "ready")
        self.assertEqual(readiness.status_code, 200)
        self.assertTrue(readiness.json()["ready"])
        self.assertEqual(version.json()["version"], "0.1.0")
        self.assertEqual(
            configuration.json(),
            {"schemaVersion": "1.0", "profile": "local", "bindHost": "loopback", "bindPort": "ephemeral"},
        )
        self.assertEqual(modules.json()["modules"][0]["moduleId"], "runtime")
        self.assertEqual(capabilities.json()["capabilities"], ["runtime.status"])
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
            with self.assertRaises(ValidationError), TestClient(app):
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
        with TestClient(create_app(settings=CoreSettings())) as client:
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


if __name__ == "__main__":
    unittest.main()
