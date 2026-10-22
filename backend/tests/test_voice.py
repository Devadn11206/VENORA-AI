"""Comprehensive test suite for Phase 8 Voice Interface & Controlled Audio Processing."""

import base64
import io
import math
import struct
import wave
import pytest
from datetime import datetime, timedelta
from typing import Generator
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AudioValidationError, VoiceSessionError, AudioDeviceError
from app.voice.audio_validation import AudioValidator
from app.voice.audio_capture import AudioCaptureService
from app.voice.session_manager import VoiceSessionManager, VoiceSessionState
from app.voice.providers import MockSTTProvider, MockTTSProvider
from app.voice.service import VoiceService
from app.voice.schemas import (
    AudioPayloadRequest,
    SpeechSynthesisRequest,
    VoiceSessionCreateRequest,
)


def create_synthetic_wav_bytes(duration_seconds: float = 1.0, sample_rate: int = 16000) -> bytes:
    """Generate in-memory valid PCM mono WAV bytes for testing."""
    buf = io.BytesIO()
    n_samples = int(sample_rate * duration_seconds)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(n_samples):
            val = int(32767.0 * 0.25 * math.sin(2.0 * math.pi * 440.0 * i / sample_rate))
            frames.extend(struct.pack("<h", val))
        wf.writeframes(frames)
    return buf.getvalue()


# -----------------------------------------------------------------------------
# 1. Audio Validation Tests
# -----------------------------------------------------------------------------
def test_audio_validation_valid_wav():
    """Verify valid WAV buffer is accepted and accurately measured."""
    validator = AudioValidator()
    wav_bytes = create_synthetic_wav_bytes(duration_seconds=2.0)
    fmt, duration = validator.validate_audio_bytes(wav_bytes)
    assert fmt == "wav"
    assert 1.9 <= duration <= 2.1


def test_audio_validation_empty_rejected():
    """Verify empty audio bytes raise AudioValidationError."""
    validator = AudioValidator()
    with pytest.raises(AudioValidationError, match="empty or missing"):
        validator.validate_audio_bytes(b"")


def test_audio_validation_unsupported_format_rejected():
    """Verify unrecognized random bytes are rejected."""
    validator = AudioValidator()
    with pytest.raises(AudioValidationError, match="Unsupported or unrecognized"):
        validator.validate_audio_bytes(b"RANDOM_NON_AUDIO_HEADER_DATA_1234567890")


def test_audio_validation_oversized_rejected():
    """Verify audio exceeding max MB size is rejected."""
    custom_settings = Settings(VOICE_MAX_AUDIO_MB=0.001)  # ~1KB limit
    validator = AudioValidator(settings=custom_settings)
    wav_bytes = create_synthetic_wav_bytes(duration_seconds=1.0)
    with pytest.raises(AudioValidationError, match="exceeds configured limit"):
        validator.validate_audio_bytes(wav_bytes)


def test_audio_validation_duration_limit_enforced():
    """Verify audio exceeding maximum recording seconds is rejected."""
    custom_settings = Settings(VOICE_MAX_RECORDING_SECONDS=1.0)
    validator = AudioValidator(settings=custom_settings)
    wav_bytes = create_synthetic_wav_bytes(duration_seconds=3.0)
    with pytest.raises(AudioValidationError, match="exceeds maximum allowed limit"):
        validator.validate_audio_bytes(wav_bytes)


def test_audio_artifact_storage_and_containment():
    """Verify audio artifacts are stored safely and path traversal is prevented."""
    validator = AudioValidator()
    wav_bytes = create_synthetic_wav_bytes(duration_seconds=0.5)
    artifact_id = validator.save_temp_artifact(wav_bytes, "wav")
    assert artifact_id is not None

    path = validator.get_artifact_path(artifact_id)
    assert path is not None
    assert path.endswith(".wav")

    # Path traversal attack attempt
    traversal_path = validator.get_artifact_path("../../etc/passwd")
    assert traversal_path is None


# -----------------------------------------------------------------------------
# 2. STT Provider Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mock_stt_transcription():
    """Verify MockSTTProvider returns valid transcription."""
    stt = MockSTTProvider(predefined_transcription="VENORA, check system health.")
    wav_bytes = create_synthetic_wav_bytes(duration_seconds=1.0)
    res = await stt.transcribe(wav_bytes)
    assert res.text == "VENORA, check system health."
    assert res.provider == "mock"
    assert res.confidence == 0.98


