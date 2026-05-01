# Future work — research-informed extensions

This is a living plan for what comes after the current v1/v2/v3 + eval-harness
baseline. Each entry below names a concrete technique, the paper(s) it draws
from, and where in this repo it would plug in. Status is tracked inline so the
plan stays honest as pieces move from "future work" into the implementation.

The scope of this project is *prompt-engineering for document AI*, so the
relevant literature falls into four buckets:

1. **Layout-aware document understanding** — replacing the naïve
   `pdfplumber → text` step with something that preserves tables, checkboxes,
   and spatial structure.
2. **Programmatic prompt optimization** — turning the human-authored
   v1 → v2 → v3 ladder into an automatic search loop driven by the eval
   harness.
3. **Constrained / grammar-guided decoding** — making schema validity 100%
   by construction instead of by prompt instruction.
4. **Self-refinement and LLM-as-judge** — extra inference passes that catch
   residual errors before they hit the metric.

---

## 1. Layout-aware document understanding (replaces `src/parser.py`)

**Status:** partially implemented. The Qwen2.5-VL path is now wired through
`src/parser.py` as `parser_mode='vlm-qwen'`, synthetic `.txt` samples can be
rendered to PDFs with `data/synth_generator.py`, and the eval harness dedupes
`.txt`/`.pdf` stems so `text` and `vlm-qwen` modes can be compared on the same
dataset. Phase 3 ablation results are still pending.

### Why
`pdfplumber` flattens spatial layout: tables collapse, checkbox state is
lost, multi-column pages get interleaved. On real ACORD / CMS-1500 forms
this is the largest single source of v3 failures we'd expect to see — the
information is on the page, the parser just throws it away before the LLM
gets a chance.

### Candidates (most promising first)

| Tool | Type | Why relevant | Effort |
| --- | --- | --- | --- |
| **Qwen2.5-VL 7B** ⭐ chosen | Open-weight VLM | Selected for this hardware (M4 Pro 24GB unified memory). 7B fits comfortably (~6GB), leaves headroom for KV cache + OS. Prior Qwen-VL + SAM2.1 experience on resume. Local via Ollama (`qwen2.5vl:7b`). | 1–2 days |
| **olmOCR** (AI2, 2025) | OSS layout-aware OCR | Recent (2025) AI2 release; tuned for academic / form documents; outputs reading-order text + layout coordinates. | 0.5 day |
| **Marker** + **Surya** (VikParuchuri, OSS) | OSS PDF → markdown | Lightweight, runs on a single GPU; preserves table structure as markdown. Good middle ground. | 0.5 day |
| **Mistral Small 3.2 24B** | Multimodal | Considered; ~14GB at Q4 plus KV cache pushes 24GB unified memory near the limit. Higher quality ceiling but slower. Held in reserve as ablation if 7B underperforms. | 1–2 days |
| **Donut** (Kim et al., ECCV 2022) | OCR-free encoder-decoder | "OCR-free Document Understanding Transformer." End-to-end image → JSON, but pretrained on receipts (CORD); needs fine-tune for insurance domain. | 2–3 days |
| **LayoutLMv3** (Huang et al., 2022) | Pretrained layout model | Tokens get layout coordinates as positional features. Mature, but predates the LLM era; better as a feature extractor feeding our prompt. | 1 day |

### Integration plan (`qwen2.5vl:7b` via Ollama)

The parser interface in `src/parser.py` is already structured for this:
`parse_document(path, mode='text' | 'vlm-qwen' | …)`. Only the new mode
implementation is needed.

**Phase 1 — render synthetic .txt samples to PDFs.** Implemented. Add `--format pdf` to
`data/synth_generator.py` that pipes the existing text through `reportlab`
to produce a typewriter-style PDF. This gives the VLM mode something to
read on the synthetic tier without manual data hunting.

**Phase 2 — implement `vlm-qwen` mode.** Implemented.
1. `pdf2image` (or `pymupdf`) to render PDF pages → PIL images.
2. Encode each page image as base64 and send to Ollama's
   `qwen2.5vl:7b` model with a prompt like
   *"Extract the text content of this insurance form, preserving
   table structure and indicating which checkboxes are checked."*
3. Concatenate per-page outputs with `[PAGE n]` markers (same shape as
   `text` mode), so the rest of the pipeline runs unchanged.
4. Optionally also pass extracted `layout_blocks` to v3 prompt as a
   separate "structural hints" block.

**Phase 3 — ablation.** In progress. Same harness, same dataset, two parser modes. Add
two columns to `results/eval_v1_v2_v3.md`: `v3 + text` vs `v3 + vlm-qwen`.
Hypothesis: blank-tier hallucination drops because the VLM can see actual
empty fields vs filled, instead of getting only the form labels;
synthetic-tier F1 stays similar because synthetic samples have no
layout-encoded information.

