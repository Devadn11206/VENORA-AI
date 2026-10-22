# VENORA AI — Voice Privacy & Audio Security Controls

## Privacy Guarantees

Voice is a personal and sensitive input medium. VENORA AI enforces strict privacy boundaries on all voice interactions.

---

### 1. No Always-On Microphone Recording
- **No Background Audio Collection**: VENORA AI does not listen continuously in the background or stream ambient audio.
- **Explicit Recording**: Microphone capture begins only on an explicit authorized API call (`POST /api/v1/voice/sessions/{id}/capture/start`) and halts upon stop or timeout.
- **Default-Off Consent**: `VOICE_MICROPHONE_ENABLED=false` by default in configuration.

---

### 2. Audio Artifact Containment & Expiration
- **Safe Directory Isolation**: Audio files are stored strictly inside the configured `VOICE_AUDIO_DIR` (`./data/audio`).
- **Path Traversal Protection**: Audio download endpoints resolve only valid artifact UUIDs (`/api/v1/voice/audio/{artifact_id}`) and forbid arbitrary file paths or directory traversal (`../../`).
- **Automatic Expiration**: Audio artifacts expire after `VOICE_AUDIO_RETENTION_MINUTES` (default 30 minutes) and are automatically pruned.

---

### 3. Voice Identity & Authorization
- **Voice Does Not Grant Privileges**: Spoken instructions cannot bypass permissions, change system settings, or execute unapproved actions.
- **Sensitive Operations Require Approval**: Consequential or destructive desktop actions (e.g. process termination, unapproved app launch, file mutation) triggered by voice requests remain subject to the existing approval workflow.
- **Prompt Injection Defense**: Transcribed text is treated as untrusted user input, preserving safety guards and prompt-injection barriers established in Phase 3 and Phase 7.
