# VENORA AI — Voice Interface Subsystem

## Overview

The **Voice Interface Subsystem** enables speech recognition, audio validation, conversational AI integration, and spoken responses for VENORA AI on Windows 11.

It adheres to a security-first principle:
- **No Background Listening**: Microphone recording is never continuous and requires explicit user consent (`VOICE_MICROPHONE_ENABLED=true`).
- **Reuse of Reasoning & Memory**: Voice requests do not create a separate LLM pipeline. They transcribe audio, validate input, and route into the existing Phase 3 `ReasoningService` and Phase 7 `MemoryService`.
- **Bounded Audio Lifecycle**: Audio uploads and syntheses are strictly validated (WAV, OGG, MP3, WEBM), bounded in duration and size, and temporary artifacts are isolated with automatic expiration.

---

## Architecture Flow

```
                      +-----------------------------+
                      | User Voice Input / Upload   |
                      +-----------------------------+
                                     |
                                     v
                      +-----------------------------+
                      |       AudioValidator        |
                      |  - Format magic bytes       |
                      |  - Duration & MB bounds     |
                      |  - Path traversal checks    |
                      +-----------------------------+
                                     |
                                     v
                      +-----------------------------+
                      |       BaseSTTProvider       |
                      |  (Mock / Remote / Windows)  |
                      +-----------------------------+
                                     |
                                     v
                      +-----------------------------+
                      |     Transcribed Request     |
                      +-----------------------------+
                                     |
                                     v
                      +-----------------------------+
                      |  ReasoningService (Phase 3) |
                      |    & MemoryService (Phase 7)|
                      +-----------------------------+
                                     |
                                     v
                      +-----------------------------+
                      |   Assistant Response Text   |
                      +-----------------------------+
                                     |
                                     v
                      +-----------------------------+
                      |       BaseTTSProvider       |
                      |  (Mock / System / Remote)   |
                      +-----------------------------+
                                     |
                                     v
                      +-----------------------------+
                      |  Audio Artifact (Download)  |
                      +-----------------------------+
```

---

## Voice Interaction Modes

1. **Mode A: Transcribe and Respond**:
   - Audio is received or recorded.
   - Speech-to-Text transcribes the query.
   - The query is executed through the standard assistant reasoning loop.
   - Returns the transcribed text and the generated assistant response.
2. **Mode B: Voice Response (TTS Enabled)**:
   - Performs Mode A.
   - Synthesizes the assistant's response into an audio artifact (WAV/MP3).
   - Returns an authorized artifact ID (`/api/v1/voice/audio/{artifact_id}`) for streaming.
   - If TTS fails, the text response is preserved and reported without failing the entire interaction.

---

## Session Lifecycle State Machine

Voice sessions follow a strict finite state machine:
- `IDLE`: Session created and awaiting audio capture or input.
- `CAPTURING`: Actively recording from the local microphone.
- `TRANSCRIBING`: Audio is being processed by STT.
- `PROCESSING`: Assistant reasoning and memory recall in progress.
- `SYNTHESIZING`: Assistant response is being synthesized to speech.
- `COMPLETED`: Turn finished successfully.
- `CANCELLED`: Interrupted by user cancellation or emergency stop.
- `FAILED`: An unrecoverable validation, hardware, or provider error occurred.

---

## REST Endpoints

Mounted under `/api/v1/voice`:

| Endpoint | Method | Required Permission | Description |
|----------|--------|---------------------|-------------|
| `/status` | GET | `voice.capabilities.read` | Report microphone consent, hardware detection, providers |
| `/capabilities` | GET | `voice.capabilities.read` | Alias for capabilities status |
| `/sessions` | POST | `voice.session.create` | Create a new tracked voice interaction session |
| `/sessions/{id}` | GET | `voice.capabilities.read` | Inspect state of a voice session |
| `/sessions/{id}/cancel` | POST | `voice.session.cancel` | Cancel an in-flight session |
| `/sessions/{id}/capture/start` | POST | `voice.capture.start` | Start local microphone capture |
| `/sessions/{id}/capture/stop` | POST | `voice.capture.stop` | Stop capture, transcribe, and process turn |
| `/transcribe` | POST | `voice.transcribe` | Transcribe base64 audio without assistant execution |
| `/respond` | POST | `voice.respond` | Full voice turn (Transcribe -> Assistant -> Synthesize) |
| `/synthesize` | POST | `voice.synthesize` | Synthesize arbitrary text into speech audio artifact |
| `/audio/{artifact_id}` | GET | `voice.audio.read` | Safely download/stream synthesized audio artifact |
