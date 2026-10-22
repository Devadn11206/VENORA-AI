"""Unified domain service orchestrating the full voice pipeline, AI assistant integration, and speech synthesis."""

import time
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.errors import (
    VoiceError,
    VoiceSessionError,
    AudioValidationError,
    AudioDeviceError,
    SpeechRecognitionError,
    SpeechSynthesisError,
)
from app.voice.schemas import (
    VoiceCapabilitiesResponse,
    VoiceSessionResponse,
    VoiceSessionState,
    TranscriptionResult,
    SpeechSynthesisResult,
    VoiceInteractionResponse,
)
from app.voice.session_manager import VoiceSessionManager, VoiceSessionRecord
from app.voice.audio_capture import AudioCaptureService
from app.voice.audio_validation import AudioValidator
from app.voice.providers import get_stt_provider, get_tts_provider, BaseSTTProvider, BaseTTSProvider
from app.ai.reasoning_service import ReasoningService
from app.ai.provider import BaseAIProvider

logger = get_logger("voice.service")


class VoiceService:
    """Core domain service for VENORA AI voice interactions."""

    def __init__(
        self,
        db: Optional[Session] = None,
        settings: Optional[Settings] = None,
        stt_provider: Optional[BaseSTTProvider] = None,
        tts_provider: Optional[BaseTTSProvider] = None,
        ai_provider: Optional[BaseAIProvider] = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.validator = AudioValidator(settings=self.settings)
        self.capture = AudioCaptureService(settings=self.settings)
        self.session_manager = VoiceSessionManager(settings=self.settings)

        self.stt = stt_provider or get_stt_provider(self.settings.VOICE_STT_PROVIDER)
        self.tts = tts_provider or get_tts_provider(self.settings.VOICE_TTS_PROVIDER)
        self.reasoning = ReasoningService(provider=ai_provider, settings=self.settings, db=db)

    def get_capabilities(self) -> VoiceCapabilitiesResponse:
        """Report hardware, consent, and provider capabilities."""
        active_sessions = len(self.session_manager.list_sessions(active_only=True))
        mic_detected = self.capture.detect_microphone()

        return VoiceCapabilitiesResponse(
            voice_enabled=self.settings.VOICE_ENABLED,
            microphone_enabled_by_user=self.settings.VOICE_MICROPHONE_ENABLED,
            microphone_hardware_detected=mic_detected,
            stt_provider=self.stt.provider_id if self.stt else None,
            tts_provider=self.tts.provider_id if self.tts else None,
            tts_enabled=self.settings.VOICE_TTS_ENABLED,
            active_sessions_count=active_sessions,
            max_recording_seconds=self.settings.VOICE_MAX_RECORDING_SECONDS,
            max_audio_mb=self.settings.VOICE_MAX_AUDIO_MB,
        )

    # -----------------------------------------------------------------
    # Speech-to-Text Pipeline
    # -----------------------------------------------------------------
    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        filename: Optional[str] = None,
        language: Optional[str] = None
    ) -> TranscriptionResult:
        """Validate audio bytes and transcribe via configured STT provider."""
        if not self.settings.VOICE_ENABLED:
            raise VoiceError("Voice interface is disabled in configuration.")

        # 1. Validate audio format, size, duration
        detected_fmt, duration = self.validator.validate_audio_bytes(audio_bytes, filename=filename)

        # 2. Transcribe via provider
        trans_res = await self.stt.transcribe(
            audio_bytes=audio_bytes,
            audio_format=detected_fmt,
            language=language or self.settings.VOICE_DEFAULT_LANGUAGE
        )
        return trans_res

    # -----------------------------------------------------------------
    # Text-to-Speech Pipeline
    # -----------------------------------------------------------------
    async def synthesize_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        language: Optional[str] = None
    ) -> SpeechSynthesisResult:
        """Synthesize text into audio and store as an authorized artifact."""
        if not self.settings.VOICE_ENABLED or not self.settings.VOICE_TTS_ENABLED:
            raise VoiceError("Speech synthesis is disabled in configuration.")

        clean_text = text.strip()
        if not clean_text:
            raise SpeechSynthesisError(self.tts.provider_id, "Cannot synthesize empty text.")

        if len(clean_text) > self.settings.VOICE_MAX_RESPONSE_CHARS:
            clean_text = clean_text[:self.settings.VOICE_MAX_RESPONSE_CHARS]

        start_time = time.time()
        audio_bytes = await self.tts.synthesize(
            text=clean_text,
            voice=voice,
            language=language or self.settings.VOICE_DEFAULT_LANGUAGE
        )

        duration = time.time() - start_time
        # Save audio artifact
        artifact_id = self.validator.save_temp_artifact(audio_bytes, audio_format="wav")

        return SpeechSynthesisResult(
            artifact_id=artifact_id,
            audio_format="wav",
            audio_bytes_length=len(audio_bytes),
            provider=self.tts.provider_id,
            duration_seconds=round(duration, 3),
            voice=voice,
            language=language or self.settings.VOICE_DEFAULT_LANGUAGE
        )

    # -----------------------------------------------------------------
    # Full Voice Interaction Loop (Transcribe -> Assistant -> Synthesize)
    # -----------------------------------------------------------------
    async def process_voice_interaction(
        self,
        audio_bytes: bytes,
        session_id: Optional[str] = None,
        synthesize_response: bool = True,
        voice_name: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> VoiceInteractionResponse:
        """Full voice interaction pipeline reusing Phase 3 Reasoning & Phase 7 Memory."""
        if not self.settings.VOICE_ENABLED:
            raise VoiceError("Voice interface is disabled in configuration.")

        # 1. Resolve or create tracked session
        session: VoiceSessionRecord
        if session_id:
            s = self.session_manager.get_session(session_id)
            if not s:
                raise VoiceSessionError(f"Voice session '{session_id}' not found.", session_id=session_id)
            session = s
        else:
            session = self.session_manager.create_session(
                synthesize_response=synthesize_response,
                voice_name=voice_name
            )

        try:
            # 2. Transcribe
            session.transition_to(VoiceSessionState.TRANSCRIBING)
            trans_result = await self.transcribe_audio(audio_bytes)
            session.transcribed_text = trans_result.text

            # 3. Process transcribed query through the existing AI Reasoning service
            session.transition_to(VoiceSessionState.PROCESSING)
            assistant_resp = await self.reasoning.chat(
                message=trans_result.text,
                conversation_id=conversation_id
            )
            session.assistant_response_text = assistant_resp.message

            # 4. Optional Speech Synthesis
            synth_result = None
            if session.synthesize_response and self.settings.VOICE_TTS_ENABLED:
                try:
                    session.transition_to(VoiceSessionState.SYNTHESIZING)
                    synth_result = await self.synthesize_speech(
                        text=assistant_resp.message,
                        voice=session.voice_name,
                        language=session.language
                    )
                    session.audio_artifact_id = synth_result.artifact_id
                except Exception as tts_err:
                    logger.warning(f"Speech synthesis failed; preserving text response: {tts_err}")

            session.transition_to(VoiceSessionState.COMPLETED)

            return VoiceInteractionResponse(
                session_id=session.session_id,
                transcription=trans_result,
                assistant_text=assistant_resp.message,
                spoken_audio=synth_result,
                conversation_id=assistant_resp.conversation_id,
                status="success"
            )

        except Exception as exc:
            logger.error(f"Voice interaction pipeline failed for session '{session.session_id}': {exc}")
            try:
                session.transition_to(VoiceSessionState.FAILED, error_message=str(exc))
            except Exception:
                pass
            raise
