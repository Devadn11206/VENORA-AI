"""Text-to-Speech provider implementations including Windows System.Speech and Mock."""

import io
import math
import struct
import time
import wave
from typing import Optional
from app.voice.providers.base import BaseTTSProvider
from app.core.errors import SpeechSynthesisError
from app.core.logging import get_logger

logger = get_logger("voice.tts_provider")


class MockTTSProvider(BaseTTSProvider):
    """Deterministic Text-to-Speech provider producing valid synthetic WAV audio frames."""

    @property
    def provider_id(self) -> str:
        return "mock"

    def is_available(self) -> bool:
        return True

    async def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        language: Optional[str] = "en"
    ) -> bytes:
        if not text or not text.strip():
            raise SpeechSynthesisError(self.provider_id, "Cannot synthesize empty or whitespace text.")

        # Generate a small, valid 0.5s mono PCM WAV tone buffer (440Hz beep)
        # Guarantees standard wave reader compatibility across tests without external dependencies
        sample_rate = 16000
        duration_sec = 0.5
        n_samples = int(sample_rate * duration_sec)

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)

            # Generate 440Hz sine wave tone
            frames = bytearray()
            for i in range(n_samples):
                val = int(32767.0 * 0.25 * math.sin(2.0 * math.pi * 440.0 * i / sample_rate))
                frames.extend(struct.pack("<h", val))

            wf.writeframes(frames)

        return buf.getvalue()
