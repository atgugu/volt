# Getting Started with VOLT

## Prerequisites

- Python 3.10+
- A GGUF model file (Mistral, Llama, Qwen, Gemma, etc.)
- CUDA-capable GPU (recommended) or CPU-only mode

## Installation

### Option 1: Docker (Recommended)

```bash
git clone https://github.com/atgugu/volt.git
cd volt
cp .env.example .env
```

Edit `.env` with your model path and settings, then:

```bash
docker compose up -d
```

This starts all four services (backend, LLM, TTS, STT) with GPU support. The UI is available at `http://localhost:10821`.

> [!TIP]
> Docker handles all dependencies automatically. Voice services (TTS/STT) are optional -- comment them out in `docker-compose.yml` if you only need text mode.

### Option 2: Manual Setup

```bash
git clone https://github.com/atgugu/volt.git
cd volt

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Configuration

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```bash
# Required: path to your GGUF model
LLM_MODEL_PATH=/path/to/your/model.gguf

# Optional: adjust as needed
LLM_CONTEXT_SIZE=8192
LLM_GPU_LAYERS=-1    # -1 = all layers on GPU
```

> [!TIP]
> Running without a GPU? Set `LLM_GPU_LAYERS=0` and increase `LLM_THREADS=8` for better CPU performance. Responses will be slower but fully functional.

## Starting Services (Manual Setup)

### Service Manager

```bash
python scripts/restart_services.py     # Start all services
python scripts/check_services.py       # Verify health
```

### Manual Start

```bash
# Terminal 1: LLM Service
cd services/llm_inference
uvicorn main:app --host 0.0.0.0 --port 8000

# Terminal 2: Backend
python backend/app.py

# Optional: Voice services
cd services/tts_service && python main.py   # Terminal 3: TTS (port 8033)
cd services/stt_service && python main.py   # Terminal 4: STT (port 8034)
```

### Health Check

```bash
python scripts/check_services.py
```

Or check individual services:

```bash
curl http://localhost:10821/health   # Backend
curl http://localhost:8000/health    # LLM
curl http://localhost:8033/health    # TTS (optional)
curl http://localhost:8034/health    # STT (optional)
```

## Your First Conversation

### Via Web UI

1. Open `http://localhost:10821` in your browser
2. Select an agent from the dropdown (e.g., "User Profile Collection")
3. Start chatting

### Via API

```bash
# Start a conversation
curl -X POST http://localhost:10821/conversation/start \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "profile_collector"}'

# Send a message (use the session_id from above)
curl -X POST http://localhost:10821/conversation/message \
  -H "Content-Type: application/json" \
  -d '{"session_id": "YOUR_SESSION_ID", "message": "My name is John Smith"}'
```

## Creating an Agent

### Quick Way: Agent Factory

Create an agent from a natural language description:

```bash
curl -X POST http://localhost:10821/agents/create \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Create an agent that collects a bug report: title, severity (low/medium/high), steps to reproduce, and expected behavior"}'
```

The factory generates the full `agent.json`, validates it, writes it to disk, and registers it -- no restart needed.

### Manual Way: Write agent.json

1. Create a directory: `mkdir agents/my_agent`
2. Create `agents/my_agent/__init__.py` (empty file)
3. Create `agents/my_agent/agent.json`:

```json
{
  "name": "My First Agent",
  "id": "my_agent",
  "description": "A simple demo agent",
  "greeting": "Hello! Let me collect some info.",
  "fields": [
    {
      "name": "favorite_color",
      "type": "string",
      "required": true,
      "question": "What is your favorite color?",
      "order": 0
    }
  ],
  "completion": {
    "message": "Great choice! {favorite_color} is a wonderful color.",
    "action": "log"
  }
}
```

4. Restart the backend -- your agent appears in the UI dropdown

See [Creating Agents](creating-agents.md) for the full reference.

## Persistence

VOLT uses SQLite to persist all sessions, conversations, and completions. This means:

- **Sessions survive restarts**: Stop the server, start it again, and resume any conversation
- **Full history**: Retrieve any past conversation transcript
- **Completion data**: Access collected field data from finished sessions

```bash
# View conversation history
curl http://localhost:10821/conversations/YOUR_SESSION_ID/history

# List all completed conversations
curl http://localhost:10821/completions

# Get collected data for a specific session
curl http://localhost:10821/completions/YOUR_SESSION_ID
```

> [!NOTE]
> The database is stored at `data/framework.db`. LangGraph checkpoint state is stored alongside application data in the same SQLite file.

## Exploring the API

List available agents:

```bash
curl http://localhost:10821/agents
```

Export an agent's full configuration:

```bash
curl http://localhost:10821/agents/profile_collector/export
```

Check session status and collected fields:

```bash
curl http://localhost:10821/conversation/YOUR_SESSION_ID/status
```

## Troubleshooting

> [!WARNING]
> **LLM service won't start**: Check that `LLM_MODEL_PATH` points to a valid `.gguf` file and you have enough VRAM (`nvidia-smi`). Try reducing `LLM_CONTEXT_SIZE`.

> [!WARNING]
> **Agent not appearing**: Verify `agent.json` is valid JSON with unique `id`, `name`, `description`, and `fields` keys. Check backend logs for validation errors.

> [!WARNING]
> **Slow responses**: Use regex-friendly field types (`email`, `phone`, `number`) for fast extraction. Reduce `LLM_CONTEXT_SIZE` for faster generation, or enable load balancing with multiple workers.
