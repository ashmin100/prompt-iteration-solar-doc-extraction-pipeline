# Sample documents

The eval harness loads `(samples/<id>.{txt,pdf}, ground_truth/<id>.json)`
pairs and runs every prompt version against them. Datasets here are split into
two tiers:

## Tier 1 — Real public-domain PDFs (primary eval set)

Hand-collected and hand-labeled by the project author. These produce the
**headline numbers** in `results/eval_v1_v2_v3.md`.

Aim for **4–5 documents** drawn from the sources below. Drop the PDF into
`samples/` and write a matching `ground_truth/<same_stem>.json`.

| Source | Form | Why useful |
| --- | --- | --- |
| `cms.gov/medicare/cms-forms/cms-forms` | **CMS-1500** health insurance claim | US standard, dense layout, codified fields |
| `irs.gov/forms-pubs/about-form-1095-a` | **1095-A** marketplace coverage | tax-form layout, dates per month |
| Search `acord 25 sample filetype:pdf` | **ACORD 25** certificate of insurance | industry-standard layout |
| `insurance.ca.gov` consumer pages | **CA DOI sample policy declarations** | real consumer-facing language |
| `naic.org` model forms | **NAIC sample applications** | regulatory-grade samples |

### Faster ground-truthing workflow (model-assisted labeling)

```bash
# 1. Run the strongest prompt on the PDF
python -m src.cli extract --pdf data/samples/cms_1500_sample.pdf \
    --version v3 --out data/ground_truth/cms_1500_sample.json

# 2. Open the JSON in an editor, fix the ~3-5 fields the model got wrong, save.
```

This is the same workflow real Document AI annotation pipelines use, so it
also doubles as portfolio signal.

## Tier 2 — Synthetic samples (dev set, already in repo)

Hand-written `.txt` files used to sanity-check the eval harness itself
(do the metrics distinguish v1 from v2? does fuzzy matching behave?). These
are not the headline numbers — they're scaffolding.

| ID | Stress-tests |
| --- | --- |
| `synthetic_auto_decl` | basic happy path, multiple coverages, extra insured |
| `synthetic_home_decl` | named coverages (A–F), included-vs-paid premiums, mortgagee in raw_notes |
| `synthetic_life_app` | many beneficiaries with shares, contingent beneficiary, multi-page |
| `synthetic_auto_claim` | claim block + loss-location address |
| `synthetic_health_card` | mostly null fields, copay table → raw_notes |
| `synthetic_partial_blank` | most fields null, model must NOT hallucinate |
| `synthetic_commercial_multi` | corporate name as policy_holder, multiple additional insureds |

When the eval runs, the report separates Tier 1 and Tier 2 totals so the
synthetic numbers don't inflate the headline.

## Do NOT add

- Real customer PII.
- Internal-only insurer documents you don't have permission to share.
- Anything copyrighted by a carrier without permission.
