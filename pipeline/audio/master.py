from __future__ import annotations

import json
from pathlib import Path

from pipeline.render.ffmpeg import ffprobe, run


def audio_duration(path: Path) -> float:
    data = ffprobe(path)
    return float(data["format"]["duration"])


def normalize_master_audio(source: Path, output_dir: Path) -> tuple[Path, Path, float]:
    """Normalize any supported input into the authoritative 48 kHz mono master WAV + MP3."""
    if not source.exists():
        raise FileNotFoundError(source)
    output_dir.mkdir(parents=True, exist_ok=True)
    wav = output_dir / "master_voice.wav"
    mp3 = output_dir / "master_voice.mp3"
    run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(source),
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "48000", "-ac", "1", str(wav),
    ])
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-codec:a", "libmp3lame", "-q:a", "3", str(mp3)])
    duration = audio_duration(wav)
    return wav, mp3, duration


def cut_audio_segment(master: Path, start: float, end: float, output: Path) -> Path:
    if end <= start:
        raise ValueError("end must be greater than start")
    output.parent.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
        "-i", str(master), "-ar", "48000", "-ac", "1", str(output),
    ])
    return output


def write_audio_manifest(output_dir: Path, provider: str, duration: float, metadata: dict | None = None) -> Path:
    path = output_dir / "audio_manifest.json"
    path.write_text(json.dumps({"provider": provider, "duration": duration, "metadata": metadata or {}}, indent=2), encoding="utf-8")
    return path
