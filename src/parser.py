"""Document → text (and, in future modes, layout / images).

The public entry point is `parse_document(path, mode='text')` so callers
don't depend on which backend is used. `mode` is the extension hook for
VLM / layout-aware parsers without changing the signature in the extractor
or harness.

Currently implemented modes
---------------------------
* `'text'`      — pdfplumber for PDFs, raw read for `.txt`. Returns a
                  single string with `[PAGE n]` markers.
* `'vlm-qwen'`  — render PDF pages to images, send each to a multimodal
                  model (default Ollama tag `qwen2.5vl:7b`) via OpenAI-compat
                  endpoint), concatenate per-page outputs with `[PAGE n]`
                  markers. Returns the same ParsedDocument shape so the
                  rest of the pipeline runs unchanged.

Planned modes (see docs/future_work.md §1)
------------------------------------------
* `'vlm-marker'` — Marker / Surya pipeline; preserves tables as markdown.
* `'olmocr'`     — AI2 olmOCR.

Each mode returns the same `ParsedDocument` shape so callers can opt in by
changing one env var or CLI flag.
"""

from __future__ import annotations

import base64
import io
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pdfplumber


# --------------------------------------------------------------------------- #
@dataclass
class ParsedDocument:
    """Backend-agnostic representation of a parsed document.

    `text` is always populated. `images`, `layout_blocks`, and `metadata`
    capture optional information emitted by richer parser modes. Today's
    `text` mode leaves images / layout_blocks empty.
    """
    text: str
    images: list[bytes] = field(default_factory=list)
    layout_blocks: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
SUPPORTED_MODES = {"text", "vlm-qwen"}
DEFAULT_MODE = "text"


def parse_document(
    path: str | Path,
    mode: str = DEFAULT_MODE,
    max_pages: Optional[int] = None,
) -> ParsedDocument:
    """Read a document into a backend-agnostic ParsedDocument.

    Args:
        path: Path to a `.pdf` or `.txt` file.
        mode: Parsing backend. See module docstring.
        max_pages: For multi-page PDFs, optionally truncate.

    Raises:
        FileNotFoundError: if `path` does not exist.
        ValueError: if `mode` is unknown or unsupported for the file type.
    """
    if mode not in SUPPORTED_MODES:
        raise ValueError(
            f"parser mode {mode!r} is not implemented. "
            f"Supported: {sorted(SUPPORTED_MODES)}. "
            "See docs/future_work.md §1 for planned modes."
        )

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)

    if mode == "text":
        if p.suffix.lower() == ".pdf":
            text = _pdf_to_text_pdfplumber(p, max_pages=max_pages)
        else:
            text = p.read_text(encoding="utf-8")
        return ParsedDocument(text=text, metadata={"source": str(p), "mode": mode})

    if mode == "vlm-qwen":
        if p.suffix.lower() != ".pdf":
            raise ValueError(
                f"vlm-qwen mode requires a PDF input; got {p.suffix!r}. "
                "Use synth_generator.py --format pdf or --render-existing first."
            )
        return _parse_vlm_qwen(p, max_pages=max_pages)

    raise AssertionError(f"unreachable: {mode!r}")  # pragma: no cover


# --------------------------------------------------------------------------- #
#  text mode (pdfplumber)                                                     #
# --------------------------------------------------------------------------- #
def pdf_to_text(pdf_path: str | Path, max_pages: Optional[int] = None) -> str:
    """Legacy convenience wrapper. Prefer `parse_document` in new code."""
    return _pdf_to_text_pdfplumber(Path(pdf_path), max_pages=max_pages)


def _pdf_to_text_pdfplumber(path: Path, max_pages: Optional[int] = None) -> str:
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


# --------------------------------------------------------------------------- #
#  vlm-qwen mode (Qwen2.5-VL via Ollama OpenAI-compat endpoint)               #
# --------------------------------------------------------------------------- #
_VLM_USER_PROMPT = (
    "You are reading a scanned insurance document image. Transcribe the "
    "page faithfully, preserving the visible layout:\n"
    "  - Keep field labels and their values on the same line when possible.\n"
    "  - For tables, preserve column structure with whitespace alignment.\n"
    "  - For checkboxes, write [X] if checked and [ ] if unchecked.\n"
    "  - For blank lines / placeholder underscores, write the underscores "
    "    so a downstream model can tell the field is empty.\n"
    "Output the page text only. No prose, no summarization, no commentary."
)


def _parse_vlm_qwen(path: Path, max_pages: Optional[int] = None) -> ParsedDocument:
    """Render PDF pages -> PIL images -> Qwen2.5-VL (Ollama) -> text."""
    images = _pdf_to_pil_images(path, max_pages=max_pages)
    image_bytes_list: list[bytes] = []
    pages_text: list[str] = []

    client = _make_vlm_client()
    model = os.getenv("VLM_MODEL", "qwen2.5vl:7b")

    for i, img in enumerate(images, start=1):
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()
        image_bytes_list.append(png_bytes)
        b64 = base64.b64encode(png_bytes).decode("ascii")

        response = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": _VLM_USER_PROMPT},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }],
            temperature=0.0,
        )
        page_text = (response.choices[0].message.content or "").strip()
        pages_text.append(f"[PAGE {i}]\n{page_text}")

    return ParsedDocument(
        text="\n\n".join(pages_text),
        images=image_bytes_list,
        metadata={"source": str(path), "mode": "vlm-qwen", "model": model},
    )


def _pdf_to_pil_images(path: Path, max_pages: Optional[int] = None):
    """Render each PDF page as a PIL.Image at 2× scale (≈ 144 DPI)."""
    import fitz  # pymupdf
    from PIL import Image

    doc = fitz.open(str(path))
    images = []
    try:
        for i, page in enumerate(doc):
            if max_pages is not None and i >= max_pages:
                break
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            mode = "RGBA" if pix.alpha else "RGB"
            img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
            if mode == "RGBA":
                img = img.convert("RGB")
            images.append(img)
    finally:
        doc.close()
    return images


def _make_vlm_client():
    """OpenAI-compatible client pointed at Ollama (or another VLM endpoint).

    Defers import so the rest of the module loads without `openai` installed.
    Override the endpoint via env vars:
        VLM_BASE_URL  (default: OLLAMA_BASE_URL or http://localhost:11434/v1)
        VLM_API_KEY   (default: 'ollama' — Ollama doesn't validate)
        VLM_MODEL     (default Ollama tag: qwen2.5vl:7b)
    """
    from openai import OpenAI

    base_url = (
        os.getenv("VLM_BASE_URL")
        or os.getenv("OLLAMA_BASE_URL")
        or "http://localhost:11434/v1"
    )
    api_key = os.getenv("VLM_API_KEY", "ollama")
    return OpenAI(base_url=base_url, api_key=api_key)


# --------------------------------------------------------------------------- #
def truncate_for_context(text: str, max_chars: int = 12000) -> str:
    """Naive truncation to fit small open-source model context windows."""
    if len(text) <= max_chars:
        return text
    head = text[: max_chars - 200]
    return head + "\n\n[...TRUNCATED FOR CONTEXT WINDOW...]"
