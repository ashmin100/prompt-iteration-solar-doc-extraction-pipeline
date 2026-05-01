# Prompt iteration log

A running record of what was changed between prompt versions, the hypothesis
behind the change, and what the eval harness actually showed.

> The point of this log is not to look polished — it is to make the iteration
> loop visible. If a hypothesis was wrong, that gets recorded too.

## v1 — Zero-shot baseline

**Prompt sketch.** Plain English description of the desired keys. No JSON
schema. No examples. Temperature 0.

**Hypothesis.** A modern instruction-tuned 7–8B open-source model can produce
a roughly correct JSON shape from a plain English description, but will drift
on:

- Field naming (camelCase vs snake_case).
- Date formats (`MM/DD/YYYY` vs `YYYY-MM-DD`).
- Money values (`$1,334.00` string vs numeric).
- Hallucinated fields when the form is partially blank.

**Result placeholder.** _(populated after eval harness lands)_

---

## v2 — Inject full schema + JSON mode

**Diff vs v1.**

- Pasted the full `InsuranceForm.model_json_schema()` into the user prompt.
- Added explicit rules: ISO 8601 dates, plain numeric strings for money,
  null over guess.
- Used `response_format={"type": "json_object"}` for backends that honour it.
- Tightened the system prompt: "no prose, no code fences, no extra keys".

**Hypothesis.** Most v1 failures are field-name / format drift, not
comprehension. Pinning the schema in-prompt should bring schema validity
from ~50% to >85% on the same model.

**Result placeholder.** _(populated after eval harness lands)_

---

## v3 — Schema + few-shot + edge-case rules

**Diff vs v2.**

- Added one fully-worked example (auto declaration page → JSON).
- Added explicit rules for ambiguous cases:
  - Multiple persons → split across `policy_holder`, `additional_insureds`,
    `beneficiaries`.
  - Important info that doesn't fit a field → `raw_notes`.
  - Partial blanks → null.

**Hypothesis.** v2 still produces shape-valid JSON whose values drift when
the form is sparse or has multiple persons. A single worked example pins
the model on these decisions without a large prompt-length cost.

**Result placeholder.** _(populated after eval harness lands)_

---

## What I expect to see in the eval

- v1 schema validity well below v2 — most v1 failures will be parse / type
  errors, not semantic ones.
- v2 → v3 lift will be smaller than v1 → v2, mostly on hallucination rate
  and on multi-person forms.
- Latency will be roughly v1 < v2 < v3 because prompt length grows; the
  question is whether the quality lift justifies the latency.

---

## Tier 1 ground-truthing notes (2026-05-01)

Labeled 4 public PDFs (IRS 1095-A, CMS-1500, ACORD 25, NAIC life insurance buyer's guide) using model-assisted labeling with qwen3:14b. v3 produced the first draft, then each JSON was corrected to the `InsuranceForm` ground-truth shape. Most common corrections: hallucinated or schema-drifted keys on blank forms; mis-categorized 1095-A as unknown instead of health; non-enum policy type emitted for ACORD 25; NAIC buyer's guide treated as an application despite containing only educational content.
