"""v2 — Inject the full JSON schema into the prompt.

Hypothesis: open-source 7B/8B models drift on field names without an explicit
schema. Pasting the Pydantic-generated JSON schema reduces schema-validity
failures dramatically.

Diff from v1:
  + Full JSON schema injected.
  + Explicit "fields not in schema must be ignored or placed in raw_notes".
  + Explicit ISO 8601 for dates and bare-number strings for money.
"""

from src.schema import schema_as_json_string

V2_SYSTEM = """You are a strict information extraction assistant for insurance
forms. You return ONLY a single valid JSON object that conforms to the provided
schema. No prose. No code fences. Never invent data."""


_V2_USER_TEMPLATE_RAW = """Extract structured information from the insurance document
below. Your output MUST validate against this JSON schema:

```json
<<SCHEMA>>
```

Rules:
  1. If a field is not in the document, use null.
  2. Dates must be ISO 8601 (YYYY-MM-DD).
  3. Money values must be plain numeric strings ("1450.00"), no currency symbols.
  4. Any information that is important but does not fit a schema field goes into
     `raw_notes` as a short paragraph.
  5. Do NOT include keys that are not in the schema.
  6. Output a single JSON object — no surrounding prose, no code fences.

DOCUMENT:
---
<<DOCUMENT_TEXT>>
---
"""

# Bake the schema in once at import time.
V2_USER_TEMPLATE = _V2_USER_TEMPLATE_RAW.replace("<<SCHEMA>>", schema_as_json_string())
