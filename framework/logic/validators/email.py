"""Email Validator"""

import re
from typing import Tuple, Optional
from framework.logic.validators.base import BaseValidator


class EmailValidator(BaseValidator):
    """Validates email addresses."""

    EMAIL_PATTERN = re.compile(
        r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    )

    def validate(self, value, **kwargs) -> Tuple[bool, Optional[str]]:
        if not value or not isinstance(value, str):
            return False, "Please provide a valid email address."

        value = value.strip().lower()

        if not self.EMAIL_PATTERN.match(value):
            return False, "That doesn't look like a valid email address. Please try again."

        return True, None
