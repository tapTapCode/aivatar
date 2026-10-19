from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

class ProviderUnavailable(RuntimeError):
    pass

@dataclass(slots=True)
class ProviderResult:
    path: Path
    duration: float
    provider: str
    estimated_cost_usd: float = 0.0
    actual_cost_usd: float = 0.0
    metadata: dict | None = None

class VoiceProvider(ABC):
    name: str
    @abstractmethod
    def generate(self, text: str, duration: float, output_dir: Path, **kwargs) -> ProviderResult: ...

class PresenterProvider(ABC):
    name: str
    @abstractmethod
    def generate(self, audio_path: Path, duration: float, output_dir: Path, **kwargs) -> ProviderResult: ...

class ImageProvider(ABC):
    name: str
    @abstractmethod
    def generate(self, prompt: str, output_dir: Path, **kwargs) -> ProviderResult: ...

class VideoProvider(ABC):
    name: str
    @abstractmethod
    def generate(self, prompt: str, duration: float, output_dir: Path, **kwargs) -> ProviderResult: ...
