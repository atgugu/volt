"""
Generic Agent Graph Builder

Constructs a LangGraph workflow from an agent definition (agent.json).
This replaces domain-specific graph definitions with a generic builder
that creates the standard field-collection conversation flow.

Graph Structure:
    START -> _start -> [entry_router]

    Entry routing:
    - If awaiting_confirmation -> confirmation_response
    - If Q&A mode active -> continuation_detection
    - If mid-task with question -> intent_detection
    - If mid-task simple answer -> field_extraction
    - Otherwise -> intent_detection

    Core flow:
    field_extraction -> field_router -> question_generation -> END
    field_router -> confirmation_summary -> END (when complete)
    confirmation_response -> completion -> END (when approved)

    Q&A flow:
    intent_detection -> save_graph_position -> question_answering -> END
    continuation_detection -> restore_graph_position -> field_extraction
"""

import logging

from langgraph.graph import StateGraph, END

from framework.state.agent_state import AgentState
from framework.nodes.intent_detection import intent_detection_node
from framework.nodes.field_initialization import field_initialization_node
from framework.nodes.field_extraction import field_extraction_node
from framework.nodes.field_router import field_router_node
from framework.nodes.question_generation import question_generation_node
from framework.nodes.confirmation import (
    confirmation_summary_node,
    confirmation_response_node,
)
from framework.nodes.field_modification import field_modification_node
from framework.nodes.completion import completion_node
from framework.nodes.qa_nodes import (
    save_graph_position_node,
    restore_graph_position_node,
    continuation_detection_node,
    question_answering_node,
)
from framework.routing.conditional_edges import (
    route_after_field_extraction,
    route_after_field_router,
    route_after_intent_detection,
    route_after_continuation_detection,
    route_after_restore_graph_position,
    route_after_confirmation_response,
)

logger = logging.getLogger(__name__)


def _has_question_indicators(message: str) -> bool:
    """
    Check if a message has explicit question indicators.
    Helps make Q&A routing more restrictive.
    """
    message_lower = message.lower().strip()
    question_indicators = [
        "what", "how", "why", "when", "where", "who", "which",
        "can you", "could you", "would you", "will you",
        "do you", "does", "is there", "are there",
        "tell me", "explain", "describe",
        "?",
    ]
    return any(indicator in message_lower for indicator in question_indicators)


def route_entry_point(state: AgentState) -> str:
    """
    Smart entry point that routes based on conversation state.

    Routing Priority:
    1. Awaiting confirmation -> confirmation_response
    2. Q&A mode active -> continuation_detection
    3. Agent selected + mid-task -> field_extraction or intent_detection
    4. New conversation -> intent_detection
    """
    # Priority 1: Handle confirmation response
    if state.get("awaiting_confirmation"):
        logger.info("ENTRY | Awaiting confirmation -> confirmation_response")
        return "confirmation_response"

    # Priority 2: Handle Q&A mode
    if state.get("qa_mode_active"):
        logger.info("ENTRY | Q&A mode active -> continuation_detection")
        return "continuation_detection"

    # Priority 3: Agent selected and collecting fields
    if state.get("agent_id"):
        required_count = len(state.get("required_fields", []))

        # If fields not initialized, initialize them
        if required_count == 0:
            logger.info("ENTRY | Agent selected, initializing fields")
            return "field_initialization"

        # If collecting fields, route based on message content
        user_message = state.get("last_user_message", "")
        if _has_question_indicators(user_message):
            logger.info("ENTRY | Mid-task, question detected -> intent_detection")
            return "intent_detection"
        else:
            logger.info("ENTRY | Mid-task, simple answer -> field_extraction")
            return "field_extraction"

    # Priority 4: New conversation
    logger.info("ENTRY | New conversation -> intent_detection")
    return "intent_detection"


def _create_greeting_node(agent_def):
    """Create a greeting node that shows the agent's greeting and first question."""

    def greeting_node(state: AgentState, endpoint: str = "", verbose: bool = False) -> AgentState:
        """Show agent greeting combined with first uncollected field question."""
        greeting = agent_def.greeting

        # Find first uncollected required field
        collected = state.get("collected_fields", {})
        first_question = None
        for field in agent_def.required_fields:
            if field["name"] not in collected:
                first_question = field.get("question", f"Please provide your {field['name']}.")
                break

        if first_question and not greeting.rstrip().endswith("?"):
            message = f"{greeting}\n\n{first_question}" if first_question not in greeting else greeting
        else:
            message = greeting

        return {
            **state,
            "last_bot_message": message,
            "first_turn": False,
        }

    return greeting_node


