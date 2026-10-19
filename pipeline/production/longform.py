from __future__ import annotations

import json
import time
from pathlib import Path

from pipeline.production.quality import production_qc
from pipeline.render.ffmpeg import run, sha256


def _write_captions(path: Path, minutes: int) -> None:
    lines: list[str] = []
    for minute in range(minutes):
        start = minute * 60
        end = start + 8
        sh, rem = divmod(start, 3600); sm, ss = divmod(rem, 60)
        eh, rem = divmod(end, 3600); em, es = divmod(rem, 60)
        lines += [str(minute + 1), f"{sh:02}:{sm:02}:{ss:02},000 --> {eh:02}:{em:02}:{es:02},000", f"Aivatar long-form reliability minute {minute + 1}", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def ensure_one_minute_seed(workdir: Path, width: int = 1920, height: int = 1080, fps: int = 30) -> Path:
    seed = workdir / "seed_60s.mp4"
    if seed.exists() and seed.stat().st_size > 100_000:
        return seed
    workdir.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c=0x16213e:s={width}x{height}:r={fps}:d=60",
        "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000:duration=60",
        "-vf", "drawgrid=width=160:height=90:thickness=1:color=white@0.07",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k", "-shortest", str(seed),
    ])
    return seed


def assemble_longform_proof(output_dir: Path, minutes: int, *, width: int = 1920, height: int = 1080, fps: int = 30) -> dict:
    if minutes <= 0 or minutes > 60:
        raise ValueError("minutes must be between 1 and 60")
    output_dir.mkdir(parents=True, exist_ok=True)
    seed = ensure_one_minute_seed(output_dir, width, height, fps)
    concat_file = output_dir / f"concat_{minutes}m.txt"
    concat_file.write_text("\n".join(f"file '{seed.resolve()}'" for _ in range(minutes)), encoding="utf-8")
    timeline = output_dir / f"timeline_{minutes}m.mp4"
    started = time.monotonic()
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(timeline)])
    srt = output_dir / f"captions_{minutes}m.srt"
    _write_captions(srt, minutes)
    final = output_dir / f"aivatar-longform-{minutes}m.mp4"
    run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(timeline), "-i", str(srt),
        "-map", "0:v:0", "-map", "0:a:0", "-map", "1:s:0", "-c:v", "copy", "-c:a", "copy",
        "-c:s", "mov_text", "-metadata:s:s:0", "language=eng", str(final),
    ])
    wall = time.monotonic() - started
    expected = minutes * 60.0
    qc = production_qc(final, expected, width=width, height=height)
    manifest = {
        "phase": 5,
        "kind": "longform_assembly_stress_proof",
        "minutes": minutes,
        "expected_duration": expected,
        "wall_seconds": wall,
        "realtime_factor": expected / wall if wall > 0 else None,
        "virtual_scene_count": minutes * 4,
        "output": str(final),
        "sha256": sha256(final),
        "qc": qc,
        "note": "Stream-copy assembly stress proof; validates long-duration container/timeline/QC reliability, not diffusion-generation throughput.",
    }
    manifest_path = output_dir / f"manifest_{minutes}m.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if not qc["ok"]:
        raise RuntimeError(f"Long-form QC failed: {qc['errors']}")
    return {**manifest, "manifest": str(manifest_path)}
