from __future__ import annotations

import asyncio
import time
from pathlib import Path

from src.providers.common import asset_id, file_sha256
from src.rendering.ffmpeg import FFmpegRunner
from src.schemas.assets import AssetKind, GeneratedAsset, Provenance
from src.schemas.scene import OutputSpec, Transition


class TimelineAssembler:
    def __init__(self, runner: FFmpegRunner | None = None) -> None:
        self.runner = runner or FFmpegRunner()

    async def assemble(
        self,
        scenes: tuple[GeneratedAsset, ...],
        *,
        project_id: str,
        output_spec: OutputSpec,
        output_dir: str | Path,
        transitions: tuple[Transition, ...] | None = None,
        crossfade_duration_seconds: float = 0.5,
    ) -> GeneratedAsset:
        return await asyncio.to_thread(
            self._assemble,
            scenes,
            project_id,
            output_spec,
            Path(output_dir),
            transitions,
            crossfade_duration_seconds,
        )

    def _assemble(
        self,
        scenes: tuple[GeneratedAsset, ...],
        project_id: str,
        output_spec: OutputSpec,
        output_dir: Path,
        transitions: tuple[Transition, ...] | None,
        crossfade_duration_seconds: float,
    ) -> GeneratedAsset:
        if not scenes:
            raise ValueError("at least one scene is required")
        if crossfade_duration_seconds <= 0:
            raise ValueError("crossfade duration must be positive")
        transitions = transitions or tuple(Transition.CUT for _ in scenes)
        if len(transitions) not in {len(scenes) - 1, len(scenes)}:
            raise ValueError("transitions must describe every join or every scene")
        joins = transitions[: max(0, len(scenes) - 1)]
        started = time.perf_counter()
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / f"{project_id}-final.mp4"
        video_codec = {"h264": "libx264", "hevc": "libx265"}[output_spec.video_codec]
        audio_codec = {"aac": "aac", "opus": "libopus"}[output_spec.audio_codec]
        if Transition.CROSSFADE in joins:
            total_duration = self._run_crossfade(
                scenes,
                joins,
                output,
                output_spec,
                video_codec,
                audio_codec,
                crossfade_duration_seconds,
            )
        else:
            total_duration = sum(scene.duration_seconds or 0 for scene in scenes)
            self._run_concat(scenes, output, output_spec, video_codec, audio_codec)
        digest = file_sha256(output)
        return GeneratedAsset(
            asset_id=asset_id("video", digest),
            kind=AssetKind.FINAL_VIDEO,
            uri=str(output.resolve()),
            content_hash=digest,
            project_id=project_id,
            parent_asset_ids=tuple(scene.asset_id for scene in scenes),
            duration_seconds=total_duration,
            width=output_spec.width,
            height=output_spec.height,
            fps=output_spec.fps,
            mime_type="video/mp4",
            provenance=Provenance(
                provider="ffmpeg-timeline-assembler",
                model_identifier="ffmpeg",
                checkpoint_revision="system-binary",
                model_configuration={
                    "video_codec": output_spec.video_codec,
                    "audio_codec": output_spec.audio_codec,
                    "scene_count": len(scenes),
                    "transitions": [transition.value for transition in joins],
                    "crossfade_duration_seconds": crossfade_duration_seconds,
                },
                postprocessing_latency_seconds=time.perf_counter() - started,
            ),
        )

    def _run_concat(
        self,
        scenes: tuple[GeneratedAsset, ...],
        output: Path,
        output_spec: OutputSpec,
        video_codec: str,
        audio_codec: str,
    ) -> None:
        concat_file = output.parent / "timeline.ffconcat"
        lines = ["ffconcat version 1.0"]
        for scene in scenes:
            escaped = scene.uri.replace("'", "'\\''")
            lines.append(f"file '{escaped}'")
        concat_file.write_text("\n".join(lines) + "\n")
        self.runner.run(
            [
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-vf",
                f"scale={output_spec.width}:{output_spec.height},fps={output_spec.fps},format=yuv420p,setsar=1",
                "-af",
                "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo",
                "-c:v",
                video_codec,
                "-preset",
                "medium",
                "-crf",
                "18",
                "-c:a",
                audio_codec,
                "-ar",
                "48000",
                "-ac",
                "2",
                "-movflags",
                "+faststart",
                str(output),
            ]
        )

    def _run_crossfade(
        self,
        scenes: tuple[GeneratedAsset, ...],
        joins: tuple[Transition, ...],
        output: Path,
        output_spec: OutputSpec,
        video_codec: str,
        audio_codec: str,
        crossfade_duration_seconds: float,
    ) -> float:
        durations = [scene.duration_seconds for scene in scenes]
        if any(duration is None for duration in durations):
            raise ValueError("scene durations are required for crossfades")
        numeric_durations = [float(duration) for duration in durations if duration is not None]
        arguments: list[str] = ["-y"]
        filters: list[str] = []
        for index, scene in enumerate(scenes):
            arguments.extend(["-i", scene.uri])
            filters.extend(
                (
                    f"[{index}:v]settb=AVTB,setpts=PTS-STARTPTS[v{index}]",
                    f"[{index}:a]aresample=48000,"
                    f"aformat=sample_fmts=fltp:channel_layouts=stereo,"
                    f"asetpts=PTS-STARTPTS[a{index}]",
                )
            )
        current_video = "v0"
        current_audio = "a0"
        elapsed = numeric_durations[0]
        previous_duration = numeric_durations[0]
        for index, (transition, next_duration) in enumerate(
            zip(joins, numeric_durations[1:], strict=True), start=1
        ):
            requested = (
                crossfade_duration_seconds
                if transition == Transition.CROSSFADE
                else 1 / output_spec.fps
            )
            fade = min(requested, previous_duration / 2, next_duration / 2)
            offset = max(0, elapsed - fade)
            next_video = f"vx{index}"
            next_audio = f"ax{index}"
            filters.append(
                f"[{current_video}][v{index}]xfade=transition=fade:duration={fade:.6f}:"
                f"offset={offset:.6f}[{next_video}]"
            )
            filters.append(
                f"[{current_audio}][a{index}]acrossfade=d={fade:.6f}:c1=tri:c2=tri[{next_audio}]"
            )
            current_video = next_video
            current_audio = next_audio
            elapsed += next_duration - fade
            previous_duration = next_duration
        arguments.extend(
            [
                "-filter_complex",
                ";".join(filters),
                "-map",
                f"[{current_video}]",
                "-map",
                f"[{current_audio}]",
                "-r",
                str(output_spec.fps),
                "-c:v",
                video_codec,
                "-preset",
                "medium",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                audio_codec,
                "-ar",
                "48000",
                "-ac",
                "2",
                "-movflags",
                "+faststart",
                str(output),
            ]
        )
        self.runner.run(arguments)
        return elapsed
