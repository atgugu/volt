"""
AgentState - Generic state schema for LangGraph agent workflows.

This defines the complete state that flows through the graph, tracking
all aspects of a field-collection conversation including fields, validation,
and conversation history.

Derived from production-tested state management, generalized
to serve as a domain-agnostic agent framework.
"""

from typing import TypedDict, Dict, Any, List, Optional, Annotated
from langgraph.graph import add_messages


class AgentState(TypedDict):
    """
    Complete state for agent conversation flow.

    This state flows through all nodes in the graph and maintains:
    - Session and agent information
    - Field collection and validation
    - Conversation history
    - Confirmation workflow
    - Q&A mode state
    - Error tracking
    """

    # =========================================================================
    # Session Tracking
    # =========================================================================
    session_id: str
    """Unique session identifier"""

    agent_id: Optional[str]
    """ID of the active agent (from agent.json)"""

    agent_name: Optional[str]
    """Display name of the active agent"""

    voice_mode: bool
    """Whether voice mode is active (enables natural speech connectors)"""

    # =========================================================================
    # Field Management (loaded from agent.json)
    # =========================================================================
    collected_fields: Dict[str, Any]
    """Fields successfully collected from user (field_name -> value)"""

    required_fields: List[Dict[str, Any]]
    """Required fields for this agent (from agent.json)"""

    optional_fields: List[Dict[str, Any]]
    """Optional fields for this agent (from agent.json)"""

    conditional_fields: List[Dict[str, Any]]
    """Conditional fields for this agent (from agent.json)"""

    active_conditional_fields: List[Dict[str, Any]]
    """Conditional fields whose conditions are currently met"""

    missing_fields: List[Dict[str, Any]]
    """Fields still needed (ordered by priority)"""

    current_field_index: int
    """Current position in field collection sequence"""

    expected_field: Optional[str]
    """Field that bot most recently asked about (for context-aware extraction)"""

    newly_extracted_this_turn: Dict[str, Any]
    """Fields extracted in current turn (for natural acknowledgment)"""

    # =========================================================================
    # Optional Field Collection
    # =========================================================================
    optional_field_mode: bool
    """Whether we're collecting optional fields (after all required done)"""

    declined_optional_fields: List[str]
    """Optional field names that user explicitly declined to provide"""

    # =========================================================================
    # Iterative Collection (comments, interests, multi-item fields)
    # =========================================================================
    iterative_collection_mode: bool
    """Whether we're in iterative collection mode (ask again after each item)"""

    iterative_field_name: Optional[str]
    """Name of the field being collected iteratively"""

    collected_items: List[str]
    """Individual items collected iteratively (concatenated when done)"""

    # =========================================================================
    # Confirmation State (before completion)
    # =========================================================================
    awaiting_confirmation: bool
    """Whether waiting for user to confirm all collected fields"""

    confirmation_attempts: int
    """Number of times we've asked for confirmation (prevent loops)"""

    field_modification_request: Optional[str]
    """Field name user wants to modify after seeing summary"""

    # =========================================================================
    # Conversation History
    # =========================================================================
    messages: Annotated[List[Dict[str, str]], add_messages]
    """Conversation history (managed by LangGraph)"""

    last_user_message: str
    """Most recent user message"""

    last_bot_message: str
    """Most recent bot response"""

    first_turn: bool
    """Whether this is the first turn (for greeting + first question)"""

    # =========================================================================
    # Completion
    # =========================================================================
    is_complete: bool
    """Whether all required fields are collected"""

    result_data: Optional[Dict[str, Any]]
    """Result data from completion action (API response, log data, etc.)"""

    # =========================================================================
    # Error Tracking
    # =========================================================================
    validation_errors: Dict[str, str]
    """Field-specific validation errors (field_name -> error_message)"""

    retry_count: int
    """Number of times we've retried collecting current field"""

    max_retries: int
    """Maximum retries before escalation"""

    # =========================================================================
    # Q&A Mode (allows users to ask questions mid-conversation)
    # =========================================================================
    qa_mode_active: bool
    """Whether Q&A mode is currently active"""

    saved_graph_position: Optional[str]
    """Graph position saved before entering Q&A (for restoration)"""

    qa_conversation_history: List[Dict[str, str]]
    """Q&A-specific conversation history"""

    qa_consecutive_questions: int
    """Number of consecutive questions in current Q&A session"""

    detected_intent: Optional[str]
    """LLM-detected intent: 'question', 'agent_task', or 'response'"""

    continuation_intent: Optional[str]
    """LLM-detected continuation: 'ask_more', 'continue_task', or 'provide_info'"""

    should_enter_qa_mode: bool
    """Flag: user wants to enter Q&A mode"""

    exit_qa_mode: bool
    """Flag: user wants to exit Q&A mode"""

    has_task_info_in_qa: bool
    """Flag: user provided task info while in Q&A mode"""

    stay_in_qa_mode: bool
    """Flag: user wants to ask more questions"""


