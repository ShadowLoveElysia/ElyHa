"""Prompt parsing and LLM-call methods for AIService."""

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


class AIServicePromptParsersMixin:
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
        prompt = self._render_prompt_template(
            "chat_global_prompt",
            fallback_key="ai.chat.global_prompt",
            route=route,
            user_message=message,
            node_count=len(nodes),
            edge_count=len(edges),
            nodes="\n".join(node_lines) if node_lines else "-",
            edges="\n".join(edge_lines) if edge_lines else "-",
        )
        return prompt

    def _chat_planner_prompt(
        self,
        project_id: str,
        node: Any,
        context: ContextPack,
        user_message: str,
        *,
        conversation_context: str = "",
        token_budget: int,
    ) -> tuple[str, PromptBundle]:
        request_text = str(user_message or "").strip()
        context_text = str(conversation_context or "").strip()
        if context_text:
            request_text = f"{request_text}\n\n{context_text}"
        instruction = self._render_prompt_template(
            "chat_planner_prompt",
            fallback_key="ai.chat.planner_prompt",
            title=node.title,
            request=request_text,
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
            extra_node_context={
                "user_request": str(user_message or ""),
                "conversation_context": context_text,
            },
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
        conversation_context: str = "",
        token_budget: int,
    ) -> tuple[str, PromptBundle]:
        current_content = str(metadata.get("content", "")).strip() or tr("ai.chat.empty_fallback")
        current_outline = str(metadata.get("outline_markdown", "")).strip() or tr("ai.chat.empty_fallback")
        request_text = str(user_message or "").strip()
        context_text = str(conversation_context or "").strip()
        if context_text:
            request_text = f"{request_text}\n\n{context_text}"
        instruction = self._render_prompt_template(
            "chat_writer_prompt",
            fallback_key="ai.chat.writer_prompt",
            title=node.title,
            request=request_text,
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
            user_correction=str(user_message or ""),
            extra_node_context={
                "current_outline": current_outline,
                "current_content_excerpt": current_content[:1000],
                "conversation_context": context_text,
            },
        )
        return bundle.final_prompt, bundle

    def _chat_outline_prompt(
        self,
        project_id: str,
        node: Any,
        context: ContextPack,
        user_message: str,
        metadata: dict[str, Any],
        *,
        conversation_context: str = "",
        token_budget: int,
    ) -> tuple[str, PromptBundle]:
        current_content = str(metadata.get("content", "")).strip() or tr("ai.chat.empty_fallback")
        current_outline = str(metadata.get("outline_markdown", "")).strip() or tr("ai.chat.empty_fallback")
        request_text = str(user_message or "").strip()
        context_text = str(conversation_context or "").strip()
        if context_text:
            request_text = f"{request_text}\n\n{context_text}"
        instruction = self._render_prompt_template(
            "chat_outline_prompt",
            fallback_key="ai.chat.outline_prompt",
            title=node.title,
            request=request_text,
            current_outline=current_outline,
            current_content=current_content,
            context="(see structured context sections below)",
        )
        bundle = self._build_prompt_bundle(
            project_id=project_id,
            node=node,
            context=context,
            token_budget=token_budget,
            task_mode="generate",
            task_type="chat_outline",
            task_instruction=instruction,
            extra_node_context={
                "current_outline": current_outline,
                "current_content_excerpt": current_content[:1000],
                "conversation_context": context_text,
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
            "outline": "outline",
            "outliner": "outline",
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

    def _should_route_to_outline(
        self,
        *,
        message: str,
        node_metadata: dict[str, Any],
    ) -> bool:
        current_outline = str(node_metadata.get("outline_markdown", "")).strip()
        if not current_outline:
            return True

        raw = str(message or "").strip()
        lowered = raw.lower()
        if not raw:
            return False

        # Keep writer route when user explicitly asks for prose based on outline.
        if ("根据大纲" in raw or "按大纲" in raw or "依照大纲" in raw) and (
            "正文" in raw or "本文" in raw
        ):
            return False
        if ("based on outline" in lowered or "follow the outline" in lowered) and (
            "prose" in lowered or "content" in lowered or "draft" in lowered
        ):
            return False

        outline_action_patterns = (
            r"(补充|完善|生成|创建|写|更新|修改|重写|扩写).{0,8}(大纲|细纲|章纲)",
            r"(大纲|细纲|章纲).{0,8}(补充|完善|生成|创建|写|更新|修改|重写|扩写)",
            r"(update|revise|rewrite|generate|create|edit)\s+(the\s+)?outline",
            r"outline\s+(update|revise|rewrite|generate|create|edit)",
            r"(大綱|アウトライン).{0,8}(更新|作成|修正|生成|書き|追記)",
        )
        for pattern in outline_action_patterns:
            if re.search(pattern, raw, flags=re.IGNORECASE):
                return True

        has_outline_keyword = any(
            marker in raw
            for marker in ("大纲", "细纲", "章纲", "大綱", "アウトライン", "プロットビート")
        ) or any(marker in lowered for marker in ("outline", "beat list", "beats"))
        has_prose_keyword = any(marker in raw for marker in ("正文", "本文", "章节正文")) or any(
            marker in lowered for marker in ("prose", "draft", "chapter content", "full text")
        )
        return has_outline_keyword and not has_prose_keyword

    def _build_global_tool_gate_specs(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "request_tool_mode",
                "description": (
                    "Request entering tool loop for this turn. "
                    "Set write_document_enabled=true only when workflow docs must be written."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "enable_tool_loop": {
                            "type": "boolean",
                            "description": "Whether to enable full tool loop for current turn.",
                        },
                        "write_document_enabled": {
                            "type": "boolean",
                            "description": "Whether write_document tool is required in this turn.",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Short reason for the decision.",
                        },
                    },
                    "required": ["enable_tool_loop"],
                },
            }
        ]

    def _append_global_tool_gate_contract(self, prompt: str) -> str:
        base = str(prompt or "").strip()
        available_tools = (
            "search_text, read_chunk, read_neighbors, get_chapter_outline, "
            "get_world_state, list_relationship_status, upsert_relationship_status, "
            "get_effective_directives, write_document(optional), "
            "graph_tools(optional)"
        )
        lines = [
            base,
            "",
            "[ToolModeGate]",
            f"Runtime tool inventory exists: {available_tools}.",
            "Important: these runtime tools are only callable after entering tool loop.",
            "Outside loop, any non-gate tool call will be blocked by backend and not executed.",
            "If normal text response is enough, answer directly without tool calls.",
            "If tool usage is needed, call request_tool_mode exactly once.",
            'Example: {"enable_tool_loop":true,"write_document_enabled":false,"reason":"need retrieval"}',
            "Set write_document_enabled=true only if workflow docs must be written via write_document.",
            "Do not claim tool execution success unless tool loop actually returns tool results.",
            "Never fabricate tool outputs.",
        ]
        return "\n".join(lines).strip()

    def _extract_global_tool_gate_decision(
        self,
        tool_calls: list[dict[str, Any]],
    ) -> dict[str, bool]:
        def _as_bool(value: Any) -> bool:
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return bool(value)
            if isinstance(value, str):
                text = value.strip().lower()
                if text in {"1", "true", "yes", "on"}:
                    return True
                if text in {"0", "false", "no", "off"}:
                    return False
            return False

        decision = {"enable_tool_loop": False, "write_document_enabled": False}
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            name = str(call.get("name", "")).strip().lower()
            if name not in {"request_tool_mode", "enable_tool_loop"}:
                continue
            args = call.get("arguments")
            if not isinstance(args, dict):
                args = {}
            enable_tool_loop = _as_bool(args.get("enable_tool_loop"))
            write_document_enabled = _as_bool(args.get("write_document_enabled"))
            if enable_tool_loop or write_document_enabled:
                decision["enable_tool_loop"] = True
            if write_document_enabled:
                decision["write_document_enabled"] = True
            break
        return decision

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
        if self._tool_loop_enabled(
            task_type=task_type,
            project_id=project_id,
            platform_config=merged_platform_config,
        ):
            response = self._generate_with_tool_loop(
                adapter=adapter,
                task_type=task_type,
                prompt=prompt,
                platform_config=merged_platform_config,
                project_id=project_id,
            )
        else:
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

