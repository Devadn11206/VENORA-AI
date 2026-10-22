"""Speech-to-Text provider implementations including Mock and extensible adapters."""

import time
from typing import Optional
from app.voice.providers.base import BaseSTTProvider
from app.voice.schemas import TranscriptionResult
from app.core.errors import SpeechRecognitionError
from app.core.logging import get_logger

logger = get_logger("voice.stt_provider")


class MockSTTProvider(BaseSTTProvider):
    """Deterministic Speech-to-Text provider for automated unit testing and offline development."""

    def __init__(self, predefined_transcription: Optional[str] = None) -> None:
        self.predefined_transcription = predefined_transcription

    @property
    def provider_id(self) -> str:
        return "mock"

    def is_available(self) -> bool:
        return True

    async def transcribe(
        self,
        audio_bytes: bytes,
        audio_format: str = "wav",
        language: Optional[str] = None
    ) -> TranscriptionResult:
        start_time = time.time()
        if not audio_bytes:
            raise SpeechRecognitionError(self.provider_id, "Empty audio buffer received.")

        # If a predefined phrase is configured, return it; otherwise synthesize a simulated transcript
        text = self.predefined_transcription or "Hello VENORA, summarize my active tasks."

        duration = time.time() - start_time
        return TranscriptionResult(
            text=text,
            language=language or "en",
            provider=self.provider_id,
            duration_seconds=round(duration, 3),
            confidence=0.98,
        )
