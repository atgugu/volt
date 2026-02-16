"""Tests for field validators."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from framework.logic.validators import get_validator
from framework.logic.validators.email import EmailValidator
from framework.logic.validators.phone import PhoneValidator
from framework.logic.validators.name import NameValidator
from framework.logic.validators.number import NumberValidator
from framework.logic.validators.text import TextValidator


class TestEmailValidator:
    def setup_method(self):
        self.v = EmailValidator()

    def test_valid_email(self):
        valid, err = self.v.validate("test@example.com")
        assert valid is True
        assert err is None

    def test_invalid_email(self):
        valid, err = self.v.validate("not-an-email")
        assert valid is False
        assert err is not None

    def test_empty_email(self):
        valid, err = self.v.validate("")
        assert valid is False


class TestPhoneValidator:
    def setup_method(self):
        self.v = PhoneValidator()

    def test_valid_phone(self):
        valid, err = self.v.validate("6155551234")
        assert valid is True

    def test_short_phone(self):
        valid, err = self.v.validate("123")
        assert valid is False

    def test_phone_with_formatting(self):
        valid, err = self.v.validate("(615) 555-1234")
        assert valid is True


class TestNameValidator:
    def setup_method(self):
        self.v = NameValidator()

    def test_valid_name(self):
        valid, err = self.v.validate("John Smith")
        assert valid is True

    def test_short_name(self):
        valid, err = self.v.validate("J")
        assert valid is False

    def test_name_with_numbers(self):
        valid, err = self.v.validate("John123")
        assert valid is False


class TestNumberValidator:
    def setup_method(self):
        self.v = NumberValidator()

    def test_valid_number(self):
        valid, err = self.v.validate(25)
        assert valid is True

    def test_min_bound(self):
        valid, err = self.v.validate(5, min=10)
        assert valid is False

    def test_max_bound(self):
        valid, err = self.v.validate(150, max=120)
        assert valid is False

    def test_within_bounds(self):
        valid, err = self.v.validate(25, min=13, max=120)
        assert valid is True

    def test_string_number(self):
        valid, err = self.v.validate("42")
        assert valid is True


class TestTextValidator:
    def setup_method(self):
        self.v = TextValidator()

    def test_valid_text(self):
        valid, err = self.v.validate("Some text here")
        assert valid is True

    def test_empty_text(self):
        valid, err = self.v.validate("")
        assert valid is False

    def test_max_length(self):
        valid, err = self.v.validate("x" * 100, max_length=50)
        assert valid is False


class TestGetValidator:
    def test_get_email(self):
        v = get_validator("email")
        assert isinstance(v, EmailValidator)

    def test_get_unknown(self):
        v = get_validator("nonexistent")
        assert v is None
