"""
LLM-Based Field Extractor

Extracts structured field values from user messages using LLM.
Builds extraction prompts dynamically from agent field definitions.
"""

import logging
import json
import re
import httpx
from typing import Dict, List, Any, Optional

from framework.config.constants import LLM_TIMEOUT_EXTRACTION

logger = logging.getLogger(__name__)

LLM_TIMEOUT = LLM_TIMEOUT_EXTRACTION


class FieldExtractor:
    """
    Extracts field values from text using LLM.

    Dynamically builds prompts from agent field definitions,
    supporting any set of fields without hardcoded knowledge.
    """

    def __init__(self, endpoint: str = "http://localhost:8000"):
        self.endpoint = endpoint

    def extract(
        self,
        message: str,
        fields: List[Dict[str, Any]],
        expected_field: Optional[str] = None,
        context: str = "",
    ) -> Dict[str, Any]:
        """
        Extract field values from a user message.

        Args:
            message: User's message
            fields: List of field definitions from agent.json
            expected_field: The field we most recently asked about
            context: Additional context

        Returns:
            Dict of field_name -> extracted_value (only for fields found)
        """
        if not message or not fields:
            return {}

        # Build field descriptions
        field_descs = []
        for field in fields:
            desc = f"- {field['name']}: {field.get('description', field['name'])}"
            desc += f" (type: {field.get('type', 'string')})"
            if field.get("extraction_hints"):
                desc += f" [hints: {', '.join(field['extraction_hints'])}]"
            field_descs.append(desc)

        field_list = "\n".join(field_descs)
        field_names = [f["name"] for f in fields]

        # Build prompt with expected field context
        expected_hint = ""
        if expected_field:
            expected_hint = f"\nThe user was asked about: {expected_field}. Prioritize extracting this field.\n"

        prompt = f"""Extract information from the user's message into structured fields.

Fields to extract:
{field_list}
{expected_hint}
User message: "{message}"

Rules:
- Only include fields clearly present in the message
- Use null for fields not mentioned
- For the expected field, try to interpret the entire message as a value
- Return ONLY valid JSON

JSON:"""

        try:
            response = httpx.post(
                f"{self.endpoint}/generate",
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
            return self._parse_json(result_text, field_names)

        except Exception as e:
            logger.error(f"LLM extraction error: {e}")
            return {}

    def _parse_json(self, text: str, valid_fields: list) -> dict:
        """Parse JSON from LLM response, filtering to valid fields."""
        # Try direct parse
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return {k: v for k, v in data.items() if k in valid_fields and v is not None}
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from text
        json_match = re.search(r'\{[^}]+\}', text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                if isinstance(data, dict):
                    return {k: v for k, v in data.items() if k in valid_fields and v is not None}
            except json.JSONDecodeError:
                pass

        return {}
