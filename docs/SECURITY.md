# VENORA AI — Security Baseline & Architecture (Phase 1)

> **IMPORTANT NOTICE**:  
> Phase 1 of VENORA AI establishes an initial local security baseline. **It is designed strictly for local development on Windows 11 and is NOT ready for public or unauthenticated network deployment.**

---

## 1. Current Security Controls (Phase 1 Implemented)

1. **Localhost Binding by Default**:
   - The backend server defaults to binding exclusively to `127.0.0.1` (loopback).
   - It does NOT bind to `0.0.0.0` or expose open network ports to external network interfaces.

2. **Strict CORS Policy**:
   - Cross-Origin Resource Sharing (CORS) is restricted to an explicit whitelist of local development origins (e.g., `http://localhost:3000`, `http://127.0.0.1:3000`, `http://localhost:5173`).
   - Wildcard `*` origins are disabled.

3. **Information Disclosure Prevention**:
   - Exception handlers intercept unhandled server errors (500) and return sanitized JSON messages (`{"detail": "An unexpected internal server error occurred."}`).
   - Raw Python tracebacks, file paths, database connection strings, and server internals are NEVER returned to the client in HTTP responses.
   - Diagnostic endpoints (`/health` and `/health/ready`) return operational indicators without exposing database passwords, host paths, or environment variables.

4. **Secrets & Environment Hygiene**:
   - Centralized configuration via `pydantic-settings` loads settings from environment variables and an optional `.env` file.
   - `.env`, `.pem`, `.key`, and database files are registered in `.gitignore` to prevent credential exposure.
   - Phase 1 does not require any paid external API keys to start, test, or operate.

5. **Conservative Request Limits**:
   - A dedicated ASGI request size limiting middleware intercepts requests and rejects bodies larger than `MAX_REQUEST_SIZE_BYTES` (default: 1 MB) with `HTTP 413 Payload Too Large` to mitigate memory exhaustion.

6. **Input Validation**:
   - All client inputs are strictly validated through Pydantic v2 schemas.
   - Task titles, priority values, and status transitions enforce boundaries before database write operations.

---

## 2. Current Limitations & Assumptions

- **No Authentication / Authorization**: Phase 1 assumes that anyone with access to `http://127.0.0.1:8000` is the trusted local system owner. There are currently no user accounts, passwords, JWT tokens, or API keys guarding the HTTP endpoints.
- **Unencrypted Transport (HTTP)**: Because communication is strictly local (`127.0.0.1`), TLS/HTTPS is not configured at this stage.
- **Single Tenant**: The database schema and session tables do not yet segment multi-tenant users.

---

## 3. Risks Before Remote Access (Telegram / External Web)

Before enabling remote access (such as a Telegram Bot, web tunnel, or mobile dashboard), the following risks MUST be mitigated:

1. **Unauthorized Command Execution**: An exposed local port without authentication could allow unauthorized parties on the local network to trigger tasks.
2. **Eavesdropping on Local Network**: If bound to non-loopback addresses (`0.0.0.0`), unencrypted traffic could expose task data to neighboring devices.
3. **Session Hijacking**: Without cryptographic tokens (e.g., HMAC-signed tokens or OAuth2/JWT), requests cannot be validated as originating from the authorized user.

---

## 4. Planned Security Milestones for Future Phases

### Authentication & Authorization
- **API Token Authentication**: Bearer token authentication required on all non-public endpoints.
- **Telegram Bot User Allowlist**: Strict Telegram user ID whitelist so only the owner can issue commands to the agent.
- **Role-Based Access**: Separation of read-only observation roles and administrative execution roles.

### Tool Permission Architecture (Independent of AI Prompts)
A fundamental tenet of VENORA AI is that **AI reasoning models must never be the sole arbiters of security**:
- Future desktop automation tools (mouse control, keyboard typing, file system manipulation, shell command execution) will feature **deterministic OS-level policy gates**.
- An AI prompt or LLM output requesting a sensitive action (e.g., deleting files, executing system commands, accessing credential vaults) will trigger an explicit interactive approval prompt (`awaiting_approval` status) or be blocked by a hardcoded sandbox policy.
- System tool permissions will be enforced in Python backend code independently of what the LLM hallucinates or suggests.
