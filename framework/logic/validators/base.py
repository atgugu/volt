"""
Base Validator

Abstract base class for all field validators.
"""

from abc import ABC, abstractmethod
from typing import Tuple, Optional


class BaseValidator(ABC):
    """
    Abstract base class for field validators.

    All validators must implement the validate() method which returns
    a (is_valid, error_message) tuple.
    """

    @abstractmethod
    def validate(self, value, **kwargs) -> Tuple[bool, Optional[str]]:
        """
        Validate a field value.

        Args:
            value: The value to validate
            **kwargs: Additional configuration from validator_config in agent.json

        Returns:
            Tuple of (is_valid: bool, error_message: Optional[str])
            If valid, error_message is None.
        """
        pass
