"""Context/state-sync helper methods for AIService."""

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


class AIServiceStateSyncMixin:
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

    def _sync_state_after_llm_write(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_id: str,
        content: str,
    ) -> dict[str, Any]:
        if self.state_service is None:
            return {
                "state_events": 0,
                "proposal_count": 0,
                "applied_count": 0,
            }
        clean_content = str(content or "").strip()
        clean_thread = str(thread_id or "").strip() or generate_id("thread")
        if not clean_content:
            return {
                "state_events": 0,
                "proposal_count": 0,
                "applied_count": 0,
            }
        try:
            llm_gate = self._plan_state_sync_with_llm(
                project_id=project_id,
                node_id=node_id,
                content=clean_content,
            )
            gate_reason = str(llm_gate.get("reason") or "").strip()
            if bool(llm_gate.get("ok")) and not bool(llm_gate.get("should_write_state")):
                return {
                    "state_events": 0,
                    "proposal_count": 0,
                    "applied_count": 0,
                    "decision_source": "llm_gate_skip",
                    "reason": gate_reason,
                }

            llm_events = [item for item in llm_gate.get("events", []) if isinstance(item, dict)]
            llm_event_apply: dict[str, Any] | None = None
            if llm_events:
                llm_event_apply = self._apply_state_events(
                    project_id=project_id,
                    node_id=node_id,
                    thread_id=clean_thread,
                    events=llm_events,
                )
                if "error" not in llm_event_apply:
                    return {
                        **llm_event_apply,
                        "decision_source": "llm_events",
                        "reason": gate_reason,
                    }

            extracted = self.state_service.extract_state_events(project_id, node_id, clean_content)
            events = [item for item in extracted.get("events", []) if isinstance(item, dict)]
            if not events:
                source = "rules_only"
                if bool(llm_gate.get("ok")):
                    source = "llm_gate_no_events"
                return {
                    "state_events": 0,
                    "proposal_count": 0,
                    "applied_count": 0,
                    "decision_source": source,
                    "reason": gate_reason,
                }

            rule_apply = self._apply_state_events(
                project_id=project_id,
                node_id=node_id,
                thread_id=clean_thread,
                events=events,
            )
            if "error" in rule_apply:
                return rule_apply
            if llm_event_apply and "error" in llm_event_apply:
                return {
                    **rule_apply,
                    "decision_source": "llm_events_fallback_rules",
                    "reason": gate_reason,
                }
            if bool(llm_gate.get("ok")):
                return {
                    **rule_apply,
                    "decision_source": "llm_gate_then_rules",
                    "reason": gate_reason,
                }
            return {
                **rule_apply,
                "decision_source": "rules_only",
            }
        except Exception:
            return {
                "state_events": 0,
                "proposal_count": 0,
                "applied_count": 0,
                "error": "state_sync_failed",
            }

    def _apply_state_events(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_id: str,
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if self.state_service is None:
            return {
                "state_events": 0,
                "proposal_count": 0,
                "applied_count": 0,
            }
        normalized_events = [item for item in events if isinstance(item, dict)]
        if not normalized_events:
            return {
                "state_events": 0,
                "proposal_count": 0,
                "applied_count": 0,
            }
        try:
            proposals = self.state_service.create_state_change_proposals(
                project_id,
                node_id,
                thread_id,
                normalized_events,
            )
            proposal_ids: list[str] = []
            for proposal in proposals:
                proposal_id = str(proposal.get("id", "")).strip()
                if not proposal_id:
                    continue
                reviewed = self.state_service.review_state_change_proposal(
                    proposal_id,
                    "approved",
                    "llm_auto",
                    "auto-approved after LLM write",
                )
                if str(reviewed.get("status", "")).strip().lower() == "approved":
                    proposal_ids.append(proposal_id)
            if not proposal_ids:
                return {
                    "state_events": len(normalized_events),
                    "proposal_count": len(proposals),
                    "applied_count": 0,
                }
            apply_result = self.state_service.apply_approved_state_changes(
                project_id,
                node_id,
                thread_id,
                proposal_ids=proposal_ids,
            )
            return {
                "state_events": len(normalized_events),
                "proposal_count": len(proposals),
                "applied_count": int(apply_result.get("applied_count", 0)),
                "conflict_count": int(apply_result.get("conflict_count", 0)),
            }
        except Exception:
            return {
                "state_events": len(normalized_events),
                "proposal_count": 0,
                "applied_count": 0,
                "error": "state_sync_failed",
            }

    def _plan_state_sync_with_llm(
        self,
        *,
        project_id: str,
        node_id: str,
        content: str,
    ) -> dict[str, Any]:
        clean_content = str(content or "").strip()
        if not clean_content:
            return {
                "ok": True,
                "should_write_state": False,
                "reason": "empty_content",
                "events": [],
            }
        snippet = clean_content[:2200]
        prompt = (
            "你是剧情世界状态同步决策器。请基于新写入正文判断是否需要写入状态库。"
            "\n\n只输出 JSON，不要代码块，不要解释。格式：\n"
            "{\n"
            '  "should_write_state": true,\n'
            '  "reason": "一句话原因",\n'
            '  "events": [\n'
            "    {\n"
            '      "entity_type": "character|item|relationship|world_variable",\n'
            '      "event_type": "事件类型",\n'
            '      "canonical_id": "角色或物品ID（character/item时可填）",\n'
            '      "subject_character_id": "关系主体（relationship时可填）",\n'
            '      "object_character_id": "关系客体（relationship时可填）",\n'
            '      "variable_key": "世界变量key（world_variable时可填）",\n'
            '      "payload": {},\n'
            '      "source_excerpt": "证据原句",\n'
            '      "confidence": 0.0\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            "要求：\n"
            "1) 若正文没有明确、可持续的状态变化，should_write_state 必须是 false，events 为空数组。\n"
            "2) 只有高置信度且有文本证据的变化才写入 events。\n"
            "3) relation_type 可以是任意文本，不限制枚举。\n"
            "4) 若不确定，宁可不写。\n\n"
            "[node_id]\n"
            f"{node_id}\n\n"
            "[new_content]\n"
            f"{snippet}\n"
        )
        try:
            response = self._generate(
                task_type="state_sync_gate",
                prompt=prompt,
                platform_config={
                    "token_budget": 420,
                    "disable_tool_loop": True,
                },
                project_id=project_id,
            )
            parsed = self._parse_outline_guide_payload(
                response.content,
                strict_json_fence=False,
            )
            if not isinstance(parsed, dict) or not parsed:
                return {
                    "ok": False,
                    "should_write_state": False,
                    "reason": "state_gate_unparsed",
                    "events": [],
                }
            raw_events = parsed.get("events")
            events: list[dict[str, Any]] = []
            if isinstance(raw_events, list):
                for item in raw_events[:32]:
                    if isinstance(item, dict):
                        events.append(item)
            has_flag = "should_write_state" in parsed
            should_write_state = bool(events)
            if has_flag:
                should_write_state = self._coerce_bool(parsed.get("should_write_state"), default=False)
            reason = str(parsed.get("reason") or "").strip()
            return {
                "ok": True,
                "should_write_state": should_write_state,
                "reason": reason,
                "events": events,
            }
        except Exception:
            return {
                "ok": False,
                "should_write_state": False,
                "reason": "state_gate_error",
                "events": [],
            }

    def _coerce_bool(self, value: Any, *, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            text = value.strip().lower()
            if text in {"1", "true", "yes", "on", "y"}:
                return True
            if text in {"0", "false", "no", "off", "n"}:
                return False
        return default

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