**Hardware note.** `qwen2.5vl:7b` Q4_K_M is about 6GB on M4 Pro 24GB. Image
prefill adds ~1–2GB per page in KV cache. Expect ~10–30 sec per page;
~4 minutes per full-doc evaluation pass on a 10-doc subset. Workable.

### References
- Kim et al., "OCR-free Document Understanding Transformer" (Donut), ECCV 2022.
- Huang et al., "LayoutLMv3: Pre-training for Document AI with Unified Text and Image Masking", ACM MM 2022.
- Bai et al., "Qwen2.5-VL Technical Report" (Alibaba, 2024).
- Lee et al., "Pix2Struct: Screenshot Parsing as Pretraining for Visual Language Understanding", ICML 2023.
- Faysse et al., "ColPali: Efficient Document Retrieval with Vision Language Models" (2024) — relevant for retrieval over many forms.

---

## 2. Programmatic prompt optimization (replaces hand-authored v1/v2/v3)

### Why
The current v1 → v2 → v3 ladder is *human-authored gradient descent*: I
wrote a hypothesis, tested it, wrote the next one. That works for three
iterations; it doesn't scale. The eval harness already emits a scalar
quality signal (overall F1). That signal can drive an automatic optimizer.

### Candidates

| Tool | Mechanism | Why relevant |
| --- | --- | --- |
| **DSPy** (Khattab et al., 2024) | Compiles declarative `Module` definitions; optimizers like `BootstrapFewShot` and `MIPRO` (Multi-prompt Instruction Proposal Optimizer) auto-pick demonstrations and instruction text. | Mature, well-documented. Most direct fit — we already have a typed Module (`Extractor`) and a metric. |
| **TextGrad** (Yuksekgonul et al., 2024) | Treats LLM-generated feedback as "textual gradients" and back-propagates them through a prompt. | More interpretable per-step than DSPy's optimizers. Useful when we want to understand *why* the optimizer changed something. |
| **PromptBreeder** (Fernando et al., DeepMind 2023) | Evolutionary / mutation-based prompt search. | Higher-variance; better for exploring radically different prompt structures. |
| **OPRO** (Yang et al., DeepMind 2023) | LLM-as-optimizer — feed prior (prompt, score) pairs back to a meta-LLM. | Simplest baseline to implement from scratch. |

### Integration plan (DSPy first)
- Wrap our extractor as a DSPy `Predict` module with the `InsuranceForm`
  schema as the output signature.
- Wrap the harness's `aggregate(...).f1` as a DSPy metric.
- Run `BootstrapFewShot` to auto-select demonstrations from the synthetic
  dev set.
- Run `MIPRO` on top to also optimize the system message.
- Output: `src/prompts/v4_dspy_optimized.py`. Add to the eval as a fourth
  column. Honest reporting: include both the *training* split (where
  optimization happened) and a *held-out* split.

### Open questions to address in interviews
- DSPy's optimizers tend to over-fit small dev sets. Held-out vs in-dist gap
  is what matters; v4 winning on dev but not on held-out would itself be a
  finding worth reporting.
- Cost: optimization runs ~50–500 LLM calls. Has to be on a fast hosted
  endpoint (Groq) not local 14B.

### References
- Khattab et al., "DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines", ICLR 2024.
- Opsahl-Ong et al., "Optimizing Instructions and Demonstrations for Multi-Stage Language Model Programs" (MIPROv2 paper, 2024).
- Yuksekgonul et al., "TextGrad: Automatic Differentiation via Text" (2024).
- Yang et al., "Large Language Models as Optimizers" (OPRO), ICLR 2024.
- Fernando et al., "Promptbreeder: Self-Referential Self-Improvement Via Prompt Evolution" (DeepMind, 2023).
- Pryzant et al., "Automatic Prompt Optimization with 'Gradient Descent' and Beam Search" (ProTeGi, EMNLP 2023).

---

## 3. Constrained / grammar-guided decoding (raises schema validity to 100%)

### Why
Right now schema validity is the first gate every prediction has to pass,
and v1's failures there are *purely structural* (wrong key names, wrong
date formats). We can eliminate that failure class entirely by constraining
generation against the Pydantic schema's JSON Schema, instead of asking
the model nicely.

### Candidates

| Tool | Notes |
| --- | --- |
| **Outlines** (Willard & Louf, 2023) | FSM-based constrained decoding. Mature. Works with most local backends; excellent Pydantic integration (`outlines.generate.json(model, InsuranceForm)`). |
| **xgrammar** (Dong et al., 2024) | Highly optimized grammar-guided decoder. Recently integrated into vLLM and SGLang. Lower latency overhead than Outlines. |
| **LM Format Enforcer** | Token-mask approach. Drop-in for HF and vLLM. |
| Built-in JSON mode (OpenAI / Groq / Solar) | Lightest; we already use it for v2/v3. Doesn't enforce per-field schema, only "is JSON". |

### Integration plan
- Add a fourth backend mode `LLM_BACKEND=ollama+outlines` that wraps Ollama
  with an Outlines decoder and yields a guaranteed-valid InsuranceForm.
