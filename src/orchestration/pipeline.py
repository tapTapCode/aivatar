from __future__ import annotations

import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

from src.orchestration.routing import plan_scene
from src.providers.base import (
    AvatarSourceProvider,
    ImageGenerator,
    LipSyncGenerator,
    SceneRenderer,
    SpeechGenerator,
    VideoGenerator,
)
from src.providers.common import asset_id, file_sha256
from src.rendering import probe_media
from src.schemas.assets import AssetKind, GeneratedAsset, Provenance
from src.schemas.requests import (
    AvatarSourceRequest,
    GenerationContext,
    LipSyncRequest,
    SceneRenderRequest,
    SpeechGenerationRequest,
    VisualGenerationRequest,
)
from src.schemas.scene import ProjectScript
from src.schemas.templates import ChannelTemplate


@dataclass(frozen=True)
class ProviderSet:
    speech: SpeechGenerator
    avatar_source: AvatarSourceProvider
    lipsync: LipSyncGenerator
    image: ImageGenerator
    video: VideoGenerator
    renderer: SceneRenderer
    native_presenter_voice: bool = False


class PipelineOrchestrator:
    def __init__(self, providers: ProviderSet, *, work_root: str | Path) -> None:
        self.providers = providers
        self.work_root = Path(work_root)

    async def render_project(
        self,
        project: ProjectScript,
        template: ChannelTemplate,
        *,
        job_id: str | None = None,
        request_id: str | None = None,
    ) -> tuple[GeneratedAsset, ...]:
        job_id = job_id or f"job_{uuid.uuid4().hex}"
        request_id = request_id or f"req_{uuid.uuid4().hex}"
        rendered: list[GeneratedAsset] = []
        for scene in project.scenes:
            rendered.append(
                await self.render_scene(
                    project,
                    scene_index=project.scenes.index(scene),
                    template=template,
                    job_id=job_id,
                    request_id=request_id,
                )
            )
        return tuple(rendered)

    async def render_scene(
        self,
        project: ProjectScript,
        *,
        scene_index: int,
        template: ChannelTemplate,
        job_id: str,
        request_id: str,
    ) -> GeneratedAsset:
        scene = project.scenes[scene_index]
        plan = plan_scene(scene)
        scene_dir = self.work_root / project.project_id / job_id / scene.scene_id
        scene_dir.mkdir(parents=True, exist_ok=True)
        context = GenerationContext(
            project_id=project.project_id,
            scene_id=scene.scene_id,
            request_id=request_id,
            job_id=job_id,
            work_dir=str(scene_dir),
        )

        native_presenter_voice = self.providers.native_presenter_voice and plan.lipsync
        audio: GeneratedAsset | None = None
        if not native_presenter_voice:
            audio = await self.providers.speech.generate(
                SpeechGenerationRequest(
                    context=context,
                    text=scene.narration_text,
                    voice_id=scene.voice_id,
                    requested_duration_seconds=scene.duration_seconds,
                    sample_rate=template.audio.sample_rate,
                )
            )
            self._assert_lineage(audio, context)
        duration = scene.duration_seconds or (
            audio.duration_seconds
            if audio is not None
            else self._estimate_duration(scene.narration_text)
        )
        if duration is None:
            raise ValueError("speech provider did not return a duration")

        avatar_video: GeneratedAsset | None = None
        visual: GeneratedAsset | None = None

        if plan.avatar_source:
            avatar = await self.providers.avatar_source.resolve(
                AvatarSourceRequest(
                    context=context,
                    avatar_id=scene.avatar_id or "",
                    duration_seconds=duration,
                    width=project.output.width,
                    height=project.output.height,
                    fps=project.output.fps,
                )
            )
            self._assert_lineage(avatar, context)
            if plan.lipsync:
                avatar_video = await self.providers.lipsync.generate(
                    LipSyncRequest(
                        context=context,
                        avatar=avatar,
                        audio=audio,
                        narration_text=scene.narration_text,
                        voice_id=scene.voice_id,
                        duration_seconds=duration,
                        fps=project.output.fps,
                    )
                )
                self._assert_lineage(avatar_video, context)
                if native_presenter_voice or self._video_has_audio(avatar_video.uri):
                    duration = avatar_video.duration_seconds or duration
                    audio = self._extract_audio(
                        avatar_video,
                        context=context,
                        sample_rate=template.audio.sample_rate,
                    )

        if plan.visual:
            visual_request = VisualGenerationRequest(
                context=context,
                prompt=scene.visual_description or "",
                width=project.output.width,
                height=project.output.height,
                duration_seconds=duration,
                fps=project.output.fps,
                seed=self._scene_seed(project.project_id, scene.scene_id),
            )
            if scene.visual_provider == "video":
                visual = await self.providers.video.generate(visual_request)
            else:
                visual = await self.providers.image.generate(visual_request)
            self._assert_lineage(visual, context)

        self._assert_exact_contract(scene.visual_format.value, avatar_video, visual)
        if audio is None:
            raise ValueError("scene renderer requires a narration audio track")
        rendered = await self.providers.renderer.render(
            SceneRenderRequest(
                context=context,
                scene=scene,
                output=project.output,
                template=template,
                audio=audio,
                avatar_video=avatar_video,
                visual=visual,
                duration_seconds=duration,
            )
        )
        self._assert_lineage(rendered, context)
        return rendered

    @staticmethod
    def _estimate_duration(text: str) -> float:
        return max(1.0, len(text.split()) / 2.5)

    @staticmethod
    def _video_has_audio(uri: str) -> bool:
        try:
            return probe_media(uri).has_audio
        except Exception:
            return False

    @staticmethod
    def _extract_audio(
        video: GeneratedAsset,
        *,
        context: GenerationContext,
        sample_rate: int,
    ) -> GeneratedAsset:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("ffmpeg is required to normalize presenter audio")
        output = Path(context.work_dir) / f"{context.scene_id}-presenter-audio.wav"
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                video.uri,
                "-vn",
                "-ac",
                "2",
                "-ar",
                str(sample_rate),
                "-c:a",
                "pcm_s16le",
                str(output),
            ],
            check=True,
        )
        digest = file_sha256(output)
        return GeneratedAsset(
            asset_id=asset_id("audio", digest),
            kind=AssetKind.AUDIO,
            uri=str(output.resolve()),
            content_hash=digest,
            project_id=context.project_id,
            scene_id=context.scene_id,
            parent_asset_ids=(video.asset_id,),
            duration_seconds=video.duration_seconds,
            sample_rate=sample_rate,
            mime_type="audio/wav",
            provenance=Provenance(
                provider="embedded-presenter-audio",
                model_identifier="ffmpeg-audio-extract",
                checkpoint_revision="system",
            ),
        )

    @staticmethod
    def _scene_seed(project_id: str, scene_id: str) -> int:
        import hashlib

        return int.from_bytes(
            hashlib.sha256(f"{project_id}:{scene_id}".encode()).digest()[:4], "big"
        )

    @staticmethod
    def _assert_exact_contract(
        visual_format: str,
        avatar_video: GeneratedAsset | None,
        visual: GeneratedAsset | None,
    ) -> None:
        if visual_format == "PRESENTER" and (avatar_video is None or visual is not None):
            raise AssertionError("PRESENTER must contain avatar only")
        if visual_format == "SPLIT" and (avatar_video is None or visual is None):
            raise AssertionError("SPLIT must contain avatar and visual")
        if visual_format == "FULL_VISUAL" and (avatar_video is not None or visual is None):
            raise AssertionError("FULL_VISUAL must contain visual only")

    @staticmethod
    def _assert_lineage(asset: GeneratedAsset, context: GenerationContext) -> None:
        if asset.project_id != context.project_id or asset.scene_id != context.scene_id:
            raise ValueError(
                "provider returned asset lineage that does not match the generation context"
            )
