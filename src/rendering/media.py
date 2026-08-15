from __future__ import annotations

from dataclasses import dataclass

from src.rendering.ffmpeg import FFmpegRunner


def _fraction(value: str | None) -> float | None:
    if not value or value == "0/0":
        return None
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        return float(numerator) / float(denominator) if float(denominator) else None
    return float(value)


@dataclass(frozen=True)
class MediaInfo:
    duration_seconds: float
    width: int | None
    height: int | None
    fps: float | None
    video_codec: str | None
    pixel_format: str | None
    has_audio: bool
    audio_codec: str | None
    sample_rate: int | None
    channels: int | None
    video_duration_seconds: float | None
    audio_duration_seconds: float | None


def probe_media(uri: str, *, runner: FFmpegRunner | None = None) -> MediaInfo:
    data = (runner or FFmpegRunner()).probe(uri)
    streams = data.get("streams", [])
    if not isinstance(streams, list):
        raise ValueError("ffprobe returned invalid streams")
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    format_info = data.get("format", {})
    duration = float(format_info.get("duration") or 0)
    return MediaInfo(
        duration_seconds=duration,
        width=int(video["width"]) if video and video.get("width") else None,
        height=int(video["height"]) if video and video.get("height") else None,
        fps=_fraction(video.get("avg_frame_rate")) if video else None,
        video_codec=video.get("codec_name") if video else None,
        pixel_format=video.get("pix_fmt") if video else None,
        has_audio=audio is not None,
        audio_codec=audio.get("codec_name") if audio else None,
        sample_rate=int(audio["sample_rate"]) if audio and audio.get("sample_rate") else None,
        channels=int(audio["channels"]) if audio and audio.get("channels") else None,
        video_duration_seconds=float(video["duration"])
        if video and video.get("duration")
        else None,
        audio_duration_seconds=float(audio["duration"])
        if audio and audio.get("duration")
        else None,
    )


def validate_output(
    info: MediaInfo,
    *,
    width: int,
    height: int,
    fps: int,
    expected_duration_seconds: float,
    sample_rate: int = 48000,
    duration_tolerance_seconds: float = 0.2,
    sync_tolerance_seconds: float = 0.12,
) -> tuple[str, ...]:
    errors: list[str] = []
    if (info.width, info.height) != (width, height):
        errors.append(f"resolution is {info.width}x{info.height}, expected {width}x{height}")
    if info.fps is None or abs(info.fps - fps) > 0.01:
        errors.append(f"fps is {info.fps}, expected {fps}")
    if abs(info.duration_seconds - expected_duration_seconds) > duration_tolerance_seconds:
        errors.append(
            f"duration is {info.duration_seconds:.3f}, expected {expected_duration_seconds:.3f}"
        )
    if not info.has_audio:
        errors.append("audio stream is missing")
    if info.sample_rate != sample_rate:
        errors.append(f"sample rate is {info.sample_rate}, expected {sample_rate}")
    if info.pixel_format != "yuv420p":
        errors.append(f"pixel format is {info.pixel_format}, expected yuv420p")
    if info.video_duration_seconds is not None and info.audio_duration_seconds is not None:
        drift = abs(info.video_duration_seconds - info.audio_duration_seconds)
        if drift > sync_tolerance_seconds:
            errors.append(f"audio/video stream duration drift is {drift:.3f}s")
    return tuple(errors)