- Compare in the eval: `v3 free-form` vs `v3 + Outlines`. Schema validity
  goes to 100%; the question is whether constrained decoding *helps* or
  *hurts* field accuracy (sometimes it forces poor choices in cells the
  model is unsure about).

### References
- Willard & Louf, "Efficient Guided Generation for Large Language Models" (Outlines, 2023).
- Dong et al., "XGrammar: Flexible and Efficient Structured Generation Engine" (2024).

---

## 4. Self-refinement and LLM-as-judge (catches residual errors)

### Why
Even with v3 + constrained decoding, we'd expect ~5% residual hallucination
on truly ambiguous fields (was that "John Q. Smith Jr." in the form a
beneficiary or a witness?). A second pass that critiques the first
extraction can catch many of these without retraining.

### Candidates

| Technique | Paper |
| --- | --- |
| **Self-Refine** | Madaan et al., "Self-Refine: Iterative Refinement with Self-Feedback", NeurIPS 2023. Same model produces output → critique → revised output. |
| **Reflexion** | Shinn et al., "Reflexion: Language Agents with Verbal Reinforcement Learning", NeurIPS 2023. Adds an explicit "memory" of past failures across documents. |
| **LLM-as-Judge** | Zheng et al., "Judging LLM-as-a-Judge with MT-Bench" (2023). For the fuzzy comparator in our metric module: replace `SequenceMatcher.ratio() >= 0.85` with an LLM judge for ambiguous string fields. |
| **SelfCheckGPT** | Manakul et al., 2023. Sample multiple outputs, measure consistency, use disagreement as a hallucination signal. |

### Integration plan
- Add `src/extractor.py: extract_with_self_refine(...)` that runs v3,
  produces an output, then issues a second prompt: *"Here is a document and
  a candidate extraction. List any field that is wrong or hallucinated.
  Output a corrected JSON."*
- Track **lift over base v3** in the eval as `v3+selfrefine`. Honest cost
  reporting: 2x the latency, 2x the token spend.

### References
- Madaan et al., "Self-Refine: Iterative Refinement with Self-Feedback", NeurIPS 2023.
- Shinn et al., "Reflexion: Language Agents with Verbal Reinforcement Learning", NeurIPS 2023.
- Zheng et al., "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena" (2023).
- Manakul et al., "SelfCheckGPT: Zero-Resource Black-Box Hallucination Detection" (EMNLP 2023).

---

## 5. Domain-specific extensions (insurance-flavored)

These don't have one canonical paper but are the directions that would make
the project specifically valuable to an insurance Document AI team.

- **Form-type router → sub-schema.** Right now one schema covers auto, home,
  life, health, commercial. Real production systems use a thin classifier
  to pick the form type first, then route to a domain-specialized schema.
  Hypothesis: F1 lifts substantially on auto vs life because each schema
  is shorter and prompt context is more focused.
- **Korean insurance forms.** Upstage's largest customers (Samsung Life,
  Hanwha Life) issue Korean-language forms with mixed Hangul/Hanja and
  occasional vertical layout. Add a parallel `data/samples/ko/` and a
  bilingual schema variant.
- **Active-learning labeling loop.** Failures in `results/eval_*.md` →
  human corrections → injected as v4 few-shot examples or as MIPRO seed
  demonstrations. Each iteration's eval set gets harder over time.
- **Streaming + batching for throughput.** Production extraction services
  hit thousands of forms/day. Adding async batching to the extractor
  exposes a different axis (throughput vs latency) that the current eval
  ignores.

### References
- Park et al., "OCR-Free Document Understanding for Korean Insurance Forms" — *(no canonical paper; this is closer to industry know-how. Upstage's own technical posts and the Donut paper are the closest references.)*
- Snorkel-style weak supervision for labeling: Ratner et al., "Snorkel: Rapid Training Data Creation with Weak Supervision" (VLDB 2018).
- Active learning for NLP labeling: Settles, "Active Learning Literature Survey" (UW-Madison TR, 2010); modern applications in Prodigy / Argilla.

---

## Suggested order of attack

| Order | Item | Estimated effort | Expected lift |
| --- | --- | --- | --- |
| 1 | **Constrained decoding (Outlines)** | 0.5 day | Schema validity → 100% by construction; isolates F1 as the only metric that matters |
| 2 | **Layout-aware parser (Marker or Qwen2.5-VL)** | 1–2 days | F1 +5 to +20 pp on real PDFs (table / checkbox info recovered) |
| 3 | **DSPy MIPRO → v4** | 1–2 days | F1 +2 to +8 pp; major *narrative* lift in interviews |
| 4 | **Self-Refine pass** | 0.5 day | Hallucination rate ↓ ~30%, latency 2x |
| 5 | **Korean / domain-specific routing** | 2–3 days | Specifically valuable for Upstage's customer base |

Items 1 and 2 are independent and can run in parallel.
