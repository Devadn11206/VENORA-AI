# VENORA AI — Security Baseline & Architecture (Phase 1 & Phase 2)

> **IMPORTANT NOTICE**:  
> VENORA AI establishes a strict local security baseline. **It is designed strictly for local execution on Windows 11 and is NOT ready for public or unauthenticated network deployment.**

---

## 1. Core Security Controls (Phase 1 & Phase 2 Implemented)

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
   - Zero external API credentials required for local operation.

5. **Conservative Request Limits**:
   - A dedicated ASGI request size limiting middleware intercepts requests and rejects bodies larger than `MAX_REQUEST_SIZE_BYTES` (default: 1 MB) with `HTTP 413 Payload Too Large` to mitigate memory exhaustion.

6. **Input Validation**:
   - All client inputs are strictly validated through Pydantic v2 schemas.
   - Task titles, priority values, and status transitions enforce boundaries before database write operations.

---

## 2. Desktop Automation Security Controls (Phase 2 Additions)

Phase 2 introduces automated desktop interaction capabilities guarded by defense-in-depth safety boundaries:

1. **Default-Deny Permission Service**:
   - Every desktop action is validated by `DesktopPermissionService` before execution.
   - Unrecognized action identifiers trigger `HTTP 403 Forbidden` (`PERMISSION_DENIED`).

2. **Central Emergency Stop Circuit Breaker**:
   - A global emergency stop switch (`POST /api/v1/desktop/emergency-stop?active=true`) halts and blocks all interactive mouse and keyboard actions immediately.
   - Resetting the stop state requires an explicit local API call (`active=false`).

3. **Input Automation Safety Lock**:
   - Mouse and keyboard automation (`DESKTOP_INPUT_AUTOMATION_ENABLED`) is **disabled by default (`false`)** in configuration.
   - Even if requested via the API, mouse movements, clicks, typing, and keypresses are rejected until the developer explicitly toggles the configuration switch.

4. **Application Launch Allowlist**:
   - Applications can only be launched via approved application identifiers (`notepad`, `calc`, `explorer`, `cmd`).
   - Arbitrary paths, PowerShell scripts, `.bat` files, or shell strings are rejected.
   - Executable launching is performed via `subprocess.Popen(args, shell=False)` with argument sanitization against shell control characters (`&`, `|`, `;`, `>`, etc.).

5. **Keyboard & Text Restrictions**:
   - Keys can only be pressed if present in the explicit keyboard allowlist (`ALLOWED_KEYS`).
   - Text typing is bounded to `MAX_TYPE_TEXT_LENGTH` (default: 250 characters).

6. **PyAutoGUI FailSafe**:
   - Fail-safe mode is permanently enabled (`pyautogui.FAILSAFE = True`). Slamming the mouse pointer into any screen corner immediately halts automation.

7. **Task-Scoped Screenshot Privacy**:
   - Screenshots are saved using unguessable tokens (`snap_<timestamp>_<hex16>.png`) in `data/screenshots/`.
   - Access to screenshots enforces strict directory containment validation to eliminate path traversal attacks (`../`).
   - Screenshot files are never uploaded to third-party endpoints.

8. **Read-Only Process Inspection**:
   - Process inspection via `psutil` sanitizes output: command lines, environment variables, authentication tokens, and credentials are omitted.

---

## 3. Current Limitations & Assumptions

- **Local Machine Boundary**: Assumes that anyone with access to `http://127.0.0.1:8000` is the authorized owner of the machine.
- **Unencrypted Transport**: Communication is local HTTP over loopback.
- **No Multi-Tenancy**: The desktop environment belongs to the logged-in OS user.

---

## 4. Planned Security Milestones for Future Phases

### Tool Permission Architecture (Independent of AI Prompts)
A fundamental tenet of VENORA AI is that **AI reasoning models must never be the sole arbiters of security**:
- Future desktop automation tools will feature **deterministic OS-level policy gates**.
- An AI prompt or LLM output requesting a sensitive action (e.g., deleting files, executing system commands, accessing credential vaults) will trigger an explicit interactive approval prompt (`awaiting_approval` status) or be blocked by a hardcoded sandbox policy.
- System tool permissions are enforced in Python backend code independently of what the LLM hallucinates or suggests.
