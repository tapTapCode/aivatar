from pipeline.providers.mock import MockVoiceProvider, MockPresenterProvider, MockImageProvider, MockVideoProvider
from pipeline.providers.presenter import AuthorizedHeyGenProvider, AuthorizedHiggsfieldProvider, MuseTalkFallbackProvider, ManualPresenterImportProvider
from pipeline.providers.voice import AI33Provider, SixtyNineLabsProvider

def test_provider_interfaces_exist():
    assert MockVoiceProvider.name=="mock_voice"
    assert AuthorizedHeyGenProvider.name=="authorized_heygen"
    assert AuthorizedHiggsfieldProvider.name=="authorized_higgsfield"
    assert MuseTalkFallbackProvider.name=="musetalk_fallback"
    assert ManualPresenterImportProvider.name=="manual_presenter_import"
    assert AI33Provider.name=="ai33"
    assert SixtyNineLabsProvider.name=="69labs"
