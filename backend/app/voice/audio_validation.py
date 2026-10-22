"""Audio payload validation, header verification, format bounds, and temporary file management."""

import io
import os
import re
import uuid
import wave
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Dict, Any

from app.core.logging import get_logger
from app.core.errors import AudioValidationError
from app.core.config import Settings, get_settings

logger = get_logger("voice.audio_validation")


class AudioValidator:
    """Validates audio files against size, duration, format, and sample bounds."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.audio_dir = os.path.abspath(self.settings.VOICE_AUDIO_DIR)
        os.makedirs(self.audio_dir, exist_ok=True)

    def validate_audio_bytes(
        self,
        audio_bytes: bytes,
        filename: Optional[str] = None
    ) -> Tuple[str, float]:
        """Validate raw audio bytes.

        Checks:
        1. Non-empty payload.
        2. Size under max MB limit.
        3. Header integrity (valid WAV header or container magic bytes).
        4. Duration under maximum recording duration.

        Returns:
            Tuple[detected_format, duration_seconds]
        """
        if not audio_bytes or len(audio_bytes) == 0:
            raise AudioValidationError("Audio data is empty or missing.")

        max_bytes = int(self.settings.VOICE_MAX_AUDIO_MB * 1024 * 1024)
        if len(audio_bytes) > max_bytes:
            raise AudioValidationError(
                f"Audio size ({len(audio_bytes)} bytes) exceeds configured limit ({max_bytes} bytes / {self.settings.VOICE_MAX_AUDIO_MB}MB)."
            )

        # Check for WAV header (RIFF ... WAVE)
        if len(audio_bytes) >= 12 and audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
            return self._validate_wav_stream(audio_bytes)

        # Ogg Vorbis/Opus magic bytes
        if len(audio_bytes) >= 4 and audio_bytes[:4] == b"OggS":
            # Basic bounded estimate for OGG container
            est_duration = min(self.settings.VOICE_MAX_RECORDING_SECONDS, len(audio_bytes) / 16000.0)
            return "ogg", est_duration

        # WebM / Matroska magic bytes (0x1A 0x45 0xDF 0xA3)
        if len(audio_bytes) >= 4 and audio_bytes[:4] == b"\x1a\x45\xdf\xa3":
            est_duration = min(self.settings.VOICE_MAX_RECORDING_SECONDS, len(audio_bytes) / 16000.0)
            return "webm", est_duration

        # MP3 ID3 or sync frame (0xFF 0xFB/0xF3/0xF2)
        if (len(audio_bytes) >= 3 and audio_bytes[:3] == b"ID3") or (len(audio_bytes) >= 2 and audio_bytes[0] == 0xFF and (audio_bytes[1] & 0xE0) == 0xE0):
            est_duration = min(self.settings.VOICE_MAX_RECORDING_SECONDS, len(audio_bytes) / 16000.0)
            return "mp3", est_duration

        raise AudioValidationError("Unsupported or unrecognized audio format. WAV (RIFF/WAVE), OGG, MP3, or WEBM required.")

    def _validate_wav_stream(self, audio_bytes: bytes) -> Tuple[str, float]:
        """Validate WAV header, channels, sample rate, and exact duration."""
        try:
            with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
                channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                framerate = wf.getframerate()
                nframes = wf.getnframes()

                if channels < 1 or channels > 8:
                    raise AudioValidationError(f"Invalid channel count ({channels}). Must be between 1 and 8.")

                if framerate < 8000 or framerate > 192000:
                    raise AudioValidationError(f"Unsupported sample rate ({framerate}Hz). Expected 8kHz - 192kHz.")

                duration = nframes / float(framerate) if framerate > 0 else 0.0

                if duration > self.settings.VOICE_MAX_RECORDING_SECONDS:
                    raise AudioValidationError(
                        f"Audio duration ({duration:.2f}s) exceeds maximum allowed limit ({self.settings.VOICE_MAX_RECORDING_SECONDS}s)."
                    )

                return "wav", duration
        except wave.Error as we:
            raise AudioValidationError(f"Malformed or corrupted WAV header: {we}")

    def save_temp_artifact(self, audio_bytes: bytes, audio_format: str = "wav") -> str:
        """Save validated audio bytes to safe application-managed storage and return artifact_id."""
        artifact_id = str(uuid.uuid4())
        clean_ext = re.sub(r"[^a-zA-Z0-9]", "", audio_format.lower()) or "wav"
        filename = f"{artifact_id}.{clean_ext}"
        filepath = os.path.join(self.audio_dir, filename)

        with open(filepath, "wb") as f:
            f.write(audio_bytes)

        logger.debug(f"Saved audio artifact '{artifact_id}' ({len(audio_bytes)} bytes) to {filepath}")
        return artifact_id

    def get_artifact_path(self, artifact_id: str) -> Optional[str]:
        """Resolve an authorized artifact ID to its local file path without permitting path traversal."""
        # Sanitize artifact_id: must be pure alphanumeric / uuid
        if not re.match(r"^[a-zA-Z0-9_\-]+$", artifact_id):
            return None

        # Look for file matching artifact_id.* in audio_dir
        if not os.path.exists(self.audio_dir):
            return None

        for fname in os.listdir(self.audio_dir):
            if fname.startswith(f"{artifact_id}."):
                full_path = os.path.abspath(os.path.join(self.audio_dir, fname))
                # Enforce containment strictly within audio_dir
                if os.path.commonpath([full_path, self.audio_dir]) == self.audio_dir:
                    return full_path

        return None

    def cleanup_expired_artifacts(self) -> int:
        """Remove audio artifacts older than VOICE_AUDIO_RETENTION_MINUTES."""
        if not os.path.exists(self.audio_dir):
            return 0

        cutoff = datetime.now() - timedelta(minutes=self.settings.VOICE_AUDIO_RETENTION_MINUTES)
        deleted_count = 0

        for fname in os.listdir(self.audio_dir):
            full_path = os.path.join(self.audio_dir, fname)
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(full_path))
                if mtime < cutoff:
                    os.remove(full_path)
                    deleted_count += 1
            except Exception as exc:
                logger.warning(f"Error cleaning up audio file {fname}: {exc}")

        return deleted_count