def create_initial_state(
    session_id: str,
    agent_id: Optional[str] = None,
    agent_name: Optional[str] = None,
    voice_mode: bool = False,
) -> AgentState:
    """
    Creates an initial AgentState for a new conversation.

    Args:
        session_id: Unique session identifier
        agent_id: Agent ID (from agent.json)
        agent_name: Agent display name
        voice_mode: Whether voice mode is active

    Returns:
        AgentState: Initial state with default values
    """
    return {
        # Session
        "session_id": session_id,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "voice_mode": voice_mode,
        # Fields
        "collected_fields": {},
        "required_fields": [],
        "optional_fields": [],
        "conditional_fields": [],
        "active_conditional_fields": [],
        "missing_fields": [],
        "current_field_index": 0,
        "expected_field": None,
        "newly_extracted_this_turn": {},
        # Optional field collection
        "optional_field_mode": False,
        "declined_optional_fields": [],
        # Iterative collection
        "iterative_collection_mode": False,
        "iterative_field_name": None,
        "collected_items": [],
        # Confirmation
        "awaiting_confirmation": False,
        "confirmation_attempts": 0,
        "field_modification_request": None,
        # Conversation
        "messages": [],
        "last_user_message": "",
        "last_bot_message": "",
        "first_turn": True,
        # Completion
        "is_complete": False,
        "result_data": None,
        # Errors
        "validation_errors": {},
        "retry_count": 0,
        "max_retries": 3,
        # Q&A Mode
        "qa_mode_active": False,
        "saved_graph_position": None,
        "qa_conversation_history": [],
        "qa_consecutive_questions": 0,
        "detected_intent": None,
        "continuation_intent": None,
        "should_enter_qa_mode": False,
        "exit_qa_mode": False,
        "has_task_info_in_qa": False,
        "stay_in_qa_mode": False,
    }


def get_state_summary(state: AgentState) -> str:
    """
    Get a human-readable summary of the current state.
    Useful for debugging and logging.

    Args:
        state: Current AgentState

    Returns:
        str: Formatted summary
    """
    collected = len(state.get("collected_fields", {}))
    required = len(state.get("required_fields", []))
    missing = [f["name"] for f in state.get("missing_fields", [])]

    return f"""
State Summary (Session: {state['session_id']})
==========================================
Agent: {state.get('agent_name')} (ID: {state.get('agent_id')})
Collected Fields: {collected}/{required}
Missing Fields: {missing}
Current Field: {state.get('current_field_index')}
Complete: {state.get('is_complete')}
Optional Mode: {state.get('optional_field_mode', False)}
Declined Optional: {state.get('declined_optional_fields', [])}
Validation Errors: {list(state.get('validation_errors', {}).keys())}
Retry Count: {state.get('retry_count')}/{state.get('max_retries')}
Q&A Mode: {state.get('qa_mode_active', False)}
    """.strip()
