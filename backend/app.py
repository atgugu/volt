"""
Backend API Service

Main FastAPI application that orchestrates agent conversations,
manages sessions, and proxies voice services.

Persistence: SQLite database + LangGraph checkpointer for session
survival across server restarts.
"""

import logging
import uuid
import sys
import os
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import (
    API_TITLE, API_DESCRIPTION, API_VERSION,
    LLM_ENDPOINT, BACKEND_HOST, BACKEND_PORT,
    MAX_SESSIONS, VERBOSE,
)
from backend.models import (
    ConversationStartRequest, ConversationStartResponse,
    ConversationMessageRequest, ConversationMessageResponse,
    ConversationStatusResponse, AgentInfo, HealthResponse,
    AgentCreateRequest, AgentCreateResponse,
    ConversationHistoryResponse, ConversationMessage,
    CompletionResponse,
)
from framework.config.agent_registry import get_registry
from framework.state.agent_state import create_initial_state, get_state_summary
from framework.db.database import get_db, close_db
from framework.db.stores import SessionStore, ConversationStore, CompletionStore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Module-level persistence (initialized in lifespan)
checkpointer = None
session_store: SessionStore | None = None
conversation_store: ConversationStore | None = None
completion_store: CompletionStore | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup and shutdown."""
    global checkpointer, session_store, conversation_store, completion_store

    # Startup
    logger.info("Starting Local LLM Agent Framework...")

    # Initialize database and checkpointer
    from framework.config.settings import DB_PATH
    from langgraph.checkpoint.sqlite import SqliteSaver

    conn = get_db(DB_PATH)
    checkpointer = SqliteSaver(conn)
    checkpointer.setup()

    session_store = SessionStore(conn)
    conversation_store = ConversationStore(conn)
    completion_store = CompletionStore(conn)

    logger.info(f"Database ready: {DB_PATH}")

    # Discover agents
    registry = get_registry()
    logger.info(f"Loaded {registry.agent_count} agent(s): {registry.agent_ids}")

    # Initialize voice proxy (optional)
    try:
        from backend.voice_proxy import VoiceServiceProxy
        app.state.voice_proxy = VoiceServiceProxy()
        await app.state.voice_proxy.initialize()
        logger.info("Voice services initialized")
    except Exception as e:
        logger.warning(f"Voice services not available: {e}")
        app.state.voice_proxy = None

    yield

    # Shutdown
    if hasattr(app.state, "voice_proxy") and app.state.voice_proxy:
        await app.state.voice_proxy.cleanup()
    close_db()
    logger.info("Shutdown complete")


# Create app
app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files (frontend)
frontend_dir = PROJECT_ROOT / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")


# =========================================================================
# Health & Info Endpoints
# =========================================================================


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check service health."""
    registry = get_registry()
    active = session_store.count_active() if session_store else 0
    return HealthResponse(
        status="healthy",
        version=API_VERSION,
        agents_loaded=registry.agent_count,
        active_sessions=active,
    )


@app.get("/agents", response_model=list)
async def list_agents():
    """List all available agents."""
    registry = get_registry()
    return registry.list_agents()


