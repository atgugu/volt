"""
Agent Factory - Generate agent configurations from natural language prompts.

Uses the local LLM to produce a valid agent.json from a user description,
then validates and writes it to disk.
"""

import json
import logging
import re
import os
from pathlib import Path
from typing import Dict, Any, Tuple

import requests

from framework.config.agent_registry import _validate_agent_config

logger = logging.getLogger(__name__)

# Validator types that can be auto-assigned from field context
_VALIDATOR_HINTS = {
    "email": "email",
    "phone": "phone",
    "name": "name",
    "full_name": "name",
    "first_name": "name",
    "last_name": "name",
    "age": "number",
    "count": "number",
    "quantity": "number",
    "amount": "number",
    "price": "number",
    "number": "number",
    "size": "number",
    "years": "number",
}

_META_PROMPT = r"""You are a configuration generator. Create an agent.json for a conversational bot.

SCHEMA:
- name: Display name (string)
- id: snake_case identifier (string)
- description: What this agent does (string)
- greeting: First message shown to user (string, should mention purpose and ask first question)
- persona: Personality description (string)
- fields: Array of field objects (see below)
- completion.message: Template with {field_name} placeholders
- completion.action: "log" (default)

FIELD SCHEMA:
- name: snake_case identifier (required)
- type: "string" | "number" | "boolean" | "text" (required)
- required: true | false (default: true)
- order: integer starting from 0 (required)
- description: Human-readable label (required)
- question: The question to ask the user (required)
- validator: "name" | "email" | "phone" | "number" | "text" | null
- validator_config: {"min": N, "max": N} for number validators
- extraction_hints: Array of keywords to help extraction

VALIDATOR REFERENCE:
- "name" validates names (letters, spaces, hyphens, 2-100 chars)
- "email" validates email format
- "phone" validates phone numbers (7-15 digits)
- "number" validates numeric ranges (use validator_config for min/max)
- "text" validates text length (1-5000 chars)
- null means no validation (for simple strings)

EXAMPLE:
{
  "name": "User Profile Collection",
  "id": "profile_collector",
  "description": "Collects user profile information through a friendly conversation",
  "greeting": "Hi! I'd like to help set up your profile. What's your name?",
  "persona": "friendly and professional assistant",
  "fields": [
    {
      "name": "full_name",
      "type": "string",
      "required": true,
      "order": 0,
      "description": "User's full name",
      "question": "What is your full name?",
      "validator": "name",
      "extraction_hints": ["name", "called", "I'm", "I am"]
    },
    {
      "name": "email",
      "type": "string",
      "required": true,
      "order": 1,
      "description": "User's email address",
      "question": "What is your email address?",
      "validator": "email"
    },
    {
      "name": "age",
      "type": "number",
      "required": false,
      "order": 2,
      "description": "User's age",
      "question": "How old are you? Feel free to skip this one if you prefer.",
      "validator": "number",
      "validator_config": {"min": 13, "max": 120}
    }
  ],
  "completion": {
    "message": "Your profile has been created successfully, {full_name}! We'll send a confirmation to {email}.",
    "action": "log"
  }
}

RULES:
- Use snake_case for id and field names
- Set appropriate validators for each field type
- Mark truly optional fields as required: false
- Include extraction_hints for non-obvious fields
- Greeting should mention the purpose AND ask the first question
- Completion message should use {field_name} placeholders for key fields
- Order fields logically (most important first)
- Return ONLY valid JSON, no explanation

USER REQUEST:
%s

JSON:"""


