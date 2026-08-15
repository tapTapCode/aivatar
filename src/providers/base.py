from __future__ import annotations

from typing import Protocol

from src.schemas.assets import GeneratedAsset
from src.schemas.requests import (
    AvatarSourceRequest,
    LipSyncRequest,
    SceneRenderRequest,
    SpeechGenerationRequest,
    VisualGenerationRequest,
)


class ProviderError(RuntimeError):
    """Base provider failure with a retryability hint."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class ProviderNotConfiguredError(ProviderError):
    pass


class ImageGenerator(Protocol):
    async def generate(self, request: VisualGenerationRequest) -> GeneratedAsset: ...


class VideoGenerator(Protocol):
    async def generate(self, request: VisualGenerationRequest) -> GeneratedAsset: ...


class SpeechGenerator(Protocol):
    async def generate(self, request: SpeechGenerationRequest) -> GeneratedAsset: ...


class LipSyncGenerator(Protocol):
    async def generate(self, request: LipSyncRequest) -> GeneratedAsset: ...


class AvatarSourceProvider(Protocol):
    async def resolve(self, request: AvatarSourceRequest) -> GeneratedAsset: ...


class SceneRenderer(Protocol):
    async def render(self, request: SceneRenderRequest) -> GeneratedAsset: ...
