from __future__ import annotations

import asyncio

from src.schemas.assets import GeneratedAsset


class AssetRepository:
    def __init__(self) -> None:
        self._assets: dict[str, GeneratedAsset] = {}
        self._owners: dict[str, str] = {}
        self._retained_uris: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def put(self, asset: GeneratedAsset, *, owner_id: str) -> None:
        async with self._lock:
            self._assets[asset.asset_id] = asset
            self._owners[asset.asset_id] = owner_id

    async def get(self, asset_id: str, *, owner_id: str) -> GeneratedAsset | None:
        async with self._lock:
            if self._owners.get(asset_id) != owner_id:
                return None
            return self._assets.get(asset_id)

    async def mark_retained(self, asset_id: str, *, owner_id: str, uri: str) -> None:
        async with self._lock:
            if self._owners.get(asset_id) != owner_id:
                raise KeyError(asset_id)
            self._retained_uris[asset_id] = uri

    async def retained_uri(self, asset_id: str, *, owner_id: str) -> str | None:
        async with self._lock:
            if self._owners.get(asset_id) != owner_id:
                return None
            return self._retained_uris.get(asset_id)
