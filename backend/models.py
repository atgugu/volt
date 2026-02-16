"""
Pydantic API Models

Request/response models for the backend API.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List


class ConversationStartRequest(BaseModel):
    """Request to start a new conversation."""
    agent_id: str = Field(..., description="ID of the agent to use")
    voice_mode: bool = Field(False, description="Enable voice mode")
    initial_message: Optional[str] = Field(None, description="Optional first message")


class ConversationStartResponse(BaseModel):
    """Response after starting a conversation."""
    session_id: str
    agent_id: str
    agent_name: str
    greeting: str
    voice_mode: bool


class ConversationMessageRequest(BaseModel):
    """Request to send a message in a conversation."""
    session_id: str = Field(..., description="Session ID")
    message: str = Field(..., description="User's message")
    voice_mode: Optional[bool] = Field(None, description="Override voice mode")


class ConversationMessageResponse(BaseModel):
    """Response to a conversation message."""
    session_id: str
    response: str
    is_complete: bool = False
    collected_fields: Dict[str, Any] = {}
    completion_percentage: int = 0


class ConversationStatusResponse(BaseModel):
    """Status of a conversation."""
    session_id: str
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    is_complete: bool = False
    collected_fields: Dict[str, Any] = {}
    missing_fields: List[str] = []


class AgentInfo(BaseModel):
    """Summary info about an available agent."""
    id: str
    name: str
    description: str
    field_count: int
    required_field_count: int
    optional_field_count: int


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    version: str = "1.0.0"
    agents_loaded: int = 0
    active_sessions: int = 0


class AgentCreateRequest(BaseModel):
    """Request to create a new agent from a natural language prompt."""
    prompt: str = Field(..., description="Natural language description of the agent to create")


class AgentCreateResponse(BaseModel):
    """Response after creating a new agent."""
    id: str
    name: str
    description: str
    field_count: int
    required_field_count: int
    optional_field_count: int
    config: dict


class ConversationMessage(BaseModel):
    """A single message in a conversation."""
    role: str
    content: str
    timestamp: str


class ConversationHistoryResponse(BaseModel):
    """Full conversation transcript."""
    session_id: str
    messages: List[ConversationMessage]


class CompletionResponse(BaseModel):
    """Completed conversation data."""
    session_id: str
    agent_id: str
    collected_fields: Dict[str, Any]
    completed_at: str
    result_data: Optional[Dict[str, Any]] = None
