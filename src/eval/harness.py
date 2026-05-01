"""End-to-end eval harness: load dataset → run prompt versions → aggregate."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from src.extractor import Extractor
from src.llm_client import LLMClient
from src.parser import parse_document
from src.eval.metrics import (
    AggregateMetrics,
    DocumentMetrics,
    aggregate,
    score_document,
)


# --------------------------------------------------------------------------- #
TIER_PREFIXES: dict[str, str] = {
    "synthetic_": "synthetic",
    "blank_":     "blank",
    "filled_":    "filled",
}
DEFAULT_TIER = "uncategorized"


def _classify_tier(stem: str) -> str:
    for prefix, tier in TIER_PREFIXES.items():
        if stem.startswith(prefix):
            return tier
    return DEFAULT_TIER


# --------------------------------------------------------------------------- #
@dataclass
class DatasetItem:
    document_id: str
    text: str
    ground_truth: dict
    tier: str  # "synthetic" | "blank" | "filled" | "uncategorized"


def discover_dataset(
    samples_dir: Path = Path("data/samples"),
    gt_dir: Path = Path("data/ground_truth"),
    parser_mode: str = "text",
) -> list[DatasetItem]:
    """Find every (sample, ground_truth) pair on disk, deduped by stem.

    Tiers (prefix-based, see TIER_PREFIXES):
      - synthetic_*   → "synthetic"  (programmatically generated, primary accuracy tier)
      - blank_*       → "blank"      (real public-domain blank forms; hallucination-resistance test)
      - filled_*      → "filled"     (filled real-layout forms; deferred — see future_work.md)
      - other         → "uncategorized"

    Stem dedup: if both `<stem>.txt` and `<stem>.pdf` exist, pick one based
    on `parser_mode`:
      - text mode    → prefer .pdf (realistic input through pdfplumber);
                       fall back to .txt only if no PDF exists.
      - vlm-* modes  → require .pdf; skip stems with only .txt.

    The .txt files are kept in the repo as human-readable references for
    each synthetic sample; the .pdf is what the harness actually evaluates.
    """
    is_vlm = parser_mode.startswith("vlm-")

    # Group by stem
    stem_to_paths: dict[str, list[Path]] = {}
    for sample_path in samples_dir.iterdir():
        if sample_path.is_dir() or sample_path.name.startswith(("_", ".")):
            continue
        if sample_path.suffix.lower() not in {".txt", ".pdf"}:
            continue
        stem = sample_path.stem
        if stem.startswith("_"):
            continue
        if not (gt_dir / f"{stem}.json").exists():
            continue
        stem_to_paths.setdefault(stem, []).append(sample_path)

    items: list[DatasetItem] = []
    for stem in sorted(stem_to_paths):
        paths = stem_to_paths[stem]
        pdf = next((p for p in paths if p.suffix.lower() == ".pdf"), None)
        txt = next((p for p in paths if p.suffix.lower() == ".txt"), None)

        if is_vlm:
            chosen = pdf  # VLM strictly needs an image
        else:
            chosen = pdf or txt  # text mode: PDF first (realistic), else .txt

        if chosen is None:
            continue  # nothing usable for this mode

        parsed = parse_document(chosen, mode=parser_mode)
        gt = json.loads((gt_dir / f"{stem}.json").read_text(encoding="utf-8"))
        items.append(
            DatasetItem(
                document_id=stem,
                text=parsed.text,
                ground_truth=gt,
                tier=_classify_tier(stem),
            )
        )
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
    parser_mode: str = "text"


# --------------------------------------------------------------------------- #
def run_evaluation(
    versions: Iterable[str] = ("v1", "v2", "v3"),
    llm: Optional[LLMClient] = None,
    samples_dir: Path = Path("data/samples"),
    gt_dir: Path = Path("data/ground_truth"),
    parser_mode: str = "text",
) -> HarnessReport:
    dataset = discover_dataset(samples_dir, gt_dir, parser_mode=parser_mode)
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
        parser_mode=parser_mode,
    )
