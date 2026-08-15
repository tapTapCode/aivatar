from __future__ import annotations

import asyncio
import time
from pathlib import Path

from src.providers.common import asset_id, file_sha256
from src.rendering.captions import ass_color, escape_filter_path, write_scene_srt
from src.rendering.ffmpeg import FFmpegRunner
from src.rendering.filtergraphs import build_filtergraph
from src.schemas.assets import AssetKind, GeneratedAsset, Provenance
from src.schemas.requests import SceneRenderRequest

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".ppm", ".bmp", ".tif", ".tiff"}


class FFmpegSceneRenderer:
    def __init__(self, runner: FFmpegRunner | None = None) -> None:
        self.runner = runner or FFmpegRunner()

    async def render(self, request: SceneRenderRequest) -> GeneratedAsset:
        return await asyncio.to_thread(self._render, request)

    def _render(self, request: SceneRenderRequest) -> GeneratedAsset:
        started = time.perf_counter()
        arguments: list[str] = ["-y"]
        avatar_input: int | None = None
        visual_input: int | None = None
        input_index = 0

        if request.avatar_video:
            avatar_input = input_index
            arguments.extend(["-stream_loop", "-1", "-i", request.avatar_video.uri])
            input_index += 1
        if request.visual:
            visual_input = input_index
            if Path(request.visual.uri).suffix.lower() in IMAGE_SUFFIXES:
                arguments.extend(
                    ["-loop", "1", "-framerate", str(request.output.fps), "-i", request.visual.uri]
                )
            else:
                arguments.extend(["-stream_loop", "-1", "-i", request.visual.uri])
            input_index += 1
        audio_input = input_index
        arguments.extend(["-i", request.audio.uri])

        captions_filter: str | None = None
        if request.template.captions.enabled:
            captions = write_scene_srt(
                Path(request.context.work_dir) / f"{request.scene.scene_id}.srt",
                request.scene.narration_text,
                request.duration_seconds,
                max_chars_per_line=request.template.captions.max_chars_per_line,
            )
            style = request.template.captions
            force_style = (
                f"FontName={style.font},FontSize={style.size_px},"
                f"PrimaryColour={ass_color(style.color)},"
                f"OutlineColour={ass_color(style.stroke_color)},"
                f"Outline={style.stroke_width_px},MarginV={style.bottom_margin_px},Alignment=2"
            )
            captions_filter = (
                f"subtitles=filename='{escape_filter_path(captions)}':force_style='{force_style}'"
            )

        graph = build_filtergraph(
            request,
            avatar_input=avatar_input,
            visual_input=visual_input,
            audio_input=audio_input,
            captions_filter=captions_filter,
        )
        output = Path(request.context.work_dir) / f"{request.scene.scene_id}-rendered.mp4"
        video_codec = {"h264": "libx264", "hevc": "libx265"}[request.output.video_codec]
        audio_codec = {"aac": "aac", "opus": "libopus"}[request.output.audio_codec]
        arguments.extend(
            [
                "-filter_complex",
                graph.expression,
                "-map",
                f"[{graph.video_label}]",
                "-map",
                f"[{graph.audio_label}]",
                "-t",
                f"{request.duration_seconds:.6f}",
                "-r",
                str(request.output.fps),
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
                str(request.template.audio.sample_rate),
                "-ac",
                "2",
                "-movflags",
                "+faststart",
                str(output),
            ]
        )
        self.runner.run(arguments)
        digest = file_sha256(output)
        parents = tuple(
            asset.asset_id
            for asset in (request.audio, request.avatar_video, request.visual)
            if asset is not None
        )
        return GeneratedAsset(
            asset_id=asset_id("scene", digest),
            kind=AssetKind.SCENE_VIDEO,
            uri=str(output.resolve()),
            content_hash=digest,
            project_id=request.context.project_id,
            scene_id=request.context.scene_id,
            parent_asset_ids=parents,
            duration_seconds=request.duration_seconds,
            width=request.output.width,
            height=request.output.height,
            fps=request.output.fps,
            mime_type="video/mp4",
            provenance=Provenance(
                provider="ffmpeg-scene-renderer",
                model_identifier="ffmpeg",
                checkpoint_revision="system-binary",
                model_configuration={
                    "visual_format": request.scene.visual_format.value,
                    "filtergraph": graph.expression,
                    "video_codec": request.output.video_codec,
                    "audio_codec": request.output.audio_codec,
                },
                postprocessing_latency_seconds=time.perf_counter() - started,
            ),
        )
