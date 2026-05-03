"""Tests for schema validators."""

from decimal import Decimal

import pytest

from src.schema import (
    InsuranceForm,
    Coverage,
    ClaimDetails,
    Policy,
    Person,
    _parse_money,
)


# --------------------------------------------------------------------------- #
#  _parse_money (module-level helper)                                         #
# --------------------------------------------------------------------------- #
class TestParseMoney:
    def test_none(self):
        assert _parse_money(None) is None

    def test_empty_string(self):
        assert _parse_money("") is None

    def test_plain_int(self):
        assert _parse_money(1000) == Decimal("1000")

    def test_float(self):
        assert _parse_money(99.99) == pytest.approx(Decimal("99.99"), abs=Decimal("0.01"))

    def test_string_with_dollar(self):
        assert _parse_money("$1,250.00") == Decimal("1250.00")

    def test_string_plain(self):
        assert _parse_money("500") == Decimal("500")

    def test_non_numeric_string(self):
        assert _parse_money("n/a") is None

    def test_decimal_passthrough(self):
        d = Decimal("123.45")
        assert _parse_money(d) == d


# --------------------------------------------------------------------------- #
#  Coverage field validators                                                  #
# --------------------------------------------------------------------------- #
class TestCoverageValidators:
    def test_limit_from_string(self):
        c = Coverage(coverage_type="collision", limit="$100,000", deductible="500", premium="400")
        assert c.limit == Decimal("100000")
        assert c.deductible == Decimal("500")
        assert c.premium == Decimal("400")

    def test_null_fields_allowed(self):
        c = Coverage()
        assert c.limit is None
        assert c.deductible is None
        assert c.premium is None


# --------------------------------------------------------------------------- #
#  Person.ssn_last4 validator                                                 #
# --------------------------------------------------------------------------- #
class TestSsnLast4:
    def test_full_ssn_trimmed(self):
        p = Person(ssn_last4="123-45-6789")
        assert p.ssn_last4 == "6789"

    def test_already_four_digits(self):
        p = Person(ssn_last4="6789")
        assert p.ssn_last4 == "6789"

    def test_too_short_returns_none(self):
        p = Person(ssn_last4="12")
        assert p.ssn_last4 is None

    def test_none_passthrough(self):
        p = Person(ssn_last4=None)
        assert p.ssn_last4 is None


# --------------------------------------------------------------------------- #
#  InsuranceForm round-trip                                                   #
# --------------------------------------------------------------------------- #
class TestInsuranceFormRoundTrip:
    def test_valid_form_validates(self):
        data = {
            "form_type": "declaration_page",
            "policy_holder": {"full_name": "Jane Doe", "date_of_birth": "1985-04-12"},
            "policy": {
                "policy_number": "AUTO-2025-00123",
                "policy_type": "auto",
                "effective_date": "2025-01-01",
                "expiration_date": "2026-01-01",
                "total_premium": "1450.00",
                "coverages": [{"coverage_type": "collision", "limit": "50000"}],
            },
        }
        form = InsuranceForm.model_validate(data)
        assert form.policy.total_premium == Decimal("1450.00")
        assert form.policy.coverages[0].limit == Decimal("50000")

    def test_extra_keys_ignored(self):
        data = {"form_type": "unknown", "unexpected_llm_key": "some value"}
        form = InsuranceForm.model_validate(data)
        assert not hasattr(form, "unexpected_llm_key")

    def test_invalid_enum_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            InsuranceForm.model_validate({"form_type": "not_a_valid_form_type"})
