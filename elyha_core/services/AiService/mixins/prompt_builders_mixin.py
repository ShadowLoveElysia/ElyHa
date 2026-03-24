"""Prompt construction methods for AIService."""

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

_STRICT_JSON_FENCE_PATTERN = re.compile(
    r"^\s*```json\s*([\s\S]*?)\s*```\s*$",
    flags=re.IGNORECASE,
)

_GUIDE_DOC_LABELS = {
    "constitution_markdown": "constitution",
    "clarify_markdown": "clarify",
    "specification_markdown": "specification",
    "plan_markdown": "plan",
}
_GUIDE_DOC_SLOTS = tuple(_GUIDE_DOC_LABELS.keys())
_GUIDE_DOC_ALIASES = {
    "constitution": "constitution_markdown",
    "constitution_markdown": "constitution_markdown",
    "clarify": "clarify_markdown",
    "clarify_markdown": "clarify_markdown",
    "specification": "specification_markdown",
    "specification_markdown": "specification_markdown",
    "plan": "plan_markdown",
    "plan_markdown": "plan_markdown",
}


class AIServicePromptBuildersMixin:
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
        tokenizer_model = self._resolve_tokenizer_model_hint()
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
            tokenizer_model=tokenizer_model,
            context_compaction_enabled=bool(getattr(settings, "context_compaction_enabled", True)),
            context_compaction_trigger_ratio=int(
                getattr(settings, "context_compaction_trigger_ratio", 80)
            ),
            context_compaction_keep_recent_chunks=int(
                getattr(settings, "context_compaction_keep_recent_chunks", 4)
            ),
            context_compaction_group_chunks=int(
                getattr(settings, "context_compaction_group_chunks", 4)
            ),
            context_compaction_chunk_chars=int(
                getattr(settings, "context_compaction_chunk_chars", 1200)
            ),
        )
        if task_mode == "correct":
            bundle = self.context_assembler.build_correction_prompt(bundle_input)
        else:
            bundle = self.context_assembler.build_generation_prompt(bundle_input)
        bundle.cache_monitor = self._record_prompt_cache_monitor(
            project_id=project_id,
            node_id=str(node.id),
            task_type=task_type,
            task_mode=task_mode,
            prompt=bundle.final_prompt,
        )
        return bundle

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
        final_prompt = bundle.final_prompt
        if instruction and instruction not in final_prompt:
            final_prompt = f"{instruction}\n\n{final_prompt}"
        return final_prompt, bundle

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
            "ai_prompt_token_counter_backend": (
                final_bundle.token_counter_backend if final_bundle is not None else ""
            ),
            "ai_prompt_cache_monitor": final_bundle.cache_monitor if final_bundle is not None else {},
            "ai_prompt_sections_by_agent": {
                name: bundle.sections_payload() for name, bundle in agent_bundles.items()
            },
            "ai_last_prompt_by_agent": {
                name: bundle.final_prompt for name, bundle in agent_bundles.items()
            },
            "ai_prompt_token_counter_by_agent": {
                name: bundle.token_counter_backend for name, bundle in agent_bundles.items()
            },
            "ai_prompt_cache_by_agent": {
                name: bundle.cache_monitor for name, bundle in agent_bundles.items()
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

    def _format_chat_history_for_prompt(self, history: list[dict[str, str]]) -> str:
        if not history:
            return ""
        lines: list[str] = []
        for item in history[-12:]:
            role = str(item.get("role", "") or "").strip().lower()
            content = str(item.get("content", "") or "").strip()
            if not content:
                continue
            role_label = "assistant" if role == "assistant" else "user"
            preview = content if len(content) <= 600 else content[:600] + "..."
            lines.append(f"{role_label}: {preview}")
        return "\n".join(lines).strip()

    def _build_workflow_docs_prompt_context(self, project_id: str) -> str:
        project = self.repository.get_project(project_id)
        if project is None:
            return ""
        settings = project.settings
        parts: list[str] = []
        constitution = str(getattr(settings, "constitution_markdown", "") or "").strip()
        clarify = str(getattr(settings, "clarify_markdown", "") or "").strip()
        specification = str(getattr(settings, "specification_markdown", "") or "").strip()
        plan = str(getattr(settings, "plan_markdown", "") or "").strip()
        if constitution:
            parts.append("[Constitution]\n" + constitution)
        if clarify:
            parts.append("[Clarify]\n" + clarify)
        if specification:
            parts.append("[Specification]\n" + specification)
        if plan:
            parts.append("[Plan]\n" + plan)
        skipped_docs = self._normalized_guide_skipped_docs(project_id)
        if skipped_docs:
            skipped_labels = [_GUIDE_DOC_LABELS.get(slot, slot) for slot in skipped_docs]
            parts.append("[Guide Skipped Docs]\n" + ", ".join(skipped_labels))
        state = self.repository.get_workflow_doc_state(project_id)
        if state is not None:
            stage = str(state.get("workflow_stage", "") or "").strip()
            mode = str(state.get("workflow_mode", "") or "").strip()
            if stage:
                parts.append(f"[Workflow Stage]\n{stage}")
            if mode:
                parts.append(f"[Workflow Mode]\n{mode}")
            pending_docs = state.get("pending_docs", {})
            if isinstance(pending_docs, dict):
                pending_constitution = str(pending_docs.get("constitution_markdown", "") or "").strip()
                pending_clarify = str(pending_docs.get("clarify_markdown", "") or "").strip()
                pending_specification = str(pending_docs.get("specification_markdown", "") or "").strip()
                pending_plan = str(pending_docs.get("plan_markdown", "") or "").strip()
                if pending_constitution:
                    parts.append("[Pending Constitution]\n" + pending_constitution)
                if pending_clarify:
                    parts.append("[Pending Clarify]\n" + pending_clarify)
                if pending_specification:
                    parts.append("[Pending Specification]\n" + pending_specification)
                if pending_plan:
                    parts.append("[Pending Plan]\n" + pending_plan)
        return "\n\n".join(parts).strip()

    def _normalized_guide_skipped_docs(self, project_id: str) -> list[str]:
        settings = self._project_settings(project_id)
        raw = getattr(settings, "guide_skipped_docs", [])
        if not isinstance(raw, list):
            return []
        normalized: list[str] = []
        for item in raw:
            slot = _GUIDE_DOC_ALIASES.get(str(item or "").strip().lower(), "")
            if not slot:
                continue
            if slot not in normalized:
                normalized.append(slot)
        return normalized

    def _workflow_doc_status(self, project_id: str) -> dict[str, Any]:
        settings = self._project_settings(project_id)
        docs = {
            "constitution_markdown": str(getattr(settings, "constitution_markdown", "") or "").strip(),
            "clarify_markdown": str(getattr(settings, "clarify_markdown", "") or "").strip(),
            "specification_markdown": str(getattr(settings, "specification_markdown", "") or "").strip(),
            "plan_markdown": str(getattr(settings, "plan_markdown", "") or "").strip(),
        }
        skipped_slots = self._normalized_guide_skipped_docs(project_id)
        skipped_set = set(skipped_slots)
        missing_slots = [slot for slot, value in docs.items() if not value and slot not in skipped_set]
        return {
            "docs": docs,
            "missing_slots": missing_slots,
            "missing_labels": [_GUIDE_DOC_LABELS.get(slot, slot) for slot in missing_slots],
            "skipped_slots": skipped_slots,
            "skipped_labels": [_GUIDE_DOC_LABELS.get(slot, slot) for slot in skipped_slots],
            "complete": not missing_slots,
        }

    def _chat_global_guide_prompt(
        self,
        project_id: str,
        message: str,
        *,
        route: str,
        missing_labels: list[str] | None = None,
    ) -> str:
        base = self._chat_global_prompt(project_id, message, route=route)
        missing = [str(item).strip() for item in list(missing_labels or []) if str(item).strip()]
        missing_text = ", ".join(missing) if missing else "none"
        lines = [
            base,
            "",
            "[GuideModeContract]",
            "This turn is in mandatory outline-guide mode.",
            "Target docs: constitution, clarify, specification, plan.",
            f"Missing docs right now: {missing_text}.",
            "You may ask concise clarification questions first, then write docs when information is sufficient.",
            "Use write_document to persist finalized doc content. Do not output chapter/story prose here.",
            "If user explicitly asks to skip a doc, call skip_document instead of writing that doc.",
            "Do not claim tool success without actual tool results.",
            "Keep reply concise: status + at most one short follow-up question.",
        ]
        return "\n".join(lines).strip()

    def _extract_guide_skip_document_request(self, raw: Any) -> str:
        if not isinstance(raw, dict):
            return ""
        logs = raw.get("agent_tool_calls")
        if not isinstance(logs, list):
            return ""
        for item in reversed(logs):
            if not isinstance(item, dict):
                continue
            tool_name = str(item.get("tool_name", "") or "").strip().lower()
            if tool_name != "skip_document":
                continue
            result_meta = item.get("result_meta")
            if not isinstance(result_meta, dict):
                continue
            if not bool(result_meta.get("skip_document_requested", False)):
                continue
            doc_type = str(result_meta.get("skip_document_type", "") or "").strip().lower()
            if doc_type in {"constitution", "clarify", "specification", "plan"}:
                return doc_type
        return ""

    def _combine_chat_prompt_context(
        self,
        *,
        history_block: str,
        workflow_docs_block: str,
    ) -> str:
        sections: list[str] = []
        if history_block:
            sections.append("[Recent Thread History]\n" + history_block)
        if workflow_docs_block:
            sections.append("[Workflow Doc Context]\n" + workflow_docs_block)
        return "\n\n".join(sections).strip()

    def _workflow_stage_prompt(
        self,
        project_id: str,
        *,
        mode: str,
        stage: str,
        collected_inputs: dict[str, str],
        clarify_questions: list[str],
    ) -> str:
        project = self.repository.get_project(project_id)
        project_title = project.title if project is not None else project_id
        input_lines = "\n".join(f"- {k}: {v}" for k, v in collected_inputs.items()) or "-"
        question_lines = "\n".join(f"- {q}" for q in clarify_questions) or "-"
        return self._render_prompt_template(
            "workflow_stage_reply_prompt",
            fallback_key="ai.workflow.stage_reply_prompt",
            project_title=project_title,
            mode=str(mode or "").strip() or "original",
            stage=str(stage or "").strip() or "collect_constitution",
            collected_inputs=input_lines,
            clarify_questions=question_lines,
        )

    def _workflow_stage_repair_prompt(
        self,
        project_id: str,
        *,
        mode: str,
        stage: str,
        collected_inputs: dict[str, str],
        clarify_questions: list[str],
        bad_reply: str,
    ) -> str:
        project = self.repository.get_project(project_id)
        project_title = project.title if project is not None else project_id
        input_lines = "\n".join(f"- {k}: {v}" for k, v in collected_inputs.items()) or "-"
        question_lines = "\n".join(f"- {q}" for q in clarify_questions) or "-"
        return self._render_prompt_template(
            "workflow_stage_repair_prompt",
            fallback_key="ai.workflow.stage_repair_prompt",
            project_title=project_title,
            mode=str(mode or "").strip() or "original",
            stage=str(stage or "").strip() or "collect_constitution",
            collected_inputs=input_lines,
            clarify_questions=question_lines,
            bad_reply=str(bad_reply or "").strip() or "-",
        )

    def _parse_workflow_stage_assistant_message(self, text: str) -> str:
        parsed = self._parse_outline_guide_payload(text, strict_json_fence=False)
        message = str(parsed.get("assistant_message", "") or "").strip()
        if message:
            return message
        return str(text or "").strip()

    def _should_repair_workflow_stage_reply(
        self,
        *,
        stage: str,
        reply: str,
        collected_inputs: dict[str, str],
        clarify_questions: list[str],
    ) -> bool:
        text = str(reply or "").strip()
        if not text:
            return True
        lowered = text.lower()
        if "请告诉我你的项目名称" in text or "我是elyha写作助手" in lowered:
            return True
        input_text = "\n".join(collected_inputs.values())
        has_story_signal = any(token in input_text for token in ("小说", "故事", "续写", "同人"))
        if has_story_signal and ("手册" in text) and ("手册" not in input_text):
            return True
        if str(stage or "").strip() == "collect_clarify" and clarify_questions:
            probes = ("套路", "角色", "第四面墙", "冲突", "结局", "视角")
            if not any((probe in text) for probe in probes):
                return True
        return False

    def _workflow_stage_default_message(self, stage: str) -> str:
        defaults = {
            "collect_constitution": "请先说明项目核心目标与基调，我会据此推进下一步。",
            "collect_specification": "请补充可执行规格（篇幅、节奏、结局方向、约束项）。",
            "collect_clarify": "请按澄清问题逐条回答，我将据此收敛方案。",
            "collect_plan": "请给出计划偏好（章节节奏/推进方式），随后生成四份文档草案。",
            "revise": "请补充修订意见，我会给出第二轮草案。",
            "modal_confirm": "若无异议，请确认并发布四份文档。",
            "published": "四份文档已发布并写入项目设置。",
        }
        return defaults.get(str(stage or "").strip(), "请继续提供可执行信息。")

    def _workflow_inputs_to_conversation(
        self,
        *,
        mode: str,
        collected_inputs: dict[str, str],
        clarify_questions: list[str],
    ) -> str:
        lines: list[str] = [f"[mode] {str(mode or '').strip() or 'original'}"]
        for key in ("constitution_input", "specification_input", "clarify_input", "plan_input", "revise_input"):
            value = str(collected_inputs.get(key, "")).strip()
            if value:
                lines.append(f"[{key}] {value}")
        if clarify_questions:
            lines.append("[clarify_questions]")
            lines.extend(f"- {item}" for item in clarify_questions)
        return "\n".join(lines).strip()

    def _parse_workflow_docs_payload(self, text: str) -> dict[str, Any]:
        raw = str(text or "").strip()
        result: dict[str, Any] = {
            "assistant_message": "",
            "constitution_markdown": "",
            "clarify_markdown": "",
            "specification_markdown": "",
            "plan_markdown": "",
            "diff_summary": "",
            "written_keys": [],
            "ignored_keys": [],
        }
        if not raw:
            return result

        ignored_keys: list[str] = []
        parsed = self._parse_outline_guide_payload(raw, strict_json_fence=False)
        if parsed:
            for key, value in parsed.items():
                clean_key = str(key or "").strip()
                if not clean_key:
                    continue
                slot = self._workflow_doc_slot_from_key(clean_key)
                if not slot:
                    ignored_keys.append(clean_key)
                    continue
                text_value = self._coerce_markdown_text(value)
                if slot in {"assistant_message", "diff_summary"}:
                    result[slot] = text_value
                    continue
                if text_value:
                    result[slot] = text_value
                    cast(list[str], result["written_keys"]).append(slot)

        if not cast(list[str], result["written_keys"]):
            section_docs, section_ignored = self._parse_workflow_docs_sections_from_text(raw)
            for slot, value in section_docs.items():
                if not value:
                    continue
                result[slot] = value
                cast(list[str], result["written_keys"]).append(slot)
            ignored_keys.extend(section_ignored)

        dedup_written: list[str] = []
        for key in cast(list[str], result["written_keys"]):
            if key in dedup_written:
                continue
            dedup_written.append(key)
        result["written_keys"] = dedup_written

        dedup_ignored: list[str] = []
        for key in ignored_keys:
            clean = str(key or "").strip()
            if not clean:
                continue
            if self._workflow_doc_slot_from_key(clean):
                continue
            if clean in dedup_ignored:
                continue
            dedup_ignored.append(clean)
        if not dedup_written and not dedup_ignored and raw:
            dedup_ignored.append("unstructured_output")
        result["ignored_keys"] = dedup_ignored

        if not str(result.get("assistant_message", "")).strip():
            result["assistant_message"] = str(text or "").strip()

        return result

    def _workflow_doc_slot_from_key(self, raw_key: str) -> str:
        key = str(raw_key or "").strip().lower()
        if not key:
            return ""
        if key.endswith(".md"):
            key = key[:-3].strip()
        compact = (
            key.replace(" ", "")
            .replace("-", "")
            .replace("_", "")
            .replace("/", "")
            .replace("\\", "")
            .replace(".", "")
        )
        mapping = {
            "assistantmessage": "assistant_message",
            "assistant": "assistant_message",
            "message": "assistant_message",
            "reply": "assistant_message",
            "diffsummary": "diff_summary",
            "changesummary": "diff_summary",
            "constitution": "constitution_markdown",
            "constitutionmarkdown": "constitution_markdown",
            "宪法": "constitution_markdown",
            "clarify": "clarify_markdown",
            "clarifymarkdown": "clarify_markdown",
            "澄清": "clarify_markdown",
            "specification": "specification_markdown",
            "specificationmarkdown": "specification_markdown",
            "规格": "specification_markdown",
            "规范": "specification_markdown",
            "plan": "plan_markdown",
            "planmarkdown": "plan_markdown",
            "计划": "plan_markdown",
        }
        return mapping.get(compact, "")

    def _coerce_markdown_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            lines: list[str] = []
            for item in value:
                text = str(item or "").strip()
                if not text:
                    continue
                lines.append(f"- {text}")
            return "\n".join(lines).strip()
        if isinstance(value, dict):
            try:
                return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).strip()
            except Exception:
                return str(value).strip()
        return str(value).strip()

    def _parse_workflow_docs_sections_from_text(self, text: str) -> tuple[dict[str, str], list[str]]:
        docs = {
            "constitution_markdown": "",
            "clarify_markdown": "",
            "specification_markdown": "",
            "plan_markdown": "",
        }
        ignored: list[str] = []
        current_slot = ""
        buckets: dict[str, list[str]] = {
            "constitution_markdown": [],
            "clarify_markdown": [],
            "specification_markdown": [],
            "plan_markdown": [],
        }

        for raw_line in str(text or "").splitlines():
            line = raw_line.rstrip("\n")
            stripped = line.strip()
            if not stripped and not current_slot:
                continue

            heading_label = ""
            markdown_heading = re.match(r"^\s{0,3}#{1,6}\s*(.+?)\s*$", line)
            bracket_heading = re.match(r"^\s*\[(.+?)\]\s*$", line)
            colon_heading = re.match(r"^\s*([A-Za-z\u4e00-\u9fff][A-Za-z0-9_.\-/\u4e00-\u9fff ]{0,80})\s*:\s*$", line)
            if markdown_heading:
                heading_label = str(markdown_heading.group(1) or "").strip()
            elif bracket_heading:
                heading_label = str(bracket_heading.group(1) or "").strip()
            elif colon_heading:
                heading_label = str(colon_heading.group(1) or "").strip()

            if heading_label:
                slot = self._workflow_doc_slot_from_key(heading_label)
                if slot in buckets:
                    current_slot = slot
                    continue
                ignored.append(heading_label)
                current_slot = ""
                continue

            if current_slot:
                buckets[current_slot].append(line)

        for slot, lines in buckets.items():
            content = "\n".join(lines).strip()
            if content:
                docs[slot] = content
        return docs, ignored

    def _fallback_workflow_docs(
        self,
        collected_inputs: dict[str, str],
        clarify_questions: list[str],
    ) -> dict[str, str]:
        constitution = str(collected_inputs.get("constitution_input", "")).strip()
        specification = str(collected_inputs.get("specification_input", "")).strip()
        clarify_answer = str(collected_inputs.get("clarify_input", "")).strip()
        plan = str(collected_inputs.get("plan_input", "")).strip()
        clarify_sections: list[str] = []
        if clarify_questions:
            clarify_sections.append("## 待确认问题")
            clarify_sections.extend(f"- {item}" for item in clarify_questions)
        if clarify_answer:
            clarify_sections.append("")
            clarify_sections.append("## 用户回答")
            clarify_sections.append(clarify_answer)
        return {
            "assistant_message": "已根据现有输入生成四份基础文档，请确认并补充待确认项。",
            "constitution_markdown": constitution or "## 待确认项\n- 核心目标与基调待补充。",
            "clarify_markdown": "\n".join(clarify_sections).strip() or "## 待确认项\n- 澄清信息不足。",
            "specification_markdown": specification or "## 待确认项\n- 规格约束（篇幅/节奏/结局）待补充。",
            "plan_markdown": plan or "## 待确认项\n- 执行计划与里程碑待补充。",
            "diff_summary": "",
        }
