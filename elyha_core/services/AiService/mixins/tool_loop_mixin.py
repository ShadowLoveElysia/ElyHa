"""Tool-loop methods for AIService."""

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


class AIServiceToolLoopMixin:
    def _tool_loop_enabled(
        self,
        *,
        task_type: str,
        project_id: str | None,
        platform_config: dict[str, Any],
    ) -> bool:
        limits = self._tool_loop_limits(project_id=project_id, platform_config=platform_config)
        if not bool(limits.get("enabled", True)):
            return False
        if bool(platform_config.get("disable_tool_loop", False)):
            return False
        if bool(platform_config.get("enable_tool_loop", False)):
            return True
        if project_id and self._strict_json_fence_output_enabled(project_id):
            return False
        enabled_tasks = {
            "generate_chapter",
            "chapter_write",
            "chapter_correction",
            "chat_writer",
            "workflow_docs_draft",
            "workflow_docs_revise",
        }
        return task_type in enabled_tasks

    def _tool_loop_limits(
        self,
        *,
        project_id: str | None,
        platform_config: dict[str, Any],
    ) -> dict[str, Any]:
        def _as_bool(value: Any, fallback: bool) -> bool:
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return bool(value)
            if isinstance(value, str):
                normalized = value.strip().lower()
                if normalized in {"1", "true", "yes", "on"}:
                    return True
                if normalized in {"0", "false", "no", "off"}:
                    return False
            return fallback

        def _as_int(value: Any, fallback: int, *, lower: int, upper: int) -> int:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                parsed = fallback
            if parsed < lower:
                return lower
            if parsed > upper:
                return upper
            return parsed

        enabled = True
        max_rounds = self._tool_loop_max_rounds
        max_calls_per_round = self._tool_loop_max_calls_per_round
        single_read_char_limit = self._tool_loop_single_read_char_limit
        total_read_char_limit = self._tool_loop_total_read_char_limit
        no_progress_limit = self._tool_loop_no_progress_limit
        write_proposal_enabled = self._tool_write_proposal_enabled
        if project_id:
            settings = self._project_settings(project_id)
            enabled = bool(getattr(settings, "agent_tool_loop_enabled", enabled))
            max_rounds = int(getattr(settings, "agent_tool_loop_max_rounds", max_rounds))
            max_calls_per_round = int(
                getattr(settings, "agent_tool_loop_max_calls_per_round", max_calls_per_round)
            )
            single_read_char_limit = int(
                getattr(settings, "agent_tool_loop_single_read_char_limit", single_read_char_limit)
            )
            total_read_char_limit = int(
                getattr(settings, "agent_tool_loop_total_read_char_limit", total_read_char_limit)
            )
            no_progress_limit = int(
                getattr(settings, "agent_tool_loop_no_progress_limit", no_progress_limit)
            )
            write_proposal_enabled = bool(
                getattr(settings, "agent_tool_write_proposal_enabled", write_proposal_enabled)
            )
        max_rounds = _as_int(
            platform_config.get("tool_loop_max_rounds", max_rounds),
            max_rounds,
            lower=1,
            upper=20,
        )
        max_calls_per_round = _as_int(
            platform_config.get("tool_loop_max_calls_per_round", max_calls_per_round),
            max_calls_per_round,
            lower=1,
            upper=20,
        )
        single_read_char_limit = _as_int(
            platform_config.get("tool_loop_single_read_char_limit", single_read_char_limit),
            single_read_char_limit,
            lower=200,
            upper=50000,
        )
        total_read_char_limit = _as_int(
            platform_config.get("tool_loop_total_read_char_limit", total_read_char_limit),
            total_read_char_limit,
            lower=1000,
            upper=200000,
        )
        no_progress_limit = _as_int(
            platform_config.get("tool_loop_no_progress_limit", no_progress_limit),
            no_progress_limit,
            lower=1,
            upper=10,
        )
        write_proposal_enabled = _as_bool(
            platform_config.get("tool_write_proposal_enabled", write_proposal_enabled),
            write_proposal_enabled,
        )
        enabled = _as_bool(platform_config.get("tool_loop_enabled", enabled), enabled)
        if total_read_char_limit < single_read_char_limit:
            total_read_char_limit = single_read_char_limit
        return {
            "enabled": enabled,
            "max_rounds": max_rounds,
            "max_calls_per_round": max_calls_per_round,
            "single_read_char_limit": single_read_char_limit,
            "total_read_char_limit": total_read_char_limit,
            "no_progress_limit": no_progress_limit,
            "write_proposal_enabled": write_proposal_enabled,
        }

    def _generate_with_tool_loop(
        self,
        *,
        adapter: Any,
        task_type: str,
        prompt: str,
        platform_config: dict[str, Any],
        project_id: str | None,
    ) -> LLMResponse:
        limits = self._tool_loop_limits(project_id=project_id, platform_config=platform_config)
        max_rounds = int(limits["max_rounds"])
        max_calls_per_round = int(limits["max_calls_per_round"])
        single_read_char_limit = int(limits["single_read_char_limit"])
        total_read_char_limit = int(limits["total_read_char_limit"])
        no_progress_limit = int(limits["no_progress_limit"])
        write_proposal_enabled = bool(limits["write_proposal_enabled"])
        system_prompt = self._build_system_prompt(project_id)
        base_prompt = str(prompt or "").strip()
        tool_result_blocks: list[str] = []
        round_logs: list[dict[str, Any]] = []
        tool_logs: list[dict[str, Any]] = []
        tool_response_cache: dict[str, tuple[Any, int, dict[str, Any]]] = {}
        evidence_chunk_ids: list[str] = []
        evidence_seen: set[str] = set()
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_read_chars = 0
        no_progress_rounds = 0
        force_final_only = False
        fallback_content = ""
        last_response: LLMResponse | None = None
        final_content = ""
        agent_name = self._agent_name_for_task(task_type)
        tool_context_node_id = str(platform_config.get("tool_context_node_id", "") or "").strip()
        tool_thread_id = str(platform_config.get("tool_thread_id", "") or "").strip()
        write_document_enabled = bool(platform_config.get("write_document_enabled", False))
        allow_skip_document = bool(platform_config.get("allow_skip_document", False))
        node_tools_visible = bool(platform_config.get("node_tools_visible", False))
        node_tools_enabled = bool(platform_config.get("node_tools_enabled", False))
        write_document_required_default = (
            write_document_enabled and task_type in {"workflow_docs_draft", "workflow_docs_revise"}
        )
        write_document_required = bool(
            platform_config.get("write_document_required", write_document_required_default)
        )
        loop_platform_config = dict(platform_config)
        native_tools = self.tool_service.build_native_tool_specs(
            write_proposal_enabled=write_proposal_enabled,
            write_document_enabled=write_document_enabled,
            allow_skip_document=allow_skip_document,
            node_tools_visible=node_tools_visible,
            node_tools_enabled=node_tools_enabled,
        )
        if native_tools:
            loop_platform_config["native_tools"] = native_tools
            loop_platform_config.setdefault("native_tool_choice", {"type": "auto"})
        for round_no in range(1, max_rounds + 1):
            round_prompt = self._build_tool_loop_prompt(
                base_prompt=base_prompt,
                round_no=round_no,
                tool_result_blocks=tool_result_blocks,
                max_rounds=max_rounds,
                max_calls_per_round=max_calls_per_round,
                single_read_char_limit=single_read_char_limit,
                total_read_char_limit=total_read_char_limit,
                write_proposal_enabled=write_proposal_enabled,
                force_final_only=force_final_only,
                write_document_enabled=write_document_enabled,
                write_document_required=write_document_required,
                allow_skip_document=allow_skip_document,
                node_tools_visible=node_tools_visible,
            )
            prompt_hash = hashlib.sha256(round_prompt.encode("utf-8")).hexdigest()
            request = LLMRequest(
                task_type=task_type,
                system_prompt=system_prompt,
                messages=[LLMMessage(role="user", content=round_prompt)],
                platform_config=loop_platform_config,
            )
            response = adapter.generate(request)
            if not response.ok:
                return response
            last_response = response
            total_prompt_tokens += int(response.prompt_tokens)
            total_completion_tokens += int(response.completion_tokens)
            parsed = self._parse_tool_loop_response(response)
            parsed_calls = cast(list[dict[str, Any]], parsed["tool_calls"])
            final_candidate = str(parsed["final_content"] or "").strip()
            action_hint = str(parsed.get("action", "") or "").strip().lower()
            if action_hint == "tool_calls":
                final_candidate = ""
            call_budget = max_calls_per_round
            if force_final_only or action_hint == "final":
                selected_calls: list[dict[str, Any]] = []
            else:
                selected_calls = parsed_calls[:call_budget]
            truncated_calls = len(parsed_calls) > len(selected_calls)
            round_status = "no_action"
            round_had_progress = False
            if final_candidate and not selected_calls:
                no_progress_rounds = 0
                round_status = "final"
            elif selected_calls:
                for call in selected_calls:
                    tool_name = str(call.get("name", "")).strip().lower()
                    args = call.get("arguments")
                    if not isinstance(args, dict):
                        args = {}
                    started = time.perf_counter()
                    result_payload, read_chars, result_meta = self.tool_service.execute_tool_call(
                        tool_name=tool_name,
                        arguments=args,
                        project_id=project_id or "",
                        tool_context_node_id=tool_context_node_id,
                        tool_thread_id=tool_thread_id,
                        write_proposal_enabled=write_proposal_enabled,
                        write_document_enabled=write_document_enabled,
                        allow_skip_document=allow_skip_document,
                        node_tools_enabled=node_tools_enabled,
                        tool_response_cache=tool_response_cache,
                        single_read_char_limit=single_read_char_limit,
                        total_read_char_limit=total_read_char_limit,
                        total_read_chars=total_read_chars,
                    )
                    elapsed_ms = int((time.perf_counter() - started) * 1000)
                    if int(read_chars) > 0:
                        total_read_chars += int(read_chars)
                        round_had_progress = True
                    result_meta = dict(result_meta)
                    result_meta["duration_ms"] = elapsed_ms
                    result_meta["total_read_chars"] = total_read_chars
                    result_meta["read_chars"] = int(read_chars)
                    result_evidence = result_meta.get("evidence_chunk_ids")
                    if isinstance(result_evidence, list):
                        for chunk_id in result_evidence:
                            clean_chunk_id = str(chunk_id).strip()
                            if not clean_chunk_id or clean_chunk_id in evidence_seen:
                                continue
                            evidence_seen.add(clean_chunk_id)
                            evidence_chunk_ids.append(clean_chunk_id)
                    if bool(result_meta.get("proposal_created", False)) or bool(
                        result_meta.get("document_written", False)
                    ):
                        round_had_progress = True
                    if bool(result_meta.get("skip_document_requested", False)):
                        round_had_progress = True
                    tool_logs.append(
                        {
                            "round_no": round_no,
                            "task_type": task_type,
                            "agent": agent_name,
                            "tool_name": tool_name,
                            "args": args,
                            "result_meta": result_meta,
                            "created_at": utc_now().isoformat(),
                        }
                    )
                    tool_result_blocks.append(
                        self._tool_result_for_prompt(
                            round_no=round_no,
                            tool_name=tool_name,
                            arguments=args,
                            result_payload=result_payload,
                        )
                    )
                # Keep prompt growth bounded while preserving most recent context.
                if len(tool_result_blocks) > 12:
                    tool_result_blocks = tool_result_blocks[-12:]
                if round_had_progress:
                    no_progress_rounds = 0
                else:
                    no_progress_rounds += 1
                if (
                    no_progress_rounds >= no_progress_limit
                    and round_no < max_rounds
                    and not force_final_only
                ):
                    force_final_only = True
                    fallback_content = (
                        "工具调用连续无新增有效信息，已切换为阶段性收敛模式。"
                    )
                    tool_result_blocks.append(
                        "[SystemNote] No new information in consecutive rounds."
                        " Return final answer without any tool_calls."
                    )
                    round_status = "force_finalize"
                elif round_no < max_rounds:
                    round_status = "tool_calls"
                else:
                    round_status = "max_rounds_reached"
            elif force_final_only and not final_candidate:
                round_status = "force_finalize_no_final"
            else:
                no_progress_rounds += 1
                if (
                    no_progress_rounds >= no_progress_limit
                    and round_no < max_rounds
                    and not force_final_only
                ):
                    force_final_only = True
                    fallback_content = "工具调用连续无新增有效信息，已切换为阶段性收敛模式。"
                    tool_result_blocks.append(
                        "[SystemNote] No valid tool action was returned."
                        " Return final answer without any tool_calls."
                    )
                    round_status = "force_finalize"
                elif round_no < max_rounds:
                    round_status = "no_action"
                else:
                    round_status = "max_rounds_reached"
            round_logs.append(
                {
                    "round_no": round_no,
                    "task_type": task_type,
                    "agent": agent_name,
                    "prompt_hash": prompt_hash,
                    "prompt_tokens": int(response.prompt_tokens),
                    "completion_tokens": int(response.completion_tokens),
                    "status": (
                        "tool_calls_limited"
                        if truncated_calls and round_status == "tool_calls"
                        else round_status
                    ),
                    "created_at": utc_now().isoformat(),
                }
            )
            if round_status in {"tool_calls", "force_finalize", "no_action"}:
                continue
            if force_final_only and not final_candidate:
                final_content = fallback_content or "已达到无进展阈值，请给出阶段性结论。"
            elif round_status == "max_rounds_reached" and not final_candidate:
                final_content = fallback_content or "已达到最大轮次，请给出阶段性结论。"
            else:
                final_content = final_candidate or str(response.content or "").strip()
            break
        if last_response is None:
            return LLMResponse(
                ok=False,
                content="",
                error_code="generic",
                error_message="tool loop ended without response",
                provider="unknown",
            )
        final_raw = dict(last_response.raw) if isinstance(last_response.raw, dict) else {}
        final_raw["agent_loop_rounds"] = round_logs
        final_raw["agent_tool_calls"] = tool_logs
        final_raw["tool_loop_total_read_chars"] = total_read_chars
        final_raw["tool_evidence_chunk_ids"] = evidence_chunk_ids
        final_raw["tool_loop_limits"] = {
            "max_rounds": max_rounds,
            "max_calls_per_round": max_calls_per_round,
            "single_read_char_limit": single_read_char_limit,
            "total_read_char_limit": total_read_char_limit,
            "no_progress_limit": no_progress_limit,
            "write_proposal_enabled": write_proposal_enabled,
        }
        final_raw["agent_loop_metrics"] = self._build_agent_loop_metrics(
            round_logs=round_logs,
            tool_logs=tool_logs,
            total_read_chars=total_read_chars,
            evidence_chunk_count=len(evidence_chunk_ids),
        )
        return LLMResponse(
            ok=True,
            content=final_content or str(last_response.content or "").strip(),
            reasoning=last_response.reasoning,
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            provider=last_response.provider,
            raw=final_raw,
        )

    def _build_tool_loop_prompt(
        self,
        *,
        base_prompt: str,
        round_no: int,
        tool_result_blocks: list[str],
        max_rounds: int,
        max_calls_per_round: int,
        single_read_char_limit: int,
        total_read_char_limit: int,
        write_proposal_enabled: bool,
        force_final_only: bool,
        write_document_enabled: bool = False,
        write_document_required: bool = False,
        allow_skip_document: bool = False,
        node_tools_visible: bool = False,
    ) -> str:
        tool_names = [
            "search_text",
            "read_chunk",
            "read_neighbors",
            "get_chapter_outline",
            "get_world_state",
            "get_effective_directives",
        ]
        if node_tools_visible:
            tool_names.extend(
                [
                    "list_nodes",
                    "get_node",
                    "create_node",
                    "split_node",
                    "update_node",
                    "create_edge",
                    "delete_node(confirm required)",
                ]
            )
        if write_proposal_enabled:
            tool_names.append("propose_setting_change")
        if write_document_enabled:
            tool_names.append("write_document")
        if allow_skip_document:
            tool_names.append("skip_document")
        lines: list[str] = [str(base_prompt or "").strip(), ""]
        lines.extend(
            [
                "[ToolLoopContract]",
                "You may either provide final answer directly, or return JSON object:",
                '{"action":"tool_calls","tool_calls":[{"name":"search_text","arguments":{"query":"...","top_k":5}}]}',
                '{"action":"final","final_answer":"..."}',
                "Legacy format is also accepted:",
                '{"tool_calls":[{"name":"search_text","arguments":{"query":"...","top_k":5}}],'
                '"final_answer":"..."}',
                "Allowed tools: " + ", ".join(tool_names) + ".",
                (
                    "Limits: "
                    f"max_rounds={max_rounds}, "
                    f"max_tool_calls_per_round={max_calls_per_round}, "
                    f"single_read_char_limit={single_read_char_limit}, "
                    f"total_read_char_limit={total_read_char_limit}."
                ),
                "When using source text, include chunk_id references in final answer if possible.",
            ]
        )
        if write_document_enabled and write_document_required:
            lines.extend(
                [
                    "",
                    "[IMPORTANT] You MUST use write_document tool to write content, DO NOT output content directly.",
                    'Example: {"action":"tool_calls","tool_calls":[{"name":"write_document","arguments":{"document_type":"constitution","content":"..."}}]}',
                    "Valid document_type: constitution, clarify, specification, plan.",
                ]
            )
        elif write_document_enabled:
            lines.extend(
                [
                    "",
                    "[GuideDraftMode]",
                    "When requirements are still unclear, ask one concise clarification question.",
                    "When enough information is available, call write_document to persist one or more docs.",
                    "Do not output long story/chapter content in guide mode.",
                ]
            )
        if allow_skip_document:
            lines.extend(
                [
                    "[SkipRule]",
                    "Only call skip_document when user explicitly confirms skipping a specific doc.",
                    "Do not skip docs by assumption.",
                ]
            )
        if node_tools_visible:
            lines.extend(
                [
                    "[GraphMutationRule]",
                    "When mutating graph, prefer create_node/update_node/create_edge.",
                    "delete_node is sensitive and requires confirm=true.",
                ]
            )
        if force_final_only:
            lines.extend(
                [
                    "",
                    "[FinalizationMode]",
                    "Do not call tools. Return final_answer directly with current evidence.",
                ]
            )
        if tool_result_blocks:
            lines.extend(["", f"[ToolResults:Round{round_no - 1}]", *tool_result_blocks[-8:]])
            lines.extend(["", "If information is enough now, output final answer directly."])
        return "\n".join(lines).strip()

    def _parse_tool_loop_payload(self, text: str) -> dict[str, Any]:
        payload = self._parse_outline_guide_payload(str(text or ""), strict_json_fence=False)
        if not payload:
            return {
                "tool_calls": [],
                "final_content": str(text or "").strip(),
                "action": "",
            }
        raw_calls = payload.get("tool_calls")
        if not isinstance(raw_calls, list):
            raw_calls = payload.get("tools")
        if not isinstance(raw_calls, list):
            raw_calls = payload.get("tool_uses")
        calls: list[dict[str, Any]] = []
        if isinstance(raw_calls, list):
            for item in raw_calls:
                if not isinstance(item, dict):
                    continue
                name = str(
                    item.get("name")
                    or item.get("tool")
                    or item.get("tool_name")
                    or ""
                ).strip()
                if not name:
                    continue
                raw_args = item.get("arguments", item.get("args", {}))
                if isinstance(raw_args, str):
                    try:
                        loaded = json.loads(raw_args)
                    except Exception:
                        loaded = {}
                    raw_args = loaded
                if not isinstance(raw_args, dict):
                    raw_args = {}
                calls.append({"name": name.lower(), "arguments": raw_args})
        final_content = str(
            payload.get("final_answer")
            or payload.get("final_content")
            or payload.get("content")
            or payload.get("answer")
            or ""
        ).strip()
        action = self._normalize_tool_loop_action(
            payload.get("action")
            or payload.get("next_action")
            or payload.get("loop_action")
            or payload.get("decision")
            or ""
        )
        return {"tool_calls": calls, "final_content": final_content, "action": action}

    def _parse_tool_loop_response(self, response: LLMResponse) -> dict[str, Any]:
        parsed = self._parse_tool_loop_payload(response.content)
        tool_calls = list(cast(list[dict[str, Any]], parsed.get("tool_calls", [])))
        final_content = str(parsed.get("final_content", "") or "").strip()
        action = self._normalize_tool_loop_action(parsed.get("action", ""))
        raw = response.raw if isinstance(response.raw, dict) else {}
        if not raw:
            return {
                "tool_calls": tool_calls,
                "final_content": final_content,
                "action": action,
            }

        raw_action = self._normalize_tool_loop_action(
            raw.get("action")
            or raw.get("next_action")
            or raw.get("loop_action")
            or raw.get("decision")
            or ""
        )
        if raw_action:
            action = raw_action

        raw_final_content = str(
            raw.get("final_answer")
            or raw.get("final_content")
            or raw.get("answer")
            or raw.get("content_text")
            or ""
        ).strip()

        raw_calls: list[dict[str, Any]] = []
        for key in ("tool_calls", "tools", "tool_uses"):
            value = raw.get(key)
            if isinstance(value, list):
                raw_calls.extend(self._parse_tool_call_items(value))

        raw_content = raw.get("content")
        if isinstance(raw_content, list):
            text_blocks: list[str] = []
            for block in raw_content:
                if not isinstance(block, dict):
                    continue
                block_type = str(block.get("type") or "").strip().lower()
                if block_type in {"tool_use", "tool_call", "function_call"}:
                    raw_calls.extend(self._parse_tool_call_items([block]))
                    continue
                if block_type in {"text", "output_text"}:
                    text = str(block.get("text") or block.get("content") or "").strip()
                    if text:
                        text_blocks.append(text)
            if text_blocks and not raw_final_content:
                raw_final_content = "\n".join(text_blocks).strip()

        if raw_calls:
            tool_calls = raw_calls
            if not action:
                action = "tool_calls"
        if raw_final_content:
            final_content = raw_final_content

        return {
            "tool_calls": tool_calls,
            "final_content": final_content,
            "action": action,
        }

    def _normalize_tool_loop_action(self, value: Any) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {"tool_calls", "tool_call", "call_tools", "tools", "continue", "next"}:
            return "tool_calls"
        if normalized in {"final", "finalize", "done", "complete", "answer", "stop"}:
            return "final"
        return ""

    def _parse_tool_call_items(self, items: list[Any]) -> list[dict[str, Any]]:
        calls: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(
                item.get("name")
                or item.get("tool")
                or item.get("tool_name")
                or ""
            ).strip()
            if not name:
                continue
            raw_args = item.get("input", item.get("arguments", item.get("args", {})))
            if isinstance(raw_args, str):
                try:
                    loaded = json.loads(raw_args)
                except Exception:
                    loaded = {}
                raw_args = loaded
            if not isinstance(raw_args, dict):
                raw_args = {}
            calls.append({"name": name.lower(), "arguments": raw_args})
        return calls

    def _tool_result_for_prompt(
        self,
        *,
        round_no: int,
        tool_name: str,
        arguments: dict[str, Any],
        result_payload: Any,
    ) -> str:
        args_json = json.dumps(arguments, ensure_ascii=False, sort_keys=True)
        if len(args_json) > 320:
            args_json = args_json[:320] + "...(truncated)"
        result_json = json.dumps(result_payload, ensure_ascii=False, sort_keys=True)
        if len(result_json) > 1200:
            result_json = result_json[:1200] + "...(truncated)"
            
        base_str = (
            f"round={round_no} tool={tool_name}\n"
            f"args={args_json}\n"
            f"result={result_json}"
        )
        if isinstance(result_payload, dict) and "error" in result_payload:
            base_str += "\n[SystemNote] Tool call failed due to argument/execution error. Please fix and retry."
            
        return base_str
    def _build_agent_loop_metrics(
        self,
        *,
        round_logs: list[dict[str, Any]],
        tool_logs: list[dict[str, Any]],
        total_read_chars: int,
        evidence_chunk_count: int,
    ) -> dict[str, Any]:
        prompt_tokens = 0
        completion_tokens = 0
        for item in round_logs:
            try:
                prompt_tokens += int(item.get("prompt_tokens", 0))
            except (TypeError, ValueError):
                pass
            try:
                completion_tokens += int(item.get("completion_tokens", 0))
            except (TypeError, ValueError):
                pass
        tool_errors = 0
        cache_hits = 0
        proposal_created = 0
        document_written = 0
        truncated_reads = 0
        for call in tool_logs:
            result_meta = call.get("result_meta")
            if not isinstance(result_meta, dict):
                result_meta = {}
            if not bool(result_meta.get("ok", False)):
                tool_errors += 1
            if bool(result_meta.get("cache_hit", False)):
                cache_hits += 1
            if bool(result_meta.get("proposal_created", False)):
                proposal_created += 1
            if bool(result_meta.get("document_written", False)):
                document_written += 1
            if bool(result_meta.get("truncated", False)):
                truncated_reads += 1
        round_statuses = [str(item.get("status", "")) for item in round_logs]
        return {
            "round_count": len(round_logs),
            "tool_call_count": len(tool_logs),
            "tool_error_count": tool_errors,
            "cache_hit_count": cache_hits,
            "proposal_created_count": proposal_created,
            "document_written_count": document_written,
            "truncated_read_count": truncated_reads,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_read_chars": int(total_read_chars),
            "evidence_chunk_count": int(evidence_chunk_count),
            "final_status": round_statuses[-1] if round_statuses else "",
        }

    def _agent_name_for_task(self, task_type: str) -> str:
        mapping = {
            "chapter_plan": "planner",
            "chapter_write": "writer",
            "chapter_review": "reviewer",
            "chapter_synthesize": "synthesizer",
            "chapter_correction": "correction",
            "generate_chapter": "single",
            "chat_writer": "writer",
        }
        return mapping.get(str(task_type or "").strip(), "single")

    def _extract_agent_loop_audits(
        self,
        response: LLMResponse,
        *,
        default_task_type: str,
        default_agent: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        def _as_int(value: Any, *, fallback: int) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return fallback

        raw = response.raw if isinstance(response.raw, dict) else {}
        raw_rounds = raw.get("agent_loop_rounds")
        raw_tools = raw.get("agent_tool_calls")
        rounds: list[dict[str, Any]] = []
        if isinstance(raw_rounds, list):
            for item in raw_rounds:
                if not isinstance(item, dict):
                    continue
                rounds.append(
                    {
                        "round_no": max(1, _as_int(item.get("round_no", 1), fallback=1)),
                        "task_type": str(item.get("task_type") or default_task_type),
                        "agent": str(item.get("agent") or default_agent),
                        "prompt_hash": str(item.get("prompt_hash") or ""),
                        "prompt_tokens": max(0, _as_int(item.get("prompt_tokens", 0), fallback=0)),
                        "completion_tokens": max(
                            0, _as_int(item.get("completion_tokens", 0), fallback=0)
                        ),
                        "status": str(item.get("status") or "final"),
                        "created_at": str(item.get("created_at") or utc_now().isoformat()),
                    }
                )
        tools: list[dict[str, Any]] = []
        if isinstance(raw_tools, list):
            for item in raw_tools:
                if not isinstance(item, dict):
                    continue
                args = item.get("args")
                if not isinstance(args, dict):
                    args = {}
                result_meta = item.get("result_meta")
                if not isinstance(result_meta, dict):
                    result_meta = {}
                tools.append(
                    {
                        "round_no": max(1, _as_int(item.get("round_no", 1), fallback=1)),
                        "task_type": str(item.get("task_type") or default_task_type),
                        "agent": str(item.get("agent") or default_agent),
                        "tool_name": str(item.get("tool_name") or ""),
                        "args": args,
                        "result_meta": result_meta,
                        "created_at": str(item.get("created_at") or utc_now().isoformat()),
                    }
                )
        return rounds, tools

    def _extract_agent_loop_meta(self, response: LLMResponse) -> tuple[dict[str, Any], list[str]]:
        raw = response.raw if isinstance(response.raw, dict) else {}
        raw_metrics = raw.get("agent_loop_metrics")
        metrics = dict(raw_metrics) if isinstance(raw_metrics, dict) else {}
        raw_evidence = raw.get("tool_evidence_chunk_ids")
        evidence: list[str] = []
        if isinstance(raw_evidence, list):
            seen: set[str] = set()
            for item in raw_evidence:
                chunk_id = str(item or "").strip()
                if not chunk_id or chunk_id in seen:
                    continue
                seen.add(chunk_id)
                evidence.append(chunk_id)
        return metrics, evidence

    def _collect_flow_agent_loop_audits(
        self,
        flow_state: WorkflowState,
        *,
        workflow_mode: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        rounds: list[dict[str, Any]] = []
        tools: list[dict[str, Any]] = []
        if workflow_mode == "multi_agent":
            specs = [
                ("planner_response", "chapter_plan", "planner"),
                ("writer_response", "chapter_write", "writer"),
                ("reviewer_response", "chapter_review", "reviewer"),
                ("llm_response", "chapter_synthesize", "synthesizer"),
            ]
        else:
            specs = [("llm_response", "generate_chapter", "single")]
        for key, task_type, agent in specs:
            response = flow_state.get(key)
            if not isinstance(response, LLMResponse):
                continue
            item_rounds, item_tools = self._extract_agent_loop_audits(
                response,
                default_task_type=task_type,
                default_agent=agent,
            )
            rounds.extend(item_rounds)
            tools.extend(item_tools)
        return rounds, tools

    def _collect_flow_agent_loop_meta(
        self,
        flow_state: WorkflowState,
        *,
        workflow_mode: str,
    ) -> tuple[dict[str, Any], list[str]]:
        if workflow_mode == "multi_agent":
            keys = [
                "planner_response",
                "writer_response",
                "reviewer_response",
                "llm_response",
            ]
        else:
            keys = ["llm_response"]
        merged_metrics: dict[str, Any] = {
            "round_count": 0,
            "tool_call_count": 0,
            "tool_error_count": 0,
            "cache_hit_count": 0,
            "proposal_created_count": 0,
            "truncated_read_count": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_read_chars": 0,
            "evidence_chunk_count": 0,
            "final_status": "",
        }
        evidence: list[str] = []
        seen: set[str] = set()
        for key in keys:
            response = flow_state.get(key)
            if not isinstance(response, LLMResponse):
                continue
            metrics, response_evidence = self._extract_agent_loop_meta(response)
            for sum_key in (
                "round_count",
                "tool_call_count",
                "tool_error_count",
                "cache_hit_count",
                "proposal_created_count",
                "truncated_read_count",
                "prompt_tokens",
                "completion_tokens",
                "total_read_chars",
            ):
                try:
                    merged_metrics[sum_key] = int(merged_metrics.get(sum_key, 0)) + int(metrics.get(sum_key, 0))
                except (TypeError, ValueError):
                    continue
            status = str(metrics.get("final_status", "")).strip()
            if status:
                merged_metrics["final_status"] = status
            for chunk_id in response_evidence:
                if chunk_id in seen:
                    continue
                seen.add(chunk_id)
                evidence.append(chunk_id)
        merged_metrics["evidence_chunk_count"] = len(evidence)
        return merged_metrics, evidence

