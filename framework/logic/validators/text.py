"""Text Validator"""

from typing import Tuple, Optional
from framework.logic.validators.base import BaseValidator


class TextValidator(BaseValidator):
    """Validates free-text fields with optional length constraints."""

    def validate(self, value, **kwargs) -> Tuple[bool, Optional[str]]:
        if not value or not isinstance(value, str):
            return False, "Please provide a text response."

        text = value.strip()

        min_length = kwargs.get("min_length", 1)
        max_length = kwargs.get("max_length", 5000)

        if len(text) < min_length:
            return False, f"Response is too short. Please provide at least {min_length} characters."

        if len(text) > max_length:
            return False, f"Response is too long. Please keep it under {max_length} characters."

        return True, None
