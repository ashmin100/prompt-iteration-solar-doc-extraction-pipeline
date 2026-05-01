# solar-doc-extraction-pipeline

An end-to-end pipeline for extracting structured information from insurance
forms, with **prompt-iteration logs** and an **evaluation harness** that
compares prompt versions on the same set of documents. Insurance forms are
a good stress test for document-AI prompt engineering: they are
semi-structured, partially blank in the wild, dense with money and date
fields, and downstream systems will not tolerate schema drift.

> **Why this project.** When LLMs are deployed against forms like these,
> the bottleneck is rarely the model — it's prompt design that is robust to
> messy inputs and produces JSON a downstream system can trust. This repo
> is a scaled-down, end-to-end take on that loop: a Pydantic-typed schema,
> three prompt versions framed as falsifiable hypotheses, and an eval
> harness that turns each version's effect on schema validity, field-level
> F1, and hallucination rate into a single auto-generated comparison.

## What's inside

| Layer | File | Notes |
| --- | --- | --- |
| Multi-backend LLM client | `src/llm_client.py` | OpenAI-compatible. Defaults to **local Ollama**; Groq / HF Inference / any OpenAI-compatible endpoint via env vars. |
| PDF parser | `src/parser.py` | `pdfplumber` page-by-page extraction with `[PAGE n]` markers. |
| Schema | `src/schema.py` | Pydantic v2 model `InsuranceForm` (ACORD-aligned). Money/date validators, `extra="ignore"` to tolerate over-eager LLM keys. |
| Prompts | `src/prompts/` | `v1` (zero-shot), `v2` (schema-injected), `v3` (schema + few-shot + edge rules). |
| Pipeline | `src/extractor.py` | parse → prompt → JSON parse → Pydantic validate, with diagnostics for the eval harness. |
| CLI | `src/cli.py` | `python -m src.cli extract --pdf ... --version v2` |
| Eval harness | `src/eval/` | (next milestone) field-level F1, schema-validity rate, hallucination rate, latency. |

## Quickstart

```bash
# 1. install
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. pick a backend (default: local Ollama)
cp .env.example .env

# Option A — Ollama (no key, true open-source)
ollama pull llama3.1:8b
LLM_BACKEND=ollama

# Option B — Groq free tier (faster demo)
# Set GROQ_API_KEY in .env, then
LLM_BACKEND=groq

# 3. run on the included synthetic sample (wrap the .txt as a 1-page PDF, or pass text directly via the API)
python -m src.cli extract --pdf data/samples/your_form.pdf --version v2
```

## Custom OpenAI-compatible endpoints

Most modern serving stacks expose an OpenAI-compatible `/v1/chat/completions`
endpoint. To point this pipeline at any of them — Together, OpenRouter,
Fireworks, vLLM running locally, a private model gateway, etc. — set in
`.env`:

```bash
LLM_BACKEND=openai_compat
OPENAI_COMPAT_BASE_URL=<your endpoint, e.g. https://your-gateway/v1>
OPENAI_COMPAT_API_KEY=<your key>
OPENAI_COMPAT_MODEL=<model identifier>
```

No code changes. The same prompts, schema, and eval harness run unchanged.

## Prompt iteration log (live)

Each version is a hypothesis. We record what we expected the change to fix and
what the eval harness actually showed. See `docs/prompt_iteration_log.md`.

| Version | Key change | Why | Status |
| --- | --- | --- | --- |
| v1 | Zero-shot, JSON-by-request | Baseline. Expect ~50% schema validity on small open-source models. | implemented |
| v2 | Inject full Pydantic JSON schema + ISO-8601/money rules + `response_format: json_object` | v1 drifts on field names and date formats. | implemented |
| v3 | v2 + 1 worked few-shot example + edge-case rules (multiple persons, partial blanks) | v2 still hallucinates when the form is sparse. | implemented |

## Eval harness (planned)

Metrics compared across `v1 / v2 / v3`:

- **Schema validity rate** — does the output parse + validate?
- **Field-level F1** — exact match for IDs/dates/amounts, fuzzy for free-form.
- **Hallucination rate** — fraction of fields filled that aren't in source.
- **Latency / tokens** — p50 / p95 per prompt version, per backend.

Output: `results/eval_v1_v2_v3.md` (auto-generated comparison table).

## Repository layout

```
solar-doc-extraction-pipeline/
├── src/                  # pipeline + prompts + (eval — next)
├── data/
│   ├── samples/          # PDFs go here; one synthetic .txt included
│   └── ground_truth/     # one JSON per sample (manually written)
├── results/              # eval reports (auto-generated)
├── docs/                 # prompt iteration logs, design notes
├── notebooks/            # demo notebooks
└── tests/
```

## Status

Day 1 of a one-week build. Schema, multi-backend client, three prompt
versions, and one synthetic ground-truth sample are in. Next: the eval
harness, plus 4–6 additional public-domain samples and matching ground truth.