@app.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get details for a specific agent."""
    registry = get_registry()
    agent = registry.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    return agent.to_dict()


# =========================================================================
# Agent Management Endpoints
# =========================================================================


@app.post("/agents/create", response_model=AgentCreateResponse)
async def create_agent(request: AgentCreateRequest):
    """Create a new agent from a natural language prompt."""
    from framework.factory.agent_factory import generate_agent
    from framework.config.settings import AGENTS_DIR

    try:
        config, agent_dir = generate_agent(
            prompt=request.prompt,
            endpoint=LLM_ENDPOINT,
            agents_dir=AGENTS_DIR,
        )
    except Exception as e:
        logger.error(f"Agent generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Agent generation failed: {str(e)}")

    registry = get_registry()
    agent_def = registry.register_agent(config, agent_dir)

    return AgentCreateResponse(
        id=agent_def.id,
        name=agent_def.name,
        description=agent_def.description,
        field_count=len(agent_def.fields),
        required_field_count=len(agent_def.required_fields),
        optional_field_count=len(agent_def.optional_fields),
        config=config,
    )


@app.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str):
    """Delete an agent by ID."""
    import shutil
    from framework.config.settings import AGENTS_DIR

    registry = get_registry()
    agent = registry.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

    registry.unregister_agent(agent_id)

    agent_dir = Path(AGENTS_DIR) / agent_id
    if agent_dir.exists():
        shutil.rmtree(agent_dir)

    return {"status": "deleted", "agent_id": agent_id}


@app.get("/agents/{agent_id}/export")
async def export_agent(agent_id: str):
    """Export full agent configuration."""
    registry = get_registry()
    agent = registry.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    return agent.config


# =========================================================================
# Conversation Endpoints
# =========================================================================


@app.post("/conversation/start", response_model=ConversationStartResponse)
async def start_conversation(request: ConversationStartRequest):
    """Start a new conversation with an agent."""
    registry = get_registry()
    agent = registry.get_agent(request.agent_id)

    if not agent:
        raise HTTPException(
            status_code=404,
            detail=f"Agent not found: {request.agent_id}. Available: {registry.agent_ids}",
        )

    # Enforce session limit
    if session_store.count_active() >= MAX_SESSIONS:
        logger.warning("Max sessions reached, oldest active sessions may exist")

    # Create session
    session_id = str(uuid.uuid4())
    state = create_initial_state(
        session_id=session_id,
        agent_id=agent.id,
        agent_name=agent.name,
        voice_mode=request.voice_mode,
    )

    # Set initial message if provided
    if request.initial_message:
        state["last_user_message"] = request.initial_message

    # Invoke graph to create initial checkpoint (greeting + field init)
    graph = registry.get_graph(agent.id, LLM_ENDPOINT, VERBOSE, checkpointer=checkpointer)
    config = {"configurable": {"thread_id": session_id}}

    greeting = agent.greeting
    if graph:
        try:
            result = graph.invoke(state, config=config)
            greeting = result.get("last_bot_message", greeting)
        except Exception as e:
            logger.error(f"Error during initial graph invocation: {e}", exc_info=True)

    # Persist session metadata
    session_store.create(session_id, agent.id, request.voice_mode)

    # Log messages
    if request.initial_message:
        conversation_store.add_message(session_id, "user", request.initial_message)
    conversation_store.add_message(session_id, "bot", greeting)

    return ConversationStartResponse(
        session_id=session_id,
        agent_id=agent.id,
        agent_name=agent.name,
        greeting=greeting,
        voice_mode=request.voice_mode,
    )


@app.post("/conversation/message", response_model=ConversationMessageResponse)
async def send_message(request: ConversationMessageRequest):
    """Send a message in an existing conversation."""
    session = session_store.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    agent_id = session["agent_id"]

    # Build partial state update (checkpointer merges with saved state)
    updates = {"last_user_message": request.message}
    if request.voice_mode is not None:
        updates["voice_mode"] = request.voice_mode

    # Get graph and invoke with checkpointer
    registry = get_registry()
    graph = registry.get_graph(agent_id, LLM_ENDPOINT, VERBOSE, checkpointer=checkpointer)

    if not graph:
        raise HTTPException(status_code=500, detail="Failed to build agent graph")

    config = {"configurable": {"thread_id": request.session_id}}

    try:
        state = graph.invoke(updates, config=config)
    except Exception as e:
        logger.error(f"Graph invocation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")

    # Log messages
    conversation_store.add_message(request.session_id, "user", request.message)
    conversation_store.add_message(
        request.session_id, "bot", state.get("last_bot_message", "")
    )

    # Handle completion
    if state.get("is_complete"):
        session_store.mark_complete(request.session_id)
        completion_store.save(
            session_id=request.session_id,
            agent_id=agent_id,
            collected_fields=state.get("collected_fields", {}),
            result_data=state.get("result_data"),
        )

    # Calculate completion percentage
    required = len(state.get("required_fields", []))
    collected = len([v for v in state.get("collected_fields", {}).values() if v])
    pct = int((collected / required) * 100) if required > 0 else 100

    return ConversationMessageResponse(
        session_id=request.session_id,
        response=state.get("last_bot_message", ""),
        is_complete=state.get("is_complete", False),
        collected_fields=state.get("collected_fields", {}),
        completion_percentage=pct,
    )


@app.get("/conversation/{session_id}/status", response_model=ConversationStatusResponse)
async def get_conversation_status(session_id: str):
    """Get the status of a conversation."""
    session = session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    agent_id = session["agent_id"]

    # Get state from checkpointer
    registry = get_registry()
    graph = registry.get_graph(agent_id, LLM_ENDPOINT, VERBOSE, checkpointer=checkpointer)

    if not graph:
        raise HTTPException(status_code=500, detail="Failed to build agent graph")

    config = {"configurable": {"thread_id": session_id}}

    try:
        snapshot = graph.get_state(config)
        state = snapshot.values
    except Exception as e:
        logger.error(f"Error getting state snapshot: {e}", exc_info=True)
        # Fall back to session metadata only
        return ConversationStatusResponse(
            session_id=session_id,
            agent_id=agent_id,
            is_complete=session["is_complete"],
        )

    missing = [f["name"] for f in state.get("missing_fields", [])]

    return ConversationStatusResponse(
        session_id=session_id,
        agent_id=state.get("agent_id"),
        agent_name=state.get("agent_name"),
        is_complete=state.get("is_complete", False),
        collected_fields=state.get("collected_fields", {}),
        missing_fields=missing,
    )


# =========================================================================
# History & Completion Endpoints
# =========================================================================


@app.get("/conversations/{session_id}/history", response_model=ConversationHistoryResponse)
async def get_conversation_history(session_id: str):
    """Get the full message transcript for a conversation."""
    session = session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = conversation_store.get_history(session_id)
    return ConversationHistoryResponse(
        session_id=session_id,
        messages=[ConversationMessage(**m) for m in messages],
    )


@app.get("/completions", response_model=list[CompletionResponse])
async def list_completions():
    """List all completed conversations with collected field data."""
    return [CompletionResponse(**c) for c in completion_store.list_all()]


@app.get("/completions/{session_id}", response_model=CompletionResponse)
async def get_completion(session_id: str):
    """Get completion data for a specific session."""
    data = completion_store.get(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Completion not found")
    return CompletionResponse(**data)


# =========================================================================
# Voice Endpoints
# =========================================================================


@app.post("/transcribe")
async def transcribe_audio(file: bytes):
    """Transcribe audio to text."""
    if not hasattr(app.state, "voice_proxy") or not app.state.voice_proxy:
        raise HTTPException(status_code=503, detail="Voice services not available")
    return await app.state.voice_proxy.transcribe_audio(file)


@app.post("/generate_speech")
async def generate_speech(text: str, voice: str = "af_heart", language: str = "en"):
    """Generate speech from text."""
    if not hasattr(app.state, "voice_proxy") or not app.state.voice_proxy:
        raise HTTPException(status_code=503, detail="Voice services not available")
    return await app.state.voice_proxy.generate_speech(text, voice, language)


# =========================================================================
# Frontend
# =========================================================================


@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the frontend chat interface."""
    index_path = frontend_dir / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text())
    return HTMLResponse(content="<h1>Local LLM Agent Framework</h1><p>Frontend not found. Place index.html in frontend/</p>")


# =========================================================================
# Graph Visualization
# =========================================================================


@app.get("/api/graph/mermaid")
async def get_graph_mermaid(agent_id: str = None):
    """Get Mermaid visualization of an agent's graph."""
    registry = get_registry()

    if not agent_id:
        agent_ids = registry.agent_ids
        if agent_ids:
            agent_id = agent_ids[0]
        else:
            return {"mermaid": "graph TD\n  A[No agents loaded]"}

    graph = registry.get_graph(agent_id, LLM_ENDPOINT, VERBOSE)
    if not graph:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

    try:
        mermaid = graph.get_graph().draw_mermaid()
        return {"agent_id": agent_id, "mermaid": mermaid}
    except Exception as e:
        logger.error(f"Mermaid generation error: {e}")
        return {"agent_id": agent_id, "mermaid": f"graph TD\n  A[Error: {e}]"}


# =========================================================================
# Run
# =========================================================================

if __name__ == "__main__":
    import uvicorn

    port = BACKEND_PORT
    # Auto-find port if default is in use
    import socket
    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("", port))
                break
        except OSError:
            port += 1

    logger.info(f"Starting backend on port {port}")
    uvicorn.run(app, host=BACKEND_HOST, port=port)
