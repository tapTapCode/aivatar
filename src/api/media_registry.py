from __future__ import annotations

import asyncio
import json
import mimetypes
import shutil
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from src.rendering.ffmpeg import FFmpegRunner

MediaKind = Literal["presenter", "voice", "background"]

PRESENTER_VIDEO_SUFFIXES = {".mp4", ".mov", ".webm"}
HEYGEN_AVATAR_ID_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
)
ALLOWED_SUFFIXES: dict[MediaKind, set[str]] = {
    "presenter": {".png", ".jpg", ".jpeg", ".webp", *PRESENTER_VIDEO_SUFFIXES},
    "voice": {".wav", ".mp3", ".flac", ".m4a"},
    "background": {".mp4", ".mov", ".webm", ".png", ".jpg", ".jpeg", ".webp"},
}


class RegisteredMedia(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    media_id: str
    owner_id: str
    kind: MediaKind
    original_filename: str
    content_type: str


class AuthorizedMediaRegistry:
    """Owner-scoped registry for explicitly authorized local media."""

    def __init__(
        self,
        root: str | Path,
        *,
        max_bytes: int,
        presenter_root: str | Path | None = None,
        voice_root: str | Path | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.max_bytes = max_bytes
        self.kind_roots = {
            "presenter": (
                Path(presenter_root).resolve() if presenter_root else self.root / "presenters"
            ),
            "voice": Path(voice_root).resolve() if voice_root else self.root / "voices",
            "background": self.root / "backgrounds",
        }
        self._records: dict[tuple[str, str], tuple[RegisteredMedia, Path]] = {}
        self._lock = asyncio.Lock()

    def _key(self, owner_id: str, media_id: str) -> tuple[str, str]:
        return (owner_id, media_id)

    async def register(
        self,
        *,
        owner_id: str,
        kind: MediaKind,
        filename: str,
        content_type: str,
        payload: bytes,
    ) -> RegisteredMedia:
        if not payload or len(payload) > self.max_bytes:
            raise ValueError(f"file must be between 1 and {self.max_bytes} bytes")
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES[kind]:
            raise ValueError(f"unsupported {kind} file extension")
        media_id = f"{kind}_{uuid.uuid4().hex}"
        kind_root = self.kind_roots[kind].resolve()
        kind_root.mkdir(parents=True, exist_ok=True)
        target = kind_root / f"{media_id}{suffix}"
        if not target.resolve().is_relative_to(kind_root):
            raise ValueError("invalid media target")
        target.write_bytes(payload)
        try:
            await asyncio.to_thread(self._validate_media, target, kind)
        except Exception:
            target.unlink(missing_ok=True)
            raise ValueError("uploaded file is not valid supported media") from None
        record = RegisteredMedia(
            media_id=media_id,
            owner_id=owner_id,
            kind=kind,
            original_filename=Path(filename).name[:200],
            content_type=(
                content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
            ),
        )
        async with self._lock:
            self._records[self._key(owner_id, media_id)] = (record, target)
        return record

    async def register_existing(
        self,
        *,
        owner_id: str,
        kind: MediaKind,
        media_id: str,
        filename: str,
        content_type: str,
        source: Path,
    ) -> RegisteredMedia:
        if not source.is_file():
            raise ValueError("seeded media file is missing")
        kind_root = self.kind_roots[kind].resolve()
        kind_root.mkdir(parents=True, exist_ok=True)
        suffix = source.suffix.lower()
        target = kind_root / f"{media_id}{suffix}"
        if source.resolve() != target:
            shutil.copy2(source, target)
        record = RegisteredMedia(
            media_id=media_id,
            owner_id=owner_id,
            kind=kind,
            original_filename=Path(filename).name[:200],
            content_type=content_type,
        )
        async with self._lock:
            self._records[self._key(owner_id, media_id)] = (record, target)
        return record

    async def register_heygen_avatar(
        self,
        *,
        owner_id: str,
        avatar_id: str,
        label: str = "",
    ) -> RegisteredMedia:
        avatar_id_value = avatar_id.strip()
        if (
            len(avatar_id_value) < 2
            or len(avatar_id_value) > 128
            or any(character not in HEYGEN_AVATAR_ID_CHARS for character in avatar_id_value)
        ):
            raise ValueError("HeyGen avatar ID must be 2-128 letters, numbers, dots, hyphens, or underscores")
        existing = await self.get(avatar_id_value, owner_id=owner_id)
        if existing is not None:
            return existing[0]
        kind_root = self.kind_roots["presenter"].resolve()
        kind_root.mkdir(parents=True, exist_ok=True)
        target = kind_root / f"{avatar_id_value}.json"
        if not target.resolve().is_relative_to(kind_root):
            raise ValueError("invalid HeyGen avatar target")
        target.write_text(
            json.dumps({"avatar_id": avatar_id_value, "provider": "heygen_api"}, sort_keys=True)
            + "\n"
        )
        record = RegisteredMedia(
            media_id=avatar_id_value,
            owner_id=owner_id,
            kind="presenter",
            original_filename=(label.strip() or avatar_id_value)[:200],
            content_type="application/json",
        )
        async with self._lock:
            self._records[self._key(owner_id, avatar_id_value)] = (record, target)
        return record

    async def ensure_default_presenter(
        self,
        owner_id: str,
        *,
        source: Path,
        media_id: str = "presenter-01",
    ) -> RegisteredMedia | None:
        if not source.is_file():
            return None
        existing = await self.list(owner_id=owner_id, kind="presenter")
        if existing:
            return None
        suffix = source.suffix.lower()
        content_type = "video/mp4" if suffix in PRESENTER_VIDEO_SUFFIXES else "image/png"
        return await self.register_existing(
            owner_id=owner_id,
            kind="presenter",
            media_id=media_id,
            filename=source.name,
            content_type=content_type,
            source=source,
        )

    async def list(self, *, owner_id: str, kind: MediaKind | None = None) -> list[RegisteredMedia]:
        async with self._lock:
            return [
                record
                for record, _ in self._records.values()
                if record.owner_id == owner_id and (kind is None or record.kind == kind)
            ]

    async def get(
        self, media_id: str, *, owner_id: str
    ) -> tuple[RegisteredMedia, Path] | None:
        async with self._lock:
            value = self._records.get(self._key(owner_id, media_id))
            if value is None or value[0].owner_id != owner_id:
                return None
            return value

    async def path_for(self, media_id: str, *, owner_id: str) -> Path | None:
        stored = await self.get(media_id, owner_id=owner_id)
        return stored[1] if stored else None

    async def delete(self, media_id: str, *, owner_id: str) -> bool:
        async with self._lock:
            value = self._records.get(self._key(owner_id, media_id))
            if value is None or value[0].owner_id != owner_id:
                return False
            del self._records[self._key(owner_id, media_id)]
            still_used = any(path == value[1] for _, path in self._records.values())
        if not still_used:
            value[1].unlink(missing_ok=True)
        return True

    @staticmethod
    def _validate_media(path: Path, kind: MediaKind) -> None:
        data = FFmpegRunner().probe(str(path))
        streams = data.get("streams", [])
        stream_types = {stream.get("codec_type") for stream in streams}
        if kind == "voice":
            required = {"audio"}
        elif kind == "presenter" and path.suffix.lower() in PRESENTER_VIDEO_SUFFIXES:
            required = {"video", "audio"}
        else:
            required = {"video"}
        missing = required - stream_types
        if missing:
            raise ValueError(f"{' and '.join(sorted(missing))} stream is missing")
