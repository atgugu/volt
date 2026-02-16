"""
Conditional Routing Functions

These functions determine which node to execute next based on the
current state. This is where the graph flow logic lives.

Explicit routing prevents re-asking bugs by ensuring:
1. Clear decision points
2. No implicit state confusion
3. Predictable flow control
"""

import logging

from framework.state.agent_state import AgentState

logger = logging.getLogger(__name__)


def route_after_field_extraction(state: AgentState) -> str:
    """
    Routes after field extraction node.

    Decision:
    - If first turn (greeting not yet shown) -> greeting
    - Else -> field_router (calculate missing fields and determine next step)
    """
    if state.get("first_turn"):
        logger.info("ROUTE | field_extraction -> greeting (first turn)")
        return "greeting"

    logger.info("ROUTE | field_extraction -> field_router")
    return "field_router"


def route_after_field_router(state: AgentState) -> str:
    """
    Routes after field_router node.

    Decision:
    - If complete -> confirmation_summary (get user confirmation)
    - If no next field but not complete -> question_generation (safety)
    - Else -> question_generation (ask next field)
    """
    if state.get("is_complete"):
        logger.info("ROUTE | field_router -> confirmation_summary")
        return "confirmation_summary"

    logger.info("ROUTE | field_router -> question_generation")
    return "question_generation"


def route_after_intent_detection(state: AgentState) -> str:
    """
    Routes after LLM-based intent detection node.

    Decision:
    - If should_enter_qa_mode -> save_graph_position (enter Q&A)
    - If has_task_info_in_qa -> restore_graph_position (return from Q&A)
    - If detected_intent is 'agent_task' -> field_extraction
    - If detected_intent is 'response' -> field_extraction
    - Default -> field_extraction
    """
    if state.get("should_enter_qa_mode"):
        logger.info("ROUTE | intent_detection -> save_graph_position (entering Q&A)")
        return "save_graph_position"

    if state.get("has_task_info_in_qa"):
        logger.info("ROUTE | intent_detection -> restore_graph_position (task info in Q&A)")
        return "restore_graph_position"

    logger.info("ROUTE | intent_detection -> field_extraction")
    return "field_extraction"


def route_after_continuation_detection(state: AgentState) -> str:
    """
    Routes after Q&A continuation detection.

    Decision:
    - If stay_in_qa_mode -> question_answering (ask more)
    - If exit_qa_mode -> restore_graph_position (resume task)
    - Else -> END (ambiguous, wait for clarification)
    """
    continuation_intent = state.get("continuation_intent", "")

    if state.get("stay_in_qa_mode") or continuation_intent == "ask_more":
        logger.info("ROUTE | continuation_detection -> question_answering (ask more)")
        return "question_answering"

    if state.get("exit_qa_mode") or continuation_intent in ["continue_task", "provide_info"]:
        logger.info("ROUTE | continuation_detection -> restore_graph_position (exit Q&A)")
        return "restore_graph_position"

    logger.info("ROUTE | continuation_detection -> END (ambiguous)")
    return "END"


def route_after_restore_graph_position(state: AgentState) -> str:
    """
    Routes after restoring graph position from Q&A mode.

    Decision:
    - If continuation_intent is 'provide_info' -> field_extraction
    - If agent selected -> field_extraction (resume)
    - Else -> field_extraction (default)
    """
    continuation_intent = state.get("continuation_intent", "")

    if continuation_intent == "provide_info":
        logger.info("ROUTE | restore_graph_position -> field_extraction (user provided info)")
        return "field_extraction"

    logger.info("ROUTE | restore_graph_position -> field_extraction (resume)")
    return "field_extraction"


def route_after_confirmation_response(state: AgentState) -> str:
    """
    Routes after user responds to confirmation summary.

    Decision:
    - If field_modification_request -> field_modification (user wants changes)
    - If awaiting_confirmation cleared -> completion (approved)
    - Else -> confirmation_response (re-ask for unclear response)
    """
    if state.get("field_modification_request"):
        logger.info("ROUTE | confirmation_response -> field_modification (modification requested)")
        return "field_modification"

    if not state.get("awaiting_confirmation"):
        logger.info("ROUTE | confirmation_response -> completion (approved)")
        return "completion"

    logger.info("ROUTE | confirmation_response -> confirmation_response (re-ask)")
    return "confirmation_response"
