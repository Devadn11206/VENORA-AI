import base64
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.core.config import get_settings, Settings
from app.core.errors import (
    VoiceError,
    VoiceSessionError,
    AudioValidationError,
    AudioDeviceError,
    SpeechRecognitionError,
    SpeechSynthesisError,
)
from app.desktop.permissions import DesktopPermissionService
from app.voice.schemas import (
    AudioPayloadRequest,
    VoiceCapabilitiesResponse,
    VoiceSessionCreateRequest,
    VoiceSessionResponse,
    TranscriptionResult,
    SpeechSynthesisRequest,
    SpeechSynthesisResult,
    VoiceInteractionResponse,
)
from app.voice.service import VoiceService
from app.voice.session_manager import VoiceSessionManager

router = APIRouter(prefix="/voice", tags=["Voice Interface"])

_GLOBAL_VOICE_SESSION_MANAGER: Optional[VoiceSessionManager] = None


def get_global_session_manager(settings: Settings) -> VoiceSessionManager:
    global _GLOBAL_VOICE_SESSION_MANAGER
    if _GLOBAL_VOICE_SESSION_MANAGER is None:
        _GLOBAL_VOICE_SESSION_MANAGER = VoiceSessionManager(settings=settings)
    return _GLOBAL_VOICE_SESSION_MANAGER


def get_voice_service(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> VoiceService:
    """Dependency provider for VoiceService."""
    svc = VoiceService(db=db, settings=settings)
    svc.session_manager = get_global_session_manager(settings)
    return svc


def verify_voice_permission(action: str, settings: Settings = Depends(get_settings)) -> None:
    """Enforce default-deny action authorization for voice endpoints."""
    perm_service = DesktopPermissionService(settings=settings)
    perm_service.check_permission(action)


# -----------------------------------------------------------------------------
# Status & Capabilities
# -----------------------------------------------------------------------------
@router.get("/status", response_model=VoiceCapabilitiesResponse, summary="Voice Subsystem Status")
def get_voice_status(
    service: VoiceService = Depends(get_voice_service),
    settings: Settings = Depends(get_settings),
) -> VoiceCapabilitiesResponse:
    """Return runtime capability, consent, and hardware detection status."""
    verify_voice_permission("voice.capabilities.read", settings=settings)
    return service.get_capabilities()


@router.get("/capabilities", response_model=VoiceCapabilitiesResponse, summary="Voice Capabilities")
def get_voice_capabilities(
    service: VoiceService = Depends(get_voice_service),
    settings: Settings = Depends(get_settings),
) -> VoiceCapabilitiesResponse:
    """Alias for status reporting."""
    verify_voice_permission("voice.capabilities.read", settings=settings)
    return service.get_capabilities()


# -----------------------------------------------------------------------------
# Voice Sessions Lifecycle
# -----------------------------------------------------------------------------
@router.post("/sessions", response_model=VoiceSessionResponse, status_code=status.HTTP_201_CREATED, summary="Create Voice Session")
def create_voice_session(
    payload: VoiceSessionCreateRequest,
    service: VoiceService = Depends(get_voice_service),
    settings: Settings = Depends(get_settings),
) -> VoiceSessionResponse:
    """Initiate a new tracked voice interaction session."""
    verify_voice_permission("voice.session.create", settings=settings)
    try:
        session = service.session_manager.create_session(
            language=payload.language,
            synthesize_response=payload.synthesize_response,
            voice_name=payload.voice_name
        )
        return VoiceSessionResponse(
            session_id=session.session_id,
            state=session.state,
            language=session.language,
            synthesize_response=session.synthesize_response,
            voice_name=session.voice_name,
            transcribed_text=session.transcribed_text,
            assistant_response_text=session.assistant_response_text,
            audio_artifact_id=session.audio_artifact_id,
            error_message=session.error_message,
            created_at=session.created_at,
            updated_at=session.updated_at,
            completed_at=session.completed_at,
        )
    except VoiceSessionError as vse:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(vse))


@router.get("/sessions/{session_id}", response_model=VoiceSessionResponse, summary="Get Voice Session")
def get_voice_session(
    session_id: str,
    service: VoiceService = Depends(get_voice_service),
    settings: Settings = Depends(get_settings),
) -> VoiceSessionResponse:
    """Inspect state and metadata of a tracked voice session."""
    verify_voice_permission("voice.capabilities.read", settings=settings)
    session = service.session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Voice session '{session_id}' not found.")
    return VoiceSessionResponse(
        session_id=session.session_id,
        state=session.state,
        language=session.language,
        synthesize_response=session.synthesize_response,
        voice_name=session.voice_name,
        transcribed_text=session.transcribed_text,
        assistant_response_text=session.assistant_response_text,
        audio_artifact_id=session.audio_artifact_id,
        error_message=session.error_message,
        created_at=session.created_at,
        updated_at=session.updated_at,
        completed_at=session.completed_at,
    )


