"""Pydantic schema for insurance form extraction.

Designed around ACORD-style insurance forms (policy applications, claims,
declaration pages). Optional everywhere because real-world forms are partial.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


def _parse_money(v) -> Optional[Decimal]:
    """Normalize a raw money value (str / int / float / Decimal) to Decimal."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float, Decimal)):
        return Decimal(str(v))
    if isinstance(v, str):
        cleaned = re.sub(r"[^\d.\-]", "", v)
        if not cleaned:
            return None
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None
    return None


# --------------------------------------------------------------------------- #
#  Enums                                                                      #
# --------------------------------------------------------------------------- #
class FormType(str, Enum):
    POLICY_APPLICATION = "policy_application"
    DECLARATION_PAGE = "declaration_page"
    CLAIM_FORM = "claim_form"
    UNKNOWN = "unknown"


class PolicyType(str, Enum):
    AUTO = "auto"
    HOME = "home"
    LIFE = "life"
    HEALTH = "health"
    COMMERCIAL = "commercial"
    OTHER = "other"


# --------------------------------------------------------------------------- #
#  Sub-models                                                                 #
# --------------------------------------------------------------------------- #
class Address(BaseModel):
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None


class Person(BaseModel):
    full_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    ssn_last4: Optional[str] = Field(
        default=None,
        description="Last 4 digits of SSN only — never extract full SSN.",
    )
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[Address] = None

    @field_validator("ssn_last4")
    @classmethod
    def _ssn_only_last4(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        digits = re.sub(r"\D", "", v)
        if len(digits) >= 4:
            return digits[-4:]
        return None


class Coverage(BaseModel):
    coverage_type: Optional[str] = Field(
        default=None,
        description="e.g., 'bodily_injury_liability', 'collision', 'dwelling'.",
    )
    limit: Optional[Decimal] = None
    deductible: Optional[Decimal] = None
    premium: Optional[Decimal] = None

    @field_validator("limit", "deductible", "premium", mode="before")
    @classmethod
    def _money_to_decimal(cls, v):
        return _parse_money(v)


class Policy(BaseModel):
    policy_number: Optional[str] = None
    policy_type: Optional[PolicyType] = None
    insurer_name: Optional[str] = None
    effective_date: Optional[date] = None
    expiration_date: Optional[date] = None
    total_premium: Optional[Decimal] = None
    coverages: List[Coverage] = Field(default_factory=list)

    @field_validator("total_premium", mode="before")
    @classmethod
    def _money(cls, v):
        return _parse_money(v)


class ClaimDetails(BaseModel):
    claim_number: Optional[str] = None
    date_of_loss: Optional[date] = None
    loss_description: Optional[str] = None
    loss_location: Optional[Address] = None
    estimated_amount: Optional[Decimal] = None

    @field_validator("estimated_amount", mode="before")
    @classmethod
    def _money(cls, v):
        return _parse_money(v)


# --------------------------------------------------------------------------- #
#  Top-level extraction target                                                #
# --------------------------------------------------------------------------- #
class InsuranceForm(BaseModel):
    """Top-level schema returned by the extractor."""

    form_type: FormType = FormType.UNKNOWN
    policy_holder: Optional[Person] = None
    additional_insureds: List[Person] = Field(default_factory=list)
    beneficiaries: List[Person] = Field(default_factory=list)
    policy: Optional[Policy] = None
    claim: Optional[ClaimDetails] = None
    raw_notes: Optional[str] = Field(
        default=None,
        description="Anything important the model saw but couldn't slot into a field.",
    )

    model_config = {
        "extra": "ignore",  # tolerate extra LLM-emitted keys without crashing
        "json_schema_extra": {
            "examples": [
                {
                    "form_type": "policy_application",
                    "policy_holder": {
                        "full_name": "Jane Doe",
                        "date_of_birth": "1985-04-12",
                    },
                    "policy": {
                        "policy_number": "AUTO-2025-00123",
                        "policy_type": "auto",
                        "effective_date": "2025-01-01",
                        "expiration_date": "2026-01-01",
                        "total_premium": "1450.00",
                        "coverages": [
                            {
                                "coverage_type": "bodily_injury_liability",
                                "limit": "100000",
                                "deductible": "0",
                                "premium": "650",
                            }
                        ],
                    },
                }
            ]
        },
    }


def schema_as_json_string(indent: int = 2) -> str:
    """Return the JSON schema as a string — used inside prompts."""
    import json

    return json.dumps(InsuranceForm.model_json_schema(), indent=indent)
