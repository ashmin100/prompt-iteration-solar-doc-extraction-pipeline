"""OpenAI-compatible multi-backend LLM client.

Supports Ollama (local), Groq, Hugging Face Inference, and any generic
OpenAI-compatible endpoint (Together, OpenRouter, Fireworks, vLLM, etc.).
The extractor only depends on `LLMClient.chat()` so swapping backends is
just an env-var change.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential


@dataclass
class LLMResponse:
    content: str
    model: str
    backend: str
    latency_ms: float
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None


class LLMClient:
    """Thin OpenAI-compatible client that routes to one of several backends."""

    def __init__(self, backend: Optional[str] = None) -> None:
        self.backend = (backend or os.getenv("LLM_BACKEND", "ollama")).lower()
        self.base_url, self.api_key, self.model = self._resolve_backend(self.backend)
        self._client = OpenAI(base_url=self.base_url, api_key=self.api_key or "sk-noop")

    # --------------------------------------------------------------------- #
    @staticmethod
    def _resolve_backend(name: str) -> tuple[str, str, str]:
        if name == "ollama":
            return (
                os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                "ollama",  # ollama doesn't validate this
                os.getenv("OLLAMA_MODEL", "llama3.1:8b"),
            )
        if name == "groq":
            return (
                "https://api.groq.com/openai/v1",
                os.getenv("GROQ_API_KEY", ""),
                os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            )
        if name == "hf":
            # HF Inference API has an OpenAI-compatible chat completions endpoint.
            model = os.getenv("HF_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
            return (
                f"https://api-inference.huggingface.co/models/{model}/v1",
                os.getenv("HF_API_KEY", ""),
                model,
            )
        if name == "openai_compat":
            return (
                os.getenv("OPENAI_COMPAT_BASE_URL", ""),
                os.getenv("OPENAI_COMPAT_API_KEY", ""),
                os.getenv("OPENAI_COMPAT_MODEL", ""),
            )
        raise ValueError(f"Unknown backend: {name}")

    # --------------------------------------------------------------------- #
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def chat(
        self,
        system: str,
        user: str,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> LLMResponse:
        import time

        messages: List[dict] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            # Most hosted OpenAI-compatible backends accept this; Ollama silently ignores it.
            kwargs["response_format"] = {"type": "json_object"}

        t0 = time.perf_counter()
        completion = self._client.chat.completions.create(**kwargs)
        latency_ms = (time.perf_counter() - t0) * 1000

        choice = completion.choices[0]
        content = choice.message.content or ""
        usage = getattr(completion, "usage", None)
        return LLMResponse(
            content=content,
            model=self.model,
            backend=self.backend,
            latency_ms=latency_ms,
            prompt_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
            completion_tokens=getattr(usage, "completion_tokens", None) if usage else None,
        )
