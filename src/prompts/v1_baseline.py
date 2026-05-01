"""v1 — Baseline zero-shot prompt.

Hypothesis: ask the model nicely for JSON, parse with Pydantic.
Known weaknesses (to be addressed in v2/v3):
  - Field names drift (e.g., 'policyNumber' vs 'policy_number').
  - Hallucinated fields not present in the source.
  - Date formats inconsistent.
  - Money values come back as strings with currency symbols.
"""

V1_SYSTEM = """You are an information extraction assistant for insurance forms.
Given the raw text of a scanned/parsed insurance document, extract the relevant
fields and return ONLY a single JSON object. Do not include any prose, no code
fences, no explanation."""


V1_USER_TEMPLATE = """Extract the following from the insurance document below.

Return a JSON object with these keys:
  - form_type: one of policy_application, declaration_page, claim_form, unknown
  - policy_holder: {full_name, date_of_birth, phone, email, address}
  - policy: {policy_number, policy_type, insurer_name, effective_date, expiration_date, total_premium, coverages: []}
  - claim: {claim_number, date_of_loss, loss_description, estimated_amount} (only if claim form)
  - beneficiaries: list of persons
  - raw_notes: anything important you saw that didn't fit a field

If a field is unknown or absent, set it to null. Do not invent values.

DOCUMENT:
---
<<DOCUMENT_TEXT>>
---
"""
