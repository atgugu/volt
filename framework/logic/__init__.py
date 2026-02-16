"""Business logic: selection parsing, bypass detection, and prompt templates."""

from framework.logic.selection_parser import SelectionParser, get_selection_parser
from framework.logic.bypass_detector import detect_bypass_intent
from framework.logic.prompt_templates import (
    ask_field,
    acknowledge_and_ask,
    confirmation_summary,
    completion_message,
    validation_error,
)

__all__ = [
    "SelectionParser",
    "get_selection_parser",
    "detect_bypass_intent",
    "ask_field",
    "acknowledge_and_ask",
    "confirmation_summary",
    "completion_message",
    "validation_error",
]
