from __future__ import annotations

import importlib
import inspect
import os
from typing import Literal

from fastapi import FastAPI, HTTPException, status

from src.providers.mock import (
    MockImageGenerator,
    MockLipSyncGenerator,
    MockSpeechGenerator,
    MockVideoGenerator,
)
from src.rendering.renderer import FFmpegSceneRenderer
from src.schemas.assets import GeneratedAsset
from src.schemas.requests import (
    LipSyncRequest,
    SceneRenderRequest,
    SpeechGenerationRequest,
    VisualGenerationRequest,
)

WorkerKind = Literal["image", "video", "tts", "lipsync", "render"]


def create_worker_app(kind: WorkerKind, *, provider_mode: str | None = None) -> FastAPI:
    mode = provider_mode or os.environ.get("PROVIDER_MODE", "unconfigured")
    external_provider = (
        _load_external_provider(os.environ.get("MODEL_ADAPTER"))
        if mode == "configured" and kind != "render"
        else None
    )
    app = FastAPI(title=f"{kind}-worker", version="1.0.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "worker": kind}

    @app.get("/ready")
    async def ready() -> dict[str, str]:
        if mode == "configured" and kind != "render" and external_provider is None:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "MODEL_ADAPTER is not configured",
            )
        if mode not in {"mock", "configured"}:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "model provider is not configured; set provider adapter and pinned revision",
            )
        return {"status": "ready", "worker": kind, "provider_mode": mode}

    if kind in {"image", "video"}:
        provider = (
            (MockImageGenerator() if kind == "image" else MockVideoGenerator())
            if mode == "mock"
            else external_provider
        )

        @app.post("/v1/generate", response_model=GeneratedAsset)
        async def generate_visual(request: VisualGenerationRequest) -> GeneratedAsset:
            _require_provider(mode, provider)
            return await _call_provider(provider, "generate", request)

    elif kind == "tts":
        provider = MockSpeechGenerator() if mode == "mock" else external_provider

        @app.post("/v1/generate", response_model=GeneratedAsset)
        async def generate_speech(request: SpeechGenerationRequest) -> GeneratedAsset:
            _require_provider(mode, provider)
            return await _call_provider(provider, "generate", request)

    elif kind == "lipsync":
        provider = MockLipSyncGenerator() if mode == "mock" else external_provider

        @app.post("/v1/generate", response_model=GeneratedAsset)
        async def generate_lipsync(request: LipSyncRequest) -> GeneratedAsset:
            _require_provider(mode, provider)
            return await _call_provider(provider, "generate", request)

    else:
        provider = FFmpegSceneRenderer()

        @app.post("/v1/generate", response_model=GeneratedAsset)
        async def render_scene(request: SceneRenderRequest) -> GeneratedAsset:
            _require_provider(mode, provider)
            return await provider.render(request)

    return app


def _require_provider(mode: str, provider: object | None) -> None:
    if mode not in {"mock", "configured"}:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "production model adapter is not configured",
        )
    if provider is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "MODEL_ADAPTER is missing or invalid",
        )


def _load_external_provider(reference: str | None) -> object | None:
    if not reference:
        return None
    module_name, separator, attribute = reference.partition(":")
    if not separator:
        raise RuntimeError("MODEL_ADAPTER must use module:factory syntax")
    factory = getattr(importlib.import_module(module_name), attribute)
    return factory()


async def _call_provider(provider: object, method_name: str, request: object) -> GeneratedAsset:
    result = getattr(provider, method_name)(request)
    if inspect.isawaitable(result):
        result = await result
    return GeneratedAsset.model_validate(result)
