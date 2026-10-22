# VENORA AI

> **Virtual Environment for Neural Operations, Reasoning & Assistance**  
> *Think. Execute. Evolve.*

VENORA AI is a modular, locally executable, personal AI agent designed for Windows 11. Built with privacy, security, and extensibility at its core, VENORA provides autonomous desktop assistance, AI reasoning, voice interaction, and remote access.

---

## Current Status: Phase 8 (Voice Interface Complete)

Phase 8 introduces the Voice Interface Subsystem, enabling speech recognition, controlled microphone capture, and voice responses:
- **FastAPI Core**: Asynchronous application with versioned REST API (`/api/v1`).
- **AI Provider Abstraction**: Modular `BaseAIProvider` and `OpenRouterProvider` with graceful offline fallback and zero credential leaks.
- **Controlled Tool Registry**: Strict validation of tool names and Pydantic arguments with automatic rejection of unknown commands.
- **Desktop Automation**: Approved tools for `list_applications`, `launch_application`, `inspect_processes`, `capture_screenshot`, and `desktop_capabilities`.
- **Reasoning Service**: Multi-round conversational tool calling engine with strict iteration bounds (`MAX_TOOL_CALL_ROUNDS=3`).
- **Structured Task Planner**: Decomposes user goals into validated multi-step plans with strict DAG dependency resolution.
- **Finite State Machines**: Validated lifecycle transitions for Tasks and Steps with fail-fast cascading error policies.
- **Sequential Execution Engine**: Safely executes approved steps through the Tool Registry, enforcing permissions, timeouts, and emergency stops.
- **Persistence & Crash Recovery**: `TaskRecoveryManager` reconciles interrupted tasks on restart; append-only audit event logging in `ExecutionLog`.
- **File Intelligence & Document Understanding**: Authorized directory containment, multi-format text extraction (PDF, DOCX, TXT, MD, CSV, XLSX, JSON), SQLite FTS5 search, and grounded Q&A with citations.
- **Browser Automation Subsystem**: Isolated Playwright Chromium sessions with strict URL validation, anti-SSRF protections, and redirect revalidation.
- **Safe Page Inspection & Interaction**: Controlled extraction of headings, links, and text; accessible element interactions guarded by explicit approvals.
- **Web Search & Multi-Page Research**: DuckDuckGo search integration and multi-page research synthesis with verifiable source citations.
- **Long-Term Memory Subsystem**: Durable persistent storage for user preferences, explicit facts, project context, procedural workflows, and conversation summaries.
- **Hybrid Semantic & Lexical Retrieval**: SQLite FTS5 full-text indexing combined with vector embedding cosine similarity and recency decay ranking.
- **Deduplication & State-Aware Conflict Resolution**: Exact content hash deduplication with automatic supersession of outdated facts.
- **Voice Interface & Audio Validation**: Multi-format audio validation (WAV, OGG, MP3, WEBM), bounded duration/size, and path-traversal-proof artifact delivery.
- **Speech-to-Text & Text-to-Speech Abstractions**: Pluggable STT and TTS provider interfaces with deterministic mock providers for testing.
- **Controlled Microphone Capture**: Explicit opt-in recording with hardware detection and strict prohibition on background/startup listening.
- **Voice Sessions & AI Integration**: Stateful session lifecycle tracking, seamless routing into Phase 3 Reasoning and Phase 7 Memory, and optional spoken responses.
- **Comprehensive Testing**: 152 out of 152 automated tests passing across Phases 1 through 8.

---

## Architecture Overview

