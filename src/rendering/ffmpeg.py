from __future__ import annotations

import json
import logging
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class FFmpegError(RuntimeError):
    def __init__(self, message: str, *, command: Sequence[str], stderr: str) -> None:
        super().__init__(message)
        self.command = tuple(command)
        self.stderr = stderr


@dataclass(frozen=True)
class CommandResult:
    command: tuple[str, ...]
    stdout: str
    stderr: str


class FFmpegRunner:
    def __init__(self, ffmpeg: str | None = None, ffprobe: str | None = None) -> None:
        self.ffmpeg = ffmpeg or shutil.which("ffmpeg") or "ffmpeg"
        self.ffprobe = ffprobe or shutil.which("ffprobe") or "ffprobe"

    def run(self, arguments: Sequence[str]) -> CommandResult:
        command = (self.ffmpeg, "-hide_banner", "-nostdin", *arguments)
        logger.info("ffmpeg_command", extra={"command": list(command)})
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        if completed.returncode:
            raise FFmpegError(
                f"ffmpeg failed with exit code {completed.returncode}",
                command=command,
                stderr=completed.stderr[-8000:],
            )
        return CommandResult(command, completed.stdout, completed.stderr)

    def probe(self, uri: str) -> dict[str, object]:
        command = (
            self.ffprobe,
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            uri,
        )
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        if completed.returncode:
            raise FFmpegError(
                f"ffprobe failed with exit code {completed.returncode}",
                command=command,
                stderr=completed.stderr[-8000:],
            )
        return json.loads(completed.stdout)
