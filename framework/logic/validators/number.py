"""Number Validator"""

from typing import Tuple, Optional
from framework.logic.validators.base import BaseValidator


class NumberValidator(BaseValidator):
    """Validates numeric values with optional min/max bounds."""

    def validate(self, value, **kwargs) -> Tuple[bool, Optional[str]]:
        try:
            num = int(value) if isinstance(value, str) else value
            if not isinstance(num, (int, float)):
                return False, "Please provide a valid number."
        except (ValueError, TypeError):
            return False, "That doesn't look like a number. Please try again."

        min_val = kwargs.get("min")
        max_val = kwargs.get("max")

        if min_val is not None and num < min_val:
            return False, f"Value must be at least {min_val}."

        if max_val is not None and num > max_val:
            return False, f"Value must be at most {max_val}."

        return True, None
