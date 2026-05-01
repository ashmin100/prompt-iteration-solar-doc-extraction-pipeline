"""Tiny CLI: `python -m src.cli extract --pdf path --version v2`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.extractor import Extractor


def main(argv: list[str] | None = None) -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(prog="solar-doc-extraction-pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)

    extract = sub.add_parser("extract", help="Extract structured JSON from one PDF")
    extract.add_argument("--pdf", required=True, type=Path)
    extract.add_argument("--version", default="v2", choices=["v1", "v2", "v3"])
    extract.add_argument("--out", type=Path, default=None)

    args = parser.parse_args(argv)

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

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
