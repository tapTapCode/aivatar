from __future__ import annotations

import textwrap
from pathlib import Path


def srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_scene_srt(
    output: str | Path,
    text: str,
    duration_seconds: float,
    *,
    max_chars_per_line: int,
) -> Path:
    target = Path(output)
    lines = textwrap.wrap(
        " ".join(text.split()),
        width=max_chars_per_line,
        break_long_words=False,
        break_on_hyphens=False,
    )
    caption_text = "\n".join(lines)
    target.write_text(
        "1\n"
        f"{srt_timestamp(0)} --> {srt_timestamp(max(0.1, duration_seconds - 0.05))}\n"
        f"{caption_text}\n",
        encoding="utf-8",
    )
    return target


def escape_filter_path(path: str | Path) -> str:
    # FFmpeg filtergraph escaping, not shell escaping (commands do not use a shell).
    return str(Path(path).resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def ass_color(hex_color: str) -> str:
    """Convert #RRGGBB to ASS &HAABBGGRR color syntax."""
    value = hex_color.removeprefix("#")
    if len(value) != 6:
        raise ValueError("caption colors must use #RRGGBB")
    int(value, 16)
    red, green, blue = value[0:2], value[2:4], value[4:6]
    return f"&H00{blue}{green}{red}"
