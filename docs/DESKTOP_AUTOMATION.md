# VENORA AI — Desktop Automation Subsystem (Phase 2)

> **Virtual Environment for Neural Operations, Reasoning & Assistance**  
> *Tagline: Think. Execute. Evolve.*

---

## 1. Overview & Architecture

Phase 2 introduces the **Desktop Automation Subsystem** to VENORA AI. Designed to run locally on Windows 11, it provides controlled application launching, read-only process inspection, verified screenshot capturing, window discovery, and safe mouse/keyboard input execution.

```
+-------------------------------------------------------------------------------+
|                                Clients                                        |
|         (CLI / API / Future Autonomous Reasoning Engine in Phase 3)           |
+-------------------------------------------------------------------------------+
                                       |
                                       v
+-------------------------------------------------------------------------------+
|                       API Layer: /api/v1/desktop                              |
|   /capabilities  /applications  /processes  /screenshots  /actions  /emergency-stop
+-------------------------------------------------------------------------------+
                                       |
                                       v
+-------------------------------------------------------------------------------+
|                     Desktop Permission & Safety Gate                          |
|   - Default-Deny Policy                                                       |
|   - Emergency Stop Circuit Breaker                                            |
|   - Whitelist Enforcement (app_id allowlist & approved keyboard keys)         |
|   - Input Automation Safety Lock (DESKTOP_INPUT_AUTOMATION_ENABLED=false)     |
+-------------------------------------------------------------------------------+
                                       |
                                       v
+-------------------------------------------------------------------------------+
|                      Core Desktop Services Subsystem                          |
|  +-----------------------+  +-----------------------+  +-------------------+  |
|  | ApplicationLauncher   |  |   ProcessInspector    |  | ScreenshotService |  |
|  | Subprocess execution  |  | Read-only psutil poll |  | Pillow grab & verify |
|  +-----------------------+  +-----------------------+  +-------------------+  |
|  |  MouseKeyboardService |  |  UIAutomationService  |  |  OutcomeVerifier  |  |
|  | PyAutoGUI + FailSafe  |  | Win32 Window Enum     |  | State Validation  |  |
|  +-----------------------+  +-----------------------+  +-------------------+  |
+-------------------------------------------------------------------------------+
                                       |
                                       v
+-------------------------------------------------------------------------------+
|                     Persistence & Audit Logging Layer                         |
|   - ExecutionLog DB records (task_id, event_type, timestamps)                 |
|   - Local Task-Scoped Screenshots Storage: data/screenshots/                  |
|   - Rotating Application Logs: logs/venora.log                                |
+-------------------------------------------------------------------------------+
```

---

## 2. Supported Operations

| Action Type | Operation | Description |
| :--- | :--- | :--- |
| `launch_application` | Application Launch | Launches an explicitly whitelisted application (`notepad`, `calc`, `explorer`, `cmd`). |
| `inspect_process` | Process Inspection | Retrieves process status, CPU, memory, and creation time by PID without leaking secrets. |
| `list_processes` | Process Listing | Returns bounded list of running system processes. |
| `capture_screenshot` | Screenshot Capture | Captures on-demand task-scoped screenshot and verifies file integrity on disk. |
| `move_mouse` | Mouse Movement | Moves cursor to validated screen coordinates with bounds checking. |
| `click_mouse` | Mouse Click | Dispatches mouse clicks (left/right/middle) with validated parameters. |
| `type_text` | Text Typing | Types plain text up to configurable maximum character length limit. |
| `press_key` | Key Press | Presses an approved key from the strict keyboard allowlist. |
| `emergency_stop` | Safety Interruption | Instantly halts and blocks all interactive desktop actions. |
| `reset_emergency_stop`| Safety Reset | Disengages emergency stop state via local command. |

---

## 3. Configuration & Safety Controls

Configuration fields added to `.env` / [`app/core/config.py`](file:///c:/Users/ddnan/Venora%20AI/backend/app/core/config.py):

```env
# Phase 2 Desktop Controls
DESKTOP_AUTOMATION_ENABLED=true
DESKTOP_INPUT_AUTOMATION_ENABLED=false
DESKTOP_EMERGENCY_STOP_ACTIVE=false
SCREENSHOT_DIR="./data/screenshots"
MAX_SCREENSHOT_BYTES=5242880
ACTION_TIMEOUT_SECONDS=10.0
LAUNCH_TIMEOUT_SECONDS=5.0
MAX_TYPE_TEXT_LENGTH=250
```

### Safety Rules:
1. **Disabled by Default**: Input automation (`DESKTOP_INPUT_AUTOMATION_ENABLED`) is set to `false` by default. It must be explicitly enabled to execute mouse/keyboard events.
2. **PyAutoGUI FailSafe**: Cursor movement to screen corners triggers immediate PyAutoGUI failsafe exception.
3. **Emergency Stop**: Central switch immediately denies all input actions with `HTTP 423 Locked` or `status="blocked"`.
4. **Shell Injection Prevention**: Executables are launched with argument lists (`subprocess.Popen(command_args, shell=False)`), preventing shell command chaining.

---

## 4. API Endpoints

### 1. Get Capabilities
```http
GET /api/v1/desktop/capabilities
```
**Response**:
```json
{
  "os_name": "Windows",
  "is_windows": true,
  "is_interactive_desktop": true,
  "screenshot_available": true,
  "ui_automation_available": true,
  "mouse_keyboard_available": true,
  "input_automation_enabled": false,
  "emergency_stop_active": false,
  "supported_applications": ["notepad", "calc", "explorer", "cmd"]
}
```

### 2. List Approved Applications
```http
GET /api/v1/desktop/applications
```

### 3. Launch Application
```http
POST /api/v1/desktop/applications/notepad/launch
Content-Type: application/json

{
  "task_id": 1,
  "arguments": []
}
```

### 4. Capture Screenshot
```http
POST /api/v1/desktop/screenshots
Content-Type: application/json

{
  "task_id": 1,
  "label": "initial_state"
}
```

### 5. Stream Screenshot Image
```http
GET /api/v1/desktop/screenshots/{screenshot_id}
```

### 6. Execute Desktop Action
```http
POST /api/v1/desktop/actions
Content-Type: application/json

{
  "action_type": "press_key",
  "parameters": {
    "key": "enter"
  },
  "task_id": 1
}
```

### 7. Emergency Stop Toggle
```http
POST /api/v1/desktop/emergency-stop?active=true
```

---

## 5. Known Limitations & Roadmap

- **Autonomous Planning**: Phase 2 provides the execution and observation subsystem. Autonomous AI reasoning and goal decomposition will be introduced in **Phase 3** via OpenRouter.
- **Headless / Locked Sessions**: If Windows screen is locked or running in a headless VM without an active display session, GDI screenshot capture will fail safely and return `HTTP 501 Not Implemented`.
- **UAC Dialogs**: Automation cannot bypass elevated Windows User Account Control (UAC) prompts by design.
