"""
Confirmation Nodes

Handles the confirmation workflow:
1. confirmation_summary_node: Shows collected fields and asks for confirmation
2. confirmation_response_node: Processes user's response (approve/modify/re-ask)
"""

import logging
import httpx

from framework.state.agent_state import AgentState
from framework.config.agent_registry import AgentDefinition
from framework.config.constants import LLM_TIMEOUT_CLASSIFICATION, DEFAULT_CONFIRMATION_MAX_ATTEMPTS

logger = logging.getLogger(__name__)

LLM_TIMEOUT = LLM_TIMEOUT_CLASSIFICATION


def confirmation_summary_node(
    state: AgentState,
    agent_def: AgentDefinition,
    verbose: bool = False,
) -> AgentState:
    """
    Generate a summary of collected fields for user confirmation.

    Args:
        state: Current AgentState
        agent_def: AgentDefinition with field configurations
        verbose: Enable verbose logging

    Returns:
        AgentState: Updated with confirmation summary message
    """
    collected = state.get("collected_fields", {})

    # Build summary
    lines = ["Here's a summary of the information you've provided:\n"]

    for field in agent_def.fields:
        name = field["name"]
        if name in collected and collected[name] is not None:
            display_name = field.get("description", name).title()
            value = collected[name]

            if isinstance(value, bool):
                value = "Yes" if value else "No"

            lines.append(f"  - **{display_name}**: {value}")

    lines.append("\nDoes everything look correct? (yes to confirm, or tell me what to change)")

    message = "\n".join(lines)

    if verbose:
        logger.info(f"CONFIRM | Summary with {len(collected)} fields")

    return {
        **state,
        "last_bot_message": message,
        "awaiting_confirmation": True,
        "confirmation_attempts": state.get("confirmation_attempts", 0) + 1,
    }


def confirmation_response_node(
    state: AgentState,
    endpoint: str = "http://localhost:8000",
    verbose: bool = False,
) -> AgentState:
    """
    Process user's response to the confirmation summary.

    Detects:
    - Approval (yes, confirm, looks good)
    - Modification request (change X to Y)
    - Unclear response (re-ask)

    Args:
        state: Current AgentState
        endpoint: LLM service endpoint
        verbose: Enable verbose logging

    Returns:
        AgentState: Updated with confirmation decision
    """
    user_message = state.get("last_user_message", "").strip().lower()

    # Check for simple approval
    approval_patterns = [
        "yes", "y", "yeah", "yep", "correct", "confirm", "looks good",
        "that's right", "perfect", "good", "ok", "okay", "sure",
        "approved", "all good", "go ahead",
    ]

    if any(pattern in user_message for pattern in approval_patterns):
        if verbose:
            logger.info("CONFIRM | User approved")
        return {
            **state,
            "awaiting_confirmation": False,
            "field_modification_request": None,
        }

    # Check for modification request using LLM
    modification_field = _detect_modification(state, endpoint, verbose)

    if modification_field:
        if verbose:
            logger.info(f"CONFIRM | Modification requested: {modification_field}")
        return {
            **state,
            "field_modification_request": modification_field,
        }

    # Unclear response - re-ask
    max_attempts = DEFAULT_CONFIRMATION_MAX_ATTEMPTS
    attempts = state.get("confirmation_attempts", 0)

    if attempts >= max_attempts:
        # After max attempts, auto-approve
        if verbose:
            logger.info("CONFIRM | Max attempts reached, auto-approving")
        return {
            **state,
            "awaiting_confirmation": False,
            "field_modification_request": None,
        }

    return {
        **state,
        "last_bot_message": "I didn't quite catch that. Could you confirm if everything looks correct? (yes/no)",
    }


def _detect_modification(state: AgentState, endpoint: str, verbose: bool) -> str:
    """Detect which field the user wants to modify."""
    user_message = state.get("last_user_message", "")
    collected = state.get("collected_fields", {})

    # Simple keyword matching for field names
    msg_lower = user_message.lower()
    for field_name in collected:
        # Check if field name or common variants appear in message
        readable = field_name.replace("_", " ")
        if readable in msg_lower or field_name in msg_lower:
            return field_name

    # Check for "change", "update", "modify" patterns
    change_words = ["change", "update", "modify", "fix", "correct", "wrong"]
    has_change_intent = any(word in msg_lower for word in change_words)

    if not has_change_intent:
        return None

    # Use LLM to detect which field
    field_names = list(collected.keys())
    prompt = f"""The user wants to modify one of these fields: {field_names}

User message: "{user_message}"

Which field does the user want to change? Reply with ONLY the field name, or "none" if unclear."""

    try:
        response = httpx.post(
            f"{endpoint}/generate",
            json={"prompt": prompt, "max_tokens": 50, "temperature": 0.1},
            timeout=LLM_TIMEOUT,
        )
        response.raise_for_status()
        result = response.json().get("text", "").strip().lower()

        for field_name in field_names:
            if field_name in result:
                return field_name

    except Exception as e:
        logger.error(f"CONFIRM | Modification detection error: {e}")

    return None