```
VENORA AI
├── backend/
│   ├── app/
│   │   ├── ai/              # AI provider, OpenRouter, prompts, schemas, reasoning, tool registry
│   │   │   ├── tools/       # BaseTool, ToolRegistry, desktop tool adapters
│   │   │   ├── conversation.py # Bounded conversation context manager
│   │   │   ├── openrouter_provider.py # OpenRouter API client
│   │   │   ├── prompts.py   # Versioned system instructions
│   │   │   ├── provider.py  # BaseAIProvider abstract interface
│   │   │   ├── reasoning_service.py # Multi-round reasoning loop coordinator
│   │   │   └── schemas.py   # Pydantic schemas for messages, tools, responses
│   │   ├── api/routes/      # REST API endpoints (health, tasks, desktop, assistant)
│   │   ├── core/            # Config, structured logging, typed errors
│   │   ├── database/        # Engine, sessionmaker, schema init
│   │   ├── desktop/         # Capability, launcher, processes, screenshots, mouse/keyboard, service
│   │   ├── models/          # SQLAlchemy models (Task, Session, ExecutionLog)
│   │   ├── schemas/         # Pydantic validation schemas
│   │   ├── services/        # Task service & business logic
│   │   └── main.py          # FastAPI application factory & lifespan
│   └── tests/               # Pytest automated test suite (60 tests)

├── data/
│   ├── screenshots/         # Local task-scoped screenshots
│   └── venora.db            # Local SQLite database
├── logs/
│   └── venora.log           # Rotating application log file
├── docs/
│   ├── ARCHITECTURE.md      # System design & extension points
│   ├── DESKTOP_AUTOMATION.md# Phase 2 desktop subsystem documentation
│   └── SECURITY.md          # Security baseline & desktop boundaries
└── scripts/
    └── run_backend.ps1      # PowerShell launcher script
```

For complete details, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/DESKTOP_AUTOMATION.md](docs/DESKTOP_AUTOMATION.md), and [docs/SECURITY.md](docs/SECURITY.md).

---

## Prerequisites

- **Operating System**: Windows 11 (or Windows 10 64-bit).
- **Python**: Python 3.10 or higher.
- **Shell**: Windows PowerShell 5.1+ or PowerShell 7+.
- **Git**: Installed and available in PATH.

---

## Installation & Setup (Windows 11)

### 1. Clone or Open the Repository
```powershell
cd "c:\Users\ddnan\Venora AI"
```

### 2. Create and Activate Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies
```powershell
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
```

### 4. Configure Environment (Optional)
The backend comes pre-configured with safe local defaults (input automation is disabled by default for safety).
```powershell
Copy-Item .env.example .env
```

---

## Running the Backend

### Option A: Using the PowerShell Launcher Script (Recommended)
```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_backend.ps1
```

### Option B: Manual Execution
```powershell
$env:PYTHONPATH = "backend"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

---

## Verifying Endpoints

Once running, access the following endpoints:

| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `http://127.0.0.1:8000/api/v1/health` | GET | Liveness probe |
| `http://127.0.0.1:8000/api/v1/health/ready` | GET | Database readiness |
| `http://127.0.0.1:8000/api/v1/tasks` | GET/POST | List and create tasks |
| `http://127.0.0.1:8000/api/v1/desktop/capabilities` | GET | Report OS & automation capabilities |
| `http://127.0.0.1:8000/api/v1/desktop/applications` | GET | List approved whitelisted applications |
| `http://127.0.0.1:8000/api/v1/desktop/applications/{app_id}/launch` | POST | Launch approved application |
| `http://127.0.0.1:8000/api/v1/desktop/processes` | GET | List running processes |
| `http://127.0.0.1:8000/api/v1/desktop/screenshots` | POST | Capture task-scoped screenshot |
| `http://127.0.0.1:8000/api/v1/desktop/screenshots/{id}` | GET | Retrieve screenshot PNG file |
| `http://127.0.0.1:8000/api/v1/desktop/actions` | POST | Dispatch structured verified desktop action |
| `http://127.0.0.1:8000/api/v1/desktop/emergency-stop` | POST | Toggle emergency stop switch |
| `http://127.0.0.1:8000/docs` | GET | Interactive Swagger UI |
| `http://127.0.0.1:8000/redoc` | GET | ReDoc Documentation |

---

## Running Automated Tests

Run the full Pytest suite covering Phase 1 and Phase 2:
```powershell
$env:PYTHONPATH = "backend"
.\.venv\Scripts\python.exe -m pytest -v backend/tests
```

All 38 unit and integration tests execute cleanly with 100% pass rate.

---

## Current Limitations & Roadmap

### Phase 2 Limitations
- Autonomous planning has not yet been introduced (planned for **Phase 3** with OpenRouter).
- Input automation requires explicit enablement in local config (`DESKTOP_INPUT_AUTOMATION_ENABLED=true`).
- Locked sessions or headless VMs cannot capture GDI screen buffers.

### Future Roadmap
- **Phase 3**: AI Reasoning Engine (OpenRouter API integration & tool calling).
- **Phase 4**: Real-time Voice Interaction (Sarvam AI STT & TTS).
- **Phase 5**: Telegram Remote Control Bot.
- **Phase 6**: Web Dashboard (React + TypeScript).
