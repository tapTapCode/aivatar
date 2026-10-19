"""One approved job: voice -> timed scenes -> media -> composition -> QC -> export."""
import json
import shutil
from pathlib import Path
from sqlalchemy import select
from pipeline.core.config import settings
from pipeline.core.services import generate_master_voice
from pipeline.models.entities import Asset, Avatar, Channel, Scene, RenderHistory, CostEntry
from pipeline.studio.planning import ProductionOptions, build_plan
from pipeline.assets.service import generate_visual_assets
from pipeline.presenter.service import generate_presenter_for_scene
from pipeline.render.composite import compose_presenter_scene
from pipeline.render.ffmpeg import run, ffprobe
from pipeline.render.graph import project_dirs
from pipeline.queue.resources import resource_limits


def dimensions(aspect: str, resolution: str) -> tuple[int, int]:
    # Use even dimensions for H.264 yuv420p output.
    return {"1080p": {"16:9": (1920,1080), "9:16": (1080,1920), "1:1": (1080,1080), "4:5": (1080,1350)},
            "720p": {"16:9": (1280,720), "9:16": (720,1280), "1:1": (720,720), "4:5": (720,900)}}[resolution][aspect]


def latest_asset(db, project_id, kind):
    return db.scalars(select(Asset).where(Asset.project_id == project_id, Asset.kind == kind)
                      .order_by(Asset.created_at.desc())).first()


def _automatic_music(options: ProductionOptions) -> None:
    if options.music_strategy != "automatic" or options.music_path:
        return
    catalog = settings.aivatar_music_catalog_dir
    tracks = sorted(p for p in catalog.glob("*") if p.suffix.lower() in {".mp3", ".wav", ".m4a"})
    if tracks:
        options.music_path = str(tracks[abs(hash(options.music_mood)) % len(tracks)])


def _assemble_timeline(clips: list[Path], timeline: Path, style: str) -> None:
    if style == "cut" or len(clips) == 1:
        run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i",
             str(timeline.parent / "studio_concat.txt"), "-c", "copy", str(timeline)])
        return
    transition = {"crossfade": "fade", "fade": "fade", "wipeleft": "wipeleft", "slideright": "slideright"}.get(style, "fade")
    duration = 0.35
    command = ["ffmpeg", "-y", "-loglevel", "error"]
    for clip in clips:
        command += ["-i", str(clip)]
    filters = []
    current = "[0:v]"
    elapsed = 0.0
    # Scene durations are read from the normalized clips so transition timing stays deterministic.
    for i in range(1, len(clips)):
        info = ffprobe(clips[i - 1])
        previous = float(info["format"]["duration"])
        elapsed += previous - duration
        output = f"[v{i}]"
        filters.append(f"{current}[{i}:v]xfade=transition={transition}:duration={duration}:offset={max(0, elapsed):.3f}{output}")
        current = output
    # xfade overlaps clips; clone the final frame for the overlap budget so narration and
    # video retain the same total duration.
    filters.append(f"{current}tpad=stop_mode=clone:stop_duration={duration * (len(clips) - 1):.3f}[vfinal]")
    command += ["-filter_complex", ";".join(filters), "-map", "[vfinal]", "-an", "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", str(timeline)]
    run(command)


