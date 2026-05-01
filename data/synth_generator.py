"""Programmatic synthetic insurance form generator.

Why this exists
---------------
Public-domain *filled* insurance forms are scarce because the only filled
forms in the wild contain real PII and aren't published. So we generate
them. Each generator below produces a (text, ground-truth JSON) pair that
mirrors the structure of a real ACORD-style form, with `Faker`-driven
variation in names / addresses / dates / policy numbers / money amounts.

VLM-extension support
---------------------
With `--format pdf` (or `both`) the generator also writes a typewriter-style
PDF rendering of the same text via `reportlab`. This is what a VLM-based
parser (`parser.py: vlm-qwen` mode) reads as an image input, so the same
ground-truth JSON can be used to evaluate both text-mode and VLM-mode
parsing on the synthetic tier. See docs/future_work.md §1.

Usage
-----
    python data/synth_generator.py --n 8 --seed 42                  # txt + json
    python data/synth_generator.py --n 8 --seed 42 --format both    # also PDF

Existing samples in data/samples/ are NOT overwritten — generated stems
include the form-type and a 4-char random suffix so collisions are
unlikely.
"""

from __future__ import annotations

import argparse
import json
import random
import string
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Callable

try:
    from faker import Faker
except ImportError as e:
    raise SystemExit(
        "Faker not installed. `pip install faker` (or run "
        "`pip install -r requirements.txt` after the next bump)."
    ) from e


# --------------------------------------------------------------------------- #
@dataclass
class GeneratedSample:
    stem: str
    text: str
    ground_truth: dict


# --------------------------------------------------------------------------- #
#  Helpers                                                                    #
# --------------------------------------------------------------------------- #
def _suffix(rng: random.Random, n: int = 4) -> str:
    return "".join(rng.choices(string.ascii_lowercase + string.digits, k=n))


def _us_phone(fake: Faker) -> str:
    # Force fake-friendly 555 prefix to keep numbers obviously synthetic
    return f"({fake.random_int(200, 989)}) 555-{fake.random_int(0, 9999):04d}"


def _email(fake: Faker, name: str) -> str:
    base = name.lower().replace(" ", ".").replace("'", "")
    return f"{base}@example.com"


def _date_iso(d: date) -> str:
    return d.isoformat()


def _date_us(d: date) -> str:
    return f"{d.month:02d}/{d.day:02d}/{d.year:04d}"


def _money(amount: Decimal | int | float) -> str:
    return f"{Decimal(str(amount)):.2f}"


def _money_dollar(amount: Decimal | int | float) -> str:
    a = Decimal(str(amount))
    return f"${a:,.2f}"


