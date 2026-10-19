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
from pipeline.cache.assets import AssetCache, cache_key
from pipeline.core.config import settings
from pipeline.director.timeline import PlannedScene, presenter_percentage, validate_timeline
from pipeline.director.visual_strategy import choose_visual_strategies, strategy_summary
from pipeline.motion_graphics.templates import MotionGraphicSpec, apply_motion_graphic
from pipeline.providers.mock import MockImageProvider, MockPresenterProvider, MockVideoProvider, MockVoiceProvider
from pipeline.render.composite import compose_presenter_scene
from pipeline.render.ffmpeg import run, sha256, write_caption_segments
from pipeline.render.graph import project_dirs, qc_final, render_still_with_motion


def proof_scenes(duration: float) -> list[tuple[PlannedScene, dict]]:
    scale = duration / 60.0
    raw = [
        (0, 8, "PRESENTER", "Opening hook: Aivatar decides which visuals are worth generating", "static", {"preset": "ultrafast"}),
        (8, 16, "FULL_VISUAL", "Section title: Build the story before spending GPU time", "slow_push_in", {}),
        (16, 22, "SPLIT", "Ocean waves crash while traffic moves and the camera tracks rapidly through the city", "pan_right", {"presenter_side": "left", "presenter_ratio": 0.40, "preset": "ultrafast"}),
        (22, 34, "FULL_VISUAL", "Archival portrait of a historic building beside a document and map", "slow_push_in", {}),
        (34, 38, "PIP", "A crowd runs through rain while the camera orbits and follows the moving action", "pan_left", {"position": "bottom_right", "size": 0.28, "preset": "ultrafast"}),
        (38, 60, "FULL_VISUAL", "Key point statistic: selective generation protects the five dollar project budget", "slow_pull_out", {}),
    ]
    result: list[tuple[PlannedScene, dict]] = []
    for i, (start, end, kind, prompt, motion, layout) in enumerate(raw, 1):
        result.append((PlannedScene(i, round(start * scale, 3), round(end * scale, 3), kind, prompt, motion), layout))
    validate_timeline([item[0] for item in result], duration)
    return result