def _finish_video(timeline: Path, audio: Path, output: Path, duration: float, options: ProductionOptions, captions: Path):
    command = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(timeline), "-i", str(audio)]
    if options.music_path:
        command += ["-stream_loop", "-1", "-i", options.music_path]
        graph = (f"[1:a]asplit=2[narration][trigger];[2:a]volume={options.music_volume}[music];"
                 "[music][trigger]sidechaincompress=threshold=0.025:ratio=8:attack=20:release=350[ducked];"
                 "[narration][ducked]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11[audio]")
        command += ["-filter_complex", graph, "-map", "0:v:0", "-map", "[audio]"]
    else:
        command += ["-map", "0:v:0", "-map", "1:a:0", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11"]
    filters = []
    if options.captions and captions.exists():
        # A controlled, local path is escaped for FFmpeg's filter grammar, not a shell.
        escaped = str(captions.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "'\\''")
        filters.append(f"subtitles=filename='{escaped}':force_style='FontName=DejaVu Sans,FontSize={options.caption_size},Outline=2,Shadow=0,MarginV=32,MarginL=32,MarginR=32,Alignment=2'")
    if filters:
        command += ["-vf", ",".join(filters), "-c:v", "libx264", "-preset", "fast", "-crf", "20"]
    else:
        command += ["-c:v", "copy"]
    command += ["-c:a", "aac", "-b:a", "192k", "-t", str(duration), "-movflags", "+faststart", str(output)]
    run(command)


def run_production(db, project, progress=lambda stage, fraction: None):
    options = ProductionOptions(**project.production_json)
    _automatic_music(options)
    demo = options.mode == "demo"
    dirs = project_dirs(settings.aivatar_workspace, project.id)
    avatar = db.get(Avatar, project.avatar_id) if project.avatar_id else None
    channel = db.get(Channel, project.channel_id)
    progress("Preparing narration", .06)
    master = latest_asset(db, project.id, "master_audio")
    if not master or not Path(master.path).is_file():
        project.state = "CREATED"
        db.commit()
        provider = "mock_voice" if demo else ("imported_audio" if options.narration_path else
                    avatar.voice_provider if avatar else (channel.settings_json or {}).get("voice_provider", "ai33"))
        generate_master_voice(db, project, provider, voice_id=avatar.voice_id if avatar else None,
                              source_path=options.narration_path if not demo else None)
        master = latest_asset(db, project.id, "master_audio")
    duration = master.duration
    progress("Planning scenes", .16)
    plan = build_plan(options, duration)
    if not project.scenes:
        for beat in plan["scenes"]:
            db.add(Scene(project_id=project.id, ordinal=beat["ordinal"], start=beat["start"], end=beat["end"],
                         type=beat["type"], visual_prompt=beat["visual_prompt"], motion=beat["motion"],
                         asset_strategy="presenter_only" if beat["type"] == "PRESENTER" else "flux_motion",
                         layout_json={"narration": beat["narration"]}))
        project.presenter_actual = plan["presenter_seconds"] / duration
        project.state = "PLANNING"
        db.commit(); db.refresh(project)
    # The exported plan is the actual persisted scene plan, including manual corrections.
    (dirs["base"] / "production-plan.json").write_text(json.dumps({"name": project.name, "duration": duration,
        "mode": options.mode, "script": project.script,
        "scenes": [{"ordinal": s.ordinal, "start": s.start, "end": s.end, "type": s.type,
                    "visual_prompt": s.visual_prompt, "narration": (s.layout_json or {}).get("narration", "")}
                   for s in project.scenes]}, indent=2), encoding="utf-8")
    progress("Generating supporting visuals", .22)
    # Reuses provider-source cache after an interruption. Demo cache is isolated from paid media.
    generate_visual_assets(db, project, mock=demo)
    visuals = {}
    for asset in db.scalars(select(Asset).where(Asset.project_id == project.id, Asset.kind == "visual")
                            .order_by(Asset.created_at.desc())).all():
        if asset.scene_id and asset.scene_id not in visuals and Path(asset.path).is_file():
            visuals[asset.scene_id] = Path(asset.path)
    width, height = dimensions(options.aspect_ratio, options.resolution)
    clips = []
    for index, scene in enumerate(project.scenes):
        progress(f"Producing scene {index + 1}/{len(project.scenes)}", .45 + .38 * index / len(project.scenes))
        presenter = None
        if scene.type in {"PRESENTER", "SPLIT", "PIP"}:
            with resource_limits.reserve("presenter"):
                result = generate_presenter_for_scene(db, project, scene,
                    provider_name="mock_presenter" if demo else avatar.presenter_provider, allow_fallback=False)
                presenter = Path(result["path"])
        output = dirs["render"] / f"studio_scene_{scene.ordinal:04}.mp4"
        seconds = scene.end - scene.start
        with resource_limits.reserve("ffmpeg"):
            if presenter:
                compose_presenter_scene(scene.type, presenter, visuals.get(scene.id), output, seconds,
                    layout={**(scene.layout_json or {}), "preset": "fast", "background_color": options.background_color},
                    width=width, height=height)
            else:
                source = visuals.get(scene.id)
                if not source: raise ValueError(f"Missing visual for scene {scene.ordinal}")
                run(["ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1", "-i", str(source),
                     "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps=30,setsar=1",
                     "-t", f"{seconds:.3f}", "-an", "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", str(output)])
            # Normalize timebase and SAR for reliable concatenation across providers/layouts.
            normalized = output.with_name(output.stem + "_normalized.mp4")
            run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(output), "-vf", "setsar=1,fps=30,tpad=stop_mode=clone:stop_duration=1",
                 "-t", f"{seconds:.3f}", "-an", "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", "-video_track_timescale", "15360", str(normalized)])
        scene.render_path = str(normalized)
        db.commit()
        clips.append(normalized)
    progress("Mixing music and assembling video", .85)
    concat = dirs["render"] / "studio_concat.txt"
    concat.write_text("\n".join("file '" + str(p.resolve()).replace("'", "'\\''") + "'" for p in clips))
    timeline = dirs["render"] / "studio_timeline.mp4"
    final = dirs["base"] / "final.mp4"
    pending = dirs["base"] / "pending_final.mp4"
    project.state = "RENDERING"; db.commit()
    with resource_limits.reserve("ffmpeg"):
        _assemble_timeline(clips, timeline, options.transition_style)
        _finish_video(timeline, Path(master.path), pending, duration, options, dirs["captions"] / "captions.srt")
    progress("Checking exported video", .96)
    info = ffprobe(pending)
    video = next((s for s in info["streams"] if s["codec_type"] == "video"), {})
    audio = next((s for s in info["streams"] if s["codec_type"] == "audio"), {})
    actual_duration = float(info["format"]["duration"])
    if (video.get("width"), video.get("height")) != (width, height) or not audio:
        raise ValueError("Export failed video dimensions or audio checks")
    if abs(actual_duration - duration) > max(.5, len(clips) / 30):
        raise ValueError("Export duration differs from narration; retained media can be retried")
    pending.replace(final)
    project.state = "COMPLETED"; project.final_duration = actual_duration; project.error = None
    project.actual_cost_usd = sum(c.actual_cost_usd for c in db.scalars(select(CostEntry).where(CostEntry.project_id == project.id)).all())
    db.add(RenderHistory(project_id=project.id, output_path=str(final.resolve()), duration=actual_duration,
        width=width, height=height, fps=30, qc_json={"mode": options.mode, "audio": True, "captions": options.captions,
        "music": bool(options.music_path), "timestamp_source": "provider timestamps when available, otherwise heuristic"}))
    db.commit()
    return {"final": str(final), "duration": actual_duration, "mode": options.mode}