def create_agent_graph(agent_def, endpoint: str = "http://localhost:8000", verbose: bool = False, checkpointer=None):
    """
    Creates a LangGraph workflow for a given agent definition.

    Args:
        agent_def: AgentDefinition from the registry
        endpoint: LLM service endpoint
        verbose: Enable verbose logging
        checkpointer: Optional LangGraph checkpointer for state persistence

    Returns:
        Compiled LangGraph workflow
    """
    logger.info(f"Creating graph for agent: {agent_def.name} (id={agent_def.id})")

    workflow = StateGraph(AgentState)

    # =========================================================================
    # Add all nodes
    # =========================================================================

    # Virtual start node for conditional entry
    workflow.add_node("_start", lambda s: s)

    # Field initialization (loads fields from agent.json)
    workflow.add_node(
        "field_initialization",
        lambda s: field_initialization_node(s, agent_def, verbose),
    )

    # Greeting node (agent-specific)
    greeting_fn = _create_greeting_node(agent_def)
    workflow.add_node("greeting", lambda s: greeting_fn(s, endpoint, verbose))

    # Q&A nodes
    workflow.add_node(
        "intent_detection",
        lambda s: intent_detection_node(s, endpoint, verbose),
    )
    workflow.add_node(
        "save_graph_position",
        lambda s: save_graph_position_node(s, verbose),
    )
    workflow.add_node(
        "continuation_detection",
        lambda s: continuation_detection_node(s, endpoint, verbose),
    )
    workflow.add_node(
        "restore_graph_position",
        lambda s: restore_graph_position_node(s, verbose),
    )
    workflow.add_node(
        "question_answering",
        lambda s: question_answering_node(s, endpoint, verbose),
    )

    # Core field collection nodes
    workflow.add_node(
        "field_extraction",
        lambda s: field_extraction_node(s, agent_def, endpoint, verbose),
    )
    workflow.add_node(
        "field_router",
        lambda s: field_router_node(s, verbose),
    )
    workflow.add_node(
        "question_generation",
        lambda s: question_generation_node(s, agent_def, endpoint, verbose),
    )

    # Confirmation nodes
    workflow.add_node(
        "confirmation_summary",
        lambda s: confirmation_summary_node(s, agent_def, verbose),
    )
    workflow.add_node(
        "confirmation_response",
        lambda s: confirmation_response_node(s, endpoint, verbose),
    )
    workflow.add_node(
        "field_modification",
        lambda s: field_modification_node(s, agent_def, endpoint, verbose),
    )

    # Completion
    workflow.add_node(
        "completion",
        lambda s: completion_node(s, agent_def, verbose),
    )

    # =========================================================================
    # Set entry point
    # =========================================================================

    workflow.set_entry_point("_start")

    # Entry routing
    workflow.add_conditional_edges(
        "_start",
        route_entry_point,
        {
            "confirmation_response": "confirmation_response",
            "continuation_detection": "continuation_detection",
            "intent_detection": "intent_detection",
            "field_initialization": "field_initialization",
            "field_extraction": "field_extraction",
        },
    )

    # =========================================================================
    # Q&A flow edges
    # =========================================================================

    workflow.add_conditional_edges(
        "intent_detection",
        route_after_intent_detection,
        {
            "save_graph_position": "save_graph_position",
            "restore_graph_position": "restore_graph_position",
            "field_extraction": "field_extraction",
        },
    )

    workflow.add_edge("save_graph_position", "question_answering")
    workflow.add_edge("question_answering", END)

    workflow.add_conditional_edges(
        "continuation_detection",
        route_after_continuation_detection,
        {
            "question_answering": "question_answering",
            "restore_graph_position": "restore_graph_position",
            "END": END,
        },
    )

    workflow.add_conditional_edges(
        "restore_graph_position",
        route_after_restore_graph_position,
        {
            "field_extraction": "field_extraction",
        },
    )

    # =========================================================================
    # Core field collection flow
    # =========================================================================

    # Field initialization -> field_extraction (extract from initial message)
    workflow.add_edge("field_initialization", "field_extraction")

    # Greeting -> END (wait for user)
    workflow.add_edge("greeting", END)

    # Field extraction -> field_router or greeting
    workflow.add_conditional_edges(
        "field_extraction",
        route_after_field_extraction,
        {
            "greeting": "greeting",
            "field_router": "field_router",
        },
    )

    # Field router -> question_generation or confirmation_summary
    workflow.add_conditional_edges(
        "field_router",
        route_after_field_router,
        {
            "confirmation_summary": "confirmation_summary",
            "question_generation": "question_generation",
        },
    )

    # Question generation -> END (wait for user)
    workflow.add_edge("question_generation", END)

    # =========================================================================
    # Confirmation flow
    # =========================================================================

    workflow.add_edge("confirmation_summary", END)

    workflow.add_conditional_edges(
        "confirmation_response",
        route_after_confirmation_response,
        {
            "completion": "completion",
            "field_modification": "field_modification",
            "confirmation_response": "confirmation_response",
        },
    )

    workflow.add_edge("field_modification", "confirmation_summary")

    # =========================================================================
    # Completion
    # =========================================================================

    workflow.add_edge("completion", END)

    # =========================================================================
    # Compile
    # =========================================================================

    compiled = workflow.compile(checkpointer=checkpointer)
    logger.info(f"Agent graph created: {len(workflow.nodes)} nodes (checkpointer={'yes' if checkpointer else 'no'})")

    return compiled
