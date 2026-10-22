"""Pydantic schemas and enums for Phase 8 Voice Interface & Audio Processing."""

from datetime import datetime
import enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict


class VoiceSessionState(str, enum.Enum):
    """Lifecycle states for a voice interaction session."""
    IDLE = "idle"
    CAPTURING = "capturing"
    TRANSCRIBING = "transcribing"
    PROCESSING = "processing"
    SYNTHESIZING = "synthesizing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class AudioFormat(str, enum.Enum):
    """Approved audio formats for ingestion and synthesis."""
    WAV = "wav"
    PCM = "pcm"
    OGG = "ogg"
    WEBM = "webm"
    MP3 = "mp3"


class VoiceCapabilitiesResponse(BaseModel):
    """Current hardware, provider, and consent capability report."""
    voice_enabled: bool = Field(..., description="Master voice subsystem enabled flag")
    microphone_enabled_by_user: bool = Field(..., description="Explicit user consent toggle for local recording")
    microphone_hardware_detected: bool = Field(..., description="Whether local audio input device is detected")
    stt_provider: Optional[str] = Field(None, description="Configured speech-to-text provider identifier")
    tts_provider: Optional[str] = Field(None, description="Configured text-to-speech provider identifier")
    tts_enabled: bool = Field(..., description="Whether spoken response synthesis is enabled")
    active_sessions_count: int = Field(..., description="Current count of active voice sessions")
    max_recording_seconds: float = Field(..., description="Upper bound recording duration")
    max_audio_mb: float = Field(..., description="Maximum audio upload limit in MB")


class VoiceSessionCreateRequest(BaseModel):
    """Request payload to initiate a new tracked voice interaction session."""
    language: Optional[str] = Field("en", max_length=10, description="Optional ISO language code")
    synthesize_response: bool = Field(default=True, description="Whether to synthesize spoken response")
    voice_name: Optional[str] = Field(None, max_length=64, description="Optional TTS voice identifier")


class VoiceSessionResponse(BaseModel):
    """Status metadata for a voice session."""
    session_id: str
    state: VoiceSessionState
    language: str
    synthesize_response: bool
    voice_name: Optional[str] = None
    transcribed_text: Optional[str] = None
    assistant_response_text: Optional[str] = None
    audio_artifact_id: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TranscriptionResult(BaseModel):
    """Result of speech-to-text transcription."""
    text: str = Field(..., description="Transcribed plain text")
    language: Optional[str] = Field(None, description="Detected or configured language code")
    provider: str = Field(..., description="Identifier of STT provider utilized")
    duration_seconds: float = Field(default=0.0, ge=0.0)
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence score if supplied by provider")
    error: Optional[str] = None


class AudioPayloadRequest(BaseModel):
    """Payload containing base64-encoded audio for clean REST JSON requests without multipart dependencies."""
    audio_base64: str = Field(..., description="Base64-encoded audio bytes (WAV, OGG, MP3, WEBM)")
    filename: Optional[str] = Field("recording.wav", max_length=255, description="Audio filename")
    language: Optional[str] = Field("en", max_length=10, description="Language code")
    synthesize_response: bool = Field(default=True, description="Whether to synthesize spoken response")
    voice_name: Optional[str] = Field(None, max_length=64, description="Optional voice name/identifier")
    conversation_id: Optional[str] = Field(None, description="Optional conversation context ID")


class SpeechSynthesisRequest(BaseModel):
    """Payload to synthesize speech from arbitrary text."""
    text: str = Field(..., min_length=1, max_length=4000, description="Text string to speak")
    voice: Optional[str] = Field(None, max_length=64, description="Optional voice name/identifier")
    language: Optional[str] = Field("en", max_length=10, description="Language code")


class SpeechSynthesisResult(BaseModel):
    """Result metadata for synthesized audio."""
    artifact_id: str = Field(..., description="Unique application-scoped identifier to fetch the audio")
    audio_format: str = Field(default="wav", description="Audio format")
    audio_bytes_length: int = Field(default=0, ge=0)
    provider: str = Field(..., description="Identifier of TTS provider utilized")
    duration_seconds: float = Field(default=0.0, ge=0.0)
    voice: Optional[str] = None
    language: Optional[str] = None


class VoiceInteractionResponse(BaseModel):
    """Combined outcome of a voice request containing transcription, reasoning, and speech."""
    session_id: str
    transcription: TranscriptionResult
    assistant_text: str
    spoken_audio: Optional[SpeechSynthesisResult] = None
    conversation_id: Optional[str] = None
    status: str = Field(default="success")
