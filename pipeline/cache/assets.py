from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def cache_key(*, kind: str, provider: str, model: str, prompt: str, parameters: dict[str, Any] | None = None) -> str:
    payload = {
        "kind": kind,
        "provider": provider,
        "model": model,
        "prompt": " ".join(prompt.split()),
        "parameters": parameters or {},
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(slots=True)
class CacheHit:
    key: str
    path: Path
    metadata: dict[str, Any]


class AssetCache:
    """Content-addressed local cache shared by all projects.

    Cache keys are derived from the generation contract rather than project IDs, so identical
    prompts/model parameters can be reused across channels/projects. Files are immutable once put.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _dir(self, key: str) -> Path:
        return self.root / key[:2] / key

    def peek(self, key: str) -> CacheHit | None:
        directory = self._dir(key)
        metadata_path = directory / "metadata.json"
        if not metadata_path.exists():
            return None
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        asset = directory / metadata["filename"]
        if not asset.exists():
            return None
        return CacheHit(key, asset, metadata)

    def get(self, key: str) -> CacheHit | None:
        hit = self.peek(key)
        if hit is None:
            return None
        metadata_path = self._dir(key) / "metadata.json"
        hit.metadata["hits"] = int(hit.metadata.get("hits", 0)) + 1
        metadata_path.write_text(json.dumps(hit.metadata, indent=2, sort_keys=True), encoding="utf-8")
        return hit

    def put(self, key: str, source: Path, metadata: dict[str, Any] | None = None) -> CacheHit:
        if not source.exists():
            raise FileNotFoundError(source)
        directory = self._dir(key)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / source.name
        if not target.exists():
            tmp = target.with_suffix(target.suffix + ".tmp")
            shutil.copy2(source, tmp)
            os.replace(tmp, target)
        body = {
            "key": key,
            "filename": target.name,
            "size_bytes": target.stat().st_size,
            "hits": 0,
            **(metadata or {}),
        }
        (directory / "metadata.json").write_text(json.dumps(body, indent=2, sort_keys=True), encoding="utf-8")
        return CacheHit(key, target, body)

    @staticmethod
    def materialize(hit: CacheHit, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            destination.unlink()
        try:
            os.link(hit.path, destination)
        except OSError:
            shutil.copy2(hit.path, destination)
        return destination
