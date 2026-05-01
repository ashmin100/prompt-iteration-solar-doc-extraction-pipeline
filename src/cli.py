"""Tiny CLI:

    python -m src.cli extract --pdf path --version v2
    python -m src.cli evaluate --versions v1,v2,v3 --out results/eval.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.extractor import Extractor
from src.eval.harness import run_evaluation
from src.eval.report import write_report


def main(argv: list[str] | None = None) -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(prog="solar-doc-extraction-pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # ---- extract --------------------------------------------------------
    extract = sub.add_parser("extract", help="Extract structured JSON from one PDF")
    extract.add_argument("--pdf", required=True, type=Path)
    extract.add_argument("--version", default="v2", choices=["v1", "v2", "v3"])
    extract.add_argument("--out", type=Path, default=None)

    # ---- evaluate -------------------------------------------------------
    evaluate = sub.add_parser(
        "evaluate",
        help="Run all prompt versions against the dataset and write a markdown report",
    )
    evaluate.add_argument(
        "--versions",
        default="v1,v2,v3",
        help="Comma-separated prompt versions (default: v1,v2,v3)",
    )
    evaluate.add_argument(
        "--samples-dir", type=Path, default=Path("data/samples")
    )
    evaluate.add_argument(
        "--gt-dir", type=Path, default=Path("data/ground_truth")
    )
    evaluate.add_argument(
        "--out", type=Path, default=Path("results/eval_v1_v2_v3.md")
    )
    evaluate.add_argument(
        "--parser-mode",
        default="text",
        help="Parser backend (default: text). Future: vlm-qwen, vlm-mistral, etc.",
    )

    args = parser.parse_args(argv)

    # ---- handlers -------------------------------------------------------
    if args.cmd == "extract":
        ex = Extractor(prompt_version=args.version)
        result = ex.extract_from_pdf(args.pdf)
        payload = {
            "document_id": result.document_id,
            "prompt_version": result.prompt_version,
            "schema_valid": result.schema_valid,
            "json_parse_error": result.json_parse_error,
            "validation_errors": result.validation_errors,
            "latency_ms": result.llm_response.latency_ms,
            "model": result.llm_response.model,
            "backend": result.llm_response.backend,
            "data": result.validated.model_dump(mode="json") if result.validated else result.parsed_json,
        }
        text = json.dumps(payload, indent=2, default=str)
        if args.out:
            args.out.write_text(text)
            print(f"wrote {args.out}", file=sys.stderr)
        else:
            print(text)
        return 0 if result.schema_valid else 1

    if args.cmd == "evaluate":
        versions = [v.strip() for v in args.versions.split(",") if v.strip()]
        report = run_evaluation(
            versions=versions,
            samples_dir=args.samples_dir,
            gt_dir=args.gt_dir,
            parser_mode=args.parser_mode,
        )
        out_path = write_report(report, args.out)
        print(f"wrote {out_path}", file=sys.stderr)
        # one-line console summary
        print()
        for r in report.runs:
            print(
                f"  {r.prompt_version}: schema_valid={r.overall.schema_validity_rate:.0%}, "
                f"F1={r.overall.f1:.3f}, "
                f"halluc={r.overall.hallucination_rate:.1%}, "
                f"p50={r.overall.latency_p50_ms:.0f}ms"
            )
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
