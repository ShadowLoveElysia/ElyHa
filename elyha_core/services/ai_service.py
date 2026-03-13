"""AI generation/review orchestration with task tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import TYPE_CHECKING, Any, NoReturn, TypedDict, cast

from elyha_core.adapters.llm_adapter import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    create_llm_adapter,
)
from elyha_core.i18n import tr
from elyha_core.llm_presets import LLMPreset, preset_to_platform_config
from elyha_core.models.task import Task, TaskStatus
from elyha_core.services.context_assembler import (
    BuildInput,
    ContextAssembler,
    PromptBundle,
)
from elyha_core.services.context_service import ContextPack, ContextService
from elyha_core.services.graph_service import GraphService, NodeCreate
from elyha_core.services.prompt_template_service import PromptTemplateService
from elyha_core.services.validation_service import ValidationService
from elyha_core.models.node import NodeType
from elyha_core.storage.repository import SQLiteRepository
from elyha_core.utils.clock import utc_now
from elyha_core.utils.ids import generate_id
from elyha_core.utils.text_splitter import split_text_by_chars
from langgraph.graph import END, StateGraph

if TYPE_CHECKING:
    from elyha_core.services.state_service import StateService

_STRICT_JSON_FENCE_PATTERN = re.compile(
    r"^\s*```json\s*([\s\S]*?)\s*```\s*$",
    flags=re.IGNORECASE,
)


@dataclass(slots=True)
class BranchOption:
    title: str
    description: str
    outline_steps: list[str] = field(default_factory=list)
    sentiment: str = "neutral"
    plan_mode: str = "story_extend"


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
class ChapterDraftResult:
    task_id: str
    project_id: str
    node_id: str
    content: str
    prompt_tokens: int
    completion_tokens: int
    provider: str
    workflow_mode: str = "single"
    agent_trace: dict[str, str] = field(default_factory=dict)
    node_metadata_patch: dict[str, Any] = field(default_factory=dict)
    prompt_version: str = ""
    diff_patch: dict[str, Any] = field(default_factory=dict)


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


@dataclass(slots=True)
class OutlineDetailNode:
    title: str
    outline_markdown: str
    summary: str = ""


@dataclass(slots=True)
class OutlineDetailNodesResult:
    project_id: str
    nodes: list[OutlineDetailNode] = field(default_factory=list)
    provider: str = "unknown"
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(slots=True)
class ClarificationQuestionResult:
    project_id: str
    clarification_id: str
    question_type: str
    question: str
    options: list[dict[str, str]] = field(default_factory=list)
    must_answer: bool = True
    timeout_sec: int = 120
    setting_proposal_status: str = "pending_confirmation"
    provider: str = "unknown"
    prompt_tokens: int = 0
    completion_tokens: int = 0


class WorkflowState(TypedDict, total=False):
    task_id: str
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
    prompt_bundle: PromptBundle
    planner_prompt: str
    planner_prompt_bundle: PromptBundle
    planner_response: LLMResponse
    writer_prompt: str
    writer_prompt_bundle: PromptBundle
    writer_response: LLMResponse
    reviewer_prompt: str
    reviewer_prompt_bundle: PromptBundle
    reviewer_response: LLMResponse
    synthesizer_prompt: str
    synthesizer_prompt_bundle: PromptBundle
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
        prompt_template_dir: str | None = None,
        state_service: StateService | None = None,
    ) -> None:
        self.repository = repository
        self.graph_service = graph_service
        self.context_service = context_service
        self.validation_service = validation_service
        self.state_service = state_service
        self.prompt_templates = PromptTemplateService(prompt_template_dir)
        self.context_assembler = ContextAssembler()
        self._default_platform_config = (llm_platform_config or {}).copy()
        self._llm_presets = dict(llm_presets or {})
        self._adapter_cache: dict[str, Any] = {}
        self.llm_adapter = create_llm_adapter(
            llm_provider,
            platform_config=self._default_platform_config,
        )
        self._single_workflow = self._build_single_workflow()
        self._chapter_multi_workflow = self._build_chapter_multi_workflow()

    def generate_chapter_draft(
        self,
        project_id: str,
        node_id: str,
        *,
        token_budget: int = 2200,
        style_hint: str = "",
        workflow_mode: str = "multi_agent",
    ) -> ChapterDraftResult:
        normalized_mode = self._normalize_workflow_mode(workflow_mode)
        task = self._create_task(project_id, node_id, task_type="generate_chapter")
        self._set_task_running(task)
        try:
            self._ensure_project_valid(project_id)
            target_node = self.graph_service.get_node(project_id, node_id)
            target_metadata = target_node.metadata if isinstance(target_node.metadata, dict) else {}
            if not str(target_metadata.get("outline_markdown", "")).strip():
                raise ValueError(tr("ai.chat.writer_outline_required"))
            flow_state = self._run_workflow(
                task_type="generate_chapter",
                project_id=project_id,
                node_id=node_id,
                token_budget=token_budget,
                style_hint=style_hint,
                workflow_mode=normalized_mode,
                task_id=task.id,
            )
            if self._is_task_cancelled(task.id):
                self._set_task_cancelled(task, message="task cancelled")
                raise RuntimeError("task cancelled")
            node = cast(Any, flow_state["node"])
            response = cast(LLMResponse, flow_state["llm_response"])
            agent_trace = cast(dict[str, str], flow_state.get("agent_trace", {}))
            route = cast(dict[str, Any], flow_state.get("llm_route", {}))
            final_bundle_key = (
                "synthesizer_prompt_bundle" if normalized_mode == "multi_agent" else "prompt_bundle"
            )
            final_bundle = cast(PromptBundle | None, flow_state.get(final_bundle_key))
            agent_bundles: dict[str, PromptBundle] = {}
            if normalized_mode == "multi_agent":
                for key, agent_name in (
                    ("planner_prompt_bundle", "planner"),
                    ("writer_prompt_bundle", "writer"),
                    ("reviewer_prompt_bundle", "reviewer"),
                    ("synthesizer_prompt_bundle", "synthesizer"),
                ):
                    bundle = cast(PromptBundle | None, flow_state.get(key))
                    if bundle is None:
                        continue
                    agent_bundles[agent_name] = bundle
            content = response.content.strip()
            if not content:
                raise RuntimeError(tr("ai.error.empty_response"))
            node_base_metadata = node.metadata if isinstance(getattr(node, "metadata", {}), dict) else {}
            metadata_patch = self._build_chapter_metadata_patch(
                node_metadata=node_base_metadata,
                content=content,
                workflow_mode=normalized_mode,
                agent_trace=agent_trace,
                route=route,
                final_bundle=final_bundle,
                agent_bundles=agent_bundles,
            )
            self._set_task_success(task, revision=self._project_revision(project_id))
            return ChapterDraftResult(
                task_id=task.id,
                project_id=project_id,
                node_id=node_id,
                content=content,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                provider=response.provider,
                workflow_mode=normalized_mode,
                agent_trace=agent_trace,
                node_metadata_patch=metadata_patch,
                prompt_version=str(metadata_patch.get("ai_prompt_version", "")),
            )
        except Exception as exc:
            if self._is_task_cancelled(task.id):
                self._set_task_cancelled(task, message="task cancelled")
            else:
                self._set_task_failed(task, exc)
            raise

    def generate_chapter_correction_draft(
        self,
        project_id: str,
        node_id: str,
        *,
        user_correction: str,
        base_content: str = "",
        token_budget: int = 2200,
    ) -> ChapterDraftResult:
        correction_text = str(user_correction or "").strip()
        if not correction_text:
            raise ValueError("user_correction cannot be empty")
        task = self._create_task(project_id, node_id, task_type="generate_chapter_correction_draft")
        self._set_task_running(task)
        try:
            self._ensure_project_valid(project_id)
            node = self.graph_service.get_node(project_id, node_id)
            context = self.context_service.build_context(
                project_id,
                node_id,
                token_budget=max(400, int(token_budget)),
            )
            prompt, bundle = self._chapter_correction_prompt(
                project_id,
                node,
                context,
                user_correction=correction_text,
                base_content=base_content,
                token_budget=max(400, int(token_budget)),
            )
            response = self._generate(
                task_type="chapter_correction",
                prompt=prompt,
                platform_config={"token_budget": max(400, int(token_budget))},
                llm_route=self._resolve_node_llm_route(node),
                project_id=project_id,
            )
            strict = self._strict_json_fence_output_enabled(project_id)
            parsed_correction = self._parse_correction_diff_payload(
                response.content,
                strict_json_fence=strict,
            )
            content = str(parsed_correction.get("revised_content") or "").strip()
            if not content:
                raise RuntimeError(tr("ai.error.empty_response"))
            diff_patch = parsed_correction.get("diff_patch")
            normalized_diff_patch = diff_patch if isinstance(diff_patch, dict) else {}
            node_base_metadata = node.metadata if isinstance(getattr(node, "metadata", {}), dict) else {}
            agent_trace = {
                "correction": self._truncate_trace(content),
                "correction_diff": self._truncate_trace(
                    json.dumps(normalized_diff_patch, ensure_ascii=False) if normalized_diff_patch else ""
                ),
            }
            metadata_patch = self._build_chapter_metadata_patch(
                node_metadata=node_base_metadata,
                content=content,
                workflow_mode="single",
                agent_trace=agent_trace,
                route={},
                final_bundle=bundle,
                agent_bundles={},
            )
            self._set_task_success(task, revision=self._project_revision(project_id))
            return ChapterDraftResult(
                task_id=task.id,
                project_id=project_id,
                node_id=node_id,
                content=content,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                provider=response.provider,
                workflow_mode="single",
                agent_trace=agent_trace,
                node_metadata_patch=metadata_patch,
                prompt_version=str(metadata_patch.get("ai_prompt_version", "")),
                diff_patch=normalized_diff_patch,
            )
        except Exception as exc:
            if self._is_task_cancelled(task.id):
                self._set_task_cancelled(task, message="task cancelled")
            else:
                self._set_task_failed(task, exc)
            raise

    def generate_chapter(
        self,
        project_id: str,
        node_id: str,
        *,
        token_budget: int = 2200,
        style_hint: str = "",
        workflow_mode: str = "multi_agent",
    ) -> GenerateResult:
        draft = self.generate_chapter_draft(
            project_id,
            node_id,
            token_budget=token_budget,
            style_hint=style_hint,
            workflow_mode=workflow_mode,
        )
        node = self.graph_service.get_node(project_id, node_id)
        node_metadata = node.metadata if isinstance(getattr(node, "metadata", {}), dict) else {}
        merged_metadata = {**node_metadata, **draft.node_metadata_patch}
        merged_metadata["content"] = draft.content
        merged_metadata["summary"] = draft.content[:200]
        self.graph_service.update_node(
            project_id,
            node_id,
            {
                "status": "generated",
                "metadata": merged_metadata,
            },
        )
        self.repository.replace_node_chunks(node_id, split_text_by_chars(draft.content))
        revision = self._project_revision(project_id)
        return GenerateResult(
            task_id=draft.task_id,
            project_id=project_id,
            node_id=node_id,
            content=draft.content,
            revision=revision,
            prompt_tokens=draft.prompt_tokens,
            completion_tokens=draft.completion_tokens,
            provider=draft.provider,
            workflow_mode=draft.workflow_mode,
            agent_trace=draft.agent_trace,
        )

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
                task_id=task.id,
            )
            if self._is_task_cancelled(task.id):
                self._set_task_cancelled(task, message="task cancelled")
                raise RuntimeError("task cancelled")
            response = cast(LLMResponse, flow_state["llm_response"])
            options = self._parse_branch_options(
                response.content,
                count=n,
                strict_json_fence=self._strict_json_fence_output_enabled(project_id),
            )
            self._set_task_success(task, revision=self._project_revision(project_id))
            return options
        except Exception as exc:
            if self._is_task_cancelled(task.id):
                self._set_task_cancelled(task, message="task cancelled")
            else:
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
            response = self._generate(
                task_type="chat_global_" + route,
                prompt=self._chat_global_prompt(project_id, cleaned_message, route=route),
                platform_config={"token_budget": token_budget},
                project_id=project_id,
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
            planner_prompt, _planner_bundle = self._chat_planner_prompt(
                project_id,
                node,
                context,
                cleaned_message,
                token_budget=max(600, token_budget // 2),
            )
            response = self._generate(
                task_type="chat_plan",
                prompt=planner_prompt,
                platform_config={"token_budget": max(600, token_budget // 2), "branch_count": 3},
                llm_route=llm_route,
                project_id=project_id,
            )
            options = self._parse_branch_options(
                response.content,
                count=3,
                strict_json_fence=self._strict_json_fence_output_enabled(project_id),
            )
            self._clear_suggested_nodes_for_source(project_id, source_node_id=node.id)
            suggested_node_ids = self._create_suggested_nodes(
                project_id,
                source_node=node,
                options=options,
            )
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
                suggested_node_ids=suggested_node_ids,
                suggested_options=[
                    {
                        "title": option.title,
                        "description": option.description,
                        "outline_steps": "\n".join(option.outline_steps),
                        "suggested_node_id": (
                            suggested_node_ids[index]
                            if index < len(suggested_node_ids)
                            else ""
                        ),
                        "next_1": option.outline_steps[0] if len(option.outline_steps) > 0 else "",
                        "next_2": option.outline_steps[1] if len(option.outline_steps) > 1 else "",
                        "sentiment": option.sentiment,
                        "plan_mode": option.plan_mode,
                    }
                    for index, option in enumerate(options)
                ],
                revision=self._project_revision(project_id),
            )

        if route == "writer":
            current_outline = str(node_metadata.get("outline_markdown", "")).strip()
            if not current_outline:
                return ChatAssistResult(
                    project_id=project_id,
                    node_id=node.id,
                    route="guard",
                    reply=tr("ai.chat.writer_outline_required"),
                    review_bypassed=False,
                    revision=self._project_revision(project_id),
                )

        writer_prompt, writer_bundle = self._chat_writer_prompt(
            project_id,
            node,
            context,
            cleaned_message,
            node_metadata,
            token_budget=token_budget,
        )
        response = self._generate(
            task_type="chat_writer",
            prompt=writer_prompt,
            platform_config={"token_budget": token_budget},
            llm_route=llm_route,
            project_id=project_id,
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
        patched_metadata["ai_prompt_version"] = writer_bundle.prompt_version
        patched_metadata["ai_prompt_sections"] = writer_bundle.sections_payload()
        patched_metadata["ai_prompt_dropped_sections"] = writer_bundle.dropped_sections
        patched_metadata["ai_prompt_constraints"] = writer_bundle.key_constraints
        patched_metadata["ai_last_prompt"] = writer_bundle.final_prompt
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
            project_id=project_id,
        )
        parsed = self._parse_outline_guide_payload(
            response.content,
            strict_json_fence=self._strict_json_fence_output_enabled(project_id),
        )
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

    def guide_outline_detail_nodes(
        self,
        project_id: str,
        *,
        outline_markdown: str = "",
        chapter_beats: list[str] | None = None,
        user_request: str = "",
        mode: str = "",
        token_budget: int = 1800,
        max_nodes: int = 8,
    ) -> OutlineDetailNodesResult:
        if self.repository.get_project(project_id) is None:
            self._raise_project_missing(project_id)
        clean_outline = str(outline_markdown or "").strip()
        safe_max_nodes = max(3, min(12, int(max_nodes)))
        normalized_beats = self._normalize_outline_list(chapter_beats or [], limit=safe_max_nodes)
        if not clean_outline and not normalized_beats:
            raise ValueError(tr("ai.chat.writer_outline_required"))
        response = self._generate(
            task_type="outline_detail_nodes",
            prompt=self._outline_detail_nodes_prompt(
                project_id,
                outline_markdown=clean_outline,
                chapter_beats=normalized_beats,
                user_request=str(user_request or "").strip(),
                mode=str(mode or "").strip(),
                max_nodes=safe_max_nodes,
            ),
            platform_config={"token_budget": max(900, token_budget)},
            project_id=project_id,
        )
        parsed_nodes = self._parse_outline_detail_nodes_payload(
            response.content,
            limit=safe_max_nodes,
            strict_json_fence=self._strict_json_fence_output_enabled(project_id),
        )
        if not parsed_nodes:
            fallback_lines = normalized_beats or self._normalize_outline_list(clean_outline, limit=safe_max_nodes)
            parsed_nodes = self._build_outline_detail_nodes_from_lines(fallback_lines, limit=safe_max_nodes)
        if not parsed_nodes:
            fallback_lines = normalized_beats or self._normalize_outline_list(clean_outline, limit=3)
            parsed_nodes = self._build_outline_detail_nodes_from_lines(fallback_lines, limit=max(1, min(3, safe_max_nodes)))
        return OutlineDetailNodesResult(
            project_id=project_id,
            nodes=parsed_nodes[:safe_max_nodes],
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
            project_id=project_id,
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
            project_id=project_id,
        )
        parsed = self._parse_workflow_sync_payload(
            response.content,
            strict_json_fence=self._strict_json_fence_output_enabled(project_id),
        )
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

    def generate_clarification_question(
        self,
        project_id: str,
        *,
        node_id: str | None = None,
        context: str = "",
        token_budget: int = 900,
    ) -> ClarificationQuestionResult:
        if self.repository.get_project(project_id) is None:
            self._raise_project_missing(project_id)
        node = self.graph_service.get_node(project_id, node_id) if node_id else None
        node_title = node.title if node is not None else ""
        prompt = self._clarification_question_prompt(
            project_id,
            node_title=node_title,
            context=str(context or "").strip(),
        )
        llm_route = self._resolve_node_llm_route(node) if node is not None else None
        response = self._generate(
            task_type="clarification_question",
            prompt=prompt,
            platform_config={"token_budget": max(500, token_budget)},
            llm_route=llm_route,
            project_id=project_id,
        )
        strict = self._strict_json_fence_output_enabled(project_id)
        parsed = self._parse_clarification_question_payload(
            response.content,
            strict_json_fence=strict,
        )
        return ClarificationQuestionResult(
            project_id=project_id,
            clarification_id=str(parsed.get("clarification_id") or generate_id("clq")),
            question_type=str(parsed.get("question_type") or "other"),
            question=str(parsed.get("question") or "").strip() or tr("ai.chat.empty_fallback"),
            options=cast(list[dict[str, str]], parsed.get("options", [])),
            must_answer=bool(parsed.get("must_answer", True)),
            timeout_sec=max(15, int(parsed.get("timeout_sec", 120))),
            setting_proposal_status="pending_confirmation",
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

    def _clear_suggested_nodes_for_source(self, project_id: str, *, source_node_id: str) -> int:
        nodes = self.graph_service.list_nodes(project_id)
        suggested_ids: list[str] = []
        for node in nodes:
            metadata = node.metadata if isinstance(node.metadata, dict) else {}
            if not metadata.get("ai_suggested"):
                continue
            if str(metadata.get("ai_suggested_from", "")).strip() != source_node_id:
                continue
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
        self._set_task_cancelled(task, message="task cancelled")
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
                task_id=task.id,
            )
            if self._is_task_cancelled(task.id):
                self._set_task_cancelled(task, message="task cancelled")
                raise RuntimeError("task cancelled")
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
            if self._is_task_cancelled(task.id):
                self._set_task_cancelled(task, message="task cancelled")
            else:
                self._set_task_failed(task, exc)
            raise

    def _render_prompt_template(
        self,
        template_name: str,
        *,
        fallback_key: str,
        **kwargs: object,
    ) -> str:
        fallback = tr(fallback_key)
        return self.prompt_templates.render(
            template_name,
            fallback=fallback,
            **kwargs,
        )

    def _append_strict_json_fence_contract(self, prompt: str, *, enabled: bool) -> str:
        if not enabled:
            return prompt
        contract = (
            "\n\n[OutputContract]\n"
            "strict_json_fence_output=true\n"
            "Response must be and only be a single ```json ... ``` fenced block.\n"
        )
        return f"{prompt.rstrip()}{contract}"

    def _project_settings(self, project_id: str):
        project = self.repository.get_project(project_id)
        if project is None:
            self._raise_project_missing(project_id)
        return project.settings

    def _strict_json_fence_output_enabled(self, project_id: str) -> bool:
        settings = self._project_settings(project_id)
        return bool(getattr(settings, "strict_json_fence_output", False))

    def _build_node_context_payload(
        self,
        *,
        node: Any,
        task_type: str,
        task_instruction: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = node.metadata if isinstance(getattr(node, "metadata", {}), dict) else {}
        payload: dict[str, Any] = {
            "task_type": task_type,
            "task_instruction": task_instruction,
            "node": {
                "id": str(getattr(node, "id", "")),
                "title": str(getattr(node, "title", "")),
                "type": str(getattr(getattr(node, "type", None), "value", "")),
                "status": str(getattr(getattr(node, "status", None), "value", "")),
                "storyline_id": str(getattr(node, "storyline_id", "") or ""),
            },
            "outline_markdown": str(metadata.get("outline_markdown", "")).strip(),
            "goal": str(metadata.get("goal", "")).strip(),
            "chapter_position": str(metadata.get("chapter_position", "")).strip(),
            "forced_progression_points": metadata.get("forced_progression_points", []),
        }
        if extra:
            payload["task_input"] = extra
        return payload

    def _node_content_text(self, node: Any) -> str:
        node_id = str(getattr(node, "id", "")).strip()
        if node_id:
            chunks = self.repository.list_node_chunks(node_id)
            if chunks:
                return "\n".join(chunks).strip()
        metadata = node.metadata if isinstance(getattr(node, "metadata", {}), dict) else {}
        for key in ("content", "summary", "notes"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _collect_working_memory(self, project_id: str, node: Any) -> str:
        nodes = self.graph_service.list_nodes(project_id)
        current_storyline_id = str(getattr(node, "storyline_id", "") or "").strip()
        eligible_status = {"generated", "reviewed", "approved"}
        ranked: list[Any] = []
        for item in nodes:
            if current_storyline_id and str(getattr(item, "storyline_id", "") or "").strip() != current_storyline_id:
                continue
            status = str(getattr(getattr(item, "status", None), "value", "")).strip().lower()
            if status and status not in eligible_status:
                continue
            if self._node_content_text(item):
                ranked.append(item)
        ranked.sort(key=lambda item: (item.updated_at, item.id), reverse=True)
        picked = ranked[:6]
        blocks: list[str] = []
        for index, item in enumerate(reversed(picked), start=1):
            content = self._node_content_text(item)
            if not content:
                continue
            blocks.append(
                f"[{index}] {item.title} ({item.type.value}, {item.status.value})\n{content}"
            )
        return "\n\n".join(blocks).strip()

    def _build_rag_context(self, context: ContextPack) -> str:
        lines: list[str] = []
        for segment in context.segments:
            if segment.kind not in {"constraint", "pinned", "ancestor", "recent"}:
                continue
            text = str(segment.text).strip()
            if not text:
                continue
            lines.append(f"[{segment.kind}] {text}")
        return "\n".join(lines).strip()

    def _metadata_id_list(self, metadata: dict[str, Any], *keys: str) -> list[str]:
        values: list[str] = []
        for key in keys:
            raw = metadata.get(key)
            if isinstance(raw, list):
                for item in raw:
                    text = str(item).strip()
                    if text:
                        values.append(text)
            elif isinstance(raw, str):
                for part in raw.split(","):
                    text = part.strip()
                    if text:
                        values.append(text)
        deduped: list[str] = []
        seen: set[str] = set()
        for item in values:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return deduped

    def _metadata_relationship_pairs(self, metadata: dict[str, Any]) -> list[tuple[str, str]]:
        raw = metadata.get("relationship_pairs")
        pairs: list[tuple[str, str]] = []
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    subject = str(item.get("subject") or item.get("a") or "").strip()
                    obj = str(item.get("object") or item.get("b") or "").strip()
                    if subject and obj:
                        pairs.append((subject, obj))
                else:
                    text = str(item).strip()
                    if not text:
                        continue
                    for sep in ("|", ",", "->", "=>"):
                        if sep in text:
                            left, right = text.split(sep, 1)
                            subject = left.strip()
                            obj = right.strip()
                            if subject and obj:
                                pairs.append((subject, obj))
                            break
        return pairs

    def _collect_world_state_snapshot(self, project_id: str, node: Any) -> dict[str, Any]:
        if self.state_service is None:
            return {}
        metadata = node.metadata if isinstance(getattr(node, "metadata", {}), dict) else {}
        character_ids = self._metadata_id_list(metadata, "character_ids", "state_character_ids")
        item_ids = self._metadata_id_list(metadata, "item_ids", "state_item_ids")
        world_variable_keys = self._metadata_id_list(metadata, "world_variable_keys")
        relationship_pairs = self._metadata_relationship_pairs(metadata)
        payload = self.state_service.build_prompt_state_payload(
            project_id,
            character_ids=character_ids or None,
            item_ids=item_ids or None,
            relationship_pairs=relationship_pairs or None,
            world_variable_keys=world_variable_keys or None,
        )
        conflicts = self.state_service.list_state_conflicts(project_id, unresolved_only=True)
        return {
            "state_snapshot": payload,
            "state_conflicts": conflicts[:30],
        }

    def _build_prompt_bundle(
        self,
        *,
        project_id: str,
        node: Any,
        context: ContextPack,
        token_budget: int,
        task_mode: str,
        task_type: str,
        task_instruction: str,
        user_correction: str = "",
        extra_node_context: dict[str, Any] | None = None,
    ) -> PromptBundle:
        settings = self._project_settings(project_id)
        system_spec_parts: list[str] = []
        style = str(getattr(settings, "system_prompt_style", "")).strip()
        forbidden = str(getattr(settings, "system_prompt_forbidden", "")).strip()
        notes = str(getattr(settings, "system_prompt_notes", "")).strip()
        if style:
            system_spec_parts.append(f"[WritingStyle]\n{style}")
        if forbidden:
            system_spec_parts.append(f"[Forbidden]\n{forbidden}")
        if notes:
            system_spec_parts.append(f"[Notes]\n{notes}")
        system_spec = "\n\n".join(system_spec_parts).strip()

        node_context_payload = self._build_node_context_payload(
            node=node,
            task_type=task_type,
            task_instruction=task_instruction,
            extra=extra_node_context,
        )
        working_memory = self._collect_working_memory(project_id, node)
        recent_anchor = ""
        node_metadata = node.metadata if isinstance(getattr(node, "metadata", {}), dict) else {}
        summary = str(node_metadata.get("summary", "")).strip()
        if summary:
            recent_anchor = summary[:500]
        bundle_input = BuildInput(
            project_id=project_id,
            node_id=str(node.id),
            task_mode=task_mode,
            token_budget=max(200, int(token_budget)),
            system_spec=system_spec,
            global_directives=str(getattr(settings, "global_directives", "") or ""),
            world_state_snapshot=self._collect_world_state_snapshot(project_id, node),
            node_context=node_context_payload,
            working_memory=working_memory,
            rag_context=self._build_rag_context(context),
            user_correction=user_correction,
            recent_anchor=recent_anchor,
            context_soft_min_chars=int(getattr(settings, "context_soft_min_chars", 3000)),
            context_soft_max_chars=int(getattr(settings, "context_soft_max_chars", 5000)),
            context_sentence_safe_expand_chars=int(
                getattr(settings, "context_sentence_safe_expand_chars", 500)
            ),
            context_soft_max_tokens=int(getattr(settings, "context_soft_max_tokens", 1600)),
            strict_json_fence_output=bool(getattr(settings, "strict_json_fence_output", False)),
        )
        if task_mode == "correct":
            return self.context_assembler.build_correction_prompt(bundle_input)
        return self.context_assembler.build_generation_prompt(bundle_input)

    def _chapter_prompt(
        self,
        project_id: str,
        node: Any,
        context: ContextPack,
        *,
        style_hint: str,
        token_budget: int,
    ) -> tuple[str, PromptBundle]:
        style = style_hint.strip() or tr("ai.chapter.style_default")
        instruction = self._render_prompt_template(
            "chapter_prompt",
            fallback_key="ai.chapter.prompt",
            title=node.title,
            style=style,
            context="(see structured context sections below)",
        )
        bundle = self._build_prompt_bundle(
            project_id=project_id,
            node=node,
            context=context,
            token_budget=token_budget,
            task_mode="generate",
            task_type="generate_chapter",
            task_instruction=instruction,
            extra_node_context={"style_hint": style},
        )
        return bundle.final_prompt, bundle

    def _chapter_correction_prompt(
        self,
        project_id: str,
        node: Any,
        context: ContextPack,
        *,
        user_correction: str,
        base_content: str,
        token_budget: int,
    ) -> tuple[str, PromptBundle]:
        clean_correction = str(user_correction or "").strip()
        clean_base_content = str(base_content or "").strip()
        if not clean_base_content:
            node_metadata = node.metadata if isinstance(getattr(node, "metadata", {}), dict) else {}
            clean_base_content = str(node_metadata.get("content", "")).strip()
        template_text = self.prompt_templates.load("chapter_correction_prompt")
        if not template_text:
            raise RuntimeError("missing prompt template: data/prompt/chapter_correction_prompt.txt")
        instruction = self.prompt_templates.render_text(
            template_text,
            title=node.title,
            correction=clean_correction,
            base_content=clean_base_content or "(empty)",
            context="(see structured context sections below)",
        )
        bundle = self._build_prompt_bundle(
            project_id=project_id,
            node=node,
            context=context,
            token_budget=token_budget,
            task_mode="correct",
            task_type="chapter_correction",
            task_instruction=instruction,
            user_correction=clean_correction,
            extra_node_context={
                "base_content_excerpt": clean_base_content[:1500],
                "correction": clean_correction,
            },
        )
        return bundle.final_prompt, bundle

    def _build_chapter_metadata_patch(
        self,
        *,
        node_metadata: dict[str, Any],
        content: str,
        workflow_mode: str,
        agent_trace: dict[str, str],
        route: dict[str, Any],
        final_bundle: PromptBundle | None,
        agent_bundles: dict[str, PromptBundle],
    ) -> dict[str, Any]:
        return {
            "content": content,
            "summary": content[:200],
            "last_generation_at": utc_now().isoformat(),
            "ai_chapter_done_signal": self._extract_chapter_done_signal_from_content(content),
            "ai_workflow_mode": workflow_mode,
            "ai_agent_trace": agent_trace,
            "ai_agent_preset": str(route.get("preset_tag", "")),
            "ai_agent_name": str(route.get("preset_name", "")),
            "ai_review_passed_once": bool(node_metadata.get("ai_review_passed_once"))
            or workflow_mode == "multi_agent",
            "ai_prompt_version": final_bundle.prompt_version if final_bundle is not None else "",
            "ai_prompt_sections": final_bundle.sections_payload() if final_bundle is not None else [],
            "ai_prompt_dropped_sections": final_bundle.dropped_sections if final_bundle is not None else [],
            "ai_prompt_constraints": final_bundle.key_constraints if final_bundle is not None else [],
            "ai_last_prompt": final_bundle.final_prompt if final_bundle is not None else "",
            "ai_prompt_sections_by_agent": {
                name: bundle.sections_payload() for name, bundle in agent_bundles.items()
            },
            "ai_last_prompt_by_agent": {
                name: bundle.final_prompt for name, bundle in agent_bundles.items()
            },
        }

    def _extract_chapter_done_signal_from_content(self, content: str) -> bool:
        text = str(content or "")
        if not text:
            return False
        if re.search(r"\bchapter_done_signal\b\s*[:=]\s*(true|1|yes)\b", text, flags=re.IGNORECASE):
            return True
        if re.search(r"章节完成信号\s*[:：]\s*(true|1|是)", text, flags=re.IGNORECASE):
            return True
        return False

    def _planner_prompt(
        self,
        project_id: str,
        node: Any,
        context: ContextPack,
        *,
        style_hint: str,
        token_budget: int,
    ) -> tuple[str, PromptBundle]:
        style = style_hint.strip() or tr("ai.chapter.style_default")
        instruction = self._render_prompt_template(
            "chapter_planner_prompt",
            fallback_key="ai.chapter.planner_prompt",
            title=node.title,
            style=style,
            context="(see structured context sections below)",
        )
        bundle = self._build_prompt_bundle(
            project_id=project_id,
            node=node,
            context=context,
            token_budget=token_budget,
            task_mode="generate",
            task_type="chapter_plan",
            task_instruction=instruction,
            extra_node_context={"style_hint": style},
        )
        return bundle.final_prompt, bundle

    def _writer_prompt(
        self,
        project_id: str,
        node: Any,
        context: ContextPack,
        *,
        plan: str,
        token_budget: int,
    ) -> tuple[str, PromptBundle]:
        instruction = self._render_prompt_template(
            "chapter_writer_prompt",
            fallback_key="ai.chapter.writer_prompt",
            title=node.title,
            plan=plan,
            context="(see structured context sections below)",
        )
        bundle = self._build_prompt_bundle(
            project_id=project_id,
            node=node,
            context=context,
            token_budget=token_budget,
            task_mode="generate",
            task_type="chapter_write",
            task_instruction=instruction,
            extra_node_context={"planner_output": plan},
        )
        return bundle.final_prompt, bundle

    def _chapter_reviewer_prompt(
        self,
        project_id: str,
        node: Any,
        context: ContextPack,
        *,
        draft: str,
        token_budget: int,
    ) -> tuple[str, PromptBundle]:
        instruction = self._render_prompt_template(
            "chapter_reviewer_prompt",
            fallback_key="ai.chapter.reviewer_prompt",
            title=node.title,
            draft=draft,
            context="(see structured context sections below)",
        )
        bundle = self._build_prompt_bundle(
            project_id=project_id,
            node=node,
            context=context,
            token_budget=token_budget,
            task_mode="generate",
            task_type="chapter_review",
            task_instruction=instruction,
            extra_node_context={"draft_excerpt": draft[:800]},
        )
        return bundle.final_prompt, bundle

    def _synthesizer_prompt(
        self,
        project_id: str,
        node: Any,
        context: ContextPack,
        *,
        draft: str,
        review_feedback: str,
        token_budget: int,
    ) -> tuple[str, PromptBundle]:
        instruction = self._render_prompt_template(
            "chapter_synthesizer_prompt",
            fallback_key="ai.chapter.synthesizer_prompt",
            title=node.title,
            draft=draft,
            review_feedback=review_feedback,
        )
        bundle = self._build_prompt_bundle(
            project_id=project_id,
            node=node,
            context=context,
            token_budget=token_budget,
            task_mode="generate",
            task_type="chapter_synthesize",
            task_instruction=instruction,
            extra_node_context={
                "draft_excerpt": draft[:800],
                "review_feedback_excerpt": review_feedback[:800],
            },
        )
        return bundle.final_prompt, bundle

    def _branch_prompt(
        self,
        project_id: str,
        node: Any,
        context: ContextPack,
        *,
        n: int,
        token_budget: int,
    ) -> tuple[str, PromptBundle]:
        instruction = self._render_prompt_template(
            "branch_prompt",
            fallback_key="ai.branch.prompt",
            title=node.title,
            count=n,
            context="(see structured context sections below)",
        )
        bundle = self._build_prompt_bundle(
            project_id=project_id,
            node=node,
            context=context,
            token_budget=token_budget,
            task_mode="generate",
            task_type="generate_branches",
            task_instruction=instruction,
            extra_node_context={"branch_count": n},
        )
        return bundle.final_prompt, bundle

    def _review_prompt(
        self,
        project_id: str,
        review_type: str,
        node: Any,
        context: ContextPack,
        *,
        token_budget: int,
    ) -> tuple[str, PromptBundle]:
        target_key = "ai.review.target_lore" if review_type == "review_lore" else "ai.review.target_logic"
        instruction = self._render_prompt_template(
            "review_prompt",
            fallback_key="ai.review.prompt",
            title=node.title,
            target=tr(target_key),
            context="(see structured context sections below)",
        )
        bundle = self._build_prompt_bundle(
            project_id=project_id,
            node=node,
            context=context,
            token_budget=token_budget,
            task_mode="generate",
            task_type=review_type,
            task_instruction=instruction,
        )
        return bundle.final_prompt, bundle

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
        return self._render_prompt_template(
            "chat_global_prompt",
            fallback_key="ai.chat.global_prompt",
            route=route,
            user_message=message,
            node_count=len(nodes),
            edge_count=len(edges),
            nodes="\n".join(node_lines) if node_lines else "-",
            edges="\n".join(edge_lines) if edge_lines else "-",
        )

    def _chat_planner_prompt(
        self,
        project_id: str,
        node: Any,
        context: ContextPack,
        user_message: str,
        *,
        token_budget: int,
    ) -> tuple[str, PromptBundle]:
        instruction = self._render_prompt_template(
            "chat_planner_prompt",
            fallback_key="ai.chat.planner_prompt",
            title=node.title,
            request=user_message,
            context="(see structured context sections below)",
        )
        bundle = self._build_prompt_bundle(
            project_id=project_id,
            node=node,
            context=context,
            token_budget=token_budget,
            task_mode="generate",
            task_type="chat_plan",
            task_instruction=instruction,
            extra_node_context={"user_request": user_message},
        )
        return bundle.final_prompt, bundle

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
        prompt = self._render_prompt_template(
            "outline_guide_prompt",
            fallback_key="ai.outline.guide_prompt",
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
        return self._append_strict_json_fence_contract(
            prompt,
            enabled=self._strict_json_fence_output_enabled(project_id),
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
        return self._render_prompt_template(
            "workflow_clarify_prompt",
            fallback_key="ai.workflow.clarify_prompt",
            project_title=project_title,
            goal=goal,
            sync_context=sync_context or "-",
            specify=specify or "-",
            constraints=constraints or "-",
            tone=tone or "-",
            snapshot=snapshot,
        )

    def _clarification_question_prompt(
        self,
        project_id: str,
        *,
        node_title: str,
        context: str,
    ) -> str:
        project = self.repository.get_project(project_id)
        project_title = project.title if project is not None else project_id
        template = self.prompt_templates.load("clarification_question_prompt")
        if template:
            prompt = self.prompt_templates.render_text(
                template,
                project_title=project_title,
                node_title=node_title or "-",
                context=context or "-",
            )
        else:
            prompt = (
                "Generate one clarification question in JSON.\n"
                "Output format:\n"
                "{\n"
                '  "clarification_id":"...","question_type":"plot_direction|route_choice|character_style|world_rule|pace|other",\n'
                '  "question":"...",\n'
                '  "options":[{"value":"...","label":"...","reason":"..."}],\n'
                '  "must_answer":true,\n'
                '  "timeout_sec":120\n'
                "}\n"
                "Rules:\n"
                "- options must include value=other.\n"
                "- question should be specific and answerable.\n"
                f"[Project]\n{project_title}\n\n"
                f"[Node]\n{node_title or '-'}\n\n"
                f"[Context]\n{context or '-'}"
            )
        return self._append_strict_json_fence_contract(
            prompt,
            enabled=self._strict_json_fence_output_enabled(project_id),
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
        prompt = self._render_prompt_template(
            "workflow_sync_prompt",
            fallback_key="ai.workflow.sync_prompt",
            project_title=project_title,
            goal=goal,
            mode=mode or "-",
            sync_context=sync_context or "-",
            constraints=constraints or "-",
            tone=tone or "-",
            search_requested="true" if search_requested else "false",
            snapshot=snapshot,
        )
        return self._append_strict_json_fence_contract(
            prompt,
            enabled=self._strict_json_fence_output_enabled(project_id),
        )

    def _outline_detail_nodes_prompt(
        self,
        project_id: str,
        *,
        outline_markdown: str,
        chapter_beats: list[str],
        user_request: str,
        mode: str,
        max_nodes: int,
    ) -> str:
        project = self.repository.get_project(project_id)
        project_title = project.title if project is not None else project_id
        snapshot = self._project_snapshot_prompt(project_id)
        beats_block = "\n".join(f"- {item}" for item in chapter_beats) if chapter_beats else "-"
        prompt = self._render_prompt_template(
            "outline_detail_nodes_prompt",
            fallback_key="ai.outline.detail_nodes_prompt",
            project_title=project_title,
            mode=mode or "-",
            outline_markdown=outline_markdown or "-",
            chapter_beats=beats_block,
            user_request=user_request or "-",
            max_nodes=max_nodes,
            snapshot=snapshot,
        )
        return self._append_strict_json_fence_contract(
            prompt,
            enabled=self._strict_json_fence_output_enabled(project_id),
        )

    def _chat_writer_prompt(
        self,
        project_id: str,
        node: Any,
        context: ContextPack,
        user_message: str,
        metadata: dict[str, Any],
        *,
        token_budget: int,
    ) -> tuple[str, PromptBundle]:
        current_content = str(metadata.get("content", "")).strip() or tr("ai.chat.empty_fallback")
        current_outline = str(metadata.get("outline_markdown", "")).strip() or tr("ai.chat.empty_fallback")
        instruction = self._render_prompt_template(
            "chat_writer_prompt",
            fallback_key="ai.chat.writer_prompt",
            title=node.title,
            request=user_message,
            current_outline=current_outline,
            current_content=current_content,
            context="(see structured context sections below)",
        )
        bundle = self._build_prompt_bundle(
            project_id=project_id,
            node=node,
            context=context,
            token_budget=token_budget,
            task_mode="correct",
            task_type="chat_writer",
            task_instruction=instruction,
            user_correction=user_message,
            extra_node_context={
                "current_outline": current_outline,
                "current_content_excerpt": current_content[:1000],
            },
        )
        return bundle.final_prompt, bundle

    def _build_outline_detail_nodes_from_lines(
        self,
        lines: list[str],
        *,
        limit: int,
    ) -> list[OutlineDetailNode]:
        result: list[OutlineDetailNode] = []
        for index, line in enumerate(lines[:limit], start=1):
            cleaned = str(line).strip()
            if not cleaned:
                continue
            title = tr("ai.outline.detail_nodes_default_title", index=index)
            outline_text = cleaned if "\n" in cleaned else f"- {cleaned}"
            result.append(
                OutlineDetailNode(
                    title=title,
                    outline_markdown=outline_text,
                    summary=cleaned[:140],
                )
            )
        return result

    def _normalize_outline_markdown_text(self, value: Any) -> str:
        if isinstance(value, list):
            rows = [str(item).strip() for item in value if str(item).strip()]
            if not rows:
                return ""
            return "\n".join(f"- {item}" for item in rows)
        text = str(value or "").strip()
        if not text:
            return ""
        if "\n" in text:
            return text
        return f"- {text}"

    def _parse_outline_detail_nodes_payload(
        self,
        text: str,
        *,
        limit: int,
        strict_json_fence: bool = False,
    ) -> list[OutlineDetailNode]:
        parsed = self._parse_outline_guide_payload(text, strict_json_fence=strict_json_fence)
        candidates: list[dict[str, Any]] = []
        if isinstance(parsed, dict):
            raw_nodes = (
                parsed.get("nodes")
                or parsed.get("node_outlines")
                or parsed.get("items")
                or parsed.get("options")
            )
            if isinstance(raw_nodes, list):
                candidates = [item for item in raw_nodes if isinstance(item, dict)]
        elif isinstance(parsed, list):
            candidates = [item for item in parsed if isinstance(item, dict)]
        result: list[OutlineDetailNode] = []
        for item in candidates[:limit]:
            outline = self._normalize_outline_markdown_text(
                item.get("outline_markdown")
                or item.get("outline")
                or item.get("detail_outline")
                or item.get("outline_steps")
                or item.get("steps")
                or item.get("beats")
            )
            if not outline:
                continue
            summary = str(item.get("summary") or item.get("description") or "").strip()
            title = str(item.get("title") or item.get("name") or "").strip()
            if not title:
                title = (summary or outline.replace("\n", " ").strip("- ").strip())[:32]
            if not title:
                title = tr("ai.outline.detail_nodes_default_title", index=len(result) + 1)
            if not summary:
                summary = outline.replace("\n", " ").strip("- ").strip()[:140]
            result.append(
                OutlineDetailNode(
                    title=title,
                    outline_markdown=outline,
                    summary=summary,
                )
            )
        return result

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

    def _parse_strict_json_fence_payload(self, text: str) -> Any:
        raw = str(text or "")
        match = _STRICT_JSON_FENCE_PATTERN.fullmatch(raw)
        if not match:
            raise RuntimeError("strict_json_fence_output=true requires a single ```json``` fenced payload")
        payload_text = match.group(1).strip()
        if not payload_text:
            raise RuntimeError("strict_json_fence_output=true received empty JSON fence payload")
        try:
            return json.loads(payload_text)
        except Exception as exc:
            raise RuntimeError("strict_json_fence_output=true received invalid JSON payload") from exc

    def _parse_outline_guide_payload(
        self,
        text: str,
        *,
        strict_json_fence: bool = False,
    ) -> dict[str, Any]:
        raw = str(text or "").strip()
        if not raw:
            return {}
        if strict_json_fence:
            payload = self._parse_strict_json_fence_payload(raw)
            if isinstance(payload, dict):
                return payload
            raise RuntimeError("strict_json_fence_output=true requires JSON object payload")
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

    def _parse_workflow_sync_payload(
        self,
        text: str,
        *,
        strict_json_fence: bool = False,
    ) -> dict[str, Any]:
        parsed = self._parse_outline_guide_payload(text, strict_json_fence=strict_json_fence)
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

    def _parse_clarification_question_payload(
        self,
        text: str,
        *,
        strict_json_fence: bool,
    ) -> dict[str, Any]:
        parsed = self._parse_outline_guide_payload(text, strict_json_fence=strict_json_fence)
        if not parsed:
            if strict_json_fence:
                raise RuntimeError("strict_json_fence_output=true requires clarification JSON fence")
            question = str(text or "").strip()
            return {
                "clarification_id": generate_id("clq"),
                "question_type": "other",
                "question": question or tr("ai.chat.empty_fallback"),
                "options": [
                    {"value": "other", "label": "其他", "reason": ""},
                ],
                "must_answer": True,
                "timeout_sec": 120,
            }

        normalized_type = str(parsed.get("question_type") or "other").strip()
        allowed_types = {
            "plot_direction",
            "route_choice",
            "character_style",
            "world_rule",
            "pace",
            "other",
        }
        if normalized_type not in allowed_types:
            normalized_type = "other"

        options: list[dict[str, str]] = []
        raw_options = parsed.get("options")
        if isinstance(raw_options, list):
            for item in raw_options:
                if not isinstance(item, dict):
                    continue
                value = str(item.get("value") or "").strip()
                label = str(item.get("label") or value).strip()
                reason = str(item.get("reason") or "").strip()
                if not value or not label:
                    continue
                options.append({"value": value, "label": label, "reason": reason})
        if not any(item.get("value") == "other" for item in options):
            options.append({"value": "other", "label": "其他", "reason": ""})
        if not options:
            options = [{"value": "other", "label": "其他", "reason": ""}]

        return {
            "clarification_id": str(parsed.get("clarification_id") or generate_id("clq")).strip(),
            "question_type": normalized_type,
            "question": str(parsed.get("question") or "").strip(),
            "options": options,
            "must_answer": bool(parsed.get("must_answer", True)),
            "timeout_sec": int(parsed.get("timeout_sec", 120) or 120),
        }

    def _parse_correction_diff_payload(
        self,
        text: str,
        *,
        strict_json_fence: bool,
    ) -> dict[str, Any]:
        raw = str(text or "").strip()
        if not raw:
            return {"revised_content": "", "diff_patch": {}}

        parsed = self._parse_outline_guide_payload(raw, strict_json_fence=strict_json_fence)
        if not parsed:
            if strict_json_fence:
                raise RuntimeError("strict_json_fence_output=true requires correction JSON fence payload")
            return {"revised_content": raw, "diff_patch": {}}

        revised_content = str(
            parsed.get("revised_content")
            or parsed.get("content")
            or parsed.get("full_text")
            or parsed.get("full_content")
            or ""
        ).strip()
        if not revised_content:
            if strict_json_fence:
                raise RuntimeError("strict_json_fence_output=true requires revised_content in correction payload")
            revised_content = raw

        diff_patch = parsed.get("diff_patch")
        if not isinstance(diff_patch, dict):
            diff_patch = {}
        raw_hunks = diff_patch.get("hunks")
        if isinstance(raw_hunks, list):
            normalized_hunks: list[dict[str, Any]] = []
            for item in raw_hunks:
                if not isinstance(item, dict):
                    continue
                op = str(item.get("op") or "").strip().lower()
                if op not in {"add", "delete", "replace"}:
                    continue
                try:
                    start_line = int(item.get("start_line") or 1)
                except (TypeError, ValueError):
                    start_line = 1
                try:
                    end_line = int(item.get("end_line") or max(0, start_line - 1))
                except (TypeError, ValueError):
                    end_line = max(0, start_line - 1)
                normalized_hunks.append(
                    {
                        "hunk_id": str(item.get("hunk_id") or generate_id("hunk")).strip(),
                        "op": op,
                        "start_line": max(1, start_line),
                        "end_line": max(0, end_line),
                        "old_text": str(item.get("old_text") or ""),
                        "new_text": str(item.get("new_text") or ""),
                        "reason": str(item.get("reason") or "").strip(),
                    }
                )
            diff_patch = {
                "diff_id": str(diff_patch.get("diff_id") or generate_id("diff")).strip(),
                "base_revision": int(diff_patch.get("base_revision") or 0),
                "base_content_hash": str(diff_patch.get("base_content_hash") or "").strip(),
                "hunks": normalized_hunks,
            }
        else:
            diff_patch = {}

        return {"revised_content": revised_content, "diff_patch": diff_patch}

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
                "outline_markdown": "\n".join(f"- {step}" for step in option.outline_steps)
                if option.outline_steps
                else "",
                "ai_suggested_sentiment": option.sentiment,
                "ai_suggested_plan_mode": option.plan_mode,
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
        project_id: str | None = None,
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
            system_prompt=self._build_system_prompt(project_id),
            messages=[LLMMessage(role="user", content=prompt)],
            platform_config=merged_platform_config,
        )
        response = adapter.generate(request)
        if not response.ok:
            code = response.error_code or "generic"
            detail = response.error_message or tr("ai.error.llm_request_failed")
            raise RuntimeError(tr("ai.error.llm_request_failed_with_code", code=code, detail=detail))
        return response

    def _build_system_prompt(self, project_id: str | None = None) -> str:
        base_prompt = (
            self.prompt_templates.load("system_prompt")
            or tr("ai.system_prompt")
        ).strip()
        if not project_id:
            return base_prompt
        project = self.repository.get_project(project_id)
        if project is None:
            return base_prompt
        settings = project.settings
        style = str(getattr(settings, "system_prompt_style", "")).strip()
        forbidden = str(getattr(settings, "system_prompt_forbidden", "")).strip()
        notes = str(getattr(settings, "system_prompt_notes", "")).strip()
        sections: list[str] = []
        if style:
            sections.append(f"[User Writing Style]\n{style}")
        if forbidden:
            sections.append(f"[Forbidden Content]\n{forbidden}")
        if notes:
            sections.append(f"[Additional Notes To Explain]\n{notes}")
        if not sections:
            return base_prompt
        return (
            f"{base_prompt}\n\n"
            "[User Constraints]\n"
            "The following constraints are from current project settings and should be followed.\n\n"
            + "\n\n".join(sections)
        )

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
        task_id: str | None = None,
    ) -> WorkflowState:
        payload: WorkflowState = {
            "task_id": task_id or "",
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
        self._ensure_task_not_cancelled(state)
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
        self._ensure_task_not_cancelled(state)
        task_type = state["task_type"]
        node = state["node"]
        context = state["context_pack"]
        project_id = str(state.get("project_id", ""))
        token_budget = int(state.get("token_budget", 2200))
        if task_type == "generate_chapter":
            prompt, bundle = self._chapter_prompt(
                project_id,
                node,
                context,
                style_hint=str(state.get("style_hint", "")),
                token_budget=token_budget,
            )
        elif task_type == "generate_branches":
            prompt, bundle = self._branch_prompt(
                project_id,
                node,
                context,
                n=int(state.get("branch_count", 3)),
                token_budget=token_budget,
            )
        elif task_type in {"review_lore", "review_logic"}:
            prompt, bundle = self._review_prompt(
                project_id,
                task_type,
                node,
                context,
                token_budget=token_budget,
            )
        else:
            raise ValueError(tr("ai.workflow.unsupported_task_type", task_type=task_type))
        return {"prompt": prompt, "prompt_bundle": bundle}

    def _wf_llm_node(self, state: WorkflowState) -> WorkflowState:
        self._ensure_task_not_cancelled(state)
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
            project_id=str(state.get("project_id", "")) or None,
        )
        return {"llm_response": response}

    def _wf_planner_prompt_node(self, state: WorkflowState) -> WorkflowState:
        self._ensure_task_not_cancelled(state)
        node = state["node"]
        context = state["context_pack"]
        prompt, bundle = self._planner_prompt(
            str(state.get("project_id", "")),
            node,
            context,
            style_hint=str(state.get("style_hint", "")),
            token_budget=max(400, int(state.get("token_budget", 2200)) // 2),
        )
        return {"planner_prompt": prompt, "planner_prompt_bundle": bundle}

    def _wf_planner_llm_node(self, state: WorkflowState) -> WorkflowState:
        self._ensure_task_not_cancelled(state)
        token_budget = int(state.get("token_budget", 2200))
        response = self._generate(
            task_type="chapter_plan",
            prompt=state["planner_prompt"],
            platform_config={"token_budget": max(400, token_budget // 2)},
            llm_route=cast(dict[str, Any] | None, state.get("llm_route")),
            project_id=str(state.get("project_id", "")) or None,
        )
        return {
            "planner_response": response,
            "agent_trace": self._append_agent_trace(state, "planner", response.content),
        }

    def _wf_writer_prompt_node(self, state: WorkflowState) -> WorkflowState:
        self._ensure_task_not_cancelled(state)
        node = state["node"]
        context = state["context_pack"]
        planner_response = cast(LLMResponse, state["planner_response"])
        prompt, bundle = self._writer_prompt(
            str(state.get("project_id", "")),
            node,
            context,
            plan=planner_response.content,
            token_budget=int(state.get("token_budget", 2200)),
        )
        return {"writer_prompt": prompt, "writer_prompt_bundle": bundle}

    def _wf_writer_llm_node(self, state: WorkflowState) -> WorkflowState:
        self._ensure_task_not_cancelled(state)
        token_budget = int(state.get("token_budget", 2200))
        response = self._generate(
            task_type="chapter_write",
            prompt=state["writer_prompt"],
            platform_config={"token_budget": token_budget},
            llm_route=cast(dict[str, Any] | None, state.get("llm_route")),
            project_id=str(state.get("project_id", "")) or None,
        )
        return {
            "writer_response": response,
            "agent_trace": self._append_agent_trace(state, "writer", response.content),
        }

    def _wf_reviewer_prompt_node(self, state: WorkflowState) -> WorkflowState:
        self._ensure_task_not_cancelled(state)
        node = state["node"]
        context = state["context_pack"]
        writer_response = cast(LLMResponse, state["writer_response"])
        prompt, bundle = self._chapter_reviewer_prompt(
            str(state.get("project_id", "")),
            node,
            context,
            draft=writer_response.content,
            token_budget=max(400, int(state.get("token_budget", 2200)) // 2),
        )
        return {"reviewer_prompt": prompt, "reviewer_prompt_bundle": bundle}

    def _wf_reviewer_llm_node(self, state: WorkflowState) -> WorkflowState:
        self._ensure_task_not_cancelled(state)
        token_budget = int(state.get("token_budget", 2200))
        response = self._generate(
            task_type="chapter_review",
            prompt=state["reviewer_prompt"],
            platform_config={"token_budget": max(400, token_budget // 2)},
            llm_route=cast(dict[str, Any] | None, state.get("llm_route")),
            project_id=str(state.get("project_id", "")) or None,
        )
        return {
            "reviewer_response": response,
            "agent_trace": self._append_agent_trace(state, "reviewer", response.content),
        }

    def _wf_synthesizer_prompt_node(self, state: WorkflowState) -> WorkflowState:
        self._ensure_task_not_cancelled(state)
        node = state["node"]
        context = state["context_pack"]
        writer_response = cast(LLMResponse, state["writer_response"])
        reviewer_response = cast(LLMResponse, state["reviewer_response"])
        prompt, bundle = self._synthesizer_prompt(
            str(state.get("project_id", "")),
            node,
            context,
            draft=writer_response.content,
            review_feedback=reviewer_response.content,
            token_budget=int(state.get("token_budget", 2200)),
        )
        return {"synthesizer_prompt": prompt, "synthesizer_prompt_bundle": bundle}

    def _wf_synthesizer_llm_node(self, state: WorkflowState) -> WorkflowState:
        self._ensure_task_not_cancelled(state)
        token_budget = int(state.get("token_budget", 2200))
        response = self._generate(
            task_type="chapter_synthesize",
            prompt=state["synthesizer_prompt"],
            platform_config={"token_budget": token_budget},
            llm_route=cast(dict[str, Any] | None, state.get("llm_route")),
            project_id=str(state.get("project_id", "")) or None,
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

    def _parse_branch_options(
        self,
        content: str,
        *,
        count: int,
        strict_json_fence: bool = False,
    ) -> list[BranchOption]:
        parsed_payload, parsed_mode = self._parse_branch_options_payload(
            content,
            strict_json_fence=strict_json_fence,
        )
        if parsed_payload:
            parsed_options: list[BranchOption] = []
            top_level_mode = self._normalize_plan_mode(parsed_mode or parsed_payload[0].get("plan_mode"))
            option_limit = 1 if top_level_mode == "outline_decompose" else max(1, count)
            for item in parsed_payload[:option_limit]:
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
                option_mode = self._normalize_plan_mode(item.get("plan_mode") or top_level_mode)
                parsed_options.append(
                    BranchOption(
                        title=title,
                        description=description,
                        outline_steps=outline_steps,
                        sentiment=self._normalize_sentiment(item.get("sentiment")),
                        plan_mode=option_mode,
                    )
                )
            min_options = 1 if top_level_mode == "outline_decompose" else max(1, count)
            while len(parsed_options) < min_options:
                index = len(parsed_options) + 1
                parsed_options.append(
                    BranchOption(
                        title=f"Branch {index}",
                        description=tr("ai.branch.option_fallback", index=index),
                        outline_steps=[],
                        sentiment="neutral",
                        plan_mode=top_level_mode,
                    )
                )
            return parsed_options

        if strict_json_fence:
            raise RuntimeError("strict_json_fence_output=true requires valid JSON fence payload")

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
            options.append(
                BranchOption(
                    title=title,
                    description=desc,
                    outline_steps=[],
                    sentiment="neutral",
                    plan_mode="story_extend",
                )
            )
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
                    plan_mode="story_extend",
                )
            )
        return options

    def _parse_branch_options_payload(
        self,
        content: str,
        *,
        strict_json_fence: bool = False,
    ) -> tuple[list[dict[str, Any]], str]:
        raw = str(content or "").strip()
        if not raw:
            return [], "story_extend"
        if strict_json_fence:
            payload = self._parse_strict_json_fence_payload(raw)
            if isinstance(payload, list):
                return [item for item in payload if isinstance(item, dict)], "story_extend"
            if isinstance(payload, dict):
                top_level_mode = self._normalize_plan_mode(payload.get("plan_mode"))
                options = payload.get("options")
                if isinstance(options, list):
                    return [item for item in options if isinstance(item, dict)], top_level_mode
                option = payload.get("option")
                if isinstance(option, dict):
                    return [option], top_level_mode
            raise RuntimeError("strict_json_fence_output=true requires JSON object/array payload")
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
                return [item for item in payload if isinstance(item, dict)], "story_extend"
            if isinstance(payload, dict):
                top_level_mode = self._normalize_plan_mode(payload.get("plan_mode"))
                options = payload.get("options")
                if isinstance(options, list):
                    return [item for item in options if isinstance(item, dict)], top_level_mode
                option = payload.get("option")
                if isinstance(option, dict):
                    return [option], top_level_mode
        return [], "story_extend"

    def _normalize_plan_mode(self, value: Any) -> str:
        raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        if raw == "outline_decompose":
            return "outline_decompose"
        if raw == "story_extend":
            return "story_extend"
        return "story_extend"

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

    def _set_task_cancelled(self, task: Task, *, message: str = "task cancelled") -> None:
        task.status = TaskStatus.CANCELLED
        task.error_code = "cancelled"
        task.error_message = message
        if task.started_at is None:
            task.started_at = utc_now()
        task.finished_at = utc_now()
        task.revision = self._project_revision(task.project_id)
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
        if "cancelled" in text or "canceled" in text:
            return "cancelled"
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

    def _ensure_task_not_cancelled(self, state: WorkflowState) -> None:
        task_id = str(state.get("task_id", "")).strip()
        if not task_id:
            return
        if self._is_task_cancelled(task_id):
            raise RuntimeError("task cancelled")

    def _is_task_cancelled(self, task_id: str) -> bool:
        task = self.repository.get_task(task_id)
        return task is not None and task.status == TaskStatus.CANCELLED

    def _ensure_project_valid(self, project_id: str) -> None:
        report = self.validation_service.validate_project(project_id)
        if report.errors:
            codes = ", ".join(sorted({issue.code for issue in report.errors}))
            raise ValueError(tr("err.project_validation_failed", codes=codes))

    def _raise_project_missing(self, project_id: str) -> NoReturn:
        raise KeyError(tr("err.project_not_found", project_id=project_id))
