"""PDF -> plain text + lightweight layout hints.

Deliberately simple for v1: page text concatenated with page markers.
Layout-aware variants (tables, bbox-based reading order) are planned for v2/v3.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pdfplumber


def pdf_to_text(pdf_path: str | Path, max_pages: Optional[int] = None) -> str:
    """Extract text from a PDF, page by page, with `[PAGE n]` markers."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(path)

    pages_text: list[str] = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            if max_pages is not None and i > max_pages:
                break
            text = page.extract_text() or ""
            pages_text.append(f"[PAGE {i}]\n{text.strip()}")
    return "\n\n".join(pages_text)


def truncate_for_context(text: str, max_chars: int = 12000) -> str:
    """Naive truncation to fit small open-source model context windows."""
    if len(text) <= max_chars:
        return text
    head = text[: max_chars - 200]
    return head + "\n\n[...TRUNCATED FOR CONTEXT WINDOW...]"
