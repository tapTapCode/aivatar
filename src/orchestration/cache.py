from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from src.providers.common import canonical_hash, file_sha256
from src.schemas.assets import GeneratedAsset


def generation_cache_key(
    *,
    provider: str,
    model: str,
    model_revision: str,
    prompt: str,
    negative_prompt: str | None,
    seed: int,
    width: int,
    height: int,
    steps: int,
    guidance: float,
    quantization: str | None,
    settings: dict[str, Any] | None = None,
) -> str:
    return canonical_hash(
        {
            "provider": provider,
            "model": model,
            "model_revision": model_revision,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "seed": seed,
            "width": width,
            "height": height,
            "steps": steps,
            "guidance": guidance,
            "quantization": quantization,
            "settings": settings or {},
        }
    )


class ContentAddressedAssetCache:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _lock_for(self, key: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(key, threading.Lock())

    def get(self, key: str) -> GeneratedAsset | None:
        metadata = self.root / key[:2] / key / "asset.json"
        if not metadata.exists():
            return None
        asset = GeneratedAsset.model_validate_json(metadata.read_text())
        uri = Path(asset.uri)
        if not uri.exists() or file_sha256(uri) != asset.content_hash:
            return None
        return asset

    def put(self, key: str, asset: GeneratedAsset) -> GeneratedAsset:
        with self._lock_for(key):
            target_dir = self.root / key[:2] / key
            target_dir.mkdir(parents=True, exist_ok=True)
            source = Path(asset.uri)
            if file_sha256(source) != asset.content_hash:
                raise ValueError("asset hash does not match file contents")
            target = target_dir / source.name
            if not target.exists():
                temporary = target.with_suffix(target.suffix + ".tmp")
                temporary.write_bytes(source.read_bytes())
                os.replace(temporary, target)
            cached = asset.model_copy(update={"uri": str(target.resolve())})
            metadata = target_dir / "asset.json"
            temporary_metadata = target_dir / "asset.json.tmp"
            temporary_metadata.write_text(
                json.dumps(cached.model_dump(mode="json"), sort_keys=True, indent=2)
            )
            os.replace(temporary_metadata, metadata)
            return cached

    def invalidate(self, key: str) -> bool:
        directory = self.root / key[:2] / key
        if not directory.exists():
            return False
        for path in sorted(directory.iterdir(), reverse=True):
            path.unlink()
        directory.rmdir()
        return True
