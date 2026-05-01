"""v3 — Schema + few-shot examples + edge-case rules.

Hypothesis: showing the model 1-2 worked examples on a similar (but distinct)
form type pushes it past the "shape is right but values drift" failure mode
that v2 still hits. Few-shot also pins the model on tricky decisions:
  - When multiple policy numbers appear, pick the primary one.
  - When the form is partially blank, return null rather than guess.
  - When a person section repeats (insured + spouse), separate into list.
"""

from src.schema import schema_as_json_string

V3_SYSTEM = """You are a meticulous insurance document extraction assistant.
You always return a single valid JSON object that conforms exactly to the
provided schema. You prefer null over guessing. You never include prose
or code fences."""


_FEW_SHOT_EXAMPLE_INPUT = """[PAGE 1]
ACME MUTUAL — AUTO POLICY DECLARATION
Policy No.: AUTO-2024-77821
Insurer: Acme Mutual Insurance Co.
Policy Period: 03/15/2024 to 03/15/2025
Named Insured: Robert J. Kim
DOB: 04/22/1981
Address: 245 Pine St, Apt 4B, San Jose CA 95110
Coverages:
  Bodily Injury Liability   $250,000 / $500,000   Premium $725
  Collision                 Deductible $500       Premium $310
Total Premium: $1,035.00"""

_FEW_SHOT_EXAMPLE_OUTPUT = """{
  "form_type": "declaration_page",
  "policy_holder": {
    "full_name": "Robert J. Kim",
    "date_of_birth": "1981-04-22",
    "address": {
      "street": "245 Pine St, Apt 4B",
      "city": "San Jose",
      "state": "CA",
      "zip_code": "95110"
    }
  },
  "policy": {
    "policy_number": "AUTO-2024-77821",
    "policy_type": "auto",
    "insurer_name": "Acme Mutual Insurance Co.",
    "effective_date": "2024-03-15",
    "expiration_date": "2025-03-15",
    "total_premium": "1035.00",
    "coverages": [
      {"coverage_type": "bodily_injury_liability", "limit": "250000", "premium": "725"},
      {"coverage_type": "collision", "deductible": "500", "premium": "310"}
    ]
  },
  "claim": null,
  "beneficiaries": [],
  "raw_notes": "Bodily Injury Liability also lists per-accident limit 500000."
}"""


_V3_USER_TEMPLATE_RAW = """Extract structured information from the insurance document.
Your output MUST validate against this JSON schema:

```json
<<SCHEMA>>
```

Rules:
  1. Use null when a field is absent. Never guess.
  2. Dates: ISO 8601 (YYYY-MM-DD).
  3. Money: plain numeric strings, no symbols.
  4. If multiple persons are listed, separate into policy_holder vs additional_insureds vs beneficiaries.
  5. Information that is important but does not fit any schema field belongs in raw_notes.
  6. Output a single JSON object only.

EXAMPLE INPUT:
---
<<EXAMPLE_INPUT>>
---

EXAMPLE OUTPUT:
<<EXAMPLE_OUTPUT>>

NOW EXTRACT FROM THIS DOCUMENT:
---
<<DOCUMENT_TEXT>>
---
"""

V3_USER_TEMPLATE = (
    _V3_USER_TEMPLATE_RAW
    .replace("<<SCHEMA>>", schema_as_json_string())
    .replace("<<EXAMPLE_INPUT>>", _FEW_SHOT_EXAMPLE_INPUT)
    .replace("<<EXAMPLE_OUTPUT>>", _FEW_SHOT_EXAMPLE_OUTPUT)
)
