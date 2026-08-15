from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.config import Settings
from src.api.media_registry import AuthorizedMediaRegistry
from src.api.provider_factory import build_provider_set, lipsync_mode
from src.orchestration.cost import HEYGEN_COST_POLICY, build_cost_ledger
from src.providers.heygen import HeyGenAvatarSourceProvider, HeyGenLipSyncGenerator
from src.rendering import FFmpegSceneRenderer


def test_settings_default_avatar_provider_is_heygen_api() -> None:
    assert Settings.model_fields["avatar_video_provider"].default == "heygen_api"


def test_unmocked_heygen_default_builds_heygen_providers() -> None:
    settings = Settings(
        force_mock_providers=False,
        provider_mode="mock",
        avatar_video_provider="heygen_api",
        heygen_api_key="",
    )
    assert lipsync_mode(settings) == "heygen_api"
    providers = build_provider_set(settings, FFmpegSceneRenderer())
    assert isinstance(providers.avatar_source, HeyGenAvatarSourceProvider)
    assert isinstance(providers.lipsync, HeyGenLipSyncGenerator)
    assert providers.native_presenter_voice is True


def test_cost_ledger_defaults_to_heygen_policy() -> None:
    ledger = build_cost_ledger([], gpu_hourly_rate_usd=0.22)
    assert ledger["billing_policy"] == HEYGEN_COST_POLICY
    assert ledger["heygen_engine"] == "avatar_iv"
    assert ledger["heygen_rate_usd_per_minute"] == 4.0
    assert ledger["heygen_job_count"] == 0


@pytest.mark.asyncio
async def test_heygen_default_does_not_seed_musetalk_presenter(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.api import main as api

    registry = AuthorizedMediaRegistry(tmp_path / "media", max_bytes=1_000_000)
    monkeypatch.setattr(api.settings, "avatar_video_provider", "heygen_api")
    monkeypatch.setattr(api.settings, "default_avatar_id", "presenter-01")
    monkeypatch.setattr(api, "media_registry", registry)

    await api.ensure_packaged_presenter("owner-heygen")

    assert await registry.list(owner_id="owner-heygen", kind="presenter") == []
    assert await registry.path_for("presenter-01", owner_id="owner-heygen") is None


def test_media_list_does_not_seed_packaged_musetalk_presenter() -> None:
    from src.api.main import app

    owner = {"X-Owner-Id": f"noseed-{uuid.uuid4().hex}"}
    with TestClient(app) as client:
        health = client.get("/health")
        listed = client.get("/v1/media", headers=owner)
    assert health.json()["avatar_video_provider"] == "heygen_api"
    assert health.json()["heygen_configured"] is False
    assert health.json()["local_proof_ready"] is False
    assert listed.status_code == 200
    assert listed.json() == []


@pytest.mark.asyncio
async def test_musetalk_seed_stays_gated_to_explicit_local_provider(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.api import main as api

    proof = Path("packaged/local-avatar/avatar_quality_proof.mp4")
    if not proof.is_file():
        pytest.skip("packaged local avatar proof is missing")
    registry = AuthorizedMediaRegistry(tmp_path / "media", max_bytes=8_000_000)
    monkeypatch.setattr(api.settings, "avatar_video_provider", "local_musetalk")
    monkeypatch.setattr(api.settings, "default_avatar_id", "presenter-01")
    monkeypatch.setattr(api, "media_registry", registry)

    await api.ensure_packaged_presenter("owner-local")

    presenters = await registry.list(owner_id="owner-local", kind="presenter")
    assert [item.media_id for item in presenters] == ["presenter-01"]
