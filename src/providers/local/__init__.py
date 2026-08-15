"""Self-hosted model adapters loaded by isolated GPU workers."""

from src.providers.local.approved import ApprovedLocalLipSyncGenerator
from src.providers.local.chatterbox import ChatterboxSpeechGenerator, create_chatterbox_provider
from src.providers.local.musetalk import MuseTalkLipSyncGenerator, create_musetalk_provider

__all__ = [
    "ApprovedLocalLipSyncGenerator",
    "ChatterboxSpeechGenerator",
    "MuseTalkLipSyncGenerator",
    "create_chatterbox_provider",
    "create_musetalk_provider",
]
