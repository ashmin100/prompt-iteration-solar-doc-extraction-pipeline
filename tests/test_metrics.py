"""Tests for evaluation metrics."""

import pytest

from src.eval.metrics import (
    compare_scalar,
    score_document,
    aggregate,
    _norm_date,
    _norm_money,
    _norm_phone,
    FieldTally,
)


# --------------------------------------------------------------------------- #
#  Normalizers                                                                #
# --------------------------------------------------------------------------- #
class TestNormDate:
    def test_iso_passthrough(self):
        assert _norm_date("2025-01-15") == "2025-01-15"

    def test_us_format(self):
        assert _norm_date("01/15/2025") == "2025-01-15"

    def test_none(self):
        assert _norm_date(None) is None

    def test_unknown_format_returned_as_is(self):
        assert _norm_date("Jan 15 2025") == "Jan 15 2025"


class TestNormMoney:
    def test_decimal_string(self):
        from decimal import Decimal
        assert _norm_money("1,250.00") == Decimal("1250.00")

    def test_dollar_sign(self):
        from decimal import Decimal
        assert _norm_money("$500") == Decimal("500")

    def test_integer(self):
        from decimal import Decimal
        assert _norm_money(500) == Decimal("500")

    def test_none(self):
        assert _norm_money(None) is None

    def test_empty_string(self):
        assert _norm_money("") is None


class TestNormPhone:
    def test_formatted(self):
        assert _norm_phone("(555) 867-5309") == "5558675309"

    def test_plain(self):
        assert _norm_phone("5558675309") == "5558675309"

    def test_with_country_code(self):
        assert _norm_phone("+1-555-867-5309") == "5558675309"

    def test_none(self):
        assert _norm_phone(None) is None


# --------------------------------------------------------------------------- #
#  compare_scalar                                                             #
# --------------------------------------------------------------------------- #
class TestCompareScalar:
    def test_categorical_case_insensitive(self):
        assert compare_scalar("categorical", "AUTO", "auto")
        assert not compare_scalar("categorical", "auto", "home")

    def test_id_strips_whitespace(self):
        assert compare_scalar("id", "AUTO-2025-00123", "AUTO-2025-00123")
        assert compare_scalar("id", "AUTO 2025 00123", "AUTO2025 00123")
        assert not compare_scalar("id", "AUTO-2025-00123", "AUTO-2025-00124")

    def test_date_iso(self):
        assert compare_scalar("date", "2025-01-01", "2025-01-01")
        assert not compare_scalar("date", "2025-01-01", "2025-01-02")

    def test_date_cross_format(self):
        assert compare_scalar("date", "2025-01-15", "01/15/2025")

    def test_money_equal(self):
        assert compare_scalar("money", "1,000.00", "1000")
        assert compare_scalar("money", "$500", "500.00")
        assert not compare_scalar("money", "500", "501")

    def test_fuzzy_similar(self):
        assert compare_scalar("fuzzy", "Jane Doe", "Jane Doe")
        assert compare_scalar("fuzzy", "Jane Doe", "jane doe")  # case-insensitive
        assert not compare_scalar("fuzzy", "Jane Doe", "John Smith")

    def test_phone(self):
        assert compare_scalar("phone", "(555) 867-5309", "5558675309")
        assert not compare_scalar("phone", "5558675309", "5558675310")

    def test_email_case_insensitive(self):
        assert compare_scalar("email", "Jane@Example.com", "jane@example.com")
        assert not compare_scalar("email", "a@b.com", "c@d.com")

    def test_unknown_comparator_raises(self):
        with pytest.raises(ValueError):
            compare_scalar("nonexistent", "a", "b")


# --------------------------------------------------------------------------- #
#  score_document / aggregate                                                 #
# --------------------------------------------------------------------------- #
GT_PERFECT = {
    "form_type": "declaration_page",
    "policy_holder": {
        "full_name": "Jane Doe",
        "date_of_birth": "1985-04-12",
        "phone": "5558675309",
        "email": "jane@example.com",
        "address": {
            "street": "123 Main St",
            "city": "Springfield",
            "state": "IL",
            "zip_code": "62701",
        },
    },
    "policy": {
        "policy_number": "AUTO-2025-00123",
        "policy_type": "auto",
        "insurer_name": "Acme Insurance",
        "effective_date": "2025-01-01",
        "expiration_date": "2026-01-01",
        "total_premium": "1450.00",
        "coverages": [
            {"coverage_type": "bodily_injury_liability", "limit": "100000", "deductible": "0", "premium": "650"},
            {"coverage_type": "collision", "limit": "50000", "deductible": "500", "premium": "400"},
        ],
    },
}


class TestScoreDocument:
    def test_perfect_prediction_high_f1(self):
        doc = score_document("doc1", "v1", GT_PERFECT, GT_PERFECT, True, 100.0)
        assert doc.tally.correct > 0
        assert doc.tally.wrong == 0
        assert doc.tally.hallucinated == 0
        assert doc.tally.omitted == 0
        assert doc.f1 == pytest.approx(1.0)

    def test_empty_prediction_all_omitted(self):
        doc = score_document("doc1", "v1", GT_PERFECT, {}, False, 100.0)
        assert doc.tally.omitted > 0
        assert doc.tally.correct == 0
        assert doc.f1 == 0.0

    def test_none_prediction_treated_as_empty(self):
        doc = score_document("doc1", "v1", GT_PERFECT, None, False, 100.0)
        assert doc.tally.omitted > 0

    def test_hallucination_counted(self):
        # GT has no claim, prediction invents one
        pr = dict(GT_PERFECT)
        pr["claim"] = {"claim_number": "CLM-999", "date_of_loss": "2025-06-01", "estimated_amount": "5000"}
        doc = score_document("doc1", "v1", GT_PERFECT, pr, True, 100.0)
        assert doc.tally.hallucinated > 0

    def test_wrong_field_counted(self):
        import copy
        pr = copy.deepcopy(GT_PERFECT)
        pr["policy"]["policy_number"] = "WRONG-NUMBER"
        doc = score_document("doc1", "v1", GT_PERFECT, pr, True, 100.0)
        assert doc.tally.wrong >= 1


class TestAggregate:
    def test_single_doc(self):
        doc = score_document("doc1", "v2", GT_PERFECT, GT_PERFECT, True, 150.0)
        agg = aggregate([doc])
        assert agg.schema_validity_rate == 1.0
        assert agg.f1 == pytest.approx(1.0)
        assert agg.n_documents == 1

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            aggregate([])

    def test_latency_percentiles(self):
        docs = [
            score_document(f"doc{i}", "v1", GT_PERFECT, GT_PERFECT, True, float(i * 100))
            for i in range(1, 11)
        ]
        agg = aggregate(docs)
        assert agg.latency_p50_ms > 0
        assert agg.latency_p95_ms >= agg.latency_p50_ms
