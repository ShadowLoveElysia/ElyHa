"""Compatibility generation mixin for AIService."""

from __future__ import annotations

from .chapter_generation_mixin import AIServiceChapterGenerationMixin
from .workflow_assist_mixin import AIServiceWorkflowAssistMixin


class AIServiceGenerationMixin(AIServiceChapterGenerationMixin, AIServiceWorkflowAssistMixin):
    """Backward-compatible alias that composes split generation mixins."""


__all__ = ["AIServiceGenerationMixin"]
