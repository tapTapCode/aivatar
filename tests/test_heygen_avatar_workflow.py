from __future__ import annotations

import uuid
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from src.orchestration.pipeline import PipelineOrchestrator
from src.providers.heygen import HeyGenLipSyncGenerator


def _mp4_bytes() -> bytes:
    return b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


def test_register_heygen_avatar_approve_and_export_mp4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.api import main as api
    from src.api.provider_factory import build_provider_set

    polls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v3/videos" and request.method == "POST":
            polls["creates"] = polls.get("creates", 0) + 1
            return httpx.Response(200, json={"data": {"video_id": "hg-video-01"}})
        if request.url.path == "/v3/videos/hg-video-01":
            polls["count"] += 1
            if polls["count"] < 2:
                return httpx.Response(200, json={"data": {"status": "processing"}})
            return httpx.Response(
                200,
                json={
                    "data": {
                        "status": "completed",
                        "video_url": "https://files.heygen.test/export.mp4",
                    }
                },
            )
        if request.url.host == "files.heygen.test":
            return httpx.Response(200, content=_mp4_bytes())
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(api.settings, "force_mock_providers", False)
    monkeypatch.setattr(api.settings, "provider_mode", "mock")
    monkeypatch.setattr(api.settings, "avatar_video_provider", "heygen_api")
    monkeypatch.setattr(api.settings, "heygen_api_key", "test-key")
    monkeypatch.setattr(api.settings, "heygen_default_voice_id", "voice-en")
    monkeypatch.setattr(api.settings, "work_root", tmp_path / "work")
    monkeypatch.setattr(api.settings, "local_storage_root", tmp_path / "assets")
    provider_set = build_provider_set(api.settings, api.renderer)
    provider_set.lipsync.client = client  # type: ignore[attr-defined]
    monkeypatch.setattr(api, "provider_set", provider_set)
    monkeypatch.setattr(
        api,
        "pipeline",
        PipelineOrchestrator(provider_set, work_root=api.settings.work_root),
    )

    project_id = f"heygen_flow_{uuid.uuid4().hex}"
    owner = {"X-Owner-Id": "heygen-owner", "X-Media-Rights-Confirmed": "true"}
    project = {
        "project_id": project_id,
        "schema_version": "1.0",
        "channel_template": "presenter_no_captions",
        "require_clean_export": True,
        "output": {
            "width": 1280,
            "height": 720,
            "fps": 30,
            "aspect_ratio": "16:9",
            "video_codec": "h264",
            "audio_codec": "aac",
        },
        "scenes": [
            {
                "scene_id": "presenter",
                "order": 1,
                "visual_format": "PRESENTER",
                "narration_text": "Conservation teams study those changes carefully.",
                "avatar_id": "Angela-inblack-20220820",
                "voice_id": "provider_voice",
                "duration_seconds": 2.0,
                "layout_preset": "presenter_centered",
                "transition_out": "cut",
                "visual_provider": "image",
            }
        ],
        "consent_records": [
            {
                "subject_id": "Angela-inblack-20220820",
                "permission_type": "avatar",
                "granted_by": "heygen-owner",
                "granted_at": "2026-08-15T00:00:00+00:00",
                "evidence_uri": "self-attested:Angela-inblack-20220820",
            },
            {
                "subject_id": "provider_voice",
                "permission_type": "voice",
                "granted_by": "heygen-owner",
                "granted_at": "2026-08-15T00:00:00+00:00",
                "evidence_uri": "self-attested:provider_voice",
            },
        ],
    }
    with TestClient(api.app) as test_client:
        registered = test_client.post(
            "/v1/heygen-avatars",
            json={"avatar_id": "Angela-inblack-20220820", "label": "Channel A"},
            headers=owner,
        )
        assert registered.status_code == 201, registered.text
        assert registered.json()["media_id"] == "Angela-inblack-20220820"
        saved = test_client.post("/v1/projects", json=project, headers=owner)
        assert saved.status_code == 201, saved.text
        approved = test_client.post(f"/v1/projects/{project_id}/approve", headers=owner)
        assert approved.status_code == 200, approved.text
        created = test_client.post(
            "/v1/videos",
            json={**project, "approval_state": "approved"},
            headers={**owner, "Idempotency-Key": f"heygen-{uuid.uuid4().hex}"},
        )
        assert created.status_code == 202, created.text
        video_id = created.json()["video_id"]
        first = test_client.get(f"/v1/videos/{video_id}", headers=owner)
        assert first.status_code == 200, first.text
        assert first.json()["state"] != "FAILED", first.json()
        second = test_client.get(f"/v1/videos/{video_id}", headers=owner)
        assert second.status_code == 200, second.text
        payload = second.json()
        if payload["state"] != "COMPLETED":
            third = test_client.get(f"/v1/videos/{video_id}", headers=owner)
            payload = third.json()
        assert payload["state"] == "COMPLETED", payload
        assert payload["output_asset_id"]
        assert payload["watermark_status"] == "CLEAN_AUTHORIZED"
        assert payload["provider_ref"] == "hg-video-01"
        assert polls.get("creates", 0) == 1
        assert payload["estimated_cost_usd"] == pytest.approx(0.1333)
        assert payload["actual_cost_usd"] == pytest.approx(0.1333)
        assert any(
            entry.get("note", "").startswith("heygen")
            for entry in payload.get("cost_entries") or []
        )
        costs = test_client.get("/v1/costs", headers=owner)
        assert costs.status_code == 200
        ledger = costs.json()
        assert ledger["billing_policy"] == (
            "HeyGen Avatar IV is billed at the configured per-minute rate."
        )
        assert ledger["heygen_rate_usd_per_minute"] == 4.0
        assert ledger["heygen_job_count"] >= 1
        assert ledger["gpu_job_count"] == 0
        download = test_client.get(
            f"/v1/assets/{payload['output_asset_id']}/content", headers=owner
        )
        assert download.status_code == 200
        assert download.headers["content-type"].startswith("video/")
        assert len(download.content) > 20