@router.post("/sessions/{session_id}/cancel", response_model=VoiceSessionResponse, summary="Cancel Voice Session")
def cancel_voice_session(
    session_id: str,
    service: VoiceService = Depends(get_voice_service),
    settings: Settings = Depends(get_settings),
) -> VoiceSessionResponse:
    """Explicitly cancel an active voice session."""
    verify_voice_permission("voice.session.cancel", settings=settings)
    try:
        service.capture.cancel_capture()
        session = service.session_manager.cancel_session(session_id)
        return VoiceSessionResponse(
            session_id=session.session_id,
            state=session.state,
            language=session.language,
            synthesize_response=session.synthesize_response,
            voice_name=session.voice_name,
            transcribed_text=session.transcribed_text,
            assistant_response_text=session.assistant_response_text,
            audio_artifact_id=session.audio_artifact_id,
            error_message=session.error_message,
            created_at=session.created_at,
            updated_at=session.updated_at,
            completed_at=session.completed_at,
        )
    except VoiceSessionError as vse:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(vse))


# -----------------------------------------------------------------------------
# Microphone Capture Endpoints
# -----------------------------------------------------------------------------
@router.post("/sessions/{session_id}/capture/start", summary="Start Audio Capture")
async def start_audio_capture(
    session_id: str,
    service: VoiceService = Depends(get_voice_service),
    settings: Settings = Depends(get_settings),
):
    """Start recording audio from microphone for the session."""
    verify_voice_permission("voice.capture.start", settings=settings)
    session = service.session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session '{session_id}' not found.")

    try:
        session.transition_to(VoiceSessionState.CAPTURING)
        await service.capture.start_capture(session_id)
        return {"session_id": session_id, "status": "capturing"}
    except (AudioDeviceError, VoiceSessionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/sessions/{session_id}/capture/stop", response_model=VoiceInteractionResponse, summary="Stop Capture and Process")
async def stop_audio_capture(
    session_id: str,
    conversation_id: Optional[str] = Query(None),
    service: VoiceService = Depends(get_voice_service),
    settings: Settings = Depends(get_settings),
) -> VoiceInteractionResponse:
    """Stop recording audio, transcribe, run assistant reasoning, and synthesize response."""
    verify_voice_permission("voice.capture.stop", settings=settings)
    session = service.session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session '{session_id}' not found.")

    try:
        audio_bytes = await service.capture.stop_capture(session_id)
        return await service.process_voice_interaction(
            audio_bytes=audio_bytes,
            session_id=session_id,
            synthesize_response=session.synthesize_response,
            voice_name=session.voice_name,
            conversation_id=conversation_id
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# -----------------------------------------------------------------------------
# Direct Audio Processing Endpoints
# -----------------------------------------------------------------------------
@router.post("/transcribe", response_model=TranscriptionResult, summary="Transcribe Audio Payload")
async def transcribe_audio(
    payload: AudioPayloadRequest,
    service: VoiceService = Depends(get_voice_service),
    settings: Settings = Depends(get_settings),
) -> TranscriptionResult:
    """Transcribe base64-encoded audio without invoking the reasoning engine."""
    verify_voice_permission("voice.transcribe", settings=settings)
    try:
        audio_bytes = base64.b64decode(payload.audio_base64)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid base64 audio payload.")

    try:
        return await service.transcribe_audio(
            audio_bytes=audio_bytes,
            filename=payload.filename,
            language=payload.language
        )
    except AudioValidationError as ave:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ave))
    except SpeechRecognitionError as sre:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(sre))


@router.post("/respond", response_model=VoiceInteractionResponse, summary="Process Audio Turn")
async def process_voice_respond(
    payload: AudioPayloadRequest,
    service: VoiceService = Depends(get_voice_service),
    settings: Settings = Depends(get_settings),
) -> VoiceInteractionResponse:
    """Process base64-encoded audio through STT, AI Assistant Reasoning & Memory, and optional TTS."""
    verify_voice_permission("voice.respond", settings=settings)
    try:
        audio_bytes = base64.b64decode(payload.audio_base64)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid base64 audio payload.")

    try:
        return await service.process_voice_interaction(
            audio_bytes=audio_bytes,
            synthesize_response=payload.synthesize_response,
            voice_name=payload.voice_name,
            conversation_id=payload.conversation_id,
        )
    except AudioValidationError as ave:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ave))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/synthesize", response_model=SpeechSynthesisResult, summary="Synthesize Text to Speech")
async def synthesize_text(
    payload: SpeechSynthesisRequest,
    service: VoiceService = Depends(get_voice_service),
    settings: Settings = Depends(get_settings),
) -> SpeechSynthesisResult:
    """Synthesize text into a downloadable audio artifact."""
    verify_voice_permission("voice.synthesize", settings=settings)
    try:
        return await service.synthesize_speech(
            text=payload.text,
            voice=payload.voice,
            language=payload.language
        )
    except SpeechSynthesisError as sse:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(sse))


@router.get("/audio/{artifact_id}", summary="Download Synthesized Audio Artifact")
def get_audio_artifact(
    artifact_id: str,
    service: VoiceService = Depends(get_voice_service),
    settings: Settings = Depends(get_settings),
):
    """Safely stream an authorized audio artifact by ID."""
    verify_voice_permission("voice.audio.read", settings=settings)
    path = service.validator.get_artifact_path(artifact_id)
    if not path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Audio artifact '{artifact_id}' not found.")

    return FileResponse(
        path=path,
        media_type="audio/wav",
        filename=f"{artifact_id}.wav"
    )
