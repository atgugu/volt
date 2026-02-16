"""
Field Modification Node

Handles user requests to modify a previously collected field.
Clears the field value and sets up re-collection.
"""

import logging
import re
from typing import Any

from framework.state.agent_state import AgentState
from framework.config.agent_registry import AgentDefinition

logger = logging.getLogger(__name__)


def field_modification_node(
    state: AgentState,
    agent_def: AgentDefinition,
    endpoint: str = "http://localhost:8000",
    verbose: bool = False,
) -> AgentState:
    """
    Handle a field modification request.

    This node:
    1. Identifies which field to modify
    2. Checks if the new value is in the user's message
    3. Either extracts the new value or asks for it

    Args:
        state: Current AgentState
        agent_def: AgentDefinition with field configurations
        endpoint: LLM service endpoint
        verbose: Enable verbose logging

    Returns:
        AgentState: Updated with cleared field for re-collection
    """
    field_to_modify = state.get("field_modification_request")

    if not field_to_modify:
        logger.warning("MODIFY | No field_modification_request set")
        return state

    collected = dict(state.get("collected_fields", {}))
    user_message = state.get("last_user_message", "")

    if verbose:
        logger.info(f"MODIFY | Field: {field_to_modify}")
        logger.info(f"MODIFY | Current value: {collected.get(field_to_modify)}")

    # Try to extract new value from the modification message
    new_value = _extract_new_value(user_message, field_to_modify, agent_def)

    if new_value:
        # User provided new value in the same message
        collected[field_to_modify] = new_value

        if verbose:
            logger.info(f"MODIFY | New value extracted: {new_value}")

        return {
            **state,
            "collected_fields": collected,
            "field_modification_request": None,
            "awaiting_confirmation": True,
        }

    # Clear the field and ask for new value
    old_value = collected.pop(field_to_modify, None)

    field_def = agent_def.get_field_by_name(field_to_modify)
    display_name = field_def.get("description", field_to_modify) if field_def else field_to_modify
    question = field_def.get("question", f"What should the new {display_name} be?") if field_def else f"What should the new {display_name} be?"

    message = f"Sure, I'll update your {display_name}. The current value is '{old_value}'. {question}"

    return {
        **state,
        "collected_fields": collected,
        "field_modification_request": None,
        "awaiting_confirmation": False,
        "is_complete": False,
        "expected_field": field_to_modify,
        "last_bot_message": message,
    }


def _extract_new_value(message: str, field_name: str, agent_def: AgentDefinition) -> Any:
    """
    Try to extract a new value from the modification message.

    Looks for patterns like:
    - "change name to John Smith"
    - "update email to john@example.com"
    - "my phone is actually 555-1234"
    """
    msg_lower = message.lower()

    # Pattern: "change X to Y" / "update X to Y"
    to_match = re.search(r'(?:change|update|set|make)\s+\w+\s+to\s+(.+)', msg_lower)
    if to_match:
        new_val = to_match.group(1).strip().rstrip(".")
        if new_val:
            return new_val

    # Pattern: "actually it's Y" / "it should be Y"
    actually_match = re.search(r'(?:actually|should be|it\'?s)\s+(.+)', msg_lower)
    if actually_match:
        new_val = actually_match.group(1).strip().rstrip(".")
        if new_val:
            return new_val

    return None
