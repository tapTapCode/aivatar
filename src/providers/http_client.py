from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import TypeVar

from pydantic import BaseModel

from src.providers.base import ProviderError
from src.schemas.assets import GeneratedAsset

RequestT = TypeVar("RequestT", bound=BaseModel)


class JsonHttpProviderClient:
    """Small standard-library client for isolated internal worker services."""

    def __init__(self, base_url: str, *, timeout_seconds: float = 3600) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def post_asset(self, endpoint: str, request: RequestT) -> GeneratedAsset:
        import asyncio

        return await asyncio.to_thread(self._post_asset, endpoint, request)

    def _post_asset(self, endpoint: str, request: RequestT) -> GeneratedAsset:
        payload = request.model_dump_json().encode()
        http_request = urllib.request.Request(
            f"{self.base_url}/{endpoint.lstrip('/')}",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                return GeneratedAsset.model_validate(json.load(response))
        except urllib.error.HTTPError as exc:
            retryable = exc.code >= 500 or exc.code == 429
            raise ProviderError(f"worker returned HTTP {exc.code}", retryable=retryable) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ProviderError("worker request failed", retryable=True) from exc
