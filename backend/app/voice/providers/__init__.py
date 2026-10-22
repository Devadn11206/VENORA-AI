"""Export voice providers and factory constructors."""

from typing import Optional
from app.voice.providers.base import BaseSTTProvider, BaseTTSProvider
from app.voice.providers.stt_provider import MockSTTProvider
from app.voice.providers.tts_provider import MockTTSProvider


def get_stt_provider(provider_type: Optional[str] = None) -> BaseSTTProvider:
    """Factory to get the configured STT provider."""
    p = (provider_type or "mock").strip().lower()
    if p in ("mock", "test"):
        return MockSTTProvider()
    # Default fallback
    return MockSTTProvider()


def get_tts_provider(provider_type: Optional[str] = None) -> BaseTTSProvider:
    """Factory to get the configured TTS provider."""
    p = (provider_type or "mock").strip().lower()
    if p in ("mock", "test"):
        return MockTTSProvider()
    return MockTTSProvider()


__all__ = [
    "BaseSTTProvider",
    "BaseTTSProvider",
    "MockSTTProvider",
    "MockTTSProvider",
    "get_stt_provider",
    "get_tts_provider",
]
