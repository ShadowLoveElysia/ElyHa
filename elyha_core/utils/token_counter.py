"""Token counting helper with best-effort exact tokenizer support."""

from __future__ import annotations

import os
from typing import Any


class TokenCounter:
    """Count tokens with `tiktoken` when available, else deterministic fallback."""

    def __init__(self) -> None:
        self._encoder_cache: dict[str, Any | None] = {}
        self._backend_cache: dict[str, str] = {}

    def count(self, text: str, *, model_hint: str = "") -> int:
        clean = str(text or "")
        if not clean:
            return 0
        encoder = self._encoder_for_model(model_hint)
        if encoder is None:
            return max(1, len(clean) // 4)
        try:
            return len(encoder.encode(clean))
        except Exception:
            return max(1, len(clean) // 4)

    def backend(self, *, model_hint: str = "") -> str:
        normalized = self._normalize_model_hint(model_hint)
        if normalized in self._backend_cache:
            return self._backend_cache[normalized]
        _ = self._encoder_for_model(normalized)
        return self._backend_cache.get(normalized, "approx_char_div4")

    def default_model_hint(self) -> str:
        return str(os.getenv("ELYHA_MODEL_NAME", "") or "").strip()

    def _encoder_for_model(self, model_hint: str) -> Any | None:
        normalized = self._normalize_model_hint(model_hint)
        if normalized in self._encoder_cache:
            return self._encoder_cache[normalized]

        try:
            import tiktoken  # type: ignore
        except Exception:
            self._encoder_cache[normalized] = None
            self._backend_cache[normalized] = "approx_char_div4"
            return None

        tried_model = normalized
        try:
            if tried_model:
                encoder = tiktoken.encoding_for_model(tried_model)
                self._encoder_cache[normalized] = encoder
                self._backend_cache[normalized] = f"tiktoken:model:{tried_model}"
                return encoder
        except Exception:
            pass

        try:
            encoder = tiktoken.get_encoding("cl100k_base")
            self._encoder_cache[normalized] = encoder
            backend = "tiktoken:cl100k_base"
            if tried_model:
                backend += f":fallback_for:{tried_model}"
            self._backend_cache[normalized] = backend
            return encoder
        except Exception:
            self._encoder_cache[normalized] = None
            self._backend_cache[normalized] = "approx_char_div4"
            return None

    def _normalize_model_hint(self, model_hint: str) -> str:
        return str(model_hint or "").strip().lower()

