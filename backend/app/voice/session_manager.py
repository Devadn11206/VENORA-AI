"""Voice session lifecycle management, state machine validation, and concurrent session tracking."""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List

from app.core.config import Settings, get_settings
from app.core.errors import VoiceSessionError
from app.core.logging import get_logger
from app.voice.schemas import VoiceSessionState, VoiceSessionResponse

logger = get_logger("voice.session_manager")


class VoiceSessionRecord:
    """In-memory tracked voice interaction session state."""

    def __init__(
        self,
        session_id: str,
        language: str = "en",
        synthesize_response: bool = True,
        voice_name: Optional[str] = None
    ) -> None:
        self.session_id = session_id
        self.state: VoiceSessionState = VoiceSessionState.IDLE
        self.language: str = language
        self.synthesize_response: bool = synthesize_response
        self.voice_name: Optional[str] = voice_name
        self.transcribed_text: Optional[str] = None
        self.assistant_response_text: Optional[str] = None
        self.audio_artifact_id: Optional[str] = None
        self.error_message: Optional[str] = None
        now = datetime.now(timezone.utc)
        self.created_at: datetime = now
        self.updated_at: datetime = now
        self.completed_at: Optional[datetime] = None

    def transition_to(self, new_state: VoiceSessionState, error_message: Optional[str] = None) -> None:
        """Validate state transition rules and update state."""
        # Terminal states cannot transition further
        if self.state in (VoiceSessionState.COMPLETED, VoiceSessionState.CANCELLED, VoiceSessionState.FAILED):
            raise VoiceSessionError(
                f"Cannot transition voice session '{self.session_id}' from terminal state '{self.state.value}' to '{new_state.value}'.",
                session_id=self.session_id
            )

        # Allowed state transitions
        valid_transitions = {
            VoiceSessionState.IDLE: {
                VoiceSessionState.CAPTURING,
                VoiceSessionState.TRANSCRIBING,
                VoiceSessionState.PROCESSING,
                VoiceSessionState.CANCELLED,
                VoiceSessionState.FAILED
            },
            VoiceSessionState.CAPTURING: {
                VoiceSessionState.TRANSCRIBING,
                VoiceSessionState.CANCELLED,
                VoiceSessionState.FAILED
            },
            VoiceSessionState.TRANSCRIBING: {
                VoiceSessionState.PROCESSING,
                VoiceSessionState.COMPLETED,
                VoiceSessionState.CANCELLED,
                VoiceSessionState.FAILED
            },
            VoiceSessionState.PROCESSING: {
                VoiceSessionState.SYNTHESIZING,
                VoiceSessionState.COMPLETED,
                VoiceSessionState.CANCELLED,
                VoiceSessionState.FAILED
            },
            VoiceSessionState.SYNTHESIZING: {
                VoiceSessionState.COMPLETED,
                VoiceSessionState.CANCELLED,
                VoiceSessionState.FAILED
            },
        }

        allowed = valid_transitions.get(self.state, set())
        if new_state not in allowed:
            raise VoiceSessionError(
                f"Invalid state transition for voice session '{self.session_id}': cannot move from '{self.state.value}' to '{new_state.value}'.",
                session_id=self.session_id
            )

        self.state = new_state
        now = datetime.now(timezone.utc)
        self.updated_at = now
        if error_message:
            self.error_message = error_message
        if new_state in (VoiceSessionState.COMPLETED, VoiceSessionState.CANCELLED, VoiceSessionState.FAILED):
            self.completed_at = now

        logger.info(f"Voice session '{self.session_id}' transitioned to state '{new_state.value}'.")


class VoiceSessionManager:
    """Manages tracking, lifecycle bounds, and cleanup for voice interaction sessions."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self._sessions: Dict[str, VoiceSessionRecord] = {}

    def create_session(
        self,
        language: Optional[str] = None,
        synthesize_response: bool = True,
        voice_name: Optional[str] = None
    ) -> VoiceSessionRecord:
        """Create a new session, enforcing concurrent session bounds."""
        self.cleanup_expired_sessions()

        active_count = sum(
            1 for s in self._sessions.values()
            if s.state not in (VoiceSessionState.COMPLETED, VoiceSessionState.CANCELLED, VoiceSessionState.FAILED)
        )

        if active_count >= self.settings.VOICE_MAX_CONCURRENT_SESSIONS:
            raise VoiceSessionError(
                f"Maximum concurrent active voice sessions ({self.settings.VOICE_MAX_CONCURRENT_SESSIONS}) reached. Complete or cancel active session first."
            )

        session_id = f"vsession_{uuid.uuid4().hex[:12]}"
        record = VoiceSessionRecord(
            session_id=session_id,
            language=language or self.settings.VOICE_DEFAULT_LANGUAGE,
            synthesize_response=synthesize_response,
            voice_name=voice_name
        )
        self._sessions[session_id] = record
        logger.info(f"Created voice session '{session_id}'.")
        return record

    def get_session(self, session_id: str) -> Optional[VoiceSessionRecord]:
        """Fetch session record by ID."""
        return self._sessions.get(session_id)

    def cancel_session(self, session_id: str) -> VoiceSessionRecord:
        """Cancel an in-flight or idle voice session."""
        session = self.get_session(session_id)
        if not session:
            raise VoiceSessionError(f"Voice session '{session_id}' not found.", session_id=session_id)

        session.transition_to(VoiceSessionState.CANCELLED)
        return session

    def list_sessions(self, active_only: bool = False) -> List[VoiceSessionRecord]:
        """List tracked sessions."""
        self.cleanup_expired_sessions()
        if active_only:
            return [
                s for s in self._sessions.values()
                if s.state not in (VoiceSessionState.COMPLETED, VoiceSessionState.CANCELLED, VoiceSessionState.FAILED)
            ]
        return list(self._sessions.values())

    def cleanup_expired_sessions(self) -> int:
        """Expire stale active sessions that exceeded VOICE_SESSION_TIMEOUT_SECONDS."""
        now = datetime.now(timezone.utc)
        timeout = timedelta(seconds=self.settings.VOICE_SESSION_TIMEOUT_SECONDS)
        expired = 0

        for session in list(self._sessions.values()):
            if session.state not in (VoiceSessionState.COMPLETED, VoiceSessionState.CANCELLED, VoiceSessionState.FAILED):
                if now - session.updated_at > timeout:
                    try:
                        session.transition_to(VoiceSessionState.FAILED, error_message="Session timed out due to inactivity.")
                        expired += 1
                    except Exception:
                        pass
        return expired
