"""Chapter generation/review methods for AIService."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import TYPE_CHECKING, Any, NoReturn, cast

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
from elyha_core.services.graph_service import GraphService
from elyha_core.services.prompt_template_service import PromptTemplateService
from elyha_core.services.readable_content_tool_service import ReadableContentToolService
from elyha_core.services.Tools import ToolService
from elyha_core.services.validation_service import ValidationService
from elyha_core.storage.repository import SQLiteRepository
from elyha_core.utils.clock import utc_now
from elyha_core.utils.ids import generate_id
from elyha_core.utils.text_splitter import split_text_by_chars
from langgraph.graph import END, StateGraph

from ..types import (
    BranchOption,
    ChapterDraftResult,
    ChatAssistResult,
    ClarificationQuestionResult,
    GenerateResult,
    OutlineDetailNode,
    OutlineDetailNodesResult,
    OutlineGuideResult,
    ReviewReport,
    WorkflowClarifyResult,
    WorkflowDocsDraftResult,
    WorkflowState,
    WorkflowSyncResult,
)

if TYPE_CHECKING:
    from elyha_core.services.setting_proposal_service import SettingProposalService
    from elyha_core.services.state_service import StateService


class AIServiceChapterGenerationMixin:
    def generate_chapter_draft(
        self,
        project_id: str,
        node_id: str,
        *,
        token_budget: int = 2200,
        style_hint: str = "",
        workflow_mode: str = "multi_agent",
        tool_thread_id: str = "",
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
                tool_thread_id=tool_thread_id,
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
            loop_rounds, loop_tool_calls = self._collect_flow_agent_loop_audits(
                flow_state,
                workflow_mode=normalized_mode,
            )
            loop_metrics, evidence_chunk_ids = self._collect_flow_agent_loop_meta(
                flow_state,
                workflow_mode=normalized_mode,
            )
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
                agent_loop_rounds=loop_rounds,
                agent_tool_calls=loop_tool_calls,
                agent_loop_metrics=loop_metrics,
                tool_evidence_chunk_ids=evidence_chunk_ids,
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
        tool_thread_id: str = "",
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
                platform_config={
                    "token_budget": max(400, int(token_budget)),
                    "tool_context_node_id": str(node_id),
                    "tool_thread_id": str(tool_thread_id or "").strip(),
                },
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
            loop_rounds, loop_tool_calls = self._extract_agent_loop_audits(
                response,
                default_task_type="chapter_correction",
                default_agent="correction",
            )
            loop_metrics, evidence_chunk_ids = self._extract_agent_loop_meta(response)
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
                agent_loop_rounds=loop_rounds,
                agent_tool_calls=loop_tool_calls,
                agent_loop_metrics=loop_metrics,
                tool_evidence_chunk_ids=evidence_chunk_ids,
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
        self._sync_state_after_llm_write(
            project_id=project_id,
            node_id=node_id,
            thread_id=draft.task_id,
            content=draft.content,
        )
        revision = self._project_revision(project_id)
        task = self.repository.get_task(draft.task_id)
        if task is not None and task.status == TaskStatus.SUCCESS and task.revision != revision:
            task.revision = revision
            self.repository.update_task(task)
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
