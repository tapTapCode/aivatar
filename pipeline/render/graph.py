from __future__ import annotations

import json
import textwrap
from pathlib import Path

from pipeline.alignment.timestamps import align_script_heuristic, caption_segments, save_timestamps
from pipeline.director.timeline import PlannedScene, serialize_timeline
from pipeline.providers.mock import MockVoiceProvider
from pipeline.render.ffmpeg import ffprobe, run, sha256, write_caption_segments

PALETTE = ["0x0b1220", "0x16213e", "0x243b55", "0x1f2937", "0x334155", "0x111827"]


def project_dirs(workspace: Path, project_id: str) -> dict[str, Path]:
    base = workspace / "projects" / project_id
    dirs = {name: base / name for name in ["audio", "images", "videos", "presenter", "captions", "cache", "render", "logs"]}
    base.mkdir(parents=True, exist_ok=True)
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    dirs["base"] = base
    return dirs


def render_scene(scene: PlannedScene, output: Path, width: int = 1920, height: int = 1080, fps: int = 30) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    duration = scene.duration
    prompt_path = output.with_suffix(".txt")
    prompt_path.write_text("\n".join(textwrap.wrap(scene.visual_prompt, width=38)), encoding="utf-8")
    prompt_arg = str(prompt_path).replace("\\", "/").replace(":", "\\:")
    text_overlay = f"drawtext=textfile='{prompt_arg}':fontcolor=white:fontsize=42:line_spacing=12:x=90:y=(h-text_h)/2:box=1:boxcolor=black@0.38:boxborderw=28"
    if scene.type == "SPLIT":
        filter_complex = (
            f"color=c={PALETTE[scene.ordinal % len(PALETTE)]}:s={width}x{height}:r={fps}:d={duration}[bg];"
            f"color=c=0x1e293b:s={width//2}x{height}:r={fps}:d={duration}[p];"
            f"[bg][p]overlay=0:0,drawbox=x={width//2}:y=0:w={width//2}:h={height}:color=0x1e40af@0.35:t=fill,{text_overlay}"
        )
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:r={fps}:d={duration}", "-filter_complex", filter_complex, "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-pix_fmt", "yuv420p", str(output)]
    elif scene.type == "PRESENTER":
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc2=size={width}x{height}:rate={fps}:duration={duration}", "-vf", "drawbox=x=0:y=0:w=iw:h=90:color=0x0b1220@0.85:t=fill", "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-pix_fmt", "yuv420p", str(output)]
    else:
        color = PALETTE[(scene.ordinal - 1) % len(PALETTE)]
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={color}:s={width}x{height}:r={fps}:d={duration}", "-vf", f"drawgrid=width=120:height=120:thickness=1:color=white@0.08,{text_overlay}", "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-pix_fmt", "yuv420p", str(output)]
    run(cmd)
    return output


def render_still_with_motion(image: Path, output: Path, duration: float, motion: str, width: int = 1920, height: int = 1080, fps: int = 30, preset: str = "medium") -> Path:
    from pipeline.render.motion import image_motion_filter

    output.parent.mkdir(parents=True, exist_ok=True)
    filter_chain = image_motion_filter(motion, width, height, fps, duration)
    run([
        "ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(image),
        "-vf", filter_chain, "-t", f"{duration:.3f}", "-an", "-c:v", "libx264",
        "-preset", preset, "-crf", "20", "-pix_fmt", "yuv420p", str(output),
    ])
    return output


def qc_final(path: Path, expected_duration: float, width: int = 1920, height: int = 1080, tolerance: float = 0.30) -> dict:
    data = ffprobe(path)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    subtitle = next((s for s in streams if s.get("codec_type") == "subtitle"), None)
    duration = float(data["format"]["duration"])
    errors: list[str] = []
    if not video:
        errors.append("missing video stream")
    if not audio:
        errors.append("missing audio stream")
    if video and (int(video.get("width", 0)) != width or int(video.get("height", 0)) != height):
        errors.append("wrong resolution")
    if abs(duration - expected_duration) > tolerance:
        errors.append(f"duration mismatch: {duration:.3f}s")
    if path.stat().st_size < 100_000:
        errors.append("output suspiciously small")
    return {
        "ok": not errors,
        "errors": errors,
        "duration": duration,
        "width": video.get("width") if video else None,
        "height": video.get("height") if video else None,
        "video_codec": video.get("codec_name") if video else None,
        "audio_codec": audio.get("codec_name") if audio else None,
        "subtitle_codec": subtitle.get("codec_name") if subtitle else None,
        "size_bytes": path.stat().st_size,
    }


def render_mock_project(workspace: Path, project_id: str, script: str, scenes: list[PlannedScene], duration: float, force: bool = False) -> dict:
    dirs = project_dirs(workspace, project_id)
    (dirs["base"] / "script.txt").write_text(script, encoding="utf-8")
    timeline = serialize_timeline(scenes, duration)
    (dirs["base"] / "timeline.json").write_text(json.dumps(timeline, indent=2), encoding="utf-8")
    (dirs["base"] / "project.json").write_text(json.dumps({"id": project_id, "duration": duration, "mode": "mock"}, indent=2), encoding="utf-8")

    voice = MockVoiceProvider().generate(script, duration, dirs["audio"])
    words = align_script_heuristic(script, voice.duration)
    timestamps = dirs["audio"] / "timestamps.json"
    save_timestamps(timestamps, words, "heuristic_mock", voice.duration)
    captions = caption_segments(words)
    srt = dirs["captions"] / "captions.srt"
    vtt = dirs["captions"] / "captions.vtt"
    write_caption_segments(captions, srt, vtt)

    rendered: list[Path] = []
    for scene in scenes:
        out = dirs["render"] / f"scene_{scene.ordinal:03}.mp4"
        if force or not out.exists():
            render_scene(scene, out)
        rendered.append(out)

    concat_file = dirs["render"] / "concat.txt"
    concat_file.write_text("\n".join(f"file '{path.resolve()}'" for path in rendered), encoding="utf-8")
    visual = dirs["render"] / "timeline_video.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(visual)])
    final = dirs["base"] / "final.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(visual), "-i", str(voice.path), "-i", str(srt), "-map", "0:v:0", "-map", "1:a:0", "-map", "2:s:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-c:s", "mov_text", "-metadata:s:s:0", "language=eng", "-shortest", str(final)])
    qc = qc_final(final, duration)
    manifest = {
        "project_id": project_id,
        "mode": "mock",
        "scenes": [{"ordinal": scene.ordinal, "path": str(path), "sha256": sha256(path)} for scene, path in zip(scenes, rendered, strict=True)],
        "master_audio": str(voice.path),
        "timestamps": str(timestamps),
        "captions_srt": str(srt),
        "captions_vtt": str(vtt),
        "final": str(final),
        "final_sha256": sha256(final),
        "qc": qc,
    }
    (dirs["render"] / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if not qc["ok"]:
        raise RuntimeError(f"QC failed: {qc['errors']}")
    return manifest
