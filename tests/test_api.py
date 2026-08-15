from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.main import app, public_job_error
from src.providers.base import ProviderError


@pytest.mark.media
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is required")
def test_video_api_completes_one_presenter_scene() -> None:
    project_id = f"api_test_{uuid.uuid4().hex}"
    project = {
        "project_id": project_id,
        "schema_version": "1.0",
        "channel_template": "default",
        "output": {
            "width": 320,
            "height": 240,
            "fps": 24,
            "aspect_ratio": "4:3",
            "video_codec": "h264",
            "audio_codec": "aac",
        },
        "scenes": [
            {
                "scene_id": "presenter",
                "order": 1,
                "visual_format": "PRESENTER",
                "narration_text": "Contract test.",
                "visual_description": None,
                "avatar_id": "mock_avatar",
                "voice_id": "mock_voice",
                "duration_seconds": 1.0,
                "layout_preset": "default",
                "transition_out": "cut",
                "visual_provider": "image",
            }
        ],
        "approval_state": "approved",
        "consent_records": [
            {
                "subject_id": "mock_avatar",
                "permission_type": "avatar",
                "granted_by": "api-test-owner",
                "granted_at": "2026-08-13T00:00:00+00:00",
                "evidence_uri": "test:mock_avatar",
            },
            {
                "subject_id": "mock_voice",
                "permission_type": "voice",
                "granted_by": "api-test-owner",
                "granted_at": "2026-08-13T00:00:00+00:00",
                "evidence_uri": "test:mock_voice",
            },
        ],
    }
    headers = {
        "Idempotency-Key": f"test-{uuid.uuid4().hex}",
        "X-Owner-Id": "api-test-owner",
    }
    with TestClient(app) as client:
        owner = {"X-Owner-Id": "api-test-owner"}
        saved = client.post("/v1/projects", json=project, headers=owner)
        assert saved.status_code == 201, saved.text
        assert saved.json()["approval_state"] == "draft"
        approved = client.post(f"/v1/projects/{project_id}/approve", headers=owner)
        assert approved.status_code == 200, approved.text
        assert approved.json()["approval_state"] == "approved"
        response = client.post("/v1/videos", json=project, headers=headers)
        assert response.status_code == 202, response.text
        payload = response.json()
        assert payload["watermark_status"] in {"PRESERVED", "CLEAN_AUTHORIZED"}
        job_response = client.get(f"/v1/jobs/{payload['job_id']}", headers=headers)
        assert job_response.status_code == 200
        job = job_response.json()
        assert job["state"] == "COMPLETED"
        assert job["output_asset_id"]
        assert job["watermark_status"] == payload["watermark_status"]
        assert client.get("/ready").status_code == 200

        listed_projects = client.get("/v1/projects", headers=headers)
        assert listed_projects.status_code == 200
        assert any(item["project_id"] == project_id for item in listed_projects.json())

        listed_videos = client.get("/v1/videos", headers=headers)
        assert listed_videos.status_code == 200
        assert any(item["video_id"] == payload["video_id"] for item in listed_videos.json())

        service = client.get("/")
        assert service.status_code == 200
        assert service.json()["service"] == "Aivatar Video Pipeline API"


def test_health_reports_heygen_api_when_key_is_missing() -> None:
    with TestClient(app) as client:
        health = client.get("/health")
        ready = client.get("/ready")
    assert health.status_code == 200
    payload = health.json()
    assert payload["status"] == "ok"
    assert payload["avatar_video_provider"] == "heygen_api"
    assert payload["lipsync_mode"] == "mock"
    assert payload["control_plane"] == "memory"
    assert payload["cost_billing"] == "heygen_api"
    assert payload["heygen_configured"] is False
    assert payload["heygen_engine"] == "avatar_iv"
    assert payload["heygen_rate_usd_per_minute"] == 4.0
    assert payload["local_proof_ready"] is False
    assert ready.status_code == 200
    assert ready.json()["lipsync_mode"] == "mock"