# --------------------------------------------------------------------------- #
#  Generators                                                                 #
# --------------------------------------------------------------------------- #
def gen_auto_decl_multi_driver(fake: Faker, rng: random.Random) -> GeneratedSample:
    """Auto declaration with primary + 2 additional drivers.

    Critical: every visible value is hoisted to a variable BEFORE we render the
    text, so the GT references the same value the text shows. Calling
    `fake.<x>()` inline inside the f-string and again later would yield a
    different random value and silently corrupt the GT.
    """
    insurer = fake.random_element([
        "Cascadia Mutual Insurance",
        "Pinecrest Auto Group",
        "Summit Ridge Casualty",
    ])
    pol_num = f"AUTO-{rng.randint(2024, 2026)}-{rng.randint(100000, 999999)}"
    eff = fake.date_between(start_date="-1y", end_date="-1m")
    exp = eff + timedelta(days=365)
    holder = fake.name()
    holder_dob = fake.date_of_birth(minimum_age=22, maximum_age=70)
    holder_phone = _us_phone(fake)
    holder_email = _email(fake, holder)
    street = fake.street_address(); city = fake.city(); st = fake.state_abbr(); zp = fake.postcode()
    extra1 = fake.name()
    extra1_dob = fake.date_of_birth(minimum_age=18, maximum_age=70)
    extra2 = fake.name()
    extra2_dob = fake.date_of_birth(minimum_age=18, maximum_age=70)

    coverages = [
        ("bodily_injury_liability", "$300,000 / $500,000", "300000", None, rng.randint(550, 800)),
        ("property_damage_liability", "$100,000", "100000", None, rng.randint(180, 240)),
        ("collision", None, None, "500", rng.randint(220, 320)),
        ("comprehensive", None, None, "250", rng.randint(110, 160)),
        ("medical_payments", "$5,000", "5000", None, rng.randint(40, 80)),
    ]
    total = sum(c[4] for c in coverages)

    text = f"""[PAGE 1]
{insurer.upper()} — AUTO POLICY DECLARATIONS

Policy Number: {pol_num}
Insurer: {insurer}
Policy Period: {_date_us(eff)} to {_date_us(exp)}

Named Insured:
  {holder}
  DOB: {_date_us(holder_dob)}
  Address: {street}, {city}, {st} {zp}
  Phone: {holder_phone}
  Email: {holder_email}

Additional Drivers:
  - {extra1}, DOB {_date_us(extra1_dob)}
  - {extra2}, DOB {_date_us(extra2_dob)}

Coverages
"""
    for ctype, lim_disp, _, ded, prem in coverages:
        lim_str = f"Limit {lim_disp}" if lim_disp else ""
        ded_str = f"Deductible ${ded}" if ded else ""
        text += f"  {ctype.replace('_',' ').title():35s} {lim_str:30s} {ded_str:25s} Premium ${prem:.2f}\n"

    text += f"\nTotal Annual Premium: {_money_dollar(total)}\n"

    gt = {
        "form_type": "declaration_page",
        "policy_holder": {
            "full_name": holder,
            "date_of_birth": _date_iso(holder_dob),
            "phone": holder_phone,
            "email": holder_email,
            "address": {"street": street, "city": city, "state": st, "zip_code": zp},
        },
        "additional_insureds": [
            {"full_name": extra1, "date_of_birth": _date_iso(extra1_dob)},
            {"full_name": extra2, "date_of_birth": _date_iso(extra2_dob)},
        ],
        "beneficiaries": [],
        "policy": {
            "policy_number": pol_num,
            "policy_type": "auto",
            "insurer_name": insurer,
            "effective_date": _date_iso(eff),
            "expiration_date": _date_iso(exp),
            "total_premium": _money(total),
            "coverages": [
                {
                    "coverage_type": c[0],
                    **({"limit": c[2]} if c[2] else {}),
                    **({"deductible": c[3]} if c[3] else {}),
                    "premium": _money(c[4]),
                }
                for c in coverages
            ],
        },
        "claim": None,
        "raw_notes": "Multi-driver policy with two additional drivers.",
    }
    return GeneratedSample(stem=f"synthetic_auto_decl_multidriver_{_suffix(rng)}", text=text, ground_truth=gt)


