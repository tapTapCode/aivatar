from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from src.api.main import app


def _project(project_id: str, narration: str = "Draft narration.") -> dict[str, object]:
    return {
        "project_id": project_id,
        "schema_version": "1.0",
        "output": {"width": 640, "height": 360},
        "scenes": [
            {
                "scene_id": "presenter",
                "order": 1,
                "visual_format": "PRESENTER",
                "narration_text": narration,
                "avatar_id": "mock_avatar",
                "voice_id": "mock_voice",
            }
        ],
    }


def test_projects_save_as_draft_and_require_approval_before_render() -> None:
    project_id = f"script_{uuid.uuid4().hex[:12]}"
    owner = {"X-Owner-Id": "script-owner"}
    project = _project(project_id)
    with TestClient(app) as client:
        created = client.post(
            "/v1/projects",
            json={**project, "approval_state": "approved"},
            headers=owner,
        )
        assert created.status_code == 201
        assert created.json()["approval_state"] == "draft"

        queued = client.post(
            "/v1/videos",
            json=project,
            headers={**owner, "Idempotency-Key": f"draft-{project_id}"},
        )
        assert queued.status_code == 422
        assert queued.json()["detail"] == "script must be approved before rendering"

        approved = client.post(f"/v1/projects/{project_id}/approve", headers=owner)
        assert approved.status_code == 200
        assert approved.json()["approval_state"] == "approved"

        replaced = client.put(
            f"/v1/projects/{project_id}",
            json=_project(project_id, "Edited narration."),
            headers=owner,
        )
        assert replaced.status_code == 200
        assert replaced.json()["approval_state"] == "draft"
        assert replaced.json()["scenes"][0]["narration_text"] == "Edited narration."

        stale = client.post(
            "/v1/videos",
            json=project,
            headers={**owner, "Idempotency-Key": f"stale-{project_id}"},
        )
        assert stale.status_code == 422
        assert stale.json()["detail"] == "script must be approved before rendering"

        missing = client.post("/v1/projects/unknown_script/approve", headers=owner)
        assert missing.status_code == 404


def test_create_video_rejects_unsaved_scripts() -> None:
    project_id = f"missing_{uuid.uuid4().hex[:12]}"
    with TestClient(app) as client:
        response = client.post(
            "/v1/videos",
            json=_project(project_id),
            headers={"X-Owner-Id": "script-owner", "Idempotency-Key": f"missing-{project_id}"},
        )
    assert response.status_code == 422
    assert response.json()["detail"] == "save and approve the script before rendering"


def test_replace_project_rejects_id_mismatch() -> None:
    project_id = f"mismatch_{uuid.uuid4().hex[:12]}"
    owner = {"X-Owner-Id": "script-owner"}
    with TestClient(app) as client:
        created = client.post("/v1/projects", json=_project(project_id), headers=owner)
        assert created.status_code == 201
        response = client.put(
            f"/v1/projects/{project_id}",
            json=_project("other_project"),
            headers=owner,
        )
    assert response.status_code == 400
    assert response.json()["detail"] == "project_id does not match the URL"


def test_delete_project_cost_ledger_and_retry() -> None:
    project_id = f"ledger_{uuid.uuid4().hex[:12]}"
    owner = {"X-Owner-Id": "ledger-owner"}
    project = _project(project_id)
    with TestClient(app) as client:
        created = client.post("/v1/projects", json=project, headers=owner)
        assert created.status_code == 201
        removed = client.delete(f"/v1/projects/{project_id}", headers=owner)
        assert removed.status_code == 204
        assert client.get(f"/v1/projects/{project_id}", headers=owner).status_code == 404

        saved = client.post("/v1/projects", json=project, headers=owner)
        assert saved.status_code == 201
        approved = client.post(f"/v1/projects/{project_id}/approve", headers=owner)
        assert approved.status_code == 200
        queued = client.post(
            "/v1/videos",
            json=project,
            headers={**owner, "Idempotency-Key": f"ledger-{project_id}"},
        )
        assert queued.status_code == 202, queued.text
        job = client.get(f"/v1/jobs/{queued.json()['job_id']}", headers=owner)
        assert job.status_code == 200
        assert job.json()["estimated_cost_usd"] >= 0
        assert job.json()["cost_entries"]

        costs = client.get("/v1/costs", headers=owner)
        assert costs.status_code == 200
        payload = costs.json()
        assert payload["job_count"] >= 1
        assert payload["billing_policy"] == "HeyGen Avatar IV is billed at the configured per-minute rate."
        assert payload["heygen_rate_usd_per_minute"] == 4.0
        assert payload["heygen_engine"] == "avatar_iv"
        assert payload["heygen_job_count"] >= 1
        assert payload["gpu_job_count"] == 0
        assert any(item["project_id"] == project_id for item in payload["projects"])

        if job.json()["state"] in {"FAILED", "CANCELLED"}:
            retried = client.post(
                f"/v1/videos/{queued.json()['video_id']}/retry",
                headers=owner,
            )
            assert retried.status_code == 202
            assert retried.json()["video_id"] != queued.json()["video_id"]
        else:
            early = client.post(
                f"/v1/videos/{queued.json()['video_id']}/retry",
                headers=owner,
            )
            assert early.status_code == 409
