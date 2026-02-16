"""
Field Validators

Provides validation for common field types.
Custom validators can be added by agents via custom_validators.py.
"""

from framework.logic.validators.base import BaseValidator
from framework.logic.validators.email import EmailValidator
from framework.logic.validators.phone import PhoneValidator
from framework.logic.validators.name import NameValidator
from framework.logic.validators.number import NumberValidator
from framework.logic.validators.text import TextValidator

# Registry of built-in validators
_VALIDATORS = {
    "email": EmailValidator(),
    "phone": PhoneValidator(),
    "name": NameValidator(),
    "number": NumberValidator(),
    "text": TextValidator(),
}


def get_validator(name: str) -> BaseValidator:
    """Get a validator by name. Returns None if not found."""
    return _VALIDATORS.get(name)


def register_validator(name: str, validator: BaseValidator):
    """Register a custom validator."""
    _VALIDATORS[name] = validator
