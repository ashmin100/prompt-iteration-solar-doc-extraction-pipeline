"""Evaluation metrics for InsuranceForm extraction.

Per-document, we compare a predicted dict against a ground-truth dict and
classify each leaf field as:
    correct      — prediction matches GT
    omitted      — GT has a value but prediction is null/missing
    hallucinated — prediction has a value but GT is null
    wrong        — both populated but values differ

Across documents we aggregate to:
    schema_validity_rate, field_accuracy, recall, precision, f1,
    hallucination_rate, omission_rate, latency p50/p95.

Comparison rules per field type:
    - Identifier / categorical / enum   → case-insensitive exact match
    - Date                              → parse to YYYY-MM-DD, exact
    - Money (Decimal-like)              → numeric equality after normalization
    - Free string (name, address line)  → fuzzy ratio >= 0.85
    - List of objects (coverages, etc.) → greedy match by a "key" field, then per-field compare
    - raw_notes                         → ignored from metric (free-form essay)
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from typing import Any, Iterable, Optional


# --------------------------------------------------------------------------- #
#  Field paths & their comparator types                                       #
# --------------------------------------------------------------------------- #
SCALAR_FIELDS: dict[str, str] = {
    # path -> comparator name
    "form_type": "categorical",
    "policy_holder.full_name": "fuzzy",
    "policy_holder.date_of_birth": "date",
    "policy_holder.phone": "phone",
    "policy_holder.email": "email",
    "policy_holder.address.street": "fuzzy",
    "policy_holder.address.city": "fuzzy",
    "policy_holder.address.state": "categorical",
    "policy_holder.address.zip_code": "id",
    "policy_holder.address.country": "categorical",
    "policy.policy_number": "id",
    "policy.policy_type": "categorical",
    "policy.insurer_name": "fuzzy",
    "policy.effective_date": "date",
    "policy.expiration_date": "date",
    "policy.total_premium": "money",
    "claim.claim_number": "id",
    "claim.date_of_loss": "date",
    "claim.loss_description": "fuzzy",
    "claim.estimated_amount": "money",
}

LIST_FIELDS: dict[str, dict] = {
    "policy.coverages": {
        "key": "coverage_type",
        "scalar_paths": {
            "coverage_type": "categorical",
            "limit": "money",
            "deductible": "money",
            "premium": "money",
        },
    },
    "additional_insureds": {
        "key": "full_name",
        "scalar_paths": {
            "full_name": "fuzzy",
            "date_of_birth": "date",
            "email": "email",
        },
    },
    "beneficiaries": {
        "key": "full_name",
        "scalar_paths": {
            "full_name": "fuzzy",
            "date_of_birth": "date",
            "email": "email",
        },
    },
}

IGNORED_PATHS = {"raw_notes"}  # explicitly free-form, not measured


# --------------------------------------------------------------------------- #
#  Path / value helpers                                                       #
# --------------------------------------------------------------------------- #
def _get_path(d: Any, path: str) -> Any:
    """Walk a dotted path through nested dicts; return None on any miss."""
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
        if cur is None:
            return None
    return cur


def _is_empty(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and v.strip() == "":
        return True
    if isinstance(v, (list, dict)) and len(v) == 0:
        return True
    return False


# --------------------------------------------------------------------------- #
#  Comparators                                                                #
# --------------------------------------------------------------------------- #
def _norm_money(v: Any) -> Optional[Decimal]:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return v
    if isinstance(v, (int, float)):
        return Decimal(str(v))
    if isinstance(v, str):
        cleaned = re.sub(r"[^\d.\-]", "", v)
        if not cleaned:
            return None
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None
    return None


def _norm_date(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    # accept YYYY-MM-DD directly
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s
    # MM/DD/YYYY → YYYY-MM-DD
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        mm, dd, yyyy = m.groups()
        return f"{int(yyyy):04d}-{int(mm):02d}-{int(dd):02d}"
    return s  # fall back: compare as-is


def _norm_phone(v: Any) -> Optional[str]:
    if v is None:
        return None
    digits = re.sub(r"\D", "", str(v))
    return digits[-10:] if len(digits) >= 10 else digits


def _fuzzy_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def compare_scalar(comparator: str, gt: Any, pr: Any) -> bool:
    """Return True if predicted value matches GT under the comparator's rule."""
    if comparator == "categorical":
        return str(gt).lower().strip() == str(pr).lower().strip()
    if comparator == "id":
        return re.sub(r"\s+", "", str(gt)).lower() == re.sub(r"\s+", "", str(pr)).lower()
    if comparator == "date":
        return _norm_date(gt) == _norm_date(pr)
    if comparator == "money":
        ng, np_ = _norm_money(gt), _norm_money(pr)
        return ng is not None and np_ is not None and ng == np_
    if comparator == "fuzzy":
        return _fuzzy_ratio(str(gt), str(pr)) >= 0.85
    if comparator == "phone":
        return _norm_phone(gt) == _norm_phone(pr)
    if comparator == "email":
        return str(gt).lower().strip() == str(pr).lower().strip()
    raise ValueError(f"unknown comparator: {comparator}")


# --------------------------------------------------------------------------- #
#  Per-document tally                                                         #
# --------------------------------------------------------------------------- #
@dataclass
class FieldTally:
    correct: int = 0
    wrong: int = 0
    omitted: int = 0      # GT non-empty, prediction empty
    hallucinated: int = 0  # GT empty, prediction non-empty
    both_empty: int = 0    # both empty — neither side gets credit or blame

    def add(self, other: "FieldTally") -> None:
        self.correct += other.correct
        self.wrong += other.wrong
        self.omitted += other.omitted
        self.hallucinated += other.hallucinated
        self.both_empty += other.both_empty


