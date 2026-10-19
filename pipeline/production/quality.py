from __future__ import annotations

import re
import subprocess
from pathlib import Path

from pipeline.render.graph import qc_final


def _run_probe(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if proc.returncode:
        raise RuntimeError(proc.stdout[-4000:])
    return proc.stdout


def production_qc(path: Path, expected_duration: float, width: int = 1920, height: int = 1080) -> dict:
    """Container/stream QC plus sampled audio and black-frame checks.

    Expensive content checks are intentionally sampled so 30–40 minute projects do not require
    decoding the entire final twice merely to validate obvious failures.
    """
    base = qc_final(path, expected_duration, width=width, height=height, tolerance=0.50)
    errors = list(base["errors"])
    sample_seconds = min(expected_duration, 30.0)

    audio_log = _run_probe([
        "ffmpeg", "-hide_banner", "-nostats", "-t", f"{sample_seconds:.3f}", "-i", str(path),
        "-map", "0:a:0", "-af", "volumedetect", "-f", "null", "-",
    ])
    mean_match = re.search(r"mean_volume:\s*(-?[0-9.]+) dB", audio_log)
    max_match = re.search(r"max_volume:\s*(-?[0-9.]+) dB", audio_log)
    mean_db = float(mean_match.group(1)) if mean_match else None
    max_db = float(max_match.group(1)) if max_match else None
    if max_db is None or max_db < -55.0:
        errors.append("sampled narration is effectively silent")

    black_log = _run_probe([
        "ffmpeg", "-hide_banner", "-nostats", "-t", f"{sample_seconds:.3f}", "-i", str(path),
        "-map", "0:v:0", "-vf", "blackdetect=d=2:pix_th=0.02", "-an", "-f", "null", "-",
    ])
    black_segments = len(re.findall(r"black_start:", black_log))
    if black_segments:
        errors.append(f"detected {black_segments} obvious black segment(s) in QC sample")

    return {
        **base,
        "ok": not errors,
        "errors": errors,
        "audio_sample_seconds": sample_seconds,
        "mean_volume_db": mean_db,
        "max_volume_db": max_db,
        "black_segments_sampled": black_segments,
    }
