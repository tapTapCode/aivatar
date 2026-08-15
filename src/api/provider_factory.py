from __future__ import annotations

from typing import Literal

from src.api.config import Settings
from src.api.packaged_paths import resolve_packaged_file
from src.orchestration.pipeline import ProviderSet
from src.providers.avatar import FileAvatarSourceProvider
from src.providers.base import SceneRenderer
from src.providers.heygen import HeyGenAvatarSourceProvider, HeyGenLipSyncGenerator
from src.providers.imported import ImportedPresenterVideoGenerator
from src.providers.image import ImageWorkerClient
from src.providers.lipsync import LipSyncWorkerClient
from src.providers.local.approved import ApprovedLocalLipSyncGenerator
from src.providers.mock import (
    MockAvatarSourceProvider,
    MockImageGenerator,
    MockLipSyncGenerator,
    MockSpeechGenerator,
    MockVideoGenerator,
)
from src.providers.render import RenderWorkerClient
from src.providers.speech import SpeechWorkerClient
from src.providers.video import VideoWorkerClient
from src.storage.s3 import S3RetentionStore

LipSyncMode = Literal[
    "mock",
    "in_process_approved",
    "lipsync_worker",
    "imported_video",
    "heygen_api",
]


def resolved_local_avatar_proof(settings: Settings):
    return resolve_packaged_file(settings.local_avatar_proof)


def resolved_local_avatar_image(settings: Settings):
    return resolve_packaged_file(settings.local_avatar_image)


def local_avatar_proof_available(settings: Settings) -> bool:
    return (
        settings.avatar_video_provider == "local_musetalk"
        and resolved_local_avatar_proof(settings) is not None
    )


def lipsync_mode(settings: Settings) -> LipSyncMode:
    """Return the lipsync backend the control plane will actually call."""

    if settings.force_mock_providers:
        return "mock"
    if settings.avatar_video_provider == "heygen_api":
        return "heygen_api"
    if settings.avatar_video_provider == "imported_video":
        return "imported_video"
    if local_avatar_proof_available(settings):
        return "in_process_approved"
    if settings.provider_mode == "workers":
        return "lipsync_worker"
    return "mock"


def build_provider_set(settings: Settings, renderer: SceneRenderer) -> ProviderSet:
    """Build the in-process or worker provider set for the configured avatar path."""

    mode = lipsync_mode(settings)
    if mode == "mock":
        return ProviderSet(
            speech=MockSpeechGenerator(),
            avatar_source=MockAvatarSourceProvider(),
            lipsync=MockLipSyncGenerator(),
            image=MockImageGenerator(),
            video=MockVideoGenerator(),
            renderer=renderer,
        )

    if mode == "heygen_api":
        retention_store = (
            S3RetentionStore(
                endpoint_url=settings.s3_endpoint_url,
                bucket=settings.s3_bucket,
                access_key_id=settings.s3_access_key,
                secret_access_key=settings.s3_secret_key,
                prefix=settings.heygen_r2_prefix,
            )
            if settings.heygen_r2_retention_enabled
            else None
        )
        return ProviderSet(
            speech=SpeechWorkerClient(settings.tts_worker_url),
            avatar_source=HeyGenAvatarSourceProvider(),
            lipsync=HeyGenLipSyncGenerator(
                api_key=settings.heygen_api_key or "",
                api_base=settings.heygen_api_base,
                engine=settings.heygen_engine,
                voice_mode=settings.heygen_voice_mode,
                resolution=settings.heygen_resolution,
                default_voice_id=settings.heygen_default_voice_id,
                rate_usd_per_minute=settings.heygen_rate_usd_per_minute,
                maximum_cost_usd_per_job=settings.heygen_maximum_cost_usd_per_job,
                poll_interval_seconds=settings.heygen_poll_interval_seconds,
                timeout_seconds=settings.heygen_timeout_seconds,
                retention_store=retention_store,
            ),
            image=ImageWorkerClient(settings.image_worker_url),
            video=VideoWorkerClient(settings.video_worker_url),
            renderer=RenderWorkerClient(settings.render_worker_url),
            native_presenter_voice=settings.heygen_voice_mode == "native",
        )

    if mode == "imported_video":
        return ProviderSet(
            speech=MockSpeechGenerator(),
            avatar_source=FileAvatarSourceProvider(settings.avatar_registry_root),
            lipsync=ImportedPresenterVideoGenerator(),
            image=MockImageGenerator(),
            video=MockVideoGenerator(),
            renderer=renderer,
            native_presenter_voice=True,
        )

    proof = resolved_local_avatar_proof(settings)
    if mode == "in_process_approved" and proof is not None:
        return ProviderSet(
            speech=MockSpeechGenerator(),
            avatar_source=FileAvatarSourceProvider(settings.avatar_registry_root),
            lipsync=ApprovedLocalLipSyncGenerator(
                proof, default_avatar_ids=frozenset({settings.default_avatar_id})
            ),
            image=MockImageGenerator(),
            video=MockVideoGenerator(),
            renderer=renderer,
            native_presenter_voice=False,
        )

    return ProviderSet(
        speech=SpeechWorkerClient(settings.tts_worker_url),
        avatar_source=FileAvatarSourceProvider(settings.avatar_registry_root),
        lipsync=LipSyncWorkerClient(settings.lipsync_worker_url),
        image=ImageWorkerClient(settings.image_worker_url),
        video=VideoWorkerClient(settings.video_worker_url),
        renderer=RenderWorkerClient(settings.render_worker_url),
    )
