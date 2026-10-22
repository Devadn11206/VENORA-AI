# VENORA AI — Long-Term Memory Subsystem

## Overview

The **Long-Term Memory Subsystem** gives VENORA AI the ability to retain durable context, user preferences, technical constraints, procedural knowledge, and project architecture decisions across application restarts and conversation sessions.

It implements a hybrid architecture:
1. **Durable Relational Database**: SQLite via SQLAlchemy with indexed metadata, confidence, importance, and lifecycle flags.
2. **SQLite FTS5 Full-Text Search**: In-database lexical full-text index using `porter unicode61` tokenization.
3. **Semantic Vector Search**: Pluggable embedding provider abstraction with in-process vector cosine similarity computation.
4. **Hybrid Ranking Engine**: Blends semantic similarity, lexical overlap, confidence, importance, and temporal recency decay.
5. **Deduplication & Conflict Resolution**: Exact content hash deduplication combined with state-aware supersession logic.

---

## Architecture Diagram

```
                 +-----------------------------------------+
                 |       Conversational Assistant / UI     |
                 +-----------------------------------------+
                                      |
                         Retrieve Context / Record
                                      v
                 +-----------------------------------------+
                 |              MemoryService              |
                 +-----------------------------------------+
                   /          |             |            \
                  /           |             |             \
                 v            v             v              v
     +--------------+  +-------------+  +-----------+  +--------------+
     | Deduplication|  | Hybrid      |  | Memory    |  | Privacy &    |
     | & Conflict   |  | Ranking     |  | Extractor |  | Secret       |
     | Resolution   |  | Engine      |  | (AI/Rules)|  | Redaction    |
     +--------------+  +-------------+  +-----------+  +--------------+
            |                 |               |               |
            +-----------------+---------------+---------------+
                                      |
                                      v
                 +-----------------------------------------+
                 |            MemoryRepository             |
                 +-----------------------------------------+
                              /              \
                             v                v
                 +-------------------+  +-------------------+
                 | SQLite `memories` |  | SQLite FTS5 Table |
                 | Durable Table     |  | `memories_fts`    |
                 +-------------------+  +-------------------+
```

---

## Memory Categories

VENORA AI categorizes memories to enforce appropriate retention, access bounds, and confidence levels:

1. **`USER_PREFERENCE`**: Explicit user habits, response styles, formatting rules, preferred languages. Permanent by default.
2. **`USER_FACT`**: Relatively stable facts explicitly provided by the user. Permanent by default.
3. **`PROJECT_CONTEXT`**: Technical constraints, architecture choices, framework decisions, and milestone progress. Permanent by default.
4. **`TASK_CONTEXT`**: Reusable workflow details and parameters from previous executions. Subject to configurable TTL (default 30 days).
5. **`PROCEDURAL_MEMORY`**: Established and verified procedures taught by the user.
6. **`CONVERSATION_SUMMARY`**: High-level summaries of completed dialogue turns with conversation identifiers.
7. **`EPISODIC_MEMORY`**: Specific events or decisions with conservative retention.

---

## Deduplication & Conflict Resolution

- **Exact Duplicate Prevention**: Uses a normalized content hash (`SHA-256(category:normalized_content)`). Saving an existing memory refreshes its timestamp and takes the highest confidence without duplicating rows.
- **State Updates & Supersession**: When new facts contain state-update markers (`"migrated"`, `"switched"`, `"now"`, `"updated"`) sharing key subject nouns with an existing memory, the older memory is marked as `status = "superseded"` and linked via `superseded_by`.
- **Retrieval Exclusion**: Superseded, archived, and expired memories are automatically excluded from ordinary active search queries.

---

## Controlled Memory Tools

Registered in `ToolRegistry` and protected by granular default-deny permissions:

| Tool Name | Required Permission | Description |
|-----------|---------------------|-------------|
| `memory_search` | `memory.search` | Natural language hybrid search across active memories |
| `memory_get` | `memory.read` | Retrieve a specific memory record by ID |
| `memory_save` | `memory.create` | Explicitly persist a durable fact or preference |
| `memory_update` | `memory.update` | Update content, category, or importance of a memory |
| `memory_archive` | `memory.archive` | Soft-archive an outdated memory record |
| `memory_delete` | `memory.delete` | Permanently delete a memory record (`confirm=true` required) |
| `memory_list` | `memory.read` | Paginated listing of stored memories with category filters |

---

## REST API Endpoints

All endpoints are mounted under `/api/v1/memory`:

- `GET /api/v1/memory/status`: Diagnostics and capacity metrics.
- `POST /api/v1/memory/search`: Natural language hybrid/lexical search.
- `POST /api/v1/memory`: Explicit memory creation.
- `GET /api/v1/memory`: Paginated list of memories.
- `GET /api/v1/memory/{id}`: Detailed memory record inspection.
- `PATCH /api/v1/memory/{id}`: Update memory fields.
- `POST /api/v1/memory/{id}/archive`: Soft-archive memory.
- `POST /api/v1/memory/{id}/restore`: Restore archived/superseded memory.
- `DELETE /api/v1/memory/{id}`: Permanently delete memory.
- `POST /api/v1/memory/extract`: Extract candidate memories from raw dialogue turns.
