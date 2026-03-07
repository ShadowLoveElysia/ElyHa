"""AI command handlers used by TUI."""

from __future__ import annotations

from elyha_core.i18n import tr
from elyha_core.models.task import TaskStatus
from elyha_core.services.ai_service import AIService


def ai_status() -> dict[str, str]:
    """Report AI module status for current milestone."""
    return {
        "status": "ready",
        "message": tr("ai.status.message"),
    }


def generate_chapter(
    service: AIService,
    *,
    project_id: str,
    node_id: str,
    token_budget: int = 2200,
    style_hint: str = "",
    workflow_mode: str = "multi_agent",
) -> dict[str, object]:
    result = service.generate_chapter(
        project_id,
        node_id,
        token_budget=token_budget,
        style_hint=style_hint,
        workflow_mode=workflow_mode,
    )
    return {
        "task_id": result.task_id,
        "project_id": result.project_id,
        "node_id": result.node_id,
        "content": result.content,
        "revision": result.revision,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "provider": result.provider,
        "workflow_mode": result.workflow_mode,
        "agent_trace": result.agent_trace,
    }


def generate_branches(
    service: AIService,
    *,
    project_id: str,
    node_id: str,
    n: int = 3,
    token_budget: int = 1800,
) -> dict[str, object]:
    options = service.generate_branches(
        project_id,
        node_id,
        n=n,
        token_budget=token_budget,
    )
    return {
        "project_id": project_id,
        "node_id": node_id,
        "options": [{"title": option.title, "description": option.description} for option in options],
    }


def review_lore(
    service: AIService,
    *,
    project_id: str,
    node_id: str,
    token_budget: int = 1500,
) -> dict[str, object]:
    report = service.review_lore(project_id, node_id, token_budget=token_budget)
    return {
        "task_id": report.task_id,
        "project_id": report.project_id,
        "node_id": report.node_id,
        "review_type": report.review_type,
        "summary": report.summary,
        "score": report.score,
        "issues": report.issues,
        "revision": report.revision,
    }


def review_logic(
    service: AIService,
    *,
    project_id: str,
    node_id: str,
    token_budget: int = 1500,
) -> dict[str, object]:
    report = service.review_logic(project_id, node_id, token_budget=token_budget)
    return {
        "task_id": report.task_id,
        "project_id": report.project_id,
        "node_id": report.node_id,
        "review_type": report.review_type,
        "summary": report.summary,
        "score": report.score,
        "issues": report.issues,
        "revision": report.revision,
    }


def task_get(service: AIService, *, task_id: str) -> dict[str, object]:
    task = service.get_task(task_id)
    return {
        "id": task.id,
        "project_id": task.project_id,
        "node_id": task.node_id,
        "task_type": task.task_type,
        "status": task.status.value,
        "error_code": task.error_code,
        "error_message": task.error_message,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        "revision": task.revision,
        "created_at": task.created_at.isoformat(),
    }


def task_cancel(service: AIService, *, task_id: str) -> dict[str, object]:
    task = service.cancel_task(task_id)
    return {
        "id": task.id,
        "status": task.status.value,
        "error_code": task.error_code,
        "error_message": task.error_message,
        "revision": task.revision,
    }


def task_list(
    service: AIService,
    *,
    project_id: str,
    status: str | None = None,
    limit: int | None = None,
) -> list[dict[str, object]]:
    parsed_status = TaskStatus(status) if status else None
    tasks = service.list_tasks(project_id, status=parsed_status, limit=limit)
    return [
        {
            "id": task.id,
            "project_id": task.project_id,
            "node_id": task.node_id,
            "task_type": task.task_type,
            "status": task.status.value,
            "error_code": task.error_code,
            "error_message": task.error_message,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "finished_at": task.finished_at.isoformat() if task.finished_at else None,
            "revision": task.revision,
            "created_at": task.created_at.isoformat(),
        }
        for task in tasks
    ]
