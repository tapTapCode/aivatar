from pathlib import Path

from pipeline.render.composite import compose_presenter_scene
from pipeline.render.ffmpeg import run


PROJECT = "d5c6870c-03f8-4eda-9b4b-aa8cc1a5e100"
BASE = Path("workspace/projects") / PROJECT
VIDEOS = BASE / "videos"
PRESENTER = BASE / "presenter"
RENDER = BASE / "render"
RENDER.mkdir(parents=True, exist_ok=True)

scenes = [
    (1, 21.370, PRESENTER / "presenter_b11b3bf4-f7e3-406a-bafd-705967aa5e48.mp4", None),
    (2, 32.055, VIDEOS / "visual_scene_002.mp4", None),
    (3, 26.712, PRESENTER / "presenter_a7642bda-761a-4d37-be27-f44b7e4d9383.mp4", VIDEOS / "visual_scene_003.mp4"),
    (4, 32.055, VIDEOS / "visual_scene_004.mp4", None),
    (5, 24.041, VIDEOS / "visual_scene_005.mp4", None),
    (6, 24.041, VIDEOS / "visual_scene_006.mp4", None),
]

rendered = []
for ordinal, duration, primary, visual in scenes:
    output = RENDER / f"local_scene_{ordinal:03}.mp4"
    if visual is None:
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(primary), "-t", f"{duration:.3f}", "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20", "-pix_fmt", "yuv420p", str(output)])
    else:
        compose_presenter_scene("SPLIT", primary, visual, output, duration, {"preset": "ultrafast"})
    rendered.append(output)

concat = RENDER / "local_concat.txt"
concat.write_text("\n".join(f"file '{p.resolve()}'" for p in rendered), encoding="utf-8")
timeline = RENDER / "local_timeline.mp4"
run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat), "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20", "-pix_fmt", "yuv420p", str(timeline)])

master = BASE / "audio" / "master_voice.wav"
captions = BASE / "captions" / "captions.srt"
final = BASE / "Aivatar-local-fallback-180s.mp4"
subtitle_filter = f"subtitles={captions.as_posix()}:force_style='FontName=Arial,FontSize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H80000000,BorderStyle=1,Outline=2,Shadow=0,MarginV=64'"
run([
    "ffmpeg", "-y", "-loglevel", "error", "-i", str(timeline), "-i", str(master),
    "-filter_complex", f"[0:v]tpad=stop_mode=clone:stop_duration=19.726,fade=t=out:st=179.2:d=0.8,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,{subtitle_filter}[v];[1:a]apad=pad_dur=19.726[a]",
    "-map", "[v]", "-map", "[a]", "-t", "180.000",
    "-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(final),
])
print(final)
