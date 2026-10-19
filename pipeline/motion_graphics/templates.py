from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pipeline.render.ffmpeg import run


@dataclass(slots=True)
class MotionGraphicSpec:
    template: str
    title: str
    subtitle: str = ""
    start: float = 0.35
    hold: float = 3.8


def _escape(text: str) -> str:
    # FFmpeg drawtext escaping for dynamically generated project strings.
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def graphic_filter(spec: MotionGraphicSpec, width: int = 1920, height: int = 1080) -> str:
    title = _escape(spec.title[:90])
    subtitle = _escape(spec.subtitle[:120])
    end = spec.start + spec.hold
    enable = f"between(t,{spec.start:.2f},{end:.2f})"
    common = "fontcolor=white:shadowcolor=black@0.55:shadowx=2:shadowy=2"

    if spec.template == "lower_third":
        return (
            f"drawbox=x=70:y=h-245:w=980:h=150:color=0x07111f@0.80:t=fill:enable='{enable}',"
            f"drawtext=text='{title}':x=105:y=h-215:fontsize=52:{common}:enable='{enable}',"
            f"drawtext=text='{subtitle}':x=107:y=h-148:fontsize=28:fontcolor=white@0.78:enable='{enable}'"
        )
    if spec.template == "callout":
        return (
            f"drawbox=x=iw-650:y=115:w=560:h=230:color=0x0b3a78@0.88:t=fill:enable='{enable}',"
            f"drawtext=text='{title}':x=w-610:y=155:fontsize=58:{common}:enable='{enable}',"
            f"drawtext=text='{subtitle}':x=w-608:y=245:fontsize=28:fontcolor=white@0.82:enable='{enable}'"
        )
    if spec.template == "keyword_highlight":
        return (
            f"drawbox=x=220:y=ih/2-95:w=iw-440:h=190:color=black@0.62:t=fill:enable='{enable}',"
            f"drawtext=text='{title}':x=(w-text_w)/2:y=(h-text_h)/2:fontsize=68:{common}:enable='{enable}'"
        )
    # section_header is the safe default.
    return (
        f"drawbox=x=0:y=0:w=iw:h=ih:color=0x06101d@0.46:t=fill:enable='{enable}',"
        f"drawbox=x=150:y=ih/2-125:w=12:h=250:color=0x2f80ff@0.95:t=fill:enable='{enable}',"
        f"drawtext=text='{title}':x=195:y=h/2-78:fontsize=72:{common}:enable='{enable}',"
        f"drawtext=text='{subtitle}':x=198:y=h/2+28:fontsize=34:fontcolor=white@0.80:enable='{enable}'"
    )


def apply_motion_graphic(
    source: Path,
    output: Path,
    duration: float,
    spec: MotionGraphicSpec,
    *,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
    preset: str = "medium",
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps={fps},{graphic_filter(spec, width, height)}"
    run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(source), "-vf", vf,
        "-t", f"{duration:.3f}", "-an", "-c:v", "libx264", "-preset", preset,
        "-crf", "20", "-pix_fmt", "yuv420p", str(output),
    ])
    return output
