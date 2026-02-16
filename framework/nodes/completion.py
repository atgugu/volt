"""
Completion Node

Handles the final step when all fields are collected and confirmed.
Uses the agent definition's completion template and action hook.
"""

import logging
import json

from framework.state.agent_state import AgentState
from framework.config.agent_registry import AgentDefinition

logger = logging.getLogger(__name__)


def completion_node(
    state: AgentState,
    agent_def: AgentDefinition,
    verbose: bool = False,
) -> AgentState:
    """
    Complete the agent's task after all fields are collected and confirmed.

    This node:
    1. Formats the completion message using collected fields
    2. Executes the completion action (log, webhook, custom)
    3. Marks the conversation as complete

    Args:
        state: Current AgentState
        agent_def: AgentDefinition with completion configuration
        verbose: Enable verbose logging

    Returns:
        AgentState: Updated with completion message and is_complete=True
    """
    collected = state.get("collected_fields", {})

    # Format completion message
    template = agent_def.completion_message
    try:
        message = template.format(**collected)
    except KeyError as e:
        logger.warning(f"COMPLETION | Missing field in template: {e}")
        message = template  # Use raw template if formatting fails

    # Execute completion action
    action = agent_def.completion_action
    result_data = _execute_action(action, collected, agent_def, verbose)

    if verbose:
        logger.info(f"COMPLETION | Action: {action}")
        logger.info(f"COMPLETION | Message: {message}")
        logger.info(f"COMPLETION | Result: {result_data}")

    return {
        **state,
        "last_bot_message": message,
        "is_complete": True,
        "result_data": result_data,
    }


def _execute_action(action: str, collected: dict, agent_def: AgentDefinition, verbose: bool) -> dict:
    """
    Execute the completion action defined in agent.json.

    Supported actions:
    - "log": Log collected data (default)
    - "webhook:<url>": POST data to a webhook URL
    - "custom": Call agent's custom_nodes.on_complete() if defined

    Returns:
        dict: Result data from the action
    """
    if action == "log":
        logger.info(f"COMPLETION | Collected data: {json.dumps(collected, indent=2)}")
        return {"action": "log", "status": "success", "data": collected}

    if action.startswith("webhook:"):
        url = action[8:]
        return _send_webhook(url, collected, verbose)

    if action == "custom":
        custom = agent_def.custom_nodes
        if custom and hasattr(custom, "on_complete"):
            try:
                return custom.on_complete(collected)
            except Exception as e:
                logger.error(f"COMPLETION | Custom action error: {e}")
                return {"action": "custom", "status": "error", "error": str(e)}

    # Default: log
    logger.info(f"COMPLETION | Collected data: {json.dumps(collected, indent=2)}")
    return {"action": action, "status": "success", "data": collected}


def _send_webhook(url: str, data: dict, verbose: bool) -> dict:
    """Send collected data to a webhook URL."""
    try:
        import httpx
        response = httpx.post(url, json=data, timeout=30.0)
        response.raise_for_status()

        if verbose:
            logger.info(f"COMPLETION | Webhook response: {response.status_code}")

        return {
            "action": "webhook",
            "status": "success",
            "status_code": response.status_code,
            "response": response.text[:500],
        }
    except Exception as e:
        logger.error(f"COMPLETION | Webhook error: {e}")
        return {"action": "webhook", "status": "error", "error": str(e)}
