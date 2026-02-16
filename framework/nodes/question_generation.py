"""
Question Generation Node

Generates natural language questions to collect the next required field.
Uses the agent definition for question templates and the LLM for
natural phrasing with acknowledgment of previously collected fields.
"""

import logging
import httpx

from framework.state.agent_state import AgentState
from framework.config.agent_registry import AgentDefinition
from framework.config.constants import LLM_TIMEOUT_CLASSIFICATION

logger = logging.getLogger(__name__)

LLM_TIMEOUT = LLM_TIMEOUT_CLASSIFICATION


def question_generation_node(
    state: AgentState,
    agent_def: AgentDefinition,
    endpoint: str = "http://localhost:8000",
    verbose: bool = False,
) -> AgentState:
    """
    Generate a natural question for the next uncollected field.

    This node:
    1. Acknowledges newly extracted fields
    2. Determines the next field to ask about
    3. Generates a natural question using the agent's persona

    Args:
        state: Current AgentState
        agent_def: AgentDefinition with field configurations
        endpoint: LLM service endpoint
        verbose: Enable verbose logging

    Returns:
        AgentState: Updated with last_bot_message containing the question
    """
    expected_field = state.get("expected_field")
    newly_extracted = state.get("newly_extracted_this_turn", {})
    validation_errors = state.get("validation_errors", {})

    # Handle validation error - re-ask with error message
    if validation_errors:
        error_field = list(validation_errors.keys())[0]
        error_msg = validation_errors[error_field]
        field_def = agent_def.get_field_by_name(error_field)
        question = field_def.get("question", f"Please provide your {error_field}.") if field_def else f"Please provide your {error_field}."

        message = f"I'm sorry, that doesn't seem right: {error_msg}. {question}"

        if verbose:
            logger.info(f"QUESTION | Validation error for {error_field}: {error_msg}")

        return {
            **state,
            "last_bot_message": message,
            "expected_field": error_field,
        }

    # Get the next field to ask about
    if not expected_field:
        missing = state.get("missing_fields", [])
        if missing:
            expected_field = missing[0]["name"]

    if not expected_field:
        return {
            **state,
            "last_bot_message": "I think we have everything we need!",
        }

    # Get field question from agent definition
    field_def = agent_def.get_field_by_name(expected_field)
    base_question = field_def.get("question", f"What is your {expected_field}?") if field_def else f"What is your {expected_field}?"

    # Build response: acknowledgment + question
    message = _build_response(newly_extracted, base_question, agent_def, state)

    # Add optional field indicator
    is_optional = state.get("optional_field_mode", False)
    if is_optional and field_def and not field_def.get("required", True):
        if "optional" not in message.lower() and "skip" not in message.lower():
            message += " (You can say 'skip' if you'd prefer not to answer.)"

    if verbose:
        logger.info(f"QUESTION | Field: {expected_field}")
        logger.info(f"QUESTION | Message: {message}")

    return {
        **state,
        "last_bot_message": message,
        "expected_field": expected_field,
    }


def _build_response(newly_extracted: dict, question: str, agent_def: AgentDefinition, state: AgentState) -> str:
    """Build response with acknowledgment of extracted fields + next question."""
    if not newly_extracted:
        return question

    # Simple acknowledgment
    ack_parts = []
    for field_name, value in newly_extracted.items():
        field_def = agent_def.get_field_by_name(field_name)
        display_name = field_def.get("description", field_name) if field_def else field_name
        ack_parts.append(f"{display_name}: {value}")

    if len(ack_parts) == 1:
        ack = "Got it, thanks!"
    else:
        ack = "Great, I've noted that down."

    # Add voice mode connector if applicable
    voice_mode = state.get("voice_mode", False)
    if voice_mode:
        return f"{ack} {question}"
    else:
        return f"{ack}\n\n{question}"
