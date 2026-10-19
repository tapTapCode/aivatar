from __future__ import annotations

from pathlib import Path
from typing import Any

from pipeline.render.ffmpeg import run


def _fit_filter(width: int, height: int) -> str:
    return f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"


def _rounded_alpha(radius: int) -> str:
    r = max(0, int(radius))
    if not r:
        return "format=rgba"
    # Alpha-out pixels lying outside any of the four corner quarter-circles.
    outside = (
        f"gt(lt(X,{r})*lt(Y,{r})*gt(pow(X-{r},2)+pow(Y-{r},2),pow({r},2))"
        f"+gt(X,W-{r})*lt(Y,{r})*gt(pow(X-(W-{r}),2)+pow(Y-{r},2),pow({r},2))"
        f"+lt(X,{r})*gt(Y,H-{r})*gt(pow(X-{r},2)+pow(Y-(H-{r}),2),pow({r},2))"
        f"+gt(X,W-{r})*gt(Y,H-{r})*gt(pow(X-(W-{r}),2)+pow(Y-(H-{r}),2),pow({r},2)),0)"
    )
    return f"format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if({outside},0,255)'"


def compose_full_presenter(
    presenter: Path,
    output: Path,
    duration: float,
    *,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
    preset: str = "medium",
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(presenter),
        "-vf", f"{_fit_filter(width, height)},fps={fps}", "-t", f"{duration:.3f}", "-an",
        "-c:v", "libx264", "-preset", preset, "-crf", "20", "-pix_fmt", "yuv420p", str(output),
    ])
    return output


def compose_split(
    presenter: Path,
    visual: Path,
    output: Path,
    duration: float,
    *,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
    presenter_side: str = "left",
    presenter_ratio: float = 0.40,
    margin: int = 22,
    border: int = 3,
    corner_radius: int = 22,
    preset: str = "medium",
) -> Path:
    if presenter_ratio not in {0.35, 0.40, 0.50}:
        raise ValueError("presenter_ratio must be one of 0.35, 0.40, 0.50")
    presenter_side = "right" if presenter_side == "right" else "left"
    pw = int(round(width * presenter_ratio))
    vw = width - pw
    inner_pw = max(64, pw - 2 * margin)
    inner_ph = max(64, height - 2 * margin)
    px = margin if presenter_side == "left" else width - pw + margin
    vx = pw if presenter_side == "left" else 0
    border_x = px - border
    border_y = margin - border
    border_w = inner_pw + 2 * border
    border_h = inner_ph + 2 * border

    filter_complex = (
        f"[1:v]{_fit_filter(vw, height)},fps={fps}[vis];"
        f"[0:v]{_fit_filter(inner_pw, inner_ph)},{_rounded_alpha(corner_radius)},fps={fps}[pres];"
        f"color=c=0x0b1220:s={width}x{height}:r={fps}:d={duration}[bg];"
        f"[bg][vis]overlay=x={vx}:y=0[tmp1];"
        f"[tmp1]drawbox=x={border_x}:y={border_y}:w={border_w}:h={border_h}:color=white@0.65:t=fill[tmp2];"
        f"[tmp2][pres]overlay=x={px}:y={margin}:format=auto[out]"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(presenter), "-i", str(visual),
        "-filter_complex", filter_complex, "-map", "[out]", "-t", f"{duration:.3f}", "-an",
        "-c:v", "libx264", "-preset", preset, "-crf", "20", "-pix_fmt", "yuv420p", str(output),
    ])
    return output


def compose_pip(
    presenter: Path,
    visual: Path,
    output: Path,
    duration: float,
    *,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
    position: str = "bottom_right",
    size: float = 0.28,
    margin: int = 40,
    border: int = 4,
    corner_radius: int = 30,
    shadow: int = 14,
    preset: str = "medium",
) -> Path:
    if not 0.15 <= size <= 0.60:
        raise ValueError("PIP size must be between 0.15 and 0.60")
    pip_w = int(width * size)
    pip_h = int(pip_w * 9 / 8)  # portrait-ish talking head window
    pip_h = min(pip_h, int(height * 0.72))
    positions = {
        "top_left": (margin, margin),
        "top_right": (width - pip_w - margin, margin),
        "bottom_left": (margin, height - pip_h - margin),
        "bottom_right": (width - pip_w - margin, height - pip_h - margin),
    }
    x, y = positions.get(position, positions["bottom_right"])
    filter_complex = (
        f"[1:v]{_fit_filter(width, height)},fps={fps}[vis];"
        f"[0:v]{_fit_filter(pip_w, pip_h)},{_rounded_alpha(corner_radius)},fps={fps}[pres];"
        f"[vis]drawbox=x={x-shadow}:y={y-shadow}:w={pip_w+shadow*2}:h={pip_h+shadow*2}:color=black@0.35:t=fill[tmp0];"
        f"[tmp0]drawbox=x={x-border}:y={y-border}:w={pip_w+border*2}:h={pip_h+border*2}:color=white@0.75:t=fill[tmp1];"
        f"[tmp1][pres]overlay=x={x}:y={y}:format=auto[out]"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(presenter), "-i", str(visual),
        "-filter_complex", filter_complex, "-map", "[out]", "-t", f"{duration:.3f}", "-an",
        "-c:v", "libx264", "-preset", preset, "-crf", "20", "-pix_fmt", "yuv420p", str(output),
    ])
    return output


def compose_presenter_scene(
    scene_type: str,
    presenter: Path,
    visual: Path | None,
    output: Path,
    duration: float,
    layout: dict[str, Any] | None = None,
    *,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
) -> Path:
    layout = layout or {}
    if scene_type == "PRESENTER":
        return compose_full_presenter(presenter, output, duration, width=width, height=height, fps=fps, preset=str(layout.get("preset", "medium")))
    if visual is None:
        raise ValueError(f"{scene_type} requires a visual clip")
    if scene_type == "SPLIT":
        return compose_split(
            presenter,
            visual,
            output,
            duration,
            width=width,
            height=height,
            fps=fps,
            presenter_side=str(layout.get("presenter_side", "left")),
            presenter_ratio=float(layout.get("presenter_ratio", 0.40)),
            margin=int(layout.get("margin", 22)),
            border=int(layout.get("border", 3)),
            corner_radius=int(layout.get("corner_radius", 22)),
            preset=str(layout.get("preset", "medium")),
        )
    if scene_type == "PIP":
        return compose_pip(
            presenter,
            visual,
            output,
            duration,
            width=width,
            height=height,
            fps=fps,
            position=str(layout.get("position", "bottom_right")),
            size=float(layout.get("size", 0.28)),
            margin=int(layout.get("margin", 40)),
            border=int(layout.get("border", 4)),
            corner_radius=int(layout.get("corner_radius", 30)),
            shadow=int(layout.get("shadow", 14)),
            preset=str(layout.get("preset", "medium")),
        )
    raise ValueError(f"Unsupported presenter scene type: {scene_type}")