def _slugify(text: str) -> str:
    """Convert text to a snake_case slug suitable for an agent ID."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s_]", "", text)
    text = re.sub(r"[\s]+", "_", text)
    text = re.sub(r"_+", "_", text)
    text = text.strip("_")
    return text or "custom_agent"


def _extract_json(text: str) -> Dict[str, Any]:
    """Extract JSON from LLM response, handling markdown code blocks."""
    # Try direct parse first
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code blocks
    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try finding the outermost { ... } block
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError("Could not extract valid JSON from LLM response")


def _auto_assign_validator(field: Dict[str, Any]) -> None:
    """Auto-assign a validator based on field name and type if not set."""
    if field.get("validator"):
        return

    name = field.get("name", "").lower()
    field_type = field.get("type", "string")

    # Check name-based hints
    for hint_key, validator in _VALIDATOR_HINTS.items():
        if hint_key in name:
            field["validator"] = validator
            return

    # Fallback: type-based
    if field_type == "number":
        field["validator"] = "number"
    elif field_type == "text":
        field["validator"] = "text"


def _fixup_config(config: Dict[str, Any], user_prompt: str) -> Dict[str, Any]:
    """Fix common issues in LLM-generated configs."""
    # Ensure required top-level keys
    if "name" not in config:
        config["name"] = user_prompt[:60].strip().title()
    if "id" not in config or not re.match(r"^[a-z][a-z0-9_]*$", config.get("id", "")):
        config["id"] = _slugify(config.get("name", user_prompt[:40]))
    if "description" not in config:
        config["description"] = user_prompt[:200].strip()
    if "fields" not in config:
        config["fields"] = []

    # Ensure greeting exists
    if "greeting" not in config:
        config["greeting"] = f"Hello! I'm here to help with {config['name'].lower()}. Let's get started!"
    if "persona" not in config:
        config["persona"] = "friendly and professional assistant"

    # Fix fields
    seen_names = set()
    for i, field in enumerate(config.get("fields", [])):
        # Ensure required field keys
        if "name" not in field:
            field["name"] = f"field_{i}"
        if "type" not in field:
            field["type"] = "string"
        if "question" not in field:
            field["question"] = f"Please provide your {field['name'].replace('_', ' ')}."

        # Auto-assign order
        if "order" not in field:
            field["order"] = i

        # Auto-assign description
        if "description" not in field:
            field["description"] = field["name"].replace("_", " ").title()

        # Auto-assign validator
        _auto_assign_validator(field)

        # Deduplicate names
        base_name = field["name"]
        if base_name in seen_names:
            suffix = 2
            while f"{base_name}_{suffix}" in seen_names:
                suffix += 1
            field["name"] = f"{base_name}_{suffix}"
        seen_names.add(field["name"])

    # Ensure completion block
    if "completion" not in config:
        config["completion"] = {
            "message": "Thank you! All information has been collected.",
            "action": "log",
        }
    elif "message" not in config["completion"]:
        config["completion"]["message"] = "Thank you! All information has been collected."
    if "action" not in config.get("completion", {}):
        config["completion"]["action"] = "log"

    return config


def _resolve_id_conflict(agent_id: str, agents_dir: Path) -> str:
    """If an agent directory with this ID already exists, append a numeric suffix."""
    if not (agents_dir / agent_id).exists():
        return agent_id

    suffix = 2
    while (agents_dir / f"{agent_id}_{suffix}").exists():
        suffix += 1
    return f"{agent_id}_{suffix}"


def generate_agent(
    prompt: str,
    endpoint: str,
    agents_dir: str,
) -> Tuple[Dict[str, Any], Path]:
    """
    Generate a complete agent from a natural language prompt.

    Args:
        prompt: Natural language description of the desired agent
        endpoint: LLM service base URL (e.g. http://localhost:8000)
        agents_dir: Path to the agents/ directory

    Returns:
        Tuple of (agent_config_dict, agent_directory_path)

    Raises:
        ValueError: If the LLM output cannot be parsed or validated
        requests.RequestException: If the LLM service is unreachable
    """
    agents_path = Path(agents_dir)

    # Build the meta-prompt
    full_prompt = _META_PROMPT % prompt

    # Call the LLM
    logger.info(f"Generating agent from prompt: {prompt[:80]}...")
    response = requests.post(
        f"{endpoint}/generate",
        json={
            "prompt": full_prompt,
            "max_tokens": 2048,
            "temperature": 0.4,
            "top_p": 0.9,
            "stop": None,
        },
        timeout=120,
    )
    response.raise_for_status()

    result = response.json()
    raw_text = result.get("text", result.get("content", result.get("response", "")))

    if not raw_text:
        raise ValueError("LLM returned empty response")

    logger.debug(f"Raw LLM response: {raw_text[:500]}...")

    # Parse and fix
    config = _extract_json(raw_text)
    config = _fixup_config(config, prompt)

    # Resolve ID conflicts
    config["id"] = _resolve_id_conflict(config["id"], agents_path)

    # Validate
    errors = _validate_agent_config(config, agents_path / config["id"])
    if errors:
        raise ValueError(f"Generated config failed validation: {errors}")

    # Write to disk
    agent_dir = agents_path / config["id"]
    agent_dir.mkdir(parents=True, exist_ok=True)

    config_path = agent_dir / "agent.json"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    logger.info(f"Agent '{config['name']}' (id={config['id']}) written to {agent_dir}")
    return config, agent_dir
