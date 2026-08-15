from pathlib import Path

import pytest

from src.api.config import Settings
from src.api.packaged_paths import resolve_packaged_file
from src.api.provider_factory import (
    build_provider_set,
    lipsync_mode,
    local_avatar_proof_available,
)
from src.providers.avatar import FileAvatarSourceProvider
from src.providers.heygen import HeyGenAvatarSourceProvider, HeyGenLipSyncGenerator
from src.providers.imported import ImportedPresenterVideoGenerator
from src.providers.lipsync import LipSyncWorkerClient
from src.providers.local.approved import ApprovedLocalLipSyncGenerator
from src.providers.mock import MockAvatarSourceProvider, MockLipSyncGenerator
from src.rendering import FFmpegSceneRenderer

PROOF = Path("packaged/local-avatar/avatar_quality_proof.mp4")


def test_mock_flag_keeps_deterministic_providers() -> None:
    settings = Settings(
        force_mock_providers=True,
        provider_mode="mock",
        avatar_video_provider="local_musetalk",
        local_avatar_proof=PROOF,
    )
    providers = build_provider_set(settings, FFmpegSceneRenderer())
    assert lipsync_mode(settings) == "mock"
    assert isinstance(providers.avatar_source, MockAvatarSourceProvider)
    assert isinstance(providers.lipsync, MockLipSyncGenerator)


def test_local_musetalk_uses_approved_proof_in_process() -> None:
    if not PROOF.is_file():
        pytest.skip("packaged local avatar proof is missing")
    settings = Settings(
        force_mock_providers=False,
        provider_mode="mock",
        avatar_video_provider="local_musetalk",
        local_avatar_proof=PROOF,
    )
    assert local_avatar_proof_available(settings)
    assert lipsync_mode(settings) == "in_process_approved"
    providers = build_provider_set(settings, FFmpegSceneRenderer())
    assert isinstance(providers.avatar_source, FileAvatarSourceProvider)
    assert isinstance(providers.lipsync, ApprovedLocalLipSyncGenerator)
    assert not isinstance(providers.lipsync, LipSyncWorkerClient)


def test_workers_mode_with_packaged_proof_stays_in_process() -> None:
    if not PROOF.is_file():
        pytest.skip("packaged local avatar proof is missing")
    settings = Settings(
        force_mock_providers=False,
        provider_mode="workers",
        avatar_video_provider="local_musetalk",
        local_avatar_proof=PROOF,
    )
    assert lipsync_mode(settings) == "in_process_approved"
    providers = build_provider_set(settings, FFmpegSceneRenderer())
    assert isinstance(providers.lipsync, ApprovedLocalLipSyncGenerator)
    assert providers.lipsync.proof_path == PROOF.resolve()


def test_workers_mode_without_proof_uses_lipsync_worker(tmp_path: Path) -> None:
    settings = Settings(
        force_mock_providers=False,
        provider_mode="workers",
        avatar_video_provider="local_musetalk",
        local_avatar_proof=tmp_path / "missing-proof.mp4",
    )
    assert lipsync_mode(settings) == "lipsync_worker"
    providers = build_provider_set(settings, FFmpegSceneRenderer())
    assert isinstance(providers.lipsync, LipSyncWorkerClient)


def test_heygen_api_is_used_when_not_mocked() -> None:
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


def test_imported_video_does_not_use_approved_proof() -> None:
    settings = Settings(
        force_mock_providers=False,
        provider_mode="workers",
        avatar_video_provider="imported_video",
        local_avatar_proof=PROOF,
    )
    assert lipsync_mode(settings) == "imported_video"
    providers = build_provider_set(settings, FFmpegSceneRenderer())
    assert isinstance(providers.lipsync, ImportedPresenterVideoGenerator)


def test_resolve_packaged_file_from_repo_root_when_cwd_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not PROOF.is_file():
        pytest.skip("packaged local avatar proof is missing")
    monkeypatch.chdir(tmp_path)
    resolved = resolve_packaged_file("packaged/local-avatar/avatar_quality_proof.mp4")
    assert resolved is not None
    assert resolved.is_file()
    settings = Settings(
        force_mock_providers=False,
        provider_mode="workers",
        avatar_video_provider="local_musetalk",
        local_avatar_proof=Path("packaged/local-avatar/avatar_quality_proof.mp4"),
    )
    assert local_avatar_proof_available(settings)
    assert lipsync_mode(settings) == "in_process_approved"
