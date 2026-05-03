# Eval report — ollama / `qwen3:14b`

_Generated 2026-05-03T19:52:01_

**Dataset:** 19 documents (blank: 4, synthetic: 15).
**Parser mode:** `text`.

## Overall

| Version | N | Schema valid | Field acc | F1 | Hallucination | Omission | Latency p50 | Latency p95 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v1 | 19 | 21.1% | 40.2% | 0.488 | 29.2% | 54.2% | 37428 ms | 77047 ms |
| v2 | 19 | 84.2% | 58.1% | 0.692 | 6.8% | 36.5% | 75048 ms | 104204 ms |
| v3 | 19 | 57.9% | 53.2% | 0.667 | 2.8% | 42.2% | 74051 ms | 125352 ms |

## Blank tier

| Version | N | Schema valid | Field acc | F1 | Hallucination | Omission | Latency p50 | Latency p95 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v1 | 4 | 50.0% | 33.3% | 0.471 | 0.0% | 58.3% | 36016 ms | 51474 ms |
| v2 | 4 | 100.0% | 41.7% | 0.500 | 0.0% | 33.3% | 53281 ms | 65740 ms |
| v3 | 4 | 25.0% | 25.0% | 0.316 | 0.0% | 41.7% | 61102 ms | 79492 ms |

## Synthetic tier

| Version | N | Schema valid | Field acc | F1 | Hallucination | Omission | Latency p50 | Latency p95 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v1 | 15 | 13.3% | 40.5% | 0.489 | 30.0% | 54.0% | 38097 ms | 77047 ms |
| v2 | 15 | 80.0% | 58.8% | 0.700 | 7.1% | 36.7% | 77716 ms | 104204 ms |
| v3 | 15 | 66.7% | 54.3% | 0.681 | 2.9% | 42.2% | 75924 ms | 125352 ms |

## Per-document failures

Documents where any version failed schema validation, parse, or had wrong fields.

| Document | Version | Schema | JSON parse | Wrong | Omitted | Hallucinated |
| --- | --- | --- | --- | --- | --- | --- |
| `blank_acord_25` | v1 | FAIL | ok | 1 | 3 | 0 |
| `blank_cms_1500` | v1 | ok | ok | 0 | 1 | 0 |
| `blank_irs_1095a` | v1 | ok | ok | 0 | 1 | 0 |
| `blank_naic_life` | v1 | FAIL | ok | 0 | 2 | 0 |
| `synthetic_auto_claim` | v1 | ok | ok | 1 | 1 | 1 |
| `synthetic_auto_decl` | v1 | FAIL | ok | 5 | 13 | 6 |
| `synthetic_auto_decl_multidriver_fd0t` | v1 | FAIL | ok | 0 | 23 | 5 |
| `synthetic_claim_theft_kw5n` | v1 | ok | ok | 1 | 1 | 1 |
| `synthetic_commercial_multi` | v1 | FAIL | ok | 1 | 26 | 8 |
| `synthetic_health_card` | v1 | FAIL | ok | 2 | 1 | 5 |
| `synthetic_health_hdhp_dd4v` | v1 | FAIL | ok | 2 | 1 | 0 |
| `synthetic_home_condo_sahx` | v1 | FAIL | ok | 1 | 15 | 11 |
| `synthetic_home_decl` | v1 | FAIL | ok | 0 | 25 | 6 |
| `synthetic_life_app` | v1 | FAIL | ok | 1 | 8 | 1 |
| `synthetic_life_whole_qk51` | v1 | FAIL | no JSON object found in response | 0 | 19 | 0 |
| `synthetic_partial_app_yzyc` | v1 | FAIL | ok | 0 | 0 | 0 |
| `synthetic_partial_blank` | v1 | FAIL | ok | 0 | 0 | 0 |
| `synthetic_renters_q4fm` | v1 | FAIL | ok | 1 | 14 | 10 |
| `synthetic_umbrella_bikc` | v1 | FAIL | ok | 1 | 9 | 3 |
| `blank_acord_25` | v2 | ok | ok | 2 | 0 | 0 |
| `blank_cms_1500` | v2 | ok | ok | 0 | 1 | 0 |
| `blank_irs_1095a` | v2 | ok | ok | 1 | 1 | 0 |
| `blank_naic_life` | v2 | ok | ok | 0 | 2 | 0 |
| `synthetic_auto_claim` | v2 | ok | ok | 1 | 0 | 0 |
| `synthetic_auto_decl` | v2 | ok | ok | 3 | 5 | 3 |
| `synthetic_auto_decl_multidriver_fd0t` | v2 | ok | ok | 0 | 15 | 0 |
| `synthetic_claim_theft_kw5n` | v2 | ok | ok | 1 | 0 | 1 |
| `synthetic_commercial_multi` | v2 | FAIL | ok | 3 | 12 | 2 |
| `synthetic_health_card` | v2 | ok | ok | 1 | 1 | 1 |
| `synthetic_health_hdhp_dd4v` | v2 | ok | ok | 1 | 1 | 3 |
| `synthetic_home_condo_sahx` | v2 | ok | ok | 0 | 1 | 0 |
| `synthetic_home_decl` | v2 | FAIL | no JSON object found in response | 0 | 35 | 0 |
| `synthetic_life_app` | v2 | ok | ok | 3 | 5 | 0 |
| `synthetic_life_whole_qk51` | v2 | ok | ok | 0 | 4 | 4 |
| `synthetic_renters_q4fm` | v2 | FAIL | no JSON object found in response | 0 | 24 | 0 |
| `synthetic_umbrella_bikc` | v2 | ok | ok | 0 | 3 | 0 |
| `blank_acord_25` | v3 | FAIL | ok | 2 | 0 | 0 |
| `blank_cms_1500` | v3 | FAIL | ok | 1 | 1 | 0 |
| `blank_irs_1095a` | v3 | ok | ok | 1 | 1 | 0 |
| `blank_naic_life` | v3 | FAIL | ok | 0 | 3 | 0 |
| `synthetic_auto_claim` | v3 | ok | ok | 0 | 3 | 0 |
| `synthetic_auto_decl` | v3 | ok | ok | 0 | 25 | 1 |
| `synthetic_claim_theft_kw5n` | v3 | ok | ok | 1 | 0 | 1 |
| `synthetic_commercial_multi` | v3 | FAIL | no JSON object found in response | 0 | 35 | 0 |
| `synthetic_health_card` | v3 | ok | ok | 1 | 0 | 0 |
| `synthetic_health_hdhp_dd4v` | v3 | FAIL | ok | 1 | 4 | 0 |
| `synthetic_home_decl` | v3 | FAIL | ok | 2 | 21 | 0 |
| `synthetic_life_app` | v3 | ok | ok | 3 | 0 | 0 |
| `synthetic_life_whole_qk51` | v3 | FAIL | ok | 1 | 6 | 3 |
| `synthetic_renters_q4fm` | v3 | ok | ok | 1 | 11 | 0 |
| `synthetic_umbrella_bikc` | v3 | FAIL | no JSON object found in response | 0 | 17 | 0 |

## Notes

- Schema validity = fraction of predictions that parse + Pydantic-validate.
- Field accuracy / F1 ignore `raw_notes` (free-form essay).
- Money values normalized to `Decimal`; dates normalized to ISO 8601 before comparison.
- Strings (names, addresses) compared with fuzzy ratio ≥ 0.85.
- List fields (coverages, beneficiaries) matched greedily by their key field.