# -----------------------------------------------------------------------------
# 3. TTS Provider Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mock_tts_synthesis():
    """Verify MockTTSProvider produces valid readable WAV audio."""
    tts = MockTTSProvider()
    audio = await tts.synthesize("Operation completed successfully.")
    assert len(audio) > 0
    # Must be valid WAV
    with wave.open(io.BytesIO(audio), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getframerate() == 16000


# -----------------------------------------------------------------------------
# 4. Voice Session Lifecycle & State Machine Tests
# -----------------------------------------------------------------------------
def test_voice_session_lifecycle_transitions():
    """Test valid lifecycle transitions for voice sessions."""
    manager = VoiceSessionManager()
    session = manager.create_session()
    assert session.state == VoiceSessionState.IDLE

    session.transition_to(VoiceSessionState.CAPTURING)
    assert session.state == VoiceSessionState.CAPTURING

    session.transition_to(VoiceSessionState.TRANSCRIBING)
    assert session.state == VoiceSessionState.TRANSCRIBING

    session.transition_to(VoiceSessionState.PROCESSING)
    assert session.state == VoiceSessionState.PROCESSING

    session.transition_to(VoiceSessionState.SYNTHESIZING)
    assert session.state == VoiceSessionState.SYNTHESIZING

    session.transition_to(VoiceSessionState.COMPLETED)
    assert session.state == VoiceSessionState.COMPLETED
    assert session.completed_at is not None

    # Cannot transition from terminal state
    with pytest.raises(VoiceSessionError, match="terminal state"):
        session.transition_to(VoiceSessionState.CAPTURING)


def test_voice_session_concurrent_limit():
    """Verify concurrent session bounds are strictly enforced."""
    settings = Settings(VOICE_MAX_CONCURRENT_SESSIONS=1)
    manager = VoiceSessionManager(settings=settings)
    s1 = manager.create_session()
    s1.transition_to(VoiceSessionState.CAPTURING)

    # Attempting to create second active session should be rejected
    with pytest.raises(VoiceSessionError, match="Maximum concurrent active voice sessions"):
        manager.create_session()


def test_voice_session_cancellation():
    """Verify active session cancellation."""
    manager = VoiceSessionManager()
    s = manager.create_session()
    cancelled = manager.cancel_session(s.session_id)
    assert cancelled.state == VoiceSessionState.CANCELLED


# -----------------------------------------------------------------------------
# 5. Microphone & Audio Capture Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_microphone_disabled_by_default():
    """Verify microphone capture is rejected when VOICE_MICROPHONE_ENABLED=false."""
    capture = AudioCaptureService(settings=Settings(VOICE_MICROPHONE_ENABLED=False))
    with pytest.raises(AudioDeviceError, match="disabled in configuration"):
        await capture.start_capture("test_session")


@pytest.mark.asyncio
async def test_microphone_capture_flow():
    """Verify start and stop capture lifecycle when enabled."""
    capture = AudioCaptureService(settings=Settings(VOICE_MICROPHONE_ENABLED=True))
    assert capture.is_capturing is False

    await capture.start_capture("vsession_1")
    assert capture.is_capturing is True

    # Duplicate capture blocked
    with pytest.raises(AudioDeviceError, match="already active"):
        await capture.start_capture("vsession_2")

    audio_bytes = await capture.stop_capture("vsession_1")
    assert capture.is_capturing is False
    assert len(audio_bytes) > 0


# -----------------------------------------------------------------------------
# 6. Full Service Pipeline Integration Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_voice_service_full_interaction_pipeline(db_session: Session):
    """Test full voice interaction: Audio in -> Transcribe -> Reasoning -> Synthesis."""
    svc = VoiceService(
        db=db_session,
        stt_provider=MockSTTProvider(predefined_transcription="List current applications"),
        tts_provider=MockTTSProvider()
    )

    wav_bytes = create_synthetic_wav_bytes(duration_seconds=1.0)
    interaction = await svc.process_voice_interaction(
        audio_bytes=wav_bytes,
        synthesize_response=True
    )

    assert interaction.session_id is not None
    assert interaction.transcription.text == "List current applications"
    assert interaction.assistant_text is not None
    assert interaction.spoken_audio is not None
    assert interaction.spoken_audio.artifact_id is not None


# -----------------------------------------------------------------------------
# 7. REST API Endpoints Tests
# -----------------------------------------------------------------------------
def test_api_voice_status_and_capabilities(client: TestClient):
    """Test voice status and capabilities endpoints."""
    resp = client.get("/api/v1/voice/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["voice_enabled"] is True
    assert "stt_provider" in data
    assert "tts_provider" in data


def test_api_voice_session_crud_and_cancel(client: TestClient):
    """Test voice session creation, retrieval, and cancellation."""
    # 1. Create session
    create_resp = client.post(
        "/api/v1/voice/sessions",
        json={"language": "en", "synthesize_response": True}
    )
    assert create_resp.status_code == 201
    sdata = create_resp.json()
    sid = sdata["session_id"]
    assert sdata["state"] == "idle"

    # 2. Get session
    get_resp = client.get(f"/api/v1/voice/sessions/{sid}")
    assert get_resp.status_code == 200
    assert get_resp.json()["session_id"] == sid

    # 3. Cancel session
    cancel_resp = client.post(f"/api/v1/voice/sessions/{sid}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["state"] == "cancelled"


def test_api_voice_transcribe(client: TestClient):
    """Test /api/v1/voice/transcribe endpoint with base64 payload."""
    wav_bytes = create_synthetic_wav_bytes(duration_seconds=1.0)
    b64_audio = base64.b64encode(wav_bytes).decode("utf-8")

    resp = client.post(
        "/api/v1/voice/transcribe",
        json={"audio_base64": b64_audio, "filename": "input.wav"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "mock"
    assert len(data["text"]) > 0


def test_api_voice_respond_and_audio_download(client: TestClient):
    """Test /api/v1/voice/respond turn and subsequent audio artifact streaming."""
    wav_bytes = create_synthetic_wav_bytes(duration_seconds=1.0)
    b64_audio = base64.b64encode(wav_bytes).decode("utf-8")

    resp = client.post(
        "/api/v1/voice/respond",
        json={"audio_base64": b64_audio, "synthesize_response": True}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "transcription" in data
    assert "assistant_text" in data
    assert data["spoken_audio"] is not None
    art_id = data["spoken_audio"]["artifact_id"]

    # Download audio artifact
    audio_resp = client.get(f"/api/v1/voice/audio/{art_id}")
    assert audio_resp.status_code == 200
    assert len(audio_resp.content) > 0


def test_api_voice_synthesize(client: TestClient):
    """Test explicit /api/v1/voice/synthesize endpoint."""
    resp = client.post(
        "/api/v1/voice/synthesize",
        json={"text": "Voice synthesis pipeline operational.", "language": "en"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["artifact_id"] is not None
    assert data["audio_format"] == "wav"
