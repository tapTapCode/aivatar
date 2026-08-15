from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from src.orchestration.cost import HEYGEN_COST_POLICY, heygen_avatar_iv_cost


def _presenter_project(project_id: str, *, duration_seconds: float, narration: str) -> dict[str, object]:
    return {
        "project_id": project_id,
        "schema_version": "1.0",
        "channel_template": "presenter_no_captions",
        "output": {"width": 640, "height": 360, "fps": 30, "aspect_ratio": "16:9"},
        "scenes": [
            {
                "scene_id": "presenter",
                "order": 1,
                "visual_format": "PRESENTER",
                "narration_text": narration,
                "avatar_id": "mock_avatar",
                "voice_id": "mock_voice",
                "duration_seconds": duration_seconds,
            }
        ],
        "consent_records": [
            {
                "subject_id": "mock_avatar",
                "permission_type": "avatar",
                "granted_by": "cost-owner",
                "granted_at": "2026-08-15T00:00:00+00:00",
                "evidence_uri": "self-attested:mock_avatar",
            },
            {
                "subject_id": "mock_voice",
                "permission_type": "voice",
                "granted_by": "cost-owner",
                "granted_at": "2026-08-15T00:00:00+00:00",
                "evidence_uri": "self-attested:mock_voice",
            },
        ],
    }


def _queue(client: TestClient, project: dict[str, object], owner: dict[str, str]) -> dict[str, object]:
    saved = client.post("/v1/projects", json=project, headers=owner)
    assert saved.status_code == 201, saved.text
    approved = client.post(f"/v1/projects/{project['project_id']}/approve", headers=owner)
    assert approved.status_code == 200, approved.text
    queued = client.post(
        "/v1/videos",
        json={**project, "approval_state": "approved"},
        headers={**owner, "Idempotency-Key": f"cost-{uuid.uuid4().hex}"},
    )
    assert queued.status_code == 202, queued.text
    job = client.get(f"/v1/jobs/{queued.json()['job_id']}", headers=owner)
    assert job.status_code == 200, job.text
    return job.json()


def test_presenter_job_uses_default_avatar_iv_rate() -> None:
    from src.api.main import app

    project_id = f"iv_default_{uuid.uuid4().hex[:12]}"
    owner = {"X-Owner-Id": f"cost-{uuid.uuid4().hex[:8]}"}
    expected = heygen_avatar_iv_cost(30, 4.0)
    with TestClient(app) as client:
        job = _queue(
            client,
            _presenter_project(project_id, duration_seconds=30, narration="Thirty second presenter."),
            owner,
        )
        assert job["estimated_cost_usd"] == expected
        assert job["cost_entries"][0]["note"] == "heygen_estimate"
        costs = client.get("/v1/costs", headers=owner)
        assert costs.status_code == 200
        payload = costs.json()
        assert payload["billing_policy"] == HEYGEN_COST_POLICY
        assert payload["heygen_engine"] == "avatar_iv"
        assert payload["heygen_rate_usd_per_minute"] == 4.0
        assert payload["heygen_job_count"] == 1
        assert payload["gpu_job_count"] == 0
        assert payload["heygen_estimated_usd"] == expected
        assert any(item["project_id"] == project_id and item["estimated_usd"] == expected for item in payload["projects"])


def test_presenter_job_uses_configured_avatar_iv_rate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.api import main as api

    monkeypatch.setattr(api.settings, "heygen_rate_usd_per_minute", 5.0)
    project_id = f"iv_custom_{uuid.uuid4().hex[:12]}"
    owner = {"X-Owner-Id": f"cost-{uuid.uuid4().hex[:8]}"}
    expected = heygen_avatar_iv_cost(60, 5.0)
    with TestClient(api.app) as client:
        job = _queue(
            client,
            _presenter_project(project_id, duration_seconds=60, narration="One minute presenter."),
            owner,
        )
        assert job["estimated_cost_usd"] == expected
        costs = client.get("/v1/costs", headers=owner)
        payload = costs.json()
        assert payload["heygen_rate_usd_per_minute"] == 5.0
        assert payload["heygen_estimated_usd"] == expected
        assert payload["gpu_job_count"] == 0
        health = client.get("/health")
        assert health.json()["heygen_rate_usd_per_minute"] == 5.0
        assert health.json()["heygen_engine"] == "avatar_iv"