def gen_home_condo_decl(fake: Faker, rng: random.Random) -> GeneratedSample:
    """Condominium (HO-6) declaration page."""
    insurer = fake.random_element([
        "Brightwater Mutual",
        "Greystone Home Insurance",
        "Coastline HO Group",
    ])
    pol_num = f"HO6-{rng.randint(2024, 2026)}-{rng.randint(100000, 999999)}"
    eff = fake.date_between(start_date="-1y", end_date="-1m")
    exp = eff + timedelta(days=365)
    holder = fake.name()
    street = fake.street_address(); city = fake.city(); st = fake.state_abbr(); zp = fake.postcode()
    dob = fake.date_of_birth(minimum_age=25, maximum_age=80)
    phone = _us_phone(fake)
    email = _email(fake, holder)
    year_built = rng.randint(1985, 2020)
    floor = rng.randint(1, 30)

    cov_a_lim = rng.randint(80, 250) * 1000
    cov_c_lim = rng.randint(40, 100) * 1000
    cov_e_lim = rng.choice([100_000, 200_000, 300_000])
    prem_a = round(cov_a_lim * 0.0035, 2)
    prem_c = round(cov_c_lim * 0.0042, 2)
    prem_e = 84.00
    total = round(prem_a + prem_c + prem_e, 2)

    text = f"""[PAGE 1]
{insurer.upper()} — CONDOMINIUM (HO-6) DECLARATIONS

Insurer: {insurer}
Policy Number: {pol_num}
Period: {_date_us(eff)} through {_date_us(exp)}

POLICYHOLDER
  Name: {holder}
  DOB: {_date_us(dob)}
  Mailing Address: {street}, {city}, {st} {zp}
  Email: {email}
  Phone: {phone}

UNIT
  Unit Address: same as mailing
  Year built: {year_built}  /  Floor: {floor}

COVERAGES
  Coverage A — Dwelling (Walls In)       Limit ${cov_a_lim:,}    Deductible $1,000   Premium ${prem_a:,.2f}
  Coverage C — Personal Property         Limit ${cov_c_lim:,}    Deductible $500     Premium ${prem_c:,.2f}
  Coverage E — Personal Liability        Limit ${cov_e_lim:,}                           Premium ${prem_e:,.2f}

ANNUAL PREMIUM TOTAL: {_money_dollar(total)}

HOA Master Policy on file. Loss assessment coverage included up to $50,000.
"""

    gt = {
        "form_type": "declaration_page",
        "policy_holder": {
            "full_name": holder,
            "date_of_birth": _date_iso(dob),
            "phone": phone,
            "email": email,
            "address": {"street": street, "city": city, "state": st, "zip_code": zp},
        },
        "additional_insureds": [],
        "beneficiaries": [],
        "policy": {
            "policy_number": pol_num,
            "policy_type": "home",
            "insurer_name": insurer,
            "effective_date": _date_iso(eff),
            "expiration_date": _date_iso(exp),
            "total_premium": _money(total),
            "coverages": [
                {"coverage_type": "dwelling", "limit": str(cov_a_lim), "deductible": "1000", "premium": _money(prem_a)},
                {"coverage_type": "personal_property", "limit": str(cov_c_lim), "deductible": "500", "premium": _money(prem_c)},
                {"coverage_type": "personal_liability", "limit": str(cov_e_lim), "premium": _money(prem_e)},
            ],
        },
        "claim": None,
        "raw_notes": "Condominium HO-6 form. HOA master policy on file. Loss assessment coverage up to $50,000 included.",
    }
    return GeneratedSample(stem=f"synthetic_home_condo_{_suffix(rng)}", text=text, ground_truth=gt)


def gen_life_whole_with_riders(fake: Faker, rng: random.Random) -> GeneratedSample:
    """Whole life insurance application with multiple riders."""
    insurer = fake.random_element([
        "Northgate Life Assurance",
        "Marigold Whole Life",
        "Silver Pine Mutual Life",
    ])
    app_no = f"APP-WL-{rng.randint(2024, 2026)}-{rng.randint(100000, 999999)}"
    eff = fake.date_between(start_date="now", end_date="+90d")
    holder = fake.name()
    spouse = fake.name()
    dob_holder = fake.date_of_birth(minimum_age=30, maximum_age=55)
    dob_spouse = fake.date_of_birth(minimum_age=30, maximum_age=55)
    face = rng.choice([250_000, 500_000, 1_000_000])
    premium = round(face * 0.0085, 2)
    street = fake.street_address(); city = fake.city(); st = fake.state_abbr(); zp = fake.postcode()
    phone = _us_phone(fake)
    email = _email(fake, holder)

    text = f"""[PAGE 1]
{insurer.upper()} — WHOLE LIFE APPLICATION

Application No.: {app_no}
Carrier: {insurer}
Product: Whole Life with Paid-Up Additions Rider
Face Amount: {_money_dollar(face)}
Annual Premium: {_money_dollar(premium)}
Requested Effective Date: {_date_us(eff)}

PROPOSED INSURED
  Full Legal Name: {holder}
  Date of Birth: {_date_us(dob_holder)}
  Address: {street}, {city}, {st} {zp}
  Phone: {phone}
  Email: {email}

BENEFICIARIES (primary)
  1) {spouse}                                Relationship: Spouse   DOB: {_date_us(dob_spouse)}   Share: 100%

RIDERS ELECTED
  - Waiver of Premium Rider
  - Accelerated Death Benefit Rider
  - Paid-Up Additions Rider (annual contribution $2,500)

[PAGE 2]
Smoker status: Non-smoker (declared).
Replacement of existing coverage: No.
Paramedical exam: required.
"""

    gt = {
        "form_type": "policy_application",
        "policy_holder": {
            "full_name": holder,
            "date_of_birth": _date_iso(dob_holder),
            "phone": phone,
            "email": email,
            "address": {"street": street, "city": city, "state": st, "zip_code": zp},
        },
        "additional_insureds": [],
        "beneficiaries": [
            {"full_name": spouse, "date_of_birth": _date_iso(dob_spouse)},
        ],
        "policy": {
            "policy_number": app_no,
            "policy_type": "life",
            "insurer_name": insurer,
            "effective_date": _date_iso(eff),
            "expiration_date": None,
            "total_premium": _money(premium),
            "coverages": [
                {"coverage_type": "whole_life", "limit": str(face), "premium": _money(premium)},
            ],
        },
        "claim": None,
        "raw_notes": "Whole life with riders: Waiver of Premium, Accelerated Death Benefit, Paid-Up Additions ($2,500/yr). Non-smoker. Paramedical exam required.",
    }
    return GeneratedSample(stem=f"synthetic_life_whole_{_suffix(rng)}", text=text, ground_truth=gt)


