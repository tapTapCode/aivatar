from pipeline.providers.base import PresenterProvider, VoiceProvider
from pipeline.providers.mock import MockPresenterProvider, MockVoiceProvider
from pipeline.providers.presenter import AuthorizedHeyGenProvider, AuthorizedHiggsfieldProvider, ManualPresenterImportProvider, MuseTalkFallbackProvider
from pipeline.providers.voice import AI33Provider, ImportedAudioProvider, SixtyNineLabsProvider


def image_provider(name: str):
    from pipeline.providers.fal import FalFluxProvider
    from pipeline.providers.images import FluxKleinProvider
    from pipeline.providers.mock import MockImageProvider
    providers = {
        "fal_flux": FalFluxProvider,
        "flux_klein": FluxKleinProvider,
        "mock_image": MockImageProvider,
    }
    try:
        return providers[name]()
    except KeyError as exc:
        raise ValueError(f"Unknown image provider: {name}") from exc


def voice_provider(name: str) -> VoiceProvider:
    providers: dict[str, type[VoiceProvider]] = {
        "mock_voice": MockVoiceProvider,
        "ai33": AI33Provider,
        "69labs": SixtyNineLabsProvider,
        "imported_audio": ImportedAudioProvider,
    }
    try:
        return providers[name]()
    except KeyError as exc:
        raise ValueError(f"Unknown voice provider: {name}") from exc


def presenter_provider(name: str) -> PresenterProvider:
    providers: dict[str, type[PresenterProvider]] = {
        "authorized_heygen": AuthorizedHeyGenProvider,
        "authorized_higgsfield": AuthorizedHiggsfieldProvider,
        "musetalk_fallback": MuseTalkFallbackProvider,
        "manual_presenter_import": ManualPresenterImportProvider,
        "mock_presenter": MockPresenterProvider,
    }
    try:
        return providers[name]()
    except KeyError as exc:
        raise ValueError(f"Unknown presenter provider: {name}") from exc