def _tally_scalar(comparator: str, gt: Any, pr: Any) -> FieldTally:
    t = FieldTally()
    g_empty, p_empty = _is_empty(gt), _is_empty(pr)
    if g_empty and p_empty:
        t.both_empty = 1
    elif g_empty and not p_empty:
        t.hallucinated = 1
    elif not g_empty and p_empty:
        t.omitted = 1
    else:
        if compare_scalar(comparator, gt, pr):
            t.correct = 1
        else:
            t.wrong = 1
    return t


def _tally_list(spec: dict, gt_list: Optional[list], pr_list: Optional[list]) -> FieldTally:
    """
    Greedy match by spec['key']. For each matched pair we tally the per-item
    scalar fields. Unmatched GT items contribute 1 omitted per scalar field;
    unmatched PR items contribute 1 hallucinated per scalar field.
    """
    t = FieldTally()
    gt_list = gt_list or []
    pr_list = pr_list or []
    key = spec["key"]
    scalars: dict = spec["scalar_paths"]

    used_pr = set()
    for g in gt_list:
        gk = (g or {}).get(key)
        match_idx = None
        if gk is not None:
            for i, p in enumerate(pr_list):
                if i in used_pr:
                    continue
                if compare_scalar("fuzzy" if isinstance(gk, str) else "categorical",
                                   gk, (p or {}).get(key)):
                    match_idx = i
                    break
        if match_idx is not None:
            used_pr.add(match_idx)
            p = pr_list[match_idx] or {}
            for sub_path, comparator in scalars.items():
                t.add(_tally_scalar(comparator, g.get(sub_path), p.get(sub_path)))
        else:
            # whole GT item missing → every scalar omitted
            for sub_path in scalars:
                if not _is_empty(g.get(sub_path)):
                    t.omitted += 1
                else:
                    t.both_empty += 1

    # leftover PR items → hallucinated
    for i, p in enumerate(pr_list):
        if i in used_pr:
            continue
        for sub_path in scalars:
            if not _is_empty((p or {}).get(sub_path)):
                t.hallucinated += 1
            else:
                t.both_empty += 1

    return t


# --------------------------------------------------------------------------- #
#  Per-document & aggregate                                                   #
# --------------------------------------------------------------------------- #
@dataclass
class DocumentMetrics:
    document_id: str
    prompt_version: str
    schema_valid: bool
    tally: FieldTally
    latency_ms: float
    json_parse_error: Optional[str] = None
    validation_errors: list[str] = field(default_factory=list)

    @property
    def field_accuracy(self) -> float:
        denom = self.tally.correct + self.tally.wrong + self.tally.omitted
        return self.tally.correct / denom if denom else 0.0

    @property
    def f1(self) -> float:
        tp = self.tally.correct
        fp = self.tally.wrong + self.tally.hallucinated
        fn = self.tally.wrong + self.tally.omitted
        if tp == 0:
            return 0.0
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        return 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0


def score_document(
    document_id: str,
    prompt_version: str,
    gt: dict,
    pr: Optional[dict],
    schema_valid: bool,
    latency_ms: float,
    json_parse_error: Optional[str] = None,
    validation_errors: Optional[list[str]] = None,
) -> DocumentMetrics:
    """Compare a predicted JSON to ground truth and produce per-document metrics."""
    tally = FieldTally()
    if pr is None:
        pr = {}

    for path, comparator in SCALAR_FIELDS.items():
        if path in IGNORED_PATHS:
            continue
        tally.add(_tally_scalar(comparator, _get_path(gt, path), _get_path(pr, path)))

    for path, spec in LIST_FIELDS.items():
        tally.add(_tally_list(spec, _get_path(gt, path), _get_path(pr, path)))

    return DocumentMetrics(
        document_id=document_id,
        prompt_version=prompt_version,
        schema_valid=schema_valid,
        tally=tally,
        latency_ms=latency_ms,
        json_parse_error=json_parse_error,
        validation_errors=validation_errors or [],
    )


# --------------------------------------------------------------------------- #
@dataclass
class AggregateMetrics:
    prompt_version: str
    n_documents: int
    schema_validity_rate: float
    field_accuracy: float
    f1: float
    hallucination_rate: float
    omission_rate: float
    latency_p50_ms: float
    latency_p95_ms: float
    per_doc: list[DocumentMetrics] = field(default_factory=list)


def aggregate(per_doc: Iterable[DocumentMetrics]) -> AggregateMetrics:
    docs = list(per_doc)
    if not docs:
        raise ValueError("no documents to aggregate")
    version = docs[0].prompt_version

    total = FieldTally()
    for d in docs:
        total.add(d.tally)

    denom_acc = total.correct + total.wrong + total.omitted
    field_acc = total.correct / denom_acc if denom_acc else 0.0

    tp = total.correct
    fp = total.wrong + total.hallucinated
    fn = total.wrong + total.omitted
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    pred_filled = total.correct + total.wrong + total.hallucinated
    halluc_rate = total.hallucinated / pred_filled if pred_filled else 0.0
    gt_filled = total.correct + total.wrong + total.omitted
    omit_rate = total.omitted / gt_filled if gt_filled else 0.0

    latencies = sorted(d.latency_ms for d in docs)
    p50 = statistics.median(latencies)
    p95 = latencies[max(0, int(round(0.95 * len(latencies))) - 1)]

    return AggregateMetrics(
        prompt_version=version,
        n_documents=len(docs),
        schema_validity_rate=sum(1 for d in docs if d.schema_valid) / len(docs),
        field_accuracy=field_acc,
        f1=f1,
        hallucination_rate=halluc_rate,
        omission_rate=omit_rate,
        latency_p50_ms=p50,
        latency_p95_ms=p95,
        per_doc=docs,
    )
