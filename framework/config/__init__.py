"""Configuration and agent registry."""

from framework.config.settings import (
    PROJECT_ROOT,
    AGENTS_DIR,
    LLM_ENDPOINT,
    LLM_PORT,
    BACKEND_PORT,
    BACKEND_HOST,
    TTS_PORT,
    STT_PORT,
    LOG_LEVEL,
    VERBOSE,
)
from framework.config.agent_registry import AgentRegistry, AgentDefinition, get_registry
from framework.config.constants import (
    PHONE_MIN_DIGITS,
    PHONE_MAX_DIGITS,
    LLM_TIMEOUT_EXTRACTION,
    LLM_TIMEOUT_CLASSIFICATION,
    SELECTION_MAX_OPTIONS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_CONFIRMATION_MAX_ATTEMPTS,
)

__all__ = [
    # Settings
    "PROJECT_ROOT",
    "AGENTS_DIR",
    "LLM_ENDPOINT",
    "LLM_PORT",
    "BACKEND_PORT",
    "BACKEND_HOST",
    "TTS_PORT",
    "STT_PORT",
    "LOG_LEVEL",
    "VERBOSE",
    # Registry
    "AgentRegistry",
    "AgentDefinition",
    "get_registry",
    # Constants
    "PHONE_MIN_DIGITS",
    "PHONE_MAX_DIGITS",
    "LLM_TIMEOUT_EXTRACTION",
    "LLM_TIMEOUT_CLASSIFICATION",
    "SELECTION_MAX_OPTIONS",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_CONFIRMATION_MAX_ATTEMPTS",
]
