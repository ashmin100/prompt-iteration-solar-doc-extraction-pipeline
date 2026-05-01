# Sample documents

## What goes here

- `samples/` — insurance form PDFs (real public forms + synthetic).
- `ground_truth/` — one JSON per sample, named `<sample_stem>.json`,
  manually written by you (the project author) and treated as the
  reference for the eval harness.

## How to gather samples (legal, public-domain only)

The eval harness needs ~5–10 documents to be useful.

1. **ACORD-style declaration pages**
   - Many state insurance departments publish blank or sample ACORD forms
     (e.g., California DOI consumer pages) — search:
     `"acord 25" filetype:pdf site:.gov`
   - Save 1–2 to `samples/`.

2. **IRS/Medicare insurance-related forms**
   - `1095-A`, `1095-B`, `1095-C` health-insurance forms are public:
     https://www.irs.gov/forms-instructions
   - These are tax forms but contain insurance policy info — good edge case.

3. **Synthetic samples** (already provided)
   - `samples/synthetic_auto_decl.txt` — easy starter, run with
     `--pdf` not applicable; pass via the `--text` flow once that exists,
     or wrap in a one-page PDF using any PDF generator.

4. **Do NOT add**
   - Real customer documents (PII).
   - Anything copyrighted by an insurance carrier without permission.

## Ground-truth template

Each `ground_truth/<id>.json` should be the InsuranceForm JSON you would
*want* the model to produce. See `data/ground_truth/_template.json`.