def gen_health_hdhp_card(fake: Faker, rng: random.Random) -> GeneratedSample:
    """High-deductible health plan ID card with HSA."""
    insurer = fake.random_element([
        "Cascade Health Plan",
        "Meridian Health Network",
        "BlueRidge Health Cooperative",
    ])
    member = fake.name()
    member_id = f"{insurer[:3].upper()}-{rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}-{rng.randint(0, 99):02d}"
    group = str(rng.randint(100000, 999999))
    eff = date(2026, 1, 1)
    deductible_ind = rng.choice([3000, 4500, 6000])
    oop_ind = rng.choice([6000, 7500, 9450])

    text = f"""[PAGE 1]
{insurer.upper()} — Member ID Card (Front)

Plan: HDHP Bronze (HSA-eligible)
Member: {member.upper()}
Member ID: {member_id}
Group #: {group}
Effective: {_date_us(eff)}

[PAGE 2]
{insurer} — Member ID Card (Back)

Customer Service: 1-800-555-{rng.randint(1000, 9999):04d}
Provider Services: 1-800-555-{rng.randint(1000, 9999):04d}

Deductible (individual): ${deductible_ind:,}
Out-of-pocket maximum (individual): ${oop_ind:,}

After deductible, plan pays 80%; member pays 20% coinsurance until OOP max.
HSA contributions allowed up to IRS annual limit.
"""

    gt = {
        "form_type": "declaration_page",
        "policy_holder": {"full_name": member.title()},
        "additional_insureds": [],
        "beneficiaries": [],
        "policy": {
            "policy_number": member_id,
            "policy_type": "health",
            "insurer_name": insurer,
            "effective_date": _date_iso(eff),
            "expiration_date": None,
            "total_premium": None,
            "coverages": [],
        },
        "claim": None,
        "raw_notes": f"HDHP Bronze HSA-eligible. Group {group}. Individual deductible ${deductible_ind:,}, OOP max ${oop_ind:,}. After deductible 80/20 coinsurance.",
    }
    return GeneratedSample(stem=f"synthetic_health_hdhp_{_suffix(rng)}", text=text, ground_truth=gt)


def gen_auto_theft_claim(fake: Faker, rng: random.Random) -> GeneratedSample:
    """Auto theft claim form."""
    insurer = "Cascadia Mutual Insurance"
    claim_num = f"CLM-{rng.randint(2024, 2026)}-AUTO-{rng.randint(10000, 99999)}"
    pol_num = f"AUTO-{rng.randint(2024, 2026)}-{rng.randint(100000, 999999)}"
    insured = fake.name()
    phone = _us_phone(fake)
    email = _email(fake, insured)
    loss_date = fake.date_between(start_date="-3m", end_date="-1d")
    estimate = rng.randint(15000, 45000)
    loc_street = fake.street_address(); loc_city = fake.city(); loc_st = fake.state_abbr(); loc_zip = fake.postcode()

    text = f"""[PAGE 1]
{insurer.upper()} — AUTO THEFT CLAIM REPORT

Claim Number: {claim_num}
Policy Number: {pol_num}
Date of Loss: {_date_iso(loss_date)}
Date Reported: {_date_iso(loss_date + timedelta(days=1))}

INSURED
  Name: {insured}
  Phone: {phone}
  Email: {email}

LOSS LOCATION
  Vehicle parked overnight at {loc_street}, {loc_city}, {loc_st} {loc_zip}

DESCRIPTION OF LOSS
  Vehicle reported missing the morning of {_date_iso(loss_date)}. No broken
  glass observed at scene; signs of relay theft suspected. Police report
  filed with local PD, report #PD-{rng.randint(2024, 2026)}-{rng.randint(10000, 99999)}.

ESTIMATED REPLACEMENT VALUE: {_money_dollar(estimate)}
Deductible applied: $1,000
"""

    gt = {
        "form_type": "claim_form",
        "policy_holder": {"full_name": insured, "phone": phone, "email": email},
        "additional_insureds": [],
        "beneficiaries": [],
        "policy": {"policy_number": pol_num, "policy_type": "auto"},
        "claim": {
            "claim_number": claim_num,
            "date_of_loss": _date_iso(loss_date),
            "loss_description": "Vehicle reported missing; no broken glass at scene; relay theft suspected. Police report filed.",
            "loss_location": {"street": loc_street, "city": loc_city, "state": loc_st, "zip_code": loc_zip},
            "estimated_amount": _money(estimate),
        },
        "raw_notes": f"Insurer: {insurer}. Deductible $1,000.",
    }
    return GeneratedSample(stem=f"synthetic_claim_theft_{_suffix(rng)}", text=text, ground_truth=gt)


