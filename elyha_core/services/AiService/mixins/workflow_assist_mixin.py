"""Workflow/chat assist methods for AIService."""

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


class AIServiceWorkflowAssistMixin:
    def chat_assist(
        self,
        project_id: str,
        *,
        message: str,
        node_id: str | None = None,
        thread_id: str | None = None,
        allow_node_write: bool = True,
        guide_mode: bool = False,
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
                route = (
                    "outline"
                    if self._should_route_to_outline(
                        message=cleaned_message,
                        node_metadata=node_metadata,
                    )
                    else "writer"
                )
        review_bypassed = node is not None and auto_review_passed and route == "writer"
        requested_thread_id = str(thread_id or "").strip()
        clean_thread_id = requested_thread_id or generate_id("chat")
        if requested_thread_id:
            existing_thread = self.repository.get_chat_thread(requested_thread_id)
            if existing_thread is not None:
                existing_project = str(existing_thread.get("project_id") or "").strip()
                if existing_project and existing_project != project_id:
                    clean_thread_id = generate_id("chat")
        self.repository.upsert_chat_thread(
            clean_thread_id,
            project_id=project_id,
            node_id=node.id if node is not None else "",
        )
        thread_history = self.repository.list_chat_messages(clean_thread_id, limit=16)
        history_block = self._format_chat_history_for_prompt(thread_history)
        workflow_docs_block = self._build_workflow_docs_prompt_context(project_id)
        chat_context = self._combine_chat_prompt_context(
            history_block=history_block,
            workflow_docs_block=workflow_docs_block,
        )
        self.repository.append_chat_message(
            clean_thread_id,
            role="user",
            content=cleaned_message,
        )
        prompt_user_message = cleaned_message
        if chat_context:
            prompt_user_message = f"{cleaned_message}\n\n{chat_context}"

        if node is None:
            if guide_mode:
                route = "planner"
                before_status = self._workflow_doc_status(project_id)
                response = self._generate(
                    task_type="chat_global_" + route,
                    prompt=self._chat_global_guide_prompt(
                        project_id,
                        prompt_user_message,
                        route=route,
                        missing_labels=cast(list[str], before_status.get("missing_labels", [])),
                    ),
                    platform_config={
                        "token_budget": token_budget,
                        "enable_tool_loop": True,
                        "write_document_enabled": True,
                        "write_document_required": False,
                        "allow_skip_document": True,
                        "node_tools_visible": False,
                        "node_tools_enabled": False,
                    },
                    project_id=project_id,
                )
                after_status = self._workflow_doc_status(project_id)
                guide_skip_document = self._extract_guide_skip_document_request(response.raw)
                content = response.content.strip() or tr("ai.chat.empty_fallback")
                after_missing_labels = cast(list[str], after_status.get("missing_labels", []))
                if bool(after_status.get("complete", False)):
                    completion_hint = "四份基础大纲已全部写入，可退出创作引导并进入节点创建。"
                    if completion_hint not in content:
                        content = f"{content}\n\n{completion_hint}" if content else completion_hint
                elif after_missing_labels:
                    before_missing_slots = cast(list[str], before_status.get("missing_slots", []))
                    after_missing_slots = cast(list[str], after_status.get("missing_slots", []))
                    if before_missing_slots == after_missing_slots:
                        missing_text = "、".join(after_missing_labels)
                        reminder = (
                            "当前仍在创作引导模式，尚未完成："
                            f"{missing_text}。请继续补充这些信息，我会写入对应文档。"
                        )
                        if reminder not in content:
                            content = f"{content}\n\n{reminder}" if content else reminder
                self.repository.append_chat_message(
                    clean_thread_id,
                    role="assistant",
                    content=content,
                )
                return ChatAssistResult(
                    project_id=project_id,
                    node_id=None,
                    thread_id=clean_thread_id,
                    route=route,
                    reply=content,
                    review_bypassed=False,
                    guide_skip_document=guide_skip_document,
                    revision=self._project_revision(project_id),
                )

            base_prompt = self._chat_global_prompt(
                project_id,
                prompt_user_message,
                route=route,
            )
            gate_prompt = self._append_global_tool_gate_contract(base_prompt)
            gate_platform_config: dict[str, Any] = {
                "token_budget": token_budget,
                "native_tools": self._build_global_tool_gate_specs(),
                "native_tool_choice": {"type": "auto"},
            }
            gate_response = self._generate(
                task_type="chat_global_" + route,
                prompt=gate_prompt,
                platform_config=gate_platform_config,
                project_id=project_id,
            )
            gate_parsed = self._parse_tool_loop_response(gate_response)
            gate_decision = self._extract_global_tool_gate_decision(
                cast(list[dict[str, Any]], gate_parsed.get("tool_calls", []))
            )
            response = gate_response
            if gate_decision["enable_tool_loop"]:
                loop_platform_config: dict[str, Any] = {
                    "token_budget": token_budget,
                    "enable_tool_loop": True,
                    "node_tools_visible": False,
                    "node_tools_enabled": False,
                }
                if gate_decision["write_document_enabled"]:
                    loop_platform_config["write_document_enabled"] = True
                response = self._generate(
                    task_type="chat_global_" + route,
                    prompt=base_prompt,
                    platform_config=loop_platform_config,
                    project_id=project_id,
                )
            content = response.content.strip() or tr("ai.chat.empty_fallback")
            self.repository.append_chat_message(
                clean_thread_id,
                role="assistant",
                content=content,
            )
            return ChatAssistResult(
                project_id=project_id,
                node_id=None,
                thread_id=clean_thread_id,
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
                conversation_context=chat_context,
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
            # Planner route now returns option proposals only; it does not persist suggested nodes.
            suggested_node_ids: list[str] = []
            reply = tr(
                "ai.chat.planner_reply",
                raw=response.content.strip() or tr("ai.chat.empty_fallback"),
                count=len(options),
            )
            self.repository.append_chat_message(
                clean_thread_id,
                role="assistant",
                content=reply,
            )
            return ChatAssistResult(
                project_id=project_id,
                node_id=node.id,
                thread_id=clean_thread_id,
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

        if route == "outline":
            outline_prompt, outline_bundle = self._chat_outline_prompt(
                project_id,
                node,
                context,
                cleaned_message,
                node_metadata,
                conversation_context=chat_context,
                token_budget=token_budget,
            )
            response = self._generate(
                task_type="chat_outline",
                prompt=outline_prompt,
                platform_config={
                    "token_budget": token_budget,
                    "tool_context_node_id": str(node.id),
                    "enable_tool_loop": True,
                    "node_tools_visible": True,
                    "node_tools_enabled": bool(allow_node_write),
                },
                llm_route=llm_route,
                project_id=project_id,
            )
            outline_text = response.content.strip()
            if not outline_text:
                raise RuntimeError(tr("ai.error.empty_response"))
            updated_node_id: str | None = None
            if allow_node_write:
                patched_metadata = node_metadata.copy()
                patched_metadata["outline_markdown"] = outline_text
                patched_metadata["ai_chat_last_route"] = route
                patched_metadata["ai_last_human_edit_at"] = utc_now().isoformat()
                patched_metadata["ai_prompt_version"] = outline_bundle.prompt_version
                patched_metadata["ai_prompt_sections"] = outline_bundle.sections_payload()
                patched_metadata["ai_prompt_dropped_sections"] = outline_bundle.dropped_sections
                patched_metadata["ai_prompt_constraints"] = outline_bundle.key_constraints
                patched_metadata["ai_last_prompt"] = outline_bundle.final_prompt
                patched_metadata["ai_prompt_token_counter_backend"] = (
                    outline_bundle.token_counter_backend
                )
                patched_metadata["ai_prompt_cache_monitor"] = outline_bundle.cache_monitor
                self.graph_service.update_node(
                    project_id,
                    node.id,
                    {
                        "metadata": patched_metadata,
                    },
                )
                updated_node_id = node.id
            self.repository.append_chat_message(
                clean_thread_id,
                role="assistant",
                content=outline_text,
            )
            return ChatAssistResult(
                project_id=project_id,
                node_id=node.id,
                thread_id=clean_thread_id,
                route="outline",
                reply=outline_text,
                review_bypassed=False,
                updated_node_id=updated_node_id,
                revision=self._project_revision(project_id),
            )

        if route == "writer":
            current_outline = str(node_metadata.get("outline_markdown", "")).strip()
            if not current_outline:
                guard_reply = tr("ai.chat.writer_outline_required")
                self.repository.append_chat_message(
                    clean_thread_id,
                    role="assistant",
                    content=guard_reply,
                )
                return ChatAssistResult(
                    project_id=project_id,
                    node_id=node.id,
                    thread_id=clean_thread_id,
                    route="guard",
                    reply=guard_reply,
                    review_bypassed=False,
                    revision=self._project_revision(project_id),
                )

        writer_prompt, writer_bundle = self._chat_writer_prompt(
            project_id,
            node,
            context,
            cleaned_message,
            node_metadata,
            conversation_context=chat_context,
            token_budget=token_budget,
        )
        response = self._generate(
            task_type="chat_writer",
            prompt=writer_prompt,
            platform_config={
                "token_budget": token_budget,
                "tool_context_node_id": str(node.id),
                "node_tools_visible": True,
                "node_tools_enabled": bool(allow_node_write),
            },
            llm_route=llm_route,
            project_id=project_id,
        )
        content = response.content.strip()
        if not content:
            raise RuntimeError(tr("ai.error.empty_response"))
        updated_node_id: str | None = None
        if allow_node_write:
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
            patched_metadata["ai_prompt_token_counter_backend"] = writer_bundle.token_counter_backend
            patched_metadata["ai_prompt_cache_monitor"] = writer_bundle.cache_monitor
            self.graph_service.update_node(
                project_id,
                node.id,
                {
                    "status": "generated",
                    "metadata": patched_metadata,
                },
            )
            self.repository.replace_node_chunks(node.id, split_text_by_chars(content))
            self._sync_state_after_llm_write(
                project_id=project_id,
                node_id=node.id,
                thread_id=clean_thread_id,
                content=content,
            )
            updated_node_id = node.id
        self.repository.append_chat_message(
            clean_thread_id,
            role="assistant",
            content=content,
        )
        return ChatAssistResult(
            project_id=project_id,
            node_id=node.id,
            thread_id=clean_thread_id,
            route="writer",
            reply=content,
            review_bypassed=review_bypassed,
            updated_node_id=updated_node_id,
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

    def generate_workflow_stage_reply(
        self,
        project_id: str,
        *,
        mode: str,
        stage: str,
        collected_inputs: dict[str, str] | None = None,
        clarify_questions: list[str] | None = None,
        token_budget: int = 1000,
    ) -> str:
        if self.repository.get_project(project_id) is None:
            self._raise_project_missing(project_id)
        clean_stage = str(stage or "").strip() or "collect_constitution"
        inputs = {
            str(k): str(v or "").strip()
            for k, v in dict(collected_inputs or {}).items()
            if str(v or "").strip()
        }
        questions = [str(item).strip() for item in list(clarify_questions or []) if str(item or "").strip()]
        prompt = self._workflow_stage_prompt(
            project_id,
            mode=mode,
            stage=clean_stage,
            collected_inputs=inputs,
            clarify_questions=questions,
        )
        response = self._generate(
            task_type="workflow_stage_reply",
            prompt=prompt,
            platform_config={"token_budget": max(500, token_budget)},
            project_id=project_id,
        )
        reply = self._parse_workflow_stage_assistant_message(response.content)
        if self._should_repair_workflow_stage_reply(
            stage=clean_stage,
            reply=reply,
            collected_inputs=inputs,
            clarify_questions=questions,
        ):
            repair_prompt = self._workflow_stage_repair_prompt(
                project_id,
                mode=mode,
                stage=clean_stage,
                collected_inputs=inputs,
                clarify_questions=questions,
                bad_reply=reply,
            )
            repaired = self._generate(
                task_type="workflow_stage_reply_repair",
                prompt=repair_prompt,
                platform_config={"token_budget": max(500, token_budget)},
                project_id=project_id,
            )
            reply = self._parse_workflow_stage_assistant_message(repaired.content)
        if not reply:
            reply = self._workflow_stage_default_message(clean_stage)
        return reply

    def generate_workflow_documents(
        self,
        project_id: str,
        *,
        mode: str,
        collected_inputs: dict[str, str] | None = None,
        clarify_questions: list[str] | None = None,
        token_budget: int = 1800,
    ) -> WorkflowDocsDraftResult:
        if self.repository.get_project(project_id) is None:
            self._raise_project_missing(project_id)
        inputs = {
            str(k): str(v or "").strip()
            for k, v in dict(collected_inputs or {}).items()
            if str(v or "").strip()
        }
        questions = [str(item).strip() for item in list(clarify_questions or []) if str(item or "").strip()]
        conversation = self._workflow_inputs_to_conversation(
            mode=mode,
            collected_inputs=inputs,
            clarify_questions=questions,
        )
        prompt = self._render_prompt_template(
            "guide_four_docs_prompt",
            fallback_key="ai.workflow.four_docs_prompt",
            conversation=conversation,
        )
        response = self._generate(
            task_type="workflow_docs_draft",
            prompt=prompt,
            platform_config={
                "token_budget": max(1000, token_budget),
                "write_document_enabled": True,
            },
            project_id=project_id,
        )

        # Check if documents were written via tools
        state = self.repository.get_workflow_doc_state(project_id)
        if state and state.get("pending_docs"):
            pending = state.get("pending_docs", {})
            docs = {
                "constitution_markdown": str(pending.get("constitution_markdown", "")).strip(),
                "clarify_markdown": str(pending.get("clarify_markdown", "")).strip(),
                "specification_markdown": str(pending.get("specification_markdown", "")).strip(),
                "plan_markdown": str(pending.get("plan_markdown", "")).strip(),
                "written_keys": [k.replace("_markdown", "") for k, v in pending.items() if v and k.endswith("_markdown")],
                "assistant_message": response.content.strip() or tr("ai.chat.empty_fallback"),
            }
        else:
            docs = self._parse_workflow_docs_payload(response.content)

        written_keys = [str(item) for item in list(docs.get("written_keys", []) or []) if str(item).strip()]
        ignored_keys = [str(item) for item in list(docs.get("ignored_keys", []) or []) if str(item).strip()]
        assistant_message = str(docs.get("assistant_message", "")).strip()
        if not assistant_message:
            assistant_message = response.content.strip() or tr("ai.chat.empty_fallback")
        return WorkflowDocsDraftResult(
            project_id=project_id,
            assistant_message=assistant_message,
            constitution_markdown=str(docs.get("constitution_markdown", "")).strip(),
            clarify_markdown=str(docs.get("clarify_markdown", "")).strip(),
            specification_markdown=str(docs.get("specification_markdown", "")).strip(),
            plan_markdown=str(docs.get("plan_markdown", "")).strip(),
            diff_summary=str(docs.get("diff_summary", "")).strip(),
            written_keys=written_keys,
            ignored_keys=ignored_keys,
        )

    def revise_workflow_documents(
        self,
        project_id: str,
        *,
        mode: str,
        collected_inputs: dict[str, str] | None = None,
        clarify_questions: list[str] | None = None,
        pending_docs: dict[str, str] | None = None,
        user_feedback: str = "",
        token_budget: int = 1800,
    ) -> WorkflowDocsDraftResult:
        if self.repository.get_project(project_id) is None:
            self._raise_project_missing(project_id)
        inputs = {
            str(k): str(v or "").strip()
            for k, v in dict(collected_inputs or {}).items()
            if str(v or "").strip()
        }
        questions = [str(item).strip() for item in list(clarify_questions or []) if str(item or "").strip()]
        pending = {
            "constitution_markdown": str(dict(pending_docs or {}).get("constitution_markdown", "") or "").strip(),
            "clarify_markdown": str(dict(pending_docs or {}).get("clarify_markdown", "") or "").strip(),
            "specification_markdown": str(dict(pending_docs or {}).get("specification_markdown", "") or "").strip(),
            "plan_markdown": str(dict(pending_docs or {}).get("plan_markdown", "") or "").strip(),
        }
        conversation = self._workflow_inputs_to_conversation(
            mode=mode,
            collected_inputs=inputs,
            clarify_questions=questions,
        )
        pending_text = (
            "[Constitution]\n"
            f"{pending['constitution_markdown'] or '-'}\n\n"
            "[Clarify]\n"
            f"{pending['clarify_markdown'] or '-'}\n\n"
            "[Specification]\n"
            f"{pending['specification_markdown'] or '-'}\n\n"
            "[Plan]\n"
            f"{pending['plan_markdown'] or '-'}"
        )
        feedback = str(user_feedback or "").strip() or "无新增修改。请仅修正表达并保持结构完整。"
        prompt = self._render_prompt_template(
            "workflow_docs_revise_prompt",
            fallback_key="ai.workflow.docs_revise_prompt",
            conversation=conversation,
            pending_docs=pending_text,
            user_feedback=feedback,
        )
        response = self._generate(
            task_type="workflow_docs_revise",
            prompt=prompt,
            platform_config={
                "token_budget": max(1000, token_budget),
                "write_document_enabled": True,
            },
            project_id=project_id,
        )

        # Check if documents were written via tools
        state = self.repository.get_workflow_doc_state(project_id)
        if state and state.get("pending_docs"):
            pending = state.get("pending_docs", {})
            docs = {
                "constitution_markdown": str(pending.get("constitution_markdown", "")).strip(),
                "clarify_markdown": str(pending.get("clarify_markdown", "")).strip(),
                "specification_markdown": str(pending.get("specification_markdown", "")).strip(),
                "plan_markdown": str(pending.get("plan_markdown", "")).strip(),
                "written_keys": [k.replace("_markdown", "") for k, v in pending.items() if v and k.endswith("_markdown")],
                "assistant_message": response.content.strip() or tr("ai.chat.empty_fallback"),
            }
        else:
            docs = self._parse_workflow_docs_payload(response.content)

        written_keys = [str(item) for item in list(docs.get("written_keys", []) or []) if str(item).strip()]
        ignored_keys = [str(item) for item in list(docs.get("ignored_keys", []) or []) if str(item).strip()]
        assistant_message = str(docs.get("assistant_message", "")).strip()
        if not assistant_message:
            assistant_message = response.content.strip() or tr("ai.chat.empty_fallback")
        return WorkflowDocsDraftResult(
            project_id=project_id,
            assistant_message=assistant_message,
            constitution_markdown=str(docs.get("constitution_markdown", "")).strip(),
            clarify_markdown=str(docs.get("clarify_markdown", "")).strip(),
            specification_markdown=str(docs.get("specification_markdown", "")).strip(),
            plan_markdown=str(docs.get("plan_markdown", "")).strip(),
            diff_summary=str(docs.get("diff_summary", "")).strip(),
            written_keys=written_keys,
            ignored_keys=ignored_keys,
        )

    def judge_workflow_mode(
        self,
        project_id: str,
        *,
        user_input: str,
        token_budget: int = 400,
    ) -> str:
        if self.repository.get_project(project_id) is None:
            self._raise_project_missing(project_id)
        raw = str(user_input or "").strip()
        if not raw:
            return "original"
        lowered = raw.lower()
        sequel_hints = ("续写", "后日谈", "同人", "fanfic", "sequel", "二创", "外传")
        if any(hint in lowered for hint in sequel_hints):
            return "sequel"
        prompt = self._render_prompt_template(
            "workflow_mode_judge_prompt",
            fallback_key="ai.workflow.mode_judge_prompt",
            user_input=raw,
        )
        response = self._generate(
            task_type="workflow_mode_judge",
            prompt=prompt,
            platform_config={"token_budget": max(200, token_budget)},
            project_id=project_id,
        )
        parsed = self._parse_outline_guide_payload(response.content, strict_json_fence=False)
        mode = str(parsed.get("mode", "") or "").strip().lower()
        if mode in {"sequel", "续写"}:
            return "sequel"
        return "original"

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
