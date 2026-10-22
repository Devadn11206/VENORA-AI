# VENORA AI — Security Baseline & Architecture (Phase 1, 2 & 3)

> **IMPORTANT NOTICE**:  
> VENORA AI establishes a strict local security baseline. **It is designed strictly for local execution on Windows 11 and is NOT ready for public or unauthenticated network deployment.**

---

## 1. Core Security Controls (Phase 1 Baseline)

1. **Localhost Binding by Default**:
   - The backend server defaults to binding exclusively to `127.0.0.1` (loopback).
   - It does NOT bind to `0.0.0.0` or expose open network ports to external network interfaces.

2. **Strict CORS Policy**:
   - Cross-Origin Resource Sharing (CORS) is restricted to an explicit whitelist of local development origins.
   - Wildcard `*` origins are disabled.

3. **Information Disclosure Prevention**:
   - Exception handlers intercept unhandled server errors (500) and return sanitized JSON messages.
   - Raw Python tracebacks, file paths, database connection strings, and server internals are NEVER returned to the client in HTTP responses.
   - Diagnostic endpoints return operational indicators without exposing database passwords, host paths, or environment variables.

4. **Secrets & Environment Hygiene**:
   - Centralized configuration via `pydantic-settings` loads settings from environment variables and an optional `.env` file.
   - `.env`, `.pem`, `.key`, and database files are registered in `.gitignore` to prevent credential exposure.

5. **Conservative Request Limits**:
   - A dedicated ASGI request size limiting middleware intercepts requests and rejects bodies larger than `MAX_REQUEST_SIZE_BYTES` (default: 1 MB) with `HTTP 413 Payload Too Large`.

6. **Input Validation**:
   - All client inputs are strictly validated through Pydantic v2 schemas.

---

## 2. Desktop Automation Security Controls (Phase 2 Baseline)

1. **Default-Deny Permission Service**:
   - Every desktop action is validated by `DesktopPermissionService` before execution.
   - Unrecognized action identifiers trigger `HTTP 403 Forbidden` (`PERMISSION_DENIED`).

2. **Central Emergency Stop Circuit Breaker**:
   - A global emergency stop switch (`POST /api/v1/desktop/emergency-stop?active=true`) halts and blocks all interactive mouse and keyboard actions immediately.

3. **Input Automation Safety Lock**:
   - Mouse and keyboard automation (`DESKTOP_INPUT_AUTOMATION_ENABLED`) is **disabled by default (`false`)** in configuration.

4. **Application Launch Allowlist**:
   - Applications can only be launched via approved application identifiers (`notepad`, `calc`, `explorer`, `cmd`).
   - Arbitrary paths, PowerShell scripts, `.bat` files, or shell strings are rejected.
   - Executable launching is performed via `subprocess.Popen(args, shell=False)` with argument sanitization against shell control characters.

5. **Keyboard & Text Restrictions**:
   - Keys can only be pressed if present in the explicit keyboard allowlist (`ALLOWED_KEYS`).
   - Text typing is bounded to `MAX_TYPE_TEXT_LENGTH` (default: 250 characters).

---

## 3. AI Reasoning & Structured Tool Calling Security Controls (Phase 3)

Phase 3 introduces an intelligent reasoning engine without compromising the underlying system security:

1. **Controlled Tool Registry & No Arbitrary Command Execution**:
   - The LLM can **never** execute arbitrary shell commands, PowerShell, CMD, Python scripts, or filesystem operations by hallucinating a tool name or arguments.
   - Tool names are strictly validated against registered `BaseTool` instances. Unrecognized tools are rejected with `UNKNOWN_TOOL`.
   - No `eval()`, `exec()`, or dynamic module loading is permitted.

2. **Independent Authorization & Permission Enforcement**:
   - The model has no power to grant permissions or bypass checks.
   - Before any tool handler executes, the `ToolRegistry` invokes `DesktopPermissionService.check_permission()`.
   - If an action or application is not permitted (e.g. unapproved application ID, disabled input automation, or active emergency stop), execution is denied at the registry boundary.

3. **Untrusted Tool Outputs & Prompt Injection Resistance**:
   - All tool results, process lists, and system-derived strings are treated as **untrusted data**.
   - System prompts are stored separately from conversational history with explicit instructions forbidding the LLM from obeying prompt injection strings embedded in tool outputs.

4. **Bounded Reasoning Loops (Circuit Breaker)**:
   - Tool-calling sequences are capped at `MAX_TOOL_CALL_ROUNDS` (default: 3).
   - Prevents denial-of-service or infinite looping if an LLM repeatedly proposes tool calls.

5. **Zero Credential Exposure**:
   - OpenRouter API keys and Authorization headers are never logged, stored in conversation context, or returned in diagnostic status responses (`GET /api/v1/assistant/status`).
   - Diagnostic status confirms configuration state as a boolean (`is_configured: true/false`).

6. **Offline & Graceful Degradation**:
   - If `OPENROUTER_API_KEY` is not provided, the application starts normally and returns clear, actionable error messages on AI endpoints without crashing or affecting Phase 1 / Phase 2 desktop endpoints.