def gen_umbrella_decl(fake: Faker, rng: random.Random) -> GeneratedSample:
    """Personal umbrella liability declaration page."""
    insurer = fake.random_element([
        "Apex Personal Umbrella",
        "Veridian Excess Lines",
    ])
    pol_num = f"UMB-{rng.randint(2024, 2026)}-{rng.randint(100000, 999999)}"
    eff = fake.date_between(start_date="-6m", end_date="-1d")
    exp = eff + timedelta(days=365)
    holder = fake.name()
    spouse = fake.name()
    limit = rng.choice([1_000_000, 2_000_000, 5_000_000])
    premium = round(limit / 1_000_000 * 285, 2)
    street = fake.street_address(); city = fake.city(); st = fake.state_abbr(); zp = fake.postcode()

    text = f"""[PAGE 1]
{insurer.upper()} — PERSONAL UMBRELLA LIABILITY DECLARATIONS

Policy Number: {pol_num}
Insurer: {insurer}
Policy Period: {_date_us(eff)} to {_date_us(exp)}

NAMED INSURED
  {holder}
  Spouse: {spouse}
  Address: {street}, {city}, {st} {zp}

COVERAGE
  Each occurrence limit: {_money_dollar(limit)}
  Annual aggregate:      {_money_dollar(limit)}
  Self-insured retention: $250
  Annual premium:        {_money_dollar(premium)}

UNDERLYING POLICIES (must be maintained)
  - Auto: $250,000 / $500,000 BI, $100,000 PD
  - Home: $300,000 personal liability
"""

    gt = {
        "form_type": "declaration_page",
        "policy_holder": {
            "full_name": holder,
            "address": {"street": street, "city": city, "state": st, "zip_code": zp},
        },
        "additional_insureds": [{"full_name": spouse}],
        "beneficiaries": [],
        "policy": {
            "policy_number": pol_num,
            "policy_type": "other",
            "insurer_name": insurer,
            "effective_date": _date_iso(eff),
            "expiration_date": _date_iso(exp),
            "total_premium": _money(premium),
            "coverages": [
                {"coverage_type": "umbrella_liability", "limit": str(limit), "deductible": "250", "premium": _money(premium)},
            ],
        },
        "claim": None,
        "raw_notes": f"Personal umbrella. Aggregate {_money_dollar(limit)}. SIR $250. Underlying auto 250/500 BI, 100 PD; home $300,000 personal liability required.",
    }
    return GeneratedSample(stem=f"synthetic_umbrella_{_suffix(rng)}", text=text, ground_truth=gt)


