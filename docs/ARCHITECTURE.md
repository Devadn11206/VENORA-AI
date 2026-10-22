# VENORA AI — Architecture Specification (Phase 1, Phase 2 & Phase 3)

> **Virtual Environment for Neural Operations, Reasoning & Assistance**  
> *Tagline: Think. Execute. Evolve.*

---

## 1. Architectural Overview

VENORA AI is engineered as a modular, local-first personal AI desktop assistant designed to run on Windows 11.
- **Phase 1** established the backend foundation: configuration, SQLite persistence, task tracking, structured logging, and health routes.
- **Phase 2** added controlled desktop automation: application launching, process inspection, screenshot capturing, and emergency-stop circuit breaking.
- **Phase 3** introduced the AI Reasoning & Structured Tool Calling Subsystem, connecting natural-language instructions with safe, validated tool dispatching.
- **Phase 4** introduced the Task Orchestration & Execution Management Subsystem, providing multi-step planning, finite state machines, sequential execution, fail-fast cascading, and crash recovery.
- **Phase 5** introduces the **File Intelligence & Document Understanding Subsystem**, providing authorized-directory containment, multi-format text extraction (PDF, DOCX, TXT, MD, CSV, XLSX, JSON), SQLite FTS5 search, and grounded AI understanding with verifiable citations.

```
+-------------------------------------------------------------------------+
|                                Clients                                  |
|   (PowerShell CLI, Future Dashboard React Web App, Future Telegram Bot) |
+-------------------------------------------------------------------------+
                                    |
                                    | HTTP / JSON (Port 8000)
                                    v
+-------------------------------------------------------------------------+
|                          FastAPI Application                            |
|                                                                         |
|  +---------------------+  +--------------------+  +------------------+  |
|  | Request Size Limit  |  |  CORS Middleware   |  | Exception Filter |  |
|  +---------------------+  +--------------------+  +------------------+  |
|                                                                         |
|  +-------------------------------------------------------------------+  |
|  |                         API Routers (/api/v1)                     |  |
|  |     /health, /tasks, /desktop, /assistant                         |  |
|  +-------------------------------------------------------------------+  |
|             |                                   |                       |
|             v                                   v                       |
|  +-----------------------+           +-------------------------------+  |
|  |  Task Service Layer   |           |    Reasoning Service Layer    |  |
|  |  CRUD & Lifecycle     |           |    Multi-Round Tool Engine    |  |
|  +-----------------------+           +-------------------------------+  |
|             |                                   |          ^            |
|             |                                   v          |            |
|             |                        +------------------+  |            |
|             |                        |   OpenRouter     |  | Context    |
|             |                        |   AI Provider    |  | Bounded    |
|             |                        +------------------+  | History    |
|             |                                   |          |            |
|             |                        +------------------+  |            |
|             |                        | Controlled Tool  |--+            |
|             |                        | Registry         |               |
|             |                        +------------------+               |
|             |                                   |                       |
|             +-----------------+-----------------+                       |
|                               v                                         |
|  +-------------------------------------------------------------------+  |
|  |                      Desktop Service Layer                        |  |
|  |  Allowlist, Launcher, Process Inspector, Screenshots, Permissions |  |
|  +-------------------------------------------------------------------+  |
|                               |                                         |
|  +----------------------------v--------------------------------------+  |
|  |                 SQLAlchemy 2.x ORM / Database Layer               |  |
|  |     Session Factory, Thread Isolation, Schema Definition          |  |
|  +-------------------------------------------------------------------+  |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|                             Storage Layer                               |
|        - SQLite Database: data/venora.db (Foreign Keys Enforced)        |
|        - Rotating File Logs: logs/venora.log                            |
|        - Screenshots Directory: data/screenshots/                       |
+-------------------------------------------------------------------------+
```

---

## 2. Phase 3 Architecture: AI Reasoning Subsystem

The reasoning layer is modularly encapsulated under `backend/app/ai/`:

| Component | File Path | Functionality |
| :--- | :--- | :--- |
| **Provider Interface** | `backend/app/ai/provider.py` | `BaseAIProvider` abstract contract specifying `generate_response()`, configuration checks, and normalized outputs. |
| **OpenRouter Provider** | `backend/app/ai/openrouter_provider.py` | OpenRouter HTTP client via `httpx.AsyncClient` supporting chat completions, tools definitions, status translation, and error categorization. |
| **Prompt System** | `backend/app/ai/prompts.py` | Versioned system instructions (`v1.0.0`) enforcing truthful outcome reporting, tool discipline, and resistance against prompt injection attacks. |
| **Schemas** | `backend/app/ai/schemas.py` | Strongly typed Pydantic models for chat turns (`ChatMessage`), tool calls (`ToolCall`), tool outputs (`ToolResult`), and responses (`AssistantResponse`). |
| **Controlled Tool Registry** | `backend/app/ai/tools/registry.py` | Registry for registered tools; validates schemas, verifies permissions, rejects unknown tools, and manages safe execution dispatch. |
| **Desktop Tool Adapters** | `backend/app/ai/tools/desktop_tools.py` | Predefined tools wrapping Phase 2 `DesktopService` (`list_applications`, `launch_application`, `inspect_processes`, `capture_screenshot`, `desktop_capabilities`). |
| **Reasoning Engine** | `backend/app/ai/reasoning_service.py` | Orchestrates multi-round reasoning loops (up to `MAX_TOOL_CALL_ROUNDS`), conversation contexts, and tool result feeds. |
| **Conversation Context** | `backend/app/ai/conversation.py` | Thread-isolated, size-bounded conversation buffer (`ConversationManager`) maintaining FIFO context with automatic eviction. |
| **Assistant API Router** | `backend/app/api/routes/assistant.py` | Endpoints: `POST /api/v1/assistant/chat` and `GET /api/v1/assistant/status`. |

---

## 3. Tool Dispatch & Safety Architecture

```
User Message
     │
     ▼
ReasoningService ─── Check Message Constraints
     │
     ▼
Assemble Context + Versioned System Prompt + Tool Definitions
     │
     ▼
OpenRouterProvider ─── (OpenRouter API completions)
     │
     ├─ [No tool calls] ───────────────► Final AssistantResponse
     │
     └─ [Tool call proposed]
            │
            ▼
        ToolRegistry
            │
            ├─ 1. Tool in Registry? (Reject unknown tool names / arbitrary commands)
            ├─ 2. Validate arguments against Pydantic schema
            ├─ 3. Enforce DesktopPermissionService (Check permission + allowlist)
            └─ 4. Dispatch to predefined handler
                    │
                    ▼
            DesktopService (Phase 2)
                    │
                    ▼
            Return Normalized ToolResult (Verified / Unverified / Failed)
                    │
                    ▼
            Feed ToolResult to context and loop (up to MAX_TOOL_CALL_ROUNDS=3)
```
