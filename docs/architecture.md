# VOLT Architecture Guide

## Service Architecture

VOLT runs as four independent microservices communicating via HTTP:

```
Frontend (Chat + Voice)
        |
        | HTTP / WebSocket
        v
Backend API (Port 10821)
  - Agent Registry
  - Agent Factory
  - SQLite Persistence + LangGraph Checkpointer
  - LangGraph Orchestration
  - Voice Proxy (optional)
        |
        +-------+--------+--------+
        |       |        |        |
        v       v        v        v
   LLM Load   LLM     TTS      STT
   Balancer  Worker   Kokoro   Whisper
   (8000)    (8010+)  (8033)   (8034)
```

| Service | Port | Description |
|---------|------|-------------|
| **Backend** | 10821 | FastAPI orchestrator with LangGraph, persistence, and voice proxy |
| **LLM** | 8000 | Load balancer + GGUF model workers (Mistral, Llama, etc.) |
| **TTS** | 8033 | Kokoro-82M text-to-speech (~550MB VRAM, 12x realtime) |
| **STT** | 8034 | Whisper Large V3 Turbo speech-to-text (~3-4GB VRAM, 50-100x realtime) |

## Persistence

VOLT persists all state in SQLite with WAL mode enabled, stored at `data/framework.db`.

### Application Tables

| Table | Purpose |
|-------|---------|
| `sessions` | Session metadata (session_id, agent_id, voice_mode, completion status) |
| `conversations` | Full message history (role, content, timestamp per message) |
| `completions` | Collected field data from finished conversations |

### LangGraph Checkpoint Tables

The LangGraph `SqliteSaver` checkpointer creates its own tables for graph state persistence. This means **sessions survive server restarts** -- a user can resume a conversation exactly where they left off.

```python
# Initialized at startup in backend/app.py
from langgraph.checkpoint.sqlite import SqliteSaver
checkpointer = SqliteSaver(conn)
graph = create_agent_graph(agent_def, checkpointer=checkpointer)
```

> [!NOTE]
> The `framework/db/stores.py` module provides `SessionStore`, `ConversationStore`, and `CompletionStore` classes for typed access to application tables.

## Agent Factory

The agent factory (`framework/factory/agent_factory.py`) generates complete agent configurations from natural language descriptions using the LLM.

```
User prompt → Meta-prompt + schema → LLM → JSON parse → Fixup → Validate → Write to disk
```

Key features:
- Auto-assigns validators based on field names (e.g., "email" gets the email validator)
- Auto-corrects common issues (missing IDs, field ordering, descriptions)
- Resolves ID conflicts by appending numeric suffixes
- Registers new agents at runtime without restart

Exposed via `POST /agents/create`. See [Creating Agents](creating-agents.md) for usage.

## LangGraph Flow

Every agent uses this graph structure:

```
START -> _start -> [entry_router]

Entry Router (based on conversation state):
  - awaiting_confirmation -> confirmation_response
  - qa_mode_active -> continuation_detection
  - agent selected + question -> intent_detection
  - agent selected + answer -> field_extraction
  - new conversation -> intent_detection

Core Flow:
  field_initialization -> field_extraction -> field_router
  field_router -> question_generation -> END (wait for user)
  field_router -> confirmation_summary -> END (all fields done)

Q&A Flow:
  intent_detection -> save_graph_position -> question_answering -> END
  continuation_detection -> restore_graph_position -> field_extraction

Confirmation Flow:
  confirmation_response -> completion (approved)
  confirmation_response -> field_modification -> confirmation_summary (changes)

Completion:
  completion -> END
```

## Node Pattern

Every node follows the same signature:

```python
def node_name(state: AgentState, ...) -> AgentState:
    # 1. Read from state
    # 2. Process (LLM calls, validation, logic)
    # 3. Return updated state (immutable)
    return {**state, "field": new_value}
```

Key principles:
- **Immutable updates**: Always `{**state, ...}`, never mutate
- **Guard clauses**: Skip processing if already handled
- **Error handling**: Log errors, provide fallbacks
- **Logging**: Every decision point is logged

## State Management

`AgentState` is a TypedDict that flows through the graph.

<details>
<summary>Full state fields</summary>

| Category | Fields |
|----------|--------|
| **Session** | `session_id`, `agent_id`, `voice_mode` |
| **Fields** | `collected_fields`, `required_fields`, `missing_fields`, `expected_field` |
| **Conversation** | `messages`, `last_user_message`, `last_bot_message` |
| **Confirmation** | `awaiting_confirmation`, `field_modification_request` |
| **Q&A Mode** | `qa_mode_active`, `saved_graph_position` |
| **Iterative Collection** | `iterative_collection_mode`, `iterative_field_name`, `collected_items` |
| **Errors** | `validation_errors`, `retry_count` |

</details>

## Dual-Path Extraction

The field extraction node uses a 2-path approach:

1. **Regex fast-path** (~0.001s): For simple responses matching known patterns
   - Email addresses, phone numbers, integers, yes/no, short names

2. **LLM extraction** (~2-3s): For complex multi-field responses
   - Builds dynamic prompts from agent.json field definitions
   - Handles ambiguous input, multiple fields in one message

This provides ~2000x speedup for simple responses.

## Agent Registry

The `AgentRegistry` auto-discovers agents at startup:

1. Scans `agents/` directory for `agent.json` files
2. Validates each configuration (required keys: `name`, `id`, `description`, `fields`)
3. Creates `AgentDefinition` objects with parsed field metadata
4. Builds and caches LangGraph workflows on demand
5. Supports runtime registration/unregistration via agent factory

## Load Balancer

The LLM load balancer supports multiple model instances:

- Round-robin distribution among healthy workers
- Context-aware routing (long prompts to large context workers)
- Automatic health monitoring and failover
- Dynamic worker count configuration

## API Surface

### Health and Info

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Service health with agent/session counts |
| `GET` | `/agents` | List all available agents |
| `GET` | `/agents/{agent_id}` | Get agent details |

### Agent Management

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/agents/create` | Create agent from natural language prompt |
| `DELETE` | `/agents/{agent_id}` | Delete an agent |
| `GET` | `/agents/{agent_id}/export` | Export full agent configuration |

### Conversations

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/conversation/start` | Start a new conversation |
| `POST` | `/conversation/message` | Send a message |
| `GET` | `/conversation/{session_id}/status` | Get session status and collected fields |

### History and Completions

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/conversations/{session_id}/history` | Full message transcript |
| `GET` | `/completions` | List all completed conversations |
| `GET` | `/completions/{session_id}` | Get completion data for a session |

### Voice

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/transcribe` | Transcribe audio file to text |
| `POST` | `/generate_speech` | Generate speech from text (streaming) |

### Visualization

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Frontend chat interface |
| `GET` | `/api/graph/mermaid` | Mermaid diagram of agent's LangGraph |

> [!TIP]
> Use `GET /api/graph/mermaid?agent_id=profile_collector` to visualize any agent's conversation flow as a Mermaid diagram.