def test_heygen_catalog_lists_account_avatars_on_default_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.api import main as api
    from src.api.provider_factory import build_provider_set

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/voices":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "voices": [
                            {"voice_id": "voice-en", "name": "English Voice", "language": "English"},
                            {"voice_id": "voice-es", "name": "Spanish Voice", "language": "Spanish"},
                        ]
                    }
                },
            )
        if request.url.path == "/v2/avatars":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "talking_photos": [
                            {"talking_photo_id": "Angela-inblack-20220820", "name": "Channel A"}
                        ],
                        "avatars": [],
                    }
                },
            )
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(api.settings, "force_mock_providers", False)
    monkeypatch.setattr(api.settings, "provider_mode", "mock")
    monkeypatch.setattr(api.settings, "avatar_video_provider", "heygen_api")
    monkeypatch.setattr(api.settings, "heygen_api_key", "test-key")
    monkeypatch.setattr(api.settings, "heygen_default_voice_id", "")
    monkeypatch.setattr(api.settings, "work_root", tmp_path / "work")
    monkeypatch.setattr(api.settings, "local_storage_root", tmp_path / "assets")
    provider_set = build_provider_set(api.settings, api.renderer)
    provider_set.lipsync.client = client  # type: ignore[attr-defined]
    monkeypatch.setattr(api, "provider_set", provider_set)

    with TestClient(api.app) as test_client:
        catalog = test_client.get("/v1/heygen/catalog")
    assert catalog.status_code == 200
    payload = catalog.json()
    assert payload["configured"] is True
    assert payload["default_voice_id"] == "voice-en"
    assert payload["voices"][0]["voice_id"] == "voice-en"
    assert payload["avatars"] == [
        {"avatar_id": "Angela-inblack-20220820", "name": "Channel A"}
    ]


def test_heygen_catalog_empty_without_key() -> None:
    from src.api.main import app

    with TestClient(app) as client:
        catalog = client.get("/v1/heygen/catalog")
    assert catalog.status_code == 200
    payload = catalog.json()
    assert payload["configured"] is False
    assert payload["voices"] == []
    assert payload["avatars"] == []