def gen_renters_decl(fake: Faker, rng: random.Random) -> GeneratedSample:
    """Renters (HO-4) declaration page."""
    insurer = fake.random_element([
        "Pinecrest Renters Insurance",
        "Brightwater Renters Co.",
    ])
    pol_num = f"HO4-{rng.randint(2024, 2026)}-{rng.randint(100000, 999999)}"
    eff = fake.date_between(start_date="-6m", end_date="-1d")
    exp = eff + timedelta(days=365)
    holder = fake.name()
    cov_c = rng.choice([20_000, 30_000, 50_000])
    cov_e = rng.choice([100_000, 300_000])
    premium_total = round(cov_c * 0.008 + 64, 2)
    street = fake.street_address(); city = fake.city(); st = fake.state_abbr(); zp = fake.postcode()
    phone = _us_phone(fake); email = _email(fake, holder)

    text = f"""[PAGE 1]
{insurer.upper()} — RENTERS (HO-4) DECLARATIONS

Insurer: {insurer}
Policy Number: {pol_num}
Period: {_date_us(eff)} - {_date_us(exp)}

POLICYHOLDER
  Name: {holder}
  Mailing Address: {street}, {city}, {st} {zp}
  Phone: {phone}
  Email: {email}

COVERAGES
  Coverage C — Personal Property         Limit ${cov_c:,}        Deductible $250        Premium ${cov_c*0.008:,.2f}
  Coverage E — Personal Liability        Limit ${cov_e:,}                                Premium $64.00
  Coverage F — Medical Payments          Limit $1,000                                       Premium included

ANNUAL PREMIUM TOTAL: {_money_dollar(premium_total)}
"""

    gt = {
        "form_type": "declaration_page",
        "policy_holder": {
            "full_name": holder,
            "phone": phone,
            "email": email,
            "address": {"street": street, "city": city, "state": st, "zip_code": zp},
        },
        "additional_insureds": [],
        "beneficiaries": [],
        "policy": {
            "policy_number": pol_num,
            "policy_type": "home",
            "insurer_name": insurer,
            "effective_date": _date_iso(eff),
            "expiration_date": _date_iso(exp),
            "total_premium": _money(premium_total),
            "coverages": [
                {"coverage_type": "personal_property", "limit": str(cov_c), "deductible": "250", "premium": _money(cov_c * 0.008)},
                {"coverage_type": "personal_liability", "limit": str(cov_e), "premium": "64.00"},
                {"coverage_type": "medical_payments", "limit": "1000", "premium": "0"},
            ],
        },
        "claim": None,
        "raw_notes": "HO-4 renters policy. Medical payments included.",
    }
    return GeneratedSample(stem=f"synthetic_renters_{_suffix(rng)}", text=text, ground_truth=gt)


def gen_partial_blank_app(fake: Faker, rng: random.Random) -> GeneratedSample:
    """Application with most fields blank — hallucination resistance test for synthetic tier."""
    insurer = fake.random_element([
        "Heartland Mutual Insurance",
        "Western Plains Insurance Co.",
    ])
    eff_target = fake.date_between(start_date="now", end_date="+60d")
    text = f"""[PAGE 1]
{insurer.upper()} — POLICY APPLICATION (Draft, page 1 of 4)

Carrier: {insurer}
Policy Type: Auto

APPLICANT INFORMATION
  Full Name: ___________________________________
  Date of Birth: ____ / ____ / ______
  Address: ___________________________________
           ___________________________________
  Phone: __________________
  Email: __________________

POLICY DETAILS
  Requested Effective Date: {_date_us(eff_target)}
  Policy Number (assigned by underwriter): ____________

VEHICLE
  Year: ____   Make: ____________   Model: ____________   VIN: ____________

NOTES
  Applicant requested follow-up to discuss liability minimums.
"""

    gt = {
        "form_type": "policy_application",
        "policy_holder": None,
        "additional_insureds": [],
        "beneficiaries": [],
        "policy": {
            "policy_number": None,
            "policy_type": "auto",
            "insurer_name": insurer,
            "effective_date": _date_iso(eff_target),
            "expiration_date": None,
            "total_premium": None,
            "coverages": [],
        },
        "claim": None,
        "raw_notes": "Draft application page 1 of 4. All applicant fields blank. Vehicle year/make/model/VIN blank. Applicant requested follow-up to discuss liability minimums.",
    }
    return GeneratedSample(stem=f"synthetic_partial_app_{_suffix(rng)}", text=text, ground_truth=gt)


# Order matters: this is the catalog used by --n.
GENERATORS: list[Callable[[Faker, random.Random], GeneratedSample]] = [
    gen_auto_decl_multi_driver,
    gen_home_condo_decl,
    gen_life_whole_with_riders,
    gen_health_hdhp_card,
    gen_auto_theft_claim,
    gen_umbrella_decl,
    gen_renters_decl,
    gen_partial_blank_app,
]


# --------------------------------------------------------------------------- #
#  PDF rendering (typewriter-style)                                           #
# --------------------------------------------------------------------------- #
import re as _re


