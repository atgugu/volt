"""Phone Validator"""

import re
from typing import Tuple, Optional
from framework.logic.validators.base import BaseValidator


class PhoneValidator(BaseValidator):
    """Validates phone numbers."""

    def validate(self, value, **kwargs) -> Tuple[bool, Optional[str]]:
        if not value:
            return False, "Please provide a valid phone number."

        digits = re.sub(r'[^\d]', '', str(value))

        min_digits = kwargs.get("min_digits", 7)
        max_digits = kwargs.get("max_digits", 15)

        if len(digits) < min_digits:
            return False, f"Phone number seems too short. Please provide at least {min_digits} digits."

        if len(digits) > max_digits:
            return False, f"Phone number seems too long. Please check and try again."

        return True, None
