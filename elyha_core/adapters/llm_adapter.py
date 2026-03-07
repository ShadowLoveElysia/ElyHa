"""Unified LLM adapter interfaces and built-in providers."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Any, Protocol

from elyha_core.i18n import tr


@dataclass(slots=True)
class LLMMessage:
    """Single conversational message."""

    role: str
    content: str


@dataclass(slots=True)
class LLMRequest:
    """Normalized prompt request sent to concrete providers."""

    task_type: str
    messages: list[LLMMessage]
    system_prompt: str = ""
    platform_config: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LLMResponse:
    """Provider response normalized for core services."""

    ok: bool
    content: str
    reasoning: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error_code: str | None = None
    error_message: str | None = None
    provider: str = "unknown"
    raw: dict[str, Any] = field(default_factory=dict)


class LLMAdapter(Protocol):
    """Interface implemented by all LLM backends."""

    def generate(self, request: LLMRequest) -> LLMResponse:
        """Execute one generation request."""


class MockLLMAdapter:
    """Deterministic mock provider used in tests and offline dev."""

    provider_name = "mock"

    def generate(self, request: LLMRequest) -> LLMResponse:
        last_user = ""
        for message in reversed(request.messages):
            if message.role == "user":
                last_user = message.content.strip()
                break
        if request.task_type == "generate_branches":
            branch_count = int(request.platform_config.get("branch_count", 3))
            content = "\n".join(f"- Branch {i + 1}: {last_user[:80]}" for i in range(branch_count))
        elif request.task_type.startswith("review_"):
            content = (
                "score: 0.78\n"
                "findings:\n"
                "- continuity: acceptable\n"
                "- setting consistency: acceptable\n"
                "- risk: low"
            )
        else:
            content = f"[mock:{request.task_type}] {last_user[:200]}"

        token_estimate = max(1, len(content) // 4)
        return LLMResponse(
            ok=True,
            content=content,
            reasoning="mock_reasoning",
            prompt_tokens=token_estimate,
            completion_tokens=token_estimate,
            provider=self.provider_name,
        )


def create_llm_adapter(
    provider: str | None = None,
    *,
    platform_config: dict[str, Any] | None = None,
) -> LLMAdapter:
    """Factory for creating configured adapter instances."""
    raw_provider = provider if provider is not None else os.getenv("ELYHA_LLM_PROVIDER")
    chosen = (raw_provider or "mock").strip().lower()
    cfg = platform_config or {}
    if chosen == "mock":
        return MockLLMAdapter()
    if chosen in {"legacy", "llmrequester"}:
        from elyha_core.adapters.legacy_llmrequester_adapter import LegacyLLMRequesterAdapter

        return LegacyLLMRequesterAdapter(default_platform_config=cfg)
    raise ValueError(tr("err.llm_provider_unsupported", provider=repr(chosen)))
