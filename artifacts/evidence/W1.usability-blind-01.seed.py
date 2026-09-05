"""Prepare synthetic study data through actual encrypted Core composition."""
from pathlib import Path
import json
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))
from fastapi.testclient import TestClient
from research_observatory_core.main import create_runtime_app
from research_observatory_core.config import CoreSettings
from research_observatory_core.authentication import capability_token_digest

study = REPO / "artifacts/tmp/ux-blind-20260905a"
parent = study / "Test-Documents"
assert parent.is_dir() and not (parent / "sample-library-study").exists()
token = "6" * 64  # Isolated in-process synthetic TestClient capability, not a user credential.
app = create_runtime_app(settings=CoreSettings(), capability_digest=capability_token_digest(token),
                         expected_authority="127.0.0.1:49152")
with TestClient(app, base_url="http://127.0.0.1:49152", headers={"Authorization": f"Bearer {token}"},
                client=("127.0.0.1", 50000)) as client:
    response = client.post("/projects", json={
        "parentDirectory": str(parent), "directoryName": "sample-library-study",
        "displayName": "Sample Library Study", "primaryUseCase": "rapid-orientation",
        "researchObjective": "Understand how local libraries support adult learning. Synthetic usability-test data only.",
    })
    assert response.status_code == 200, (response.status_code, response.text)
    sample = response.json()
    root = sample["root"]
    opened = client.post("/projects/open", json={"root": root})
    assert opened.status_code == 200, opened.text
    progress = client.post("/projects/workflow-progress", json={"root": root})
    assert progress.status_code == 200, progress.text
    closed = client.post("/projects/close", json={"root": root})
    assert closed.status_code == 200, closed.text
assert not (Path(root) / "state/project.sqlite3").read_bytes().startswith(b"SQLite format 3")
report = {"ok": True, "synthetic": True, "root": root,
          "boundary": "actual Core composition; normal Windows DPAPI and encrypted project DB; no mocks",
          "project": sample, "progress": progress.json()}
with (study / "sample-preparation.json").open("x", encoding="utf-8") as handle:
    json.dump(report, handle, indent=2)
print(json.dumps({"ok": True, "sample": root, "encryptedDatabase": True}))
