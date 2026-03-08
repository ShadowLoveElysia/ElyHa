"""AI generation/review orchestration with task tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any, NoReturn, TypedDict, cast

from elyha_core.adapters.llm_adapter import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    create_llm_adapter,
)
from elyha_core.i18n import tr
from elyha_core.llm_presets import LLMPreset, preset_to_platform_config
from elyha_core.models.task import Task, TaskStatus
from elyha_core.services.context_service import ContextPack, ContextService
from elyha_core.services.graph_service import GraphService, NodeCreate
from elyha_core.services.validation_service import ValidationService
from elyha_core.models.node import NodeType
from elyha_core.storage.repository import SQLiteRepository
from elyha_core.utils.clock import utc_now
from elyha_core.utils.ids import generate_id
from elyha_core.utils.text_splitter import split_text_by_chars
from langgraph.graph import END, StateGraph


@dataclass(slots=True)
class BranchOption:
    title: str
    description: str
    outline_steps: list[str] = field(default_factory=list)
    sentiment: str = "neutral"


@dataclass(slots=True)
class GenerateResult:
    task_id: str
    project_id: str
    node_id: str
    content: str
    revision: int
    prompt_tokens: int
    completion_tokens: int
    provider: str
    workflow_mode: str = "single"
    agent_trace: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ReviewReport:
    task_id: str
    project_id: str
    node_id: str
    review_type: str
    summary: str
    score: float
    issues: list[str] = field(default_factory=list)
    revision: int = 0


@dataclass(slots=True)
class ChatAssistResult:
    project_id: str
    node_id: str | None
    route: str
    reply: str
    review_bypassed: bool = False
    updated_node_id: str | None = None
    suggested_node_ids: list[str] = field(default_factory=list)
    suggested_options: list[dict[str, str]] = field(default_factory=list)
    revision: int = 0


@dataclass(slots=True)
class OutlineGuideResult:
    project_id: str
    questions: list[str] = field(default_factory=list)
    outline_markdown: str = ""
    chapter_beats: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    provider: str = "unknown"
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(slots=True)
class WorkflowClarifyResult:
    project_id: str
    questions: list[str] = field(default_factory=list)
    provider: str = "unknown"
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(slots=True)
class WorkflowSyncResult:
    project_id: str
    background_markdown: str = ""
    must_confirm: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    risk_notes: list[str] = field(default_factory=list)
    search_requested: bool = False
    search_used: bool = False
    provider: str = "unknown"
    prompt_tokens: int = 0
    completion_tokens: int = 0


class WorkflowState(TypedDict, total=False):
    task_type: str
    project_id: str
    node_id: str
    token_budget: int
    style_hint: str
    branch_count: int
    workflow_mode: str
    node: Any
    context_pack: ContextPack
    llm_route: dict[str, Any]
    prompt: str
    planner_prompt: str
    planner_response: LLMResponse
    writer_prompt: str
    writer_response: LLMResponse
    reviewer_prompt: str
    reviewer_response: LLMResponse
    synthesizer_prompt: str
    agent_trace: dict[str, str]
    llm_response: LLMResponse


class AIService:
    """Unified AI workflows for generation, branching and review."""

    def __init__(
        self,
        repository: SQLiteRepository,
        graph_service: GraphService,
        context_service: ContextService,
        validation_service: ValidationService,
        *,
        llm_provider: str | None = None,
        llm_platform_config: dict[str, Any] | None = None,
        llm_presets: dict[str, LLMPreset] | None = None,
    ) -> None:
        self.repository = repository
        self.graph_service = graph_service
        self.context_service = context_service
        self.validation_service = validation_service
        self._default_platform_config = (llm_platform_config or {}).copy()
        self._llm_presets = dict(llm_presets or {})
        self._adapter_cache: dict[str, Any] = {}
        self.llm_adapter = create_llm_adapter(
            llm_provider,
            platform_config=self._default_platform_config,
        )
        self._single_workflow = self._build_single_workflow()
        self._chapter_multi_workflow = self._build_chapter_multi_workflow()

    def generate_chapter(
        self,
        project_id: str,
        node_id: str,
        *,
        token_budget: int = 2200,
        style_hint: str = "",
        workflow_mode: str = "multi_agent",
    ) -> GenerateResult:
        normalized_mode = self._normalize_workflow_mode(workflow_mode)
        task = self._create_task(project_id, node_id, task_type="generate_chapter")
        self._set_task_running(task)
        try:
            flow_state = self._run_workflow(
                task_type="generate_chapter",
                project_id=project_id,
                node_id=node_id,
                token_budget=token_budget,
                style_hint=style_hint,
                workflow_mode=normalized_mode,
            )
            node = cast(Any, flow_state["node"])
            response = cast(LLMResponse, flow_state["llm_response"])
            agent_trace = cast(dict[str, str], flow_state.get("agent_trace", {}))
            route = cast(dict[str, Any], flow_state.get("llm_route", {}))
            content = response.content.strip()
            if not content:
                raise RuntimeError(tr("ai.error.empty_response"))
            node_patch = {
                "status": "generated",
                "metadata": {
                    **node.metadata,
                    "content": content,
                    "summary": content[:200],
                    "last_generation_at": utc_now().isoformat(),
                    "ai_workflow_mode": normalized_mode,
                    "ai_agent_trace": agent_trace,
                    "ai_agent_preset": str(route.get("preset_tag", "")),
                    "ai_agent_name": str(route.get("preset_name", "")),
                    "ai_review_passed_once": bool(node.metadata.get("ai_review_passed_once"))
                    or normalized_mode == "multi_agent",
                },
            }
            self.graph_service.update_node(project_id, node_id, node_patch)
            self.repository.replace_node_chunks(node_id, split_text_by_chars(content))
            revision = self._project_revision(project_id)
            self._set_task_success(task, revision=revision)
            return GenerateResult(
                task_id=task.id,
                project_id=project_id,
                node_id=node_id,
                content=content,
                revision=revision,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                provider=response.provider,
                workflow_mode=normalized_mode,
                agent_trace=agent_trace,
            )
        except Exception as exc:
            self._set_task_failed(task, exc)
            raise

    def generate_branches(
        self,
        project_id: str,
        node_id: str,
        *,
        n: int = 3,
        token_budget: int = 1800,
    ) -> list[BranchOption]:
        if n <= 0:
            raise ValueError(tr("err.n_positive"))
        task = self._create_task(project_id, node_id, task_type="generate_branches")
        self._set_task_running(task)
        try:
            flow_state = self._run_workflow(
                task_type="generate_branches",
                project_id=project_id,
                node_id=node_id,
                token_budget=token_budget,
                branch_count=n,
                workflow_mode="single",
            )
            response = cast(LLMResponse, flow_state["llm_response"])
            options = self._parse_branch_options(response.content, count=n)
            self._set_task_success(task, revision=self._project_revision(project_id))
            return options
        except Exception as exc:
            self._set_task_failed(task, exc)
            raise

    def review_lore(
        self,
        project_id: str,
        node_id: str,
        *,
        token_budget: int = 1500,
    ) -> ReviewReport:
        return self._review(
            review_type="review_lore",
            project_id=project_id,
            node_id=node_id,
            token_budget=token_budget,
        )

    def review_logic(
        self,
        project_id: str,
        node_id: str,
        *,
        token_budget: int = 1500,
    ) -> ReviewReport:
        return self._review(
            review_type="review_logic",
            project_id=project_id,
            node_id=node_id,
            token_budget=token_budget,
        )

    def chat_assist(
        self,
        project_id: str,
        *,
        message: str,
        node_id: str | None = None,
        token_budget: int = 1800,
    ) -> ChatAssistResult:
        cleaned_message, explicit_route = self._extract_chat_route(message)
        if not cleaned_message:
            raise ValueError(tr("ai.chat.message_required"))
        if self.repository.get_project(project_id) is None:
            self._raise_project_missing(project_id)

        node = self.graph_service.get_node(project_id, node_id) if node_id else None
        node_metadata = node.metadata if node and isinstance(node.metadata, dict) else {}
        auto_review_passed = bool(node_metadata.get("ai_review_passed_once"))
        route = explicit_route
        if route == "auto":
            if node is None:
                route = "planner"
            else:
                route = "writer"
        review_bypassed = node is not None and auto_review_passed and route == "writer"

        if node is None:
            if route == "planner" and self._is_planner_scope_violation(cleaned_message):
                return ChatAssistResult(
                    project_id=project_id,
                    node_id=None,
                    route="planner",
                    reply=tr("ai.chat.planner_scope_refusal"),
                    review_bypassed=False,
                    suggested_options=[],
                    revision=self._project_revision(project_id),
                )
            response = self._generate(
                task_type="chat_global_" + route,
                prompt=self._chat_global_prompt(project_id, cleaned_message, route=route),
                platform_config={"token_budget": token_budget},
            )
            content = response.content.strip() or tr("ai.chat.empty_fallback")
            return ChatAssistResult(
                project_id=project_id,
                node_id=None,
                route=route,
                reply=content,
                review_bypassed=False,
                revision=self._project_revision(project_id),
            )

        context = self.context_service.build_context(
            project_id,
            node.id,
            token_budget=max(400, token_budget),
        )
        llm_route = self._resolve_node_llm_route(node)

        if route == "planner":
            if self._is_planner_scope_violation(cleaned_message):
                return ChatAssistResult(
                    project_id=project_id,
                    node_id=node.id,
                    route="planner",
                    reply=tr("ai.chat.planner_scope_refusal"),
                    review_bypassed=False,
                    suggested_options=[],
                    revision=self._project_revision(project_id),
                )
            response = self._generate(
                task_type="chat_plan",
                prompt=self._chat_planner_prompt(node.title, context, cleaned_message),
                platform_config={"token_budget": max(600, token_budget // 2), "branch_count": 3},
                llm_route=llm_route,
            )
            options = self._parse_branch_options(response.content, count=3)
            reply = tr(
                "ai.chat.planner_reply",
                raw=response.content.strip() or tr("ai.chat.empty_fallback"),
                count=len(options),
            )
            return ChatAssistResult(
                project_id=project_id,
                node_id=node.id,
                route="planner",
                reply=reply,
                review_bypassed=False,
                suggested_options=[
                    {
                        "title": option.title,
                        "description": option.description,
                        "outline_steps": "\n".join(option.outline_steps),
                        "next_1": option.outline_steps[0] if len(option.outline_steps) > 0 else "",
                        "next_2": option.outline_steps[1] if len(option.outline_steps) > 1 else "",
                        "sentiment": option.sentiment,
                    }
                    for option in options
                ],
                revision=self._project_revision(project_id),
            )

        response = self._generate(
            task_type="chat_writer",
            prompt=self._chat_writer_prompt(node.title, context, cleaned_message, node_metadata),
            platform_config={"token_budget": token_budget},
            llm_route=llm_route,
        )
        content = response.content.strip()
        if not content:
            raise RuntimeError(tr("ai.error.empty_response"))

        patched_metadata = node_metadata.copy()
        patched_metadata["content"] = content
        patched_metadata["summary"] = content[:200]
        patched_metadata["ai_chat_last_route"] = route
        patched_metadata["ai_last_human_edit_at"] = utc_now().isoformat()
        patched_metadata["ai_review_passed_once"] = auto_review_passed
        self.graph_service.update_node(
            project_id,
            node.id,
            {
                "status": "generated",
                "metadata": patched_metadata,
            },
        )
        self.repository.replace_node_chunks(node.id, split_text_by_chars(content))
        return ChatAssistResult(
            project_id=project_id,
            node_id=node.id,
            route="writer",
            reply=content,
            review_bypassed=review_bypassed,
            updated_node_id=node.id,
            revision=self._project_revision(project_id),
        )

    def guide_project_outline(
        self,
        project_id: str,
        *,
        goal: str,
        sync_context: str = "",
        specify: str = "",
        clarify_answers: str = "",
        plan_notes: str = "",
        constraints: str = "",
        tone: str = "",
        token_budget: int = 2200,
    ) -> OutlineGuideResult:
        if self.repository.get_project(project_id) is None:
            self._raise_project_missing(project_id)
        clean_goal = str(goal).strip()
        if not clean_goal:
            raise ValueError(tr("ai.chat.message_required"))
        response = self._generate(
            task_type="outline_guide",
            prompt=self._outline_guide_prompt(
                project_id,
                goal=clean_goal,
                sync_context=str(sync_context or "").strip(),
                specify=str(specify or "").strip(),
                clarify_answers=str(clarify_answers or "").strip(),
                plan_notes=str(plan_notes or "").strip(),
                constraints=str(constraints or "").strip(),
                tone=str(tone or "").strip(),
            ),
            platform_config={"token_budget": max(800, token_budget)},
        )
        parsed = self._parse_outline_guide_payload(response.content)
        questions = self._normalize_outline_list(parsed.get("questions"), limit=8)
        chapter_beats = self._normalize_outline_list(parsed.get("chapter_beats"), limit=16)
        next_steps = self._normalize_outline_list(parsed.get("next_steps"), limit=8)
        outline_markdown = str(parsed.get("outline_markdown", "")).strip()
        if not outline_markdown:
            outline_markdown = response.content.strip() or tr("ai.chat.empty_fallback")
        return OutlineGuideResult(
            project_id=project_id,
            questions=questions,
            outline_markdown=outline_markdown,
            chapter_beats=chapter_beats,
            next_steps=next_steps,
            provider=response.provider,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
        )

    def guide_workflow_clarify(
        self,
        project_id: str,
        *,
        goal: str,
        sync_context: str = "",
        specify: str = "",
        constraints: str = "",
        tone: str = "",
        token_budget: int = 1200,
    ) -> WorkflowClarifyResult:
        if self.repository.get_project(project_id) is None:
            self._raise_project_missing(project_id)
        clean_goal = str(goal).strip()
        if not clean_goal:
            raise ValueError(tr("ai.chat.message_required"))
        response = self._generate(
            task_type="workflow_clarify",
            prompt=self._workflow_clarify_prompt(
                project_id,
                goal=clean_goal,
                sync_context=str(sync_context or "").strip(),
                specify=str(specify or "").strip(),
                constraints=str(constraints or "").strip(),
                tone=str(tone or "").strip(),
            ),
            platform_config={"token_budget": max(600, token_budget)},
        )
        questions = self._parse_question_lines(response.content, limit=6)
        if not questions:
            questions = self._normalize_outline_list(response.content, limit=6)
        return WorkflowClarifyResult(
            project_id=project_id,
            questions=questions,
            provider=response.provider,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
        )

    def guide_workflow_sync_background(
        self,
        project_id: str,
        *,
        goal: str,
        sync_context: str,
        mode: str = "",
        constraints: str = "",
        tone: str = "",
        token_budget: int = 1400,
    ) -> WorkflowSyncResult:
        if self.repository.get_project(project_id) is None:
            self._raise_project_missing(project_id)
        clean_goal = str(goal).strip()
        clean_sync = str(sync_context).strip()
        if not clean_goal:
            raise ValueError(tr("ai.chat.message_required"))
        if not clean_sync:
            raise ValueError(tr("ai.chat.message_required"))
        search_requested = bool(self._default_platform_config.get("web_search_enabled"))
        response = self._generate(
            task_type="workflow_sync_background",
            prompt=self._workflow_sync_prompt(
                project_id,
                goal=clean_goal,
                sync_context=clean_sync,
                mode=str(mode or "").strip(),
                constraints=str(constraints or "").strip(),
                tone=str(tone or "").strip(),
                search_requested=search_requested,
            ),
            platform_config={
                "token_budget": max(800, token_budget),
                "web_search_enabled": search_requested,
            },
        )
        parsed = self._parse_workflow_sync_payload(response.content)
        background_markdown = str(parsed.get("background_markdown", "")).strip()
        if not background_markdown:
            background_markdown = response.content.strip() or tr("ai.chat.empty_fallback")
        must_confirm = self._normalize_outline_list(parsed.get("must_confirm"), limit=10)
        citations = self._normalize_outline_list(parsed.get("citations"), limit=12)
        risk_notes = self._normalize_outline_list(parsed.get("risk_notes"), limit=8)
        search_used = bool(parsed.get("search_used"))
        if not search_used:
            search_used = search_requested and bool(citations)
        return WorkflowSyncResult(
            project_id=project_id,
            background_markdown=background_markdown,
            must_confirm=must_confirm,
            citations=citations,
            risk_notes=risk_notes,
            search_requested=search_requested,
            search_used=search_used,
            provider=response.provider,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
        )

    def clear_suggested_nodes(self, project_id: str) -> int:
        if self.repository.get_project(project_id) is None:
            self._raise_project_missing(project_id)
        nodes = self.graph_service.list_nodes(project_id)
        suggested_ids: list[str] = []
        for node in nodes:
            metadata = node.metadata if isinstance(node.metadata, dict) else {}
            if metadata.get("ai_suggested"):
                suggested_ids.append(node.id)
        for node_id in suggested_ids:
            self.graph_service.delete_node(project_id, node_id)
        return len(suggested_ids)

    def get_task(self, task_id: str) -> Task:
        task = self.repository.get_task(task_id)
        if task is None:
            raise KeyError(tr("err.task_not_found", task_id=task_id))
        return task

    def list_tasks(
        self,
        project_id: str,
        *,
        status: TaskStatus | None = None,
        limit: int | None = None,
    ) -> list[Task]:
        if self.repository.get_project(project_id) is None:
            self._raise_project_missing(project_id)
        return self.repository.list_tasks(project_id, status=status, limit=limit)

    def cancel_task(self, task_id: str) -> Task:
        task = self.get_task(task_id)
        if task.status in {TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            return task
        task.status = TaskStatus.CANCELLED
        task.finished_at = utc_now()
        self.repository.update_task(task)
        return self.get_task(task_id)

    def _review(
        self,
        *,
        review_type: str,
        project_id: str,
        node_id: str,
        token_budget: int,
    ) -> ReviewReport:
        task = self._create_task(project_id, node_id, task_type=review_type)
        self._set_task_running(task)
        try:
            flow_state = self._run_workflow(
                task_type=review_type,
                project_id=project_id,
                node_id=node_id,
                token_budget=token_budget,
                workflow_mode="single",
            )
            response = cast(LLMResponse, flow_state["llm_response"])
            summary, score, issues = self._parse_review_output(response.content)
            revision = self._project_revision(project_id)
            self._set_task_success(task, revision=revision)
            return ReviewReport(
                task_id=task.id,
                project_id=project_id,
                node_id=node_id,
                review_type=review_type,
                summary=summary,
                score=score,
                issues=issues,
                revision=revision,
            )
        except Exception as exc:
            self._set_task_failed(task, exc)
            raise

    def _chapter_prompt(self, title: str, context: ContextPack, *, style_hint: str) -> str:
        style = style_hint.strip() or tr("ai.chapter.style_default")
        return tr(
            "ai.chapter.prompt",
            title=title,
            style=style,
            context=context.to_prompt(),
        )

    def _planner_prompt(self, title: str, context: ContextPack, *, style_hint: str) -> str:
        style = style_hint.strip() or tr("ai.chapter.style_default")
        return tr(
            "ai.chapter.planner_prompt",
            title=title,
            style=style,
            context=context.to_prompt(),
        )

    def _writer_prompt(self, title: str, context: ContextPack, *, plan: str) -> str:
        return tr(
            "ai.chapter.writer_prompt",
            title=title,
            plan=plan,
            context=context.to_prompt(),
        )

    def _chapter_reviewer_prompt(
        self,
        title: str,
        context: ContextPack,
        *,
        draft: str,
    ) -> str:
        return tr(
            "ai.chapter.reviewer_prompt",
            title=title,
            draft=draft,
            context=context.to_prompt(),
        )

    def _synthesizer_prompt(
        self,
        title: str,
        *,
        draft: str,
        review_feedback: str,
    ) -> str:
        return tr(
            "ai.chapter.synthesizer_prompt",
            title=title,
            draft=draft,
            review_feedback=review_feedback,
        )

    def _branch_prompt(self, title: str, context: ContextPack, *, n: int) -> str:
        return tr(
            "ai.branch.prompt",
            title=title,
            count=n,
            context=context.to_prompt(),
        )

    def _review_prompt(self, review_type: str, title: str, context: ContextPack) -> str:
        target_key = "ai.review.target_lore" if review_type == "review_lore" else "ai.review.target_logic"
        return tr(
            "ai.review.prompt",
            title=title,
            target=tr(target_key),
            context=context.to_prompt(),
        )

    def _chat_global_prompt(self, project_id: str, message: str, *, route: str) -> str:
        nodes = self.graph_service.list_nodes(project_id)
        edges = self.graph_service.list_edges(project_id)
        node_lines: list[str] = []
        for index, node in enumerate(nodes[:18], start=1):
            node_lines.append(
                f"{index}. {node.title} ({node.id}) type={node.type.value}, status={node.status.value}"
            )
        edge_lines: list[str] = []
        for index, edge in enumerate(edges[:24], start=1):
            edge_lines.append(
                f"{index}. {edge.source_id} -> {edge.target_id} label={edge.label or '-'}"
            )
        return tr(
            "ai.chat.global_prompt",
            route=route,
            user_message=message,
            node_count=len(nodes),
            edge_count=len(edges),
            nodes="\n".join(node_lines) if node_lines else "-",
            edges="\n".join(edge_lines) if edge_lines else "-",
        )

    def _chat_planner_prompt(self, title: str, context: ContextPack, user_message: str) -> str:
        return tr(
            "ai.chat.planner_prompt",
            title=title,
            request=user_message,
            context=context.to_prompt(),
        )

    def _outline_guide_prompt(
        self,
        project_id: str,
        *,
        goal: str,
        sync_context: str,
        specify: str,
        clarify_answers: str,
        plan_notes: str,
        constraints: str,
        tone: str,
    ) -> str:
        project = self.repository.get_project(project_id)
        project_title = project.title if project is not None else project_id
        snapshot = self._project_snapshot_prompt(project_id)
        return tr(
            "ai.outline.guide_prompt",
            project_title=project_title,
            goal=goal,
            sync_context=sync_context or "-",
            specify=specify or "-",
            clarify_answers=clarify_answers or "-",
            plan_notes=plan_notes or "-",
            constraints=constraints or "-",
            tone=tone or "-",
            snapshot=snapshot,
        )

    def _workflow_clarify_prompt(
        self,
        project_id: str,
        *,
        goal: str,
        sync_context: str,
        specify: str,
        constraints: str,
        tone: str,
    ) -> str:
        project = self.repository.get_project(project_id)
        project_title = project.title if project is not None else project_id
        snapshot = self._project_snapshot_prompt(project_id)
        return tr(
            "ai.workflow.clarify_prompt",
            project_title=project_title,
            goal=goal,
            sync_context=sync_context or "-",
            specify=specify or "-",
            constraints=constraints or "-",
            tone=tone or "-",
            snapshot=snapshot,
        )

    def _workflow_sync_prompt(
        self,
        project_id: str,
        *,
        goal: str,
        sync_context: str,
        mode: str,
        constraints: str,
        tone: str,
        search_requested: bool,
    ) -> str:
        project = self.repository.get_project(project_id)
        project_title = project.title if project is not None else project_id
        snapshot = self._project_snapshot_prompt(project_id)
        return tr(
            "ai.workflow.sync_prompt",
            project_title=project_title,
            goal=goal,
            mode=mode or "-",
            sync_context=sync_context or "-",
            constraints=constraints or "-",
            tone=tone or "-",
            search_requested="true" if search_requested else "false",
            snapshot=snapshot,
        )

    def _chat_writer_prompt(
        self,
        title: str,
        context: ContextPack,
        user_message: str,
        metadata: dict[str, Any],
    ) -> str:
        current_content = str(metadata.get("content", "")).strip() or tr("ai.chat.empty_fallback")
        current_outline = str(metadata.get("outline_markdown", "")).strip() or tr("ai.chat.empty_fallback")
        return tr(
            "ai.chat.writer_prompt",
            title=title,
            request=user_message,
            current_outline=current_outline,
            current_content=current_content,
            context=context.to_prompt(),
        )

    def _extract_chat_route(self, message: str) -> tuple[str, str]:
        text = str(message or "").strip()
        if not text:
            return "", "auto"
        route = "auto"
        mapping = {
            "plan": "planner",
            "planner": "planner",
            "writer": "writer",
        }

        def _replace(match: re.Match[str]) -> str:
            nonlocal route
            token = match.group(1).strip().lower()
            mapped = mapping.get(token)
            if mapped is None:
                return match.group(0)
            route = mapped
            return " "

        cleaned = re.sub(r"(?<![A-Za-z0-9_])@([A-Za-z_]+)\b", _replace, text)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned, route

    def _is_planner_scope_violation(self, message: str) -> bool:
        lowered = str(message or "").strip().lower()
        if not lowered:
            return False
        explicit_other_agent_calls = [
            "@writer",
            "@review",
            "@reviewer",
            "@synth",
            "@synthesizer",
            "@lore",
            "@logic",
        ]
        if any(marker in lowered for marker in explicit_other_agent_calls):
            return True

        plan_markers = [
            "@plan",
            "@planner",
            "plan",
            "planner",
            "outline",
            "beat",
            "branch",
            "route",
            "scene",
            "plot",
            "分支",
            "路线",
            "走向",
            "大纲",
            "细纲",
            "节拍",
            "场景",
            "剧情",
            "计划",
            "规划",
            "提纲",
            "梗概",
            "ビート",
            "分岐",
            "アウトライン",
            "プロット",
            "シーン",
            "構成",
        ]
        writer_markers = [
            "writer",
            "rewrite",
            "revise",
            "draft",
            "write full",
            "expand into prose",
            "continue writing",
            "polish",
            "copyedit",
            "正文",
            "改写",
            "润色",
            "扩写",
            "续写",
            "写成",
            "本文",
            "章节正文",
            "ライター",
            "改稿",
            "本文を書",
            "執筆",
            "推敲",
        ]
        review_markers = [
            "review",
            "proofread",
            "consistency check",
            "lore review",
            "logic review",
            "审查",
            "校对",
            "逻辑审查",
            "设定审查",
            "レビュー",
            "校閲",
            "整合性チェック",
        ]
        asks_non_plan = any(marker in lowered for marker in writer_markers + review_markers)
        if not asks_non_plan:
            return False
        if any(marker in lowered for marker in plan_markers):
            return False
        return True

    def _project_snapshot_prompt(self, project_id: str, *, max_nodes: int = 18, max_edges: int = 30) -> str:
        nodes = self.graph_service.list_nodes(project_id)
        edges = self.graph_service.list_edges(project_id)
        node_lines: list[str] = []
        for node in nodes[:max_nodes]:
            storyline = str(node.storyline_id or "").strip() or "-"
            node_lines.append(f"- {node.id} | {node.title} | {node.type.value} | storyline={storyline}")
        edge_lines: list[str] = []
        for edge in edges[:max_edges]:
            label = str(edge.label or "").strip() or "-"
            edge_lines.append(f"- {edge.source_id} -> {edge.target_id} | {label}")
        return (
            f"node_count={len(nodes)}, edge_count={len(edges)}\n\n"
            f"[Nodes]\n{chr(10).join(node_lines) if node_lines else '-'}\n\n"
            f"[Edges]\n{chr(10).join(edge_lines) if edge_lines else '-'}"
        )

    def _parse_outline_guide_payload(self, text: str) -> dict[str, Any]:
        raw = str(text or "").strip()
        if not raw:
            return {}
        candidates: list[str] = []
        for match in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", raw, flags=re.IGNORECASE):
            candidates.append(match.group(1).strip())
        candidates.append(raw)
        brace_match = re.search(r"\{[\s\S]*\}", raw)
        if brace_match:
            candidates.append(brace_match.group(0).strip())
        for candidate in candidates:
            try:
                payload = json.loads(candidate)
            except Exception:
                continue
            if isinstance(payload, dict):
                return payload
        return {}

    def _normalize_outline_list(self, value: Any, *, limit: int) -> list[str]:
        if isinstance(value, list):
            result: list[str] = []
            for item in value:
                text = str(item).strip()
                if text:
                    result.append(text)
                if len(result) >= limit:
                    break
            return result
        if isinstance(value, str):
            lines = [line.strip("- ").strip() for line in value.splitlines() if line.strip()]
            return lines[:limit]
        return []

    def _parse_question_lines(self, text: str, *, limit: int) -> list[str]:
        result: list[str] = []
        for line in str(text or "").splitlines():
            cleaned = re.sub(r"^\s*(?:[-*]|\d+[.)、])\s*", "", line).strip()
            if not cleaned:
                continue
            if "?" not in cleaned and "？" not in cleaned:
                continue
            result.append(cleaned)
            if len(result) >= limit:
                break
        return result

    def _parse_workflow_sync_payload(self, text: str) -> dict[str, Any]:
        parsed = self._parse_outline_guide_payload(text)
        if parsed:
            return parsed
        raw = str(text or "").strip()
        if not raw:
            return {}
        return {
            "background_markdown": raw,
            "must_confirm": [],
            "citations": [],
            "risk_notes": [],
            "search_used": False,
        }

    def _create_suggested_nodes(
        self,
        project_id: str,
        *,
        source_node: Any,
        options: list[BranchOption],
    ) -> list[str]:
        created_ids: list[str] = []
        source_x = float(getattr(source_node, "pos_x", 0.0))
        source_y = float(getattr(source_node, "pos_y", 0.0))
        now_iso = utc_now().isoformat()
        for index, option in enumerate(options):
            metadata = {
                "ai_suggested": True,
                "ai_suggested_from": source_node.id,
                "ai_suggested_at": now_iso,
                "summary": option.description,
                "content": option.description,
            }
            node = self.graph_service.add_node(
                project_id,
                NodeCreate(
                    title=option.title[:200],
                    type=NodeType.BRANCH,
                    status=getattr(source_node, "status"),
                    storyline_id=getattr(source_node, "storyline_id"),
                    pos_x=source_x + 280 + index * 240,
                    pos_y=source_y + (index - 1) * 150,
                    metadata=metadata,
                ),
            )
            self.graph_service.add_edge(
                project_id,
                source_node.id,
                node.id,
                label=tr("ai.chat.suggested_edge_label"),
            )
            created_ids.append(node.id)
        return created_ids

    def _generate(
        self,
        *,
        task_type: str,
        prompt: str,
        platform_config: dict[str, Any],
        llm_route: dict[str, Any] | None = None,
    ) -> LLMResponse:
        merged_platform_config = self._default_platform_config.copy()
        adapter = self.llm_adapter
        if llm_route:
            route_defaults = llm_route.get("platform_config")
            if isinstance(route_defaults, dict):
                merged_platform_config.update(route_defaults)
            route_provider = str(llm_route.get("provider", "")).strip()
            if route_provider:
                adapter = self._adapter_for_provider(route_provider)
        merged_platform_config.update(platform_config)
        request = LLMRequest(
            task_type=task_type,
            system_prompt=tr("ai.system_prompt"),
            messages=[LLMMessage(role="user", content=prompt)],
            platform_config=merged_platform_config,
        )
        response = adapter.generate(request)
        if not response.ok:
            code = response.error_code or "generic"
            detail = response.error_message or tr("ai.error.llm_request_failed")
            raise RuntimeError(tr("ai.error.llm_request_failed_with_code", code=code, detail=detail))
        return response

    def _build_single_workflow(self):
        graph = StateGraph(WorkflowState)
        graph.add_node("context", self._wf_context_node)
        graph.add_node("prompt", self._wf_prompt_node)
        graph.add_node("llm", self._wf_llm_node)
        graph.set_entry_point("context")
        graph.add_edge("context", "prompt")
        graph.add_edge("prompt", "llm")
        graph.add_edge("llm", END)
        return graph.compile()

    def _build_chapter_multi_workflow(self):
        graph = StateGraph(WorkflowState)
        graph.add_node("context", self._wf_context_node)
        graph.add_node("planner_prompt", self._wf_planner_prompt_node)
        graph.add_node("planner_llm", self._wf_planner_llm_node)
        graph.add_node("writer_prompt", self._wf_writer_prompt_node)
        graph.add_node("writer_llm", self._wf_writer_llm_node)
        graph.add_node("reviewer_prompt", self._wf_reviewer_prompt_node)
        graph.add_node("reviewer_llm", self._wf_reviewer_llm_node)
        graph.add_node("synthesizer_prompt", self._wf_synthesizer_prompt_node)
        graph.add_node("synthesizer_llm", self._wf_synthesizer_llm_node)
        graph.set_entry_point("context")
        graph.add_edge("context", "planner_prompt")
        graph.add_edge("planner_prompt", "planner_llm")
        graph.add_edge("planner_llm", "writer_prompt")
        graph.add_edge("writer_prompt", "writer_llm")
        graph.add_edge("writer_llm", "reviewer_prompt")
        graph.add_edge("reviewer_prompt", "reviewer_llm")
        graph.add_edge("reviewer_llm", "synthesizer_prompt")
        graph.add_edge("synthesizer_prompt", "synthesizer_llm")
        graph.add_edge("synthesizer_llm", END)
        return graph.compile()

    def _run_workflow(
        self,
        *,
        task_type: str,
        project_id: str,
        node_id: str,
        token_budget: int,
        style_hint: str = "",
        branch_count: int = 3,
        workflow_mode: str = "single",
    ) -> WorkflowState:
        payload: WorkflowState = {
            "task_type": task_type,
            "project_id": project_id,
            "node_id": node_id,
            "token_budget": token_budget,
            "style_hint": style_hint,
            "branch_count": branch_count,
            "workflow_mode": workflow_mode,
        }
        workflow = self._single_workflow
        if task_type == "generate_chapter" and workflow_mode == "multi_agent":
            workflow = self._chapter_multi_workflow
        result = workflow.invoke(payload)
        return cast(WorkflowState, result)

    def _wf_context_node(self, state: WorkflowState) -> WorkflowState:
        project_id = state["project_id"]
        node_id = state["node_id"]
        token_budget = int(state.get("token_budget", 2200))
        self._ensure_project_valid(project_id)
        node = self.graph_service.get_node(project_id, node_id)
        context = self.context_service.build_context(
            project_id,
            node_id,
            token_budget=token_budget,
        )
        return {
            "node": node,
            "context_pack": context,
            "llm_route": self._resolve_node_llm_route(node),
        }

    def _wf_prompt_node(self, state: WorkflowState) -> WorkflowState:
        task_type = state["task_type"]
        node = state["node"]
        context = state["context_pack"]
        if task_type == "generate_chapter":
            prompt = self._chapter_prompt(
                node.title,
                context,
                style_hint=str(state.get("style_hint", "")),
            )
        elif task_type == "generate_branches":
            prompt = self._branch_prompt(
                node.title,
                context,
                n=int(state.get("branch_count", 3)),
            )
        elif task_type in {"review_lore", "review_logic"}:
            prompt = self._review_prompt(task_type, node.title, context)
        else:
            raise ValueError(tr("ai.workflow.unsupported_task_type", task_type=task_type))
        return {"prompt": prompt}

    def _wf_llm_node(self, state: WorkflowState) -> WorkflowState:
        task_type = state["task_type"]
        prompt = state["prompt"]
        token_budget = int(state.get("token_budget", 2200))
        platform_config = {"token_budget": token_budget}
        if task_type == "generate_branches":
            platform_config["branch_count"] = int(state.get("branch_count", 3))
        response = self._generate(
            task_type=task_type,
            prompt=prompt,
            platform_config=platform_config,
            llm_route=cast(dict[str, Any] | None, state.get("llm_route")),
        )
        return {"llm_response": response}

    def _wf_planner_prompt_node(self, state: WorkflowState) -> WorkflowState:
        node = state["node"]
        context = state["context_pack"]
        prompt = self._planner_prompt(
            node.title,
            context,
            style_hint=str(state.get("style_hint", "")),
        )
        return {"planner_prompt": prompt}

    def _wf_planner_llm_node(self, state: WorkflowState) -> WorkflowState:
        token_budget = int(state.get("token_budget", 2200))
        response = self._generate(
            task_type="chapter_plan",
            prompt=state["planner_prompt"],
            platform_config={"token_budget": max(400, token_budget // 2)},
            llm_route=cast(dict[str, Any] | None, state.get("llm_route")),
        )
        return {
            "planner_response": response,
            "agent_trace": self._append_agent_trace(state, "planner", response.content),
        }

    def _wf_writer_prompt_node(self, state: WorkflowState) -> WorkflowState:
        node = state["node"]
        context = state["context_pack"]
        planner_response = cast(LLMResponse, state["planner_response"])
        prompt = self._writer_prompt(node.title, context, plan=planner_response.content)
        return {"writer_prompt": prompt}

    def _wf_writer_llm_node(self, state: WorkflowState) -> WorkflowState:
        token_budget = int(state.get("token_budget", 2200))
        response = self._generate(
            task_type="chapter_write",
            prompt=state["writer_prompt"],
            platform_config={"token_budget": token_budget},
            llm_route=cast(dict[str, Any] | None, state.get("llm_route")),
        )
        return {
            "writer_response": response,
            "agent_trace": self._append_agent_trace(state, "writer", response.content),
        }

    def _wf_reviewer_prompt_node(self, state: WorkflowState) -> WorkflowState:
        node = state["node"]
        context = state["context_pack"]
        writer_response = cast(LLMResponse, state["writer_response"])
        prompt = self._chapter_reviewer_prompt(
            node.title,
            context,
            draft=writer_response.content,
        )
        return {"reviewer_prompt": prompt}

    def _wf_reviewer_llm_node(self, state: WorkflowState) -> WorkflowState:
        token_budget = int(state.get("token_budget", 2200))
        response = self._generate(
            task_type="chapter_review",
            prompt=state["reviewer_prompt"],
            platform_config={"token_budget": max(400, token_budget // 2)},
            llm_route=cast(dict[str, Any] | None, state.get("llm_route")),
        )
        return {
            "reviewer_response": response,
            "agent_trace": self._append_agent_trace(state, "reviewer", response.content),
        }

    def _wf_synthesizer_prompt_node(self, state: WorkflowState) -> WorkflowState:
        node = state["node"]
        writer_response = cast(LLMResponse, state["writer_response"])
        reviewer_response = cast(LLMResponse, state["reviewer_response"])
        prompt = self._synthesizer_prompt(
            node.title,
            draft=writer_response.content,
            review_feedback=reviewer_response.content,
        )
        return {"synthesizer_prompt": prompt}

    def _wf_synthesizer_llm_node(self, state: WorkflowState) -> WorkflowState:
        token_budget = int(state.get("token_budget", 2200))
        response = self._generate(
            task_type="chapter_synthesize",
            prompt=state["synthesizer_prompt"],
            platform_config={"token_budget": token_budget},
            llm_route=cast(dict[str, Any] | None, state.get("llm_route")),
        )
        return {
            "llm_response": response,
            "agent_trace": self._append_agent_trace(state, "synthesizer", response.content),
        }

    def _adapter_for_provider(self, provider: str):
        normalized = str(provider).strip().lower()
        cached = self._adapter_cache.get(normalized)
        if cached is not None:
            return cached
        adapter = create_llm_adapter(normalized, platform_config={})
        self._adapter_cache[normalized] = adapter
        return adapter

    def _resolve_node_llm_route(self, node: Any) -> dict[str, Any]:
        metadata = getattr(node, "metadata", {})
        if not isinstance(metadata, dict):
            return {}
        raw_preset = metadata.get("agent_preset")
        preset_tag = str(raw_preset).strip() if raw_preset is not None else ""
        if not preset_tag:
            return {}
        preset = self._llm_presets.get(preset_tag)
        if preset is None:
            return {}
        platform_config = preset_to_platform_config(preset)
        return {
            "provider": "llmrequester",
            "preset_tag": preset.tag,
            "preset_name": preset.name,
            "platform_config": platform_config,
        }

    def _normalize_workflow_mode(self, workflow_mode: str) -> str:
        normalized = str(workflow_mode).strip().lower().replace("-", "_")
        if not normalized:
            return "multi_agent"
        if normalized in {"single", "single_agent"}:
            return "single"
        if normalized in {"multi", "multi_agent", "multiagent"}:
            return "multi_agent"
        raise ValueError(tr("ai.workflow.mode_invalid"))

    def _append_agent_trace(
        self,
        state: WorkflowState,
        agent_name: str,
        content: str,
    ) -> dict[str, str]:
        trace = {
            str(key): str(value)
            for key, value in cast(dict[str, str], state.get("agent_trace", {})).items()
        }
        trace[agent_name] = self._truncate_trace(content)
        return trace

    def _truncate_trace(self, content: str, *, max_len: int = 800) -> str:
        compact = " ".join(content.strip().split())
        if len(compact) <= max_len:
            return compact
        return f"{compact[: max_len - 3]}..."

    def _parse_branch_options(self, content: str, *, count: int) -> list[BranchOption]:
        parsed_payload = self._parse_branch_options_payload(content)
        if parsed_payload:
            parsed_options: list[BranchOption] = []
            for item in parsed_payload[:count]:
                title = str(item.get("title", "")).strip() or f"Branch {len(parsed_options) + 1}"
                description = str(
                    item.get("description", "")
                    or item.get("summary", "")
                    or item.get("outline", "")
                ).strip()
                outline_steps = self._normalize_outline_list(
                    item.get("outline_steps")
                    or item.get("beats")
                    or item.get("next_steps")
                    or item.get("future_steps"),
                    limit=8,
                )
                if not description and outline_steps:
                    description = " / ".join(outline_steps[:2])
                if not description:
                    description = tr("ai.branch.option_fallback", index=len(parsed_options) + 1)
                parsed_options.append(
                    BranchOption(
                        title=title,
                        description=description,
                        outline_steps=outline_steps,
                        sentiment=self._normalize_sentiment(item.get("sentiment")),
                    )
                )
            while len(parsed_options) < count:
                index = len(parsed_options) + 1
                parsed_options.append(
                    BranchOption(
                        title=f"Branch {index}",
                        description=tr("ai.branch.option_fallback", index=index),
                        outline_steps=[],
                        sentiment="neutral",
                    )
                )
            return parsed_options

        options: list[BranchOption] = []
        for line in content.splitlines():
            text = line.strip()
            if not text:
                continue
            if text.startswith("-"):
                text = text[1:].strip()
            parts = text.split(":", 1)
            if len(parts) == 2:
                title = parts[0].strip() or f"Branch {len(options) + 1}"
                desc = parts[1].strip() or "No description"
            else:
                title = f"Branch {len(options) + 1}"
                desc = text
            options.append(BranchOption(title=title, description=desc, outline_steps=[], sentiment="neutral"))
            if len(options) >= count:
                break
        while len(options) < count:
            index = len(options) + 1
            options.append(
                BranchOption(
                    title=f"Branch {index}",
                    description=tr("ai.branch.option_fallback", index=index),
                    outline_steps=[],
                    sentiment="neutral",
                )
            )
        return options

    def _parse_branch_options_payload(self, content: str) -> list[dict[str, Any]]:
        raw = str(content or "").strip()
        if not raw:
            return []
        candidates = [raw]
        bracket_match = re.search(r"\[[\s\S]*\]", raw)
        if bracket_match:
            candidates.append(bracket_match.group(0).strip())
        brace_match = re.search(r"\{[\s\S]*\}", raw)
        if brace_match:
            candidates.append(brace_match.group(0).strip())
        for candidate in candidates:
            try:
                payload = json.loads(candidate)
            except Exception:
                continue
            if isinstance(payload, list):
                return [item for item in payload if isinstance(item, dict)]
            if isinstance(payload, dict):
                options = payload.get("options")
                if isinstance(options, list):
                    return [item for item in options if isinstance(item, dict)]
        return []

    def _normalize_sentiment(self, value: Any) -> str:
        raw = str(value or "").strip().lower()
        alias_map = {
            "conflict": "conflict",
            "high_pressure": "conflict",
            "pressure": "conflict",
            "combat": "conflict",
            "冲突": "conflict",
            "高压": "conflict",
            "対峙": "conflict",
            "衝突": "conflict",
            "calm": "calm",
            "memory": "calm",
            "flashback": "calm",
            "平缓": "calm",
            "回忆": "calm",
            "穏やか": "calm",
            "suspense": "suspense",
            "mystery": "suspense",
            "悬疑": "suspense",
            "疑云": "suspense",
            "サスペンス": "suspense",
            "twist": "twist",
            "turning": "twist",
            "转折": "twist",
            "反转": "twist",
            "転換": "twist",
            "neutral": "neutral",
            "中性": "neutral",
            "中立": "neutral",
        }
        return alias_map.get(raw, "neutral")

    def _parse_review_output(self, content: str) -> tuple[str, float, list[str]]:
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        score = 0.7
        issues: list[str] = []
        summary_lines: list[str] = []
        for line in lines:
            lower = line.lower()
            if lower.startswith("score:"):
                raw = line.split(":", 1)[1].strip()
                try:
                    score = float(raw)
                except ValueError:
                    pass
            elif line.startswith("-"):
                issues.append(line[1:].strip())
            else:
                summary_lines.append(line)
        summary = "\n".join(summary_lines) if summary_lines else tr("ai.review.summary_default")
        return summary, max(0.0, min(1.0, score)), issues

    def _create_task(self, project_id: str, node_id: str, *, task_type: str) -> Task:
        task = Task(
            id=generate_id("task"),
            project_id=project_id,
            node_id=node_id,
            task_type=task_type,
            status=TaskStatus.PENDING,
            revision=self._project_revision(project_id),
        )
        self.repository.create_task(task)
        return task

    def _set_task_running(self, task: Task) -> None:
        task.status = TaskStatus.RUNNING
        task.started_at = utc_now()
        task.error_code = None
        task.error_message = None
        self.repository.update_task(task)

    def _set_task_success(self, task: Task, *, revision: int) -> None:
        task.status = TaskStatus.SUCCESS
        task.finished_at = utc_now()
        task.revision = revision
        self.repository.update_task(task)

    def _set_task_failed(self, task: Task, exc: Exception) -> None:
        message = str(exc).strip() or exc.__class__.__name__
        code = self._extract_error_code(message)
        task.status = TaskStatus.FAILED
        task.error_code = code
        task.error_message = message
        task.finished_at = utc_now()
        task.revision = self._project_revision(task.project_id)
        self.repository.update_task(task)

    def _extract_error_code(self, message: str) -> str:
        text = message.lower()
        if "[auth]" in text or "unauthorized" in text:
            return "auth"
        if "rate_limit" in text or "429" in text:
            return "rate_limit"
        if "timeout" in text:
            return "timeout"
        if "network" in text or "connection" in text:
            return "network"
        if "server" in text:
            return "server"
        if "content" in text or "parse" in text:
            return "content"
        return "generic"

    def _project_revision(self, project_id: str) -> int:
        project = self.repository.get_project(project_id)
        if project is None:
            self._raise_project_missing(project_id)
        assert project is not None
        return project.active_revision

    def _ensure_project_valid(self, project_id: str) -> None:
        report = self.validation_service.validate_project(project_id)
        if report.errors:
            codes = ", ".join(sorted({issue.code for issue in report.errors}))
            raise ValueError(tr("err.project_validation_failed", codes=codes))

    def _raise_project_missing(self, project_id: str) -> NoReturn:
        raise KeyError(tr("err.project_not_found", project_id=project_id))
