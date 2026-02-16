"""
Field Initialization Node

Loads required, optional, and conditional fields from the agent definition.
Establishes the field collection roadmap for the conversation.
"""

import logging

from framework.state.agent_state import AgentState
from framework.config.agent_registry import AgentDefinition

logger = logging.getLogger(__name__)


def field_initialization_node(state: AgentState, agent_def: AgentDefinition, verbose: bool = False) -> AgentState:
    """
    Loads field definitions from agent.json into state.

    This node:
    1. Reads field definitions from the agent definition
    2. Sorts fields by order
    3. Initializes field tracking in state

    Args:
        state: Current AgentState
        agent_def: AgentDefinition with field configurations
        verbose: Enable verbose logging

    Returns:
        AgentState: Updated with field lists initialized
    """
    if verbose:
        logger.info(f"FIELD_INIT | Agent: {agent_def.name} (id={agent_def.id})")

    required_fields = sorted(agent_def.required_fields, key=lambda x: x.get("order", 999))
    optional_fields = sorted(agent_def.optional_fields, key=lambda x: x.get("order", 999))
    conditional_fields = sorted(agent_def.conditional_fields, key=lambda x: x.get("order", 999))

    if verbose:
        logger.info(f"FIELD_INIT | Required: {len(required_fields)}")
        logger.info(f"FIELD_INIT | Optional: {len(optional_fields)}")
        logger.info(f"FIELD_INIT | Conditional: {len(conditional_fields)}")
        req_names = [f["name"] for f in required_fields]
        logger.info(f"FIELD_INIT | Required fields: {req_names}")

    return {
        **state,
        "agent_id": agent_def.id,
        "agent_name": agent_def.name,
        "required_fields": required_fields,
        "optional_fields": optional_fields,
        "conditional_fields": conditional_fields,
        "active_conditional_fields": [],
        "current_field_index": 0,
    }


def get_all_field_names(state: AgentState) -> list:
    """Get all field names for the current agent."""
    names = []
    names.extend([f["name"] for f in state.get("required_fields", [])])
    names.extend([f["name"] for f in state.get("optional_fields", [])])
    names.extend([f["name"] for f in state.get("conditional_fields", [])])
    return names


def get_field_by_name(state: AgentState, field_name: str) -> dict:
    """Get field definition by name."""
    all_fields = (
        state.get("required_fields", [])
        + state.get("optional_fields", [])
        + state.get("conditional_fields", [])
    )
    for field in all_fields:
        if field["name"] == field_name:
            return field
    return None
