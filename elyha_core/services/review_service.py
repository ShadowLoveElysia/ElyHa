"""Review service facade."""

from __future__ import annotations

from elyha_core.services.ai_service import AIService, ReviewReport


class ReviewService:
    """Thin wrapper around AIService review methods."""

    def __init__(self, ai_service: AIService) -> None:
        self.ai_service = ai_service

    def review_lore(self, project_id: str, node_id: str) -> ReviewReport:
        return self.ai_service.review_lore(project_id, node_id)

    def review_logic(self, project_id: str, node_id: str) -> ReviewReport:
        return self.ai_service.review_logic(project_id, node_id)