def render_text_to_pdf(text: str, output_path: Path) -> None:
    """Render canonical sample text into a typewriter-style PDF.

    The same text becomes:
      - input for `--parser-mode text`  (pdfplumber re-extracts it)
      - input for `--parser-mode vlm-*` (VLM reads the rendered image)

    `[PAGE n]` markers in the source text become real page breaks in the
    PDF; the marker line itself is dropped.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    width, height = letter
    margin_x, margin_y = 54, 54        # 0.75 inch
    line_height = 11
    font_name, font_size = "Courier", 9

    c = canvas.Canvas(str(output_path), pagesize=letter)
    c.setFont(font_name, font_size)

    # Split by [PAGE n] markers, drop empty leading/trailing segments
    parts = _re.split(r"\[PAGE\s+\d+\]\s*\n?", text)
    parts = [p for p in parts if p.strip()]

    for idx, page_text in enumerate(parts):
        if idx > 0:
            c.showPage()
            c.setFont(font_name, font_size)
        y = height - margin_y
        for line in page_text.split("\n"):
            # Long-line guard so we don't run off the page width
            if len(line) > 110:
                line = line[:107] + "..."
            if y < margin_y:
                c.showPage()
                c.setFont(font_name, font_size)
                y = height - margin_y
            c.drawString(margin_x, y, line)
            y -= line_height

    c.save()


# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--n", type=int, default=len(GENERATORS),
                        help=f"Number of samples to generate (max {len(GENERATORS)} unique types).")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--samples-dir", type=Path, default=Path("data/samples"))
    parser.add_argument("--gt-dir", type=Path, default=Path("data/ground_truth"))
    parser.add_argument(
        "--format",
        choices=("txt", "pdf", "both"),
        default="both",
        help="Output format(s). 'both' (default) writes .txt for inspection AND .pdf for harness eval.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print what would be written, don't write.")
    parser.add_argument(
        "--render-existing",
        action="store_true",
        help="Skip generation; just render data/samples/synthetic_*.txt → matching .pdf.",
    )
    args = parser.parse_args(argv)

    args.samples_dir.mkdir(parents=True, exist_ok=True)
    args.gt_dir.mkdir(parents=True, exist_ok=True)

    # ----- render-only mode --------------------------------------------- #
    if args.render_existing:
        try:
            import reportlab  # noqa: F401
        except ImportError as e:
            raise SystemExit("reportlab required for rendering. pip install reportlab") from e
        rendered = []
        for txt_path in sorted(args.samples_dir.glob("synthetic_*.txt")):
            pdf_path = txt_path.with_suffix(".pdf")
            if args.dry_run:
                print(f"[dry-run] would render {txt_path} → {pdf_path}")
                continue
            render_text_to_pdf(txt_path.read_text(encoding="utf-8"), pdf_path)
            rendered.append(pdf_path.name)
        if not args.dry_run:
            print(f"rendered {len(rendered)} PDFs:")
            for r in rendered:
                print(f"  - {r}")
        return 0

    if args.format in ("pdf", "both"):
        try:
            import reportlab  # noqa: F401
        except ImportError as e:
            raise SystemExit(
                "reportlab not installed but --format requires it. "
                "Run: pip install reportlab"
            ) from e

    fake = Faker("en_US")
    Faker.seed(args.seed)
    rng = random.Random(args.seed)

    generators = GENERATORS[: args.n]
    written = []
    for gen in generators:
        sample = gen(fake, rng)
        txt_path = args.samples_dir / f"{sample.stem}.txt"
        pdf_path = args.samples_dir / f"{sample.stem}.pdf"
        gt_path = args.gt_dir / f"{sample.stem}.json"
        if args.dry_run:
            wrote = []
            if args.format in ("txt", "both"):
                wrote.append(str(txt_path))
            if args.format in ("pdf", "both"):
                wrote.append(str(pdf_path))
            print(f"[dry-run] would write {wrote} and {gt_path}")
            continue
        if args.format in ("txt", "both"):
            txt_path.write_text(sample.text, encoding="utf-8")
        if args.format in ("pdf", "both"):
            render_text_to_pdf(sample.text, pdf_path)
        gt_path.write_text(json.dumps(sample.ground_truth, indent=2, ensure_ascii=False), encoding="utf-8")
        written.append(sample.stem)
    if not args.dry_run:
        print(f"wrote {len(written)} samples:")
        for s in written:
            print(f"  - {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
