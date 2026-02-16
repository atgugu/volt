"""
Field Router Node

Determines which field to ask for next, checks completion status,
and manages optional field collection mode.

This is the CENTRAL routing node that prevents re-asking bugs
through explicit field calculation.
"""

import logging

from framework.state.agent_state import AgentState

logger = logging.getLogger(__name__)


def field_router_node(state: AgentState, verbose: bool = False) -> AgentState:
    """
    Calculate missing fields and determine next step.

    This node:
    1. Calculates which required fields are still missing
    2. Evaluates conditional fields
    3. Determines if collection is complete
    4. Sets the next field to ask about

    Args:
        state: Current AgentState
        verbose: Enable verbose logging

    Returns:
        AgentState: Updated with missing_fields, is_complete, expected_field
    """
    collected = state.get("collected_fields", {})
    required_fields = state.get("required_fields", [])
    optional_fields = state.get("optional_fields", [])
    optional_mode = state.get("optional_field_mode", False)
    declined = state.get("declined_optional_fields", [])

    # Calculate missing required fields
    missing_required = [
        f for f in required_fields
        if f["name"] not in collected or not collected[f["name"]]
    ]
    missing_required.sort(key=lambda f: f.get("order", 999))

    # Evaluate conditional fields
    conditional_fields = state.get("conditional_fields", [])
    active_conditionals = _evaluate_conditionals(conditional_fields, collected)
    missing_conditionals = [
        f for f in active_conditionals
        if f["name"] not in collected or not collected[f["name"]]
    ]

    # Combine all missing fields
    all_missing = missing_required + missing_conditionals

    if verbose:
        collected_names = list(collected.keys())
        missing_names = [f["name"] for f in all_missing]
        logger.info(f"FIELD_ROUTER | Collected: {collected_names}")
        logger.info(f"FIELD_ROUTER | Missing: {missing_names}")

    # Check if all required + conditional fields are collected
    if not all_missing:
        if not optional_mode and optional_fields:
            # Switch to optional field mode
            missing_optional = [
                f for f in optional_fields
                if f["name"] not in collected and f["name"] not in declined
            ]

            if missing_optional:
                missing_optional.sort(key=lambda f: f.get("order", 999))
                next_field = missing_optional[0]

                if verbose:
                    logger.info(f"FIELD_ROUTER | Switching to optional mode, next: {next_field['name']}")

                return {
                    **state,
                    "missing_fields": missing_optional,
                    "is_complete": False,
                    "optional_field_mode": True,
                    "expected_field": next_field["name"],
                    "active_conditional_fields": active_conditionals,
                }

        # All fields collected
        if verbose:
            logger.info("FIELD_ROUTER | All fields collected!")

        return {
            **state,
            "missing_fields": [],
            "is_complete": True,
            "active_conditional_fields": active_conditionals,
        }

    # Get next field to ask
    next_field = all_missing[0]
    completion_pct = _get_completion_percentage(state)

    if verbose:
        logger.info(f"FIELD_ROUTER | Next field: {next_field['name']} ({completion_pct}% complete)")

    return {
        **state,
        "missing_fields": all_missing,
        "is_complete": False,
        "expected_field": next_field["name"],
        "active_conditional_fields": active_conditionals,
    }


def _evaluate_conditionals(conditional_fields: list, collected: dict) -> list:
    """
    Evaluate which conditional fields should be active.

    Conditions in agent.json use format: "field_name == value"
    """
    active = []
    for field in conditional_fields:
        condition = field.get("condition", "")
        if not condition:
            continue

        try:
            # Parse simple conditions: "field_name == value"
            if "==" in condition:
                parts = condition.split("==")
                cond_field = parts[0].strip()
                cond_value = parts[1].strip().strip("'\"")

                actual_value = str(collected.get(cond_field, "")).strip()
                if actual_value.lower() == cond_value.lower():
                    active.append(field)

            elif "!=" in condition:
                parts = condition.split("!=")
                cond_field = parts[0].strip()
                cond_value = parts[1].strip().strip("'\"")

                actual_value = str(collected.get(cond_field, "")).strip()
                if actual_value.lower() != cond_value.lower():
                    active.append(field)

        except Exception as e:
            logger.warning(f"FIELD_ROUTER | Error evaluating condition '{condition}': {e}")

    return active


def _get_completion_percentage(state: AgentState) -> int:
    """Calculate field collection completion percentage."""
    required = len(state.get("required_fields", []))
    if required == 0:
        return 100

    collected = len([
        v for v in state.get("collected_fields", {}).values()
        if v is not None and v != ""
    ])
    return min(100, int((collected / required) * 100))


def get_next_field_to_ask(state: AgentState) -> dict:
    """Get the next field that needs to be collected."""
    missing = state.get("missing_fields", [])
    if missing:
        return missing[0]
    return None
