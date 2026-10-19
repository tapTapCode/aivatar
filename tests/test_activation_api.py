from fastapi.testclient import TestClient
from pipeline.api.main import app


def test_activation_endpoints_exist():
    with TestClient(app) as client:
        response = client.get("/activation/status")
        assert response.status_code == 200
        payload = response.json()
        assert "ready_for_real_reference_test" in payload
        assert payload["next_milestone"].startswith("Real 60")

        response = client.get("/reference-profiles")
        assert response.status_code == 200
        profiles = response.json()
        assert profiles[0]["id"] == "reference_documentary_v1"

        response = client.get("/reference-profiles/reference_documentary_v1")
        assert response.status_code == 200
        assert response.json()["editorial"]["presenter_target"] == 0.3
