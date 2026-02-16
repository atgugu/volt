"""
Field Extraction Node

Extracts field values from user messages using a dual-path approach:
1. Fast-path regex extraction for simple responses (emails, phones, numbers)
2. LLM-based extraction for complex responses

This dual-path provides 2000x speedup for simple responses while
maintaining accuracy for complex multi-field messages.
"""

import logging
import re
import json
import httpx
from typing import Any

from framework.state.agent_state import AgentState
from framework.config.agent_registry import AgentDefinition
from framework.config.constants import LLM_TIMEOUT_EXTRACTION
from framework.nlp.regex_extractor import RegexExtractor
from framework.logic.validators import get_validator

logger = logging.getLogger(__name__)

LLM_TIMEOUT = LLM_TIMEOUT_EXTRACTION

_regex_extractor = RegexExtractor()


def field_extraction_node(
    state: AgentState,
    agent_def: AgentDefinition,
    endpoint: str = "http://localhost:8000",
    verbose: bool = False,
) -> AgentState:
    """
    Extract field values from the user's message.

    Uses fast-path regex for simple responses and LLM for complex ones.

    Args:
        state: Current AgentState
        agent_def: AgentDefinition with field configurations
        endpoint: LLM service endpoint
        verbose: Enable verbose logging

    Returns:
        AgentState: Updated with newly extracted fields
    """
    user_message = state.get("last_user_message", "").strip()
    if not user_message:
        return state

    collected = dict(state.get("collected_fields", {}))
    expected_field = state.get("expected_field")
    newly_extracted = {}

    # Check for bypass/skip indicators
    if _is_skip_response(user_message) and expected_field:
        field_def = agent_def.get_field_by_name(expected_field)
        if field_def and not field_def.get("required", True):
            if verbose:
                logger.info(f"EXTRACT | User skipped optional field: {expected_field}")
            declined = list(state.get("declined_optional_fields", []))
            declined.append(expected_field)
            return {
                **state,
                "declined_optional_fields": declined,
                "newly_extracted_this_turn": {},
                "retry_count": 0,
            }

    # Determine which fields to extract
    fields_to_extract = _get_fields_to_extract(state, agent_def)

    if verbose:
        logger.info(f"EXTRACT | Message: '{user_message}'")
        logger.info(f"EXTRACT | Expected field: {expected_field}")
        logger.info(f"EXTRACT | Fields to extract: {[f['name'] for f in fields_to_extract]}")

    # Try fast-path regex extraction first
    if expected_field:
        regex_result = _try_regex_extraction(user_message, expected_field, agent_def)
        if regex_result is not None:
            if verbose:
                logger.info(f"EXTRACT | Fast-path regex: {expected_field} = {regex_result}")
            newly_extracted[expected_field] = regex_result

    # If regex didn't extract the expected field, try LLM
    if expected_field and expected_field not in newly_extracted:
        llm_results = _try_llm_extraction(
            user_message, fields_to_extract, agent_def, endpoint, verbose
        )
        newly_extracted.update(llm_results)

    # Validate extracted fields
    validated = {}
    validation_errors = dict(state.get("validation_errors", {}))

    for field_name, value in newly_extracted.items():
        is_valid, error_msg = _validate_field(field_name, value, agent_def)
        if is_valid:
            validated[field_name] = value
            validation_errors.pop(field_name, None)
        else:
            if verbose:
                logger.info(f"EXTRACT | Validation failed: {field_name} = {value} ({error_msg})")
            validation_errors[field_name] = error_msg

    # Merge with collected fields
    collected.update(validated)

    if verbose:
        logger.info(f"EXTRACT | Newly extracted: {validated}")
        logger.info(f"EXTRACT | Total collected: {list(collected.keys())}")

    return {
        **state,
        "collected_fields": collected,
        "newly_extracted_this_turn": validated,
        "validation_errors": validation_errors,
        "retry_count": 0 if validated else state.get("retry_count", 0) + 1,
    }