def render(workspace: Path, duration: float = 60.0, project_id: str | None = None) -> dict:
    project_id = project_id or f"phase4-proof-{uuid4().hex[:8]}"
    dirs = project_dirs(workspace, project_id)
    script = (
        "Aivatar now plans visual spending before generation begins. "
        "Template graphics handle titles and callouts without expensive video diffusion. "
        "Fast moving scenes can earn a selective LTX generation when the motion value justifies the cost. "
        "Static documentary material defaults to a FLUX still with local FFmpeg movement. "
        "Reusable assets are content addressed and shared across projects instead of generated twice. "
        "The master narration remains authoritative while every scene stays independently resumable."
    )
    scene_layouts = proof_scenes(duration)
    scenes = [item[0] for item in scene_layouts]

    # Seed one reusable source asset so the proof demonstrates cache-first planning.
    shared_cache = AssetCache(workspace / "cache" / "assets")
    cache_scene = scenes[3]
    flux_params = {"width": 1280, "height": 720, "steps": 4, "guidance_scale": 1.0}
    seeded_key = cache_key(
        kind="image", provider="flux_klein", model=settings.aivatar_flux_model,
        prompt=cache_scene.visual_prompt, parameters=flux_params,
    )
    if shared_cache.peek(seeded_key) is None:
        seed_image = MockImageProvider().generate(cache_scene.visual_prompt, dirs["cache"] / "seed").path
        shared_cache.put(seeded_key, seed_image, {"provider": "mock_image", "model": settings.aivatar_flux_model})

    decisions = choose_visual_strategies(
        scenes,
        total_budget_usd=5.0,
        visual_budget_fraction=0.60,
        max_ltx_scenes=2,
        cached_scene_ordinals={cache_scene.ordinal},
    )
    decision_by_scene = {d.scene_ordinal: d for d in decisions}
    decision_by_scene[cache_scene.ordinal].cache_key = seeded_key

    (dirs["base"] / "script.txt").write_text(script, encoding="utf-8")
    (dirs["base"] / "timeline.json").write_text(json.dumps({
        "duration": duration,
        "presenter_percentage": presenter_percentage(scenes),
        "visual_strategy": strategy_summary(decisions),
        "scenes": [
            {**asdict(scene), "layout": layout, "visual_decision": decision_by_scene[scene.ordinal].as_dict()}
            for scene, layout in scene_layouts
        ],
    }, indent=2), encoding="utf-8")

    voice = MockVoiceProvider().generate(script, duration, dirs["audio"])
    words = align_script_heuristic(script, voice.duration)
    timestamps = dirs["audio"] / "timestamps.json"
    save_timestamps(timestamps, words, "heuristic_mock_phase4", voice.duration)
    segments = caption_segments(words)
    srt = dirs["captions"] / "captions.srt"
    vtt = dirs["captions"] / "captions.vtt"
    write_caption_segments(segments, srt, vtt)

    presenter_provider = MockPresenterProvider()
    rendered: list[Path] = []
    asset_manifest: list[dict] = []
    for scene, layout in scene_layouts:
        decision = decision_by_scene[scene.ordinal]
        out = dirs["render"] / f"scene_{scene.ordinal:03}.mp4"
        # Scene renders are immutable intermediates. A resumed proof skips completed scenes
        # instead of paying the FFmpeg/presenter cost again.
        if out.exists() and out.stat().st_size > 0:
            if scene.type != "PRESENTER":
                visual_base = dirs["cache"] / f"phase4_visual_{scene.ordinal:03}.mp4"
                graphic = dirs["cache"] / f"phase4_graphic_{scene.ordinal:03}.mp4"
                visual = graphic if decision.template and graphic.exists() else visual_base if visual_base.exists() else None
                asset_manifest.append({
                    "scene": scene.ordinal,
                    "strategy": decision.strategy,
                    "estimated_cost_usd": decision.estimated_cost_usd,
                    "motion_score": decision.motion_score,
                    "template": decision.template,
                    "cache_hit": decision.strategy == "cache",
                    "source_kind": "resumed_existing_intermediate",
                    "visual": str(visual) if visual else None,
                    "resumed": True,
                })
            rendered.append(out)
            continue

        visual: Path | None = None
        if scene.type != "PRESENTER":
            visual_base = dirs["cache"] / f"phase4_visual_{scene.ordinal:03}.mp4"
            if decision.strategy == "ltx_video":
                source = MockVideoProvider().generate(scene.visual_prompt, scene.duration, dirs["cache"] / f"ltx_{scene.ordinal:03}").path
                run([
                    "ffmpeg", "-y", "-loglevel", "error", "-i", str(source), "-t", f"{scene.duration:.3f}",
                    "-an", "-c:v", "copy", str(visual_base),
                ])
                source_kind = "mock_ltx_video"
                cache_hit = False
            else:
                if decision.strategy == "cache":
                    hit = shared_cache.get(seeded_key)
                    assert hit is not None
                    image = hit.path
                    cache_hit = True
                else:
                    image = MockImageProvider().generate(scene.visual_prompt, dirs["cache"] / f"flux_{scene.ordinal:03}").path
                    cache_hit = False
                render_still_with_motion(image, visual_base, scene.duration, scene.motion, preset="ultrafast")
                source_kind = "cached_flux_image" if cache_hit else "mock_flux_image"
            visual = visual_base
            if decision.template:
                graphic = dirs["cache"] / f"phase4_graphic_{scene.ordinal:03}.mp4"
                apply_motion_graphic(
                    visual,
                    graphic,
                    scene.duration,
                    MotionGraphicSpec(decision.template, scene.visual_prompt[:72], "Budget-aware visual treatment", start=0.25, hold=min(4.5, max(1.0, scene.duration - 0.5))),
                    preset="ultrafast",
                )
                visual = graphic
            asset_manifest.append({
                "scene": scene.ordinal,
                "strategy": decision.strategy,
                "estimated_cost_usd": decision.estimated_cost_usd,
                "motion_score": decision.motion_score,
                "template": decision.template,
                "cache_hit": cache_hit,
                "source_kind": source_kind,
                "visual": str(visual),
            })

        if scene.type in {"PRESENTER", "SPLIT", "PIP"}:
            segment_audio = dirs["audio"] / "presenter_segments" / f"scene_{scene.ordinal:03}.wav"
            cut_audio_segment(voice.path, scene.start, scene.end, segment_audio)
            presenter = presenter_provider.generate(segment_audio, scene.duration, dirs["presenter"] / f"scene_{scene.ordinal:03}")
            compose_presenter_scene(scene.type, presenter.path, visual, out, scene.duration, layout)
        else:
            assert visual is not None
            run([
                "ffmpeg", "-y", "-loglevel", "error", "-i", str(visual), "-t", f"{scene.duration:.3f}",
                "-an", "-c:v", "copy", str(out),
            ])
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
    summary = strategy_summary(decisions)
    manifest = {
        "project_id": project_id,
        "phase": 4,
        "mode": "mock-with-real-optimization",
        "duration": duration,
        "presenter_percentage": presenter_percentage(scenes),
        "presenter_seconds": sum(s.duration for s in scenes if s.type in {"PRESENTER", "SPLIT", "PIP"}),
        "budget_usd": 5.0,
        "visual_budget_usd": 3.0,
        "visual_strategy": summary,
        "actual_external_cost_usd": 0.0,
        "assets": asset_manifest,
        "scene_hashes": [{"scene": scene.ordinal, "type": scene.type, "sha256": sha256(path)} for scene, path in zip(scenes, rendered, strict=True)],
        "master_audio": str(voice.path),
        "timestamps": str(timestamps),
        "captions_srt": str(srt),
        "captions_vtt": str(vtt),
        "final": str(final),
        "final_sha256": sha256(final),
        "qc": qc,
    }
    manifest_path = dirs["render"] / "phase4_manifest.json"
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
