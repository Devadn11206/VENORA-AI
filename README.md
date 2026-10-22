# VENORA AI

> **Virtual Environment for Neural Operations, Reasoning & Assistance**  
> *Think. Execute. Evolve.*

VENORA AI is a modular, locally executable, personal AI agent designed for Windows 11. Built with privacy, security, and extensibility at its core, VENORA aims to provide autonomous desktop assistance, AI reasoning, voice interaction, and remote access.

---

## Current Status: Phase 1 (Foundation Complete)

Phase 1 establishes the production-grade backend foundation:
- **FastAPI Core**: Asynchronous application with versioned REST API (`/api/v1`).
- **Pydantic Settings**: Centralized configuration with environment variable support.
- **SQLAlchemy 2.x**: Relational database persistence using SQLite with strict foreign keys.
- **Structured Logging**: Rotating file handler (`logs/venora.log`) and console output.
- **Task Lifecycle Management**: Validated state machine for task creation, query, update, and cancellation.
- **Initial Security**: Localhost binding, CORS restrictions, size limiting, and sanitized error responses.
- **Comprehensive Testing**: 100% passing automated test suite (Pytest).

---

## Architecture Overview

```
VENORA AI
├── backend/
│   ├── app/
│   │   ├── api/routes/      # REST API endpoints (health, tasks)
│   │   ├── core/            # Config, structured logging, errors
│   │   ├── database/        # Engine, sessionmaker, schema init
│   │   ├── models/          # SQLAlchemy models (Task, Session, ExecutionLog)
│   │   ├── schemas/         # Pydantic validation schemas
│   │   ├── services/        # Business logic & state transitions
│   │   └── main.py          # FastAPI application factory & lifespan
│   └── tests/               # Pytest automated test suite
├── data/                    # Local SQLite database (venora.db)
├── logs/                    # Rotating log files (venora.log)
├── docs/                    # Architecture and Security specifications
└── scripts/                 # PowerShell launcher scripts
```

For complete details, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/SECURITY.md](docs/SECURITY.md).

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
The backend comes pre-configured with safe local defaults. If you wish to customize configuration:
```powershell
Copy-Item .env.example .env
```

### 5. Initialize the Database
The database tables are created automatically on application startup, or you can run:
```powershell
$env:PYTHONPATH = "backend"
python -m app.database.init_db
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

| Endpoint | Method | Purpose | Example Response |
| :--- | :--- | :--- | :--- |
| `http://127.0.0.1:8000/api/v1/health` | GET | Liveness probe | `{"status":"ok","app_name":"VENORA AI","version":"0.1.0"}` |
| `http://127.0.0.1:8000/api/v1/health/ready` | GET | Database readiness | `{"status":"ready","database":"connected"}` |
| `http://127.0.0.1:8000/api/v1/tasks` | GET | List tasks (paginated) | `{"items":[],"total":0,"page":1,"page_size":20}` |
| `http://127.0.0.1:8000/api/v1/tasks` | POST | Create task | `{"id":1,"title":"...","status":"pending"}` |
| `http://127.0.0.1:8000/docs` | GET | Interactive Swagger Docs | Interactive OpenAPI UI |
| `http://127.0.0.1:8000/redoc` | GET | ReDoc Documentation | Human-readable API specs |

---

## Running Automated Tests

Run the full Pytest suite using the isolated in-memory database:
```powershell
$env:PYTHONPATH = "backend"
.\.venv\Scripts\python.exe -m pytest -v backend/tests
```

All 22 unit and integration tests will execute and report results.

---

## Database Backup and Restore

- **Database Location**: `data/venora.db`
- **Backup**:
  ```powershell
  Copy-Item data\venora.db data\venora_backup.db
  ```
- **Restore**:
  ```powershell
  Copy-Item data\venora_backup.db data\venora.db
  ```

---

## Troubleshooting

1. **PowerShell Script Execution Policy Error**:
   Run: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`
2. **ModuleNotFoundError: No module named 'app'**:
   Ensure `backend` is in your `PYTHONPATH` or run uvicorn with `--app-dir backend`.
3. **Database locked error**:
   SQLite is configured with `check_same_thread=False` and handles concurrent reads. If writing under high load in future phases, migration to PostgreSQL will be enabled via `DATABASE_URL`.

---

## Current Limitations & Roadmap

### Phase 1 Limitations
- No external AI reasoning (no LLM calls yet).
- Localhost only (no remote authentication yet).
- Manual task execution only (autonomous background runner scheduled for Phase 2).

### Future Roadmap
- **Phase 2**: Windows Desktop Observation & Automation (pyautogui / pywinauto with permission gates).
- **Phase 3**: AI Reasoning Engine (OpenRouter API integration).
- **Phase 4**: Real-time Voice Interaction (Sarvam AI STT & TTS).
- **Phase 5**: Telegram Remote Control Bot.
- **Phase 6**: Web Dashboard (React + TypeScript).
