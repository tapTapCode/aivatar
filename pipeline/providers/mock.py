from pathlib import Path
import subprocess
from pipeline.providers.base import VoiceProvider, PresenterProvider, ImageProvider, VideoProvider, ProviderResult

def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode:
        raise RuntimeError(proc.stderr[-4000:])

class MockVoiceProvider(VoiceProvider):
    name = "mock_voice"
    def generate(self, text: str, duration: float, output_dir: Path, **kwargs) -> ProviderResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        wav = output_dir / "master_voice.wav"
        mp3 = output_dir / "master_voice.mp3"
        run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=frequency=220:duration={duration}", "-af", "volume=0.12", "-ar", "48000", "-ac", "1", str(wav)])
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-codec:a", "libmp3lame", "-q:a", "5", str(mp3)])
        return ProviderResult(wav, duration, self.name)

class MockPresenterProvider(PresenterProvider):
    name = "mock_presenter"
    def generate(self, audio_path: Path, duration: float, output_dir: Path, **kwargs) -> ProviderResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / "presenter.mp4"
        run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc2=size=960x1080:rate=30:duration={duration}", "-an", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(out)])
        return ProviderResult(out, duration, self.name)

class MockImageProvider(ImageProvider):
    name = "mock_image"
    def generate(self, prompt: str, output_dir: Path, **kwargs) -> ProviderResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / "image.png"
        run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0x16213e:s=1920x1080", "-frames:v", "1", str(out)])
        return ProviderResult(out, 0.0, self.name)

class MockVideoProvider(VideoProvider):
    name = "mock_video"
    def generate(self, prompt: str, duration: float, output_dir: Path, **kwargs) -> ProviderResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / "video.mp4"
        run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=size=1920x1080:rate=30:duration={duration}", "-an", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(out)])
        return ProviderResult(out, duration, self.name)
