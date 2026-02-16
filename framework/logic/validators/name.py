"""Name Validator"""

import re
from typing import Tuple, Optional
from framework.logic.validators.base import BaseValidator


class NameValidator(BaseValidator):
    """Validates person names."""

    def validate(self, value, **kwargs) -> Tuple[bool, Optional[str]]:
        if not value or not isinstance(value, str):
            return False, "Please provide your name."

        name = value.strip()

        if len(name) < 2:
            return False, "Name seems too short. Please provide your full name."

        if len(name) > 100:
            return False, "Name seems too long. Please provide a shorter version."

        if re.search(r'[0-9@#$%^&*(){}[\]|\\<>]', name):
            return False, "Name contains invalid characters. Please provide just your name."

        return True, None
