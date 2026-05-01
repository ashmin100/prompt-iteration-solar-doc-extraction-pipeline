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
| Document parser | `src/parser.py` | `parse_document(path, mode='text' \| 'vlm-qwen')`. `text` mode uses `pdfplumber`; `vlm-qwen` renders PDF pages with PyMuPDF and transcribes them with local Ollama `qwen2.5vl:7b`. |
| Schema | `src/schema.py` | Pydantic v2 model `InsuranceForm` (ACORD-aligned). Money/date validators, `extra="ignore"` to tolerate over-eager LLM keys. |
| Prompts | `src/prompts/` | `v1` (zero-shot), `v2` (schema-injected), `v3` (schema + few-shot + edge rules). |
| Pipeline | `src/extractor.py` | parse → prompt → JSON parse → Pydantic validate, with diagnostics for the eval harness. |
| Synthetic generator | `data/synth_generator.py` | `Faker`-driven generator producing varied insurance forms plus typewriter-style PDFs via `reportlab` for parser ablations. |
| Eval harness | `src/eval/` | Type-aware metrics (categorical / id / date / money / fuzzy / phone / email), greedy list matching, schema validity rate, hallucination / omission rates, latency p50/p95. Three-tier reporting (`synthetic` / `blank` / `filled`). |
| CLI | `src/cli.py` | `python -m src.cli extract --pdf ... --version v2` and `python -m src.cli evaluate --versions v1,v2,v3` |

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

## Eval harness

Run all three prompt versions against the dataset in one shot:

```bash
python -m src.cli evaluate --versions v1,v2,v3 --out results/eval_v1_v2_v3.md
```

For the PDF parser ablation, run the same prompt version against the same
PDF-backed dataset with two parser modes:

```bash
python -m src.cli evaluate --versions v3 \
  --parser-mode text \
  --out results/eval_text_qwen3.md

python -m src.cli evaluate --versions v3 \
  --parser-mode vlm-qwen \
  --out results/eval_vlm_qwen.md
```

This compares `pdfplumber + v3` against `qwen2.5vl:7b page transcription + v3`
on the same synthetic and blank-form stems. The `.txt` files remain as
human-readable references; when a matching PDF exists, the harness evaluates
the PDF.

The harness loads every `(samples/<id>.{txt,pdf}, ground_truth/<id>.json)`
pair under `data/`, runs each version, and writes a markdown report with:

- **Schema validity rate** — fraction of predictions that parse + Pydantic-validate.
- **Field accuracy & F1** — per-field comparison with type-aware rules: exact match for IDs / categoricals, normalized comparison for dates and money, fuzzy ratio (≥ 0.85) for names / addresses, greedy key-based matching for list fields like `coverages` and `beneficiaries`.
- **Hallucination rate** — fields the model filled that ground truth left null.
- **Omission rate** — fields ground truth populated that the model returned null.
- **Latency p50 / p95** — per prompt version, per backend.
- **Per-document failure breakdown** — which docs failed schema, parse, or had wrong / hallucinated fields.

Reported separately for the **real** tier (public-domain PDFs) and the
**synthetic** dev tier so synthetic numbers don't inflate the headline.

Current Tier 1 real-PDF set uses four public documents saved under
`data/samples/`: IRS 1095-A, CMS-1500, an ACORD 25 certificate example, and
the NAIC life insurance buyer's guide. The planned California DOI auto
insurance sample was excluded from this pass because the official
`insurance.ca.gov` PDF endpoint repeatedly timed out during local download;
it can be added later without changing the evaluation flow.

## Repository layout

```
solar-doc-extraction-pipeline/
├── src/
│   ├── schema.py          # Pydantic InsuranceForm
│   ├── parser.py          # PDF → text
│   ├── llm_client.py      # multi-backend OpenAI-compatible client
│   ├── extractor.py       # parse → prompt → JSON → validate
│   ├── prompts/           # v1 / v2 / v3
│   ├── eval/              # metrics + harness + report
│   └── cli.py             # `extract` and `evaluate` subcommands
├── data/
│   ├── samples/           # 7 synthetic .txt + your real PDFs
│   └── ground_truth/      # one JSON per sample
├── results/               # eval_v1_v2_v3.md (auto-generated)
├── docs/                  # prompt iteration log
├── notebooks/             # demo
└── tests/
```

## Dataset & tier strategy

Public-domain *filled* insurance forms are vanishingly rare because real
filled forms contain PII. Rather than scrape borderline material, this repo
uses a **three-tier dataset** that turns the data-availability problem into
a deliberate evaluation design:

| Tier | What's in it | What it measures |
| --- | --- | --- |
| **synthetic** (`synthetic_*`) | 15 hand-written + Faker-generated text samples covering 8 form types | Primary accuracy / F1; this is where v1 → v2 → v3 lift is measured |
| **blank** (`blank_*`) | 4 real public-domain blank forms (CMS-1500, IRS 1095-A, ACORD 25, NAIC life app) | Hallucination resistance — does the model invent values into placeholder lines? |
| **filled** (`filled_*`) | _deferred_ | Real-layout robustness; planned via VLM parsing path (see `docs/future_work.md` §1) |

Each tier is reported separately so synthetic numbers don't inflate the
headline. To regenerate the synthetic tier:

```bash
pip install faker
python data/synth_generator.py --n 8 --seed 42
```

## Status

Day 2 of a one-week build. End-to-end pipeline + three prompt versions +
type-aware eval harness + three-tier dataset (15 synthetic + 4 blank,
filled deferred). The `vlm-qwen` parser path is implemented for local
Qwen2.5-VL via Ollama; evaluation is pending/ongoing. Next: generate
`results/eval_text_qwen3.md` and `results/eval_vlm_qwen.md` to quantify the
pdfplumber baseline vs VLM trade-off.
