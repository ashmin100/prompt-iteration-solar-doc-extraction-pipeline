"""End-to-end extraction pipeline.

PDF -> text -> LLM (versioned prompt) -> JSON parse -> Pydantic validation.
Returns a structured ExtractionResult including diagnostics for the eval harness.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from src.llm_client import LLMClient, LLMResponse
from src.parser import pdf_to_text, truncate_for_context
from src.prompts import PROMPT_VERSIONS
from src.schema import InsuranceForm


# --------------------------------------------------------------------------- #
@dataclass
class ExtractionResult:
    document_id: str
    prompt_version: str
    raw_text: str
    llm_response: LLMResponse
    parsed_json: Optional[dict] = None
    validated: Optional[InsuranceForm] = None
    schema_valid: bool = False
    json_parse_error: Optional[str] = None
    validation_errors: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
def _strip_code_fences(s: str) -> str:
    """Open-source models love wrapping JSON in ```json ... ``` despite instructions."""
    s = s.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", s, flags=re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return s


def _extract_first_json_object(s: str) -> Optional[str]:
    """Find the outermost balanced {...} block. Handles trailing commentary."""
    depth = 0
    start = -1
    in_string = False
    escape = False
    for i, ch in enumerate(s):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                return s[start : i + 1]
    return None


# --------------------------------------------------------------------------- #
class Extractor:
    def __init__(
        self,
        llm: Optional[LLMClient] = None,
        prompt_version: str = "v1",
    ) -> None:
        if prompt_version not in PROMPT_VERSIONS:
            raise ValueError(
                f"Unknown prompt version {prompt_version!r}; "
                f"choose one of {list(PROMPT_VERSIONS)}"
            )
        self.llm = llm or LLMClient()
        self.prompt_version = prompt_version
        self._system, self._user_template = PROMPT_VERSIONS[prompt_version]

    # --------------------------------------------------------------------- #
    def extract_from_text(
        self, document_text: str, document_id: str = "in-memory"
    ) -> ExtractionResult:
        text = truncate_for_context(document_text)
        user = self._user_template.replace("<<DOCUMENT_TEXT>>", text)

        # Only request JSON mode for v2/v3 — v1 is intentionally bare.
        json_mode = self.prompt_version in {"v2", "v3"}

        response = self.llm.chat(
            system=self._system,
            user=user,
            temperature=0.0,
            max_tokens=2048,
            json_mode=json_mode,
        )

        result = ExtractionResult(
            document_id=document_id,
            prompt_version=self.prompt_version,
            raw_text=text,
            llm_response=response,
        )

        # 1. Strip fences / pull out first JSON object
        cleaned = _strip_code_fences(response.content)
        candidate = cleaned if cleaned.startswith("{") else _extract_first_json_object(cleaned)
        if candidate is None:
            result.json_parse_error = "no JSON object found in response"
            return result

        # 2. JSON parse
        try:
            result.parsed_json = json.loads(candidate)
        except json.JSONDecodeError as e:
            result.json_parse_error = f"JSONDecodeError: {e}"
            return result

        # 3. Pydantic validation
        try:
            result.validated = InsuranceForm.model_validate(result.parsed_json)
            result.schema_valid = True
        except ValidationError as e:
            result.validation_errors = [
                f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
                for err in e.errors()
            ]

        return result

    # --------------------------------------------------------------------- #
    def extract_from_pdf(self, pdf_path: str | Path) -> ExtractionResult:
        path = Path(pdf_path)
        text = pdf_to_text(path)
        return self.extract_from_text(text, document_id=path.stem)