def test_backend_is_api_only() -> None:
    with TestClient(app) as client:
        css = client.get("/ui/assets/app.css")
        js = client.get("/ui/assets/app.js")
        auth_page = client.get("/auth")
        service = client.get("/")
    assert css.status_code == 404
    assert js.status_code == 404
    assert auth_page.status_code == 404
    assert service.json() == {
        "service": "Aivatar Video Pipeline API",
        "status": "ok",
        "documentation": "/docs",
    }


def test_auth_configuration_exposes_only_public_provider_status() -> None:
    with TestClient(app) as client:
        config = client.get("/v1/auth/config")
        page = client.get("/auth", follow_redirects=False)
    assert config.status_code == 200
    assert "superadmin_display_names" not in config.json()
    assert "superadmin_email_count" not in config.json()
    assert {item["name"] for item in config.json()["providers"]} == {"Google", "Apple"}
    assert page.status_code == 404


def test_public_asset_schema_does_not_expose_provider_or_storage_path() -> None:
    schema = app.openapi()["components"]["schemas"]["PublicAsset"]["properties"]
    assert "provenance" not in schema
    assert "uri" not in schema
    assert "retained" in schema


def test_provider_error_is_sanitized_for_customer_job_records() -> None:
    error = public_job_error(ProviderError("HeyGen upstream quota exhausted"))
    assert str(error) == "Presenter rendering failed. Please retry the job."
    assert "HeyGen" not in str(error)


def test_clean_export_rejects_imported_free_before_job_creation(monkeypatch) -> None:
    from src.api import main

    monkeypatch.setattr(main.settings, "avatar_video_provider", "imported_video")

    def rendering_allocation_would_be_a_failure(*_args, **_kwargs) -> None:
        raise AssertionError("clean-export routing must fail before resource cleanup or rendering")

    monkeypatch.setattr(main, "cleanup_expired_files", rendering_allocation_would_be_a_failure)
    project = {
        "project_id": f"clean_rejection_{uuid.uuid4().hex}",
        "schema_version": "1.0",
        "require_clean_export": True,
        "output": {"width": 640, "height": 360},
        "scenes": [
            {
                "scene_id": "presenter",
                "order": 1,
                "visual_format": "PRESENTER",
                "narration_text": "Clean export required.",
                "avatar_id": "authorized_presenter",
                "voice_id": "embedded_voice",
            }
        ],
    }
    with TestClient(app) as client:
        response = client.post(
            "/v1/videos",
            json=project,
            headers={
                "Idempotency-Key": f"reject-{uuid.uuid4().hex}",
                "X-Owner-Id": "routing-owner",
            },
        )
    assert response.status_code == 422
    assert response.json() == {
        "error": "UNLICENSED_WATERMARK_REJECTION",
        "message": (
            "Cannot satisfy clean export request with watermarked free source media. "
            "Please select an authorized provider (HeyGen API or local GPU)."
        ),
    }


@pytest.mark.media
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is required")
def test_authorized_presenter_upload_is_owner_scoped(tmp_path: Path) -> None:
    source = tmp_path / "presenter.png"
    subprocess.run(
        [
            shutil.which("ffmpeg") or "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=64x64",
            "-frames:v",
            "1",
            str(source),
        ],
        check=True,
    )
    owner_headers = {
        "X-Owner-Id": "upload-owner",
        "X-Filename": "presenter.png",
        "X-Media-Rights-Confirmed": "true",
        "Content-Type": "image/png",
    }
    with TestClient(app) as client:
        response = client.post(
            "/v1/media/presenter", content=source.read_bytes(), headers=owner_headers
        )
        assert response.status_code == 201, response.text
        media_id = response.json()["media_id"]
        own = client.get("/v1/media", headers={"X-Owner-Id": "upload-owner"})
        other = client.get("/v1/media", headers={"X-Owner-Id": "another-owner"})
        assert any(item["media_id"] == media_id for item in own.json())
        assert all(item["media_id"] != media_id for item in other.json())
