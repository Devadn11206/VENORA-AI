"""Abstract provider interfaces for Speech-to-Text and Text-to-Speech engines."""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from app.voice.schemas import TranscriptionResult, SpeechSynthesisResult


class BaseSTTProvider(ABC):
    """Abstract interface for speech-to-text transcription providers."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique provider identifier (e.g. 'mock', 'openrouter', 'whisper_local')."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider credentials/libraries are configured and available."""
        pass

    @abstractmethod
    async def transcribe(
        self,
        audio_bytes: bytes,
        audio_format: str = "wav",
        language: Optional[str] = None
    ) -> TranscriptionResult:
        """Transcribe audio bytes to plain text."""
        pass


class BaseTTSProvider(ABC):
    """Abstract interface for text-to-speech synthesis providers."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique provider identifier (e.g. 'mock', 'windows_system', 'openrouter')."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider backend/libraries are configured and available."""
        pass

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        language: Optional[str] = "en"
    ) -> bytes:
        """Synthesize text into audio bytes (WAV/MP3)."""
        pass