def _get_fields_to_extract(state: AgentState, agent_def: AgentDefinition) -> list:
    """Get list of fields that still need extraction."""
    collected = state.get("collected_fields", {})
    all_fields = agent_def.fields
    return [f for f in all_fields if f["name"] not in collected]


def _is_skip_response(message: str) -> bool:
    """Check if user is trying to skip a field."""
    skip_patterns = [
        r"^(skip|pass|next|no thanks|none|n/a|na|nah|no)$",
        r"^(i('d| would) rather not|prefer not to|don'?t want to)$",
        r"^(skip (this|that|it)|move on|let'?s skip)$",
    ]
    msg_lower = message.lower().strip()
    return any(re.match(pattern, msg_lower) for pattern in skip_patterns)


def _try_regex_extraction(message: str, expected_field: str, agent_def: AgentDefinition) -> Any:
    """
    Try fast-path regex extraction for the expected field.
    Returns extracted value or None if regex can't handle it.

    Delegates to the shared RegexExtractor to avoid duplicating patterns.
    """
    field_def = agent_def.get_field_by_name(expected_field)
    if not field_def:
        return None

    field_type = field_def.get("type", "string")
    validator = field_def.get("validator", "")

    return _regex_extractor.try_extract(message, expected_field, field_type, validator)


def _try_llm_extraction(
    message: str,
    fields_to_extract: list,
    agent_def: AgentDefinition,
    endpoint: str,
    verbose: bool,
) -> dict:
    """Extract fields using LLM when regex can't handle it."""
    if not fields_to_extract:
        return {}

    # Build field descriptions for the prompt
    field_descriptions = []
    for field in fields_to_extract:
        desc = f"- {field['name']}: {field.get('description', field['name'])} (type: {field.get('type', 'string')})"
        if field.get("extraction_hints"):
            desc += f" [hints: {', '.join(field['extraction_hints'])}]"
        field_descriptions.append(desc)

    field_list = "\n".join(field_descriptions)
    field_names = [f["name"] for f in fields_to_extract]

    prompt = f"""Extract information from the user's message. Return ONLY a JSON object with the extracted fields.

Fields to extract:
{field_list}

User message: "{message}"

Rules:
- Only include fields that are clearly mentioned in the message
- Use null for fields not mentioned
- Return valid JSON only, no explanation

JSON:"""

    try:
        response = httpx.post(
            f"{endpoint}/generate",
            json={
                "prompt": prompt,
                "max_tokens": 256,
                "temperature": 0.1,
                "stop": ["\n\n", "```"],
            },
            timeout=LLM_TIMEOUT,
        )
        response.raise_for_status()

        result_text = response.json().get("text", "").strip()

        # Parse JSON from response
        extracted = _parse_json_response(result_text, field_names)

        if verbose:
            logger.info(f"EXTRACT | LLM raw: {result_text}")
            logger.info(f"EXTRACT | LLM parsed: {extracted}")

        return extracted

    except Exception as e:
        logger.error(f"EXTRACT | LLM extraction error: {e}")
        return {}


def _parse_json_response(text: str, valid_fields: list) -> dict:
    """Parse JSON from LLM response, filtering to valid fields."""
    # Try direct parse
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if k in valid_fields and v is not None}
    except json.JSONDecodeError:
        pass

    # Try extracting JSON from markdown code block
    json_match = re.search(r'\{[^}]+\}', text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            if isinstance(data, dict):
                return {k: v for k, v in data.items() if k in valid_fields and v is not None}
        except json.JSONDecodeError:
            pass

    return {}


def _validate_field(field_name: str, value: Any, agent_def: AgentDefinition) -> tuple:
    """
    Validate a field value using the configured validator.

    Returns:
        (is_valid, error_message) tuple
    """
    field_def = agent_def.get_field_by_name(field_name)
    if not field_def:
        return True, None

    validator_name = field_def.get("validator")
    if not validator_name:
        return True, None

    validator_config = field_def.get("validator_config", {})

    validator = get_validator(validator_name)
    if validator:
        return validator.validate(value, **validator_config)

    return True, None
