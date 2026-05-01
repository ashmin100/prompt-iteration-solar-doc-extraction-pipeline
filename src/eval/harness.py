"""End-to-end eval harness: load dataset → run prompt versions → aggregate."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from src.extractor import Extractor
from src.llm_client import LLMClient
from src.parser import pdf_to_text
from src.eval.metrics import (
    AggregateMetrics,
    DocumentMetrics,
    aggregate,
    score_document,
)


# --------------------------------------------------------------------------- #
@dataclass
class DatasetItem:
    document_id: str
    text: str
    ground_truth: dict
    tier: str  # "real" or "synthetic"


def discover_dataset(
    samples_dir: Path = Path("data/samples"),
    gt_dir: Path = Path("data/ground_truth"),
) -> list[DatasetItem]:
    """Find every (sample, ground_truth) pair on disk.

    Tier:
      - "synthetic" if sample basename starts with `synthetic_`
      - "real"      otherwise (real public-domain PDFs)
    """
    items: list[DatasetItem] = []
    for sample_path in sorted(samples_dir.iterdir()):
        if sample_path.is_dir() or sample_path.name.startswith(("_", ".")):
            continue
        if sample_path.suffix.lower() not in {".txt", ".pdf"}:
            continue
        stem = sample_path.stem
        gt_path = gt_dir / f"{stem}.json"
        if not gt_path.exists() or stem.startswith("_"):
            continue
        text = (
            pdf_to_text(sample_path)
            if sample_path.suffix.lower() == ".pdf"
            else sample_path.read_text(encoding="utf-8")
        )
        gt = json.loads(gt_path.read_text(encoding="utf-8"))
        tier = "synthetic" if stem.startswith("synthetic_") else "real"
        items.append(DatasetItem(document_id=stem, text=text, ground_truth=gt, tier=tier))
    return items


# --------------------------------------------------------------------------- #
@dataclass
class HarnessRun:
    prompt_version: str
    backend: str
    model: str
    overall: AggregateMetrics
    by_tier: dict[str, AggregateMetrics] = field(default_factory=dict)


@dataclass
class HarnessReport:
    runs: list[HarnessRun]
    dataset_size: int
    tier_counts: dict[str, int]


# --------------------------------------------------------------------------- #
def run_evaluation(
    versions: Iterable[str] = ("v1", "v2", "v3"),
    llm: Optional[LLMClient] = None,
    samples_dir: Path = Path("data/samples"),
    gt_dir: Path = Path("data/ground_truth"),
) -> HarnessReport:
    dataset = discover_dataset(samples_dir, gt_dir)
    if not dataset:
        raise RuntimeError(
            f"No (sample, ground_truth) pairs found under {samples_dir} / {gt_dir}"
        )

    tier_counts: dict[str, int] = {}
    for item in dataset:
        tier_counts[item.tier] = tier_counts.get(item.tier, 0) + 1

    llm_client = llm or LLMClient()
    runs: list[HarnessRun] = []

    for version in versions:
        extractor = Extractor(llm=llm_client, prompt_version=version)
        per_doc: list[DocumentMetrics] = []

        for item in dataset:
            res = extractor.extract_from_text(item.text, document_id=item.document_id)
            pred = (
                res.validated.model_dump(mode="json")
                if res.validated is not None
                else res.parsed_json
            )
            per_doc.append(
                score_document(
                    document_id=item.document_id,
                    prompt_version=version,
                    gt=item.ground_truth,
                    pr=pred,
                    schema_valid=res.schema_valid,
                    latency_ms=res.llm_response.latency_ms,
                    json_parse_error=res.json_parse_error,
                    validation_errors=res.validation_errors,
                )
            )

        # Stash tier per doc for split reporting
        tier_lookup = {item.document_id: item.tier for item in dataset}
        overall = aggregate(per_doc)
        by_tier: dict[str, AggregateMetrics] = {}
        for tier in tier_counts:
            tier_docs = [d for d in per_doc if tier_lookup[d.document_id] == tier]
            if tier_docs:
                by_tier[tier] = aggregate(tier_docs)

        runs.append(
            HarnessRun(
                prompt_version=version,
                backend=llm_client.backend,
                model=llm_client.model,
                overall=overall,
                by_tier=by_tier,
            )
        )

    return HarnessReport(
        runs=runs,
        dataset_size=len(dataset),
        tier_counts=tier_counts,
    )
