from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.alignment.timestamps import align_script_heuristic, caption_segments, save_timestamps
from pipeline.audio.master import cut_audio_segment
from pipeline.director.timeline import PlannedScene, presenter_percentage, validate_timeline
from pipeline.providers.mock import MockPresenterProvider, MockVoiceProvider
from pipeline.render.composite import compose_presenter_scene
from pipeline.render.ffmpeg import run, sha256, write_caption_segments
from pipeline.render.graph import project_dirs, qc_final, render_scene


def proof_scenes(duration: float) -> list[tuple[PlannedScene, dict]]:
    # 30% presenter visibility: 8s presenter + 6s split + 4s PIP = 18s of a 60s proof.
    scale = duration / 60.0
    raw = [
        (0, 8, "PRESENTER", "Opening hook with presenter", "static", {"presenter_side": "left", "preset": "ultrafast"}),
        (8, 20, "FULL_VISUAL", "Documentary establishing B-roll", "slow_push_in", {}),
        (20, 26, "SPLIT", "Supporting visual beside the presenter", "pan_right", {"presenter_side": "left", "presenter_ratio": 0.40, "corner_radius": 26, "preset": "ultrafast"}),
        (26, 38, "FULL_VISUAL", "Evidence and explanatory visuals", "subtle_zoom", {}),
        (38, 42, "PIP", "Visual-first section with presenter PIP", "pan_left", {"position": "bottom_right", "size": 0.28, "corner_radius": 34, "preset": "ultrafast"}),
        (42, 60, "FULL_VISUAL", "Closing documentary montage and CTA graphic", "slow_pull_out", {}),
    ]
    result = []
    for i, (start, end, kind, prompt, motion, layout) in enumerate(raw, 1):
        result.append((PlannedScene(i, round(start * scale, 3), round(end * scale, 3), kind, prompt, motion), layout))
    validate_timeline([x[0] for x in result], duration)
    return result


def render(workspace: Path, duration: float = 60.0, project_id: str | None = None) -> dict:
    project_id = project_id or f"phase3-proof-{uuid4().hex[:8]}"
    dirs = project_dirs(workspace, project_id)
    script = (
        "Aivatar starts with a presenter-led hook, then moves into visual storytelling. "
        "The master narration remains authoritative while presenter clips are generated only for selected intervals. "
        "Split-screen composition keeps the presenter beside documentary visuals. "
        "Full visual scenes reduce presenter cost and create pacing variety. "
        "Picture in picture keeps the speaker visible without hiding important B-roll. "
        "Every scene is rendered independently so one failed segment can be regenerated without rebuilding the entire video."
    )
    scene_layouts = proof_scenes(duration)
    scenes = [item[0] for item in scene_layouts]
    (dirs["base"] / "script.txt").write_text(script, encoding="utf-8")
    (dirs["base"] / "timeline.json").write_text(
        json.dumps(
            {
                "duration": duration,
                "presenter_percentage": presenter_percentage(scenes),
                "scenes": [{**asdict(scene), "layout": layout} for scene, layout in scene_layouts],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    voice = MockVoiceProvider().generate(script, duration, dirs["audio"])
    words = align_script_heuristic(script, voice.duration)
    timestamps = dirs["audio"] / "timestamps.json"
    save_timestamps(timestamps, words, "heuristic_mock_phase3", voice.duration)
    segments = caption_segments(words)
    srt = dirs["captions"] / "captions.srt"
    vtt = dirs["captions"] / "captions.vtt"
    write_caption_segments(segments, srt, vtt)

    presenter_provider = MockPresenterProvider()
    rendered: list[Path] = []
    presenter_manifest: list[dict] = []
    for scene, layout in scene_layouts:
        out = dirs["render"] / f"scene_{scene.ordinal:03}.mp4"
        if scene.type in {"PRESENTER", "SPLIT", "PIP"}:
            segment_audio = dirs["audio"] / "presenter_segments" / f"scene_{scene.ordinal:03}.wav"
            cut_audio_segment(voice.path, scene.start, scene.end, segment_audio)
            presenter = presenter_provider.generate(
                segment_audio,
                scene.duration,
                dirs["presenter"] / f"scene_{scene.ordinal:03}",
                scene_id=f"scene_{scene.ordinal:03}",
            )
            visual = None
            if scene.type in {"SPLIT", "PIP"}:
                visual = dirs["cache"] / f"visual_scene_{scene.ordinal:03}.mp4"
                visual_scene = PlannedScene(scene.ordinal, 0, scene.duration, "FULL_VISUAL", scene.visual_prompt, scene.motion)
                render_scene(visual_scene, visual)
            compose_presenter_scene(scene.type, presenter.path, visual, out, scene.duration, layout)
            presenter_manifest.append(
                {
                    "scene": scene.ordinal,
                    "type": scene.type,
                    "start": scene.start,
                    "end": scene.end,
                    "audio_segment": str(segment_audio),
                    "presenter": str(presenter.path),
                    "layout": layout,
                }
            )
        else:
            render_scene(scene, out)
        rendered.append(out)

    concat = dirs["render"] / "concat.txt"
    concat.write_text("\n".join(f"file '{path.resolve()}'" for path in rendered), encoding="utf-8")
    visual_timeline = dirs["render"] / "timeline_video.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(visual_timeline)])
    final = dirs["base"] / "final.mp4"
    run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(visual_timeline), "-i", str(voice.path), "-i", str(srt),
        "-map", "0:v:0", "-map", "1:a:0", "-map", "2:s:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
        "-c:s", "mov_text", "-metadata:s:s:0", "language=eng", "-shortest", str(final),
    ])
    qc = qc_final(final, duration)
    manifest = {
        "project_id": project_id,
        "phase": 3,
        "mode": "mock",
        "duration": duration,
        "presenter_percentage": presenter_percentage(scenes),
        "presenter_seconds": sum(s.duration for s in scenes if s.type in {"PRESENTER", "SPLIT", "PIP"}),
        "presenter_scenes": presenter_manifest,
        "scene_hashes": [{"scene": scene.ordinal, "type": scene.type, "sha256": sha256(path)} for scene, path in zip(scenes, rendered, strict=True)],
        "master_audio": str(voice.path),
        "timestamps": str(timestamps),
        "captions_srt": str(srt),
        "captions_vtt": str(vtt),
        "final": str(final),
        "final_sha256": sha256(final),
        "qc": qc,
    }
    manifest_path = dirs["render"] / "phase3_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if not qc["ok"]:
        raise RuntimeError(f"QC failed: {qc['errors']}")
    return {**manifest, "manifest": str(manifest_path)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--workspace", type=Path, default=ROOT / "workspace")
    parser.add_argument("--project-id", default=None)
    args = parser.parse_args()
    print(json.dumps(render(args.workspace, args.duration, args.project_id), indent=2))
