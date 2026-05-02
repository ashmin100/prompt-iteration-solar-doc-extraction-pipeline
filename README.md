# 📄 solar-doc-extraction-pipeline

<div align="center">

**An end-to-end pipeline for extracting structured information from insurance forms —
with prompt-iteration logs and an evaluation harness that compares prompt versions on the same document set.**

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Pydantic](https://img.shields.io/badge/Pydantic-v2-E92063?style=flat-square&logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)
[![Ollama](https://img.shields.io/badge/Ollama-Local%20LLM-black?style=flat-square)](https://ollama.com/)
[![Groq](https://img.shields.io/badge/Groq-Compatible-F55036?style=flat-square)](https://groq.com/)
[![OpenAI](https://img.shields.io/badge/OpenAI-Compatible-412991?style=flat-square&logo=openai&logoColor=white)](https://openai.com/)
[![Status](https://img.shields.io/badge/Status-Active%20Build-brightgreen?style=flat-square)]()

</div>

> Insurance forms are a demanding stress test for document-AI prompt engineering: semi-structured, partially blank in the wild, dense with money and date fields, and downstream systems will not tolerate schema drift.
>
> The bottleneck when deploying LLMs against forms like these is rarely the model — it's prompt design that is robust to messy inputs and produces JSON a downstream system can trust. This repo is a scaled-down, end-to-end take on that loop: a Pydantic-typed schema, three prompt versions framed as falsifiable hypotheses, and an eval harness that turns each version's effect on schema validity, field-level F1, and hallucination rate into a single auto-generated comparison.

---

## Table of Contents

- [What's Inside](#-whats-inside)
- [Quickstart](#-quickstart)
- [Backends & Configuration](#-backends--configuration)
- [Prompt Iteration Log](#-prompt-iteration-log)
- [Eval Harness](#-eval-harness)
- [Dataset & Tier Strategy](#-dataset--tier-strategy)
- [Repository Layout](#️-repository-layout)
- [Status](#-status)

---

## 📦 What's Inside

| Layer | File | Notes |
|-------|------|-------|
| **Multi-backend LLM client** | `src/llm_client.py` | OpenAI-compatible. Defaults to local Ollama; supports Groq / HF Inference / any OpenAI-compatible endpoint via env vars. |
| **Document parser** | `src/parser.py` | `parse_document(path, mode='text' \| 'vlm-qwen')`. `text` mode uses `pdfplumber`; `vlm-qwen` renders PDF pages with PyMuPDF and transcribes with local Ollama `qwen2.5vl:7b`. |
| **Schema** | `src/schema.py` | Pydantic v2 model `InsuranceForm` (ACORD-aligned). Money/date validators, `extra="ignore"` to tolerate over-eager LLM keys. |
| **Prompts** | `src/prompts/` | `v1` (zero-shot) · `v2` (schema-injected) · `v3` (schema + few-shot + edge rules). |
| **Pipeline** | `src/extractor.py` | parse → prompt → JSON parse → Pydantic validate, with diagnostics for the eval harness. |
| **Synthetic generator** | `data/synth_generator.py` | `Faker`-driven generator producing varied insurance forms + typewriter-style PDFs via `reportlab` for parser ablations. |
| **Eval harness** | `src/eval/` | Type-aware metrics (categorical / id / date / money / fuzzy / phone / email), greedy list matching, schema validity rate, hallucination / omission rates, latency p50/p95. Three-tier reporting. |
| **CLI** | `src/cli.py` | `extract` and `evaluate` subcommands. |

---

## 🚀 Quickstart

### 1. Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Choose a Backend

```bash
cp .env.example .env
```

**Option A — Ollama** (no API key, fully local)

```bash
ollama pull llama3.1:8b
# In .env:
LLM_BACKEND=ollama
```

**Option B — Groq** (faster demo, free tier available)

```bash
# Set GROQ_API_KEY in .env, then:
LLM_BACKEND=groq
```

### 3. Run Extraction

```bash
python -m src.cli extract --pdf data/samples/your_form.pdf --version v2
```

---

## ⚙️ Backends & Configuration

### Custom OpenAI-Compatible Endpoints

Most modern serving stacks expose an OpenAI-compatible `/v1/chat/completions` endpoint. To point this pipeline at any of them — Together, OpenRouter, Fireworks, vLLM, a private model gateway, etc. — set in `.env`:

```bash
LLM_BACKEND=openai_compat
OPENAI_COMPAT_BASE_URL=<your endpoint, e.g. https://your-gateway/v1>
OPENAI_COMPAT_API_KEY=<your key>
OPENAI_COMPAT_MODEL=<model identifier>
```

No code changes required. The same prompts, schema, and eval harness run unchanged across all backends.

---

## 🧪 Prompt Iteration Log

Each prompt version is a falsifiable hypothesis. We record what we expected the change to fix and what the eval harness actually showed.

Full details in [`docs/prompt_iteration_log.md`](docs/prompt_iteration_log.md).

| Version | Key Change | Hypothesis | Status |
|---------|-----------|------------|--------|
| **v1** | Zero-shot, JSON-by-request | Baseline. Expect ~50% schema validity on small open-source models. | ✅ Implemented |
| **v2** | Full Pydantic JSON schema + ISO-8601/money rules + `response_format: json_object` | v1 drifts on field names and date formats. | ✅ Implemented |
| **v3** | v2 + 1 worked few-shot example + edge-case rules (multiple persons, partial blanks) | v2 still hallucinates when the form is sparse. | ✅ Implemented |

---

## 📊 Eval Harness

### Run All Prompt Versions

```bash
python -m src.cli evaluate --versions v1,v2,v3 --out results/eval_v1_v2_v3.md
```

### PDF Parser Ablation

Compare `pdfplumber + v3` vs `qwen2.5vl:7b page transcription + v3` on the same document set:

```bash
# Text parser baseline
python -m src.cli evaluate --versions v3 \
  --parser-mode text \
  --out results/eval_text_qwen3.md

# VLM parser
python -m src.cli evaluate --versions v3 \
  --parser-mode vlm-qwen \
  --out results/eval_vlm_qwen.md
```

### Metrics Reported

The harness loads every `(samples/<id>.{txt,pdf}, ground_truth/<id>.json)` pair, runs each version, and writes a markdown report covering:

| Metric | Description |
|--------|-------------|
| **Schema validity rate** | Fraction of predictions that parse + Pydantic-validate |
| **Field accuracy & F1** | Type-aware: exact match for IDs/categoricals, normalized for dates/money, fuzzy ratio (≥ 0.85) for names/addresses, greedy key-based matching for list fields (`coverages`, `beneficiaries`) |
| **Hallucination rate** | Fields the model filled that ground truth left null |
| **Omission rate** | Fields ground truth populated that the model returned null |
| **Latency p50 / p95** | Per prompt version, per backend |
| **Per-document failure breakdown** | Which docs failed schema, parse, or had wrong/hallucinated fields |

> Results are reported separately for the **real** and **synthetic** tiers so synthetic numbers don't inflate the headline.

---

## 🗃️ Dataset & Tier Strategy

Public-domain *filled* insurance forms are rare because real filled forms contain PII. Rather than scrape borderline material, this repo uses a **three-tier dataset** that turns the data-availability problem into a deliberate evaluation design.

| Tier | Contents | What It Measures |
|------|----------|-----------------|
| **`synthetic_*`** | 15 hand-written + Faker-generated text samples across 8 form types | Primary accuracy / F1 — where v1 → v2 → v3 lift is measured |
| **`blank_*`** | 4 real public-domain blank forms (CMS-1500, IRS 1095-A, ACORD 25, NAIC life app) | Hallucination resistance — does the model invent values into placeholder lines? |
| **`filled_*`** | _Deferred_ | Real-layout robustness; planned via VLM parsing path (see `docs/future_work.md §1`) |

<details>
<summary>Notes on the real-PDF set</summary>

The current Tier 1 real-PDF set uses four public documents saved under `data/samples/`: IRS 1095-A, CMS-1500, an ACORD 25 certificate example, and the NAIC life insurance buyer's guide. The planned California DOI auto insurance sample was excluded because the official `insurance.ca.gov` PDF endpoint repeatedly timed out during local download; it can be added later without changing the evaluation flow.

</details>

### Regenerate the Synthetic Tier

```bash
pip install faker
python data/synth_generator.py --n 8 --seed 42
```

---

## 🗂️ Repository Layout

```
solar-doc-extraction-pipeline/
├── src/
│   ├── schema.py          # Pydantic InsuranceForm
│   ├── parser.py          # PDF → text (text | vlm-qwen)
│   ├── llm_client.py      # Multi-backend OpenAI-compatible client
│   ├── extractor.py       # parse → prompt → JSON → validate
│   ├── prompts/           # v1 / v2 / v3
│   ├── eval/              # Metrics + harness + report generator
│   └── cli.py             # extract and evaluate subcommands
├── data/
│   ├── samples/           # 7 synthetic .txt + real PDFs
│   ├── ground_truth/      # One JSON per sample
│   └── synth_generator.py
├── results/               # eval_v1_v2_v3.md (auto-generated)
├── docs/                  # Prompt iteration log + future work
├── notebooks/             # Demo
└── tests/
```

---

## 🔖 Status

- ✅ End-to-end pipeline
- ✅ Three prompt versions (v1 / v2 / v3)
- ✅ Type-aware eval harness
- ✅ Three-tier dataset (15 synthetic + 4 blank; filled deferred)
- ✅ `vlm-qwen` parser path implemented for local Qwen2.5-VL via Ollama
- 🔄 `results/eval_text_qwen3.md` and `results/eval_vlm_qwen.md` — pending (to quantify the pdfplumber baseline vs VLM trade-off)
