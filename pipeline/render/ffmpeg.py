from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode:
        raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stderr[-5000:]}")
    return proc


def ffprobe(path: Path) -> dict:
    proc = run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)])
    return json.loads(proc.stdout)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _stamp(seconds: float, vtt_mode: bool = False) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    sep = "." if vtt_mode else ","
    return f"{h:02}:{m:02}:{s:02}{sep}{ms:03}"


def write_caption_segments(segments, srt: Path, vtt: Path) -> None:
    srt_lines: list[str] = []
    vtt_lines = ["WEBVTT", ""]
    for i, segment in enumerate(segments, 1):
        text = str(segment.text).strip()
        if not text:
            continue
        srt_lines += [str(i), f"{_stamp(segment.start)} --> {_stamp(segment.end)}", text, ""]
        vtt_lines += [f"{_stamp(segment.start, True)} --> {_stamp(segment.end, True)}", text, ""]
    srt.write_text("\n".join(srt_lines), encoding="utf-8")
    vtt.write_text("\n".join(vtt_lines), encoding="utf-8")


def write_captions(scenes, srt: Path, vtt: Path) -> None:
    """Backward-compatible scene captions used by older tests/tools."""
    class Segment:
        def __init__(self, text: str, start: float, end: float) -> None:
            self.text, self.start, self.end = text, start, end
    segments = [Segment(f"Scene {i}: {scene.visual_prompt[:90]}", scene.start, scene.end) for i, scene in enumerate(scenes, 1)]
    write_caption_segments(segments, srt, vtt)
