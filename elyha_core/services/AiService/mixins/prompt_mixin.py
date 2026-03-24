"""Compatibility prompt mixin for AIService."""

from __future__ import annotations

from .prompt_builders_mixin import AIServicePromptBuildersMixin
from .prompt_parsers_mixin import AIServicePromptParsersMixin


class AIServicePromptMixin(AIServicePromptBuildersMixin, AIServicePromptParsersMixin):
    """Backward-compatible alias that composes split prompt mixins."""


__all__ = ["AIServicePromptMixin"]
