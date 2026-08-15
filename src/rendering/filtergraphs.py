from __future__ import annotations

from dataclasses import dataclass

from src.schemas.assets import AssetKind
from src.schemas.requests import SceneRenderRequest
from src.schemas.scene import VisualFormat


@dataclass(frozen=True)
class FilterGraph:
    expression: str
    video_label: str = "vout"
    audio_label: str = "aout"


def _cover(input_label: str, width: int, height: int, fps: int, output_label: str) -> str:
    return (
        f"[{input_label}]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1,fps={fps}[{output_label}]"
    )


def _contain(
    input_label: str,
    width: int,
    height: int,
    fps: int,
    background_color: str,
    output_label: str,
) -> str:
    color = background_color.replace("#", "0x")
    return (
        f"[{input_label}]scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={color},setsar=1,fps={fps}[{output_label}]"
    )


def _static_motion(
    input_label: str,
    width: int,
    height: int,
    fps: int,
    duration_seconds: float,
    mode: str,
    output_label: str,
) -> str:
    if mode == "slow_pan":
        zoom = "1.08"
        x = f"min((iw-iw/zoom)*on/{max(1, fps * duration_seconds):.6f}\\,iw-iw/zoom)"
        y = "(ih-ih/zoom)/2"
    else:
        zoom = "min(max(zoom,pzoom)+0.0007\\,1.08)"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    return (
        f"[{input_label}]zoompan=z='{zoom}':x='{x}':y='{y}':"
        f"d=1:s={width}x{height}:fps={fps}[{output_label}]"
    )


def build_filtergraph(
    request: SceneRenderRequest,
    *,
    avatar_input: int | None,
    visual_input: int | None,
    audio_input: int,
    captions_filter: str | None = None,
) -> FilterGraph:
    width = request.output.width
    height = request.output.height
    fps = request.output.fps
    graph: list[str] = []

    if request.scene.visual_format == VisualFormat.PRESENTER:
        if avatar_input is None or visual_input is not None:
            raise ValueError("PRESENTER filtergraph requires avatar only")
        if request.template.presenter_fit == "contain":
            graph.append(
                _contain(
                    f"{avatar_input}:v",
                    width,
                    height,
                    fps,
                    request.template.background_color,
                    "base",
                )
            )
        else:
            graph.append(_cover(f"{avatar_input}:v", width, height, fps, "base"))

    elif request.scene.visual_format == VisualFormat.FULL_VISUAL:
        if visual_input is None or avatar_input is not None:
            raise ValueError("FULL_VISUAL filtergraph requires visual only")
        fit = request.template.split.visual_fit
        if fit == "contain":
            graph.append(
                _contain(
                    f"{visual_input}:v",
                    width,
                    height,
                    fps,
                    request.template.background_color,
                    "base",
                )
            )
        else:
            motion = (
                request.visual is not None
                and request.visual.kind == AssetKind.IMAGE
                and request.template.static_visual_motion != "none"
            )
            target = "visual_base" if motion else "base"
            graph.append(_cover(f"{visual_input}:v", width, height, fps, target))
            if motion:
                graph.append(
                    _static_motion(
                        target,
                        width,
                        height,
                        fps,
                        request.duration_seconds,
                        request.template.static_visual_motion,
                        "base",
                    )
                )

    else:
        if avatar_input is None or visual_input is None:
            raise ValueError("SPLIT filtergraph requires avatar and visual")
        split = request.template.split
        divider = split.divider_width_px
        color = split.divider_color.replace("#", "0x")
        if split.orientation == "horizontal":
            available = width - divider
            avatar_width = max(2, int(available * split.avatar_ratio) // 2 * 2)
            visual_width = available - avatar_width
            graph.append(_cover(f"{avatar_input}:v", avatar_width, height, fps, "avatar"))
            if split.visual_fit == "contain":
                graph.append(
                    _contain(
                        f"{visual_input}:v",
                        visual_width,
                        height,
                        fps,
                        request.template.background_color,
                        "visual",
                    )
                )
            else:
                motion = (
                    request.visual is not None
                    and request.visual.kind == AssetKind.IMAGE
                    and request.template.static_visual_motion != "none"
                )
                target = "visual_base" if motion else "visual"
                graph.append(_cover(f"{visual_input}:v", visual_width, height, fps, target))
                if motion:
                    graph.append(
                        _static_motion(
                            target,
                            visual_width,
                            height,
                            fps,
                            request.duration_seconds,
                            request.template.static_visual_motion,
                            "visual",
                        )
                    )
            if divider:
                graph.append(
                    f"color=c={color}:s={divider}x{height}:r={fps}:d={request.duration_seconds}[divider]"
                )
                order = (
                    "[avatar][divider][visual]"
                    if split.avatar_side == "left"
                    else "[visual][divider][avatar]"
                )
                graph.append(f"{order}hstack=inputs=3[base]")
            else:
                order = "[avatar][visual]" if split.avatar_side == "left" else "[visual][avatar]"
                graph.append(f"{order}hstack=inputs=2[base]")
        else:
            available = height - divider
            avatar_height = max(2, int(available * split.avatar_ratio) // 2 * 2)
            visual_height = available - avatar_height
            graph.append(_cover(f"{avatar_input}:v", width, avatar_height, fps, "avatar"))
            if split.visual_fit == "contain":
                graph.append(
                    _contain(
                        f"{visual_input}:v",
                        width,
                        visual_height,
                        fps,
                        request.template.background_color,
                        "visual",
                    )
                )
            else:
                motion = (
                    request.visual is not None
                    and request.visual.kind == AssetKind.IMAGE
                    and request.template.static_visual_motion != "none"
                )
                target = "visual_base" if motion else "visual"
                graph.append(_cover(f"{visual_input}:v", width, visual_height, fps, target))
                if motion:
                    graph.append(
                        _static_motion(
                            target,
                            width,
                            visual_height,
                            fps,
                            request.duration_seconds,
                            request.template.static_visual_motion,
                            "visual",
                        )
                    )
            if divider:
                graph.append(
                    f"color=c={color}:s={width}x{divider}:r={fps}:d={request.duration_seconds}[divider]"
                )
                order = (
                    "[avatar][divider][visual]"
                    if split.avatar_side == "top"
                    else "[visual][divider][avatar]"
                )
                graph.append(f"{order}vstack=inputs=3[base]")
            else:
                order = "[avatar][visual]" if split.avatar_side == "top" else "[visual][avatar]"
                graph.append(f"{order}vstack=inputs=2[base]")

    if captions_filter:
        graph.append(f"[base]{captions_filter},format=yuv420p,setpts=PTS-STARTPTS[vout]")
    else:
        graph.append("[base]format=yuv420p,setpts=PTS-STARTPTS[vout]")

    lufs = request.template.audio.target_lufs
    true_peak = request.template.audio.true_peak_db
    graph.append(
        f"[{audio_input}:a]aresample={request.template.audio.sample_rate},"
        "aformat=sample_fmts=fltp:channel_layouts=stereo,"
        f"atrim=duration={request.duration_seconds},asetpts=PTS-STARTPTS,"
        f"loudnorm=I={lufs}:TP={true_peak}:LRA=11[aout]"
    )
    return FilterGraph(";".join(graph))
