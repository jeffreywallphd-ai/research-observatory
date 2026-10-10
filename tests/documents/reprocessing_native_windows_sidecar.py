"""Task-owned supervised Native/Core witness with declared synthetic parse data.

Production Native capability, window context, project/vault, source rights and
SQLCipher composition stay real. Selection/output are authored doubles. The real
parser pump stays stopped; this fixture claims no packaged parser/model execution.
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from threading import Lock
from types import MethodType, SimpleNamespace
from unittest.mock import patch

from research_observatory_core import main as core_main
from research_observatory_core.document_parser_runtime import InstalledParser

from tests.documents.test_document_reprocessing_service import complete_job
from tests.parsing import contract_fixtures
from tests.service.fixtures import native_integration_sidecar

RAW = "SYNTHETIC Native reprocessing witness source. Retained human decisions are explicitly reconciled."


def main():
    original = core_main.create_runtime_app

    def authored_app(**kwargs):
        app = original(**kwargs)
        original_lifespan = app.router.lifespan_context

        @asynccontextmanager
        async def authored_lifespan(current):
            async with original_lifespan(current) as state:
                service = current.state.runtime.document_revisions
                service.shutdown()
                service.runtime = SimpleNamespace(
                    load_text=lambda: InstalledParser(
                        None, contract_fixtures.descriptor("ro-native-text", ("plain-text",))
                    )
                )
                create = service.reprocessing_create
                lock, futures = Lock(), []
                submitted_jobs: set[str] = set()
                # Match queue semantics: create returns after enqueue. Authored
                # delivery runs separately rather than consuming Native's
                # mutation-response deadline with synthetic SQLCipher work.
                with ThreadPoolExecutor(max_workers=1, thread_name_prefix="authored-reparse") as delivery:

                    def submitted(self, command, *, trace_id):
                        wire = create(command, trace_id=trace_id)
                        for item in wire["items"]:
                            if item["state"] == "processing":
                                with lock:
                                    if item["jobId"] in submitted_jobs:
                                        continue
                                    if len(submitted_jobs) >= 10:
                                        raise RuntimeError("authored-reparse-fixture-limit")
                                    submitted_jobs.add(item["jobId"])
                                futures.append(
                                    delivery.submit(
                                        complete_job,
                                        self,
                                        command.root,
                                        command.project_id,
                                        command.session_id,
                                        item["jobId"],
                                        RAW,
                                    )
                                )
                        return wire

                    service.reprocessing_create = MethodType(submitted, service)
                    yield state
                for future in futures:
                    future.result()

        app.router.lifespan_context = authored_lifespan
        return app

    with patch.object(core_main, "create_runtime_app", side_effect=authored_app):
        return native_integration_sidecar.main()


if __name__ == "__main__":
    raise SystemExit(main())
