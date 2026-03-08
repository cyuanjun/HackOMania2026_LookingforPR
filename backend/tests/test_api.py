from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    backend_root = Path(__file__).resolve().parents[1]
    settings = Settings(
        csv_dir=backend_root / "data" / "csv",
        cases_dir=tmp_path / "cases",
        uploads_dir=tmp_path / "uploads",
    )
    app = create_app(settings)
    return TestClient(app)


def test_intake_ai_process_and_operator_flow(client: TestClient) -> None:
    residents_response = client.get("/api/v1/residents")
    assert residents_response.status_code == 200
    profile_id = residents_response.json()[0]["profile_id"]

    intake_response = client.post(
        "/api/v1/cases/intake",
        data={"profile_id": profile_id},
        files={"audio_file": ("alert.wav", b"fake-audio-content", "audio/wav")},
    )
    assert intake_response.status_code == 201
    created_case = intake_response.json()
    case_id = created_case["metadata"]["case_id"]
    assert created_case["metadata"]["state"] == "pending_ai_assessment"
    assert created_case["audio_metadata"]["size_bytes"] > 0

    process_response = client.post(f"/api/v1/cases/{case_id}/process-ai")
    assert process_response.status_code == 200
    processed_case = process_response.json()
    assert processed_case["metadata"]["state"] == "ai_assessed"
    assert processed_case["triage_result"]["urgency_class"] in {"non-urgent", "uncertain", "urgent"}

    decision_response = client.post(
        f"/api/v1/cases/{case_id}/operator-decision",
        json={
            "operator_id": "operator-001",
            "chosen_action": "operator_callback",
            "notes": "Follow-up needed after review.",
        },
    )
    assert decision_response.status_code == 200
    finalized_case = decision_response.json()
    assert finalized_case["metadata"]["state"] == "operator_processed"
    assert finalized_case["operator_decision"]["operator_id"] == "operator-001"


def test_invalid_state_transition_returns_409(client: TestClient) -> None:
    intake_response = client.post(
        "/api/v1/cases/intake",
        data={"profile_id": "p001"},
        files={"audio_file": ("alert.wav", b"fake-audio-content", "audio/wav")},
    )
    assert intake_response.status_code == 201
    case_id = intake_response.json()["metadata"]["case_id"]

    invalid_transition = client.post(
        f"/api/v1/cases/{case_id}/operator-decision",
        json={"operator_id": "operator-002", "chosen_action": "community_response", "notes": "Invalid step"},
    )
    assert invalid_transition.status_code == 409


def test_delete_case_removes_case(client: TestClient) -> None:
    intake_response = client.post(
        "/api/v1/cases/intake",
        data={"profile_id": "p001"},
        files={"audio_file": ("alert.wav", b"fake-audio-content", "audio/wav")},
    )
    assert intake_response.status_code == 201
    case_id = intake_response.json()["metadata"]["case_id"]

    delete_response = client.delete(f"/api/v1/cases/{case_id}")
    assert delete_response.status_code == 204

    get_response = client.get(f"/api/v1/cases/{case_id}")
    assert get_response.status_code == 404
