"""
Shared constants used across the framework.

Centralizes magic numbers and timeout values that were previously
scattered across multiple modules.
"""

# Phone number validation bounds
PHONE_MIN_DIGITS = 7
PHONE_MAX_DIGITS = 15

# LLM request timeouts (seconds)
LLM_TIMEOUT_EXTRACTION = 60.0
LLM_TIMEOUT_CLASSIFICATION = 30.0

# Selection parser limits
SELECTION_MAX_OPTIONS = 10

# Retry / confirmation limits
DEFAULT_MAX_RETRIES = 3
DEFAULT_CONFIRMATION_MAX_ATTEMPTS = 3
