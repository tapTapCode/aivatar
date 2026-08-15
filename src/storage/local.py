from __future__ import annotations

import asyncio
import os
from pathlib import Path

from src.providers.common import file_sha256
from src.schemas.assets import GeneratedAsset


class LocalAssetStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    async def put(self, asset: GeneratedAsset) -> GeneratedAsset:
        return await asyncio.to_thread(self._put, asset)

    def _put(self, asset: GeneratedAsset) -> GeneratedAsset:
        source = Path(asset.uri)
        if file_sha256(source) != asset.content_hash:
            raise ValueError("asset hash verification failed")
        target_dir = self.root / asset.project_id / asset.content_hash[:2]
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{asset.asset_id}{source.suffix}"
        if not target.exists():
            temporary = target.with_suffix(target.suffix + ".tmp")
            temporary.write_bytes(source.read_bytes())
            os.replace(temporary, target)
        return asset.model_copy(update={"uri": str(target)})

    def ready(self) -> bool:
        probe = self.root / ".readiness"
        try:
            probe.write_text("ready")
            probe.unlink()
            return True
        except OSError:
            return False
