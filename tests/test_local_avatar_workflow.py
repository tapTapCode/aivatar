from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.media_registry import AuthorizedMediaRegistry
from src.orchestration.pipeline import PipelineOrchestrator
from src.providers.local.approved import ApprovedLocalLipSyncGenerator
from src.schemas.assets import AssetKind, GeneratedAsset, Provenance
from src.schemas.requests import GenerationContext, LipSyncRequest

PROOF = Path("packaged/local-avatar/avatar_quality_proof.mp4")
STILL = Path("packaged/local-avatar/presenter.png")


def _context(tmp_path: Path) -> GenerationContext:
    work = tmp_path / "work"
    work.mkdir(parents=True, exist_ok=True)
    return GenerationContext(
        project_id="proj_local",
        scene_id="presenter",
        request_id="req_local",
        job_id="job_local",
        work_dir=str(work),
    )


def _avatar(tmp_path: Path, *, avatar_id: str, uri: Path) -> GeneratedAsset:
    return GeneratedAsset(
        asset_id="avatar_test",
        kind=AssetKind.AVATAR_SOURCE,
        uri=str(uri),
        content_hash="a" * 64,
        project_id="proj_local",
        scene_id="presenter",
        mime_type="video/mp4",
        provenance=Provenance(
            provider="authorized-file-avatar-registry",
            model_identifier="client-supplied-avatar",
            checkpoint_revision="content-hash",
            model_configuration={"avatar_id": avatar_id, "source_type": "video"},
        ),
    )


@pytest.mark.media
@pytest.mark.skipif(not PROOF.is_file() or shutil.which("ffmpeg") is None, reason="proof or ffmpeg missing")
@pytest.mark.asyncio
async def test_approved_lipsync_uses_packaged_proof_for_default_avatar(tmp_path: Path) -> None:
    generator = ApprovedLocalLipSyncGenerator(PROOF)
    result = await generator.generate(
        LipSyncRequest(
            context=_context(tmp_path),
            avatar=_avatar(tmp_path, avatar_id="presenter-01", uri=PROOF),
            audio=None,
            narration_text="Quality script.",
            voice_id="provider_voice",
            duration_seconds=2.0,
            fps=25,
        )
    )
    assert result.provenance.provider == "local-musetalk-approved"
    assert result.duration_seconds is not None
    assert 1.8 <= result.duration_seconds <= 2.2
    assert Path(result.uri).is_file()


@pytest.mark.media
@pytest.mark.skipif(not STILL.is_file(), reason="presenter still missing")
@pytest.mark.asyncio
async def test_registry_seeds_default_presenter_once(tmp_path: Path) -> None:
    registry = AuthorizedMediaRegistry(tmp_path / "registry", max_bytes=8_000_000)
    first = await registry.ensure_default_presenter("owner-a", source=STILL)
    second = await registry.ensure_default_presenter("owner-a", source=STILL)
    other = await registry.ensure_default_presenter("owner-b", source=STILL)
    assert first is not None
    assert first.media_id == "presenter-01"
    assert second is None
    assert other is not None
    assert await registry.path_for("presenter-01", owner_id="owner-a")
    assert await registry.path_for("presenter-01", owner_id="owner-b")


@pytest.mark.media
@pytest.mark.skipif(not PROOF.is_file() or shutil.which("ffmpeg") is None, reason="proof or ffmpeg missing")
def test_add_avatar_approve_and_download_local_quality_mp4(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.api import main as api
    from src.api.provider_factory import build_provider_set

    monkeypatch.setattr(api.settings, "force_mock_providers", False)
    monkeypatch.setattr(api.settings, "provider_mode", "workers")
    monkeypatch.setattr(api.settings, "avatar_video_provider", "local_musetalk")
    monkeypatch.setattr(api.settings, "local_avatar_proof", PROOF)
    monkeypatch.setattr(api.settings, "default_avatar_id", "presenter-01")
    monkeypatch.setattr(api.settings, "work_root", tmp_path / "work")
    monkeypatch.setattr(api.settings, "local_storage_root", tmp_path / "assets")
    provider_set = build_provider_set(api.settings, api.renderer)
    monkeypatch.setattr(api, "provider_set", provider_set)
    monkeypatch.setattr(
        api,
        "pipeline",
        PipelineOrchestrator(provider_set, work_root=api.settings.work_root),
    )

    project_id = f"local_quality_{uuid.uuid4().hex}"
    owner = {"X-Owner-Id": "local-quality-owner"}
    project = {
        "project_id": project_id,
        "schema_version": "1.0",
        "channel_template": "default",
        "output": {
            "width": 320,
            "height": 240,
            "fps": 25,
            "aspect_ratio": "4:3",
            "video_codec": "h264",
            "audio_codec": "aac",
        },
        "scenes": [
            {
                "scene_id": "presenter",
                "order": 1,
                "visual_format": "PRESENTER",
                "narration_text": "Conservation teams study those changes carefully.",
                "avatar_id": "presenter-01",
                "voice_id": "provider_voice",
                "duration_seconds": 2.0,
                "layout_preset": "presenter_centered",
                "transition_out": "cut",
                "visual_provider": "image",
            }
        ],
        "consent_records": [
            {
                "subject_id": "presenter-01",
                "permission_type": "avatar",
                "granted_by": "local-quality-owner",
                "granted_at": "2026-08-15T00:00:00+00:00",
                "evidence_uri": "self-attested:presenter-01",
            },
            {
                "subject_id": "provider_voice",
                "permission_type": "voice",
                "granted_by": "local-quality-owner",
                "granted_at": "2026-08-15T00:00:00+00:00",
                "evidence_uri": "self-attested:provider_voice",
            },
        ],
    }
    with TestClient(api.app) as client:
        saved = client.post("/v1/projects", json=project, headers=owner)
        assert saved.status_code == 201, saved.text
        approved = client.post(f"/v1/projects/{project_id}/approve", headers=owner)
        assert approved.status_code == 200, approved.text
        created = client.post(
            "/v1/videos",
            json={**project, "approval_state": "approved"},
            headers={**owner, "Idempotency-Key": f"local-{uuid.uuid4().hex}"},
        )
        assert created.status_code == 202, created.text
        job = client.get(f"/v1/jobs/{created.json()['job_id']}", headers=owner)
        assert job.status_code == 200, job.text
        payload = job.json()
        assert payload["state"] == "COMPLETED", payload
        assert payload["output_asset_id"]
        assert payload["watermark_status"] == "CLEAN_AUTHORIZED"
        assert payload["estimated_cost_usd"] == 0.0
        assert payload["actual_cost_usd"] == 0.0
        download = client.get(f"/v1/assets/{payload['output_asset_id']}/content", headers=owner)
        assert download.status_code == 200
        assert download.headers["content-type"].startswith("video/")
        assert len(download.content) > 10_000
